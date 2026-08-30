"""「获取模型」共享能力：从 OpenAI 兼容接口拉取可用模型列表。

供各模型方案弹窗（对话/识图/生图/Sleep-time Compute）使用：
输入接口地址（Base URL）+ API Key → GET {base}/models → 弹出菜单选择回填。

地址归一化容错（用户可能照抄各种写法）：
    https://api.deepseek.com              → 尝试 /v1/models，再退 /models
    https://api.deepseek.com/v1           → /v1/models
    https://x.example/v1/chat/completions → 剥掉 /chat/completions → /v1/models
"""
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
    QVBoxLayout,
)

from gui import dialog_theme

_TIMEOUT = 10.0
_SESSION = requests.Session()
_SESSION.trust_env = False  # 与 brain/tools.py 一致：忽略系统代理，避免国内接口被代理干扰

_VERSION_TAILS = ("v1", "v2", "v3", "v4", "api", "openai")


def normalize_base_urls(api_base: str) -> list:
    """把用户输入的接口地址归一化成候选的 /models 端点（按优先级排列）。"""
    base = (api_base or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")].rstrip("/")
    if not base or not base.startswith(("http://", "https://")):
        return []
    if base.endswith("/models"):
        return [base]
    if base.rsplit("/", 1)[-1] in _VERSION_TAILS:
        return [base + "/models"]
    return [base + "/v1/models", base + "/models"]


def fetch_model_ids(api_base: str, api_key: str) -> list:
    """阻塞式拉取模型 ID 列表（排序去重）。失败抛 RuntimeError（带可读原因）。"""
    candidates = normalize_base_urls(api_base)
    if not candidates:
        raise RuntimeError("接口地址无效：请填写 http(s):// 开头的 Base URL")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    last_err = "未知错误"
    for url in candidates:
        try:
            resp = _SESSION.get(url, headers=headers, timeout=_TIMEOUT)
        except Exception as exc:
            last_err = f"{url} 不可达：{exc}"
            continue
        if resp.status_code != 200:
            last_err = f"HTTP {resp.status_code}（{url}）：{resp.text[:120]}"
            continue
        try:
            payload = resp.json()
        except ValueError:
            last_err = f"返回的不是 JSON（{url}）"
            continue
        data = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(data, list):
            last_err = f"返回结构里没有模型列表 data（{url}）"
            continue
        ids = sorted({
            str(m.get("id") or m.get("name") or "").strip()
            for m in data if isinstance(m, dict)
        } - {""})
        if ids:
            return ids
        last_err = f"接口返回了空模型列表（{url}）"
    raise RuntimeError(last_err)


class ModelListFetcher(QThread):
    """后台拉取模型列表，避免阻塞界面。finished 后自动 deleteLater。"""

    fetched = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, api_base, api_key, parent=None):
        super().__init__(parent)
        self._api_base = api_base
        self._api_key = api_key

    def run(self):
        try:
            self.fetched.emit(fetch_model_ids(self._api_base, self._api_key))
        except Exception as exc:
            self.failed.emit(str(exc))


# 运行中的拉取线程由模块持有（对话框销毁也不会有线程被 GC 的风险），settled 后释放
_ACTIVE_FETCHERS = set()


def run_model_fetch(api_base, api_key, on_ok, on_fail, on_settle=None):
    """启动后台模型拉取。on_ok(list)/on_fail(str)/on_settle() 通过信号回调到对话框，
    对话框若已销毁会自动断连，无崩溃风险。"""
    fetcher = ModelListFetcher(api_base, api_key)
    _ACTIVE_FETCHERS.add(fetcher)

    def _settle():
        _ACTIVE_FETCHERS.discard(fetcher)
        fetcher.deleteLater()
        if on_settle:
            on_settle()

    fetcher.fetched.connect(on_ok)
    fetcher.failed.connect(on_fail)
    fetcher.finished.connect(_settle)
    fetcher.start()
    return fetcher


class ModelPickerDialog(QDialog):
    """可搜索、可滚动的模型选择弹窗——几百个模型也能优雅展示与筛选。"""

    def __init__(self, models, parent=None):
        super().__init__(parent)
        self.setObjectName("ModelPickerDialog")
        self.setWindowTitle("选择模型")
        self.setModal(True)
        self.resize(440, 520)
        self._models = list(models)
        self._picked = ""

        palette = dialog_theme.colors()
        accent = palette["accent"]
        self.setStyleSheet(
            f"""
            QDialog {{ background:{palette['surface_soft']}; color:{palette['text']}; }}
            QLabel {{ color:{palette['text']}; }}
            QLineEdit {{
                background:{palette['field']}; border:1px solid {palette['border_accent']};
                border-radius:8px; padding:8px 10px; color:{palette['text']}; font-size:12px;
            }}
            QLineEdit:focus {{ border-color:{accent}; background:{palette['surface_strong']}; }}
            QListWidget {{
                background:{palette['field']}; border:1px solid {palette['border_accent']};
                border-radius:8px; color:{palette['text']}; font-size:12px;
                padding:4px; outline:none;
            }}
            QListWidget::item {{ padding:6px 8px; border-radius:6px; }}
            QListWidget::item:hover {{ background:{palette['accent_soft']}; }}
            QListWidget::item:selected {{ background:{accent}; color:#ffffff; }}
            QPushButton#DashboardPrimaryButton {{
                background:{accent}; color:#ffffff; border:none; border-radius:8px;
                padding:8px 18px; font-weight:700;
            }}
            QPushButton#DashboardPrimaryButton:hover {{ background:{palette['accent_hover']}; }}
            QPushButton#DashboardSecondaryButton {{
                background:{palette['field']}; color:{palette['muted']};
                border:1px solid {palette['border_accent']}; border-radius:8px; padding:8px 14px;
            }}
            QPushButton#DashboardSecondaryButton:hover {{ background:{palette['accent_soft']}; border-color:{accent}; }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel(f"选择模型（共 {len(self._models)} 个）")
        title.setObjectName("ModelPickerTitle")
        head.addWidget(title)
        head.addStretch()
        root.addLayout(head)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索模型…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        self.search.returnPressed.connect(self._confirm)
        root.addWidget(self.search)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self._confirm())
        root.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("DashboardSecondaryButton")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        ok = QPushButton("使用")
        ok.setObjectName("DashboardPrimaryButton")
        ok.setDefault(True)
        ok.clicked.connect(self._confirm)
        buttons.addWidget(ok)
        root.addLayout(buttons)

        self._apply_filter("")

    def _apply_filter(self, keyword):
        kw = (keyword or "").strip().lower()
        self.list.clear()
        for mid in self._models:
            if not kw or kw in mid.lower():
                self.list.addItem(mid)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _confirm(self, *_args):
        item = self.list.currentItem()
        if item is not None:
            self._picked = item.text()
            self.accept()

    def picked(self):
        return self._picked


def show_model_picker(anchor_widget, models):
    """弹出可搜索的模型选择列表；返回选中的模型 ID，取消返回空串。"""
    dialog = ModelPickerDialog(models, anchor_widget)
    dialog.exec_()
    return dialog.picked()
