import hashlib
import os
import unittest
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from backend.store import RunStore


def create_test_store(test_case: unittest.TestCase, namespace: Path) -> RunStore:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        raise unittest.SkipTest("Set TEST_DATABASE_URL to a dedicated PostgreSQL test database")
    schema = "test_" + hashlib.sha256(str(namespace.resolve()).encode()).hexdigest()[:24]
    with psycopg.connect(database_url) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))

    def cleanup():
        with psycopg.connect(database_url) as connection:
            connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))

    test_case.addCleanup(cleanup)
    return RunStore(make_conninfo(database_url, options=f"-c search_path={schema}"))
