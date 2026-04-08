"""
ui.py - Interactive Gradio interface for CloudCostGuardEnv
Allows users to train and test FinOps agents in an episodic RL environment
"""
import gradio as gr
import httpx
import json
import os
import pandas as pd
from typing import Optional

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Global state for current episode
episode_state = {
    "task_id": None,
    "obs": None,
    "cumulative_reward": 0.0,
    "step_count": 0,
    "max_steps": 15,
    "done": False,
    "history": []
}

async def reset_episode(task_id: str):
    """Reset the environment for a new episode."""
    try:
        # Explicitly clear global state first
        episode_state["task_id"] = task_id
        episode_state["cumulative_reward"] = 0.0
        episode_state["step_count"] = 0
        episode_state["done"] = False
        episode_state["history"] = []
        episode_state["obs"] = None
        
        # Make API call to reset
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(
                f"{API_BASE_URL}/reset",
                json={"task_id": task_id}
            )
            
            if resp.status_code != 200:
                print(f"Reset error response: {resp.status_code} - {resp.text}")
                return f"Error: {resp.text}", "", "", "", "[]"
            
            obs = resp.json().get("observation", {})
            if not obs:
                print("Warning: Empty observation from reset")
                obs = {}
            
            # Set observation after clearing everything
            episode_state["obs"] = obs
            
            # Determine max steps based on task
            max_steps_map = {"task_easy": 15, "task_medium": 20, "task_hard": 25}
            episode_state["max_steps"] = max_steps_map.get(task_id, 15)
            
            print(f"Episode reset: task={task_id}, steps=0, reward=0.0, max_steps={episode_state['max_steps']}")
            
            dashboard = format_dashboard(obs)
            pod_table = format_pod_table(obs)
            metrics = format_metrics(obs, 0, 0)
            
            return dashboard, pod_table, metrics, "Episode ready. Execute actions below.", "[]"
            
    except Exception as e:
        print(f"Reset exception: {str(e)}")
        return f"Error: {str(e)}", "", "", "", "[]"


async def step_environment(action_type: str, target_pod: str, value: float, reasoning: str):
    """Take a step in the current episode."""
    try:
        if episode_state["obs"] is None:
            return "Please start an episode first.", "", "", "", "[]"
        
        if episode_state["done"]:
            return "Episode complete. Start a new one.", "", "", "", "[]"
        
        if episode_state["step_count"] >= episode_state["max_steps"]:
            return "Max steps reached. Start a new episode.", "", "", "", "[]"
        
        # Map display names to internal action names
        action_map = {
            "Lower CPU request": "set_request_cpu",
            "Lower Memory request": "set_request_memory",
            "Change replicas": "set_replicas",
            "Move to Spot": "migrate_to_spot",
            "Move to On-Demand": "migrate_to_ondemand",
            "No action": "noop"
        }
        
        internal_action = action_map.get(action_type, "noop")
        
        async with httpx.AsyncClient(timeout=30.0) as http:
            action = {
                "action_type": internal_action,
                "target": target_pod,
                "value": value,
                "reasoning": reasoning or "Optimization strategy"
            }
            
            step_resp = await http.post(
                f"{API_BASE_URL}/step",
                json={"action": action}
            )
            
            if step_resp.status_code != 200:
                print(f"Step error: {step_resp.status_code} - {step_resp.text}")
                return f"Error: {step_resp.text}", "", "", "", "[]"
            
            result = step_resp.json()
            obs = result.get("observation", {})
            reward = result.get("reward", 0.0)
            done = result.get("done", False)
            info = result.get("info", {})
            
            # Update global state
            episode_state["obs"] = obs
            episode_state["step_count"] += 1
            episode_state["cumulative_reward"] += reward
            episode_state["done"] = done
            
            # Add to history
            episode_state["history"].append({
                "step": episode_state["step_count"],
                "action": f"{action_type}({target_pod}={value})",
                "reward": reward,
                "cumulative": episode_state["cumulative_reward"]
            })
            
            print(f"Step {episode_state['step_count']}/{episode_state['max_steps']}: reward={reward:+.4f}, cumulative={episode_state['cumulative_reward']:+.4f}, done={done}")
            
            # Format response
            status = "Success" if reward > 0 else "Reduced Reward"
            if done:
                final_score = info.get('score', 0)
                result_text = f"**{status}** · Step {episode_state['step_count']}/{episode_state['max_steps']}\n\n**Reward:** {reward:+.4f} · **Final Score:** {final_score:.3f}/1.0\n\nEpisode complete!"
            else:
                result_text = f"**{status}** · Step {episode_state['step_count']}/{episode_state['max_steps']}\n\n**Reward:** {reward:+.4f} · **Total:** {episode_state['cumulative_reward']:+.4f}"
            
            pod_table = format_pod_table(obs)
            metrics = format_metrics(obs, episode_state["cumulative_reward"], episode_state["step_count"])
            history_df = pd.DataFrame(episode_state["history"])
            history_json = history_df.to_json(orient="records")
            
            return result_text, pod_table, metrics, history_json, json.dumps(obs, indent=2)
            
    except Exception as e:
        print(f"Step exception: {str(e)}")
        return f"Error: {str(e)}", "", "", "", "[]"


def format_dashboard(obs: dict) -> str:
    """Format clean dashboard display."""
    cost = obs.get('total_cost_per_hour', 0)
    baseline = obs.get('baseline_cost_per_hour', 0)
    saved = obs.get('cost_saved_percent', 0)
    budget = obs.get('budget_remaining', 0)
    sla = obs.get('sla_violations', 0)
    response_time = obs.get('avg_response_time_ms', 0)
    
    return f"""
**Total Cost:** ${cost:.2f}/hr · **Baseline:** ${baseline:.2f}/hr · **Saved:** {saved:.1f}%

**Budget:** ${budget:.2f} · **SLA Violations:** {sla} · **Latency:** {response_time:.1f}ms
"""


def format_pod_table(obs: dict) -> str:
    """Format pod information as clean table."""
    pods = obs.get('pods', [])
    if not pods:
        return "No pod data"
    
    lines = ["| Pod | CPU | Memory | Replicas | Cost/hr |", 
             "|-----|-----|--------|----------|---------|"]
    
    for pod in pods[:6]:
        name = pod.get('name', 'N/A')[:12]
        cpu = f"{pod.get('cpu_requested', 0):.1f}"
        mem = f"{pod.get('mem_requested_mb', 0):.0f}"
        reps = pod.get('replicas', 1)
        cost = f"${pod.get('cost_per_hour', 0):.2f}"
        lines.append(f"| {name} | {cpu} | {mem} | {reps} | {cost} |")
    
    return "\n".join(lines)


def format_metrics(obs: dict, cumulative_reward: float, steps: int) -> str:
    """Format key metrics cleanly."""
    efficiency = obs.get('efficiency_score', 0)
    sla_good = "Yes" if obs.get('sla_violations', 0) == 0 else "No"
    
    return f"""
**Step:** {steps} · **Cumulative Reward:** {cumulative_reward:+.4f}

**Efficiency:** {efficiency:.2f} · **SLA Healthy:** {sla_good}
"""


def get_action_guidance(action_type: str) -> str:
    """Return guidance text for each action type."""
    guidance = {
        "Lower CPU request": """**CPU Reduction** · Lower the CPU reserved for a pod
- **Value range:** 0.1 - 8.0 cores
- **Example:** Current=4.0 → Set to 3.0 to save costs
- ⚠️ Too low causes SLA violations if pod needs more CPU""",
        
        "Lower Memory request": """**Memory Reduction** · Lower the memory reserved for a pod
- **Value range:** 128 - 4096 MB
- **Example:** Current=2048 MB → Set to 1536 MB to save costs
- ⚠️ Too low causes pod eviction if usage spikes""",
        
        "Change replicas": """**Scaling** · Increase or decrease pod replicas
- **Value range:** 1 - 10 replicas
- **Example:** Current=2 → Set to 1 to reduce cost (risky), or 3 for more availability
- ⚠️ Too few replicas reduce availability, too many waste money""",
        
        "Move to Spot": """**Spot Instances** · Move pod to cheaper Spot instances (can be interrupted)
- **Value:** Enter 0 or 1 (0=no action, 1=migrate to spot)
- **Benefit:** 60-90% cheaper but can be terminated
- ⚠️ Only safe for non-critical workloads""",
        
        "Move to On-Demand": """**On-Demand Instances** · Move pod back to reliable On-Demand instances
- **Value:** Enter 0 or 1 (0=no action, 1=migrate to on-demand)
- **Cost:** Higher than Spot but guaranteed uptime
- ✓ Best for critical services (api-server, db-proxy)""",
        
        "No action": """**No-Op** · Skip this step without making changes
- **Value:** Any value (ignored)
- **Use when:** You need to observe effect of previous action"""
    }
    return guidance.get(action_type, "Select an action type to see guidance")


def update_value_guidance(action_type: str):
    """Update UI based on selected action."""
    guidance = get_action_guidance(action_type)
    
    # Set placeholder based on action
    placeholders = {
        "Lower CPU request": "e.g., 2.0 (in cores)",
        "Lower Memory request": "e.g., 1024 (in MB)",
        "Change replicas": "e.g., 2 (1-10)",
        "Move to Spot": "1 to move, 0 to cancel",
        "Move to On-Demand": "1 to move, 0 to cancel",
        "No action": "ignored"
    }
    placeholder = placeholders.get(action_type, "Enter value")
    
    return gr.update(info=placeholder), gr.update(value=guidance)


def create_interface():
    """Create clean, professional Gradio interface."""
    
    with gr.Blocks(title="CloudCostGuardEnv") as demo:
        # Header
        with gr.Row():
            with gr.Column():
                gr.Markdown('# CloudCostGuardEnv')
                gr.Markdown(
                    'Optimize Kubernetes costs while maintaining service quality. '
                    'Control a simulated cluster and learn cost-saving strategies.'
                )
        
        gr.Markdown("---")
        
        # Control Panel
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("**Select Task**")
                task_id = gr.Dropdown(
                    choices=[
                        ("Easy - Pod Right-Sizing", "task_easy"),
                        ("Medium - Spot Migration", "task_medium"),
                        ("Hard - Budget Management", "task_hard")
                    ],
                    value="task_easy",
                    label=None,
                    interactive=True
                )
            
            with gr.Column(scale=1):
                gr.Markdown("**Action**")
                reset_btn = gr.Button("Start Episode", variant="primary", size="lg", scale=2)
        
        gr.Markdown("---")
        
        # Dashboard
        with gr.Row():
            with gr.Column():
                gr.Markdown("**Cluster Status**")
                dashboard = gr.Markdown(value="Start an episode to see metrics")
        
        gr.Markdown("---")
        
        # Pod Table
        with gr.Row():
            with gr.Column():
                gr.Markdown("**Resources**")
                pod_table = gr.Markdown(value="Waiting...")
        
        gr.Markdown("---")
        
        # Actions
        gr.Markdown("## Take Action")
        
        with gr.Row():
            with gr.Column():
                action_type = gr.Dropdown(
                    choices=[
                        "Lower CPU request",
                        "Lower Memory request",
                        "Change replicas",
                        "Move to Spot",
                        "Move to On-Demand",
                        "No action"
                    ],
                    value="No action",
                    label="Action Type",
                    info="Select what optimization to perform"
                )
            
            with gr.Column():
                target_pod = gr.Textbox(
                    value="frontend",
                    label="Target Pod",
                    placeholder="e.g., frontend, api-server, worker",
                    info="Which pod to target (see list above)"
                )
        
        # Guidance box (updates dynamically)
        with gr.Row():
            with gr.Column():
                action_guide = gr.Markdown(value=get_action_guidance("No action"))
        
        with gr.Row():
            with gr.Column():
                value = gr.Number(
                    value=0.0,
                    label="Value",
                    info="ignored",
                    precision=1
                )
            
            with gr.Column():
                reasoning = gr.Textbox(
                    value="",
                    label="Why?",
                    lines=2,
                    placeholder="Brief explanation (optional) - why this action?"
                )
        
        with gr.Row():
            execute_btn = gr.Button("Execute", variant="primary", size="lg", scale=2)
        
        gr.Markdown("---")
        
        # Results
        with gr.Row():
            with gr.Column():
                gr.Markdown("**Result**")
                step_result = gr.Markdown(value="Execute an action to see results")
            
            with gr.Column():
                gr.Markdown("**Progress**")
                metrics = gr.Markdown(value="...")
        
        gr.Markdown("---")
        
        # Data
        with gr.Row():
            history_json = gr.Code(value="[]", language="json", label="History")
        
        with gr.Row():
            obs_json = gr.Code(value="{}", language="json", label="Full State")
        
        gr.Markdown("---")
        
        # Help
        gr.Markdown("## Help")
        gr.Markdown("""
**Tasks:**
- **Easy:** Find over-provisioned pods, reduce CPU/Memory to match usage
- **Medium:** Move batch workloads to cheaper Spot instances, keep critical services safe
- **Hard:** Stay within budget during traffic surge by scaling strategically

**Pods available:** frontend, api-server, worker, cache, db-proxy, batch-job, ml-worker, log-proc

**Goal:** Get a final score of 1.0 by reducing costs while keeping SLA violations at 0.
        """)
        
        # Event Handlers
        reset_btn.click(
            fn=reset_episode,
            inputs=[task_id],
            outputs=[dashboard, pod_table, metrics, step_result, history_json]
        )
        
        execute_btn.click(
            fn=step_environment,
            inputs=[action_type, target_pod, value, reasoning],
            outputs=[step_result, pod_table, metrics, history_json, obs_json]
        )
        
        # Update guidance when action type changes
        action_type.change(
            fn=update_value_guidance,
            inputs=[action_type],
            outputs=[value, action_guide]
        )
    
    return demo


if __name__ == "__main__":
    print("Starting CloudCostGuardEnv Gradio Interface...")
    print(f"API Base URL: {API_BASE_URL}")
    print("\nLaunch at: http://localhost:7860")
    
    interface = create_interface()
    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )
