#!/usr/bin/env python3
import sys
from PySide6.QtWidgets import QApplication
import pyqtgraph as pg

from ui.main_window import MainWindow

pg.setConfigOption('background', '#252526')
pg.setConfigOption('foreground', '#CCCCCC')
pg.setConfigOption('antialias', True)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
