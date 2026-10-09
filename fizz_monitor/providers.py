"""Providers contain no authentication code / 数据源不包含认证代码。"""
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from .db import upsert

class Provider(ABC):
    @abstractmethod
    def collect(self, now):
        """Return normalized records; never infer daily usage from bucket deltas.
        返回标准记录；禁止通过剩余流量差值推断日用量。
        """

class ManualImportProvider(Provider):
    def collect(self, now):
        raise NotImplementedError('Manual import format is reserved for Step 2.')

class BrowserProvider(Provider):
    """Interface only. Implement privately outside the public project.
    仅接口：未来实现必须存放在公共项目之外的私有模块。
    """
    def collect(self, now):
        raise NotImplementedError('No browser, login, or network collection implemented.')

class MockProvider(Provider):
    def collect(self, now):
        if now.tzinfo is None:
            raise ValueError('Timezone-aware collection timestamp required')
        now = now.astimezone(ZoneInfo('America/Toronto'))
        today = now.date()
        timestamp = now.isoformat()
        records = []
        for index, account in enumerate(('account_a','account_b')):
            base = {'account_id':account,'source':'synthetic/mock'}
            for offset in (-50,-20):
                start = today + timedelta(days=offset)
                records.append(('billing_cycles', dict(base,start_date=str(start),end_date=str(start+timedelta(days=29))), ('account_id','start_date')))
                records.append(('plan_charges', dict(base,cycle_start=str(start),amount_cents=2500+index*700,currency='CAD',next_payment_date=str(start+timedelta(days=30))), ('account_id','cycle_start')))
            records.append(('wallet_snapshots',dict(base,collected_at=timestamp,balance_cents=1200+index*500),('account_id','collected_at')))
            for n, kind in enumerate(('plan','rollover','gift','perk','addon')):
                records.append(('data_buckets',dict(base,bucket_id=kind,kind=kind,remaining_mb=1000+n*200+index*100,total_mb=2000+n*200,expires_on=str(today+timedelta(days=10+n*8)),collected_at=timestamp),('account_id','bucket_id','collected_at')))
            for days in range(1,41):
                if days in (2,7): # Deliberate missing values / 故意保留缺失日
                    continue
                usage = 0 if days == 3 else (days*73+index*41)%600
                records.append(('daily_usage',dict(base,date=str(today-timedelta(days=days)),usage_mb=usage,updated_at=timestamp),('account_id','date')))
            records.append(('collection_status',dict(account_id=account,last_success_at=timestamp,failed=0,last_attempt_at=timestamp,error_code=None),('account_id',)))
        return records

def import_records(conn, records):
    """Atomic trusted provider import / 可信 Provider 的原子导入。"""
    allowed = {'billing_cycles':('account_id','start_date'),'plan_charges':('account_id','cycle_start'),'wallet_snapshots':('account_id','collected_at'),'data_buckets':('account_id','bucket_id','collected_at'),'daily_usage':('account_id','date'),'collection_status':('account_id',)}
    with conn:
        for table, values, keys in records:
            if table not in allowed or tuple(keys) != allowed[table]:
                raise ValueError('Unsupported record type')
            # Column names originate only from the schema, never arbitrary SQL.
            columns = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
            if not set(values) <= columns:
                raise ValueError('Unknown column')
            for field in ('usage_mb','amount_cents','balance_cents','remaining_mb','total_mb'):
                if field in values and type(values[field]) is not int:
                    raise ValueError('Amounts and usage must be integers')
            for field in ('date','start_date','end_date','cycle_start','next_payment_date','expires_on'):
                if field in values:
                    parsed = date.fromisoformat(values[field])
                    if parsed.isoformat() != values[field]:
                        raise ValueError('Dates must use YYYY-MM-DD')
            for field in ('collected_at','updated_at','last_success_at','last_attempt_at'):
                if values.get(field) is not None:
                    if datetime.fromisoformat(values[field]).tzinfo is None:
                        raise ValueError('Timezone-aware timestamp required')
            upsert(conn,table,values,keys)
