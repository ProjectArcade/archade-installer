#!/usr/bin/env bash
set -e

echo "== Arcade Installer :: Uninstall =="

# Remove launcher
rm -f "$HOME/.local/bin/arcade-installer"
echo "✔ Launcher removed"

# Remove desktop entry
rm -f "$HOME/.local/share/applications/arcade-installer.desktop"
echo "✔ Desktop entry removed"

# Remove icon
rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/arcade-installer.png"
echo "✔ Icon removed"

# Remove MIME associations (user-only, safe)
rm -f "$HOME/.local/share/applications/mimeapps.list"

# Clear KDE / desktop caches (safe)
rm -rf "$HOME/.cache/ksycoca*" "$HOME/.cache/kioexec"

echo ""
echo "======================================"
echo " Arcade Installer completely removed"
echo "======================================"
echo ""
echo "➡ Log out and log back in once"
