#!/usr/bin/env bash
# scripts/server_setup.sh
# Run once on a fresh Amazon Linux 2023 t3.medium to prepare it for Northbridge.
# Usage: bash scripts/server_setup.sh
set -euo pipefail

echo "==> [1/5] Updating system packages"
sudo dnf update -y -q

echo "==> [2/5] Installing Docker"
sudo dnf install -y -q docker

echo "==> [3/5] Enabling Docker to start on boot"
sudo systemctl enable docker
sudo systemctl start docker

echo "==> [4/5] Adding current user to docker group (re-login required)"
sudo usermod -aG docker "$USER"

echo "==> [5/5] Installing Docker Compose plugin"
DOCKER_CONFIG=${DOCKER_CONFIG:-$HOME/.docker}
mkdir -p "$DOCKER_CONFIG/cli-plugins"
curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o "$DOCKER_CONFIG/cli-plugins/docker-compose"
chmod +x "$DOCKER_CONFIG/cli-plugins/docker-compose"

echo "==> Setting vm.overcommit_memory for Redis"
sudo sysctl -w vm.overcommit_memory=1
echo "vm.overcommit_memory = 1" | sudo tee -a /etc/sysctl.conf

echo "==> Verifying installation"
docker --version
docker compose version

echo ""
echo "✓ Server setup complete."
echo ""
echo "Next steps:"
echo "  1. Log out and back in (or run: newgrp docker) so group change takes effect"
echo "  2. Clone your repo: git clone <your-repo-url> northbridge && cd northbridge"
echo "  3. Copy secrets:    cp .env.example .env && nano .env"
echo "  4. Start services:  docker compose up --build -d"
echo "  5. Check health:    docker compose ps"