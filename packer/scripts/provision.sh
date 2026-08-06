#!/usr/bin/env bash

set -euo pipefail

echo "==> Waiting for cloud-init to complete..."
sudo cloud-init status --wait || true

echo "==> Updating package repository and installing Docker..."
for i in {1..5}; do
    if sudo apt-get update; then
        break
    fi
    echo "apt-get update retry $i/5..."
    sleep 5
done

sudo apt-get install -y --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Install Docker GPG key & repo
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

for i in {1..5}; do
    if sudo apt-get update; then
        break
    fi
    echo "apt-get update retry $i/5..."
    sleep 5
done

sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

sudo usermod -aG docker ubuntu

echo "==> Installing Kanga-Route stack to /opt/kanga-route..."
sudo mkdir -p /opt/kanga-route
sudo cp -r /tmp/kanga-route/* /opt/kanga-route/
sudo chown -R root:root /opt/kanga-route

# Copy CLI wrapper to /usr/local/bin
sudo cp /opt/kanga-route/bin/kanga-route /usr/local/bin/kanga-route
sudo chmod +x /usr/local/bin/kanga-route

# Copy systemd service unit
sudo cp /opt/kanga-route/systemd/kanga-route.service /etc/systemd/system/kanga-route.service
sudo systemctl daemon-reload
sudo systemctl enable kanga-route.service

echo "==> Pre-pulling DynamoDB Local sidecar and building engine..."
cd /opt/kanga-route
sudo docker compose pull dynamodb-local
sudo docker compose build engine

echo "==> Cleaning up build context artifacts..."
sudo rm -rf /tmp/kanga-route

echo "==> Provisioning complete."
