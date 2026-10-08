"""Write the OpenAPI contract to api/openapi.yaml.

Run from backend/: `uv run python -m app.openapi_export`
"""

import sys
from pathlib import Path

import yaml

from app.main import create_app

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "api" / "openapi.yaml"


class _Dumper(yaml.SafeDumper):
    """Writes multi-line strings as literal blocks so descriptions stay readable."""


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _represent_str)


def render() -> str:
    return yaml.dump(
        create_app().openapi(), Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100
    )


def main() -> int:
    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT_PATH.write_text(render(), encoding="utf-8", newline="\n")
    print(f"Wrote {CONTRACT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
