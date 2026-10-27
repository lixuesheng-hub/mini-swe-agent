"""Check that the TL;DR block is identical in README.md and experiments/REPORT.md.

The headline numbers must have a single source of truth: the dashboard generates
them, REPORT explains them, and README mirrors REPORT's block verbatim. This script
fails fast when one side is updated without the other.

Usage:
    uv run python tools/check_docs_sync.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = [ROOT / "README.md", ROOT / "experiments" / "REPORT.md"]
START, END = "<!-- TLDR:START -->", "<!-- TLDR:END -->"


def _label(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def extract(path: Path) -> str:
    text = path.read_text()
    if START not in text or END not in text:
        raise SystemExit(f"{_label(path)}: missing {START} ... {END} block")
    body = text.split(START, 1)[1].split(END, 1)[0]
    return "\n".join(line.rstrip() for line in body.strip().splitlines())


def main() -> int:
    blocks = {p: extract(p) for p in DOCS}
    values = list(blocks.values())
    if all(v == values[0] for v in values):
        print(f"docs in sync: {', '.join(_label(p) for p in DOCS)}")
        return 0

    print("TL;DR blocks differ:", file=sys.stderr)
    for path, body in blocks.items():
        print(f"\n--- {_label(path)} ---\n{body}", file=sys.stderr)
    print("\nFix: copy the block from experiments/REPORT.md into README.md (or vice versa).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
