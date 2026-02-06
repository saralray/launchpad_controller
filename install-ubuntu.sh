#!/usr/bin/env bash
set -e

# ======================================================
# CONFIG
# ======================================================
APP_NAME="launchpad_controller"

# safer user detection on Ubuntu
USER_NAME="${SUDO_USER:-$(id -un)}"

SRC_DIR="$(pwd)"
DEST_DIR="/opt/${APP_NAME}"
VENV_DIR="${DEST_DIR}/venv"

SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
UDEV_RULE="/etc/udev/rules.d/99-${APP_NAME}.rules"

PYTHON_BIN="/usr/bin/python3"

# Launchpad vendor/product
VENDOR_ID="1235"
PRODUCT_ID="0113"

# ======================================================
# PRECHECK
# ======================================================
if [[ $EUID -ne 0 ]]; then
  echo "❌ Please run with sudo"
  exit 1
fi

echo "🧹 Removing old services, rules, and files..."

systemctl stop ${APP_NAME}.service 2>/dev/null || true
systemctl disable ${APP_NAME}.service 2>/dev/null || true
systemctl reset-failed ${APP_NAME}.service 2>/dev/null || true

rm -f "$SERVICE_FILE"
rm -f "$UDEV_RULE"
rm -rf "$DEST_DIR"

systemctl daemon-reload
udevadm control --reload-rules

# ======================================================
# SYSTEM DEPENDENCIES (UBUNTU)
# ======================================================
echo "📦 Installing system dependencies..."

apt update
apt install -y \
  python3 \
  python3-venv \
  python3-dev \
  python3-pip \
  build-essential \
  pkg-config \
  cmake \
  libasound2-dev \
  udev \
  systemd

# ======================================================
# COPY PROJECT
# ======================================================
echo "📁 Copying project to ${DEST_DIR}"

mkdir -p "$DEST_DIR"
cp -a "${SRC_DIR}/." "$DEST_DIR"
chown -R ${USER_NAME}:${USER_NAME} "$DEST_DIR"

# ======================================================
# PYTHON VIRTUALENV
# ======================================================
echo "🐍 Creating virtualenv"

sudo -u ${USER_NAME} ${PYTHON_BIN} -m venv "$VENV_DIR"

echo "📦 Installing Python packages"

sudo -u ${USER_NAME} "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel

if [[ -f "${DEST_DIR}/requirements.txt" ]]; then
  sudo -u ${USER_NAME} "$VENV_DIR/bin/pip" install -r "${DEST_DIR}/requirements.txt"
else
  echo "⚠️ requirements.txt not found – skipping"
fi

# ======================================================
# .env
# ======================================================
if [[ -f "${SRC_DIR}/.env" ]]; then
  echo "🔐 Copying .env"
  cp "${SRC_DIR}/.env" "${DEST_DIR}/.env"
  chown ${USER_NAME}:${USER_NAME} "${DEST_DIR}/.env"
else
  echo "⚠️ No .env found – controller will run in PASSIVE MODE"
fi

# ======================================================
# SYSTEMD SERVICE
# ======================================================
echo "⚙️ Creating systemd service"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Launchpad Controller
After=network.target sound.target
Wants=sound.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${DEST_DIR}
EnvironmentFile=-${DEST_DIR}/.env

# wait for USB + MIDI stack
ExecStartPre=/bin/sleep 5

ExecStart=${VENV_DIR}/bin/python ${DEST_DIR}/controller.py
Restart=on-failure
RestartSec=2

# better realtime MIDI stability
Nice=-10

[Install]
WantedBy=multi-user.target
EOF

# ======================================================
# UDEV RULE (START ON PLUG)
# ======================================================
echo "🔌 Creating udev rule (start on plug only)"

cat > "$UDEV_RULE" <<EOF
ACTION=="add", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", \\
  ATTR{idVendor}=="${VENDOR_ID}", ATTR{idProduct}=="${PRODUCT_ID}", \\
  TAG+="systemd", ENV{SYSTEMD_WANTS}="${APP_NAME}.service"
EOF

# ======================================================
# RELOAD
# ======================================================
echo "🔄 Reloading systemd & udev"

systemctl daemon-reload
udevadm control --reload-rules
udevadm trigger

echo ""
echo "✅ Installation complete (Ubuntu)"
echo "👉 Plug Launchpad → service starts"
echo "👉 Unplug → service keeps running (idle)"
echo "👉 Replug → reconnects automatically"
echo "👉 Logs: journalctl -u ${APP_NAME} -f"
