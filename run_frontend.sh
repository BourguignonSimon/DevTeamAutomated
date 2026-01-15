#!/bin/bash
# Run the Frontend API Gateway
#
# Usage:
#   ./run_frontend.sh           # Uses default settings (Redis on localhost:6379)
#   ./run_frontend.sh --dev     # Development mode with auto-reload
#
# Environment variables:
#   REDIS_HOST    - Redis server host (default: localhost)
#   REDIS_PORT    - Redis server port (default: 6379)
#   PORT          - API server port (default: 3000)
#   LOG_LEVEL     - Logging level (default: INFO)

set -e

cd "$(dirname "$0")"

# Default configuration
export REDIS_HOST="${REDIS_HOST:-localhost}"
export REDIS_PORT="${REDIS_PORT:-6379}"
export PORT="${PORT:-3000}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

echo "========================================"
echo "  DevTeam Automated - Frontend API"
echo "========================================"
echo ""
echo "Configuration:"
echo "  Redis:  ${REDIS_HOST}:${REDIS_PORT}"
echo "  Port:   ${PORT}"
echo "  Log:    ${LOG_LEVEL}"
echo ""
echo "Open http://localhost:${PORT} in your browser"
echo "========================================"
echo ""

if [ "$1" == "--dev" ]; then
    echo "Starting in development mode (auto-reload enabled)..."
    python -m uvicorn services.frontend_api.main:app --host 0.0.0.0 --port "$PORT" --reload
else
    python -m uvicorn services.frontend_api.main:app --host 0.0.0.0 --port "$PORT"
fi
