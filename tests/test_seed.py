import shutil
from pathlib import Path

import pytest
import yaml
from psycopg import errors

import counterwrench.db.seed as seed_module
from counterwrench.catalog import Bike, WheelSize
from counterwrench.db.migrate import migrate
from counterwrench.db.seed import SEED_DIR, SeedError, load_seed, sync
from counterwrench.taxonomy import pairs


@pytest.fixture
def seed_dir(tmp_path: Path) -> Path:
    """A private copy of the real seed files that each test can edit."""
    target = tmp_path / "seed"
    shutil.copytree(SEED_DIR, target)
    return target


@pytest.fixture
def catalog(conn):
    migrate(conn)
    return conn


def edit(directory: Path, filename: str, change) -> None:
    path = directory / filename
    entries = yaml.safe_load(path.read_text("utf-8"))
    change(entries)
    path.write_text(yaml.safe_dump(entries, sort_keys=False), "utf-8")


def count(conn, table: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


# --- Loading and validation (no database) ----------------------------------------------------


def test_real_seed_files_are_valid():
    data = load_seed()
    assert data.bikes and data.parts and data.compat_rules and data.labor_menu


def test_wheel_label_names_both_conventions():
    assert WheelSize(622).label == '622 mm (700c / 29")'
    assert WheelSize(584).label == '584 mm (650b / 27.5")'


@pytest.mark.parametrize(
    ("filename", "change", "message"),
    [
        ("bikes.yaml", lambda e: e[0].update(freehub="microsplne"), "freehub"),
        ("bikes.yaml", lambda e: e[0].update(rotor_mount=None), "rotor_mount"),
        ("bikes.yaml", lambda e: e[0].update(front_wheel_bsd_mm=630), "front_wheel_bsd_mm"),
        ("bikes.yaml", lambda e: e[0].pop("udh"), "udh"),
        ("bikes.yaml", lambda e: e.append(dict(e[0])), "duplicate"),
        ("parts.yaml", lambda e: e[0].update(price_cents=-1), "price_cents"),
        ("parts.yaml", lambda e: e[0].update(category="frame"), "category"),
        ("parts.yaml", lambda e: e[0]["specs"].update(largest_cog=9), "largest_cog"),
        ("parts.yaml", lambda e: e[0]["specs"].update(speeds=12, chain_type="x"), "Extra"),
        ("compat_rules.yaml", lambda e: e[1].update(adapter="hope"), "adapter"),
        ("labor_menu.yaml", lambda e: e[0].update(code="seatpost adjust"), "code"),
    ],
)
def test_invalid_entry_names_file_and_entry(seed_dir, filename, change, message):
    edit(seed_dir, filename, change)
    with pytest.raises(SeedError, match=filename) as excinfo:
        load_seed(seed_dir)
    assert message in str(excinfo.value)


def test_cassette_specs_are_typed_by_category():
    cassette = next(p for p in load_seed().parts if p.category == "cassette")
    assert cassette.specs.freehub == "microspline"


# --- Sync (real database) ----------------------------------------------------------------------


def test_seed_loads_everything(catalog):
    data = load_seed()
    report = sync(catalog, data)
    assert report.changed
    assert count(catalog, "bikes") == len(data.bikes)
    assert count(catalog, "parts") == len(data.parts)
    assert count(catalog, "compat_rules") == len(data.compat_rules)
    assert count(catalog, "labor_menu") == len(data.labor_menu)


def test_second_seed_changes_nothing(catalog):
    sync(catalog, load_seed())
    assert not sync(catalog, load_seed()).changed


def test_taxonomy_table_matches_code(catalog):
    sync(catalog, load_seed())
    rows = catalog.execute(
        "SELECT complaint, suspected_area FROM complaint_taxonomy ORDER BY 1, 2"
    ).fetchall()
    assert rows == pairs()


def test_changed_price_updates_one_row(catalog, seed_dir):
    sync(catalog, load_seed(seed_dir))
    edit(seed_dir, "parts.yaml", lambda e: e[0].update(price_cents=9999))
    report = sync(catalog, load_seed(seed_dir))
    assert (report.tables["parts"].updated, report.tables["parts"].added) == (1, 0)
    price = catalog.execute("SELECT price_cents FROM parts WHERE id = 'sample-cassette-12s-ms'")
    assert price.fetchone() == (9999,)


def test_changed_specs_update_the_row(catalog, seed_dir):
    sync(catalog, load_seed(seed_dir))
    edit(seed_dir, "parts.yaml", lambda e: e[0]["specs"].update(largest_cog=52))
    assert sync(catalog, load_seed(seed_dir)).tables["parts"].updated == 1


def test_removed_entry_is_deleted(catalog, seed_dir):
    sync(catalog, load_seed(seed_dir))
    edit(seed_dir, "parts.yaml", lambda e: e.pop())
    report = sync(catalog, load_seed(seed_dir))
    assert report.tables["parts"].removed == 1
    assert count(catalog, "parts") == len(load_seed(seed_dir).parts)


def test_duplicate_bike_passes_pydantic_but_not_the_database(catalog, seed_dir):
    # Each entry is valid on its own; only the DB sees both and enforces unique make/model/year.
    data = load_seed(seed_dir)
    data.bikes.append(Bike.model_validate({**data.bikes[0].model_dump(), "id": "dupe-bike"}))
    with pytest.raises(errors.UniqueViolation):
        sync(catalog, data)
    assert count(catalog, "bikes") == 0


def test_failure_after_updates_rolls_back_the_updates(catalog, seed_dir, monkeypatch):
    sync(catalog, load_seed(seed_dir))
    data = load_seed(seed_dir)
    data.parts[0] = data.parts[0].model_copy(update={"price_cents": 1})

    # Fail on a table synced *after* parts, so the price update has really run first.
    real_sync_table = seed_module._sync_table
    applied = []

    def fail_on_labor(conn, table, keys, rows):
        if table == "labor_menu":
            applied.append(conn.execute(PRICE_SQL).fetchone())
            raise RuntimeError("refused")
        return real_sync_table(conn, table, keys, rows)

    monkeypatch.setattr(seed_module, "_sync_table", fail_on_labor)
    with pytest.raises(RuntimeError):
        sync(catalog, data)
    assert applied == [(1,)]  # the update happened inside the transaction...
    assert catalog.execute(PRICE_SQL).fetchone() == (12999,)  # ...and was rolled back


PRICE_SQL = "SELECT price_cents FROM parts WHERE id = 'sample-cassette-12s-ms'"


def test_source_url_is_not_stored(catalog):
    sync(catalog, load_seed())
    columns = catalog.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'bikes'"
    ).fetchall()
    assert ("source",) not in columns
