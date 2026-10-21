"""Write the API's OpenAPI schema for the frontend's generated types: `make api-types`.

Built from the app itself (no server, no models: nothing is called while building the schema).
"""

import json
import sys
from pathlib import Path

from counterwrench.agent.nodes import Deps
from counterwrench.api.app import create_app


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "frontend/openapi.json")
    out.write_text(json.dumps(create_app(deps=Deps()).openapi(), indent=1) + "\n", "utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
