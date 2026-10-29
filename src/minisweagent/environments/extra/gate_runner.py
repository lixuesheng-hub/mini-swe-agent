#!/usr/bin/env python3
"""Submit-gate checker, executed INSIDE the agent container at repo root.

Args: argv[1] = base64(patch text), argv[2] = base64(json targets).
It applies the patch in a throwaway git worktree (main worktree untouched),
runs syntax check + the tests the model itself ran, and prints a final JSON line:
  {"verdict": "pass"|"reject"|"error", "applied": bool, "checks": [...]}
"""

import base64
import json
import re
import subprocess
import sys
import tempfile
import uuid


def run(cmd, cwd, input_text=None, timeout=300):
    return subprocess.run(
        cmd, cwd=cwd, input=input_text, capture_output=True, text=True, timeout=timeout
    )


def main() -> int:
    patch = base64.b64decode(sys.argv[1]).decode()
    targets = json.loads(base64.b64decode(sys.argv[2]).decode())
    repo = "."
    wt = f".gate-wt-{uuid.uuid4().hex[:8]}"
    checks = []
    verdict = "reject"
    applied = False

    try:
        # 1) clean worktree off HEAD (equals the harness's fresh-checkout premise)
        r = run(["git", "worktree", "add", "--detach", wt, "HEAD"], repo)
        if r.returncode != 0:
            print(json.dumps({"verdict": "error", "applied": False,
                              "checks": [{"name": "worktree", "ok": False,
                                          "detail": (r.stderr or r.stdout)[-500:]}]}))
            return 0

        # 2) apply patch
        if patch.strip():
            r = run(["git", "apply", "--whitespace=nowarn", "-"], wt, input_text=patch)
            ok = r.returncode == 0
            checks.append({"name": "patch_applies", "ok": ok,
                           "detail": "" if ok else (r.stderr or r.stdout)[-800:]})
            if not ok:
                _done(wt, "reject", False, checks)
                return 0
            applied = True
        else:
            checks.append({"name": "patch_applies", "ok": True, "detail": "empty patch"})

        # 3) syntax check on modified python files
        py_files = re.findall(r"^\+\+\+ b/(.+\.py)$", patch, flags=re.MULTILINE)
        if py_files:
            r = run([sys.executable, "-m", "py_compile", *py_files], wt, timeout=60)
            ok = r.returncode == 0
            checks.append({"name": "syntax", "ok": ok,
                           "detail": "" if ok else (r.stderr or r.stdout)[-800:]})
            if not ok:
                _done(wt, "reject", applied, checks)
                return 0

        # 4) re-run the tests the model itself used as evidence
        bad = []
        for t in targets:
            if t.get("runner") == "runtests":
                cmd = [sys.executable, "runtests.py", t["target"], "-v1"]
                cwd = f"{wt}/{t.get('runtests_dir', 'tests')}"
            else:
                cmd = [sys.executable, "-m", "pytest", t["target"], "-q", "--no-header"]
                cwd = wt
            try:
                r = run(cmd, cwd, timeout=300)
            except subprocess.TimeoutExpired:
                bad.append(f"{t['target']}: timeout")
                continue
            if r.returncode != 0:
                tail = (r.stdout + r.stderr)[-600:]
                bad.append(f"{t['target']}:\n{tail}")
        ok = not bad
        checks.append({"name": "own_tests", "ok": ok, "detail": "\n".join(bad)[:2000]})

        _done(wt, "pass" if ok else "reject", applied, checks)
        return 0
    except Exception as e:  # gate infra failure must never kill the agent
        _done(wt, "error", applied,
              checks + [{"name": "gate_exception", "ok": False, "detail": repr(e)[-500:]}])
        return 0


def _done(wt, verdict, applied, checks):
    run(["git", "worktree", "remove", "--force", wt], ".")
    run(["rm", "-rf", wt], ".")
    print(json.dumps({"verdict": verdict, "applied": applied, "checks": checks}))


if __name__ == "__main__":
    sys.exit(main())
