#!/usr/bin/env python3
import sys
import os
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QTimer

# ----------------------------
# Resolve paths
# ----------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_PATH = os.path.join(BASE_DIR, "assets", "arcade-installer.png")

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

# ----------------------------
# Qt App
# ----------------------------
app = QApplication(sys.argv)
app.setApplicationName("Arcade Installer")

window = QWidget()
window.setWindowTitle("Arcade Installer")
window.setWindowIcon(QIcon(ICON_PATH))
window.setFixedSize(500, 300)

title = QLabel("Arcade Installer")
title.setAlignment(Qt.AlignCenter)
title.setStyleSheet("font-size:22px;font-weight:600;")

if installer_file:
    subtitle = QLabel(
        f"Ready to install:\n<b>{os.path.basename(installer_file)}</b>"
    )
else:
    subtitle = QLabel("Install Linux software without the terminal")

subtitle.setAlignment(Qt.AlignCenter)
subtitle.setWordWrap(True)
subtitle.setStyleSheet("color:#9e9e9e;font-size:13px;")

layout = QVBoxLayout(window)
layout.addStretch()
layout.addWidget(title)
layout.addWidget(subtitle)
layout.addStretch()

window.setLayout(layout)

# ----------------------------
# FORCE SHOW (WM safe)
# ----------------------------
window.show()
window.raise_()
window.activateWindow()
QTimer.singleShot(100, window.activateWindow)

sys.exit(app.exec_())
