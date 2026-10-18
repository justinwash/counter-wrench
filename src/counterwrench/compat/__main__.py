"""Try the engine by hand: python -m counterwrench.compat <bike_id> <category> [--tire-width MM]"""

from __future__ import annotations

import argparse
import sys

from counterwrench.compat.lookup import find_compatible_parts
from counterwrench.db.connection import connect
from counterwrench.models import PartCategory


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m counterwrench.compat")
    parser.add_argument("bike_id")
    parser.add_argument("category", choices=[c.value for c in PartCategory])
    parser.add_argument("--tire-width", type=int, help="installed tire width (mm), for tubes")
    args = parser.parse_args()

    with connect() as conn:
        try:
            results = find_compatible_parts(
                conn, args.bike_id, PartCategory(args.category), args.tire_width
            )
        except LookupError as exc:
            print(exc)
            return 1
    for r in results:
        where = f" [{r.position}]" if r.position else ""
        adapter = f"  (adapter: {r.requires_adapter})" if r.requires_adapter else ""
        print(f"{r.status.upper():<13}{r.part_id}{where}{adapter}")
        print(f"{'':13}{r.reasons[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
