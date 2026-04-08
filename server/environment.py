# server/environment.py
import uuid
import sys
import os
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State
from models import CostGuardAction, CostGuardObservation, CostGuardState
from server.simulator import ClusterSimulator
from server.tasks import GRADERS, TASK_DESCRIPTIONS


MAX_STEPS = {"task_easy": 15, "task_medium": 20, "task_hard": 25}


class CloudCostGuardEnvironment(Environment):
    """
    CloudCostGuardEnv — A Kubernetes FinOps RL environment.
    Agent learns to cut cloud costs while maintaining SLAs.
    """

    def __init__(self, task_id: str = "task_easy", seed: int = 42):
        self.task_id = task_id
        self.seed = seed
        self._state = CostGuardState(
            episode_id=str(uuid.uuid4()),
            step_count=0,
            task_id=task_id,
        )
        self.sim = ClusterSimulator(task_id=task_id, seed=seed)
        self.sim.record_baseline()
        self.baseline_cost = self.sim.baseline_cost
        self._max_steps = MAX_STEPS.get(task_id, 20)

    def reset(self) -> CostGuardObservation:
        # Randomize seed slightly each episode for variety
        new_seed = self.seed + hash(str(uuid.uuid4())) % 100
        self.sim = ClusterSimulator(task_id=self.task_id, seed=new_seed)
        self.sim.record_baseline()
        self.baseline_cost = self.sim.baseline_cost
        self._state = CostGuardState(
            episode_id=str(uuid.uuid4()),
            step_count=0,
            task_id=self.task_id,
            total_reward=0.0,
            sla_violations=0,
        )
        task_info = TASK_DESCRIPTIONS[self.task_id]
        return CostGuardObservation(
            total_cost_per_hour=self.sim.total_cost_per_hour,
            baseline_cost_per_hour=self.baseline_cost,
            cost_saved_percent=0.0,
            pods=[p.to_dict() for p in self.sim.pods],
            sla_violations=0,
            avg_response_time_ms=self.sim.get_response_time_ms(),
            sla_threshold_ms=500.0,
            budget_remaining=self.sim.budget_limit,
            budget_limit=self.sim.budget_limit,
            step=0,
            max_steps=self._max_steps,
            task_id=self.task_id,
            message=f"Episode started. Task: {task_info['name']}. {task_info['description']}",
            done=False,
            reward=0.0,
        )

    def step(self, action: CostGuardAction) -> CostGuardObservation:
        self._state.step_count += 1
        self._state.actions_taken.append(f"{action.action_type}:{action.target}:{action.value}")

        # Apply action to simulator
        reward_delta, sla_hit, msg = self.sim.apply_action(
            action.action_type, action.target, action.value
        )

        # Compute partial reward
        grader = GRADERS[self.task_id]
        grade = grader(self.sim, self.baseline_cost)
        step_reward = round(reward_delta + grade["score"] * 0.1, 4)  # partial signal per step

        self._state.total_reward += step_reward
        self._state.sla_violations = self.sim.sla_violations

        current_cost = self.sim.total_cost_per_hour
        cost_saved_pct = 0.0
        if self.baseline_cost > 0:
            cost_saved_pct = round((self.baseline_cost - current_cost) / self.baseline_cost * 100, 2)

        done = (
            self._state.step_count >= self._max_steps or
            self.sim.budget_spent > self.sim.budget_limit * 1.5
        )

        return CostGuardObservation(
            total_cost_per_hour=current_cost,
            baseline_cost_per_hour=self.baseline_cost,
            cost_saved_percent=cost_saved_pct,
            pods=[p.to_dict() for p in self.sim.pods],
            sla_violations=self.sim.sla_violations,
            avg_response_time_ms=self.sim.get_response_time_ms(),
            sla_threshold_ms=500.0,
            budget_remaining=round(self.sim.budget_limit - self.sim.budget_spent, 4),
            budget_limit=self.sim.budget_limit,
            step=self._state.step_count,
            max_steps=self._max_steps,
            task_id=self.task_id,
            message=msg,
            done=done,
            reward=step_reward,
        )

    @property
    def state(self) -> CostGuardState:
        return self._state