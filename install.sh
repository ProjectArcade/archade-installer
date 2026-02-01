#!/usr/bin/env bash
set -e

APP_NAME="arcade-installer"
INSTALL_DIR="/opt/arcade-installer"

echo "== Arcade Installer :: System Installation =="

# ----------------------------
# 1. Install app files
# ----------------------------
sudo mkdir -p "$INSTALL_DIR"
sudo cp -r src assets "$INSTALL_DIR"
sudo chmod -R 755 "$INSTALL_DIR"

echo "✔ Application files installed to $INSTALL_DIR"

# ----------------------------
# 2. Install launcher
# ----------------------------
sudo install -Dm755 launcher/arcade-installer /usr/bin/arcade-installer
echo "✔ Launcher installed to /usr/bin"

# ----------------------------
# 3. Install icon
# ----------------------------
sudo install -Dm644 assets/arcade-installer.png \
  /usr/share/icons/hicolor/256x256/apps/arcade-installer.png
echo "✔ Icon installed"

# ----------------------------
# 4. Desktop entry
# ----------------------------
sudo tee /usr/share/applications/arcade-installer.desktop >/dev/null <<EOF
[Desktop Entry]
Version=1.0
Name=Arcade Installer
Comment=Install applications without the terminal
Exec=/usr/bin/arcade-installer %f
Icon=arcade-installer
Terminal=false
Type=Application
Categories=System;Utility;
StartupNotify=true
MimeType=application/octet-stream;
EOF

echo "✔ Desktop entry installed"

# ----------------------------
# 5. Update caches (silent)
# ----------------------------
command -v update-desktop-database >/dev/null && \
  sudo update-desktop-database /usr/share/applications || true

command -v gtk-update-icon-cache >/dev/null && \
  sudo gtk-update-icon-cache -q /usr/share/icons/hicolor || true

# ----------------------------
# Done
# ----------------------------
echo ""
echo "======================================"
echo " Arcade Installer installed successfully"
echo "======================================"
echo ""
echo "➡ Open from App Menu or run: arcade-installer"
