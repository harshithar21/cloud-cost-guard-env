# server/simulator.py
"""
Simulates a Kubernetes cluster with pods, costs, and SLA metrics.
All numbers are deterministic given a seed — graders are NOT hardcoded.
"""
import random
import math
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class Pod:
    name: str
    cpu_requested: float      # cores
    cpu_used: float           # cores (actual usage)
    mem_requested_mb: float   # MB
    mem_used_mb: float        # MB
    replicas: int
    on_spot: bool
    base_cost_per_core_hour: float = 0.048   # on-demand price
    spot_discount: float = 0.65              # spot = 65% cheaper

    @property
    def cost_per_hour(self) -> float:
        price = self.base_cost_per_core_hour * (1 - (self.spot_discount if self.on_spot else 0))
        return round(price * self.cpu_requested * self.replicas, 4)

    @property
    def cpu_waste_ratio(self) -> float:
        if self.cpu_requested == 0:
            return 0.0
        return max(0.0, (self.cpu_requested - self.cpu_used) / self.cpu_requested)

    @property
    def mem_waste_ratio(self) -> float:
        if self.mem_requested_mb == 0:
            return 0.0
        return max(0.0, (self.mem_requested_mb - self.mem_used_mb) / self.mem_requested_mb)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "cpu_requested": round(self.cpu_requested, 3),
            "cpu_used": round(self.cpu_used, 3),
            "mem_requested_mb": round(self.mem_requested_mb, 1),
            "mem_used_mb": round(self.mem_used_mb, 1),
            "replicas": self.replicas,
            "on_spot": self.on_spot,
            "cost_per_hour": self.cost_per_hour,
            "cpu_waste_ratio": round(self.cpu_waste_ratio, 3),
            "mem_waste_ratio": round(self.mem_waste_ratio, 3),
        }


class ClusterSimulator:
    """Simulates a Kubernetes cluster for FinOps training."""

    def __init__(self, task_id: str = "task_easy", seed: int = 42):
        self.task_id = task_id
        self.seed = seed
        self.rng = random.Random(seed)
        self.pods: List[Pod] = []
        self.step_num = 0
        self.sla_violations = 0
        self.traffic_multiplier = 1.0
        self.budget_spent = 0.0
        self.budget_limit = 200.0
        self._setup_cluster()

    def _setup_cluster(self):
        """Create an over-provisioned cluster with waste opportunities."""
        if self.task_id == "task_easy":
            self._setup_easy()
        elif self.task_id == "task_medium":
            self._setup_medium()
        else:
            self._setup_hard()

    def _setup_easy(self):
        """Over-provisioned pods — just needs right-sizing."""
        pod_templates = [
            ("frontend",    4.0, 0.8,  2048, 512,   3, False),
            ("api-server",  8.0, 1.5,  4096, 1024,  2, False),
            ("worker",      4.0, 0.4,  2048, 256,   4, False),
            ("cache",       2.0, 1.8,  1024, 900,   2, False),
            ("db-proxy",    4.0, 0.3,  2048, 200,   1, False),
        ]
        for name, cpu_req, cpu_use, mem_req, mem_use, reps, spot in pod_templates:
            jitter = self.rng.uniform(0.9, 1.1)
            self.pods.append(Pod(
                name=name,
                cpu_requested=cpu_req,
                cpu_used=round(cpu_use * jitter, 3),
                mem_requested_mb=mem_req,
                mem_used_mb=round(mem_use * jitter, 1),
                replicas=reps,
                on_spot=spot
            ))

    def _setup_medium(self):
        """Mix of on-demand pods that should be on spot + scaling issues."""
        pod_templates = [
            ("frontend",    2.0, 0.9,  1024, 700,   4, False),
            ("api-server",  4.0, 2.1,  2048, 1800,  3, False),
            ("batch-job",   8.0, 6.0,  4096, 3000,  2, False),  # should be spot
            ("ml-worker",   4.0, 3.5,  2048, 1900,  4, False),  # should be spot
            ("cache",       2.0, 1.6,  1024, 850,   2, False),
            ("log-proc",    2.0, 0.2,  1024, 150,   3, False),  # over-provisioned
        ]
        for name, cpu_req, cpu_use, mem_req, mem_use, reps, spot in pod_templates:
            jitter = self.rng.uniform(0.95, 1.05)
            self.pods.append(Pod(
                name=name,
                cpu_requested=cpu_req,
                cpu_used=round(cpu_use * jitter, 3),
                mem_requested_mb=mem_req,
                mem_used_mb=round(mem_use * jitter, 1),
                replicas=reps,
                on_spot=spot
            ))

    def _setup_hard(self):
        """Multi-service cluster with budget constraints and traffic surges."""
        pod_templates = [
            ("frontend",    2.0, 1.8,  1024, 900,   5, False),
            ("api-v1",      4.0, 3.2,  2048, 1900,  4, False),
            ("api-v2",      4.0, 1.0,  2048, 800,   2, False),
            ("ml-inference",8.0, 7.5,  8192, 7000,  2, True),
            ("batch-proc",  4.0, 3.8,  2048, 1800,  3, True),
            ("data-etl",    4.0, 0.5,  2048, 400,   2, False),   # waste
            ("monitoring",  2.0, 0.3,  1024, 200,   3, False),   # waste
            ("cache",       2.0, 1.9,  2048, 1800,  3, False),
        ]
        for name, cpu_req, cpu_use, mem_req, mem_use, reps, spot in pod_templates:
            jitter = self.rng.uniform(0.9, 1.1)
            self.pods.append(Pod(
                name=name,
                cpu_requested=cpu_req,
                cpu_used=round(cpu_use * jitter, 3),
                mem_requested_mb=mem_req,
                mem_used_mb=round(mem_use * jitter, 1),
                replicas=reps,
                on_spot=spot
            ))
        self.budget_limit = 150.0  # tighter budget for hard task

    @property
    def total_cost_per_hour(self) -> float:
        return round(sum(p.cost_per_hour for p in self.pods), 4)

    @property
    def baseline_cost(self) -> float:
        """Cost if nothing was changed (stored at init)."""
        return self._baseline

    def record_baseline(self):
        self._baseline = self.total_cost_per_hour

    def get_pod(self, name: str) -> Optional[Pod]:
        for p in self.pods:
            if p.name == name:
                return p
        return None

    def apply_action(self, action_type: str, target: str, value: float) -> tuple[float, bool, str]:
        """
        Apply an action to the cluster.
        Returns: (reward_delta, caused_sla_violation, message)
        """
        pod = self.get_pod(target)

        if action_type == "noop":
            return 0.0, False, "No-op taken."

        if pod is None and action_type not in ("set_budget_limit",):
            return -0.05, False, f"Pod '{target}' not found."

        reward = 0.0
        sla_hit = False
        msg = ""

        if action_type == "set_request_cpu":
            old_cost = pod.cost_per_hour
            # Penalize setting below actual usage (SLA risk)
            if value < pod.cpu_used * 0.9:
                sla_hit = True
                self.sla_violations += 1
                pod.cpu_requested = max(value, pod.cpu_used * 0.5)
                msg = f"WARNING: CPU request for {target} set too low — SLA risk!"
                reward = -0.3
            else:
                pod.cpu_requested = max(0.1, value)
                cost_saved = old_cost - pod.cost_per_hour
                reward = min(0.3, cost_saved * 2)
                msg = f"CPU request for {target} set to {value:.2f} cores. Saved ${cost_saved:.4f}/hr."

        elif action_type == "set_request_memory":
            old_cost = pod.cost_per_hour
            if value < pod.mem_used_mb * 0.9:
                sla_hit = True
                self.sla_violations += 1
                pod.mem_requested_mb = max(value, pod.mem_used_mb * 0.5)
                msg = f"WARNING: Memory for {target} set too low — SLA risk!"
                reward = -0.3
            else:
                pod.mem_requested_mb = max(64, value)
                cost_saved = old_cost - pod.cost_per_hour
                reward = min(0.2, cost_saved * 1.5)
                msg = f"Memory for {target} set to {value:.0f}MB. Saved ${cost_saved:.4f}/hr."

        elif action_type == "set_replicas":
            old_cost = pod.cost_per_hour
            new_reps = max(1, int(value))
            # Check if reducing replicas causes SLA issues under load
            if new_reps < pod.replicas and self.traffic_multiplier > 1.5:
                sla_hit = True
                self.sla_violations += 1
                msg = f"Reducing replicas for {target} during traffic surge — SLA violation!"
                reward = -0.4
            else:
                pod.replicas = new_reps
                cost_delta = old_cost - pod.cost_per_hour
                reward = min(0.25, cost_delta * 1.5) if cost_delta > 0 else max(-0.2, cost_delta)
                msg = f"Replicas for {target} set to {new_reps}. Cost delta: ${cost_delta:.4f}/hr."

        elif action_type == "migrate_to_spot":
            if pod.on_spot:
                msg = f"{target} is already on spot."
                reward = -0.01
            else:
                old_cost = pod.cost_per_hour
                pod.on_spot = True
                saved = old_cost - pod.cost_per_hour
                # Spot has eviction risk — SLA penalty if critical service
                if target in ("frontend", "api-server", "api-v1", "cache"):
                    sla_hit = True
                    self.sla_violations += 1
                    msg = f"Migrated {target} to spot but it's a critical service — SLA risk!"
                    reward = saved * 0.5 - 0.2
                else:
                    msg = f"Migrated {target} to spot. Saved ${saved:.4f}/hr."
                    reward = min(0.4, saved * 3)

        elif action_type == "migrate_to_ondemand":
            if not pod.on_spot:
                msg = f"{target} is already on-demand."
                reward = -0.01
            else:
                pod.on_spot = False
                msg = f"Migrated {target} to on-demand (safer, costs more)."
                reward = 0.05  # small reward for correcting a bad spot migration

        elif action_type == "set_budget_limit":
            self.budget_limit = max(10.0, value)
            msg = f"Budget limit set to ${value:.2f}."
            reward = 0.0

        # Simulate traffic surge for hard task
        if self.task_id == "task_hard" and self.step_num > 8:
            self.traffic_multiplier = 2.5
            if pod and pod.replicas < 3 and not sla_hit:
                sla_hit = True
                self.sla_violations += 1
                msg += " Traffic surge detected — under-provisioned!"
                reward -= 0.2

        self.budget_spent += self.total_cost_per_hour * (1/60)  # simulate 1-min step
        self.step_num += 1
        return round(reward, 4), sla_hit, msg

    def get_response_time_ms(self) -> float:
        """Estimate response time based on CPU utilization."""
        total_requested = sum(p.cpu_requested * p.replicas for p in self.pods)
        total_used = sum(p.cpu_used * p.replicas for p in self.pods)
        if total_requested == 0:
            return 9999.0
        utilization = total_used / total_requested
        # Higher utilization = slower response
        base_ms = 80.0
        response = base_ms * (1 + max(0, (utilization - 0.7)) * 5) * self.traffic_multiplier
        return round(min(response, 5000.0), 1)