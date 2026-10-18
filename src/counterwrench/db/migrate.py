"""Minimal migration runner: applies numbered plain-SQL files in order.

- Files are `NNN_description.sql` in `migrations/`; each runs in its own transaction, so a
  failing migration leaves no partial changes.
- Applied versions are recorded in `schema_migrations` with a checksum. If an applied file
  is later edited, the runner refuses to continue: the database and a fresh database built
  from the files would silently differ. Fix forward with a new migration instead.
"""

from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg

from counterwrench.db.connection import connect

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
FILENAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")

CREATE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    int PRIMARY KEY,
    name       text NOT NULL,
    checksum   text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        # Normalize line endings so a Windows (CRLF) and a Mac/Linux (LF) checkout agree.
        return hashlib.sha256(self.sql.replace("\r\n", "\n").encode()).hexdigest()


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    migrations = []
    for path in sorted(directory.glob("*.sql")):
        match = FILENAME.match(path.name)
        if not match:
            raise MigrationError(f"{path.name}: migration files must be named NNN_description.sql")
        migrations.append(Migration(int(match.group(1)), path.name, path.read_text("utf-8")))
    versions = [m.version for m in migrations]
    if len(versions) != len(set(versions)):
        raise MigrationError(f"Duplicate migration version in {directory}")
    return migrations


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Apply pending migrations; return the ones applied. `conn` must be in autocommit mode
    so each migration gets its own transaction."""
    conn.execute(CREATE_TRACKING_TABLE)
    applied = dict(conn.execute("SELECT version, checksum FROM schema_migrations").fetchall())
    on_disk = discover(directory)

    missing = set(applied) - {m.version for m in on_disk}
    if missing:
        raise MigrationError(f"Database has migrations not on disk: {sorted(missing)}")

    pending = []
    for migration in on_disk:
        if migration.version not in applied:
            pending.append(migration)
        elif applied[migration.version] != migration.checksum:
            raise MigrationError(
                f"{migration.name} was edited after it was applied. "
                "Revert the edit and add a new migration instead."
            )

    for migration in pending:
        with conn.transaction():
            conn.execute(migration.sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, checksum) VALUES (%s, %s, %s)",
                (migration.version, migration.name, migration.checksum),
            )
    return pending


def main() -> int:
    try:
        with connect(autocommit=True) as conn:
            applied = migrate(conn)
    except psycopg.OperationalError as exc:
        print(f"Can't connect to Postgres ({exc}). Is it running? Try `make up`.")
        return 1
    except MigrationError as exc:
        print(f"Migration error: {exc}")
        return 1
    if applied:
        for migration in applied:
            print(f"applied {migration.name}")
    else:
        print("nothing to apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
