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


@pytest.fixture
def seeded_db(conn):
    """A test database with the real catalog seeded and the knowledge base ingested
    (fake embeddings, so no model download)."""
    from counterwrench.db.migrate import migrate
    from counterwrench.db.seed import load_seed, sync
    from counterwrench.rag.embed import FakeEmbedder
    from counterwrench.rag.ingest import build_chunks, ingest

    migrate(conn)
    sync(conn, load_seed())
    ingest(conn, build_chunks(conn), FakeEmbedder())
    return conn
