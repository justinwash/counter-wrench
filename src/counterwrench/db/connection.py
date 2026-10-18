"""Postgres connection settings, shared by the app, migrations and tests."""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import quote

import psycopg
from dotenv import load_dotenv


def database_url(env: Mapping[str, str]) -> str:
    """DATABASE_URL if set; otherwise built from the same POSTGRES_* values (and defaults)
    that docker-compose.yml uses, so the two can't drift apart."""
    url = env.get("DATABASE_URL", "").strip()
    if url:
        return url
    user = env.get("POSTGRES_USER", "").strip() or "counterwrench"
    password = env.get("POSTGRES_PASSWORD", "").strip() or "counterwrench"
    db = env.get("POSTGRES_DB", "").strip() or "counterwrench"
    # Not "localhost": it can resolve to IPv6 ::1 first, and compose binds IPv4 127.0.0.1
    # only, so the connection hangs until the IPv6 attempt times out.
    host = env.get("POSTGRES_HOST", "").strip() or "127.0.0.1"
    port = env.get("POSTGRES_PORT", "").strip() or "5432"
    return f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}/{db}"


def connect(url: str | None = None, **kwargs) -> psycopg.Connection:
    if url is None:
        load_dotenv(override=False)
        url = database_url(os.environ)
    return psycopg.connect(url, **kwargs)
