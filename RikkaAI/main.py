"""
RikkaAI entry point.
"""
import logging
import os
import subprocess
import sys


def _bootstrap_project_python():
    
    """Relaunch with the isolated project environment when it is available."""
    root = os.path.dirname(os.path.abspath(__file__))
    project_python = os.path.join(root, ".venv", "Scripts", "python.exe")
    if not os.path.isfile(project_python):
        return
    if os.path.normcase(os.path.abspath(sys.executable)) == os.path.normcase(project_python):
        return
    if os.environ.get("RIKKAAI_BOOTSTRAPPED") == "1":
        return

    env = os.environ.copy()
    env["RIKKAAI_BOOTSTRAPPED"] = "1"
    for name in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        env.pop(name, None)
    command = [project_python, os.path.abspath(__file__), *sys.argv[1:]]
    raise SystemExit(subprocess.call(command, cwd=root, env=env))


_bootstrap_project_python()

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QCursor, QPalette
from PyQt5.QtWidgets import QApplication

# Import WebEngine before QApplication is created; Qt 5 initializes Chromium here.
try:
    from PyQt5 import QtWebEngineWidgets  # noqa: F401
except ImportError:
    QtWebEngineWidgets = None


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.makedirs(os.path.join(os.path.dirname(__file__), "memory_data"), exist_ok=True)


def setup_high_dpi():
    """Enable high-DPI support when the Qt build supports it."""
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


def center_window_on_active_screen(window, app):
    """Place the initial window in the usable center of the active display."""
    screen = app.screenAt(QCursor.pos()) if hasattr(app, "screenAt") else None
    screen = screen or app.primaryScreen()
    if screen is None:
        return
    available = screen.availableGeometry()
    frame_size = window.frameGeometry().size()
    x = available.left() + max(0, (available.width() - frame_size.width()) // 2)
    y = available.top() + max(0, (available.height() - frame_size.height()) // 2)
    window.move(x, y)


def main():
    setup_high_dpi()

    # 让 qq_bridge / voice 等模块的 logger 真正打印到控制台（QQ 链路诊断靠它）
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("RikkaAI")
    app.setApplicationDisplayName("RikkaAI - 六花AI")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(252, 247, 255))
    palette.setColor(QPalette.WindowText, QColor(63, 52, 92))
    palette.setColor(QPalette.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.AlternateBase, QColor(250, 244, 255))
    palette.setColor(QPalette.Text, QColor(63, 52, 92))
    palette.setColor(QPalette.Button, QColor(255, 255, 255))
    palette.setColor(QPalette.ButtonText, QColor(87, 66, 133))
    palette.setColor(QPalette.Highlight, QColor(178, 150, 255))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    from main_window import MainWindow

    window = MainWindow()
    center_window_on_active_screen(window, app)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
