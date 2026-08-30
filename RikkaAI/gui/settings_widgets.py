"""Widgets ported from the retired settings dialog, restyled for the dashboard."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import config
from gui import dialog_theme
from gui.model_fetcher import run_model_fetch, show_model_picker


class _ElidedPresetLabel(QLabel):
    """Single-line preset text that yields space to the action buttons."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self._full_text = str(text or "")
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setToolTip(self._full_text)
        self._update_elided_text()

    def resizeEvent(self, event):
        self._update_elided_text()
        super().resizeEvent(event)

    def _update_elided_text(self):
        available_width = max(0, self.contentsRect().width())
        QLabel.setText(
            self,
            self.fontMetrics().elidedText(
                self._full_text, Qt.ElideRight, available_width
            ),
        )


class PresetEditDialog(QDialog):
    """Edit one preset's name / api key / model / base url."""

    def __init__(self, name, api_key="", model="", api_base="", parent=None):
        super().__init__(parent)
        self._original_name = name
        self.setWindowTitle("编辑预设")
        self.setFixedSize(460, 330)
        palette = dialog_theme.colors()
        self._palette = palette
        accent = palette["accent"]
        self.setStyleSheet(
            f"""
            QDialog {{ background:{palette['surface_soft']}; color:{palette['text']}; }}
            QLabel {{ color:{palette['text']}; }}
            QLineEdit {{
                background:{palette['field']}; border:1px solid {palette['border_accent']}; border-radius:10px;
                padding:9px 12px; color:{palette['text']}; font-size:13px;
            }}
            QLineEdit:focus {{ border-color:{accent}; background:{palette['surface_strong']}; }}
            QPushButton#DashboardPrimaryButton {{ background:{accent}; color:#ffffff; border:none; border-radius:10px; }}
            QPushButton#DashboardPrimaryButton:hover {{ background:{palette['accent_hover']}; }}
            QPushButton#DashboardSecondaryButton {{ background:{palette['field']}; color:{palette['muted']}; border:1px solid {palette['border_accent']}; border-radius:10px; }}
            QPushButton#DashboardSecondaryButton:hover {{ background:{palette['accent_soft']}; border-color:{accent}; }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self._title = QLabel("编辑预设方案")
        self._title.setStyleSheet(f"font-size:20px;font-weight:700;color:{accent};")
        layout.addWidget(self._title)

        form = QFormLayout()
        form.setSpacing(12)
        self._name = QLineEdit(name)
        self._api_key = QLineEdit(api_key)
        self._api_key.setEchoMode(QLineEdit.Password)
        self._model = QLineEdit(model)
        self._api_base = QLineEdit(api_base)
        form.addRow("名称", self._name)
        form.addRow("API Key", self._api_key)
        model_row = QHBoxLayout()
        model_row.setSpacing(8)
        model_row.addWidget(self._model, 1)
        self._fetch_btn = QPushButton("获取模型")
        self._fetch_btn.setObjectName("DashboardSecondaryButton")
        self._fetch_btn.setToolTip("用地址和 Key 拉取该接口（OpenAI 格式）可用的模型列表")
        self._fetch_btn.setFixedWidth(88)
        self._fetch_btn.setCursor(Qt.PointingHandCursor)
        self._fetch_btn.clicked.connect(self._fetch_models)
        model_row.addWidget(self._fetch_btn)
        form.addRow("模型", model_row)
        form.addRow("地址", self._api_base)
        layout.addLayout(form)
        layout.addStretch()

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("DashboardSecondaryButton")
        cancel.setFixedSize(92, 36)
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        save = QPushButton("保存")
        save.setObjectName("DashboardPrimaryButton")
        save.setFixedSize(92, 36)
        save.clicked.connect(self._on_save)
        actions.addWidget(save)
        layout.addLayout(actions)

    def _fetch_models(self):
        base = self._api_base.text().strip()
        if not base:
            QMessageBox.warning(
                self, "获取模型", "请先填写下面的接口地址（Base URL），再点击获取模型"
            )
            return
        self._fetch_btn.setEnabled(False)
        self._fetch_btn.setText("获取中…")
        run_model_fetch(
            base, self._api_key.text().strip(),
            on_ok=self._on_models_fetched,
            on_fail=self._on_models_failed,
            on_settle=self._restore_fetch_btn,
        )

    def _on_models_fetched(self, models):
        picked = show_model_picker(self._fetch_btn, models)
        if picked:
            self._model.setText(picked)

    def _on_models_failed(self, err):
        QMessageBox.warning(
            self, "获取模型失败",
            f"没能拿到模型列表：\n{err}\n\n请检查接口地址与 API Key 是否正确。",
        )

    def _restore_fetch_btn(self):
        self._fetch_btn.setEnabled(True)
        self._fetch_btn.setText("获取模型")

    def _on_save(self):
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "名称不能为空")
            return
        if name != self._original_name:
            if not config.delete_preset(self._original_name):
                QMessageBox.warning(self, "失败", "无法更新原方案，请检查配置文件的写入权限")
                return
        if not config.add_preset(
            name,
            self._api_key.text().strip(),
            self._model.text().strip(),
            self._api_base.text().strip(),
        ):
            QMessageBox.warning(self, "失败", "方案保存失败，请检查 API Key 的安全存储权限")
            return
        self.accept()


class ImageGenerationPresetEditDialog(PresetEditDialog):
    """Edit a provider configuration used exclusively by image generation."""

    def __init__(self, name, api_key="", model="", api_base="", parent=None):
        super().__init__(name, api_key, model, api_base, parent)
        self.setWindowTitle("编辑生图方案")
        self._title.setText("编辑生图模型方案")
        self._model.setPlaceholderText("例如：provider-image-model")
        self._api_base.setPlaceholderText("例如：https://api.example.com/v1")

    def _on_save(self):
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "名称不能为空")
            return
        if name != self._original_name:
            if not config.delete_image_generation_preset(self._original_name):
                QMessageBox.warning(self, "失败", "无法重命名原有生图方案")
                return
        if not config.add_image_generation_preset(
            name,
            self._api_key.text().strip(),
            self._model.text().strip(),
            self._api_base.text().strip(),
        ):
            QMessageBox.warning(self, "失败", "生图方案保存失败，请检查 API Key 的安全存储权限")
            return
        self.accept()


class VisionPresetEditDialog(PresetEditDialog):
    """Edit a provider configuration used exclusively for image understanding."""

    def __init__(self, name, api_key="", model="", api_base="", parent=None):
        super().__init__(name, api_key, model, api_base, parent)
        self.setWindowTitle("编辑识图方案")
        self._title.setText("编辑识图模型方案")
        self._model.setPlaceholderText("例如：provider-vision-model")
        self._api_base.setPlaceholderText(
            "例如：https://api.example.com/v1/chat/completions"
        )

    def _on_save(self):
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "名称不能为空")
            return
        if name != self._original_name:
            if not config.delete_vision_preset(self._original_name):
                QMessageBox.warning(self, "失败", "无法重命名原有识图方案")
                return
        if not config.add_vision_preset(
            name,
            self._api_key.text().strip(),
            self._model.text().strip(),
            self._api_base.text().strip(),
        ):
            QMessageBox.warning(self, "失败", "识图方案保存失败，请检查 API Key 的安全存储权限")
            return
        self.accept()


class PresetItemWidget(QWidget):
    """One preset row: name + model, with 管理 / 使用 actions."""

    manage_clicked = pyqtSignal(object)
    use_clicked = pyqtSignal(object)
    selection_requested = pyqtSignal()

    def __init__(self, data, parent=None, active=False):
        super().__init__(parent)
        self._data = data
        self.setObjectName("SettingsPresetRow")
        self.setProperty("selected", False)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(64)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 14, 10)
        layout.setSpacing(12)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        name = _ElidedPresetLabel(data["name"])
        name.setObjectName("DashboardRowTitle")
        name.setMinimumHeight(20)
        name.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        text_layout.addWidget(name)
        model = _ElidedPresetLabel(data.get("model", "") or "未配置模型")
        model.setObjectName("DashboardMuted")
        model.setMinimumHeight(18)
        model.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        text_layout.addWidget(model)
        layout.addLayout(text_layout, 1)

        manage = QPushButton("管理")
        manage.setObjectName("DashboardSecondaryButton")
        manage.setFixedSize(76, 36)
        manage.setCursor(Qt.PointingHandCursor)
        manage.pressed.connect(self.selection_requested)
        manage.clicked.connect(lambda: self.manage_clicked.emit(self._data))
        layout.addWidget(manage)

        use = QPushButton("使用中" if active else "使用")
        use.setObjectName("DashboardPrimaryButton")
        use.setFixedSize(76, 36)
        use.setCursor(Qt.PointingHandCursor)
        use.setEnabled(not active)
        use.pressed.connect(self.selection_requested)
        use.clicked.connect(lambda: self.use_clicked.emit(self._data))
        layout.addWidget(use)

    def set_selected(self, selected):
        selected = bool(selected)
        if self.property("selected") == selected:
            return
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
