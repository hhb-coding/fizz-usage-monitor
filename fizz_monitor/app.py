"""Read-only dashboard / 只读仪表盘。"""
import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, render_template
from . import __version__
from .db import connect, data_directory, check_schema, DataError
from .alerts import evaluate_alerts

TZ = ZoneInfo('America/Toronto')

def snapshot(conn, now=None):
    now = now or datetime.now(TZ)
    now = now.astimezone(TZ)
    today = now.date()
    accounts = []
    for row in conn.execute('SELECT * FROM accounts ORDER BY account_id'):
        account = dict(row)
        aid = account['account_id']
        history = {r['date']:dict(r) for r in conn.execute('SELECT * FROM daily_usage WHERE account_id=? AND date BETWEEN ? AND ?', (aid,str(today-timedelta(days=30)),str(today-timedelta(days=1))))}
        days = [{'date':str(today-timedelta(days=d)), 'usage_mb':history.get(str(today-timedelta(days=d)),{}).get('usage_mb'),'source':history.get(str(today-timedelta(days=d)),{}).get('source')} for d in range(30,0,-1)]
        status = conn.execute('SELECT * FROM collection_status WHERE account_id=?',(aid,)).fetchone()
        status = dict(status) if status else {'last_success_at':None,'failed':0}
        # Malformed/naive/future timestamps cannot establish fresh data.
        # 无效、无时区或未来时间戳不能证明数据新鲜。
        stale = True
        if status['last_success_at']:
            try:
                success = datetime.fromisoformat(status['last_success_at'])
                stale = success.tzinfo is None or success > now or (now-success).total_seconds() > float(os.environ.get('FIZZ_STALE_HOURS','36'))*3600
            except (ValueError, TypeError):
                stale = True
        wallet = conn.execute('SELECT * FROM wallet_snapshots WHERE account_id=? ORDER BY collected_at DESC LIMIT 1',(aid,)).fetchone()
        plan = conn.execute('SELECT * FROM plan_charges WHERE account_id=? AND cycle_start<=? ORDER BY cycle_start DESC LIMIT 1',(aid,str(today))).fetchone()
        bucket_snapshot = [dict(r) for r in conn.execute('SELECT * FROM data_buckets WHERE account_id=? AND collected_at=(SELECT MAX(collected_at) FROM data_buckets WHERE account_id=?)',(aid,aid))]
        buckets = [b for b in bucket_snapshot if b['expires_on'] >= str(today)]
        has_bucket_snapshot = conn.execute('SELECT 1 FROM data_buckets WHERE account_id=? LIMIT 1', (aid,)).fetchone() is not None
        account.update(history=days,recent_days=days[-3:],known_days=sum(d['usage_mb'] is not None for d in days),usage_30d_mb=sum(d['usage_mb'] or 0 for d in days),status=status,stale=stale,wallet=dict(wallet) if wallet else None,plan=dict(plan) if plan else None,buckets=buckets,total_available_mb=sum(b['remaining_mb'] for b in buckets) if has_bucket_snapshot else None)
        account['bucket_snapshot'] = bucket_snapshot
        accounts.append(account)
    return {'timezone':'America/Toronto','as_of':now.isoformat(),'accounts':accounts}

def create_app(data_dir=None):
    app = Flask(__name__)
    # Freeze configuration at startup; all requests use the same database.
    # 启动时固定路径，避免请求期间环境变量变更导致切换数据库。
    app.config['FIZZ_DATA_DIR'] = data_directory(data_dir)
    threshold = int(os.environ.get('FIZZ_LOW_DATA_MB', '1000'))
    if threshold <= 0:
        raise ValueError('FIZZ_LOW_DATA_MB must be a positive integer')
    app.config['FIZZ_LOW_DATA_MB'] = threshold
    app.config['FIZZ_STALE_HOURS'] = float(os.environ.get('FIZZ_STALE_HOURS','36'))
    messages = {
        'database_missing': '数据库不存在：请使用相同 FIZZ_DATA_DIR 初始化并写入模拟数据。',
        'database_not_initialized': '数据库尚未初始化：请先执行 init 和 demo。',
        'unsafe_directory_permissions': '私有数据目录权限不符合要求，应为 700。',
        'unsafe_database_permissions': '数据库权限不符合要求，应为 600。',
    }
    def error_code(exc):
        return exc.code if isinstance(exc, DataError) else 'data_unavailable'
    def read():
        conn = connect(app.config['FIZZ_DATA_DIR'], readonly=True)
        try:
            check_schema(conn)
            return snapshot(conn)
        finally:
            conn.close()
    @app.get('/')
    def dashboard():
        try:
            return render_template('dashboard.html',data=read(),error=False)
        except (sqlite3.Error, ValueError, OSError) as exc:
            code = error_code(exc)
            return render_template('dashboard.html',data=None,error=True,error_message=messages.get(code,'读取失败：数据暂不可用。请检查本地数据库及私有目录权限。'),error_code=code),503
    @app.get('/api/v1/summary')
    def summary():
        try:
            return jsonify(read())
        except (sqlite3.Error, ValueError, OSError) as exc:
            return jsonify(error=error_code(exc)),503
    @app.get('/lite')
    def lite():
        try:
            data = read()
            now = datetime.fromisoformat(data['as_of'])
            for account in data['accounts']:
                account['alerts'] = evaluate_alerts(account, now, app.config['FIZZ_LOW_DATA_MB'], app.config['FIZZ_STALE_HOURS'])
            return render_template('lite.html',data=data,error=False,threshold=app.config['FIZZ_LOW_DATA_MB'])
        except (sqlite3.Error, ValueError, OSError) as exc:
            code = error_code(exc)
            return render_template('lite.html',data=None,error=True,error_code=code,error_message=messages.get(code,'读取失败：流量状态未知。'),threshold=app.config['FIZZ_LOW_DATA_MB']),503
    @app.get('/health')
    def health():
        try:
            data = read()
            return jsonify(status='ok',project='fizz-usage-monitor',version=__version__,database='readable',stale_accounts=[a['account_id'] for a in data['accounts'] if a['stale']],failed_accounts=[a['account_id'] for a in data['accounts'] if a['status']['failed']])
        except (sqlite3.Error, ValueError, OSError) as exc:
            return jsonify(status='error',error=error_code(exc)),503
    @app.after_request
    def headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'"
        return response
    return app
