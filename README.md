git clone https://github.com/yourname/Arcade-Installer.git
cd Arcade-Installer

# Make launcher executable
chmod +x arcade-installer.sh

# Install launcher into PATH
sudo ln -sf "$(pwd)/arcade-installer.sh" /usr/local/bin/arcade-installer

# Install icon (user-local, no cache hacks)
mkdir -p ~/.local/share/icons/hicolor/256x256/apps
cp arcade-installer.png ~/.local/share/icons/hicolor/256x256/apps/

# Install desktop entry
mkdir -p ~/.local/share/applications
cp arcade-installer.desktop ~/.local/share/applications/
