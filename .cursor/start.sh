#!/usr/bin/env bash
# Per-boot startup for the Cloud Agent VM. The Docker engine is installed by
# install.sh; this script starts the daemon on every boot (it is not carried
# over from the build snapshot) and makes the socket usable without sudo.
set -euo pipefail

if sudo docker info >/dev/null 2>&1; then
  echo "==> Docker daemon already running"
else
  echo "==> Starting Docker daemon"
  # Run the redirect inside the root shell: a redirect written by the
  # unprivileged login shell cannot create a file under root-owned /var/log.
  sudo sh -c 'nohup dockerd >/var/log/dockerd.log 2>&1 &'
  for _ in $(seq 1 30); do
    if sudo docker info >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! sudo docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon failed to start; see /var/log/dockerd.log" >&2
  exit 1
fi

# Allow the agent user to talk to Docker without sudo (group membership from
# install.sh does not apply to already-created login sessions).
sudo chmod 666 /var/run/docker.sock || true

echo "==> Docker is ready ($(docker --version))"
