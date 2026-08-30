"""Sleep-time Compute settings page."""

import uuid

from PyQt5.QtCore import QSize, Qt, QThread, QTime, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

import config as cfg
from gui import theme_manager
from gui.model_fetcher import run_model_fetch, show_model_picker
from gui.settings_assets import tinted_settings_asset_icon
from gui.sleep_compute_assets import sleep_compute_asset_pixmap


def _repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class _ElidedLabel(QLabel):
    """Single-line label that keeps long model IDs inside the card."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = str(text or "")
        self.setTextFormat(Qt.PlainText)
        self.setToolTip(self._full_text)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        QLabel.setText(self, self._full_text)

    def resizeEvent(self, event):
        self._update_text()
        super().resizeEvent(event)

    def _update_text(self):
        QLabel.setText(
            self,
            self.fontMetrics().elidedText(
                self._full_text, Qt.ElideRight, max(0, self.contentsRect().width())
            ),
        )


class ModelPresetDialog(QDialog):
    """Create or edit one Sleep-time Compute model preset."""

    DELETE_RESULT = 2

    def __init__(self, preset=None, parent=None):
        super().__init__(parent)
        self._preset = preset or {}
        editing = bool(preset)
        self.setObjectName("SleepModelDialog")
        self.setWindowTitle("编辑模型方案" if editing else "添加模型方案")
        self.setModal(True)
        self.setFixedWidth(450)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(16)

        title = QLabel("编辑模型方案" if editing else "添加模型方案")
        title.setObjectName("SleepDialogTitle")
        root.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        self.name_input = QLineEdit(self._preset.get("name", ""))
        self.name_input.setPlaceholderText("例如：DeepSeek 记忆整理")
        self.model_input = QLineEdit(self._preset.get("model", ""))
        self.model_input.setPlaceholderText("例如：deepseek-chat")
        self.api_key_input = QLineEdit(self._preset.get("api_key", ""))
        self.api_key_input.setPlaceholderText("留空则使用全局 API Key")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_base_input = QLineEdit(self._preset.get("api_base", ""))
        self.api_base_input.setPlaceholderText("留空则使用全局 API Base")
        self.desc_input = QLineEdit(self._preset.get("description", ""))
        self.desc_input.setPlaceholderText("一句话说明模型特点")
        self.cost_input = QLineEdit(self._preset.get("cost", ""))
        self.cost_input.setPlaceholderText("例如：按服务商计费")
        form.addRow("方案名称", self.name_input)
        model_row = QHBoxLayout()
        model_row.setSpacing(8)
        model_row.addWidget(self.model_input, 1)
        self.fetch_btn = QPushButton("获取模型")
        self.fetch_btn.setObjectName("DashboardSecondaryButton")
        self.fetch_btn.setToolTip("用 API Base 和 Key 拉取该接口（OpenAI 格式）可用的模型列表")
        self.fetch_btn.setFixedWidth(88)
        self.fetch_btn.setCursor(Qt.PointingHandCursor)
        self.fetch_btn.clicked.connect(self._fetch_models)
        model_row.addWidget(self.fetch_btn)
        form.addRow("模型 ID", model_row)
        form.addRow("API Key", self.api_key_input)
        form.addRow("API Base", self.api_base_input)
        form.addRow("方案说明", self.desc_input)
        form.addRow("成本备注", self.cost_input)
        root.addLayout(form)

        actions = QHBoxLayout()
        if editing:
            delete_button = QPushButton("删除方案")
            delete_button.setObjectName("DashboardDangerButton")
            delete_button.setIcon(
                tinted_settings_asset_icon("action.delete", "#c54164")
            )
            delete_button.clicked.connect(
                lambda: self.done(ModelPresetDialog.DELETE_RESULT)
            )
            actions.addWidget(delete_button)
        actions.addStretch()
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("DashboardSecondaryButton")
        cancel_button.clicked.connect(self.reject)
        actions.addWidget(cancel_button)
        save_button = QPushButton("保存")
        save_button.setObjectName("DashboardPrimaryButton")
        save_button.setIcon(tinted_settings_asset_icon("action.save", "#ffffff"))
        save_button.clicked.connect(self._accept_if_valid)
        actions.addWidget(save_button)
        root.addLayout(actions)

    def _fetch_models(self):
        base = self.api_base_input.text().strip()
        if not base:
            QMessageBox.warning(
                self, "获取模型", "请先填写 API Base（OpenAI 格式接口地址），再点击获取模型"
            )
            return
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("获取中…")
        run_model_fetch(
            base, self.api_key_input.text().strip(),
            on_ok=self._on_models_fetched,
            on_fail=self._on_models_failed,
            on_settle=self._restore_fetch_btn,
        )

    def _on_models_fetched(self, models):
        picked = show_model_picker(self.fetch_btn, models)
        if picked:
            self.model_input.setText(picked)

    def _on_models_failed(self, err):
        QMessageBox.warning(
            self, "获取模型失败",
            f"没能拿到模型列表：\n{err}\n\n请检查 API Base 与 API Key 是否正确。",
        )

    def _restore_fetch_btn(self):
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("获取模型")

    def _accept_if_valid(self):
        if not self.name_input.text().strip() or not self.model_input.text().strip():
            QMessageBox.warning(self, "信息不完整", "方案名称和模型 ID 不能为空。")
            return
        self.accept()

    def values(self):
        return {
            "name": self.name_input.text().strip(),
            "model": self.model_input.text().strip(),
            "api_key": self.api_key_input.text().strip(),
            "api_base": self.api_base_input.text().strip(),
            "description": self.desc_input.text().strip() or "自定义记忆整合模型",
            "cost": self.cost_input.text().strip() or "按服务商计费",
        }


class ModelPresetCard(QWidget):
    """Compact model preset row styled after the supplied reference."""

    clicked = pyqtSignal(str)
    manage_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, preset, is_current=False, parent=None):
        super().__init__(parent)
        self.preset = preset
        self.setObjectName("ModelPresetCard")
        self.setProperty("current", bool(is_current))
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(86)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(11, 8, 10, 8)
        layout.setSpacing(11)

        artwork = QLabel()
        artwork.setObjectName("SleepModelArtwork")
        artwork.setAlignment(Qt.AlignCenter)
        artwork.setFixedSize(58, 58)
        artwork.setPixmap(
            sleep_compute_asset_pixmap("model.crystal", QSize(56, 56))
        )
        layout.addWidget(artwork)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(2)
        name_row = QHBoxLayout()
        name_row.setSpacing(7)
        name = _ElidedLabel(preset.get("name", "未命名方案"))
        name.setObjectName("PresetName")
        name.setMinimumHeight(20)
        name_row.addWidget(name, 1)
        if preset.get("recommended"):
            badge = QLabel("推荐")
            badge.setObjectName("SleepRecommendBadge")
            name_row.addWidget(badge)
        name_row.addStretch()
        copy.addLayout(name_row)

        description = _ElidedLabel(preset.get("description", ""))
        description.setObjectName("PresetDesc")
        description.setMinimumHeight(18)
        copy.addWidget(description)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(5)
        model = preset.get("model") or cfg.MODEL
        model_chip = _ElidedLabel(model)
        model_chip.setObjectName("SleepModelChip")
        model_chip.setMaximumWidth(210)
        model_chip.setMinimumHeight(18)
        meta_row.addWidget(model_chip)
        cost_chip = _ElidedLabel(preset.get("cost", "按服务商计费"))
        cost_chip.setObjectName("SleepModelChip")
        cost_chip.setMaximumWidth(150)
        cost_chip.setMinimumHeight(18)
        meta_row.addWidget(cost_chip)
        meta_row.addStretch()
        copy.addLayout(meta_row)
        layout.addLayout(copy, 1)

        if is_current:
            status = QLabel("当前方案")
            status.setObjectName("PresetCurrent")
            status.setAlignment(Qt.AlignCenter)
            status.setFixedSize(68, 28)
            layout.addWidget(status)
        else:
            use_button = QPushButton("使用")
            use_button.setObjectName("PresetUseButton")
            use_button.setFixedSize(62, 30)
            use_button.setCursor(Qt.PointingHandCursor)
            use_button.clicked.connect(lambda: self.clicked.emit(preset["id"]))
            layout.addWidget(use_button)

        if preset.get("custom"):
            manage_button = QPushButton()
            manage_button.setObjectName("SleepIconButton")
            manage_button.setFixedSize(30, 30)
            manage_button.setCursor(Qt.PointingHandCursor)
            manage_button.setToolTip("编辑模型方案")
            manage_button.setIcon(
                tinted_settings_asset_icon(
                    "action.edit", theme_manager.current_accent()
                )
            )
            manage_button.setIconSize(QSize(15, 15))
            manage_button.clicked.connect(
                lambda: self.manage_requested.emit(preset["id"])
            )
            layout.addWidget(manage_button)

            delete_button = QPushButton()
            delete_button.setObjectName("SleepIconButton")
            delete_button.setFixedSize(30, 30)
            delete_button.setCursor(Qt.PointingHandCursor)
            delete_button.setToolTip("删除模型方案")
            delete_button.setIcon(
                tinted_settings_asset_icon("action.delete", "#c54164")
            )
            delete_button.setIconSize(QSize(15, 15))
            delete_button.clicked.connect(
                lambda: self.delete_requested.emit(preset["id"])
            )
            layout.addWidget(delete_button)

    def sizeHint(self):
        return QSize(600, 90)


class SleepComputeWorker(QThread):
    """Run one manual memory consolidation without blocking the interface."""

    progress = pyqtSignal(str)
    completed = pyqtSignal(bool, str)

    def __init__(self, lookback_days, model_preset, parent=None):
        super().__init__(parent)
        self.lookback_days = lookback_days
        self.model_preset = model_preset  # 完整的模型方案配置

    def run(self):
        try:
            self.progress.emit("正在读取并分析记忆碎片...")
            from brain import archivist

            # 保存原始配置
            original_model = cfg.MODEL
            original_api_key = cfg.API_KEY
            original_api_base = cfg.API_BASE

            # 应用方案配置
            if self.model_preset:
                if self.model_preset.get("model"):
                    cfg.MODEL = self.model_preset["model"]
                if self.model_preset.get("api_key"):
                    cfg.API_KEY = self.model_preset["api_key"]
                if self.model_preset.get("api_base"):
                    cfg.API_BASE = self.model_preset["api_base"]

            try:
                archivist.sleep_time_consolidation(
                    lookback_days=self.lookback_days
                )
            finally:
                # 恢复原始配置
                cfg.MODEL = original_model
                cfg.API_KEY = original_api_key
                cfg.API_BASE = original_api_base
            self.completed.emit(True, "记忆整合已完成，可在运行日志中查看详情。")
        except Exception as error:
            self.completed.emit(False, f"整合失败：{error}")


class SleepComputeSettingsWidget(QWidget):
    """Reference-driven Sleep-time Compute settings surface."""

    settings_saved = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SleepComputeSettings")
        self.worker = None
        self.custom_presets = self._load_custom_presets()
        self._display_presets = []
        self._selected_model_preset = "default"
        self._pending_model = cfg.MODEL
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 0)
        root.setSpacing(9)

        basic = QFrame()
        basic.setObjectName("SleepSectionCard")
        basic.setProperty("section", "basic")
        basic_layout = QVBoxLayout(basic)
        basic_layout.setContentsMargins(15, 11, 15, 11)
        basic_layout.setSpacing(7)
        header = self._section_header("基础设置", "sidebar.settings")
        petals = QLabel()
        petals.setObjectName("SleepPetalDecoration")
        petals.setAttribute(Qt.WA_TransparentForMouseEvents)
        petals.setFixedSize(86, 30)
        petals.setPixmap(
            sleep_compute_asset_pixmap("decor.petals", QSize(86, 42))
        )
        petals.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(petals)
        basic_layout.addLayout(header)

        enable_row = QHBoxLayout()
        enable_row.setContentsMargins(2, 0, 2, 0)
        enable_copy = QVBoxLayout()
        enable_copy.setSpacing(0)
        enable_title = QLabel("启用 Sleep-time Compute")
        enable_title.setObjectName("SleepFieldTitle")
        enable_copy.addWidget(enable_title)
        enable_hint = QLabel("按设定时间自动整理长期记忆")
        enable_hint.setObjectName("SleepFieldHint")
        enable_copy.addWidget(enable_hint)
        enable_row.addLayout(enable_copy, 1)
        self.enable_status = QLabel("已启用")
        self.enable_status.setObjectName("SleepEnabledStatus")
        enable_row.addWidget(self.enable_status)
        from gui.dashboard_pages import SettingsToggle

        self.enable_toggle = SettingsToggle()
        self.enable_toggle.setToolTip("启用或暂停定时记忆整合")
        self.enable_toggle.toggled.connect(self._on_enable_changed)
        self.enable_check = self.enable_toggle
        enable_row.addWidget(self.enable_toggle)
        basic_layout.addLayout(enable_row)

        divider = QFrame()
        divider.setObjectName("SleepHairline")
        divider.setFixedHeight(1)
        basic_layout.addWidget(divider)

        self.time_edit = QTimeEdit()
        self.time_edit.setObjectName("SleepTimeEdit")
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setFixedWidth(132)
        self.time_edit.setToolTip("每天开始自动记忆整合的时间")
        basic_layout.addLayout(
            self._schedule_field(
                "每天执行时间", self.time_edit, "建议选择深夜，避免打扰"
            )
        )

        self.days_spin = QSpinBox()
        self.days_spin.setObjectName("SleepDaysSpin")
        self.days_spin.setRange(1, 30)
        self.days_spin.setSuffix(" 天")
        self.days_spin.setFixedWidth(132)
        self.days_spin.setToolTip("每次整合向前分析的天数")
        basic_layout.addLayout(
            self._schedule_field(
                "回溯天数", self.days_spin, "分析最近 N 天的记忆"
            )
        )
        root.addWidget(basic)

        model_section = QFrame()
        model_section.setObjectName("SleepSectionCard")
        model_section.setProperty("section", "model")
        model_section.setMinimumHeight(245)
        model_section.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Expanding
        )
        model_layout = QVBoxLayout(model_section)
        model_layout.setContentsMargins(15, 10, 15, 10)
        model_layout.setSpacing(5)
        model_header = self._section_header("模型设置", "nav.ai")
        self.add_preset_btn = QPushButton("添加方案")
        self.add_preset_btn.setObjectName("DashboardTextButton")
        self.add_preset_btn.setProperty("settingsIcon", "action.add")
        self.add_preset_btn.setCursor(Qt.PointingHandCursor)
        self.add_preset_btn.clicked.connect(self._add_custom_model)
        model_header.addWidget(self.add_preset_btn)
        model_layout.addLayout(model_header)

        model_copy = QHBoxLayout()
        model_copy.setSpacing(8)
        model_title = QLabel("模型预设方案")
        model_title.setObjectName("SleepFieldTitle")
        model_copy.addWidget(model_title)
        model_hint = QLabel("选择用于深度记忆整合的模型")
        model_hint.setObjectName("SleepFieldHint")
        model_copy.addWidget(model_hint)
        model_copy.addStretch()
        model_layout.addLayout(model_copy)

        self.model_list_widget = QListWidget()
        self.model_list_widget.setObjectName("ModelPresetList")
        self.model_list_widget.setFrameShape(QFrame.NoFrame)
        self.model_list_widget.setSpacing(3)
        self.model_list_widget.setMinimumHeight(155)
        self.model_list_widget.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self.model_list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.model_list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.model_list_widget.setVerticalScrollMode(
            QAbstractItemView.ScrollPerPixel
        )
        self.model_list_widget.setFocusPolicy(Qt.NoFocus)
        model_layout.addWidget(self.model_list_widget, 1)
        self.empty_model_hint = QLabel("暂无自定义方案，记忆整合将使用主对话模型")
        self.empty_model_hint.setObjectName("SleepFieldHint")
        self.empty_model_hint.setAlignment(Qt.AlignCenter)
        self.empty_model_hint.setVisible(False)
        model_layout.addWidget(self.empty_model_hint)
        root.addWidget(model_section, 1)

        manual = QFrame()
        manual.setObjectName("SleepSectionCard")
        manual.setProperty("section", "manual")
        manual.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        manual_layout = QVBoxLayout(manual)
        manual_layout.setContentsMargins(15, 10, 15, 10)
        manual_layout.setSpacing(6)
        manual_layout.addLayout(self._section_header("手动执行", "action.run"))
        manual_row = QHBoxLayout()
        manual_copy = QVBoxLayout()
        manual_copy.setSpacing(0)
        manual_title = QLabel("立即进行一次记忆整合")
        manual_title.setObjectName("SleepFieldTitle")
        manual_copy.addWidget(manual_title)
        manual_hint = QLabel("无需等待预定时间，使用当前页面参数执行")
        manual_hint.setObjectName("SleepFieldHint")
        manual_copy.addWidget(manual_hint)
        manual_row.addLayout(manual_copy, 1)
        self.run_btn = QPushButton("立即执行")
        self.run_btn.setObjectName("SleepRunButton")
        self.run_btn.setProperty("settingsIcon", "action.run")
        self.run_btn.setFixedSize(108, 38)
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.clicked.connect(self._run_manually)
        manual_row.addWidget(self.run_btn)
        manual_layout.addLayout(manual_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("SleepProgress")
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        manual_layout.addWidget(self.progress_bar)

        self.result_label = QLabel()
        self.result_label.setObjectName("SleepRunStatus")
        self.result_label.setWordWrap(True)
        self.result_label.setVisible(False)
        manual_layout.addWidget(self.result_label)
        self.result_text = self.result_label
        root.addWidget(manual)

        footer = QHBoxLayout()
        footer.setSpacing(9)
        self.save_feedback = QLabel()
        self.save_feedback.setObjectName("SleepSaveFeedback")
        self.save_feedback.setVisible(False)
        footer.addWidget(self.save_feedback)
        footer.addStretch()
        self.save_btn = QPushButton("保存设置")
        self.save_btn.setObjectName("DashboardPrimaryButton")
        self.save_btn.setProperty("settingsIcon", "action.save")
        self.save_btn.setFixedSize(112, 38)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self._save_settings)
        footer.addWidget(self.save_btn)
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setObjectName("DashboardSecondaryButton")
        self.reset_btn.setProperty("settingsIcon", "action.reset")
        self.reset_btn.setFixedSize(88, 38)
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.clicked.connect(self._reset_settings)
        footer.addWidget(self.reset_btn)
        root.addLayout(footer)

        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(self.save_feedback.hide)

    def _section_header(self, title, icon_name):
        row = QHBoxLayout()
        row.setSpacing(7)
        icon = QLabel()
        icon.setObjectName("SleepSectionIcon")
        icon.setFixedSize(22, 22)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(
            tinted_settings_asset_icon(
                icon_name, theme_manager.current_accent()
            ).pixmap(16, 16)
        )
        row.addWidget(icon)
        label = QLabel(title)
        label.setObjectName("SleepSectionTitle")
        row.addWidget(label)
        row.addStretch()
        return row

    def _schedule_field(self, title, control, hint):
        row = QHBoxLayout()
        row.setContentsMargins(1, 0, 1, 0)
        row.setSpacing(9)
        dot = QLabel("•")
        dot.setObjectName("SleepFieldDot")
        dot.setAlignment(Qt.AlignCenter)
        dot.setFixedWidth(10)
        row.addWidget(dot)
        label = QLabel(title)
        label.setObjectName("SleepFieldTitle")
        label.setFixedWidth(106)
        row.addWidget(label)
        row.addWidget(control)
        description = QLabel(hint)
        description.setObjectName("SleepFieldHint")
        description.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row.addWidget(description, 1)
        return row

    def _load_custom_presets(self):
        try:
            raw_presets = cfg.get_sleep_compute_custom_models()
        except Exception:
            return []
        presets = []
        for index, value in enumerate(raw_presets):
            if not isinstance(value, dict):
                continue
            name = str(value.get("name", "")).strip()
            model = str(value.get("model", "")).strip()
            if not name or not model:
                continue
            preset = dict(value)
            preset["id"] = str(
                preset.get("id") or f"custom-{index}-{uuid.uuid4().hex[:6]}"
            )
            preset["name"] = name
            preset["model"] = model
            preset["api_key"] = str(preset.get("api_key", "")).strip()
            preset["api_base"] = str(preset.get("api_base", "")).strip()
            preset["description"] = str(
                preset.get("description") or "自定义记忆整合模型"
            )
            preset["cost"] = str(preset.get("cost") or "按服务商计费")
            preset["custom"] = True
            presets.append(preset)
        return presets

    def _save_custom_presets(self):
        if not cfg.save_sleep_compute_custom_models(self.custom_presets):
            QMessageBox.warning(self, "保存失败", "模型方案未能写入配置文件。")
            return False
        return True

    def _all_presets(self, current_model=None):
        presets = [dict(item) for item in self.custom_presets]
        model = current_model or self._pending_model
        if model and model != cfg.MODEL and not any(
            item.get("model") == model for item in presets
        ):
            presets.insert(
                0,
                {
                    "id": "stored-model",
                    "name": model,
                    "model": model,
                    "description": "已保存在 Sleep-time Compute 中的模型",
                    "cost": "当前配置",
                },
            )
        return presets

    def _resolve_preset_id(self, model):
        for preset in self.custom_presets:
            if preset.get("model") == model:
                return preset["id"]
        if model and model != cfg.MODEL:
            return "stored-model"
        return ""  # 无选中：跟随主对话模型

    def _preset_by_id(self, preset_id):
        return next(
            (item for item in self._display_presets if item["id"] == preset_id),
            None,
        )

    def _refresh_all_model_cards(self):
        self.model_list_widget.clear()
        self._display_presets = self._all_presets()
        selected_item = None
        for preset in self._display_presets:
            is_current = preset["id"] == self._selected_model_preset
            card = ModelPresetCard(preset, is_current)
            card.clicked.connect(self._on_model_preset_clicked)
            card.manage_requested.connect(self._edit_custom_model)
            card.delete_requested.connect(self._delete_custom_model)
            item = QListWidgetItem()
            item.setFlags(Qt.ItemIsEnabled)
            item.setSizeHint(card.sizeHint())
            self.model_list_widget.addItem(item)
            self.model_list_widget.setItemWidget(item, card)
            if is_current:
                selected_item = item
        if selected_item is not None:
            self.model_list_widget.scrollToItem(
                selected_item, QAbstractItemView.PositionAtCenter
            )
        self.empty_model_hint.setVisible(not self._display_presets)

    def _on_enable_changed(self, enabled):
        enabled = bool(enabled)
        self.time_edit.setEnabled(enabled)
        self.days_spin.setEnabled(enabled)
        self.enable_status.setText("已启用" if enabled else "已暂停")
        self.enable_status.setProperty("enabled", enabled)
        _repolish(self.enable_status)

    def _on_model_preset_clicked(self, preset_id):
        preset = self._preset_by_id(preset_id)
        if preset is None:
            return
        self._selected_model_preset = preset_id
        self._pending_model = preset.get("model") or cfg.MODEL
        self._refresh_all_model_cards()

    def _load_settings(self):
        try:
            settings = cfg.get_sleep_compute_settings()
            self.enable_toggle.setChecked(bool(settings.get("enabled", True)))
            time_value = QTime.fromString(
                str(settings.get("execution_time", "23:00")), "HH:mm"
            )
            self.time_edit.setTime(time_value if time_value.isValid() else QTime(23, 0))
            self.days_spin.setValue(int(settings.get("lookback_days", 7)))
            self._pending_model = str(settings.get("model") or cfg.MODEL)
            self._selected_model_preset = self._resolve_preset_id(
                self._pending_model
            )
        except (TypeError, ValueError):
            self.enable_toggle.setChecked(True)
            self.time_edit.setTime(QTime(23, 0))
            self.days_spin.setValue(7)
            self._pending_model = cfg.MODEL
            self._selected_model_preset = ""
        self._on_enable_changed(self.enable_toggle.isChecked())
        self._refresh_all_model_cards()

    def _open_model_dialog(self, preset=None):
        dialog = ModelPresetDialog(preset, self)
        result = dialog.exec_()
        return dialog, result

    def _add_custom_model(self):
        dialog, result = self._open_model_dialog()
        if result != QDialog.Accepted:
            return
        preset = dialog.values()
        preset.update(
            {
                "id": f"custom-{uuid.uuid4().hex[:10]}",
                "custom": True,
            }
        )
        self.custom_presets.append(preset)
        if not self._save_custom_presets():
            self.custom_presets.pop()
            return
        self._selected_model_preset = preset["id"]
        self._pending_model = preset["model"]
        self._refresh_all_model_cards()
        self._show_feedback("模型方案已添加", "success")

    def _edit_custom_model(self, preset_id):
        index = next(
            (
                position
                for position, item in enumerate(self.custom_presets)
                if item["id"] == preset_id
            ),
            -1,
        )
        if index < 0:
            return
        original = dict(self.custom_presets[index])
        dialog, result = self._open_model_dialog(original)
        if result == ModelPresetDialog.DELETE_RESULT:
            self._confirm_and_remove(index)
            return
        if result != QDialog.Accepted:
            return
        updated = dict(original)
        updated.update(dialog.values())
        self.custom_presets[index] = updated
        if not self._save_custom_presets():
            self.custom_presets[index] = original
            return
        if self._selected_model_preset == preset_id:
            self._pending_model = updated["model"]
        self._refresh_all_model_cards()
        self._show_feedback("模型方案已更新", "success")

    def _delete_custom_model(self, preset_id):
        index = next(
            (
                position
                for position, item in enumerate(self.custom_presets)
                if item["id"] == preset_id
            ),
            -1,
        )
        if index < 0:
            return
        self._confirm_and_remove(index)

    def _confirm_and_remove(self, index):
        name = self.custom_presets[index].get("name") or "该方案"
        preset_id = self.custom_presets[index].get("id")
        answer = QMessageBox.question(
            self,
            "删除模型方案",
            f"确定删除“{name}”吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        removed = self.custom_presets.pop(index)
        if not self._save_custom_presets():
            self.custom_presets.insert(index, removed)
            return
        ref = removed.get("secret_ref")
        if ref:
            try:
                cfg.secret_store.delete(ref)
            except Exception:
                pass
        if self._selected_model_preset == preset_id:
            self._selected_model_preset = ""
            self._pending_model = cfg.MODEL
        self._refresh_all_model_cards()
        self._show_feedback("模型方案已删除", "success")

    def _get_selected_model(self):
        preset = self._preset_by_id(self._selected_model_preset)
        if preset is None:
            return self._pending_model or cfg.MODEL
        return preset.get("model") or cfg.MODEL

    def _get_selected_preset(self):
        """获取当前选中的完整方案配置（无选中/遗留模型名返回 None，使用全局配置）。"""
        preset = self._preset_by_id(self._selected_model_preset)
        if preset is None or not preset.get("custom"):
            return None
        return preset

    def _save_settings(self):
        settings = {
            "enabled": self.enable_toggle.isChecked(),
            "execution_time": self.time_edit.time().toString("HH:mm"),
            "lookback_days": self.days_spin.value(),
            "model": self._get_selected_model(),
        }
        # 保存完整的方案配置（包括 API Key 和 Base）
        preset = self._get_selected_preset()
        if preset:
            settings["model_preset"] = {
                "model": preset.get("model"),
                "api_key": preset.get("api_key", ""),
                "api_base": preset.get("api_base", ""),
            }
        if not cfg.save_sleep_compute_settings(settings):
            QMessageBox.warning(self, "保存失败", "Sleep-time Compute 设置未能写入配置文件。")
            return False
        self._pending_model = settings["model"]
        self.settings_saved.emit()
        self._show_feedback("设置已保存", "success")
        QMessageBox.information(self, "已保存", "Sleep-time Compute 设置已保存。")
        return True

    def _reset_settings(self):
        self.enable_toggle.setChecked(True)
        self.time_edit.setTime(QTime(23, 0))
        self.days_spin.setValue(7)
        self._selected_model_preset = ""
        self._pending_model = cfg.MODEL
        self._refresh_all_model_cards()
        self._show_feedback("已恢复默认值，保存后生效", "neutral")

    def _show_feedback(self, text, kind):
        self.save_feedback.setText(text)
        self.save_feedback.setProperty("kind", kind)
        _repolish(self.save_feedback)
        self.save_feedback.show()
        self._feedback_timer.start(3500)

    def _run_manually(self):
        if self.worker is not None and self.worker.isRunning():
            return
        self.run_btn.setEnabled(False)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        self.result_label.setText("正在准备记忆整合...")
        self.result_label.setProperty("kind", "running")
        _repolish(self.result_label)
        self.result_label.show()

        worker = SleepComputeWorker(
            self.days_spin.value(), self._get_selected_preset(), self
        )
        self.worker = worker
        worker.progress.connect(self._on_progress)
        worker.completed.connect(self._on_finished)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda: self._clear_worker(worker))
        worker.start()

    def _clear_worker(self, worker):
        if self.worker is worker:
            self.worker = None

    def _on_progress(self, message):
        self.result_label.setText(message)

    def _on_finished(self, success, result):
        self.result_label.setText(result)
        self.result_label.setProperty("kind", "success" if success else "error")
        _repolish(self.result_label)
        self.progress_bar.hide()
        self.run_btn.setEnabled(True)
