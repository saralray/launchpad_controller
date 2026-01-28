#!/usr/bin/env bash
set -e

### CONFIG ###
USER_NAME="saral"
PROJECT_DIR="/home/${USER_NAME}/launchpad_controller"
VENV_DIR="${PROJECT_DIR}/launchpad_controller"
SERVICE_NAME="launchpad_controller"
PYTHON_BIN="python3.12"

VENDOR_ID="1235"   # Focusrite / Novation
PRODUCT_ID="0113"  # Launchpad Mini MK3 (from lsusb)

echo "🚀 Installing Launchpad Controller..."

### 1️⃣ Check Python ###
if ! command -v ${PYTHON_BIN} >/dev/null 2>&1; then
  echo "❌ ${PYTHON_BIN} not found"
  exit 1
fi

### 2️⃣ Install system dependencies ###
echo "📦 Installing system dependencies..."
sudo dnf install -y \
  gcc gcc-c++ make \
  alsa-lib-devel \
  pkgconf-pkg-config \
  cmake \
  python3.12-devel

### 3️⃣ Create virtual environment ###
echo "🐍 Creating virtual environment..."
cd "${PROJECT_DIR}"

if [ ! -d "${VENV_DIR}" ]; then
  ${PYTHON_BIN} -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"

pip install --upgrade pip
pip install -r requirements.txt

### 4️⃣ Create systemd service ###
echo "⚙️ Installing systemd service..."
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=Launchpad Mini MK3 Controller
After=sound.target network.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${VENV_DIR}/bin/python controller.py
Restart=on-failure
RestartSec=2
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

### 5️⃣ Create udev rule ###
echo "🔌 Installing udev rule..."
sudo tee /etc/udev/rules.d/99-launchpad.rules > /dev/null <<EOF
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="${VENDOR_ID}", ATTR{idProduct}=="${PRODUCT_ID}", \
  RUN+="/usr/bin/systemctl start ${SERVICE_NAME}.service"

ACTION=="remove", SUBSYSTEM=="usb", ATTR{idVendor}=="${VENDOR_ID}", ATTR{idProduct}=="${PRODUCT_ID}", \
  RUN+="/usr/bin/systemctl stop ${SERVICE_NAME}.service"
EOF

### 6️⃣ Reload systemd + udev ###
echo "🔄 Reloading system services..."
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "✅ Installation complete!"
echo ""
echo "👉 Unplug & replug your Launchpad to auto-start the controller"
echo "👉 Logs: journalctl -u ${SERVICE_NAME} -f"
