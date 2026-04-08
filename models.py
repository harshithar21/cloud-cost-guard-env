# models.py
from typing import Optional, List, Dict
from pydantic import Field
from openenv.core.env_server.types import Action, Observation, State

class CostGuardAction(Action):
    """Action the agent takes to optimize cloud costs."""
    action_type: str = Field(..., description=(
        "Type of action: 'scale_pod', 'set_replicas', 'migrate_to_spot', "
        "'migrate_to_ondemand', 'set_request_cpu', 'set_request_memory', "
        "'set_budget_limit', 'noop'"
    ))
    target: str = Field(..., description="Target resource: pod name or cluster id")
    value: float = Field(default=0.0, description="Numeric parameter for the action")
    reasoning: str = Field(default="", description="Agent's reasoning for this action")

class ClusterMetrics(object):
    pass

class CostGuardObservation(Observation):
    """What the agent observes about the cluster state."""
    # Current cluster snapshot
    total_cost_per_hour: float = Field(..., description="Current $/hr spend")
    baseline_cost_per_hour: float = Field(..., description="Original $/hr before any actions")
    cost_saved_percent: float = Field(..., description="% cost reduced so far")

    # Pod metrics
    pods: List[Dict] = Field(default_factory=list, description=(
        "List of pod dicts: {name, cpu_requested, cpu_used, mem_requested_mb, "
        "mem_used_mb, replicas, on_spot, cost_per_hour}"
    ))

    # SLA status
    sla_violations: int = Field(default=0, description="Number of SLA breaches this episode")
    avg_response_time_ms: float = Field(default=100.0, description="Average response time in ms")
    sla_threshold_ms: float = Field(default=500.0, description="SLA limit in ms")

    # Budget
    budget_remaining: float = Field(default=100.0, description="$ budget left this episode")
    budget_limit: float = Field(default=100.0, description="Total episode budget")

    # Episode info
    step: int = Field(default=0)
    max_steps: int = Field(default=20)
    task_id: str = Field(default="task_easy")
    message: str = Field(default="", description="Human-readable status message")
    done: bool = Field(default=False)
    reward: float = Field(default=0.0)

class CostGuardState(State):
    """Internal episode state."""
    episode_id: str = Field(default="")
    step_count: int = Field(default=0)
    task_id: str = Field(default="task_easy")
    total_reward: float = Field(default=0.0)
    sla_violations: int = Field(default=0)
    actions_taken: List[str] = Field(default_factory=list)