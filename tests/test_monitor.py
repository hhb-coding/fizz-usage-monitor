"""Isolated synthetic/mock fixtures only / 仅使用独立模拟测试数据。"""
import tempfile
import unittest
import sqlite3
from unittest.mock import patch
from datetime import datetime, timedelta
from pathlib import Path
from fizz_monitor.db import connect, initialize
from fizz_monitor.providers import MockProvider, import_records, BrowserProvider, ManualImportProvider
from fizz_monitor.app import snapshot, create_app, TZ

class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = connect(self.tmp.name)
        initialize(self.conn)
        self.now = datetime(2026,10,9,12,tzinfo=TZ)
        self.records = MockProvider().collect(self.now)
        import_records(self.conn,self.records)
    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()
    def test_account_isolation(self):
        accounts = snapshot(self.conn,self.now)['accounts']
        self.assertNotEqual(accounts[0]['wallet']['balance_cents'],accounts[1]['wallet']['balance_cents'])
        self.assertNotEqual(accounts[0]['recent_days'][-1]['usage_mb'],accounts[1]['recent_days'][-1]['usage_mb'])
    def test_cross_cycle_and_missing_zero(self):
        a = snapshot(self.conn,self.now)['accounts'][0]
        self.assertEqual(len(a['history']),30)
        self.assertEqual(a['recent_days'][0]['usage_mb'],0)
        self.assertIsNone(a['recent_days'][1]['usage_mb'])
        self.assertEqual(a['recent_days'][-1]['date'],'2026-10-08')
        self.assertIsNotNone(a['history'][0]['usage_mb'])
        cycles=list(self.conn.execute("SELECT start_date,end_date FROM billing_cycles WHERE account_id='account_a' ORDER BY start_date"))
        self.assertEqual(len(cycles),2)
        self.assertTrue(cycles[0]['start_date'] <= a['history'][0]['date'] <= cycles[0]['end_date'])
        self.assertTrue(cycles[1]['start_date'] <= a['recent_days'][-1]['date'] <= cycles[1]['end_date'])
    def test_duplicate_import(self):
        before = self.conn.execute('SELECT COUNT(*) FROM daily_usage').fetchone()[0]
        import_records(self.conn,self.records)
        self.assertEqual(before,self.conn.execute('SELECT COUNT(*) FROM daily_usage').fetchone()[0])
    def test_correction(self):
        import_records(self.conn,[('daily_usage',dict(account_id='account_a',date='2026-10-08',usage_mb=99,source='synthetic/mock',updated_at=self.now.isoformat()),('account_id','date'))])
        self.assertEqual(snapshot(self.conn,self.now)['accounts'][0]['recent_days'][-1]['usage_mb'],99)
        self.assertNotEqual(snapshot(self.conn,self.now)['accounts'][1]['recent_days'][-1]['usage_mb'],99)
    def test_atomic_failure_and_integer(self):
        bad=('daily_usage',dict(account_id='account_a',date='2026-10-08',usage_mb=1.5,source='synthetic/mock',updated_at=self.now.isoformat()),('account_id','date'))
        with self.assertRaises(ValueError): import_records(self.conn,[bad])
    def test_stale_failure(self):
        self.conn.execute("UPDATE collection_status SET failed=1 WHERE account_id='account_a'")
        a=snapshot(self.conn,self.now+timedelta(days=3))['accounts'][0]
        self.assertTrue(a['stale'])
        self.assertTrue(a['status']['failed'])
    def test_routes_read_only(self):
        client=create_app(self.tmp.name).test_client()
        for route in ('/','/health','/api/v1/summary'):
            self.assertEqual(client.get(route).status_code,200)
        self.assertEqual(client.post('/api/v1/summary').status_code,405)
        self.assertIn(b'synthetic/mock',client.get('/').data)
    def test_read_failure(self):
        self.conn.execute('DROP TABLE daily_usage')
        self.conn.commit()
        client=create_app(self.tmp.name).test_client()
        self.assertEqual(client.get('/').status_code,503)
        self.assertEqual(client.get('/health').status_code,503)
    def test_permissions(self):
        self.assertEqual(Path(self.tmp.name).stat().st_mode & 0o777,0o700)
        self.assertEqual((Path(self.tmp.name)/'monitor.sqlite3').stat().st_mode & 0o777,0o600)
    def test_interfaces_only(self):
        for cls in (BrowserProvider,ManualImportProvider):
            with self.assertRaises(NotImplementedError): cls().collect(self.now)

    def test_empty_initialized_dashboard(self):
        with tempfile.TemporaryDirectory() as directory:
            conn=connect(directory)
            initialize(conn)
            conn.close()
            client=create_app(directory).test_client()
            self.assertEqual(client.get('/').status_code,200)
            data=client.get('/api/v1/summary').get_json()
            self.assertEqual(len(data['accounts']),2)
            self.assertIsNone(data['accounts'][0]['total_available_mb'])
            self.assertEqual(data['accounts'][0]['known_days'],0)

    def test_all_expired_buckets_are_zero(self):
        self.conn.execute("UPDATE data_buckets SET expires_on='2026-10-01'")
        a=snapshot(self.conn,self.now)['accounts'][0]
        self.assertEqual(a['total_available_mb'],0)
        self.assertEqual(a['buckets'],[])

    def test_bucket_expiry_inclusive_and_latest_snapshot(self):
        self.conn.execute("UPDATE data_buckets SET expires_on='2026-10-09'")
        self.assertEqual(snapshot(self.conn,self.now)['accounts'][0]['total_available_mb'],7000)
        future=self.now+timedelta(hours=1)
        import_records(self.conn,[('data_buckets',dict(account_id='account_a',bucket_id='new',kind='gift',remaining_mb=42,total_mb=42,expires_on='2026-10-10',collected_at=future.isoformat(),source='synthetic/mock'),('account_id','bucket_id','collected_at'))])
        self.assertEqual(snapshot(self.conn,future)['accounts'][0]['total_available_mb'],42)
        self.assertEqual(snapshot(self.conn,future)['accounts'][1]['total_available_mb'],7500)

    def test_transaction_rolls_back_valid_first_record(self):
        first=('daily_usage',dict(account_id='account_a',date='2026-10-08',usage_mb=999,source='synthetic/mock',updated_at=self.now.isoformat()),('account_id','date'))
        second=('daily_usage',dict(account_id='unknown',date='2026-10-08',usage_mb=999,source='synthetic/mock',updated_at=self.now.isoformat()),('account_id','date'))
        with self.assertRaises(sqlite3.IntegrityError): import_records(self.conn,[first,second])
        self.assertEqual(snapshot(self.conn,self.now)['accounts'][0]['recent_days'][-1]['usage_mb'],73)

    def test_schema_and_all_table_idempotence(self):
        expected={'accounts','billing_cycles','plan_charges','wallet_snapshots','data_buckets','daily_usage','collection_status'}
        self.assertEqual({r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")},expected)
        before={t:self.conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in expected}
        import_records(self.conn,self.records)
        self.assertEqual(before,{t:self.conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in expected})
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("UPDATE daily_usage SET usage_mb=1.5 WHERE account_id='account_a'")

    def test_toronto_midnight_and_dst(self):
        from datetime import timezone
        # UTC Nov 2 04:30 is Nov 1 23:30 Toronto, after DST ends.
        now=datetime(2026,11,2,4,30,tzinfo=timezone.utc)
        self.assertEqual(snapshot(self.conn,now)['accounts'][0]['recent_days'][-1]['date'],'2026-10-31')
        records=MockProvider().collect(now)
        days=[v['date'] for t,v,k in records if t=='daily_usage']
        self.assertIn('2026-10-31',days)
        self.assertNotIn('2026-11-01',days)

    def test_bad_dates_and_naive_timestamps_rejected(self):
        for date_value, stamp in [('2026-02-30',self.now.isoformat()),('2026-10-08','2026-10-09T12:00:00')]:
            record=('daily_usage',dict(account_id='account_a',date=date_value,usage_mb=1,source='synthetic/mock',updated_at=stamp),('account_id','date'))
            with self.assertRaises(ValueError): import_records(self.conn,[record])

    def test_readonly_database_and_alias_preservation(self):
        with self.conn:
            self.conn.execute("UPDATE accounts SET alias='New alias' WHERE account_id='account_a'")
        initialize(self.conn)
        self.assertEqual(snapshot(self.conn,self.now)['accounts'][0]['alias'],'New alias')
        readonly=connect(self.tmp.name,readonly=True)
        try:
            with self.assertRaises(sqlite3.OperationalError): readonly.execute("DELETE FROM accounts")
        finally: readonly.close()

    def test_no_network_required_and_safe_headers(self):
        with patch('socket.socket',side_effect=AssertionError('Network prohibited')):
            records=MockProvider().collect(self.now)
            import_records(self.conn,records)
            client=create_app(self.tmp.name).test_client()
            response=client.get('/')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertIn("default-src 'self'",response.headers['Content-Security-Policy'])
            self.assertEqual(client.get('/health').get_json()['version'],'0.1.0')


    def test_missing_database_diagnostic_no_side_effect(self):
        directory=Path(self.tmp.name)/'not-created'
        client=create_app(directory).test_client()
        self.assertEqual(client.get('/health').get_json()['error'],'database_missing')
        self.assertEqual(client.get('/').status_code,503)
        self.assertIn(b'database_missing',client.get('/').data)
        self.assertFalse(directory.exists())

    def test_uninitialized_database_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            connect(directory).close()
            client=create_app(directory).test_client()
            self.assertEqual(client.get('/health').get_json()['error'],'database_not_initialized')

    def test_unsafe_permissions_diagnostics(self):
        root=Path(self.tmp.name)
        database=root/'monitor.sqlite3'
        root.chmod(0o755)
        try:
            self.assertEqual(create_app(root).test_client().get('/health').get_json()['error'],'unsafe_directory_permissions')
        finally: root.chmod(0o700)
        database.chmod(0o644)
        try:
            self.assertEqual(create_app(root).test_client().get('/health').get_json()['error'],'unsafe_database_permissions')
        finally: database.chmod(0o600)

    def test_environment_configuration_frozen(self):
        with patch.dict('os.environ',{'FIZZ_DATA_DIR':self.tmp.name}):
            app=create_app()
        with patch.dict('os.environ',{'FIZZ_DATA_DIR':'/tmp/nonexistent-fizz-config-test'}):
            self.assertEqual(app.test_client().get('/health').status_code,200)
        from fizz_monitor.db import data_directory, DataError
        with patch.dict('os.environ',{'FIZZ_DATA_DIR':''}):
            with self.assertRaises(DataError): data_directory()

    def test_persistent_demo_restart_and_no_overwrite(self):
        from fizz_monitor.demo import prepare_demo
        with tempfile.TemporaryDirectory() as parent:
            directory=Path(parent)/'persistent-demo'
            prepare_demo(directory)
            database=directory/'monitor.sqlite3'
            before=database.read_bytes()
            prepare_demo(directory)
            self.assertEqual(before,database.read_bytes())
            data=create_app(directory).test_client().get('/api/v1/summary').get_json()
            self.assertEqual([a['alias'] for a in data['accounts']],['Account A','Account B'])
            self.assertEqual(directory.stat().st_mode & 0o777,0o700)
            self.assertEqual(database.stat().st_mode & 0o777,0o600)
            (directory/'.synthetic-demo').unlink()
            with self.assertRaises(ValueError): prepare_demo(directory)
            self.assertEqual(before,database.read_bytes())

    def test_cli_doctor_and_missing_serve_preflight(self):
        import os, subprocess, sys
        env=dict(os.environ,FIZZ_DATA_DIR=self.tmp.name)
        result=subprocess.run([sys.executable,'-m','fizz_monitor','doctor'],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        env['FIZZ_DATA_DIR']=str(Path(self.tmp.name)/'missing')
        result=subprocess.run([sys.executable,'-m','fizz_monitor','serve'],env=env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('database_missing',result.stderr)
        self.assertNotIn('Serving Flask',result.stdout)


if __name__=='__main__': unittest.main()
