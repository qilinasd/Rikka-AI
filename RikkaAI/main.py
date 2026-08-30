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

    # 从 conda 激活的终端重启动到 .venv 时，清掉 conda 相关环境变量，
    # 避免子进程再次触发 `conda activate` 造成 CondaError: KeyboardInterrupt。
    env = os.environ.copy()
    env["RIKKAAI_BOOTSTRAPPED"] = "1"
    for name in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        env.pop(name, None)
    # 清理 conda / virtualenv 激活残留，确保用 .venv 的纯净解释器直接启动
    for name in ("CONDA_PREFIX", "CONDA_DEFAULT_ENV", "CONDA_PROMPT_MODIFIER",
                 "CONDA_SHLVL", "VIRTUAL_ENV", "_CE_CONDA", "_CE_M"):
        env.pop(name, None)
    command = [project_python, os.path.abspath(__file__), *sys.argv[1:]]
    try:
        # 用列表参数直接启动，不经过 shell/conda activate，避免终端干扰
        raise SystemExit(subprocess.call(command, cwd=root, env=env))
    except KeyboardInterrupt:
        # 用户手动 Ctrl+C：给一个清晰的退出提示，而不是抛 conda 报错
        sys.exit(130)


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

    # 上线前：全局未捕获异常日志（Qt 主线程 / Python 后台线程），不再静默崩溃
    def _excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            # Ctrl+C / 外部中断信号：正常退出，不算崩溃（否则控制台按 Ctrl+C 会刷两条 ERROR 假崩溃）
            logging.getLogger("RikkaAI.crash").info("收到中断信号（Ctrl+C），正在退出")
            app.quit()
            return
        logging.getLogger("RikkaAI.crash").error(
            "未捕获异常: %s", exc_value, exc_info=(exc_type, exc_value, exc_tb)
        )
        if hasattr(exc_value, "message"):
            logging.getLogger("RikkaAI.crash").error("异常详情: %s", exc_value.message)
    sys.excepthook = _excepthook

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

    # ── 🆕 升级后台服务（做梦 / 自动拉取 / 定时，均受特性开关控制）──
    try:
        from brain.background import start_background_services
        start_background_services()
    except Exception:
        pass

    # ── 🆕 Sleep-time Compute 定时线程（每天按设置页时间自动整合记忆）──
    try:
        from brain.archivist import schedule_sleep_time_compute
        schedule_sleep_time_compute()
    except Exception:
        pass

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
