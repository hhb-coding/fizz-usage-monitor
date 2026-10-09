"""Isolated synthetic alert scenarios / 独立模拟告警，不触碰运行数据库。"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from fizz_monitor.app import TZ, create_app, snapshot
from fizz_monitor.db import connect, initialize
from fizz_monitor.providers import import_records


class LiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.conn=connect(self.tmp.name)
        initialize(self.conn)
        self.now=datetime(2026,10,9,12,tzinfo=TZ)
        self.account('account_a',2000)
        self.account('account_b',3000)
        self.fixed=patch('fizz_monitor.app.snapshot',side_effect=lambda conn: snapshot(conn,self.now))
        self.fixed.start()
        self.client=create_app(self.tmp.name).test_client()

    def tearDown(self):
        self.fixed.stop()
        self.conn.close()
        self.tmp.cleanup()

    def account(self, aid, mb, expires=10, age=0, bucket_age=None, failed=0):
        self.conn.execute('DELETE FROM data_buckets WHERE account_id=?',(aid,))
        self.conn.commit()
        stamp=(self.now-timedelta(hours=age)).isoformat()
        bucket_stamp=(self.now-timedelta(hours=age if bucket_age is None else bucket_age)).isoformat()
        records=[('collection_status',dict(account_id=aid,last_success_at=stamp,last_attempt_at=stamp,failed=failed,error_code=None),('account_id',))]
        if mb is not None:
            records.append(('data_buckets',dict(account_id=aid,bucket_id='plan',kind='plan',remaining_mb=mb,total_mb=max(mb,3000),expires_on=str(self.now.date()+timedelta(days=expires)),collected_at=bucket_stamp,source='synthetic/mock'),('account_id','bucket_id','collected_at')))
        import_records(self.conn,records)

    def card(self, aid='account_a'):
        r=self.client.get('/lite')
        self.assertEqual(r.status_code,200)
        html=r.get_data(as_text=True)
        return html.split('id="'+aid+'"')[0].rsplit('<div class="account ',1)[-1]+html.split('id="'+aid+'"')[1].split('</div>',1)[0]

    def test_below_default_red(self):
        self.account('account_a',999)
        self.assertIn('low',self.card())
        self.assertIn('999 MB',self.card())

    def test_equal_threshold_green(self):
        self.account('account_a',1000)
        self.assertIn('normal',self.card())
        self.assertNotIn('低流量警告',self.card())

    def test_zero_red(self):
        self.account('account_a',0)
        self.assertIn('low',self.card())
        self.assertIn('0 MB',self.card())

    def test_missing_unknown(self):
        self.account('account_a',None)
        self.assertIn('unknown',self.card())
        self.assertNotIn('正常',self.card())

    def test_expired_bucket_excluded(self):
        self.account('account_a',4000,expires=-1)
        self.assertIn('low',self.card())
        self.assertIn('已过期',self.card())
        self.assertIn('0 MB',self.card())

    def test_three_days_yellow(self):
        self.account('account_a',2000,expires=3)
        self.assertIn('expiry',self.card())
        self.assertIn('3 天内到期',self.card())
        self.assertNotIn('正常',self.card())

    def test_expiration_today_inclusive(self):
        self.account('account_a',2000,expires=0)
        self.assertIn('2000 MB',self.card())
        self.assertIn('0 天内到期',self.card())

    def test_four_days_green(self):
        self.account('account_a',2000,expires=4)
        self.assertIn('normal',self.card())

    def test_stale_never_green(self):
        self.account('account_a',3000,age=37)
        self.assertIn('unknown',self.card())
        self.assertIn('数据陈旧',self.card())
        self.assertNotIn('正常',self.card())

    def test_old_bucket_even_with_recent_success(self):
        self.account('account_a',3000,age=0,bucket_age=37)
        self.assertIn('unknown',self.card())
        self.assertIn('数据陈旧',self.card())

    def test_failure_never_green(self):
        self.account('account_a',3000,failed=1)
        self.assertIn('unknown',self.card())
        self.assertIn('采集失败',self.card())

    def test_no_success_unknown(self):
        with self.conn:
            self.conn.execute("UPDATE collection_status SET last_success_at=NULL WHERE account_id='account_a'")
        self.assertIn('unknown',self.card())
        self.assertNotIn('正常',self.card())

    def test_accounts_independent(self):
        self.account('account_a',500,expires=2)
        self.assertIn('low',self.card('account_a'))
        self.assertIn('expiry',self.card('account_a'))
        self.assertIn('normal',self.card('account_b'))
        self.assertNotIn('低流量警告',self.card('account_b'))

    def test_custom_threshold_and_validation(self):
        with patch.dict(os.environ,{'FIZZ_LOW_DATA_MB':'2500'}):
            self.client=create_app(self.tmp.name).test_client()
        self.assertIn('low',self.card('account_a'))
        self.assertIn('normal',self.card('account_b'))
        for value in ['0','-1','1.5','invalid']:
            with patch.dict(os.environ,{'FIZZ_LOW_DATA_MB':value}):
                with self.assertRaises(ValueError): create_app(self.tmp.name)

    def test_read_failure_unknown_and_503(self):
        self.conn.execute('DROP TABLE daily_usage')
        self.conn.commit()
        response=self.client.get('/lite')
        self.assertEqual(response.status_code,503)
        html=response.get_data(as_text=True)
        self.assertIn('Account A',html)
        self.assertIn('Account B',html)
        self.assertIn('未知：读取失败',html)
        self.assertNotIn('正常：',html)

    def test_read_only_no_javascript_and_full_dashboard(self):
        database=Path(self.tmp.name)/'monitor.sqlite3'
        before=database.read_bytes()
        response=self.client.get('/lite')
        html=response.get_data(as_text=True)
        self.assertIn('返回完整 Dashboard',html)
        self.assertNotIn('<script',html)
        self.assertNotIn('https://',html)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(self.client.post('/lite').status_code,405)
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(before,database.read_bytes())
        with self.client.get('/static/lite.css') as css:
            self.assertEqual(css.status_code,200)

    def test_invalid_success_timestamps_never_green(self):
        for value in ['invalid','2026-10-09T12:00:00','2026-10-10T12:00:00-04:00']:
            with self.conn:
                self.conn.execute("UPDATE collection_status SET last_success_at=? WHERE account_id='account_a'",(value,))
            self.assertIn('unknown',self.card())
            self.assertNotIn('正常',self.card())

    def test_future_bucket_unknown(self):
        self.account('account_a',2000,bucket_age=-1)
        self.assertIn('unknown',self.card())
        self.assertNotIn('正常',self.card())
