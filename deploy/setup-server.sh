#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu/Debian server for CompLens.
# Run it ONCE, on the server:   sudo bash deploy/setup-server.sh
# It: installs Docker, adds swap memory if the server is small, and opens ports 80 and 443.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run with sudo:  sudo bash deploy/setup-server.sh"; exit 1
fi

echo "==> 1/4  Updating the package list and installing basic tools"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl git

echo "==> 2/4  Installing Docker"
if command -v docker >/dev/null 2>&1; then
  echo "Docker is already installed: $(docker --version)"
else
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
  usermod -aG docker "$SUDO_USER"   # so you can run docker without typing sudo (after you log in again)
fi

echo "==> 3/4  Swap memory (a safety net so the build and the OCR never run out of RAM)"
MEM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo)
if [ "$(swapon --show --noheadings | wc -l)" -eq 0 ] && [ "$MEM_MB" -lt 7000 ]; then
  fallocate -l 4G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=4096
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "Added 4 GB swap."
else
  echo "Swap not needed or already present (RAM: ${MEM_MB} MB)."
fi

echo "==> 4/4  Opening ports 22 (SSH), 80 (http) and 443 (https) in the server's own firewall"
if [ -f /etc/iptables/rules.v4 ]; then
  # Oracle Cloud Ubuntu images ship with iptables rules that only allow SSH.
  # Open the ports right now ...
  iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport 80 -j ACCEPT
  iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || iptables -I INPUT -p tcp --dport 443 -j ACCEPT
  # ... and keep them open after a reboot (edit the saved rules file; do not dump Docker's own rules into it)
  if ! grep -q -- '--dport 80 -j ACCEPT' /etc/iptables/rules.v4; then
    sed -i '/--dport 22 -j ACCEPT/a -A INPUT -p tcp -m state --state NEW -m tcp --dport 80 -j ACCEPT\n-A INPUT -p tcp -m state --state NEW -m tcp --dport 443 -j ACCEPT' /etc/iptables/rules.v4
  fi
  echo "iptables updated."
else
  command -v ufw >/dev/null 2>&1 || apt-get install -y ufw
  ufw allow 22/tcp
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw --force enable
fi

echo
echo "Done. Server RAM: ${MEM_MB} MB."
if [ "$MEM_MB" -lt 3000 ]; then
  echo "NOTE: under 3 GB of RAM. In your .env file set OCR_MAX_PASSES=1 so only one OCR model is loaded."
fi
echo "IMPORTANT: log out and log in again (type: exit, then ssh back in) so the docker permission takes effect."
echo "Also open ports 80 and 443 in your cloud provider's own firewall page (see DEPLOY-PYCHARM-AZURE.md, section 4)."
