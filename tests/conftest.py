import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo

from counterwrench.db.connection import database_url


@pytest.fixture
def db_url() -> Iterator[str]:
    """A throwaway database per test, dropped afterwards. Skips if Postgres isn't running."""
    load_dotenv(override=False)
    admin_url = database_url(os.environ)
    name = f"cw_test_{uuid.uuid4().hex[:12]}"
    try:
        admin = psycopg.connect(admin_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres isn't running (make up)")
    with admin:
        admin.execute(f'CREATE DATABASE "{name}"')
        try:
            yield make_conninfo(admin_url, dbname=name)
        finally:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


@pytest.fixture
def conn(db_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(db_url, autocommit=True) as connection:
        yield connection
