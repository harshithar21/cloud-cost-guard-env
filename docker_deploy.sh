#!/bin/bash
# Quick Docker deployment script

set -e

echo "🚀 CloudCostGuard Docker Deployment"
echo "===================================="

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Menu
echo ""
echo "${BLUE}What would you like to do?${NC}"
echo "1) Build Docker image locally"
echo "2) Run container (requires image to exist)"
echo "3) Push to Docker Hub"
echo "4) Deploy to HuggingFace Spaces"
echo "5) Stop running container"
echo "6) View logs"
echo "7) Clean up all Docker resources"
echo ""
read -p "Enter choice (1-7): " choice

case $choice in
  1)
    echo "${YELLOW}Building Docker image...${NC}"
    docker build -t cloud-cost-guard:latest .
    echo "${GREEN}✅ Build complete!${NC}"
    echo ""
    echo "Next: Run 'docker run -d -p 8000:8000 -p 7860:7860 cloud-cost-guard:latest'"
    ;;
  
  2)
    echo "${YELLOW}Starting container...${NC}"
    CONTAINER_NAME="cloud-cost-guard-$(date +%s)"
    docker run -d \
      --name $CONTAINER_NAME \
      -p 8000:8000 \
      -p 7860:7860 \
      -e API_BASE_URL=http://localhost:8000 \
      cloud-cost-guard:latest
    
    echo "${GREEN}✅ Container started: $CONTAINER_NAME${NC}"
    echo "🎮 Gradio UI: http://localhost:7860"
    echo "📡 API: http://localhost:8000"
    echo ""
    echo "View logs: docker logs -f $CONTAINER_NAME"
    ;;
  
  3)
    read -p "Enter Docker Hub username: " USERNAME
    echo "${YELLOW}Tagging and pushing to Docker Hub...${NC}"
    docker tag cloud-cost-guard:latest $USERNAME/cloud-cost-guard:latest
    docker push $USERNAME/cloud-cost-guard:latest
    echo "${GREEN}✅ Pushed to Docker Hub!${NC}"
    echo "Others can run: docker run -p 8000:8000 -p 7860:7860 $USERNAME/cloud-cost-guard:latest"
    ;;
  
  4)
    echo "${BLUE}HuggingFace Spaces Deployment${NC}"
    echo "Follow these steps:"
    echo "1. Push code to GitHub: git push origin main"
    echo "2. Go to https://huggingface.co/spaces/create"
    echo "3. Select 'Docker' as SDK"
    echo "4. Connect your GitHub repo"
    echo "5. HF Spaces will auto-deploy!"
    ;;
  
  5)
    echo "${YELLOW}Stopping container...${NC}"
    CONTAINER=$(docker ps --quiet --filter "ancestor=cloud-cost-guard:latest")
    if [ -n "$CONTAINER" ]; then
      docker stop $CONTAINER
      echo "${GREEN}✅ Container stopped${NC}"
    else
      echo "No running container found"
    fi
    ;;
  
  6)
    read -p "Container name/ID (or press Enter for latest): " CONTAINER
    if [ -z "$CONTAINER" ]; then
      CONTAINER=$(docker ps --quiet --filter "ancestor=cloud-cost-guard:latest" | head -n1)
    fi
    
    if [ -n "$CONTAINER" ]; then
      docker logs -f $CONTAINER
    else
      echo "No container found"
    fi
    ;;
  
  7)
    echo "${YELLOW}Stopping all containers...${NC}"
    docker stop $(docker ps -q --filter "ancestor=cloud-cost-guard:latest") 2>/dev/null || true
    echo "${YELLOW}Removing containers...${NC}"
    docker rm $(docker ps -aq --filter "ancestor=cloud-cost-guard:latest") 2>/dev/null || true
    echo "${YELLOW}Removing image...${NC}"
    docker rmi cloud-cost-guard:latest 2>/dev/null || true
    echo "${GREEN}✅ Cleanup complete${NC}"
    ;;
  
  *)
    echo "Invalid choice"
    ;;
esac
