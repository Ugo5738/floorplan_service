#!/bin/bash

# Update package index
sudo apt-get update

# Install Docker and Docker Compose from Ubuntu's repository
# sudo apt-get install -y docker.io docker-compose

# Optionally, install the latest version of Docker from Docker's official repository
# Uncomment the following lines to use this option

# Remove any existing Docker installations
sudo apt-get remove -y docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc

# Install dependencies
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# Add Docker's GPG key and repository
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo install -m 0755 -d /etc/apt/keyrings
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine, CLI, and Containerd
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Verify Docker installation
docker -v

# Run Docker without sudo (optional)
sudo usermod -aG docker $USER

# Inform user to log out and log back in
echo "Please log out and log back in to apply Docker group changes, or reboot the system."

# make this script executable with "chmod +x install_docker.sh"
# run script with "./install_docker.sh".
