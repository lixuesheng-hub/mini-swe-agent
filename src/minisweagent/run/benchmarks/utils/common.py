"""Shared agent utilities for benchmark runners."""

from minisweagent.agents import get_agent_class
from minisweagent.agents.default import DefaultAgent
from minisweagent.run.benchmarks.utils.batch_progress import RunBatchProgressManager


def make_progress_tracking_agent(base_class: type[DefaultAgent] = DefaultAgent) -> type:
    """Build a progress-reporting agent on top of any configured agent class.

    Keeps batch progress reporting while preserving variant behaviour (e.g. GatedAgent)."""

    class ProgressTrackingAgent(base_class):
        def __init__(self, *args, progress_manager: RunBatchProgressManager, instance_id: str = "", **kwargs):
            super().__init__(*args, **kwargs)
            self.progress_manager = progress_manager
            self.instance_id = instance_id

        def step(self) -> dict:
            self.progress_manager.update_instance_status(
                self.instance_id, f"Step {self.n_calls + 1:3d} (${self.cost:.2f})"
            )
            return super().step()

    return ProgressTrackingAgent


# Backwards-compatible default (DefaultAgent base).
ProgressTrackingAgent = make_progress_tracking_agent(DefaultAgent)
