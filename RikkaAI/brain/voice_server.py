"""
RikkaAI - 本地 GPT-SoVITS api_v2.py 常驻服务管理器。

负责六花语音推理服务（端口 9880）的启动/停止/就绪判定，供首页按钮与 voice.py 共用。

生命周期: stopped → starting → ready ⇄ stopping → stopped；异常 → error。
- api_v2.py 在模块 import 时即加载模型（30-60s），加载完才 uvicorn 绑端口，
  因此「端口可达」≈「模型就绪」，直接用 HTTP 探针判就绪。
- 子进程 cwd 必须是整合包根目录：tts_infer.yaml 里的权重路径是相对路径。
- 启动/停止/轮询都在 GUI 线程（QTimer），stdout 由 daemon 线程常驻读取防管道阻塞。
- Windows 下用 taskkill /PID <pid> /T /F 杀进程树（Popen.kill 只杀直接子进程）。
"""
import logging
import os
import subprocess
import threading
import time
from collections import deque

import requests

import config as cfg
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

logger = logging.getLogger("VoiceServer")

# 状态常量（字符串，直接进 JSON 给 JS）
STOPPED, STARTING, READY, STOPPING, ERROR = "stopped", "starting", "ready", "stopping", "error"


class VoiceServerSignals(QObject):
    """状态变更信号。payload: {"state","detail","pid","elapsed"}。"""
    status_changed = pyqtSignal(object)


class VoiceServerManager(QObject):
    """GPT-SoVITS 本地服务的进程生命周期管理器（单例）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = VoiceServerSignals()
        self._state = STOPPED
        self._proc = None
        self._external_pid = None                 # 接管外部已运行服务时的监听 PID
        self._started_at = None
        self._detail = ""                        # 最近一次状态描述
        self._tail = deque(maxlen=200)          # stdout 尾部（线程安全）
        self._tail_lock = threading.Lock()
        self._timer = QTimer(self)               # 就绪轮询（GUI 线程）
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll_ready)
        self._api_base = (getattr(cfg, "GPT_SOVITS_URL", "") or "http://127.0.0.1:9880").rstrip("/")

    # ── 公共 API ─────────────────────────────────────────────

    def start(self):
        """启动服务；已在跑则幂等接管。失败置 ERROR。"""
        if self._state in (STARTING, READY, STOPPING):
            return
        # 服务可能已由外部手动启动（api_v2.py 独立跑着）→ 直接接管
        if self._is_up():
            self._external_pid = self._discover_pid()
            self._set_state(READY, "服务已在运行")
            return
        py = self._python()
        if not os.path.exists(py):
            self._set_state(ERROR, "GPT-SoVITS 路径不存在，请检查 config.GPT_SOVITS_ROOT")
            return
        self._spawn()
        self._started_at = time.time()
        self._set_state(STARTING, "正在加载模型…")
        self._timer.start()

    def stop(self):
        """停止服务；已是 stopped/stopping 则 no-op。"""
        if self._state in (STOPPED, STOPPING):
            return
        self._set_state(STOPPING, "正在停止…")
        self._kill_tree()
        self._timer.stop()
        self._set_state(STOPPED, "已停止")

    def is_running(self):
        return self._state in (STARTING, READY)

    def status(self):
        """JSON 安全快照，可直接 json.dumps 发给前端。"""
        detail = self._detail or self._last_line()
        elapsed = (time.time() - self._started_at) if self._started_at else 0.0
        pid = self._proc.pid if (self._proc and self._proc.poll() is None) else self._external_pid
        return {
            "state": self._state,
            "detail": detail,
            "pid": pid,
            "elapsed": round(elapsed, 1),
        }

    def ensure_adopt_external(self):
        """初始状态校正：服务可能在外部已运行，探到端口就置 ready。"""
        if self._state == STOPPED and self._is_up():
            self._external_pid = self._discover_pid()
            self._set_state(READY, "服务已在运行")

    # ── 内部 ─────────────────────────────────────────────────

    def _python(self):
        return os.path.join(cfg.GPT_SOVITS_ROOT, "runtime", "python.exe")

    def _build_command(self):
        return [
            self._python(), "api_v2.py",
            "-a", str(getattr(cfg, "GPT_SOVITS_HOST", "127.0.0.1")),
            "-p", str(getattr(cfg, "GPT_SOVITS_PORT", 9880)),
            "-c", "GPT_SoVITS/configs/tts_infer.yaml",
        ]

    def _spawn(self):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # 不弹控制台黑窗
        self._external_pid = None
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")   # api_v2 默认按 GBK 打印，遇「・」等字符会崩
        # api_v2 用 ffmpeg.exe（整合包根目录）解码参考音频，必须把它加进 PATH，否则 /tts 报
        # [WinError 2] 系统找不到指定的文件（subprocess 找不到 ffmpeg）。
        env["PATH"] = cfg.GPT_SOVITS_ROOT + os.pathsep + env.get("PATH", "")
        self._proc = subprocess.Popen(
            self._build_command(),
            cwd=cfg.GPT_SOVITS_ROOT,          # 关键：tts_infer.yaml 权重是相对路径
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env=env, creationflags=flags,
        )
        threading.Thread(target=self._read_stdout, daemon=True,
                         name="VoiceServerStdout").start()

    def _read_stdout(self):
        """daemon 线程常驻读 stdout，避免管道写满阻塞子进程。绝不 communicate()。"""
        proc = self._proc
        if proc is None:
            return
        try:
            for line in proc.stdout:
                with self._tail_lock:
                    self._tail.append(line.rstrip())
        except Exception:
            pass

    def _last_line(self):
        with self._tail_lock:
            return self._tail[-1] if self._tail else ""

    def _is_up(self):
        """端口可达即就绪：任何状态码（404/400 都算）都说明 uvicorn 已绑定。"""
        try:
            requests.get(self._api_base + "/", timeout=2)
            return True
        except requests.RequestException:
            return False

    def _poll_ready(self):
        if self._state != STARTING:
            return
        # 进程提前退出 → error
        if self._proc is not None and self._proc.poll() is not None:
            self._timer.stop()
            self._set_state(ERROR, self._last_line() or "进程异常退出")
            return
        if self._is_up():
            self._timer.stop()
            self._set_state(READY, "服务就绪")
            return
        timeout = float(getattr(cfg, "GPT_SOVITS_START_TIMEOUT", 90))
        if self._started_at and time.time() - self._started_at > timeout:
            self._timer.stop()
            self._kill_tree()
            self._set_state(ERROR, f"启动超时（{int(timeout)}s），已自动停止")

    def _discover_pid(self):
        """在服务端口上发现监听 PID（接管外部已运行的服务时用）。Windows netstat。"""
        try:
            out = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=5,
            ).stdout or ""
            port = str(getattr(cfg, "GPT_SOVITS_PORT", 9880))
            for line in out.splitlines():
                parts = line.split()
                if (len(parts) >= 5 and parts[0] == "TCP"
                        and parts[1].endswith(":" + port) and parts[3] == "LISTENING"):
                    return int(parts[4])
        except Exception:
            pass
        return None

    def _effective_pid(self):
        if self._proc is not None and self._proc.poll() is None:
            return self._proc.pid
        return self._external_pid

    def _kill_tree(self):
        pid = self._effective_pid()
        proc = self._proc
        if pid:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)   # 短等回收，避免 closeEvent 阻塞
            except Exception:
                pass
        self._proc = None
        self._external_pid = None

    def _set_state(self, state, detail=""):
        self._state = state
        self._detail = detail
        self.signals.status_changed.emit(self.status())


# 模块级单例（与 brain/voice.py 的 get_engine() 同款）
_manager = None


def get_voice_server():
    global _manager
    if _manager is None:
        _manager = VoiceServerManager()
    return _manager
