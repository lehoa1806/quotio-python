#!/bin/bash
# Helper script to run Quotio in Docker on macOS

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Quotio Docker Runner (macOS)${NC}"
echo "================================"

# Check if running on macOS
if [ "$(uname)" != "Darwin" ]; then
    echo -e "${RED}Error: This script is for macOS only${NC}"
    echo "Use run-docker.sh for Linux"
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    echo "Install Docker Desktop from: https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Check if XQuartz is installed
if ! command -v xquartz &> /dev/null && [ ! -d "/Applications/Utilities/XQuartz.app" ]; then
    echo -e "${YELLOW}XQuartz not found. Installing...${NC}"
    if command -v brew &> /dev/null; then
        brew install --cask xquartz
    else
        echo -e "${RED}Error: Homebrew not found. Please install XQuartz manually:${NC}"
        echo "https://www.xquartz.org/"
        exit 1
    fi
fi

# Check if XQuartz is running
if ! pgrep -x "Xquartz" > /dev/null; then
    echo -e "${YELLOW}Starting XQuartz...${NC}"
    open -a XQuartz
    echo "Waiting for XQuartz to start..."
    sleep 3
fi

# Allow connections from Docker
echo -e "${YELLOW}Configuring X11 access...${NC}"
xhost +localhost 2>/dev/null || true

# Set DISPLAY for Docker
export DISPLAY=host.docker.internal:0

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
echo -e "${YELLOW}Note: GUI will appear in XQuartz window${NC}"

docker run -it --rm \
    --name quotio-python \
    -e DISPLAY=host.docker.internal:0 \
    -v ~/.quotio:/home/quotio/.quotio:rw \
    -v ~/.cli-proxy-api:/home/quotio/.cli-proxy-api:rw \
    --network host \
    quotio-python

# Cleanup
echo -e "${YELLOW}Cleaning up X11 access...${NC}"
xhost -localhost 2>/dev/null || true

echo -e "${GREEN}Done!${NC}"
