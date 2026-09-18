"""Print the OpenAPI schema as JSON: `python -m app.export_openapi > openapi.json`.

The frontend generates its TypeScript types from this file, so API and UI cannot drift apart
silently (CI regenerates it and fails on differences).
"""

import json
import sys

from app.core.config import Settings
from app.main import create_app


def main() -> None:
    app = create_app(Settings(_env_file=None))
    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
