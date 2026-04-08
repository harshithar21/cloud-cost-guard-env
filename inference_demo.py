"""
inference_demo.py — Demo inference script that works without API keys.
Tests the full environment without requiring real LLM API access.
"""
import asyncio
import json
import os
import sys
from typing import List
import httpx
import random

# ── Config ────────────────────────────────────────────────────────────────────
ENV_BASE_URL = os.getenv("ENV_BASE_URL", "http://localhost:8000")
TASKS = ["task_easy", "task_medium", "task_hard"]
MAX_STEPS = {"task_easy": 15, "task_medium": 20, "task_hard": 25}
MAX_TOTAL_REWARD_PER_TASK = 3.0
SUCCESS_THRESHOLD = 0.5

# ── Logging helpers (EXACT format required by hackathon) ──────────────────────
def log_start(task: str, env: str, model: str):
    print(json.dumps({"type": "START", "task": task, "env": env, "model": model}), flush=True)

def log_step(step: int, action: dict, reward: float, done: bool, error=None):
    print(json.dumps({
        "type": "STEP",
        "step": step,
        "action": action,
        "reward": reward,
        "done": done,
        "error": error,
    }), flush=True)

def log_end(success: bool, steps: int, score: float, rewards: List[float]):
    print(json.dumps({
        "type": "END",
        "success": success,
        "steps": steps,
        "score": score,
        "rewards": rewards,
    }), flush=True)

# ── Simple heuristic agent (no API required) ──────────────────────────────────
def get_demo_action(obs: dict, step: int, task_id: str) -> dict:
    """Simple heuristic agent: right-size pods, then migrate to spot."""
    pods = obs.get("pods", [])
    
    if not pods:
        return {"action_type": "noop", "target": "none", "value": 0, "reasoning": "no pods"}
    
    # Strategy 1: Find most wasteful pod and right-size it (easy task)
    if step < 10:
        wasteful = max(pods, key=lambda p: p.get("cpu_waste_ratio", 0) + p.get("mem_waste_ratio", 0))
        if wasteful.get("cpu_waste_ratio", 0) > 0.5:
            return {
                "action_type": "set_request_cpu",
                "target": wasteful["name"],
                "value": round(wasteful["cpu_used"] * 1.1, 2),
                "reasoning": f"Right-size {wasteful['name']} (waste: {wasteful.get('cpu_waste_ratio', 0):.1%})"
            }
    
    # Strategy 2: Migrate batch/non-critical to spot (medium/hard)
    batch_like = [p for p in pods if "batch" in p["name"] or "worker" in p["name"] or "ml" in p["name"]]
    for p in batch_like:
        if not p.get("on_spot"):
            return {
                "action_type": "migrate_to_spot",
                "target": p["name"],
                "value": 0,
                "reasoning": f"Migrate {p['name']} to spot"
            }
    
    # Strategy 3: Reduce replicas if over-provisioned
    for p in pods:
        if p.get("cpu_waste_ratio", 0) > 0.6 and p.get("replicas", 1) > 1:
            return {
                "action_type": "set_replicas",
                "target": p["name"],
                "value": max(1, p.get("replicas", 1) - 1),
                "reasoning": f"Reduce replicas for {p['name']}"
            }
    
    # Default: noop
    return {"action_type": "noop", "target": "none", "value": 0, "reasoning": "no action needed"}

# ── Run one task episode ──────────────────────────────────────────────────────
async def run_task(task_id: str) -> float:
    """Run one full episode for a task. Returns normalized score 0.0–1.0."""
    max_steps = MAX_STEPS[task_id]
    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    log_start(task=task_id, env="cloud_cost_guard_env", model="demo-heuristic")

    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            # Reset with task_id
            reset_resp = await http.post(f"{ENV_BASE_URL}/reset", json={"task_id": task_id})
            result = reset_resp.json()
            obs = result.get("observation", {})

            for step in range(1, max_steps + 1):
                if obs.get("done", False):
                    break

                action = get_demo_action(obs, step, task_id)
                # Wrap action in required format for OpenEnv
                step_resp = await http.post(f"{ENV_BASE_URL}/step", json={"action": action})
                result = step_resp.json()

                obs = result.get("observation", {})
                reward = float(result.get("reward", 0.0))
                done = result.get("done", False)

                rewards.append(reward)
                steps_taken = step

                log_step(step=step, action=action, reward=reward, done=done, error=None)

                if done:
                    break

        total_reward = sum(rewards)
        score = min(1.0, max(0.0, total_reward / MAX_TOTAL_REWARD_PER_TASK))
        success = score >= SUCCESS_THRESHOLD
    except Exception as e:
        print(f"[ERROR] Task {task_id} failed: {e}", flush=True)
        log_step(step=1, action={}, reward=0.0, done=True, error=str(e))

    log_end(success=success, steps=steps_taken, score=score, rewards=rewards)
    return score

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    """Run all tasks."""
    all_scores = {}
    
    print(f"\n{'='*60}", flush=True)
    print("CloudCostGuardEnv - Demo Agent Baseline", flush=True)
    print(f"{'='*60}\n", flush=True)

    for task_id in TASKS:
        print(f"\n{'='*60}", flush=True)
        print(f"Running task: {task_id}", flush=True)
        print(f"{'='*60}", flush=True)
        
        try:
            score = await run_task(task_id)
            all_scores[task_id] = score
            print(f"\n[OK] Task {task_id} completed with score: {score:.4f}\n", flush=True)
        except Exception as e:
            print(f"\n[FAILED] Task {task_id} failed: {e}\n", flush=True)
            all_scores[task_id] = 0.0

    print(f"\n{'='*60}", flush=True)
    print("BASELINE SCORES (Demo Agent):", flush=True)
    print(f"{'='*60}", flush=True)
    for task, s in all_scores.items():
        print(f"  {task:20s}: {s:.4f}", flush=True)
    
    if all_scores:
        avg = sum(all_scores.values()) / len(all_scores)
        print(f"  {'AVERAGE':20s}: {avg:.4f}", flush=True)
    print(f"{'='*60}\n", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
