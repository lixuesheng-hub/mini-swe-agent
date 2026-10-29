"""GatedAgent: keeps the gated environment's test-target list in sync with the
command history, so the gate only re-runs tests the model itself ran."""
import pytest

from minisweagent.agents.default import AgentConfig
from minisweagent.agents.extra.gated_agent import GatedAgent
from minisweagent.models.test_models import DeterministicModel, make_output


class RecordingEnv:
    """Minimal env stand-in: records executed commands and the synced gate targets."""

    def __init__(self):
        self.commands = []
        self.synced = None
        self.calls = 0

    def execute(self, action, cwd=""):
        self.calls += 1
        self.commands.append(action["command"])
        return {"output": "ok", "returncode": 0, "exception_info": ""}

    def set_gate_targets(self, targets):
        self.synced = targets

    def get_template_vars(self, **kw):
        return {}


def _agent(actions_per_step):
    model = DeterministicModel(outputs=[make_output("thinking", acts) for acts in actions_per_step])
    env = RecordingEnv()
    agent = GatedAgent(
        model, env,
        system_template="sys", instance_template="task {{task}}",
        step_limit=10,
    )
    return agent, env


def test_targets_synced_after_each_step():
    agent, env = _agent([
        [{"command": "pytest tests/test_a.py::test_x -q"}],
        [{"command": "grep -rn foo sphinx/"}],
    ])
    agent.step()
    assert env.synced and env.synced[0]["target"] == "tests/test_a.py::test_x"
    before = env.synced
    agent.step()
    # second step adds no test targets; list stays equal
    assert env.synced == before


def test_non_gated_env_without_setter_does_not_crash():
    """Environments lacking set_gate_targets must keep working."""
    class BareEnv:
        def __init__(self):
            self.commands = []

        def execute(self, action, cwd=""):
            self.commands.append(action["command"])
            return {"output": "ok", "returncode": 0, "exception_info": ""}

        def get_template_vars(self, **kw):
            return {}

    model = DeterministicModel(outputs=[make_output("t", [{"command": "pytest tests/a.py"}])])
    env = BareEnv()
    agent = GatedAgent(model, env, system_template="s", instance_template="t {{task}}", step_limit=5)
    agent.step()  # should not raise
    assert env.commands == ["pytest tests/a.py"]
