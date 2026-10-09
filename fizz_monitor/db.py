"""Integer storage and transactional UPSERT / 整数存储及事务更新。"""
import os
import sqlite3
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS accounts(account_id TEXT PRIMARY KEY, alias TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS billing_cycles(account_id TEXT NOT NULL REFERENCES accounts, start_date TEXT NOT NULL, end_date TEXT NOT NULL, source TEXT NOT NULL, PRIMARY KEY(account_id,start_date), CHECK(end_date>=start_date));
CREATE TABLE IF NOT EXISTS plan_charges(account_id TEXT NOT NULL REFERENCES accounts, cycle_start TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK(typeof(amount_cents)='integer' AND amount_cents>=0), currency TEXT NOT NULL CHECK(currency='CAD'), next_payment_date TEXT NOT NULL, source TEXT NOT NULL, PRIMARY KEY(account_id,cycle_start));
CREATE TABLE IF NOT EXISTS wallet_snapshots(account_id TEXT NOT NULL REFERENCES accounts, collected_at TEXT NOT NULL, balance_cents INTEGER NOT NULL CHECK(typeof(balance_cents)='integer' AND balance_cents>=0), source TEXT NOT NULL, PRIMARY KEY(account_id,collected_at));
CREATE TABLE IF NOT EXISTS data_buckets(account_id TEXT NOT NULL REFERENCES accounts, bucket_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('plan','rollover','gift','perk','addon')), remaining_mb INTEGER NOT NULL CHECK(typeof(remaining_mb)='integer' AND remaining_mb>=0), total_mb INTEGER NOT NULL CHECK(typeof(total_mb)='integer' AND total_mb>=remaining_mb), expires_on TEXT NOT NULL, collected_at TEXT NOT NULL, source TEXT NOT NULL, PRIMARY KEY(account_id,bucket_id,collected_at));
CREATE TABLE IF NOT EXISTS daily_usage(account_id TEXT NOT NULL REFERENCES accounts, date TEXT NOT NULL, usage_mb INTEGER NOT NULL CHECK(typeof(usage_mb)='integer' AND usage_mb>=0), source TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(account_id,date));
CREATE TABLE IF NOT EXISTS collection_status(account_id TEXT PRIMARY KEY REFERENCES accounts, last_success_at TEXT, failed INTEGER NOT NULL DEFAULT 0 CHECK(failed IN (0,1)), last_attempt_at TEXT, error_code TEXT);
'''

class DataError(ValueError):
    """Safe diagnostic codes, without personal data / 不包含个人数据的诊断码。"""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def data_directory(data_dir=None):
    """Resolve one stable path / 解析稳定的数据目录。"""
    configured = data_dir if data_dir is not None else os.environ.get('FIZZ_DATA_DIR')
    if configured is not None and not str(configured).strip():
        raise DataError('empty_data_directory')
    return Path(configured or '~/.local/share/fizz-usage-monitor').expanduser().absolute()


def check_schema(conn):
    required = {'accounts', 'billing_cycles', 'plan_charges', 'wallet_snapshots',
                'data_buckets', 'daily_usage', 'collection_status'}
    present = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not required <= present:
        raise DataError('database_not_initialized')


def connect(data_dir=None, readonly=False):
    directory = data_directory(data_dir)
    if directory.is_symlink():
        raise DataError('data_directory_symlink')
    if readonly and not (directory / 'monitor.sqlite3').is_file():
        raise DataError('database_missing')
    if not readonly:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Refuse unsafe existing paths instead of changing user-owned permissions.
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise DataError('unsafe_directory_permissions')
    path = directory / 'monitor.sqlite3'
    if path.is_symlink():
        raise DataError('database_symlink')
    if not path.exists():
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
    if path.stat().st_mode & 0o077:
        raise DataError('unsafe_database_permissions')
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) if readonly else sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def initialize(conn):
    conn.executescript(SCHEMA)
    with conn:
        conn.executemany('INSERT OR IGNORE INTO accounts VALUES (?,?)', [('account_a','Account A'),('account_b','Account B')])

def upsert(conn, table, values, keys):
    columns = list(values)
    updates = ','.join(f'{c}=excluded.{c}' for c in columns if c not in keys)
    conn.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)}) ON CONFLICT ({','.join(keys)}) DO UPDATE SET {updates}", list(values.values()))
