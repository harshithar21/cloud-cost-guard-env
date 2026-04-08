# client.py
from openenv.core.env_client import EnvClient
from openenv.core.client_types import StepResult
from .models import CostGuardAction, CostGuardObservation, CostGuardState


class CloudCostGuardEnv(EnvClient):
    """Client for CloudCostGuardEnv."""

    def _step_payload(self, action: CostGuardAction) -> dict:
        return action.model_dump()

    def _parse_result(self, data: dict) -> StepResult:
        obs = CostGuardObservation(**data["observation"])
        return StepResult(
            observation=obs,
            reward=data.get("reward", 0.0),
            done=data.get("done", False),
            info=data.get("info", {}),
        )

    def _parse_state(self, data: dict) -> CostGuardState:
        return CostGuardState(**data)