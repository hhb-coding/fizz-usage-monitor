"""CLI / 命令行工具。"""
import argparse
import os
import sqlite3
from datetime import datetime
from .app import create_app, TZ
from .db import connect, initialize, data_directory, check_schema
from .demo import prepare_demo
from .providers import MockProvider, import_records

def main():
    parser = argparse.ArgumentParser(description='Local Fizz monitor — synthetic/mock only')
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init')
    sub.add_parser('demo')
    sub.add_parser('doctor')
    alias = sub.add_parser('alias')
    alias.add_argument('account_id',choices=['account_a','account_b'])
    alias.add_argument('name')
    serve = sub.add_parser('serve')
    serve.add_argument('--port',type=int,default=int(os.environ.get('FIZZ_PORT','5000')))
    start_demo = sub.add_parser('start-demo')
    start_demo.add_argument('--port',type=int,default=int(os.environ.get('FIZZ_PORT','5000')))
    args = parser.parse_args()
    if args.command in ('serve', 'start-demo', 'doctor'):
        try:
            directory = prepare_demo() if args.command == 'start-demo' else data_directory()
            conn = connect(directory, readonly=True)
            try:
                check_schema(conn)
                if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('database_integrity_failed')
            finally:
                conn.close()
        except (ValueError, OSError, sqlite3.Error) as exc:
            # Do not print raw exceptions which might contain private information.
            # 不输出可能包含个人信息的原始异常。
            code = getattr(exc, 'code', 'startup_check_failed')
            parser.exit(1, f'{code}: check FIZZ_DATA_DIR, initialization and permissions. Existing data is not replaced. / 请检查数据目录、初始化与权限；现有数据不会被替换。\n')
        print(f'Database / 数据库: {directory / "monitor.sqlite3"}', flush=True)
        print('Startup checks passed / 启动检查通过', flush=True)
        if args.command == 'doctor':
            return
        create_app(directory).run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False)
        return
    conn = connect()
    try:
        initialize(conn)
        if args.command == 'demo':
            # Never overwrite a real dataset / 禁止覆盖真实数据集
            for table in ('billing_cycles','plan_charges','wallet_snapshots','data_buckets','daily_usage'):
                if conn.execute(f"SELECT 1 FROM {table} WHERE source!='synthetic/mock' LIMIT 1").fetchone():
                    raise ValueError('Demo refused: existing non-mock records detected.')
            import_records(conn,MockProvider().collect(datetime.now(TZ)))
        elif args.command == 'alias':
            if not args.name.strip() or len(args.name)>80:
                parser.error('Alias must contain 1–80 characters')
            with conn:
                conn.execute('UPDATE accounts SET alias=? WHERE account_id=?',(args.name,args.account_id))
        print('Completed locally / 本地操作完成')
    finally:
        conn.close()

if __name__ == '__main__':
    main()
