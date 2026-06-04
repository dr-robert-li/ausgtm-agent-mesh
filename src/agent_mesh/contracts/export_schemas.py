"""Export JSON Schema for every contract model into ``schemas/contracts/``.

Run via ``python -m agent_mesh.contracts.export_schemas`` or ``make schemas``.
Non-Python consumers (Cloudflare Worker, MCP clients, dashboards) read these
generated files so there is a single source of truth for the contract.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_mesh.contracts.models import CONTRACT_MODELS

# Repo-root relative output dir. Resolved from this file's location so it works
# regardless of the current working directory.
_REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = _REPO_ROOT / "schemas" / "contracts"


def export(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in CONTRACT_MODELS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["title"] = name
        path = output_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
        written.append(path)
    return written


def main() -> None:
    written = export()
    for path in written:
        print(f"wrote {path.relative_to(_REPO_ROOT)}")


if __name__ == "__main__":
    main()
