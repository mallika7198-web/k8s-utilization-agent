#!/bin/bash
# K8s Capacity Analyzer - Startup Script
# Activates venv, runs analysis, and starts HTTP server for viewer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== K8s Capacity Analyzer ===${NC}"

# Activate virtual environment
if [ -d ".venv" ]; then
    echo -e "${YELLOW}Activating virtual environment...${NC}"
    source .venv/bin/activate
else
    echo "Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
fi

# Run analysis (optional - comment out if you just want the server)
if [ "${1:-}" != "--server-only" ]; then
    echo -e "${YELLOW}Running capacity analysis...${NC}"
    python3 capacity_analyzer.py "${2:-clusters.yaml}"
fi

# Start HTTP server for viewer
PORT="${PORT:-8000}"
echo -e "${GREEN}Starting HTTP server on port ${PORT}...${NC}"
echo -e "Open: ${GREEN}http://localhost:${PORT}/viewer/${NC}"
echo -e "Press Ctrl+C to stop"

python3 -m http.server "$PORT"
