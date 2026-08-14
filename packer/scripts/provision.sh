#!/usr/bin/env bash

set -euo pipefail

retry() {
    local attempt
    for attempt in {1..5}; do
        if "$@"; then
            return 0
        fi
        echo "Command failed (attempt ${attempt}/5); retrying..." >&2
        sleep 5
    done
    echo "Command failed after 5 attempts: $*" >&2
    return 1
}

echo "==> Waiting for cloud-init to complete..."
sudo cloud-init status --wait || true

echo "==> Updating package repository and installing Docker..."
retry sudo apt-get update

sudo apt-get install -y --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    util-linux

# Install Docker GPG key & repo
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

retry sudo apt-get update

sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

sudo usermod -aG docker ubuntu
sudo systemctl enable docker.service

echo "==> Installing Kanga-Route stack to /opt/kanga-route..."
sudo install -d -m 0755 /opt/kanga-route
sudo cp -a /tmp/kanga-route/. /opt/kanga-route/
sudo chown -R root:root /opt/kanga-route
sudo install -m 0600 -o root -g root /opt/kanga-route/.env.example /opt/kanga-route/.env

sudo install -m 0755 -o root -g root /opt/kanga-route/bin/kanga-route /usr/local/bin/kanga-route

echo "==> Installing and enabling systemd units..."
sudo install -m 0644 -o root -g root /opt/kanga-route/systemd/kanga-route.service /etc/systemd/system/kanga-route.service
sudo install -m 0644 -o root -g root /opt/kanga-route/systemd/kanga-route-run.service /etc/systemd/system/kanga-route-run.service
sudo install -m 0644 -o root -g root /opt/kanga-route/systemd/kanga-route-run.timer /etc/systemd/system/kanga-route-run.timer
sudo systemctl daemon-reload
sudo systemctl enable kanga-route.service kanga-route-run.timer

echo "==> Pre-pulling DynamoDB Local sidecar and building engine..."
cd /opt/kanga-route
sudo docker compose config --quiet
sudo docker compose pull dynamodb-local
sudo docker compose build engine

echo "==> Cleaning up build context artifacts..."
sudo find /tmp/kanga-route -mindepth 1 -delete
sudo rmdir /tmp/kanga-route

echo "==> Provisioning complete."
