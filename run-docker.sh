#!/bin/bash
# Helper script to run Quotio in Docker with X11 forwarding

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Quotio Docker Runner${NC}"
echo "===================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    exit 1
fi

# Check if X11 is available (Linux)
if [ "$(uname)" = "Linux" ]; then
    if [ -z "$DISPLAY" ]; then
        echo -e "${YELLOW}Warning: DISPLAY not set. Setting to :0${NC}"
        export DISPLAY=:0
    fi
    
    # Check X11 socket
    if [ ! -S /tmp/.X11-unix/X0 ] && [ ! -S /tmp/.X11-unix/X${DISPLAY#*:} ]; then
        echo -e "${RED}Error: X11 socket not found${NC}"
        echo "Make sure X server is running"
        exit 1
    fi
    
    # Allow Docker to access X11
    echo -e "${YELLOW}Allowing Docker to access X11...${NC}"
    xhost +local:docker 2>/dev/null || true
fi

# Build image if it doesn't exist
if ! docker images | grep -q quotio-python; then
    echo -e "${GREEN}Building Docker image...${NC}"
    docker build -t quotio-python .
fi

# Create directories if they don't exist
mkdir -p ~/.quotio
mkdir -p ~/.cli-proxy-api

# Run container
echo -e "${GREEN}Starting Quotio...${NC}"

if [ "$(uname)" = "Linux" ]; then
    # Linux: X11 forwarding
    docker run -it --rm \
        --name quotio-python \
        -e DISPLAY=$DISPLAY \
        -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
        -v ~/.quotio:/home/quotio/.quotio:rw \
        -v ~/.cli-proxy-api:/home/quotio/.cli-proxy-api:rw \
        --network host \
        quotio-python
elif [ "$(uname)" = "Darwin" ]; then
    # macOS: XQuartz
    echo -e "${YELLOW}macOS detected. Using XQuartz.${NC}"
    echo "Make sure XQuartz is running: open -a XQuartz"
    docker run -it --rm \
        --name quotio-python \
        -e DISPLAY=host.docker.internal:0 \
        -v ~/.quotio:/home/quotio/.quotio:rw \
        -v ~/.cli-proxy-api:/home/quotio/.cli-proxy-api:rw \
        --network host \
        quotio-python
else
    echo -e "${YELLOW}Windows or other OS detected.${NC}"
    echo "Consider using VNC method (see DOCKER_GUI_GUIDE.md)"
    docker run -it --rm \
        --name quotio-python \
        -v ~/.quotio:/home/quotio/.quotio:rw \
        -v ~/.cli-proxy-api:/home/quotio/.cli-proxy-api:rw \
        --network host \
        quotio-python
fi

# Cleanup X11 access (Linux)
if [ "$(uname)" = "Linux" ]; then
    echo -e "${YELLOW}Revoking X11 access...${NC}"
    xhost -local:docker 2>/dev/null || true
fi

echo -e "${GREEN}Done!${NC}"
