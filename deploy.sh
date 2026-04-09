#!/bin/bash
set -euo pipefail

# Disney Piano Stream — Deployment Script
# Run this on a fresh Ubuntu/Debian VM to set up everything.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "=============================================="
echo "  Disney Piano Stream — Deployment"
echo "=============================================="
echo ""

# ── System packages ──────────────────────────────

echo "[1/6] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-venv python3-pip \
    ffmpeg fluidsynth fluid-soundfont-gm \
    fonts-dejavu-core \
    > /dev/null 2>&1
echo "  Done."

# ── Python virtual environment ───────────────────

echo "[2/6] Setting up Python environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Done."

# ── Directory structure ──────────────────────────

echo "[3/6] Creating directories..."
mkdir -p output queue library/videos library/thumbnails overlays/images templates static
echo "  Done."

# ── Environment file ────────────────────────────

echo "[4/6] Checking configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "  =========================================="
    echo "  IMPORTANT: Edit .env with your API keys!"
    echo "  =========================================="
    echo ""
    echo "  nano $SCRIPT_DIR/.env"
    echo ""
else
    echo "  .env already exists, skipping."
fi

# ── Systemd service ─────────────────────────────

echo "[5/6] Installing systemd service..."

# Update paths in service file to match actual install location
SERVICE_FILE="$SCRIPT_DIR/disney-stream.service"
ACTUAL_USER="$(whoami)"

# Create a temp service file with correct paths
cat > /tmp/disney-stream.service <<EOF
[Unit]
Description=Disney Piano Livestream
After=network.target

[Service]
Type=simple
User=$ACTUAL_USER
WorkingDirectory=$SCRIPT_DIR
EnvironmentFile=$SCRIPT_DIR/.env
ExecStart=$SCRIPT_DIR/venv/bin/gunicorn \\
    --bind 0.0.0.0:8080 \\
    --workers 1 \\
    --threads 4 \\
    --timeout 300 \\
    app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo cp /tmp/disney-stream.service /etc/systemd/system/disney-stream.service
sudo systemctl daemon-reload
sudo systemctl enable disney-stream
echo "  Done."

# ── Start service ────────────────────────────────

echo "[6/6] Starting service..."
sudo systemctl restart disney-stream

# Wait a moment and check status
sleep 2
if sudo systemctl is-active --quiet disney-stream; then
    echo "  Service is running!"
else
    echo "  WARNING: Service may not have started. Check:"
    echo "  sudo journalctl -u disney-stream -n 20"
fi

# ── Done ─────────────────────────────────────────

IP=$(hostname -I | awk '{print $1}')
PORT=8080

echo ""
echo "=============================================="
echo "  Deployment Complete!"
echo "=============================================="
echo ""
echo "  Web UI:  http://$IP:$PORT"
echo ""
echo "  Next steps:"
echo "  1. Open the URL above in your browser"
echo "  2. Go to Settings and enter your API keys"
echo "  3. Go to Generate to create your first video"
echo "  4. Once you have videos, start streaming!"
echo ""
echo "  Useful commands:"
echo "  sudo systemctl status disney-stream"
echo "  sudo systemctl restart disney-stream"
echo "  sudo journalctl -u disney-stream -f"
echo ""
