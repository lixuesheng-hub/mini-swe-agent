"""Agent variant that feeds the model's own test commands to a gated environment."""

from minisweagent.agents.default import AgentConfig, DefaultAgent
from minisweagent.agents.extra.submit_gate import extract_test_targets


class GatedAgent(DefaultAgent):
    """After each step, parse the command history for tests the model ran and
    publish them to the environment (if it implements the gate setter)."""

    def _sync_gate_targets(self):
        commands = []
        for message in self.messages:
            for action in message.get("extra", {}).get("actions", []) or []:
                if isinstance(action, dict) and action.get("command"):
                    commands.append(action["command"])
        targets = [vars(t) for t in extract_test_targets(commands)]
        setter = getattr(self.env, "set_gate_targets", None)
        if callable(setter):
            setter(targets)

    def step(self) -> list[dict]:
        result = super().step()
        self._sync_gate_targets()
        return result
