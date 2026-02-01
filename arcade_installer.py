#!/usr/bin/env python3
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt

app = QApplication(sys.argv)

window = QWidget()
window.setWindowTitle("Arcade Installer")
window.setWindowIcon(QIcon("arcade-installer.png"))
window.setFixedSize(480, 300)

title = QLabel("Arcade Installer")
title.setAlignment(Qt.AlignCenter)
title.setStyleSheet("font-size: 20px; font-weight: bold;")

subtitle = QLabel("Install apps without using the terminal")
subtitle.setAlignment(Qt.AlignCenter)
subtitle.setStyleSheet("color: #aaaaaa;")

layout = QVBoxLayout()
layout.addStretch()
layout.addWidget(title)
layout.addWidget(subtitle)
layout.addStretch()

window.setLayout(layout)
window.show()

sys.exit(app.exec_())gi
