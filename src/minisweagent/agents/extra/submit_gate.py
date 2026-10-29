"""Submit gate: extract test targets that the model itself ran during the episode.

The gate re-runs only tests that appear in the agent's own command history.
Dataset FAIL_TO_PASS/PASS_TO_PASS fields must never be read here (answer leak).
"""

import re
import shlex
from dataclasses import dataclass

# pytest <file>[::node] ...  (file must look like a path containing "test")
_PYTEST_RE = re.compile(
    r"(?:python\s+-m\s+)?pytest\s+((?:[^\s;|&]+\.py)(?:::[^\s;|&]+)?(?:\s+(?:[^\s;|&]+\.py)(?:::[^\s;|&]+)?)*)"
)
# runtests.py <dotted.path>  (one or more targets)
_RUNTESTS_RE = re.compile(
    r"(?P<dir>\S*/)?runtests\.py\s+(?P<args>.+)"
)
_DOTTED_RE = re.compile(r"^[A-Za-z_][\w.]*(?:\.[A-Za-z_]\w*)+$")
# strip pytest flags / shell noise that may be glued after the target
_FLAG_TOKEN = re.compile(r"^-")


@dataclass(frozen=True)
class TestTarget:
    __test__ = False  # prevent pytest from collecting this as a test class
    runner: str          # "pytest" | "runtests"
    target: str
    runtests_dir: str = ""  # directory holding runtests.py (django: "tests")

    def to_command(self) -> str:
        if self.runner == "runtests":
            return f"cd {self.runtests_dir} && python runtests.py {self.target}"
        return f"python -m pytest {self.target} -q"


def _strip_flags(token: str) -> str:
    return token.rstrip("2>").rstrip("'\"")


def _parse_one(cmd: str) -> list[TestTarget]:
    """Extract test targets from a single shell command (best-effort, no shell execution)."""
    targets: list[TestTarget] = []

    m = _PYTEST_RE.search(cmd)
    if m:
        for tok in m.group(1).split():
            raw = _strip_flags(tok).strip("'\"")
            if ".py" in raw and not raw.startswith("-"):
                targets.append(TestTarget("pytest", raw))

    m = _RUNTESTS_RE.search(cmd)
    if m:
        runtests_dir = (m.group("dir") or "").rstrip("/")
        # e.g. "python tests/runtests.py" -> runtests_dir "tests"
        if runtests_dir.endswith("tests") is False and runtests_dir:
            # common case: ".../tests"
            pass
        if not runtests_dir:
            runtests_dir = "tests"
        else:
            runtests_dir = runtests_dir.removeprefix("python ").strip()
            if not runtests_dir.endswith("tests"):
                runtests_dir = "tests"
        try:
            tokens = shlex.split(m.group("args"), comments=True, posix=True)
        except ValueError:
            tokens = m.group("args").split()
        for tok in tokens:
            tok = tok.strip()
            if not tok or _FLAG_TOKEN.match(tok):
                continue
            if _DOTTED_RE.match(tok):
                targets.append(TestTarget("runtests", tok, runtests_dir=runtests_dir))

    return targets


def extract_test_targets(commands: list[str], max_targets: int = 30) -> list[TestTarget]:
    """Parse model-issued commands into a de-duplicated, coarsened target list.

    Rules:
    - same target with different flags/repeats -> one entry (order = first seen);
    - once a whole test file was run, its individual nodes are subsumed.
    """
    seen: set[TestTarget] = set()
    ordered: list[TestTarget] = []

    def add(t: TestTarget):
        if t in seen:
            return
        seen.add(t)
        ordered.append(t)

    for cmd in commands:
        for t in _parse_one(cmd):
            add(t)

    # Coarsen pytest targets: when the model ran BOTH a whole file and specific nodes
    # of that file, keep only the nodes. Rationale: the whole-file run is exploration
    # (often slow/network-heavy, e.g. linkcheck times out at 300s), while the nodes are
    # the precise verification intent. Re-running the whole file at submit time would
    # spuriously time out and reject every submission.
    node_files = {
        t.target.split("::", 1)[0]
        for t in ordered
        if t.runner == "pytest" and "::" in t.target
    }
    coarsened = [
        t
        for t in ordered
        if not (t.runner == "pytest" and "::" not in t.target and t.target in node_files)
    ]
    return coarsened[:max_targets]
