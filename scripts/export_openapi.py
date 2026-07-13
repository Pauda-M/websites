"""Export the API's OpenAPI specification to shared/openapi/openapi.json.

The exported spec is the cross-language contract consumed by TypeScript
clients (packages/api-client) and external integrators.

Run from apps/api so the pb-api virtualenv is used:

    cd apps/api && uv run python ../../scripts/export_openapi.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "shared" / "openapi" / "openapi.json"


def main() -> int:
    from pb_api.core.config import Settings
    from pb_api.main import create_app

    # A minimal, deterministic settings object: no .env, no external services.
    settings = Settings.model_validate(
        {
            "environment": "test",
            "database_url": "sqlite+aiosqlite://",
            "redis_url": None,
            "secret_key": "openapi-export-not-a-runtime-secret-000000000000",
            "rate_limit_enabled": False,
        }
    )
    app = create_app(settings)
    spec = app.openapi()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)} ({len(spec.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
