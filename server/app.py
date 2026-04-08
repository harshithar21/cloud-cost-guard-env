# server/app.py
import os
import sys
from pathlib import Path
app = FastAPI()
# Add parent directory to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from openenv.core.env_server import create_app
from models import CostGuardAction, CostGuardObservation
from server.environment import CloudCostGuardEnvironment

task_id = os.getenv("TASK_ID", "task_easy")
seed = int(os.getenv("SEED", "42"))

def create_env():
    return CloudCostGuardEnvironment(task_id=task_id, seed=seed)

app = create_app(create_env, CostGuardAction, CostGuardObservation, env_name="cloud_cost_guard_env")

@app.get("/")
def root():
    """Root endpoint - returns API info."""
    return {
        "message": "CloudCostGuard RL Environment Server",
        "endpoints": {
            "health": "GET /health",
            "reset": "POST /reset",
            "step": "POST /step",
            "docs": "GET /docs"
        }
    }