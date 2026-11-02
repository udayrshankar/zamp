#!/usr/bin/env bash
# One-time setup for a fresh EC2 instance running Ubuntu or Amazon Linux 2023.
# Run as the default login user (ubuntu or ec2-user).
set -euo pipefail

# Swap gives OCR spikes and image builds room on a 2 GB instance.
# dd rather than fallocate, because XFS (Amazon Linux) rejects sparse swapfiles.
if [ ! -f /swapfile ]; then
  sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

if ! command -v docker >/dev/null; then
  if command -v dnf >/dev/null; then
    # Amazon Linux ships Docker but not the compose or buildx plugins.
    sudo dnf install -y -q docker git
    arch=$(uname -m)
    plugins=/usr/local/lib/docker/cli-plugins
    sudo mkdir -p "$plugins"
    sudo curl -fsSL -o "$plugins/docker-compose" \
      "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$arch"
    buildx_arch=$([ "$arch" = aarch64 ] && echo arm64 || echo amd64)
    buildx_version=$(curl -fsSL -o /dev/null -w '%{url_effective}' \
      https://github.com/docker/buildx/releases/latest | sed 's#.*/##')
    sudo curl -fsSL -o "$plugins/docker-buildx" \
      "https://github.com/docker/buildx/releases/download/$buildx_version/buildx-$buildx_version.linux-$buildx_arch"
    sudo chmod +x "$plugins/docker-compose" "$plugins/docker-buildx"
  else
    sudo apt-get update -qq
    sudo apt-get install -y -qq git
    curl -fsSL https://get.docker.com | sudo sh
  fi
  sudo usermod -aG docker "$USER"
fi

# Keep container logs from filling the disk.
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" } }
JSON
sudo systemctl enable docker
sudo systemctl restart docker

echo "Setup done. Log out and back in so the docker group applies."
