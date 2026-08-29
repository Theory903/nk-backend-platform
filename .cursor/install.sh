#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for the NK Backend / FastAPI-template generator.
# Runs once to build the environment snapshot: install uv, the Docker engine
# (needed by `nk build`, docker-compose smoke tests, and the CI matrix), and
# the generator's Python dependencies. Per-boot daemon startup lives in start.sh.
set -euo pipefail

UV_VERSION="0.9.12"

echo "==> Ensuring uv ${UV_VERSION} is installed"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh
fi
# uv installs to ~/.local/bin, which is already on the login PATH.
export PATH="${HOME}/.local/bin:${PATH}"
uv --version

echo "==> Ensuring the Docker engine is installed"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi

echo "==> Ensuring fuse-overlayfs is installed (nested-VM storage driver)"
if ! command -v fuse-overlayfs >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y --no-install-recommends fuse-overlayfs
fi

echo "==> Configuring the Docker daemon for the Cloud Agent VM"
sudo mkdir -p /etc/docker
# The default overlay2 driver cannot mount inside the nested Cloud Agent VM;
# fuse-overlayfs works with the /dev/fuse device that is available here.
printf '{\n  "storage-driver": "fuse-overlayfs"\n}\n' | sudo tee /etc/docker/daemon.json >/dev/null
sudo usermod -aG docker "${USER}" || true

echo "==> Installing generator dependencies (uv sync --locked)"
uv sync --locked

echo "==> install.sh complete"
