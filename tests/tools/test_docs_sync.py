from pathlib import Path

import pytest

import tools.check_docs_sync as docs


def _write(tmp_path: Path, name: str, block: str) -> Path:
    p = tmp_path / name
    p.write_text(f"# doc\n\n<!-- TLDR:START -->\n{block}\n<!-- TLDR:END -->\n")
    return p


@pytest.fixture
def two_docs(tmp_path, monkeypatch):
    a = _write(tmp_path, "README.md", "- 基线 30/50")
    b = _write(tmp_path, "REPORT.md", "- 基线 30/50")
    monkeypatch.setattr(docs, "DOCS", [a, b])
    return a, b


def test_identical_blocks_pass(two_docs):
    assert docs.main() == 0


def test_diverging_blocks_fail(two_docs):
    a, _ = two_docs
    a.write_text(a.read_text().replace("30/50", "31/50"))
    assert docs.main() == 1


def test_missing_marker_is_reported(tmp_path, monkeypatch):
    p = tmp_path / "README.md"
    p.write_text("# no markers here")
    monkeypatch.setattr(docs, "DOCS", [p])
    with pytest.raises(SystemExit, match="missing"):
        docs.extract(p)
