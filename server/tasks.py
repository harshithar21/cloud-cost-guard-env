# server/tasks.py
"""
3 tasks with deterministic graders. Score is ALWAYS based on real cluster
state numbers — never hardcoded. Range: 0.0–1.0.
"""
from typing import Dict, Any
from .simulator import ClusterSimulator


def grade_task_easy(sim: ClusterSimulator, baseline_cost: float) -> Dict[str, Any]:
    """
    Task Easy: Pod Right-Sizing
    Goal: Reduce cost by setting CPU/memory requests close to actual usage.
    Score = weighted sum of (cost_saved_ratio, waste_reduced, sla_ok)
    """
    current_cost = sim.total_cost_per_hour

    # Component 1: How much cost was saved (0.0 – 0.6 weight)
    if baseline_cost > 0:
        cost_saved_ratio = max(0.0, (baseline_cost - current_cost) / baseline_cost)
    else:
        cost_saved_ratio = 0.0
    cost_score = min(1.0, cost_saved_ratio / 0.4) * 0.6  # full marks at 40% savings

    # Component 2: Waste reduction — how close are requests to actual usage (0.0 – 0.3 weight)
    total_waste = sum(p.cpu_waste_ratio + p.mem_waste_ratio for p in sim.pods)
    avg_waste = total_waste / (len(sim.pods) * 2) if sim.pods else 1.0
    waste_score = (1.0 - avg_waste) * 0.3

    # Component 3: SLA penalty (0.0 – 0.1 weight)
    sla_score = max(0.0, 0.1 - sim.sla_violations * 0.05)

    total = round(cost_score + waste_score + sla_score, 4)
    return {
        "score": min(1.0, total),
        "cost_saved_pct": round(cost_saved_ratio * 100, 2),
        "avg_waste_ratio": round(avg_waste, 4),
        "sla_violations": sim.sla_violations,
        "breakdown": {"cost_score": cost_score, "waste_score": waste_score, "sla_score": sla_score}
    }


def grade_task_medium(sim: ClusterSimulator, baseline_cost: float) -> Dict[str, Any]:
    """
    Task Medium: Spot Migration + Auto-scaling
    Goal: Move batch/ML workloads to spot, right-size others, keep SLA.
    Score = cost_saved + spot_migration_quality + sla_ok
    """
    current_cost = sim.total_cost_per_hour
    cost_saved_ratio = max(0.0, (baseline_cost - current_cost) / baseline_cost) if baseline_cost > 0 else 0.0
    cost_score = min(1.0, cost_saved_ratio / 0.5) * 0.5  # full marks at 50% savings

    # Check spot migration quality — batch-job and ml-worker should be on spot
    spot_candidates = {"batch-job", "ml-worker"}
    correctly_spotted = sum(1 for p in sim.pods if p.name in spot_candidates and p.on_spot)
    critical_on_spot = sum(1 for p in sim.pods if p.name in {"frontend", "api-server"} and p.on_spot)
    spot_score = (correctly_spotted / len(spot_candidates)) * 0.3
    spot_score -= critical_on_spot * 0.15  # penalize risky spot migrations
    spot_score = max(0.0, spot_score)

    # SLA score
    sla_score = max(0.0, 0.2 - sim.sla_violations * 0.07)

    total = round(cost_score + spot_score + sla_score, 4)
    return {
        "score": min(1.0, max(0.0, total)),
        "cost_saved_pct": round(cost_saved_ratio * 100, 2),
        "correctly_spotted": correctly_spotted,
        "critical_on_spot": critical_on_spot,
        "sla_violations": sim.sla_violations,
        "breakdown": {"cost_score": cost_score, "spot_score": spot_score, "sla_score": sla_score}
    }


def grade_task_hard(sim: ClusterSimulator, baseline_cost: float) -> Dict[str, Any]:
    """
    Task Hard: Multi-cluster budget balancing under traffic surge.
    Goal: Stay under budget, maintain SLA during traffic surge, minimize cost.
    Score = budget_ok + sla_under_surge + cost_efficiency
    """
    current_cost = sim.total_cost_per_hour

    # Component 1: Budget compliance (0.0 – 0.35)
    if sim.budget_spent <= sim.budget_limit:
        budget_score = 0.35
    else:
        overage = (sim.budget_spent - sim.budget_limit) / sim.budget_limit
        budget_score = max(0.0, 0.35 - overage * 0.5)

    # Component 2: SLA under traffic surge (0.0 – 0.4)
    response_ms = sim.get_response_time_ms()
    if response_ms <= 500:
        sla_score = 0.4
    elif response_ms <= 1000:
        sla_score = 0.4 * (1000 - response_ms) / 500
    else:
        sla_score = 0.0
    sla_score = max(0.0, sla_score - sim.sla_violations * 0.08)

    # Component 3: Cost efficiency (0.0 – 0.25)
    cost_saved_ratio = max(0.0, (baseline_cost - current_cost) / baseline_cost) if baseline_cost > 0 else 0.0
    cost_score = min(0.25, cost_saved_ratio / 0.3 * 0.25)

    total = round(budget_score + sla_score + cost_score, 4)
    return {
        "score": min(1.0, max(0.0, total)),
        "budget_spent": round(sim.budget_spent, 4),
        "budget_limit": sim.budget_limit,
        "response_time_ms": response_ms,
        "cost_saved_pct": round(cost_saved_ratio * 100, 2),
        "sla_violations": sim.sla_violations,
        "breakdown": {"budget_score": budget_score, "sla_score": sla_score, "cost_score": cost_score}
    }


GRADERS = {
    "task_easy": grade_task_easy,
    "task_medium": grade_task_medium,
    "task_hard": grade_task_hard,
}

TASK_DESCRIPTIONS = {
    "task_easy": {
        "name": "Pod Right-Sizing",
        "description": "Your cluster is over-provisioned. Set CPU/memory requests close to actual usage to cut costs without violating SLAs.",
        "max_steps": 15,
        "target_score": 0.7,
        "hint": "Use set_request_cpu and set_request_memory actions. Check cpu_used and mem_used_mb to right-size each pod.",
    },
    "task_medium": {
        "name": "Spot Migration + Auto-scaling",
        "description": "Migrate batch/ML workloads to cheaper spot instances. Right-size other pods. Keep critical services on on-demand.",
        "max_steps": 20,
        "target_score": 0.65,
        "hint": "Use migrate_to_spot for batch-job and ml-worker. Avoid spotting frontend and api-server. Also right-size log-proc.",
    },
    "task_hard": {
        "name": "Budget Balancing Under Surge",
        "description": "Optimize costs under a tight budget while maintaining SLA during unexpected traffic surges in step 9+.",
        "max_steps": 25,
        "target_score": 0.55,
        "hint": "Pre-scale critical pods before surge. Move non-critical to spot. Monitor budget_remaining closely.",
    },
}