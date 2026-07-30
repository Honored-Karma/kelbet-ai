"""Export FastAPI OpenAPI schema to docs/openapi/v1.json."""

from __future__ import annotations

import json
from pathlib import Path

from apps.api.main import create_app


def main() -> None:
    app = create_app(testing=True)
    schema = app.openapi()
    out = Path(__file__).resolve().parents[1] / "docs" / "openapi" / "v1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
