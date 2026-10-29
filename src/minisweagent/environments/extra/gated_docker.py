"""Docker environment with a pre-submit verification gate.

When the model emits COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT, instead of ending the
episode the patch is applied in a throwaway git worktree and checked:
  1. patch applies cleanly   2. modified python compiles
  3. tests the model itself ran earlier still pass
Failure is returned to the model as a regular observation (bounded retries);
pass (or exhausted retries / gate errors) raises Submitted as usual.

The gate is only active when ``submit_gate_enabled`` is set; default Docker
behaviour is byte-identical otherwise.
"""

import base64
import json
import logging

from pydantic import BaseModel

from minisweagent.environments.docker import DockerEnvironment, DockerEnvironmentConfig
from minisweagent.exceptions import Submitted
from minisweagent.environments.extra.gate_runner import __file__ as _GATE_RUNNER_PATH


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


GATE_RUNNER_SOURCE = _read(_GATE_RUNNER_PATH)

GATE_FEEDBACK_TEMPLATE = """<submit_gate {verdict_upper} (attempt {attempt}/{max_attempts})>
Your submission was NOT accepted. The patch was applied to a clean checkout and the
tests YOU used to verify your fix were re-run:

{detail}

Fix the issues (or verify your fix properly) and re-submit. Do not submit until your
own evidence passes. After {max_attempts} rejected attempts your submission will be
accepted as-is and graded externally.
</submit_gate>
<returncode>0</returncode>"""


class GatedDockerEnvironmentConfig(DockerEnvironmentConfig):
    submit_gate_enabled: bool = False
    submit_gate_max_attempts: int = 3
    submit_gate_timeout: int = 900


class GatedDockerEnvironment(DockerEnvironment):
    def __init__(self, *args, config_class: type = GatedDockerEnvironmentConfig, **kwargs):
        super().__init__(*args, config_class=config_class, **kwargs)
        self.gate_targets: list[dict] = []
        self.gate_attempts = 0

    def set_gate_targets(self, targets: list[dict]):
        self.gate_targets = targets

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict:
        command = action.get("command", "")
        stripped = command.lstrip()
        if self.config.submit_gate_enabled and self._is_submit(stripped):
            # Do not run echo+cat (upstream would end the episode); gate the patch file.
            return self._run_gate()
        return super().execute(action, cwd, timeout=timeout)

    @staticmethod
    def _is_submit(command: str) -> bool:
        # Per prompt: `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt`,
        # possibly with a leading `cd /testbed && ...`.
        return "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT" in command

    def _read_patch(self) -> str:
        r = super().execute({"command": "cat patch.txt 2>/dev/null || true"}, timeout=30)
        return r["output"]

    def _run_gate(self) -> dict:
        log = logging.getLogger("minisweagent.environment.gate")
        cfg = self.config
        self.gate_attempts += 1
        submission = self._read_patch()

        # Upload the runner script into the container (idempotent overwrite).
        import base64 as _b64
        runner_b64 = _b64.b64encode(GATE_RUNNER_SOURCE.encode()).decode()
        upload = (
            f"mkdir -p /tmp/mswe_gate && echo {runner_b64} | base64 -d > /tmp/mswe_gate/gate_runner.py"
        )
        up = super().execute({"command": upload}, timeout=60)
        if up["returncode"] != 0:
            log.warning("gate runner upload failed, passing through submission")
            self._raise_submitted(submission)

        patch_b64 = base64.b64encode(submission.encode()).decode()
        targets_b64 = base64.b64encode(json.dumps(self.gate_targets).encode()).decode()
        cmd = (
            f"python /tmp/mswe_gate/gate_runner.py {patch_b64} {targets_b64}"
        )
        result = super().execute({"command": cmd}, timeout=cfg.submit_gate_timeout)

        try:
            verdict_line = [l for l in result["output"].splitlines() if l.strip().startswith("{")][-1]
            verdict = json.loads(verdict_line)
        except (IndexError, json.JSONDecodeError):
            log.warning("gate produced no verdict, passing through: %s", result["output"][-300:])
            self._raise_submitted(submission)

        if verdict["verdict"] == "pass" or self.gate_attempts >= cfg.submit_gate_max_attempts:
            self._raise_submitted(submission)

        detail = "\n".join(
            f"- [{c['name']}] {'OK' if c['ok'] else 'FAIL'}\n  {c.get('detail','')[:400]}"
            for c in verdict["checks"] if not c["ok"]
        ) or "verdict reject without details"
        output = GATE_FEEDBACK_TEMPLATE.format(
            verdict_upper="REJECTED",
            attempt=self.gate_attempts,
            max_attempts=cfg.submit_gate_max_attempts,
            detail=detail,
        )
        return {"output": output, "returncode": 0, "exception_info": ""}

    def _raise_submitted(self, submission: str):
        """End the episode the same way upstream's _check_finished would."""
        raise Submitted(
            {
                "role": "exit",
                "content": submission,
                "extra": {"exit_status": "Submitted", "submission": submission},
            }
        )
