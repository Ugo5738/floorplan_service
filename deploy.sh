#!/bin/bash

# Load environment variables from .env
set -a
source .env
set +a

# Stop and remove current containers first (ensures clean slate)
echo "Stopping and removing current containers..."
docker compose -f docker-compose-prod.yml down --remove-orphans # Added --remove-orphans

# Start containers with the updated image, forcing a pull
echo "Starting containers, ensuring latest image is pulled..."
# No need for separate docker pull if using --pull always
# docker pull $DOCKER_IMAGE
docker compose -f docker-compose-prod.yml up -d --pull always --remove-orphans

echo "Deployment completed successfully."