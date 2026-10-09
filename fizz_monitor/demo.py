"""Persistent mock-only setup / 持久化模拟数据，不覆盖未知数据库。"""
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from .db import connect, data_directory, initialize, check_schema, DataError
from .providers import MockProvider, import_records


def prepare_demo(data_dir=None):
    directory = data_directory(data_dir)
    project = Path(__file__).resolve().parents[1]
    if directory.resolve().is_relative_to(project):
        raise DataError('demo_directory_inside_project')
    database = directory / 'monitor.sqlite3'
    marker = directory / '.synthetic-demo'
    if database.exists() or database.is_symlink():
        # Read only our marker, never inspect an unknown dataset.
        # 仅检查本工具标记；不读取未知数据库内容。
        if marker.is_symlink() or not marker.is_file() or marker.read_text() != 'synthetic/mock\n':
            raise DataError('existing_database_not_marked_demo')
        conn = connect(directory, readonly=True)
        try:
            check_schema(conn)
        finally:
            conn.close()
        return directory
    if directory.exists() and any(directory.iterdir()):
        raise DataError('existing_nonempty_directory')
    conn = connect(directory)
    try:
        initialize(conn)
        import_records(conn, MockProvider().collect(datetime.now(ZoneInfo('America/Toronto'))))
    finally:
        conn.close()
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write('synthetic/mock\n')
    return directory
