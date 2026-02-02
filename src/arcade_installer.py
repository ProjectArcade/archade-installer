#!/usr/bin/env python3
import sys
import os
import tarfile
import tempfile
import configparser
import shutil
import subprocess
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                             QPushButton, QHBoxLayout, QMessageBox, QProgressBar)
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt, QTimer, QSize, QThread, pyqtSignal

# ----------------------------
# Resolve paths
# ----------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_PATH = os.path.join(BASE_DIR, "assets", "arcade-installer.png")
DEFAULT_APP_ICON = os.path.join(BASE_DIR, "assets", "arcade-installer.png")

# Default installation directory
INSTALL_DIR = os.path.expanduser("~/.local/share/applications")
BIN_DIR = os.path.expanduser("~/.local/bin")
DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")

# ----------------------------
# Installation Worker Thread
# ----------------------------
class InstallWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str)  # success, message, executable_path
    
    def __init__(self, tar_path, app_name):
        super().__init__()
        self.tar_path = tar_path
        self.app_name = app_name
        self.executable_path = None
    
    def run(self):
        try:
            # Create installation directories
            os.makedirs(INSTALL_DIR, exist_ok=True)
            os.makedirs(BIN_DIR, exist_ok=True)
            os.makedirs(DESKTOP_DIR, exist_ok=True)
            
            self.status.emit("Preparing installation...")
            self.progress.emit(10)
            
            # Create app-specific directory
            app_dir = os.path.join(INSTALL_DIR, self.app_name.replace(' ', '-').lower())
            if os.path.exists(app_dir):
                shutil.rmtree(app_dir)
            os.makedirs(app_dir)
            
            self.status.emit("Extracting files...")
            self.progress.emit(30)
            
            # Extract tar.gz
            with tarfile.open(self.tar_path, 'r:*') as tar:
                tar.extractall(app_dir)
            
            self.progress.emit(60)
            self.status.emit("Setting up application...")
            
            # Find executable or main script
            executable = None
            for root, dirs, files in os.walk(app_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Look for executables or scripts
                    if os.access(file_path, os.X_OK):
                        executable = file_path
                        break
                    elif file.endswith(('.sh', '.py', '.run')):
                        executable = file_path
                        os.chmod(executable, 0o755)
                        break
                if executable:
                    break
            
            self.progress.emit(80)
            
            # Create symlink in bin directory if executable found
            if executable:
                bin_link = os.path.join(BIN_DIR, self.app_name.replace(' ', '-').lower())
                if os.path.exists(bin_link):
                    os.remove(bin_link)
                os.symlink(executable, bin_link)
                self.executable_path = executable  # Store for launching
                self.status.emit("Creating shortcuts...")
            
            # Look for .desktop file and copy to applications
            desktop_file = None
            for root, dirs, files in os.walk(app_dir):
                for file in files:
                    if file.endswith('.desktop'):
                        desktop_file = os.path.join(root, file)
                        break
                if desktop_file:
                    break
            
            # If .desktop file exists, update and copy it
            if desktop_file:
                desktop_dest = os.path.expanduser(f"~/.local/share/applications/{os.path.basename(desktop_file)}")
                
                # Read and update .desktop file to ensure correct paths
                try:
                    with open(desktop_file, 'r') as f:
                        desktop_content = f.read()
                    
                    # Update Exec path if needed
                    if executable and 'Exec=' in desktop_content:
                        lines = desktop_content.split('\n')
                        updated_lines = []
                        for line in lines:
                            if line.startswith('Exec='):
                                updated_lines.append(f'Exec={executable}')
                            else:
                                updated_lines.append(line)
                        desktop_content = '\n'.join(updated_lines)
                    
                    # Write updated .desktop file
                    with open(desktop_dest, 'w') as f:
                        f.write(desktop_content)
                    os.chmod(desktop_dest, 0o755)
                except:
                    # If update fails, just copy the original
                    shutil.copy2(desktop_file, desktop_dest)
                    os.chmod(desktop_dest, 0o755)
            
            # If no .desktop file found, create one
            else:
                desktop_dest = os.path.expanduser(f"~/.local/share/applications/{self.app_name.replace(' ', '-').lower()}.desktop")
                
                # Find icon in the extracted files
                icon_path = None
                for root, dirs, files in os.walk(app_dir):
                    for file in files:
                        if any(file.lower().endswith(ext) for ext in ['.png', '.svg', '.ico', '.jpg', '.jpeg']):
                            if 'icon' in file.lower() or 'logo' in file.lower():
                                icon_path = os.path.join(root, file)
                                break
                    if icon_path:
                        break
                
                # Create .desktop file content
                desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name={self.app_name}
Comment=Installed via Arcade Installer
Exec={executable if executable else '/bin/true'}
Icon={icon_path if icon_path else 'application-x-executable'}
Terminal=false
Categories=Application;
"""
                
                # Write .desktop file
                with open(desktop_dest, 'w') as f:
                    f.write(desktop_content)
                os.chmod(desktop_dest, 0o755)
            
            # Update desktop database to make the app appear immediately
            try:
                subprocess.run(['update-desktop-database', os.path.expanduser('~/.local/share/applications')], 
                             check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except:
                pass
            
            self.progress.emit(100)
            self.status.emit("Installation complete!")
            
            self.finished.emit(True, f"Successfully installed {self.app_name}", self.executable_path or "")
            
        except Exception as e:
            self.finished.emit(False, f"Installation failed: {str(e)}", "")

# ----------------------------
# Extract app metadata from tar.gz
# ----------------------------
def extract_app_metadata(tar_path):
    """Extract app icon, name, and publisher from tar.gz file"""
    metadata = {
        'name': 'Unknown Application',
        'publisher': 'Unknown Publisher',
        'icon_path': DEFAULT_APP_ICON,
        'version': 'Unknown'
    }
    
    if not tar_path or not os.path.exists(tar_path):
        return metadata
    
    try:
        with tarfile.open(tar_path, 'r:*') as tar:
            members = tar.getnames()
            
            # Look for .desktop file or app metadata
            desktop_file = None
            icon_file = None
            
            # First pass: find .desktop file (highest priority)
            for member in members:
                if member.lower().endswith('.desktop'):
                    desktop_file = member
                    break
            
            # Parse .desktop file if found (this is the most reliable source)
            if desktop_file:
                try:
                    desktop_content = tar.extractfile(desktop_file).read().decode('utf-8')
                    
                    # Parse manually to handle files without proper sections
                    for line in desktop_content.split('\n'):
                        line = line.strip()
                        if line.startswith('Name='):
                            metadata['name'] = line.split('=', 1)[1].strip()
                        elif line.startswith('Comment='):
                            metadata['publisher'] = line.split('=', 1)[1].strip()
                        elif line.startswith('GenericName=') and metadata['publisher'] == 'Unknown Publisher':
                            metadata['publisher'] = line.split('=', 1)[1].strip()
                        elif line.startswith('Version='):
                            metadata['version'] = line.split('=', 1)[1].strip()
                        elif line.startswith('Icon='):
                            icon_name = line.split('=', 1)[1].strip()
                            # Look for this icon in the tar
                            for m in members:
                                if icon_name in m and any(m.lower().endswith(ext) for ext in ['.png', '.svg', '.ico', '.jpg', '.jpeg']):
                                    icon_file = m
                                    break
                except Exception as e:
                    print(f"Error parsing .desktop file: {e}")
            
            # If no name from .desktop, try to extract from filename
            if metadata['name'] == 'Unknown Application':
                base_name = os.path.basename(tar_path)
                if base_name.endswith('.tar.gz'):
                    app_name = base_name[:-7]
                elif base_name.endswith('.tgz'):
                    app_name = base_name[:-4]
                else:
                    app_name = base_name
                
                # Clean up common filename patterns
                # Remove version numbers, arch, and common suffixes
                import re
                app_name = re.sub(r'-\d+(\.\d+)*', '', app_name)  # Remove version numbers
                app_name = re.sub(r'-(x64|x86|amd64|i386|arm64)', '', app_name, flags=re.IGNORECASE)
                app_name = re.sub(r'-(stable|beta|alpha|dev)', '', app_name, flags=re.IGNORECASE)
                app_name = re.sub(r'-linux.*', '', app_name, flags=re.IGNORECASE)
                
                metadata['name'] = app_name.replace('-', ' ').replace('_', ' ').title()
            
            # Second pass: find icon files
            if not icon_file:
                # Prioritize files with 'icon' or 'logo' in name
                icon_candidates = []
                for member in members:
                    member_lower = member.lower()
                    if any(member_lower.endswith(ext) for ext in ['.png', '.svg', '.ico', '.jpg', '.jpeg']):
                        # Prioritize by filename
                        if 'icon' in member_lower or 'logo' in member_lower:
                            icon_candidates.insert(0, member)
                        else:
                            icon_candidates.append(member)
                
                if icon_candidates:
                    icon_file = icon_candidates[0]
            
            # Extract icon to temp file
            if icon_file:
                try:
                    icon_data = tar.extractfile(icon_file).read()
                    temp_icon = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(icon_file)[1])
                    temp_icon.write(icon_data)
                    temp_icon.close()
                    metadata['icon_path'] = temp_icon.name
                except Exception as e:
                    print(f"Error extracting icon: {e}")
            
            # Look for README, LICENSE, or metadata files for publisher info
            if metadata['publisher'] == 'Unknown Publisher':
                for member in members:
                    if 'readme' in member.lower() or 'license' in member.lower() or 'package.json' in member.lower():
                        try:
                            content = tar.extractfile(member).read().decode('utf-8', errors='ignore')
                            lines = content.split('\n')[:20]  # First 20 lines
                            for line in lines:
                                if 'author' in line.lower() or 'publisher' in line.lower() or 'maintainer' in line.lower():
                                    # Simple extraction
                                    if ':' in line:
                                        publisher_text = line.split(':', 1)[1].strip()
                                        # Clean up common formats
                                        publisher_text = publisher_text.replace('"', '').replace("'", '').strip()
                                        if publisher_text and len(publisher_text) < 100:
                                            metadata['publisher'] = publisher_text[:50]
                                            break
                        except:
                            pass
                        if metadata['publisher'] != 'Unknown Publisher':
                            break
    
    except Exception as e:
        print(f"Error extracting metadata: {e}")
    
    return metadata

# ----------------------------
# Normalize file argument
# ----------------------------
installer_file = None
if len(sys.argv) > 1:
    arg = sys.argv[1]
    if arg.startswith("file://"):
        arg = arg.replace("file://", "")
    arg = os.path.abspath(os.path.expanduser(arg))
    if os.path.exists(arg):
        installer_file = arg

# Extract metadata
app_metadata = extract_app_metadata(installer_file)

# ----------------------------
# Qt App
# ----------------------------
app = QApplication(sys.argv)
app.setApplicationName("Arcade Installer")

class InstallerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.installer_file = installer_file
        self.install_worker = None
        self.executable_path = None
        self.initUI()
    
    def initUI(self):
        self.setWindowTitle("Arcade Installer")
        self.setWindowIcon(QIcon(ICON_PATH))
        self.setFixedSize(500, 450)
        
        # Apply macOS dark theme
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QMessageBox {
                background-color: #2d2d2d;
            }
            QMessageBox QLabel {
                color: #ffffff;
            }
        """)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(20)
        
        # App Icon
        icon_label = QLabel()
        icon_pixmap = QPixmap(app_metadata['icon_path'])
        if not icon_pixmap.isNull():
            icon_pixmap = icon_pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            # Fallback to default
            icon_pixmap = QPixmap(DEFAULT_APP_ICON).scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        icon_label.setPixmap(icon_pixmap)
        icon_label.setAlignment(Qt.AlignCenter)
        
        # App Name
        app_name_label = QLabel(app_metadata['name'])
        app_name_label.setAlignment(Qt.AlignCenter)
        app_name_label.setStyleSheet("""
            font-size: 24px;
            font-weight: 600;
            color: #ffffff;
            margin-top: 10px;
        """)
        app_name_label.setWordWrap(True)
        
        # Publisher
        publisher_label = QLabel(f"by {app_metadata['publisher']}")
        publisher_label.setAlignment(Qt.AlignCenter)
        publisher_label.setStyleSheet("""
            font-size: 14px;
            color: #8e8e93;
            margin-bottom: 5px;
        """)
        
        # Version (if available)
        version_label = None
        if app_metadata['version'] != 'Unknown':
            version_label = QLabel(f"Version {app_metadata['version']}")
            version_label.setAlignment(Qt.AlignCenter)
            version_label.setStyleSheet("""
                font-size: 12px;
                color: #8e8e93;
            """)
        
        # Progress bar (initially hidden)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #3a3a3c;
                border-radius: 4px;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #0a84ff;
                border-radius: 4px;
            }
        """)
        self.progress_bar.hide()
        
        # Status label (initially hidden)
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("""
            font-size: 12px;
            color: #8e8e93;
        """)
        self.status_label.hide()
        
        # Install Button
        self.install_button = QPushButton("Install")
        self.install_button.setFixedHeight(44)
        self.install_button.setCursor(Qt.PointingHandCursor)
        self.install_button.setStyleSheet("""
            QPushButton {
                background-color: #0a84ff;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 500;
                padding: 10px 30px;
            }
            QPushButton:hover {
                background-color: #0f8fff;
            }
            QPushButton:pressed {
                background-color: #0670dd;
            }
            QPushButton:disabled {
                background-color: #3a3a3c;
                color: #8e8e93;
            }
        """)
        self.install_button.clicked.connect(self.install_app)
        
        # Cancel Button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setFixedHeight(44)
        self.cancel_button.setCursor(Qt.PointingHandCursor)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #0a84ff;
                border: 1px solid #48484a;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 500;
                padding: 10px 30px;
            }
            QPushButton:hover {
                background-color: #2d2d2d;
                border-color: #5e5e60;
            }
            QPushButton:pressed {
                background-color: #3a3a3c;
            }
        """)
        self.cancel_button.clicked.connect(self.close)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.install_button)
        
        # Add widgets to main layout
        main_layout.addStretch()
        main_layout.addWidget(icon_label)
        main_layout.addWidget(app_name_label)
        main_layout.addWidget(publisher_label)
        if version_label:
            main_layout.addWidget(version_label)
        main_layout.addSpacing(20)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.status_label)
        main_layout.addStretch()
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    def install_app(self):
        """Handle installation"""
        if not self.installer_file:
            self.show_message("No File", "No installation file provided.", QMessageBox.Warning)
            return
        
        # Confirm installation
        reply = QMessageBox.question(
            self,
            "Install Application",
            f"Install {app_metadata['name']}?\n\nThis will extract and install the application to:\n{INSTALL_DIR}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Disable buttons and show progress
            self.install_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.progress_bar.show()
            self.status_label.show()
            self.progress_bar.setValue(0)
            
            # Start installation in background thread
            self.install_worker = InstallWorker(self.installer_file, app_metadata['name'])
            self.install_worker.progress.connect(self.update_progress)
            self.install_worker.status.connect(self.update_status)
            self.install_worker.finished.connect(self.installation_finished)
            self.install_worker.start()
    
    def update_progress(self, value):
        """Update progress bar"""
        self.progress_bar.setValue(value)
    
    def update_status(self, message):
        """Update status label"""
        self.status_label.setText(message)
    
    def installation_finished(self, success, message, executable_path):
        """Handle installation completion"""
        self.executable_path = executable_path
        
        if success:
            # Hide progress indicators
            self.progress_bar.hide()
            self.status_label.hide()
            
            # Change Install button to Launch button
            if self.executable_path:
                self.install_button.setText("Launch")
                self.install_button.setEnabled(True)
                self.install_button.clicked.disconnect()
                self.install_button.clicked.connect(self.launch_app)
                self.cancel_button.setText("Close")
                self.cancel_button.setEnabled(True)
                
                # Show success message
                self.status_label.setText("Installation successful! Click Launch to start the application.")
                self.status_label.setStyleSheet("""
                    font-size: 13px;
                    color: #30d158;
                    font-weight: 500;
                """)
                self.status_label.show()
            else:
                self.show_message("Success", message + "\n\nNo executable found to launch.", QMessageBox.Information)
                QTimer.singleShot(500, self.close)
        else:
            self.show_message("Error", message, QMessageBox.Critical)
            self.install_button.setEnabled(True)
            self.cancel_button.setEnabled(True)
            self.progress_bar.hide()
            self.status_label.hide()
    
    def launch_app(self):
        """Launch the installed application"""
        if not self.executable_path or not os.path.exists(self.executable_path):
            self.show_message("Error", "Executable not found. The application may not have been installed correctly.", QMessageBox.Warning)
            return
        
        try:
            # Launch the application in the background
            subprocess.Popen([self.executable_path], 
                           start_new_session=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            
            # Close the installer
            QTimer.singleShot(500, self.close)
            
        except Exception as e:
            self.show_message("Launch Error", f"Failed to launch application:\n{str(e)}", QMessageBox.Critical)
    
    def show_message(self, title, message, icon_type):
        """Show a styled message box"""
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setIcon(icon_type)
        
        # Apply dark theme to message box
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #2d2d2d;
            }
            QMessageBox QLabel {
                color: #ffffff;
            }
            QPushButton {
                background-color: #0a84ff;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #0f8fff;
            }
        """)
        msg.exec_()

# ----------------------------
# Create and show window
# ----------------------------
window = InstallerWindow()
window.show()
window.raise_()
window.activateWindow()
QTimer.singleShot(100, window.activateWindow)

sys.exit(app.exec_())