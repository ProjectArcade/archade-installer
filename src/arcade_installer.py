#!/usr/bin/env python3
import sys
import os
import tarfile
import tempfile
import shutil
import subprocess
import platform
import re
import urllib.request
import urllib.parse
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                             QPushButton, QHBoxLayout, QMessageBox, QProgressBar)
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal

# ----------------------------
# Detect OS and Architecture
# ----------------------------
IS_LINUX = platform.system() == 'Linux'
IS_DEBIAN = os.path.exists('/etc/debian_version')
IS_REDHAT = os.path.exists('/etc/redhat-release') or os.path.exists('/etc/fedora-release')

# Detect architecture
ARCH = platform.machine().lower()
if ARCH in ['x86_64', 'amd64']:
    ARCH_DEB = 'amd64'
    ARCH_RPM = 'x86_64'
elif ARCH in ['i386', 'i686']:
    ARCH_DEB = 'i386'
    ARCH_RPM = 'i686'
elif ARCH in ['aarch64', 'arm64']:
    ARCH_DEB = 'arm64'
    ARCH_RPM = 'aarch64'
elif ARCH.startswith('arm'):
    ARCH_DEB = 'armhf'
    ARCH_RPM = 'armv7hl'
else:
    ARCH_DEB = 'all'
    ARCH_RPM = 'noarch'

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
# Download Worker Thread
# ----------------------------
class DownloadWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(bool, str)  # success, local_path
    
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.local_path = None
    
    def run(self):
        try:
            self.status.emit("Downloading file...")
            
            # Create temp file
            parsed_url = urllib.parse.urlparse(self.url)
            filename = os.path.basename(parsed_url.path)
            if not filename:
                filename = "downloaded_package"
            
            temp_dir = tempfile.mkdtemp()
            self.local_path = os.path.join(temp_dir, filename)
            
            # Download with progress
            def reporthook(blocknum, blocksize, totalsize):
                if totalsize > 0:
                    percent = min(int(blocknum * blocksize * 100 / totalsize), 100)
                    self.progress.emit(percent)
                    downloaded = blocknum * blocksize / (1024 * 1024)
                    total = totalsize / (1024 * 1024)
                    self.status.emit(f"Downloading: {downloaded:.1f}MB / {total:.1f}MB")
            
            urllib.request.urlretrieve(self.url, self.local_path, reporthook)
            
            self.status.emit("Download complete!")
            self.finished.emit(True, self.local_path)
            
        except Exception as e:
            self.finished.emit(False, f"Download failed: {str(e)}")

# ----------------------------
# Installation Worker Thread
# ----------------------------
class InstallWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str)  # success, message, executable_path
    
    def __init__(self, file_path, app_name, convert_format=None):
        super().__init__()
        self.file_path = file_path
        self.app_name = app_name
        self.convert_format = convert_format
        self.executable_path = None
    
    def run(self):
        try:
            # Detect file type
            file_type = self.detect_file_type(self.file_path)
            
            # Convert if needed
            if self.convert_format and self.convert_format != file_type:
                self.status.emit(f"Converting {file_type} to {self.convert_format}...")
                self.progress.emit(10)
                converted_path = self.convert_package(self.file_path, file_type, self.convert_format)
                if converted_path:
                    self.file_path = converted_path
                    file_type = self.convert_format
                else:
                    # If conversion fails, try to install original
                    self.status.emit("Conversion not available, installing original format...")
            
            # Install based on type
            if file_type in ['tar.gz', 'tgz', 'tar.bz2', 'tar.xz']:
                self.install_tar()
            elif file_type == 'deb':
                self.install_deb()
            elif file_type == 'rpm':
                self.install_rpm()
            else:
                self.finished.emit(False, f"Unsupported file type: {file_type}", "")
                
        except Exception as e:
            self.finished.emit(False, f"Installation failed: {str(e)}", "")
    
    def detect_file_type(self, file_path):
        """Detect file type from extension"""
        file_lower = file_path.lower()
        
        if file_lower.endswith('.deb'):
            return 'deb'
        elif file_lower.endswith('.rpm'):
            return 'rpm'
        elif file_lower.endswith('.tar.gz') or file_lower.endswith('.tgz'):
            return 'tar.gz'
        elif file_lower.endswith('.tar.bz2'):
            return 'tar.bz2'
        elif file_lower.endswith('.tar.xz'):
            return 'tar.xz'
        else:
            return None
    
    def convert_package(self, source_path, from_format, to_format):
        """Convert package from one format to another"""
        try:
            temp_dir = tempfile.mkdtemp()
            
            # Convert DEB to TAR.GZ
            if from_format == 'deb' and to_format == 'tar.gz':
                return self.deb_to_tar(source_path, temp_dir)
            
            # Convert RPM to TAR.GZ
            elif from_format == 'rpm' and to_format == 'tar.gz':
                return self.rpm_to_tar(source_path, temp_dir)
            
            # Convert TAR.GZ to DEB
            elif from_format in ['tar.gz', 'tgz'] and to_format == 'deb':
                return self.tar_to_deb(source_path, temp_dir)
            
            # Convert TAR.GZ to RPM
            elif from_format in ['tar.gz', 'tgz'] and to_format == 'rpm':
                return self.tar_to_rpm(source_path, temp_dir)
            
            return None
            
        except Exception as e:
            print(f"Conversion error: {e}")
            return None
    
    def deb_to_tar(self, deb_path, temp_dir):
        """Convert DEB package to TAR.GZ"""
        try:
            extract_dir = os.path.join(temp_dir, 'deb_extracted')
            os.makedirs(extract_dir)
            
            # Try method 1: dpkg-deb (if available)
            if shutil.which('dpkg-deb'):
                try:
                    subprocess.run(['dpkg-deb', '-x', deb_path, extract_dir], 
                                 check=True, stderr=subprocess.DEVNULL)
                except:
                    pass
            
            # Try method 2: ar + tar extraction (works without dpkg)
            if not os.listdir(extract_dir):
                try:
                    # DEB files are ar archives containing data.tar.*
                    # Extract using ar if available
                    if shutil.which('ar'):
                        # Extract the DEB archive
                        temp_ar_dir = os.path.join(temp_dir, 'ar_extract')
                        os.makedirs(temp_ar_dir)
                        subprocess.run(['ar', 'x', deb_path], 
                                     cwd=temp_ar_dir, check=True, stderr=subprocess.DEVNULL)
                        
                        # Find and extract data.tar.*
                        for f in os.listdir(temp_ar_dir):
                            if f.startswith('data.tar'):
                                data_tar = os.path.join(temp_ar_dir, f)
                                with tarfile.open(data_tar, 'r:*') as tar:
                                    tar.extractall(extract_dir)
                                break
                except Exception as e:
                    print(f"ar extraction failed: {e}")
            
            # Try method 3: Direct tar extraction (some DEBs)
            if not os.listdir(extract_dir):
                try:
                    with tarfile.open(deb_path, 'r:*') as tar:
                        tar.extractall(extract_dir)
                except:
                    pass
            
            # Check if extraction succeeded
            if not os.listdir(extract_dir):
                return None
            
            # Create tar.gz from extracted contents
            tar_path = os.path.join(temp_dir, 'converted.tar.gz')
            with tarfile.open(tar_path, 'w:gz') as tar:
                for item in os.listdir(extract_dir):
                    tar.add(os.path.join(extract_dir, item), arcname=item)
            
            return tar_path
        except Exception as e:
            print(f"DEB conversion error: {e}")
            return None
    
    def rpm_to_tar(self, rpm_path, temp_dir):
        """Convert RPM package to TAR.GZ"""
        try:
            extract_dir = os.path.join(temp_dir, 'rpm_extracted')
            os.makedirs(extract_dir)
            
            # Try method 1: rpm2cpio + cpio (most reliable)
            if shutil.which('rpm2cpio') and shutil.which('cpio'):
                try:
                    # Use rpm2cpio to convert RPM to CPIO format
                    rpm2cpio_proc = subprocess.Popen(
                        ['rpm2cpio', rpm_path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL
                    )
                    
                    # Extract with cpio
                    subprocess.run(
                        ['cpio', '-idm', '--quiet'],
                        stdin=rpm2cpio_proc.stdout,
                        cwd=extract_dir,
                        stderr=subprocess.DEVNULL
                    )
                    rpm2cpio_proc.wait()
                except Exception as e:
                    print(f"rpm2cpio method failed: {e}")
            
            # Try method 2: Use rpm command directly (if available)
            if not os.listdir(extract_dir) and shutil.which('rpm'):
                try:
                    # Some systems allow extracting with rpm
                    subprocess.run(
                        ['rpm', '-qpl', rpm_path],
                        capture_output=True,
                        check=True
                    )
                    # If that worked, try to extract
                    subprocess.run(
                        ['rpm2cpio', rpm_path],
                        stdout=subprocess.PIPE,
                        check=False
                    )
                except:
                    pass
            
            # Try method 3: Python rpm library (if available)
            if not os.listdir(extract_dir):
                try:
                    import rpm
                    ts = rpm.TransactionSet()
                    with open(rpm_path, 'rb') as f:
                        hdr = ts.hdrFromFdno(f)
                    # This method is complex, skip for now
                except:
                    pass
            
            # Check if extraction succeeded
            if not os.listdir(extract_dir):
                return None
            
            # Create tar.gz from extracted contents
            tar_path = os.path.join(temp_dir, 'converted.tar.gz')
            with tarfile.open(tar_path, 'w:gz') as tar:
                for item in os.listdir(extract_dir):
                    tar.add(os.path.join(extract_dir, item), arcname=item)
            
            return tar_path
        except Exception as e:
            print(f"RPM conversion error: {e}")
            return None
    
    def tar_to_deb(self, tar_path, temp_dir):
        """Convert TAR.GZ to DEB package"""
        if not shutil.which('dpkg-deb'):
            return None
        
        try:
            # Extract tar
            extract_dir = os.path.join(temp_dir, 'tar_extracted')
            os.makedirs(extract_dir)
            
            with tarfile.open(tar_path, 'r:*') as tar:
                tar.extractall(extract_dir)
            
            # Create DEB structure
            deb_dir = os.path.join(temp_dir, f'{self.app_name}_1.0_{ARCH_DEB}')
            os.makedirs(os.path.join(deb_dir, 'DEBIAN'))
            
            # Create control file
            control_content = f"""Package: {self.app_name.lower().replace(' ', '-')}
Version: 1.0
Section: misc
Priority: optional
Architecture: {ARCH_DEB}
Maintainer: Arcade Installer <installer@arcade.local>
Description: {self.app_name}
 Installed via Arcade Installer
"""
            with open(os.path.join(deb_dir, 'DEBIAN', 'control'), 'w') as f:
                f.write(control_content)
            
            # Copy files
            data_dir = os.path.join(deb_dir, 'opt', self.app_name.lower().replace(' ', '-'))
            shutil.copytree(extract_dir, data_dir)
            
            # Build DEB
            deb_path = os.path.join(temp_dir, f'{self.app_name.lower().replace(" ", "-")}_1.0_{ARCH_DEB}.deb')
            subprocess.run(['dpkg-deb', '--build', deb_dir, deb_path], 
                         check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            return deb_path
        except:
            return None
    
    def tar_to_rpm(self, tar_path, temp_dir):
        """Convert TAR.GZ to RPM package"""
        if not shutil.which('rpmbuild'):
            return None
        
        try:
            # This is a simplified conversion - full RPM creation is complex
            # For now, we'll just install as tar.gz
            return None
        except:
            return None
    
    def install_tar(self):
        """Install from tar.gz/tgz archive"""
        os.makedirs(INSTALL_DIR, exist_ok=True)
        os.makedirs(BIN_DIR, exist_ok=True)
        os.makedirs(DESKTOP_DIR, exist_ok=True)
        
        self.status.emit("Preparing installation...")
        self.progress.emit(20)
        
        # Create app-specific directory
        app_dir = os.path.join(INSTALL_DIR, self.app_name.replace(' ', '-').lower())
        if os.path.exists(app_dir):
            shutil.rmtree(app_dir)
        os.makedirs(app_dir)
        
        self.status.emit("Extracting files...")
        self.progress.emit(40)
        
        # Extract tar archive
        with tarfile.open(self.file_path, 'r:*') as tar:
            tar.extractall(app_dir)
        
        self.progress.emit(60)
        self.status.emit("Setting up application...")
        
        # Find executable or main script
        executable = None
        for root, dirs, files in os.walk(app_dir):
            for file in files:
                file_path = os.path.join(root, file)
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
        
        # Create symlink in bin directory
        if executable:
            bin_link = os.path.join(BIN_DIR, self.app_name.replace(' ', '-').lower())
            if os.path.exists(bin_link):
                os.remove(bin_link)
            os.symlink(executable, bin_link)
            self.executable_path = executable
            self.status.emit("Creating shortcuts...")
        
        # Create/update desktop file
        self.create_desktop_file(app_dir, executable)
        
        # Update desktop database
        try:
            subprocess.run(['update-desktop-database', DESKTOP_DIR], 
                         check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
        
        self.progress.emit(100)
        self.status.emit("Installation complete!")
        self.finished.emit(True, f"Successfully installed {self.app_name}", self.executable_path or "")
    
    def install_deb(self):
        """Install DEB package"""
        if not IS_DEBIAN:
            # Try to convert to tar.gz instead
            self.status.emit("Converting DEB to TAR.GZ...")
            self.progress.emit(20)
            
            tar_path = self.deb_to_tar(self.file_path, tempfile.mkdtemp())
            if tar_path:
                self.file_path = tar_path
                self.install_tar()
                return
            else:
                # Show helpful error message
                error_msg = "DEB conversion failed. Please install conversion tools:\n\n"
                error_msg += "sudo apt install dpkg-dev ar\n"
                error_msg += "OR\n"
                error_msg += "Try installing a TAR.GZ version of this application instead."
                self.finished.emit(False, error_msg, "")
                return
        
        self.status.emit("Installing DEB package...")
        self.progress.emit(50)
        
        try:
            # Try GUI sudo first
            if shutil.which('pkexec'):
                result = subprocess.run(['pkexec', 'apt', 'install', '-y', self.file_path],
                                      capture_output=True, text=True)
            else:
                # Use terminal
                terminals = ['x-terminal-emulator', 'gnome-terminal', 'konsole', 'xterm']
                terminal = None
                for term in terminals:
                    if shutil.which(term):
                        terminal = term
                        break
                
                if terminal:
                    cmd = f"sudo apt install -y '{self.file_path}'; read -p 'Press Enter...'"
                    subprocess.run([terminal, '-e', f'bash -c "{cmd}"'])
            
            self.progress.emit(100)
            self.finished.emit(True, f"Successfully installed {self.app_name}", "")
        except Exception as e:
            self.finished.emit(False, f"Installation failed: {str(e)}", "")
    
    def install_rpm(self):
        """Install RPM package"""
        if not IS_REDHAT:
            # Try to convert to tar.gz instead
            self.status.emit("Converting RPM to TAR.GZ...")
            self.progress.emit(20)
            
            tar_path = self.rpm_to_tar(self.file_path, tempfile.mkdtemp())
            if tar_path:
                self.file_path = tar_path
                self.install_tar()
                return
            else:
                # Show helpful error message
                error_msg = "RPM conversion failed. Please install conversion tools:\n\n"
                error_msg += "sudo apt install rpm2cpio cpio\n"
                error_msg += "OR\n"
                error_msg += "Try installing a TAR.GZ version of this application instead."
                self.finished.emit(False, error_msg, "")
                return
        
        self.status.emit("Installing RPM package...")
        self.progress.emit(50)
        
        try:
            # Detect package manager
            if shutil.which('dnf'):
                pkg_manager = 'dnf'
            elif shutil.which('yum'):
                pkg_manager = 'yum'
            else:
                pkg_manager = 'rpm'
            
            # Try GUI sudo first
            if shutil.which('pkexec'):
                result = subprocess.run(['pkexec', pkg_manager, 'install', '-y', self.file_path],
                                      capture_output=True, text=True)
            else:
                # Use terminal
                terminals = ['x-terminal-emulator', 'gnome-terminal', 'konsole', 'xterm']
                terminal = None
                for term in terminals:
                    if shutil.which(term):
                        terminal = term
                        break
                
                if terminal:
                    cmd = f"sudo {pkg_manager} install -y '{self.file_path}'; read -p 'Press Enter...'"
                    subprocess.run([terminal, '-e', f'bash -c "{cmd}"'])
            
            self.progress.emit(100)
            self.finished.emit(True, f"Successfully installed {self.app_name}", "")
        except Exception as e:
            self.finished.emit(False, f"Installation failed: {str(e)}", "")
    
    def create_desktop_file(self, app_dir, executable):
        """Create desktop shortcut"""
        desktop_dest = os.path.join(DESKTOP_DIR, f"{self.app_name.replace(' ', '-').lower()}.desktop")
        
        # Find icon
        icon_path = None
        for root, dirs, files in os.walk(app_dir):
            for file in files:
                if any(file.lower().endswith(ext) for ext in ['.png', '.svg', '.ico']):
                    if 'icon' in file.lower() or 'logo' in file.lower():
                        icon_path = os.path.join(root, file)
                        break
            if icon_path:
                break
        
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
        
        with open(desktop_dest, 'w') as f:
            f.write(desktop_content)
        os.chmod(desktop_dest, 0o755)

# ----------------------------
# Extract metadata
# ----------------------------
def extract_app_metadata(file_path):
    """Extract app metadata"""
    metadata = {
        'name': 'Unknown Application',
        'publisher': 'Unknown Publisher',
        'icon_path': DEFAULT_APP_ICON,
        'version': 'Unknown'
    }
    
    if not file_path or not os.path.exists(file_path):
        return metadata
    
    file_lower = file_path.lower()
    
    # TAR archives
    if file_lower.endswith(('.tar.gz', '.tgz', '.tar.bz2', '.tar.xz')):
        return extract_tar_metadata(file_path)
    # DEB packages
    elif file_lower.endswith('.deb'):
        return extract_deb_metadata(file_path)
    # RPM packages
    elif file_lower.endswith('.rpm'):
        return extract_rpm_metadata(file_path)
    
    return metadata

def extract_tar_metadata(tar_path):
    """Extract metadata from tar archive"""
    metadata = {
        'name': 'Unknown Application',
        'publisher': 'Unknown Publisher',
        'icon_path': DEFAULT_APP_ICON,
        'version': 'Unknown'
    }
    
    try:
        with tarfile.open(tar_path, 'r:*') as tar:
            members = tar.getnames()
            
            # Look for .desktop file
            for member in members:
                if member.lower().endswith('.desktop'):
                    try:
                        desktop_content = tar.extractfile(member).read().decode('utf-8')
                        for line in desktop_content.split('\n'):
                            line = line.strip()
                            if line.startswith('Name='):
                                metadata['name'] = line.split('=', 1)[1].strip()
                            elif line.startswith('Version='):
                                metadata['version'] = line.split('=', 1)[1].strip()
                    except:
                        pass
                    break
            
            # Extract from filename if needed
            if metadata['name'] == 'Unknown Application':
                base_name = os.path.basename(tar_path)
                for ext in ['.tar.gz', '.tgz', '.tar.bz2', '.tar.xz']:
                    if base_name.endswith(ext):
                        base_name = base_name[:-len(ext)]
                        break
                
                base_name = re.sub(r'-\d+(\.\d+)*', '', base_name)
                base_name = re.sub(r'-(x64|amd64|i386|arm)', '', base_name, flags=re.IGNORECASE)
                metadata['name'] = base_name.replace('-', ' ').replace('_', ' ').title()
    except:
        pass
    
    return metadata

def extract_deb_metadata(deb_path):
    """Extract metadata from DEB"""
    metadata = {
        'name': 'Unknown Application',
        'publisher': 'Unknown Publisher',
        'icon_path': DEFAULT_APP_ICON,
        'version': 'Unknown'
    }
    
    if not shutil.which('dpkg'):
        return metadata
    
    try:
        result = subprocess.run(['dpkg', '-I', deb_path], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('Package:'):
                metadata['name'] = line.split(':', 1)[1].strip().replace('-', ' ').title()
            elif line.startswith('Version:'):
                metadata['version'] = line.split(':', 1)[1].strip()
    except:
        pass
    
    return metadata

def extract_rpm_metadata(rpm_path):
    """Extract metadata from RPM"""
    metadata = {
        'name': 'Unknown Application',
        'publisher': 'Unknown Publisher',
        'icon_path': DEFAULT_APP_ICON,
        'version': 'Unknown'
    }
    
    if not shutil.which('rpm'):
        return metadata
    
    try:
        result = subprocess.run(['rpm', '-qip', rpm_path], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('Name'):
                metadata['name'] = line.split(':', 1)[1].strip().replace('-', ' ').title()
            elif line.startswith('Version'):
                metadata['version'] = line.split(':', 1)[1].strip()
    except:
        pass
    
    return metadata

# ----------------------------
# Parse arguments
# ----------------------------
installer_file = None
is_url = False

if len(sys.argv) > 1:
    arg = sys.argv[1]
    
    # Check if it's a URL
    if arg.startswith(('http://', 'https://', 'ftp://')):
        is_url = True
        installer_file = arg
    else:
        # Local file
        if arg.startswith("file://"):
            arg = arg.replace("file://", "")
        arg = os.path.abspath(os.path.expanduser(arg))
        if os.path.exists(arg):
            installer_file = arg

# ----------------------------
# Qt App
# ----------------------------
app = QApplication(sys.argv)
app.setApplicationName("Arcade Installer")

class InstallerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.installer_file = installer_file
        self.is_url = is_url
        self.install_worker = None
        self.download_worker = None
        self.executable_path = None
        self.app_metadata = None
        self.initUI()
        
        # Start download if URL
        if self.is_url:
            QTimer.singleShot(100, self.start_download)
    
    def initUI(self):
        self.setWindowTitle("Arcade Installer")
        self.setWindowIcon(QIcon(ICON_PATH))
        self.setFixedSize(500, 500)
        
        # Apply dark theme
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
        self.icon_label = QLabel()
        if not self.is_url:
            self.app_metadata = extract_app_metadata(installer_file)
            icon_pixmap = QPixmap(self.app_metadata['icon_path'])
            if icon_pixmap.isNull():
                icon_pixmap = QPixmap(DEFAULT_APP_ICON)
        else:
            icon_pixmap = QPixmap(DEFAULT_APP_ICON)
            self.app_metadata = {
                'name': 'Downloading...',
                'publisher': 'Please wait',
                'version': 'Unknown'
            }
        
        icon_pixmap = icon_pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.icon_label.setPixmap(icon_pixmap)
        self.icon_label.setAlignment(Qt.AlignCenter)
        
        # App Name
        self.app_name_label = QLabel(self.app_metadata['name'])
        self.app_name_label.setAlignment(Qt.AlignCenter)
        self.app_name_label.setStyleSheet("""
            font-size: 24px;
            font-weight: 600;
            color: #ffffff;
            margin-top: 10px;
        """)
        self.app_name_label.setWordWrap(True)
        
        # Publisher
        self.publisher_label = QLabel(f"by {self.app_metadata['publisher']}")
        self.publisher_label.setAlignment(Qt.AlignCenter)
        self.publisher_label.setStyleSheet("""
            font-size: 14px;
            color: #8e8e93;
            margin-bottom: 5px;
        """)
        
        # Version
        self.version_label = QLabel(f"Version {self.app_metadata['version']}")
        self.version_label.setAlignment(Qt.AlignCenter)
        self.version_label.setStyleSheet("""
            font-size: 12px;
            color: #8e8e93;
        """)
        if self.app_metadata['version'] == 'Unknown':
            self.version_label.hide()
        
        # Platform info
        platform_text = f"Platform: Linux ({ARCH})"
        if IS_DEBIAN:
            platform_text += " • Debian-based"
        elif IS_REDHAT:
            platform_text += " • RedHat-based"
        
        self.platform_label = QLabel(platform_text)
        self.platform_label.setAlignment(Qt.AlignCenter)
        self.platform_label.setStyleSheet("""
            font-size: 11px;
            color: #636366;
        """)
        
        # Progress bar
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
        
        # Status label
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
        if self.is_url:
            self.install_button.setEnabled(False)
        
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
        main_layout.addWidget(self.icon_label)
        main_layout.addWidget(self.app_name_label)
        main_layout.addWidget(self.publisher_label)
        main_layout.addWidget(self.version_label)
        main_layout.addWidget(self.platform_label)
        main_layout.addSpacing(20)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.status_label)
        main_layout.addStretch()
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    def start_download(self):
        """Start downloading from URL"""
        self.progress_bar.show()
        self.status_label.show()
        self.download_worker = DownloadWorker(self.installer_file)
        self.download_worker.progress.connect(self.update_progress)
        self.download_worker.status.connect(self.update_status)
        self.download_worker.finished.connect(self.download_finished)
        self.download_worker.start()
    
    def download_finished(self, success, result):
        """Handle download completion"""
        if success:
            self.installer_file = result
            self.is_url = False
            self.app_metadata = extract_app_metadata(self.installer_file)
            
            # Update UI
            self.app_name_label.setText(self.app_metadata['name'])
            self.publisher_label.setText(f"by {self.app_metadata['publisher']}")
            self.version_label.setText(f"Version {self.app_metadata['version']}")
            if self.app_metadata['version'] != 'Unknown':
                self.version_label.show()
            
            self.progress_bar.hide()
            self.status_label.hide()
            self.install_button.setEnabled(True)
        else:
            self.show_message("Download Error", result, QMessageBox.Critical)
            self.close()
    
    def install_app(self):
        """Handle installation"""
        if not self.installer_file:
            self.show_message("No File", "No installation file provided.", QMessageBox.Warning)
            return
        
        # Determine target format
        file_type = None
        file_lower = self.installer_file.lower()
        if file_lower.endswith(('.tar.gz', '.tgz', '.tar.bz2', '.tar.xz')):
            file_type = 'tar.gz'
        elif file_lower.endswith('.deb'):
            file_type = 'deb'
        elif file_lower.endswith('.rpm'):
            file_type = 'rpm'
        
        # Auto-convert if needed
        convert_to = None
        if file_type == 'deb' and not IS_DEBIAN:
            convert_to = 'tar.gz'
        elif file_type == 'rpm' and not IS_REDHAT:
            convert_to = 'tar.gz'
        
        # Confirm installation
        install_msg = f"Install {self.app_metadata['name']}?"
        if convert_to:
            install_msg += f"\n\nThe package will be converted from {file_type.upper()} to {convert_to.upper()} for your system."
        install_msg += f"\n\nInstallation directory: {INSTALL_DIR}"
        
        reply = QMessageBox.question(
            self,
            "Install Application",
            install_msg,
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
            
            # Start installation
            self.install_worker = InstallWorker(
                self.installer_file,
                self.app_metadata['name'],
                convert_to
            )
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
            self.progress_bar.hide()
            self.status_label.hide()
            
            if self.executable_path:
                self.install_button.setText("Launch")
                self.install_button.setEnabled(True)
                self.install_button.clicked.disconnect()
                self.install_button.clicked.connect(self.launch_app)
                self.cancel_button.setText("Close")
                self.cancel_button.setEnabled(True)
                
                self.status_label.setText("Installation successful! Click Launch to start.")
                self.status_label.setStyleSheet("""
                    font-size: 13px;
                    color: #30d158;
                    font-weight: 500;
                """)
                self.status_label.show()
            else:
                self.show_message("Success", message, QMessageBox.Information)
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
            self.show_message("Error", "Executable not found.", QMessageBox.Warning)
            return
        
        try:
            subprocess.Popen([self.executable_path], 
                           start_new_session=True,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            QTimer.singleShot(500, self.close)
        except Exception as e:
            self.show_message("Launch Error", f"Failed to launch: {str(e)}", QMessageBox.Critical)
    
    def show_message(self, title, message, icon_type):
        """Show a styled message box"""
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setIcon(icon_type)
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