"""
RikkaAI - 小鸟游六花 角色立绘组件
"""
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QScrollArea, QFrame,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QFont

import config


class CharacterWidget(QWidget):
    """六花角色展示面板"""

    STATUS_TEXTS = [
        "邪王真眼 激活中 ✨",
        "魔力充填中… 🔮",
        "感知境界线中 🌙",
    ]

    QUOTES = [
        "「寄宿在我左眼的黑暗之力啊…」",
        "「这是…契约的证明！」",
        "「邪王真眼看穿了！」",
        "「哼，可别小看了我的力量」",
        "「现充爆炸吧！」",
        "「黑暗之力…要溢出来了…！」",
        "「不行！不行！绝对不行！」",
        "「勇太…！？」",
        "「我是普通的女高中生啦！」",
        "「不，黑暗之力是永恒的」",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CharacterWidget")
        self.setFixedWidth(config.CHARACTER_PANEL_WIDTH)

        # 扫描可用头像
        self._avatars = self._scan_avatars()
        # 从配置文件读取上次选择的头像索引
        import json
        saved_idx = 0
        try:
            if os.path.exists(config.USER_CONFIG_PATH):
                with open(config.USER_CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                saved_idx = int(cfg_data.get("avatar_index", 0))
        except Exception:
            pass
        self._avatar_index = saved_idx if saved_idx < len(self._avatars) else 0

        self._quote_index = 0
        self._status_index = 0

        self._setup_ui()
        self._load_avatar()
        self._start_animations()

    def _scan_avatars(self):
        """扫描 assets/images/ 下的 rikka_*.png"""
        img_dir = config.IMAGES_DIR
        files = []
        for f in sorted(os.listdir(img_dir)):
            if f.startswith("rikka_") and f.endswith(".png"):
                files.append(os.path.join(img_dir, f))
        return files if files else [config.CHARACTER_IMAGE_PATH]

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignTop)

        # ── 角色图片（点击切换） ──
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedHeight(280)
        self.image_label.setCursor(Qt.PointingHandCursor)
        self.image_label.setToolTip("点击切换头像")
        self.image_label.setStyleSheet("""
            background-color: #12081e;
            border: 1px solid #2a1050;
            border-radius: 12px;
        """)
        self.image_label.mousePressEvent = lambda e: self._switch_avatar()
        layout.addWidget(self.image_label)

        # ── 头像计数器 ──
        self._avatar_counter = QLabel()
        self._avatar_counter.setAlignment(Qt.AlignCenter)
        self._avatar_counter.setStyleSheet("color: #5a3a7a; font-size: 10px; padding-bottom: 2px;")
        layout.addWidget(self._avatar_counter)

        # ── 角色名称 ──
        name_label = QLabel("小鸟游六花")
        name_label.setObjectName("CharacterName")
        name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_label)

        # ── 称号 ──
        title_label = QLabel("邪王真眼使用者")
        title_label.setObjectName("CharacterTitle")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # ── 副标题 ──
        sub_label = QLabel("Far East Magic Nap Society")
        sub_label.setObjectName("CharacterSubtitle")
        sub_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub_label)

        # ── 分隔线 ──
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("border: none; border-top: 1px solid #2a1050;")
        separator.setFixedHeight(1)
        layout.addWidget(separator)

        # ── 状态标签 ──
        self.status_label = QLabel(self.STATUS_TEXTS[0])
        self.status_label.setObjectName("CharacterQuote")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # ── 名言引用 ──
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setStyleSheet("border: none; border-top: 1px solid #2a1050;")
        separator2.setFixedHeight(1)
        layout.addWidget(separator2)

        quote_title = QLabel("💬 六花语録")
        quote_title.setStyleSheet("color: #5a3a7a; font-size: 10px; padding-top: 4px;")
        quote_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(quote_title)

        self.quote_label = QLabel(self.QUOTES[0])
        self.quote_label.setStyleSheet("""
            color: #c084fc;
            font-size: 11px;
            font-style: italic;
            padding: 6px 8px;
            background-color: transparent;
            border: none;
        """)
        self.quote_label.setAlignment(Qt.AlignCenter)
        self.quote_label.setWordWrap(True)
        layout.addWidget(self.quote_label)

        # ── 填充 ──
        layout.addStretch()

    def _start_animations(self):
        """定时切换状态和语录"""
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._cycle_status)
        self._status_timer.start(5000)

        self._quote_timer = QTimer(self)
        self._quote_timer.timeout.connect(self._cycle_quote)
        self._quote_timer.start(8000)

    def _cycle_status(self):
        self._status_index = (self._status_index + 1) % len(self.STATUS_TEXTS)
        self.status_label.setText(self.STATUS_TEXTS[self._status_index])

    def _cycle_quote(self):
        self._quote_index = (self._quote_index + 1) % len(self.QUOTES)
        self.quote_label.setText(self.QUOTES[self._quote_index])

    def update_status(self, text: str):
        """外部更新状态显示"""
        self.status_label.setText(text)

    def update_emotion(self, emotion: str):
        """外部更新情绪状态"""
        emoji_map = {
            "happy": "😊", "angry": "😠", "sad": "😢",
            "surprise": "😲", "tsundere": "😤", "chuunibyou": "✨",
        }
        emoji = emoji_map.get(emotion, "✨")
        self.status_label.setText(f"邪王真眼 · {emotion} {emoji}")

    def _load_avatar(self):
        """加载当前索引的头像"""
        if not self._avatars:
            return
        path = self._avatars[self._avatar_index]
        pixmap = QPixmap(path)
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                196, 276, Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            self.image_label.setPixmap(scaled)
        else:
            self.image_label.setText("🦋\n六花")
        total = len(self._avatars)
        self._avatar_counter.setText(f"{self._avatar_index + 1} / {total}")

    def _switch_avatar(self):
        """点击切换到下一张头像"""
        if not self._avatars:
            return
        self._avatar_index = (self._avatar_index + 1) % len(self._avatars)
        self._load_avatar()
        config.save_user_config({"avatar_index": self._avatar_index})
