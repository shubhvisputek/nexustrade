#!/usr/bin/env bash
set -euo pipefail

# NexusTrade deployment script
# Usage: ./scripts/deploy.sh [cpu-only|full] [--build] [--pull]

PROFILE="${1:-cpu-only}"
BUILD_FLAG=""
PULL_FLAG=""

for arg in "$@"; do
  case "$arg" in
    --build) BUILD_FLAG="--build" ;;
    --pull)  PULL_FLAG="--pull always" ;;
  esac
done

echo "=== NexusTrade Deployment ==="
echo "Profile: $PROFILE"
echo "Build: ${BUILD_FLAG:-no}"

# Pre-flight checks
command -v docker >/dev/null || { echo "Docker not found"; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo "Docker Compose not found"; exit 1; }

# Check .env exists
if [ ! -f .env ]; then
  echo "WARNING: .env file not found. Copying from .env.example..."
  cp .env.example .env 2>/dev/null || echo "No .env.example found. Create .env manually."
fi

# Stop existing services
echo "Stopping existing services..."
docker compose --profile "$PROFILE" down || true

# Build if requested
if [ -n "$BUILD_FLAG" ]; then
  echo "Building images..."
  docker compose --profile "$PROFILE" build
fi

# Start services
echo "Starting services..."
docker compose --profile "$PROFILE" up -d $PULL_FLAG

# Wait for health
echo "Waiting for services to be healthy..."
sleep 10

# Health check
echo "=== Health Status ==="
docker compose ps
echo ""
echo "Checking API health..."
curl -sf http://localhost:8085/health 2>/dev/null && echo "" || echo "API not ready yet (may still be starting)"

echo ""
echo "=== Deployment Complete ==="
echo "Dashboard: http://localhost:8501"
echo "API:       http://localhost:8085"
echo "Metrics:   http://localhost:8085/metrics"
echo "Webhook:   http://localhost:8888/webhook"
