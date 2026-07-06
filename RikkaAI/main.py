"""
RikkaAI - 入口文件
小鸟游六花 · 邪王真眼 AI 伙伴
"""
import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor

# 确保数据目录存在
os.makedirs(os.path.join(os.path.dirname(__file__), "memory_data"), exist_ok=True)


def setup_high_dpi():
    """高DPI适配"""
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


def main():
    setup_high_dpi()

    app = QApplication(sys.argv)
    app.setApplicationName("RikkaAI")
    app.setApplicationDisplayName("RikkaAI - 六花AI")

    # 设置应用范围的调色板（暗色系）
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(13, 10, 20))
    palette.setColor(QPalette.WindowText, QColor(212, 192, 224))
    palette.setColor(QPalette.Base, QColor(15, 10, 24))
    palette.setColor(QPalette.Text, QColor(212, 192, 224))
    palette.setColor(QPalette.Button, QColor(26, 13, 46))
    palette.setColor(QPalette.ButtonText, QColor(212, 192, 224))
    palette.setColor(QPalette.Highlight, QColor(90, 42, 158))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    # 导入主窗口（延迟导入，确保app已创建）
    from main_window import MainWindow

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
