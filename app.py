# server/app.py
import os, sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
from typing import Optional
from models import CostGuardAction, CostGuardObservation
from server.environment import CloudCostGuardEnvironment

app = FastAPI()

task_id = os.getenv("TASK_ID", "task_easy")
seed = int(os.getenv("SEED", "42"))

_env: CloudCostGuardEnvironment = None

def get_env(tid=None):
    global _env
    if _env is None or (tid and tid != _env.task_id):
        _env = CloudCostGuardEnvironment(task_id=tid or task_id, seed=seed)
    return _env

@app.get("/")
def root():
    return {"message": "CloudCostGuard RL Environment", "status": "ok"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/reset")
def reset(body: dict = Body(default={})):
    tid = body.get("task_id", task_id)
    env = get_env(tid)
    obs = env.reset()
    return {"observation": obs, "done": False, "reward": 0.0, "info": {}}

@app.post("/step")
def step(body: dict = Body(...)):
    action = body.get("action", body)
    env = get_env()
    obs, reward, done, info = env.step(action)
    return {"observation": obs, "reward": float(reward), "done": done, "info": info}

@app.get("/state")
def state():
    env = get_env()
    return env.state() if hasattr(env, "state") else {}

def main():
    import uvicorn
    uvicorn.run("server.app:app", host="0.0.0.0", port=7860)

if __name__ == "__main__":
    main()