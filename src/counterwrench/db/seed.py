"""Load the seed files and sync them into the catalog tables.

Two phases, so a bad file never leaves a half-seeded catalog:
1. Load and validate every entry in every file. Any error stops here, naming file and entry.
2. Sync each table to match the files in one transaction: insert new rows, update changed
   ones, delete rows that are gone from the files. Re-running with unchanged files is a no-op.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg
import yaml
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, TypeAdapter, ValidationError

from counterwrench.catalog import Bike, CompatRule, LaborItem, Part
from counterwrench.db.connection import connect
from counterwrench.taxonomy import pairs

SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "seed"


class SeedError(Exception):
    pass


@dataclass
class SeedData:
    bikes: list[Bike]
    parts: list[BaseModel]
    compat_rules: list[CompatRule]
    labor_menu: list[LaborItem]


@dataclass
class TableChanges:
    added: int = 0
    updated: int = 0
    removed: int = 0

    def __str__(self) -> str:
        return f"{self.added} added, {self.updated} updated, {self.removed} removed"


@dataclass
class SyncReport:
    tables: dict[str, TableChanges] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return any(c.added or c.updated or c.removed for c in self.tables.values())


# --- Phase 1: load and validate --------------------------------------------------------------


def _load_file(
    directory: Path, filename: str, adapter: TypeAdapter, keys: Sequence[str]
) -> list[Any]:
    """Validate every entry; reject duplicates on `keys` (the table's primary key)."""
    path = directory / filename
    if not path.exists():
        raise SeedError(f"{filename}: missing from {directory}")
    raw = yaml.safe_load(path.read_text("utf-8")) or []
    if not isinstance(raw, list):
        raise SeedError(f"{filename}: expected a list of entries at the top level")
    entries, seen = [], set()
    for index, item in enumerate(raw, start=1):
        label = "/".join(str(item.get(k, "?")) for k in keys) if isinstance(item, dict) else "?"
        try:
            entry = adapter.validate_python(item)
        except ValidationError as exc:
            raise SeedError(f"{filename} entry {index} ({label}):\n{exc}") from exc
        identity = tuple(getattr(entry, k) for k in keys)
        if identity in seen:
            raise SeedError(f"{filename} entry {index}: duplicate {label}")
        seen.add(identity)
        entries.append(entry)
    return entries


def load_seed(directory: Path = SEED_DIR) -> SeedData:
    rule_keys = ["rule_type", "bike_value", "part_value"]
    return SeedData(
        bikes=_load_file(directory, "bikes.yaml", TypeAdapter(Bike), ["id"]),
        parts=_load_file(directory, "parts.yaml", TypeAdapter(Part), ["id"]),
        compat_rules=_load_file(directory, "compat_rules.yaml", TypeAdapter(CompatRule), rule_keys),
        labor_menu=_load_file(directory, "labor_menu.yaml", TypeAdapter(LaborItem), ["code"]),
    )


# --- Phase 2: sync ---------------------------------------------------------------------------


def _sync_table(
    conn: psycopg.Connection, table: str, keys: Sequence[str], rows: list[dict[str, Any]]
) -> TableChanges:
    """Make `table` contain exactly `rows`, matched on the `keys` columns."""
    changes = TableChanges()
    columns = list(rows[0]) if rows else list(keys)
    ident = sql.Identifier
    select = sql.SQL("SELECT {} FROM {}").format(
        sql.SQL(", ").join(map(ident, columns)), ident(table)
    )
    cursor = conn.cursor(row_factory=dict_row)
    existing = {tuple(r[k] for k in keys): r for r in cursor.execute(select).fetchall()}
    desired = {tuple(r[k] for k in keys): r for r in rows}

    where = sql.SQL(" AND ").join(sql.SQL("{} = %s").format(ident(k)) for k in keys)
    for key, row in desired.items():
        params = [Jsonb(v) if isinstance(v, dict) else v for v in row.values()]
        if key not in existing:
            conn.execute(
                sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    ident(table),
                    sql.SQL(", ").join(map(ident, row)),
                    sql.SQL(", ").join(sql.Placeholder() * len(row)),
                ),
                params,
            )
            changes.added += 1
        elif existing[key] != row:
            values = [p for c, p in zip(row, params, strict=True) if c not in keys]
            conn.execute(
                sql.SQL("UPDATE {} SET {} WHERE {}").format(
                    ident(table),
                    sql.SQL(", ").join(
                        sql.SQL("{} = %s").format(ident(c)) for c in row if c not in keys
                    ),
                    where,
                ),
                [*values, *key],
            )
            changes.updated += 1
    for key in existing.keys() - desired.keys():
        conn.execute(sql.SQL("DELETE FROM {} WHERE {}").format(ident(table), where), key)
        changes.removed += 1
    return changes


def sync(conn: psycopg.Connection, data: SeedData) -> SyncReport:
    """Sync all catalog tables in one transaction."""
    bikes = [b.model_dump(mode="json", exclude={"source"}) for b in data.bikes]
    parts = [p.model_dump(mode="json") for p in data.parts]
    rules = [r.model_dump(mode="json") for r in data.compat_rules]
    labor = [item.model_dump(mode="json") for item in data.labor_menu]
    taxonomy = [{"complaint": c, "suspected_area": a} for c, a in pairs()]

    report = SyncReport()
    with conn.transaction():
        report.tables["bikes"] = _sync_table(conn, "bikes", ["id"], bikes)
        report.tables["parts"] = _sync_table(conn, "parts", ["id"], parts)
        report.tables["compat_rules"] = _sync_table(
            conn, "compat_rules", ["rule_type", "bike_value", "part_value"], rules
        )
        report.tables["labor_menu"] = _sync_table(conn, "labor_menu", ["code"], labor)
        report.tables["complaint_taxonomy"] = _sync_table(
            conn, "complaint_taxonomy", ["complaint", "suspected_area"], taxonomy
        )
    return report


def main() -> int:
    try:
        data = load_seed()
    except SeedError as exc:
        print(f"Seed files are invalid; nothing was written.\n{exc}")
        return 1
    try:
        with connect(autocommit=True) as conn:
            report = sync(conn, data)
    except psycopg.OperationalError as exc:
        print(f"Can't connect to Postgres ({exc}). Is it running? Try `make up`.")
        return 1
    for table, changes in report.tables.items():
        print(f"{table:<20} {changes}")
    print("seeded" if report.changed else "already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
