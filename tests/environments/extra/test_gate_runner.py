"""Integration tests for the in-container gate runner script.

Runs the actual gate script against throwaway local git repos (no docker, no mocks):
git worktree, patch application and pytest are all real.
"""
import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest

from minisweagent.environments.extra.gated_docker import GATE_RUNNER_SOURCE


@pytest.fixture
def repo_factory(tmp_path):
    counter = {"n": 0}

    def make(files: dict[str, str]):
        counter["n"] += 1
        repo = tmp_path / f"repo{counter['n']}"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        for rel, content in files.items():
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
        return repo

    return make


def run_gate(repo: Path, patch: str, targets: list[dict]) -> dict:
    script = repo / "_gate_runner.py"
    script.write_text(GATE_RUNNER_SOURCE)
    args = [
        sys.executable,
        str(script),
        base64.b64encode(patch.encode()).decode(),
        base64.b64encode(json.dumps(targets).encode()).decode(),
    ]
    proc = subprocess.run(args, cwd=repo, capture_output=True, text=True, timeout=120)
    # Last line of stdout must be the JSON verdict
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    assert proc.returncode == 0, f"gate crashed: {proc.stdout}\n{proc.stderr}"
    return json.loads(lines[-1])


GOOD_TEST = """
def test_ok():
    from pkg import value
    assert value == 42
"""
BAD_INIT = "value = 0\n"
FIX_INIT = "value = 42\n"


def _patch(repo: Path, new_content: str, rel: str = "pkg/__init__.py") -> str:
    return subprocess.run(
        ["git", "diff", "--no-index", "/dev/null", "/dev/null"], capture_output=True, text=True
    ).stdout or _diff(repo, rel, new_content)


def _diff(repo: Path, rel: str, new_content: str) -> str:
    import difflib
    old = (repo / rel).read_text().splitlines(keepends=True)
    new = [new_content if not new_content.endswith("\n") else new_content]
    diff = "".join(
        difflib.unified_diff(old, new, fromfile=f"a/{rel}", tofile=f"b/{rel}")
    )
    return diff


def test_passing_patch_with_model_owned_test_is_accepted(repo_factory):
    repo = repo_factory({"pkg/__init__.py": BAD_INIT, "tests/test_it.py": GOOD_TEST})
    verdict = run_gate(repo, _diff(repo, "pkg/__init__.py", FIX_INIT),
                       [{"runner": "pytest", "target": "tests/test_it.py::test_ok"}])
    assert verdict["verdict"] == "pass", verdict
    assert verdict["applied"] is True


def test_patch_that_does_not_apply_is_rejected(repo_factory):
    repo = repo_factory({"pkg/__init__.py": "something_else = 1\n", "tests/test_it.py": GOOD_TEST})
    # diff against a context that does not exist in the repo
    patch = "--- a/pkg/__init__.py\n+++ b/pkg/__init__.py\n@@ -1,1 +1,1 @@\n-value = 0\n+value = 42\n"
    verdict = run_gate(repo, patch, [{"runner": "pytest", "target": "tests/test_it.py::test_ok"}])
    assert verdict["verdict"] == "reject"
    assert any(c["name"] == "patch_applies" and not c["ok"] for c in verdict["checks"])


def test_failing_model_test_rejects(repo_factory):
    repo = repo_factory({"pkg/__init__.py": BAD_INIT, "tests/test_it.py": GOOD_TEST})
    # empty patch: test stays red
    verdict = run_gate(repo, "", [{"runner": "pytest", "target": "tests/test_it.py::test_ok"}])
    assert verdict["verdict"] == "reject"
    failed = [c for c in verdict["checks"] if c["name"] == "own_tests" and not c["ok"]]
    assert failed and "test_ok" in failed[0]["detail"]


def test_no_targets_passes_when_patch_applies(repo_factory):
    repo = repo_factory({"pkg/__init__.py": BAD_INIT})
    verdict = run_gate(repo, _diff(repo, "pkg/__init__.py", FIX_INIT), [])
    assert verdict["verdict"] == "pass"


def test_syntax_error_in_modified_python_file_is_rejected(repo_factory):
    repo = repo_factory({"pkg/__init__.py": BAD_INIT, "tests/test_it.py": GOOD_TEST})
    verdict = run_gate(repo, _diff(repo, "pkg/__init__.py", "def broken(:\n"), [])
    assert verdict["verdict"] == "reject"
    assert any(c["name"] == "syntax" and not c["ok"] for c in verdict["checks"])


def test_worktree_is_cleaned_up_and_main_worktree_untouched(repo_factory):
    repo = repo_factory({"pkg/__init__.py": BAD_INIT, "tests/test_it.py": GOOD_TEST})
    verdict = run_gate(repo, _diff(repo, "pkg/__init__.py", FIX_INIT),
                       [{"runner": "pytest", "target": "tests/test_it.py::test_ok"}])
    assert verdict["verdict"] == "pass"
    # model's working tree unchanged (still unfixed)
    assert (repo / "pkg/__init__.py").read_text() == BAD_INIT
    wt = subprocess.run(["git", "worktree", "list"], cwd=repo, capture_output=True, text=True)
    assert "gate-" not in wt.stdout
