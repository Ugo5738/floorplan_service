#!/bin/bash

# Load environment variables from .env
set -a
source .env
set +a

# Pull the latest Docker image from .env
echo "Pulling Docker image: $DOCKER_IMAGE"
docker pull $DOCKER_IMAGE

# Stop and remove current containers
echo "Stopping and removing current containers..."
docker compose -f docker-compose-prod.yml down

# Start containers with the updated image
echo "Starting containers with the updated image..."
docker compose -f docker-compose-prod.yml up -d

echo "Deployment completed successfully."