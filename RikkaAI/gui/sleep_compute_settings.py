"""
RikkaAI - Sleep-time Compute 设置界面
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QSpinBox, QTimeEdit, QComboBox,
                             QGroupBox, QCheckBox, QTextEdit, QProgressBar)
from PyQt5.QtCore import Qt, QTime, pyqtSignal, QThread
from PyQt5.QtGui import QFont
import config as cfg


class SleepComputeWorker(QThread):
    """后台执行 Sleep-time Compute 的线程"""
    finished = pyqtSignal(str)  # 完成信号（返回结果文本）
    progress = pyqtSignal(str)   # 进度信号

    def __init__(self, lookback_days, model):
        super().__init__()
        self.lookback_days = lookback_days
        self.model = model

    def run(self):
        try:
            self.progress.emit("正在分析记忆碎片...")

            from brain import archivist
            # 临时修改模型（如果需要）
            original_model = cfg.MODEL
            if self.model != "default":
                cfg.MODEL = self.model

            try:
                archivist.sleep_time_consolidation(lookback_days=self.lookback_days)
                result = "✅ 记忆整合完成！查看日志了解详情。"
            finally:
                cfg.MODEL = original_model

            self.finished.emit(result)
        except Exception as e:
            self.finished.emit(f"❌ 整合失败: {str(e)}")


class SleepComputeSettingsWidget(QWidget):
    """Sleep-time Compute 设置界面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # 标题
        title = QLabel("🌙 Sleep-time Compute - 深度记忆整合")
        title.setFont(QFont("Microsoft YaHei UI", 16, QFont.Bold))
        layout.addWidget(title)

        # 说明文本
        desc = QLabel(
            "每天凌晨自动运行，使用大模型深度整合记忆：\n"
            "• 识别并合并重复记忆\n"
            "• 提取长期行为模式\n"
            "• 生成连贯的叙事段落"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; padding: 10px; background: #f5f5f5; border-radius: 8px;")
        layout.addWidget(desc)

        # ═══ 基础设置 ═══
        basic_group = QGroupBox("⚙️ 基础设置")
        basic_layout = QVBoxLayout()

        # 启用开关
        self.enable_check = QCheckBox("启用 Sleep-time Compute")
        self.enable_check.setChecked(True)
        self.enable_check.stateChanged.connect(self._on_enable_changed)
        basic_layout.addWidget(self.enable_check)

        # 执行时间
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("每天执行时间:"))
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime(3, 0))  # 默认凌晨3点
        self.time_edit.setDisplayFormat("HH:mm")
        time_layout.addWidget(self.time_edit)
        time_layout.addWidget(QLabel("（建议选择深夜，避免打扰）"))
        time_layout.addStretch()
        basic_layout.addLayout(time_layout)

        # 回溯天数
        days_layout = QHBoxLayout()
        days_layout.addWidget(QLabel("回溯天数:"))
        self.days_spin = QSpinBox()
        self.days_spin.setRange(1, 30)
        self.days_spin.setValue(7)
        self.days_spin.setSuffix(" 天")
        days_layout.addWidget(self.days_spin)
        days_layout.addWidget(QLabel("（分析最近N天的记忆）"))
        days_layout.addStretch()
        basic_layout.addLayout(days_layout)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # ═══ 模型设置 ═══
        model_group = QGroupBox("🤖 模型设置")
        model_layout = QVBoxLayout()

        model_select_layout = QHBoxLayout()
        model_select_layout.addWidget(QLabel("使用模型:"))
        self.model_combo = QComboBox()
        self.model_combo.addItem("默认（当前配置）", "default")
        self.model_combo.addItem("DeepSeek v3 (推荐)", "deepseek-chat")
        self.model_combo.addItem("Claude Opus 4", "claude-opus-4-20250514")
        self.model_combo.addItem("Claude Sonnet 3.5", "claude-3-5-sonnet-20241022")
        self.model_combo.addItem("Qwen Max", "qwen-max")
        self.model_combo.addItem("自定义", "custom")
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        model_select_layout.addWidget(self.model_combo)
        model_select_layout.addStretch()
        model_layout.addLayout(model_select_layout)

        # 自定义模型输入
        self.custom_model_input = QComboBox()
        self.custom_model_input.setEditable(True)
        self.custom_model_input.setPlaceholderText("输入自定义模型名称（如 gpt-4）")
        self.custom_model_input.addItems([
            "gpt-4-turbo",
            "gpt-4o",
            "claude-3-opus-20240229",
            "deepseek-chat",
            "qwen-max-latest",
        ])
        self.custom_model_input.setVisible(False)
        model_layout.addWidget(self.custom_model_input)

        # 模型说明
        model_info = QLabel(
            "💡 模型选择建议：\n"
            "• DeepSeek v3: 性价比最高，速度快，成本低（¥0.004/次）\n"
            "• Claude Opus: 最强理解力，但成本较高（¥0.15/次）\n"
            "• Claude Sonnet: 平衡选择（¥0.03/次）"
        )
        model_info.setWordWrap(True)
        model_info.setStyleSheet("color: #555; font-size: 12px; padding: 8px; background: #fff9e6; border-radius: 6px;")
        model_layout.addWidget(model_info)

        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # ═══ 手动执行 ═══
        manual_group = QGroupBox("🔧 手动执行")
        manual_layout = QVBoxLayout()

        manual_desc = QLabel("不想等到凌晨？立即执行一次记忆整合：")
        manual_layout.addWidget(manual_desc)

        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton("▶ 立即执行")
        self.run_btn.setFixedHeight(40)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background: #4CAF50;
                color: white;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #45a049;
            }
            QPushButton:disabled {
                background: #ccc;
            }
        """)
        self.run_btn.clicked.connect(self._run_manually)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addStretch()
        manual_layout.addLayout(btn_layout)

        # 进度显示
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        manual_layout.addWidget(self.progress_bar)

        # 结果显示
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(100)
        self.result_text.setPlaceholderText("执行结果将显示在这里...")
        self.result_text.setVisible(False)
        manual_layout.addWidget(self.result_text)

        manual_group.setLayout(manual_layout)
        layout.addWidget(manual_group)

        # ═══ 底部按钮 ═══
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton("💾 保存设置")
        save_btn.setFixedHeight(36)
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)

        reset_btn = QPushButton("🔄 重置")
        reset_btn.setFixedHeight(36)
        reset_btn.clicked.connect(self._reset_settings)
        btn_layout.addWidget(reset_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

    def _on_enable_changed(self, state):
        """启用状态改变"""
        enabled = (state == Qt.Checked)
        self.time_edit.setEnabled(enabled)
        self.days_spin.setEnabled(enabled)
        self.model_combo.setEnabled(enabled)
        self.custom_model_input.setEnabled(enabled)

    def _on_model_changed(self, index):
        """模型选择改变"""
        model_data = self.model_combo.currentData()
        self.custom_model_input.setVisible(model_data == "custom")

    def _load_settings(self):
        """加载设置"""
        try:
            settings = cfg.get_sleep_compute_settings()
            self.enable_check.setChecked(settings.get("enabled", True))

            # 执行时间
            time_str = settings.get("execution_time", "03:00")
            hour, minute = map(int, time_str.split(":"))
            self.time_edit.setTime(QTime(hour, minute))

            # 回溯天数
            self.days_spin.setValue(settings.get("lookback_days", 7))

            # 模型
            model = settings.get("model", "deepseek-chat")
            index = self.model_combo.findData(model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)
            else:
                self.model_combo.setCurrentIndex(self.model_combo.findData("custom"))
                self.custom_model_input.setCurrentText(model)
        except Exception:
            pass

    def _save_settings(self):
        """保存设置"""
        settings = {
            "enabled": self.enable_check.isChecked(),
            "execution_time": self.time_edit.time().toString("HH:mm"),
            "lookback_days": self.days_spin.value(),
            "model": self._get_selected_model(),
        }

        cfg.save_sleep_compute_settings(settings)

        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(self, "保存成功", "Sleep-time Compute 设置已保存！\n重启应用后生效。")

    def _reset_settings(self):
        """重置设置"""
        self.enable_check.setChecked(True)
        self.time_edit.setTime(QTime(3, 0))
        self.days_spin.setValue(7)
        self.model_combo.setCurrentIndex(1)  # DeepSeek v3

    def _get_selected_model(self):
        """获取选中的模型"""
        model_data = self.model_combo.currentData()
        if model_data == "custom":
            return self.custom_model_input.currentText()
        elif model_data == "default":
            return cfg.MODEL
        else:
            return model_data

    def _run_manually(self):
        """手动执行"""
        if self.worker and self.worker.isRunning():
            return

        self.run_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不确定进度
        self.result_text.setVisible(True)
        self.result_text.clear()
        self.result_text.append("⏳ 正在执行记忆整合...")

        lookback_days = self.days_spin.value()
        model = self._get_selected_model()

        self.worker = SleepComputeWorker(lookback_days, model)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, message):
        """进度更新"""
        self.result_text.append(f"📝 {message}")

    def _on_finished(self, result):
        """执行完成"""
        self.result_text.append(f"\n{result}")
        self.progress_bar.setVisible(False)
        self.run_btn.setEnabled(True)
