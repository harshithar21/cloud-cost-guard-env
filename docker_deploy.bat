@echo off
REM Quick Docker deployment script for Windows

setlocal enabledelayedexpansion

echo 🚀 CloudCostGuard Docker Deployment
echo ====================================

:menu
echo.
echo What would you like to do?
echo 1 - Build Docker image locally
echo 2 - Run container (requires image to exist)
echo 3 - Push to Docker Hub
echo 4 - Deploy to HuggingFace Spaces
echo 5 - Stop running container
echo 6 - View logs
echo 7 - Clean up all Docker resources
echo.

set /p choice="Enter choice (1-7): "

if "%choice%"=="1" (
    echo Building Docker image...
    docker build -t cloud-cost-guard:latest .
    echo.
    echo ✅ Build complete!
    echo.
    echo Next: Run 'docker run -d -p 8000:8000 -p 7860:7860 cloud-cost-guard:latest'
    goto menu
)

if "%choice%"=="2" (
    echo Starting container...
    
    REM Generate random container name
    for /f %%A in ('powershell Get-Random') do set RAND=%%A
    set CONTAINER_NAME=cloud-cost-guard-!RAND!
    
    docker run -d ^
      --name !CONTAINER_NAME! ^
      -p 8000:8000 ^
      -p 7860:7860 ^
      -e API_BASE_URL=http://localhost:8000 ^
      cloud-cost-guard:latest
    
    echo.
    echo ✅ Container started: !CONTAINER_NAME!
    echo 🎮 Gradio UI: http://localhost:7860
    echo 📡 API: http://localhost:8000
    echo.
    echo View logs: docker logs -f !CONTAINER_NAME!
    goto menu
)

if "%choice%"=="3" (
    set /p USERNAME="Enter Docker Hub username: "
    echo Tagging and pushing to Docker Hub...
    docker tag cloud-cost-guard:latest %USERNAME%/cloud-cost-guard:latest
    docker push %USERNAME%/cloud-cost-guard:latest
    echo.
    echo ✅ Pushed to Docker Hub!
    echo Others can run: docker run -p 8000:8000 -p 7860:7860 %USERNAME%/cloud-cost-guard:latest
    goto menu
)

if "%choice%"=="4" (
    echo HuggingFace Spaces Deployment
    echo Follow these steps:
    echo 1. Push code to GitHub: git push origin main
    echo 2. Go to https://huggingface.co/spaces/create
    echo 3. Select 'Docker' as SDK
    echo 4. Connect your GitHub repo:
    echo    - Username: your_github_username
    echo    - Repo: cloud-cost-guard-env
    echo 5. Enable Auto-Deploy
    echo 6. HF Spaces will auto-deploy!
    echo.
    echo 📖 Full guide: See DOCKER_HACKATHON_GUIDE.md
    goto menu
)

if "%choice%"=="5" (
    echo Stopping container...
    for /f %%i in ('docker ps -q --filter "ancestor=cloud-cost-guard:latest"') do (
        docker stop %%i
        echo ✅ Container stopped: %%i
    )
    goto menu
)

if "%choice%"=="6" (
    set /p CONTAINER="Container name/ID (or press Enter for latest): "
    if "!CONTAINER!"=="" (
        for /f %%i in ('docker ps -q --filter "ancestor=cloud-cost-guard:latest" ^| findstr /O .*') do (
            set CONTAINER=%%i
            goto show_logs
        )
    )
    
    :show_logs
    if "!CONTAINER!"=="" (
        echo No container found
    ) else (
        docker logs -f !CONTAINER!
    )
    goto menu
)

if "%choice%"=="7" (
    echo Stopping all containers...
    for /f %%i in ('docker ps -q --filter "ancestor=cloud-cost-guard:latest"') do (
        docker stop %%i
    )
    
    echo Removing containers...
    for /f %%i in ('docker ps -aq --filter "ancestor=cloud-cost-guard:latest"') do (
        docker rm %%i
    )
    
    echo Removing image...
    docker rmi cloud-cost-guard:latest 2>nul
    
    echo ✅ Cleanup complete
    goto menu
)

echo Invalid choice, please try again
goto menu

:end
endlocal
