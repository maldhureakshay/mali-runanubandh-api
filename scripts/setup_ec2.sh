#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
# EC2 Initial Setup Script for Matrimony API
#
# Run this ONCE on a fresh EC2 Ubuntu instance to set up:
#   - System packages (Python 3.11, Nginx, Certbot, UFW)
#   - Dedicated 'matrimony' service user
#   - App directory, virtual environment, dependencies
#   - Gunicorn systemd service
#   - Nginx reverse proxy
#   - UFW firewall rules
#   - Log rotation
#
# Usage:
#   chmod +x scripts/setup_ec2.sh
#   sudo bash scripts/setup_ec2.sh <GITHUB_REPO_URL> [DOMAIN_NAME]
#
# Example:
#   sudo bash scripts/setup_ec2.sh git@github.com:maldhureakshay/mali-runanubandh-api.git api.example.com
# ────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="/opt/matrimony-api"
SERVICE_USER="matrimony"
LOG_DIR="/var/log/matrimony-api"
REPO_URL="${1:?Usage: $0 <GITHUB_REPO_URL> [DOMAIN_NAME]}"
DOMAIN="${2:-_}"  # underscore = IP-only, no SSL

echo "════════════════════════════════════════════════"
echo "  Matrimony API — EC2 Setup"
echo "════════════════════════════════════════════════"

# ── 1. System Packages ──────────────────────────────────────────
echo ""
echo "📦 [1/8] Installing system packages..."
apt update && apt upgrade -y
apt install -y python3.11 python3.11-venv python3.11-dev \
    python3-pip nginx certbot python3-certbot-nginx \
    git curl ufw

# ── 2. Create Service User ──────────────────────────────────────
echo ""
echo "👤 [2/8] Creating service user '${SERVICE_USER}'..."
if ! id -u "${SERVICE_USER}" &>/dev/null; then
    useradd -m -s /bin/bash "${SERVICE_USER}"
    echo "   Created user: ${SERVICE_USER}"
else
    echo "   User '${SERVICE_USER}' already exists, skipping."
fi

# ── 3. Clone Repository ─────────────────────────────────────────
echo ""
echo "📥 [3/8] Cloning repository..."
if [ -d "${APP_DIR}/.git" ]; then
    echo "   Repository already exists at ${APP_DIR}, pulling latest..."
    sudo -u "${SERVICE_USER}" git -C "${APP_DIR}" pull origin main
else
    mkdir -p "${APP_DIR}"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"
    sudo -u "${SERVICE_USER}" git clone "${REPO_URL}" "${APP_DIR}"
fi

# ── 4. Python Virtual Environment & Dependencies ────────────────
echo ""
echo "🐍 [4/8] Setting up Python virtual environment..."
sudo -u "${SERVICE_USER}" bash -c "
    cd ${APP_DIR}
    python3.11 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    pip install gunicorn -q
"

# ── 5. Create .env (if not present) ─────────────────────────────
echo ""
echo "⚙️  [5/8] Configuring environment..."
if [ ! -f "${APP_DIR}/.env" ]; then
    cat > "${APP_DIR}/.env" <<'ENVEOF'
# ── Production Configuration ──
APP_NAME="Matrimony Geo-Search API"
DEBUG=false
HOST="0.0.0.0"
PORT=8000

# MongoDB (update with your credentials)
MONGO_URI="mongodb://localhost:27017/matrimony"
MONGO_DB_NAME="matrimony"
MONGO_COLLECTION_NAME="profiles"
ENVEOF
    chown "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"
    echo "   Created ${APP_DIR}/.env — ⚠️  UPDATE MONGO_URI WITH AUTH CREDENTIALS"
else
    echo "   .env already exists, skipping."
fi

# ── 6. Systemd Service ──────────────────────────────────────────
echo ""
echo "🔧 [6/8] Creating systemd service..."
mkdir -p "${LOG_DIR}"
chown "${SERVICE_USER}:${SERVICE_USER}" "${LOG_DIR}"

cat > /etc/systemd/system/matrimony-api.service <<EOF
[Unit]
Description=Matrimony Geo-Search API (Gunicorn + Uvicorn)
After=network.target mongod.service
Wants=mongod.service

[Service]
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/.venv/bin:/usr/bin"
ExecStart=${APP_DIR}/.venv/bin/gunicorn main:app -c gunicorn.conf.py
ExecReload=/bin/kill -s HUP \$MAINPID

Restart=on-failure
RestartSec=10
StartLimitBurst=5
StartLimitIntervalSec=60

# Security hardening
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=${LOG_DIR} ${APP_DIR}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable matrimony-api
echo "   Service created and enabled."

# ── 7. Nginx Reverse Proxy ──────────────────────────────────────
echo ""
echo "🌐 [7/8] Configuring Nginx..."
cat > /etc/nginx/sites-available/matrimony-api <<NGINXEOF
# Rate limiting: 10 req/sec per IP
limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=10r/s;

upstream matrimony_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name ${DOMAIN};

    # Security headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;

    location / {
        proxy_pass http://matrimony_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_http_version 1.1;
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
        proxy_send_timeout 60s;
        limit_req zone=api_limit burst=20 nodelay;
    }

    location /health {
        proxy_pass http://matrimony_backend;
        access_log off;
    }

    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/matrimony-api /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
echo "   Nginx configured and reloaded."

# ── 8. Firewall ─────────────────────────────────────────────────
echo ""
echo "🔒 [8/8] Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
echo "   Firewall enabled (SSH + Nginx only)."

# ── 9. Log Rotation ─────────────────────────────────────────────
cat > /etc/logrotate.d/matrimony-api <<'LOGEOF'
/var/log/matrimony-api/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 matrimony matrimony
    sharedscripts
    postrotate
        systemctl reload matrimony-api > /dev/null 2>&1 || true
    endscript
}
LOGEOF

# ── Done ─────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════"
echo "  ✅ Setup Complete!"
echo "════════════════════════════════════════════════"
echo ""
echo "  Next steps:"
echo "  1. Edit ${APP_DIR}/.env with your MongoDB credentials"
echo "  2. Start the service:  sudo systemctl start matrimony-api"
echo "  3. Verify:             curl http://127.0.0.1:8000/health"
echo ""
if [ "${DOMAIN}" != "_" ]; then
    echo "  4. SSL:  sudo certbot --nginx -d ${DOMAIN}"
fi
echo ""
