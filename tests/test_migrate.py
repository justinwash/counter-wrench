from pathlib import Path

import psycopg
import pytest
from psycopg import errors

from counterwrench.db.connection import database_url
from counterwrench.db.migrate import (
    MIGRATIONS_DIR,
    Migration,
    MigrationError,
    discover,
    migrate,
)


def write(directory: Path, name: str, sql: str) -> None:
    (directory / name).write_text(sql, "utf-8")


def tables(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
    return {row[0] for row in rows}


def versions(conn: psycopg.Connection) -> list[int]:
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return [row[0] for row in rows]


# --- Runner behavior (synthetic migrations) ---------------------------------------------


def test_applies_in_order_and_records(conn, tmp_path):
    write(tmp_path, "002_child.sql", "CREATE TABLE child (parent_id int REFERENCES parent);")
    write(tmp_path, "001_parent.sql", "CREATE TABLE parent (id int PRIMARY KEY);")
    applied = migrate(conn, tmp_path)
    assert [m.version for m in applied] == [1, 2]
    assert {"parent", "child"} <= tables(conn)
    assert versions(conn) == [1, 2]


def test_second_run_applies_nothing(conn, tmp_path):
    write(tmp_path, "001_a.sql", "CREATE TABLE a (id int);")
    migrate(conn, tmp_path)
    assert migrate(conn, tmp_path) == []


def test_later_migration_applies_to_existing_database(conn, tmp_path):
    write(tmp_path, "001_a.sql", "CREATE TABLE a (id int);")
    migrate(conn, tmp_path)
    conn.execute("INSERT INTO a VALUES (1)")
    write(tmp_path, "002_b.sql", "ALTER TABLE a ADD COLUMN note text;")
    assert [m.version for m in migrate(conn, tmp_path)] == [2]
    assert conn.execute("SELECT id, note FROM a").fetchall() == [(1, None)]


def test_failing_migration_rolls_back_completely(conn, tmp_path):
    write(tmp_path, "001_ok.sql", "CREATE TABLE ok (id int);")
    write(tmp_path, "002_bad.sql", "CREATE TABLE half (id int); SELECT 1 / 0;")
    with pytest.raises(errors.DivisionByZero):
        migrate(conn, tmp_path)
    assert "ok" in tables(conn)
    assert "half" not in tables(conn)
    assert versions(conn) == [1]


def test_edited_applied_migration_is_rejected(conn, tmp_path):
    write(tmp_path, "001_a.sql", "CREATE TABLE a (id int);")
    migrate(conn, tmp_path)
    write(tmp_path, "001_a.sql", "CREATE TABLE a (id int, sneaky text);")
    with pytest.raises(MigrationError, match="edited after it was applied"):
        migrate(conn, tmp_path)


def test_applied_migration_missing_from_disk_is_rejected(conn, tmp_path):
    write(tmp_path, "001_a.sql", "CREATE TABLE a (id int);")
    migrate(conn, tmp_path)
    (tmp_path / "001_a.sql").unlink()
    with pytest.raises(MigrationError, match="not on disk"):
        migrate(conn, tmp_path)


@pytest.mark.parametrize("bad_name", ["1_a.sql", "001-a.sql", "001_Add.sql", "abc_a.sql"])
def test_bad_filename_is_rejected(tmp_path, bad_name):
    write(tmp_path, bad_name, "SELECT 1;")
    with pytest.raises(MigrationError, match="NNN_description"):
        discover(tmp_path)


def test_duplicate_version_is_rejected(tmp_path):
    write(tmp_path, "001_a.sql", "SELECT 1;")
    write(tmp_path, "001_b.sql", "SELECT 1;")
    with pytest.raises(MigrationError, match="Duplicate"):
        discover(tmp_path)


def test_checksum_ignores_line_endings():
    assert Migration(1, "a", "SELECT 1;\r\nSELECT 2;").checksum == (
        Migration(1, "a", "SELECT 1;\nSELECT 2;").checksum
    )


# --- The real catalog schema --------------------------------------------------------------

BIKE = {
    "id": "trek-checkpoint-alr-5-2024",
    "make": "Trek",
    "model": "Checkpoint ALR 5",
    "year": 2024,
    "spec_variant": None,
    "variant_note": None,
    "category": "gravel",
    "bb_standard": "T47",
    "rear_axle": "12x142",
    "freehub": "HG",
    "drivetrain_speeds": 11,
    "udh": True,
    "brake_type": "hydraulic_disc",
    "brake_caliper": "Shimano GRX RX400",
    "rotor_mount": "centerlock",
    "max_tire_mm": 45,
    # Added by 002_bike_fit.sql
    "front_wheel_bsd_mm": 622,
    "rear_wheel_bsd_mm": 622,
    "crank_spindle": "hollowtech_24",
    "dropper_post": False,
    # Added by 003_rotor_sizes.sql
    "front_rotor_mm": 160,
    "rear_rotor_mm": 160,
}


def insert_bike(conn: psycopg.Connection, base: dict = BIKE, **overrides) -> None:
    row = {**base, **overrides}
    columns = ", ".join(row)
    placeholders = ", ".join(f"%({key})s" for key in row)
    conn.execute(f"INSERT INTO bikes ({columns}) VALUES ({placeholders})", row)


@pytest.fixture
def catalog(conn):
    migrate(conn)
    return conn


def test_catalog_migration_creates_tables(catalog):
    assert {"bikes", "parts", "compat_rules", "labor_menu", "complaint_taxonomy"} <= tables(catalog)


def test_valid_bike_inserts(catalog):
    insert_bike(catalog)
    assert catalog.execute("SELECT count(*) FROM bikes").fetchone() == (1,)


@pytest.mark.parametrize(
    "overrides",
    [
        {"brake_type": "magic"},
        {"category": "unicycle"},
        {"id": "Not A Slug"},
        {"drivetrain_speeds": 14},
        {"brake_type": "rim"},  # rim brake with a rotor mount and rotors
        {"rear_rotor_mm": None},  # disc brake missing a rear rotor size
        {"rotor_mount": None},  # disc brake without a rotor mount
        {"spec_variant": "late"},  # variant without a note saying how to tell
    ],
)
def test_bike_check_constraints(catalog, overrides):
    with pytest.raises(errors.CheckViolation):
        insert_bike(catalog, **overrides)


def test_udh_must_be_stated(catalog):
    with pytest.raises(errors.NotNullViolation):
        insert_bike(catalog, udh=None)


def test_duplicate_bike_without_variant_is_rejected(catalog):
    insert_bike(catalog)
    with pytest.raises(errors.UniqueViolation):
        insert_bike(catalog, id="trek-checkpoint-alr-5-2024-dupe")


def test_mid_year_variants_coexist(catalog):
    insert_bike(catalog, id="bike-early", spec_variant="early", variant_note="Serial before X")
    insert_bike(catalog, id="bike-late", spec_variant="late", variant_note="Serial X onward")
    assert catalog.execute("SELECT count(*) FROM bikes").fetchone() == (2,)


def test_part_rejects_negative_price_and_non_object_specs(catalog):
    sql = (
        "INSERT INTO parts (id, category, brand, name, price_cents, specs) "
        "VALUES (%s, %s, %s, %s, %s, %s)"
    )
    with pytest.raises(errors.CheckViolation):
        catalog.execute(sql, ("p1", "chain", "Shimano", "CN-M8100", -100, "{}"))
    with pytest.raises(errors.CheckViolation):
        catalog.execute(sql, ("p2", "chain", "Shimano", "CN-M8100", 4500, "[1, 2]"))


def test_incompatible_rule_cannot_have_adapter(catalog):
    with pytest.raises(errors.CheckViolation):
        catalog.execute(
            "INSERT INTO compat_rules (rule_type, bike_value, part_value, compatible, adapter) "
            "VALUES ('freehub_cassette', 'HG', 'XD', false, 'wishful thinking')"
        )


def test_database_url_built_from_postgres_vars():
    url = database_url({"POSTGRES_USER": "u", "POSTGRES_PASSWORD": "p@ss/word", "POSTGRES_DB": "d"})
    assert url == "postgresql://u:p%40ss%2Fword@127.0.0.1:5432/d"


def test_database_url_prefers_explicit_value():
    assert database_url({"DATABASE_URL": "postgresql://x", "POSTGRES_USER": "u"}) == (
        "postgresql://x"
    )


def test_rotor_split_backfills_existing_disc_bikes(conn, tmp_path):
    # Build the database as it was before 003, with a disc bike already in it...
    for path in sorted(MIGRATIONS_DIR.glob("00[12]_*.sql")):
        (tmp_path / path.name).write_text(path.read_text("utf-8"), "utf-8")
    migrate(conn, tmp_path)
    old_bike = {k: v for k, v in BIKE.items() if k not in ("front_rotor_mm", "rear_rotor_mm")}
    insert_bike(conn, base=old_bike, max_rotor_mm=180)
    # ...then apply the real migrations: 003 must carry the rotor size over, not reject the row.
    assert [m.name for m in migrate(conn)] == ["003_rotor_sizes.sql"]
    row = conn.execute("SELECT front_rotor_mm, rear_rotor_mm FROM bikes").fetchone()
    assert row == (180, 180)
