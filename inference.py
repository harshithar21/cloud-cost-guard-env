"""
inference.py — CloudCostGuardEnv baseline inference script
Required by hackathon. Uses OpenAI client. Reads credentials from env vars.
Emits [START], [STEP], [END] logs exactly as specified.
"""
import asyncio
import json
import os
import sys
import time
from typing import List

from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
API_KEY      = os.getenv("HF_TOKEN", "")
MODEL_NAME   = os.getenv("MODEL_NAME", "meta-llama/Llama-3.2-3B-Instruct")
TEMPERATURE  = 0.3
MAX_TOKENS   = 512

TASKS        = ["task_easy", "task_medium", "task_hard"]
MAX_STEPS    = {"task_easy": 15, "task_medium": 20, "task_hard": 25}
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

# ── LLM call ──────────────────────────────────────────────────────────────────
def get_action(client: OpenAI, obs: dict, step: int, task_id: str) -> dict:
    """Ask the LLM to choose an action given the current observation."""
    pods_summary = "\n".join([
        f"  - {p['name']}: cpu_req={p['cpu_requested']} cpu_used={p['cpu_used']} "
        f"mem_req={p['mem_requested_mb']}MB mem_used={p['mem_used_mb']}MB "
        f"replicas={p['replicas']} spot={p['on_spot']} cost=${p['cost_per_hour']}/hr"
        for p in obs.get("pods", [])
    ])

    prompt = f"""You are a Kubernetes FinOps agent. Your goal is to reduce cloud costs while maintaining SLAs.

Current cluster state (step {step}):
- Total cost: ${obs['total_cost_per_hour']}/hr (baseline: ${obs['baseline_cost_per_hour']}/hr)
- Cost saved so far: {obs['cost_saved_percent']}%
- SLA violations: {obs['sla_violations']}
- Response time: {obs['avg_response_time_ms']}ms (SLA limit: {obs['sla_threshold_ms']}ms)
- Budget remaining: ${obs['budget_remaining']:.2f} of ${obs['budget_limit']:.2f}
- Last message: {obs['message']}

Pods:
{pods_summary}

Available actions:
- set_request_cpu: target=<pod_name>, value=<cpu_cores>
- set_request_memory: target=<pod_name>, value=<mb>
- set_replicas: target=<pod_name>, value=<count>
- migrate_to_spot: target=<pod_name>, value=0
- migrate_to_ondemand: target=<pod_name>, value=0
- noop: target=none, value=0

Respond ONLY with a JSON object:
{{"action_type": "...", "target": "...", "value": <number>, "reasoning": "..."}}

Pick the action that saves the most cost without violating SLAs."""

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        text = (resp.choices[0].message.content or "").strip()
        # Extract JSON from response
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        action = json.loads(text)
        # Validate required fields
        if "action_type" not in action:
            raise ValueError("Missing action_type")
        return action
    except Exception as e:
        # Fallback: find most wasteful pod and right-size it
        pods = obs.get("pods", [])
        if pods:
            worst = max(pods, key=lambda p: p.get("cpu_waste_ratio", 0))
            return {
                "action_type": "set_request_cpu",
                "target": worst["name"],
                "value": round(worst["cpu_used"] * 1.2, 2),
                "reasoning": "fallback: right-size most wasteful pod"
            }
        return {"action_type": "noop", "target": "none", "value": 0, "reasoning": "fallback noop"}


# ── Run one task episode ──────────────────────────────────────────────────────
async def run_task(task_id: str, client: OpenAI) -> float:
    """Run one full episode for a task. Returns normalized score 0.0–1.0."""
    import httpx

    base_url = os.getenv("ENV_BASE_URL", "http://localhost:8000")
    max_steps = MAX_STEPS[task_id]
    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    log_start(task=task_id, env="cloud_cost_guard_env", model=MODEL_NAME)

    async with httpx.AsyncClient(timeout=30.0) as http:
        # Reset with task_id
        reset_resp = await http.post(f"{base_url}/reset", json={"task_id": task_id})
        result = reset_resp.json()
        obs = result.get("observation", {})

        for step in range(1, max_steps + 1):
            if obs.get("done", False):
                break

            action = get_action(client, obs, step, task_id)
            # Wrap action in required format for OpenEnv
            step_resp = await http.post(f"{base_url}/step", json={"action": action})
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
    log_end(success=success, steps=steps_taken, score=score, rewards=rewards)
    return score


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY or "dummy")
    all_scores = {}

    for task_id in TASKS:
        print(f"\n{'='*50}", flush=True)
        print(f"Running task: {task_id}", flush=True)
        score = await run_task(task_id, client)
        all_scores[task_id] = score
        print(f"Task {task_id} score: {score:.4f}", flush=True)

    print(f"\n{'='*50}", flush=True)
    print("BASELINE SCORES:", flush=True)
    for task, s in all_scores.items():
        print(f"  {task}: {s:.4f}", flush=True)
    avg = sum(all_scores.values()) / len(all_scores)
    print(f"  AVERAGE: {avg:.4f}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())