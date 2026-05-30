from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Generator

_use_mysql = os.getenv("MYSQL_HOST") is not None
DB_PATH = os.path.join(os.path.dirname(__file__), "commerce.db")


def get_db_connection():
    if _use_mysql:
        import pymysql
        conn = pymysql.connect(
            host=os.getenv("MYSQL_HOST", "localhost"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("MYSQL_DATABASE", "smart_cs"),
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
        _orig_cursor = conn.cursor
        _orig_commit = conn.commit
        _cursor = [None]

        def _exec(query: str, params: tuple | None = None) -> Any:
            if params:
                query = query.replace("?", "%s")
            _cursor[0] = _orig_cursor()
            _cursor[0].execute(query, params)
            return _cursor[0]

        def _cursor_wrapper() -> Any:
            raw_cursor = _orig_cursor()
            _orig_cursor_execute = raw_cursor.execute

            def _cursor_execute(query: str, params: tuple | None = None) -> Any:
                if params:
                    query = query.replace("?", "%s")
                _orig_cursor_execute(query, params)
                return raw_cursor

            raw_cursor.execute = _cursor_execute
            return raw_cursor

        conn.execute = _exec
        conn.cursor = _cursor_wrapper

        def _commit() -> None:
            _orig_commit()

        conn.commit = _commit

        return conn
    else:
        conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn


@contextmanager
def db_transaction() -> Generator:
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def db_query() -> Generator:
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()
