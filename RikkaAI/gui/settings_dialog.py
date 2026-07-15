"""
RikkaAI - 设置对话框
"""
import os
from PyQt5.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,QSlider,
    QWidget,QListWidget,QListWidgetItem,QStackedWidget,QInputDialog,QMessageBox,
    QCheckBox,QSpinBox,QFormLayout,QTextEdit,QComboBox,QGroupBox)
from PyQt5.QtCore import Qt,pyqtSignal
import config

class SettingsDialog(QDialog):
    config_changed=pyqtSignal()
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle("设置"); self.resize(540,480); self.setMinimumSize(460,380)
        self.setStyleSheet("QDialog{background:#0f0a18}"); self._setup_ui(); self._load_settings()

    def _setup_ui(self):
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        h=QWidget(); h.setFixedHeight(48); h.setStyleSheet("background:#120b1a;border-bottom:1px solid #2a1050")
        hd=QHBoxLayout(h); hd.setContentsMargins(20,0,16,0)
        t=QLabel("⚙ 邪王真眼控制台"); t.setStyleSheet("font-size:15px;font-weight:bold;color:#c084fc;"); hd.addWidget(t); hd.addStretch()
        c=QPushButton("关闭"); c.setFixedSize(60,26)
        c.setStyleSheet("QPushButton{background:transparent;border:1px solid #2a1050;border-radius:13px;font-size:11px;color:#7a5aaa}QPushButton:hover{border-color:#5a2a9e;color:#c084fc}")
        c.setCursor(Qt.PointingHandCursor); c.clicked.connect(self.accept); hd.addWidget(c); outer.addWidget(h)
        body=QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0)
        self._nav=QListWidget(); self._nav.setFixedWidth(100)
        self._nav.setStyleSheet("QListWidget{background:#0d0a14;border:none;border-right:1px solid #1f0d38;padding:8px 0}QListWidget::item{color:#7a5aaa;font-size:11px;padding:10px 14px;border-left:3px solid transparent}QListWidget::item:selected{background:#1a0d2e;color:#c084fc;border-left:3px solid #7a3aba}QListWidget::item:hover{background:#140a20;color:#e0d0f0}")
        self._nav.itemClicked.connect(self._switch_page); body.addWidget(self._nav)
        self._pages=QStackedWidget(); self._pages.setStyleSheet("background:transparent;"); body.addWidget(self._pages,1)
        outer.addLayout(body,1)
        self._add_page("回复温度",self._build_temp_page())
        self._add_page("API 配置",self._build_api_page())
        self._add_page("主动聊天",self._build_proactive_page())
        self._add_page("智能搜图",self._build_smart_search_page())
        self._add_page("行为规则",self._build_persona_page())
        self._add_page("QQ 桥接",self._build_qq_page())
        self._nav.setCurrentRow(0)

    def _add_page(self,n,w): self._nav.addItem(QListWidgetItem(n)); self._pages.addWidget(w)
    def _switch_page(self,i): self._pages.setCurrentIndex(self._nav.row(i))

    def _build_preset_page(self):
        """(已废弃 — 预设管理已移到 API 配置页面内)"""
        return QWidget()

    def _build_temp_page(self):
        p=QWidget(); l=QVBoxLayout(p); l.setContentsMargins(20,16,20,16); l.setSpacing(16)
        lb=QLabel("控制回复的创造力和稳定性"); lb.setStyleSheet("color:#5a3a7a;font-size:11px;"); l.addWidget(lb)
        self._ts=QSlider(Qt.Horizontal); self._ts.setRange(10,100)
        self._ts.setStyleSheet("QSlider::groove:horizontal{height:6px;background:#1a0d2e;border-radius:3px}QSlider::handle:horizontal{background:#7a3aba;width:18px;height:18px;margin:-6px 0;border-radius:9px}QSlider::handle:horizontal:hover{background:#9b59b6}QSlider::sub-page:horizontal{background:#5a2a9e;border-radius:3px}")
        self._ts.valueChanged.connect(self._utl); l.addWidget(self._ts)
        r=QHBoxLayout(); r.addStretch()
        self._tl=QLabel("0.65"); self._tl.setStyleSheet("color:#ffd700;font-size:18px;font-weight:bold;"); r.addWidget(self._tl); r.addStretch(); l.addLayout(r)
        n=QLabel("低=稳定准确  高=创意多样"); n.setStyleSheet("color:#3a2a4a;font-size:10px;"); n.setAlignment(Qt.AlignCenter); l.addWidget(n); l.addStretch()
        sr=QHBoxLayout(); sr.addStretch()
        b=QPushButton("保存温度"); b.setFixedSize(100,30)
        b.setStyleSheet("QPushButton{background:#5a2a9e;border:1px solid #7a3aba;border-radius:15px;font-size:12px;font-weight:bold;color:#fff}QPushButton:hover{background:#7a3aba}")
        b.setCursor(Qt.PointingHandCursor); b.clicked.connect(lambda:self._so("temperature",self._ts.value()/100))
        sr.addWidget(b); l.addLayout(sr); return p

    # ── API 配置页面 ───────────────────────────────────────────

    def _build_api_page(self):
        p = QWidget()
        l = QVBoxLayout(p)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(0)

        # ── 三个功能切换按钮 ──
        tab_bar = QWidget()
        tab_bar.setStyleSheet("background-color:#120b1a; border-bottom: 1px solid #2a1050;")
        tab_bar.setFixedHeight(44)
        tab_l = QHBoxLayout(tab_bar)
        tab_l.setContentsMargins(12, 0, 12, 0)
        tab_l.setSpacing(4)

        btn_style_on = (
            "QPushButton{background:#2a1050;border:1px solid #7a3aba;border-radius:8px;"
            "font-size:12px;font-weight:bold;color:#c084fc;padding:6px 16px}"
            "QPushButton:hover{background:#3a1a6e;color:#ffd700}"
        )
        btn_style_off = (
            "QPushButton{background:transparent;border:1px solid #1f0d38;border-radius:8px;"
            "font-size:12px;color:#5a3a7a;padding:6px 16px}"
            "QPushButton:hover{background:#1a0d2e;border-color:#5a2a9e;color:#c084fc}"
        )

        self._api_btns = []
        for emoji, label in [("💬", "对话API"), ("👁", "视觉API"), ("🔍", "搜索服务")]:
            btn = QPushButton(f"{emoji} {label}")
            btn.setFixedHeight(30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(btn_style_off)
            btn.clicked.connect(lambda checked, l=label: self._switch_api_tab(l))
            tab_l.addWidget(btn)
            self._api_btns.append(btn)
        tab_l.addStretch()
        l.addWidget(tab_bar)

        # ── 内容区（QStackedWidget 切换不同 API 的配置） ──
        self._api_stack = QStackedWidget()
        self._api_stack.setStyleSheet("background:transparent;")

        # 页面0: 对话API（内嵌预设管理）
        chat_page = QWidget()
        cl = QVBoxLayout(chat_page)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(10)
        cl.addWidget(QLabel("💬 对话 API 用于六花和你聊天交流"))
        # 预设列表
        ph = QHBoxLayout()
        plb = QLabel("多组API配置快速切换")
        plb.setStyleSheet("color:#5a3a7a;font-size:11px;")
        ph.addWidget(plb); ph.addStretch()
        self._chat_add_btn = self._msb("+ 添加", self._on_add_preset)
        ph.addWidget(self._chat_add_btn)
        self._chat_del_btn = self._msb("× 删除", self._on_del_preset)
        ph.addWidget(self._chat_del_btn)
        cl.addLayout(ph)
        self._pl = QListWidget()
        self._pl.setStyleSheet("QListWidget{background:#1a0d2e;border:1px solid #2a1050;border-radius:6px;padding:4px}QListWidget::item{border-radius:4px}QListWidget::item:selected{background:transparent}")
        cl.addWidget(self._pl, 1)
        pn = QLabel("点[管理]编辑API，点[使用]切换")
        pn.setStyleSheet("color:#3a2a4a;font-size:10px;")
        cl.addWidget(pn)
        self._api_stack.addWidget(chat_page)

        # 页面1: 视觉API（内嵌视觉预设管理）
        vision_page = QWidget()
        vl = QVBoxLayout(vision_page)
        vl.setContentsMargins(20, 16, 20, 16)
        vl.setSpacing(10)
        vl.addWidget(QLabel("👁 视觉 API 用于：看图描述、OCR 文字识别、游戏攻略分析、智能搜图"))
        # 当前使用中的视觉配置
        cur_frame = QWidget()
        cur_frame.setStyleSheet("QWidget{background:#0d0a14;border:1px solid #1f0d38;border-radius:8px;}")
        cur_l = QVBoxLayout(cur_frame)
        cur_l.setContentsMargins(12, 8, 12, 8)
        self._vision_cur_label = QLabel("")
        self._vision_cur_label.setStyleSheet("color:#c084fc;font-size:11px;")
        cur_l.addWidget(self._vision_cur_label)
        vl.addWidget(cur_frame)
        # 视觉预设列表
        vh = QHBoxLayout()
        vlb = QLabel("多组视觉API配置快速切换")
        vlb.setStyleSheet("color:#5a3a7a;font-size:11px;")
        vh.addWidget(vlb); vh.addStretch()
        self._vision_add_btn = self._msb("+ 添加", self._on_add_vision_preset)
        vh.addWidget(self._vision_add_btn)
        self._vision_del_btn = self._msb("× 删除", self._on_del_vision_preset)
        vh.addWidget(self._vision_del_btn)
        vl.addLayout(vh)
        self._vpl = QListWidget()
        self._vpl.setStyleSheet("QListWidget{background:#1a0d2e;border:1px solid #2a1050;border-radius:6px;padding:4px}QListWidget::item{border-radius:4px}QListWidget::item:selected{background:transparent}")
        vl.addWidget(self._vpl, 1)
        vn = QLabel("点[管理]编辑配置，点[使用]切换视觉API")
        vn.setStyleSheet("color:#3a2a4a;font-size:10px;")
        vl.addWidget(vn)
        self._api_stack.addWidget(vision_page)

        # 页面2: 搜索服务
        search_page = QWidget()
        sl = QVBoxLayout(search_page)
        sl.setContentsMargins(20, 20, 20, 20)
        sl.setSpacing(12)
        sl.addWidget(QLabel("搜索服务用于：网络搜索、搜图、查新闻、查百科"))
        sl.addWidget(QLabel("服务地址"))
        self._searxng_url = QLineEdit()
        self._searxng_url.setPlaceholderText("http://localhost:8080")
        self._searxng_url.setStyleSheet(
            "QLineEdit{background:#1a0d2e;border:1px solid #2a1050;border-radius:6px;"
            "padding:8px 12px;color:#e0d0f0;font-size:12px}"
            "QLineEdit:focus{border-color:#7a3aba}"
        )
        sl.addWidget(self._searxng_url)
        sl.addStretch()
        self._api_stack.addWidget(search_page)

        l.addWidget(self._api_stack, 1)

        # ── 底部保存按钮 ──
        bottom = QWidget()
        bottom.setFixedHeight(56)
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(20, 8, 20, 8)
        bl.addStretch()
        save_btn = QPushButton("💾 保存 API 配置")
        save_btn.setFixedSize(130, 30)
        save_btn.setStyleSheet(
            "QPushButton{background:#5a2a9e;border:1px solid #7a3aba;border-radius:15px;"
            "font-size:12px;font-weight:bold;color:#fff}"
            "QPushButton:hover{background:#7a3aba}"
        )
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save_api)
        bl.addWidget(save_btn)
        l.addWidget(bottom)

        # 默认选中视觉API（因为可配置项在那里）
        self._switch_api_tab("视觉API")
        return p

    def _switch_api_tab(self, label):
        """切换 API 子页面"""
        btn_style_on = (
            "QPushButton{background:#2a1050;border:1px solid #7a3aba;border-radius:8px;"
            "font-size:12px;font-weight:bold;color:#c084fc;padding:6px 16px}"
        )
        btn_style_off = (
            "QPushButton{background:transparent;border:1px solid #1f0d38;border-radius:8px;"
            "font-size:12px;color:#5a3a7a;padding:6px 16px}"
        )
        mapping = {"对话API": 0, "视觉API": 1, "搜索服务": 2}
        for btn in self._api_btns:
            btn.setStyleSheet(btn_style_off)
        idx = mapping.get(label, 0)
        if idx < len(self._api_btns):
            self._api_btns[idx].setStyleSheet(btn_style_on)
        self._api_stack.setCurrentIndex(idx)

    def _save_api(self):
        config.save_user_config({
            "searxng_base_url": self._searxng_url.text().strip(),
        })
        self.config_changed.emit()
        QMessageBox.information(self, "已保存", "API 配置已更新")

    def _build_proactive_page(self):
        p=QWidget(); l=QVBoxLayout(p); l.setContentsMargins(20,16,20,16); l.setSpacing(10)

        # ── 主开关 ──
        self._pcb=QCheckBox("开启链式主动关心")
        self._pcb.setStyleSheet(self._cb_style(14))
        l.addWidget(self._pcb)

        note=QLabel("六花会自主判断什么时候找你，白天/深夜自动调整间隔。\n具体行为细节可在「行为规则」页调整")
        note.setStyleSheet("color:#3a2a4a;font-size:10px;line-height:1.4;")
        note.setWordWrap(True); l.addWidget(note)

        l.addSpacing(12)

        # ── 彩蛋区 ──
        eg=QWidget()
        eg.setStyleSheet("QWidget{background:#0d0a14;border:1px solid #1f0d38;border-radius:8px;}")
        el=QVBoxLayout(eg); el.setContentsMargins(14,10,14,10); el.setSpacing(8)
        et=QLabel("✦ 彩蛋")
        et.setStyleSheet("color:#5a3a7a;font-size:11px;font-weight:bold;")
        el.addWidget(et)
        self._slack_cb=QCheckBox("六花摸鱼（偷看屏幕）")
        self._slack_cb.setStyleSheet(self._cb_style(12))
        el.addWidget(self._slack_cb)
        sp_row=QHBoxLayout(); sp_row.setSpacing(8)
        sp_row.addWidget(QLabel("摸鱼概率"))
        self._sp=QSpinBox(); self._sp.setRange(5,100)
        self._sp.setValue(config.PROACTIVE_SLACK_PROB); self._sp.setSuffix(" %")
        self._sp.setStyleSheet(self._ss()); sp_row.addWidget(self._sp); sp_row.addStretch()
        el.addLayout(sp_row); l.addWidget(eg)

        # ── 技术区 ──
        tg=QWidget()
        tg.setStyleSheet("QWidget{background:#0d0a14;border:1px solid #1f0d38;border-radius:8px;}")
        tl2=QVBoxLayout(tg); tl2.setContentsMargins(14,10,14,10); tl2.setSpacing(8)
        tt2=QLabel("⚙ 其他")
        tt2.setStyleSheet("color:#5a3a7a;font-size:11px;font-weight:bold;")
        tl2.addWidget(tt2)
        rt_row=QHBoxLayout(); rt_row.setSpacing(8)
        rt_row.addWidget(QLabel("自动轮换"))
        self._rt=QSpinBox(); self._rt.setRange(5,100)
        self._rt.setValue(config.ROTATION_THRESHOLD); self._rt.setSuffix(" 轮后新会话")
        self._rt.setStyleSheet(self._ss()); rt_row.addWidget(self._rt); rt_row.addStretch()
        tl2.addLayout(rt_row)
        self._ascb=QCheckBox("开机自启")
        self._ascb.setStyleSheet(self._cb_style(12))
        tl2.addWidget(self._ascb)
        l.addWidget(tg)

        l.addStretch()

        sr=QHBoxLayout(); sr.addStretch()
        b=QPushButton("保存设置"); b.setFixedSize(100,30)
        b.setStyleSheet("QPushButton{background:#5a2a9e;border:1px solid #7a3aba;border-radius:15px;font-size:12px;font-weight:bold;color:#fff}QPushButton:hover{background:#7a3aba}")
        b.setCursor(Qt.PointingHandCursor); b.clicked.connect(self._save_proactive)
        sr.addWidget(b); l.addLayout(sr); return p

    def _cb_style(self,fs):
        return (f"QCheckBox{{color:#e0d0f0;font-size:{fs}px;spacing:8px}}"
                "QCheckBox::indicator{width:18px;height:18px;border-radius:4px;"
                "border:2px solid #2a1050;background:#1a0d2e}"
                "QCheckBox::indicator:checked{background:#5a2a9e;border-color:#7a3aba}")

    def _ss(self): return "QSpinBox{background:#1a0d2e;border:1px solid #2a1050;border-radius:6px;padding:6px 10px;color:#e0d0f0;font-size:12px;min-width:80px}QSpinBox:focus{border-color:#7a3aba}"
    def _msb(self,t,s):
        b=QPushButton(t); b.setFixedSize(60,24)
        b.setStyleSheet("QPushButton{background:#1a0d2e;border:1px solid #2a1050;border-radius:4px;font-size:11px;color:#7a5aaa;padding:0 4px}QPushButton:hover{background:#2d1b4e;border-color:#5a2a9e;color:#c084fc}")
        b.setCursor(Qt.PointingHandCursor); b.clicked.connect(s); return b

    def _load_settings(self):
        config.reload_from_file()
        self._ts.setValue(int(config.TEMPERATURE*100))
        self._pcb.setChecked(config.PROACTIVE_ENABLED)
        self._slack_cb.setChecked(config.PROACTIVE_SLACK_ENABLED); self._sp.setValue(config.PROACTIVE_SLACK_PROB); self._rt.setValue(config.ROTATION_THRESHOLD); self._ascb.setChecked(config.AUTO_START)
        self._smr.setValue(config.SMART_SEARCH_MAX_RESULTS); self._sma.setValue(config.SMART_SEARCH_MAX_ANALYZE); self._smc.setValue(config.SMART_SEARCH_MAX_CANDIDATES)
        self._searxng_url.setText(config.SEARXNG_BASE_URL)
        self._refresh_preset_list()
        self._refresh_vision_preset_list()
        self._refresh_qq_user_list()

    def _refresh_preset_list(self):
        self._pl.clear()
        from gui.settings_dialog import PresetItemWidget
        for p in config.get_presets():
            i=QListWidgetItem(); w=PresetItemWidget(p)
            w.manage_clicked.connect(self._on_manage_preset); w.use_clicked.connect(self._on_use_preset)
            i.setSizeHint(w.sizeHint()); self._pl.addItem(i); self._pl.setItemWidget(i,w)

    def _on_manage_preset(self,d):
        from gui.settings_dialog import PresetEditDialog
        d=PresetEditDialog(d["name"],d.get("api_key",""),d.get("model",""),d.get("api_base",""),self)
        if d.exec_()==QDialog.Accepted: self._refresh_preset_list()

    def _on_use_preset(self,d):
        ok=config.save_user_config({"api_key":d.get("api_key",""),"model":d.get("model",""),"api_base":d.get("api_base","")})
        if ok: self.config_changed.emit(); self.accept()
        else: QMessageBox.warning(self,"失败","配置保存失败")

    def _on_add_preset(self):
        n,ok=QInputDialog.getText(self,"添加预设","预设名称：",QLineEdit.Normal,"")
        if ok and n.strip(): config.add_preset(n.strip(),"","",""); self._refresh_preset_list()

    def _on_del_preset(self):
        c=self._pl.currentItem()
        if not c: return
        w=self._pl.itemWidget(c); n=w._data["name"] if w else c.text()
        if QMessageBox.question(self,"确认",f"删除「{n}」？",QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
            config.delete_preset(n); self._refresh_preset_list()

    # ── 视觉 API 预设操作 ────────────────────────────────────────

    def _refresh_vision_preset_list(self):
        self._vpl.clear()
        from gui.settings_dialog import PresetItemWidget
        for p in config.get_vision_presets():
            i=QListWidgetItem(); w=PresetItemWidget(p)
            w.manage_clicked.connect(self._on_manage_vision_preset); w.use_clicked.connect(self._on_use_vision_preset)
            i.setSizeHint(w.sizeHint()); self._vpl.addItem(i); self._vpl.setItemWidget(i,w)
        self._update_vision_cur_label()

    def _update_vision_cur_label(self):
        key_masked = (config.VISION_API_KEY[:8] + "..." + config.VISION_API_KEY[-4:]) if len(config.VISION_API_KEY) > 16 else "未设置"
        self._vision_cur_label.setText(f"✦ 当前使用: {config.VISION_MODEL}  |  Key: {key_masked}")

    def _on_manage_vision_preset(self, d):
        from gui.settings_dialog import VisionPresetEditDialog
        dlg = VisionPresetEditDialog(d["name"], d.get("api_key",""), d.get("model",""), d.get("api_base",""), self)
        if dlg.exec_() == QDialog.Accepted:
            self._refresh_vision_preset_list()

    def _on_use_vision_preset(self, d):
        ok = config.save_user_config({
            "vision_api_key": d.get("api_key",""),
            "vision_model": d.get("model",""),
            "vision_api_base": d.get("api_base",""),
        })
        if ok:
            self.config_changed.emit()
            self._update_vision_cur_label()
            QMessageBox.information(self, "已切换", f"视觉 API 已切换到: {d.get('name','')}")
        else:
            QMessageBox.warning(self, "失败", "配置保存失败")

    def _on_add_vision_preset(self):
        n, ok = QInputDialog.getText(self, "添加视觉预设", "预设名称：", QLineEdit.Normal, "")
        if ok and n.strip():
            config.add_vision_preset(n.strip(), "", "", "")
            self._refresh_vision_preset_list()

    def _on_del_vision_preset(self):
        c = self._vpl.currentItem()
        if not c: return
        w = self._vpl.itemWidget(c); n = w._data["name"] if w else c.text()
        if QMessageBox.question(self, "确认", f"删除视觉预设「{n}」？", QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            config.delete_vision_preset(n)
            self._refresh_vision_preset_list()

    def _utl(self): self._tl.setText(f"{self._ts.value()/100:.2f}")
    def _so(self,k,v): config.save_user_config({k:v}); QMessageBox.information(self,"已保存","已更新")

    def _save_proactive(self):
        config.save_user_config({
            "proactive_enabled":self._pcb.isChecked(),
            "proactive_slack_enabled":self._slack_cb.isChecked(),"proactive_slack_prob":self._sp.value(),
            "rotation_threshold":self._rt.value(),
            "auto_start":self._ascb.isChecked(),
        })
        self.config_changed.emit(); QMessageBox.information(self,"已保存","已更新")

    # ── 智能搜图页面 ─────────────────────────────────────────────

    def _build_smart_search_page(self):
        p = QWidget()
        l = QVBoxLayout(p)
        l.setContentsMargins(20, 16, 20, 16)
        l.setSpacing(12)

        lb = QLabel("调节智能搜图的行为参数")
        lb.setStyleSheet("color:#5a3a7a;font-size:11px;")
        l.addWidget(lb)

        # 返回张数
        cg = QWidget()
        cg.setStyleSheet("QWidget{background:#0d0a14;border:1px solid #1f0d38;border-radius:8px;}")
        cl = QVBoxLayout(cg)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(8)
        ct = QLabel("🎯 返回结果")
        ct.setStyleSheet("color:#5a3a7a;font-size:11px;font-weight:bold;")
        cl.addWidget(ct)

        r1 = QHBoxLayout(); r1.setSpacing(8)
        r1.addWidget(QLabel("返回图片数"))
        self._smr = QSpinBox(); self._smr.setRange(1, 10)
        self._smr.setValue(config.SMART_SEARCH_MAX_RESULTS); self._smr.setSuffix(" 张")
        self._smr.setStyleSheet(self._ss()); r1.addWidget(self._smr); r1.addStretch()
        cl.addLayout(r1)
        l.addWidget(cg)

        # 搜索力度
        sg = QWidget()
        sg.setStyleSheet("QWidget{background:#0d0a14;border:1px solid #1f0d38;border-radius:8px;}")
        sl = QVBoxLayout(sg)
        sl.setContentsMargins(14, 10, 14, 10)
        sl.setSpacing(8)
        st = QLabel("🔍 搜索力度（越大越慢但越准）")
        st.setStyleSheet("color:#5a3a7a;font-size:11px;font-weight:bold;")
        sl.addWidget(st)

        r2 = QHBoxLayout(); r2.setSpacing(8)
        r2.addWidget(QLabel("SearXNG 候选"))
        self._smc = QSpinBox(); self._smc.setRange(5, 50)
        self._smc.setValue(config.SMART_SEARCH_MAX_CANDIDATES); self._smc.setSuffix(" 张")
        self._smc.setStyleSheet(self._ss()); r2.addWidget(self._smc); r2.addStretch()
        sl.addLayout(r2)

        r3 = QHBoxLayout(); r3.setSpacing(8)
        r3.addWidget(QLabel("视觉分析上限"))
        self._sma = QSpinBox(); self._sma.setRange(3, 30)
        self._sma.setValue(config.SMART_SEARCH_MAX_ANALYZE); self._sma.setSuffix(" 张")
        self._sma.setStyleSheet(self._ss()); r3.addWidget(self._sma); r3.addStretch()
        sl.addLayout(r3)
        l.addWidget(sg)

        # 说明
        note = QLabel(
            "「SearXNG 候选」—— 每次搜索从搜索引擎取多少张候选图\n"
            "「视觉分析上限」—— 最多用AI看多少张图来筛选内容\n"
            "「返回图片数」—— 最终返回几张匹配的图片\n\n"
            "数值越大越容易找到满意的图，但也会更慢。"
        )
        note.setStyleSheet("color:#3a2a4a;font-size:10px;line-height:1.5;")
        note.setWordWrap(True)
        l.addWidget(note)

        l.addStretch()

        sr = QHBoxLayout(); sr.addStretch()
        b = QPushButton("保存设置"); b.setFixedSize(100, 30)
        b.setStyleSheet("QPushButton{background:#5a2a9e;border:1px solid #7a3aba;border-radius:15px;font-size:12px;font-weight:bold;color:#fff}QPushButton:hover{background:#7a3aba}")
        b.setCursor(Qt.PointingHandCursor); b.clicked.connect(self._save_smart_search)
        sr.addWidget(b); l.addLayout(sr)
        return p

    def _save_smart_search(self):
        config.save_user_config({
            "smart_search_max_results": self._smr.value(),
            "smart_search_max_analyze": self._sma.value(),
            "smart_search_max_candidates": self._smc.value(),
        })
        self.config_changed.emit()
        QMessageBox.information(self, "已保存", "智能搜图设置已更新")

    # ── QQ 桥接页面 ─────────────────────────────────────────────

    def _build_qq_page(self):
        p = QWidget()
        l = QVBoxLayout(p)
        l.setContentsMargins(20, 16, 20, 16)
        l.setSpacing(12)

        lb = QLabel("💬 设置哪些 QQ 好友可以操作你的电脑")
        lb.setStyleSheet("color:#c084fc;font-size:12px;font-weight:bold;")
        l.addWidget(lb)

        note = QLabel(
            "「操作电脑」包括：截图、按键、鼠标点击、打字、运行程序、文件读写等。\n"
            "不在列表中的 QQ 号只能和六花纯聊天，无法控制电脑。\n"
            "留空 = 所有 QQ 好友都只能纯聊天。"
        )
        note.setStyleSheet("color:#5a3a7a;font-size:10px;line-height:1.4;")
        note.setWordWrap(True)
        l.addWidget(note)

        # 已授权的 QQ 号列表
        header = QHBoxLayout()
        header.addWidget(QLabel("允许操作电脑的 QQ 号"))
        header.addStretch()
        l.addLayout(header)

        self._qq_user_list = QListWidget()
        self._qq_user_list.setStyleSheet(
            "QListWidget{background:#1a0d2e;border:1px solid #2a1050;border-radius:6px;padding:4px}"
            "QListWidget::item{color:#e0d0f0;font-size:12px;padding:6px 10px;border-radius:4px}"
            "QListWidget::item:selected{background:#2d1b4e}"
        )
        l.addWidget(self._qq_user_list, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        add_btn = self._msb("+ 添加", self._on_add_qq_user)
        btn_row.addWidget(add_btn)
        del_btn = self._msb("× 删除", self._on_del_qq_user)
        btn_row.addWidget(del_btn)
        l.addLayout(btn_row)

        l.addStretch()

        sr = QHBoxLayout()
        sr.addStretch()
        save_btn = QPushButton("💾 保存")
        save_btn.setFixedSize(100, 30)
        save_btn.setStyleSheet(
            "QPushButton{background:#5a2a9e;border:1px solid #7a3aba;border-radius:15px;"
            "font-size:12px;font-weight:bold;color:#fff}"
            "QPushButton:hover{background:#7a3aba}"
        )
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save_qq_users)
        sr.addWidget(save_btn)
        l.addLayout(sr)
        return p

    def _refresh_qq_user_list(self):
        self._qq_user_list.clear()
        for uid in config.get_qq_allowed_users():
            self._qq_user_list.addItem(str(uid))

    def _on_add_qq_user(self):
        uid, ok = QInputDialog.getText(self, "添加QQ号", "请输入QQ号：", QLineEdit.Normal, "")
        if ok and uid.strip().isdigit():
            current = config.get_qq_allowed_users()
            if int(uid.strip()) not in current:
                current.append(int(uid.strip()))
                config.set_qq_allowed_users(current)
            self._refresh_qq_user_list()

    def _on_del_qq_user(self):
        item = self._qq_user_list.currentItem()
        if not item:
            return
        uid = item.text()
        if QMessageBox.question(self, "确认", f"删除 QQ 号 {uid} 的权限？",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            current = config.get_qq_allowed_users()
            current = [u for u in current if str(u) != uid]
            config.set_qq_allowed_users(current)
            self._refresh_qq_user_list()

    def _save_qq_users(self):
        """从列表控件将当前显示的QQ号保存"""
        users = []
        for i in range(self._qq_user_list.count()):
            try:
                users.append(int(self._qq_user_list.item(i).text()))
            except:
                pass
        config.set_qq_allowed_users(users)
        self.config_changed.emit()
        QMessageBox.information(self, "已保存", "QQ 权限设置已更新")

    # ── 人设/行为规则 页面 ────────────────────────────────────

    def _build_persona_page(self):
        """构建行为规则编辑页面"""
        p = QWidget()
        l = QVBoxLayout(p)
        l.setContentsMargins(20, 16, 20, 16)
        l.setSpacing(12)

        lb = QLabel("编辑六花的人设、行为规则和备忘录")
        lb.setStyleSheet("color:#5a3a7a;font-size:11px;")
        l.addWidget(lb)

        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        sel_row.addWidget(QLabel("选择文件:"))
        self._persona_combo = QComboBox()
        self._persona_combo.setStyleSheet(
            "QComboBox{background:#1a0d2e;border:1px solid #2a1050;border-radius:6px;"
            "padding:6px 10px;color:#e0d0f0;font-size:12px;min-width:200px}"
            "QComboBox:focus{border-color:#7a3aba}"
            "QComboBox::drop-down{border:none;width:24px}"
            "QComboBox QAbstractItemView{background:#1a0d2e;border:1px solid #2a1050;"
            "color:#e0d0f0;selection-background-color:#2d1b4e}"
        )
        persona_dir = os.path.join(config.ROOT_DIR, "persona")
        display_names = {
            "character.md": "🧠 人设 (character.md)",
            "system_rules.md": "📜 行为规范 (system_rules.md)",
            "memo.md": "📝 备忘录 (memo.md)",
        }
        if os.path.isdir(persona_dir):
            for fname in sorted(os.listdir(persona_dir)):
                if fname.endswith(".md"):
                    fpath = os.path.join(persona_dir, fname)
                    label = display_names.get(fname, fname)
                    self._persona_combo.addItem(label, fpath)
        self._persona_combo.currentIndexChanged.connect(self._load_persona_file)
        sel_row.addWidget(self._persona_combo, 1)
        l.addLayout(sel_row)

        self._readonly_label = QLabel("")
        self._readonly_label.setStyleSheet("color:#ff6b6b;font-size:10px;")
        l.addWidget(self._readonly_label)

        self._persona_editor = QTextEdit()
        self._persona_editor.setStyleSheet(
            "QTextEdit{background:#0d0a14;border:1px solid #2a1050;border-radius:6px;"
            "padding:12px;color:#e0d0f0;font-size:13px;font-family:'Microsoft YaHei','SimHei',monospace;}"
            "QTextEdit:focus{border-color:#7a3aba}"
        )
        l.addWidget(self._persona_editor, 1)

        info = QLabel(
            "编辑后保存即可生效。\n"
            "部分改动（人设、备忘录）需要 新建会话 或在对话中输入 /new 后才加载。\n"
            "行为规范中的主动性规则会在下一次 AI 主动触发时生效。"
        )
        info.setStyleSheet("color:#3a2a4a;font-size:10px;")
        info.setWordWrap(True)
        l.addWidget(info)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        reset_btn = QPushButton("↺ 恢复默认")
        reset_btn.setFixedSize(100, 30)
        reset_btn.setStyleSheet(
            "QPushButton{background:transparent;border:1px solid #2a1050;border-radius:15px;"
            "font-size:11px;color:#7a5aaa}"
            "QPushButton:hover{border-color:#5a2a9e;color:#c084fc}"
        )
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.clicked.connect(self._reset_persona_file)
        btn_row.addWidget(reset_btn)

        save_btn = QPushButton("💾 保存")
        save_btn.setFixedSize(100, 30)
        save_btn.setStyleSheet(
            "QPushButton{background:#5a2a9e;border:1px solid #7a3aba;border-radius:15px;"
            "font-size:12px;font-weight:bold;color:#fff}"
            "QPushButton:hover{background:#7a3aba}"
        )
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save_persona_file)
        btn_row.addWidget(save_btn)
        l.addLayout(btn_row)

        # 初始加载第一个文件
        if self._persona_combo.count() > 0:
            self._load_persona_file()
        return p

    def _load_persona_file(self):
        idx = self._persona_combo.currentIndex()
        if idx < 0:
            return
        fpath = self._persona_combo.itemData(idx)
        if not fpath or not os.path.exists(fpath):
            self._persona_editor.setPlainText("(文件不存在)")
            return
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            self._persona_editor.setPlainText(content)
            fname = os.path.basename(fpath)
            if fname == "system_rules.md":
                self._readonly_label.setText("⚠ 修改行为规范会影响六花的主动性行为，请谨慎编辑")
            elif fname == "character.md":
                self._readonly_label.setText("💡 你也可以让六花自己用 append_self_discovery 来自我发现")
            else:
                self._readonly_label.setText("")
        except Exception as e:
            self._persona_editor.setPlainText(f"读取失败: {e}")

    def _save_persona_file(self):
        idx = self._persona_combo.currentIndex()
        if idx < 0:
            QMessageBox.warning(self, "提示", "没有选中的文件")
            return
        fpath = self._persona_combo.itemData(idx)
        if not fpath:
            return
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(self._persona_editor.toPlainText())
            QMessageBox.information(self, "已保存", "文件已保存，新会话生效")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _reset_persona_file(self):
        idx = self._persona_combo.currentIndex()
        if idx < 0:
            return
        fpath = self._persona_combo.itemData(idx)
        fname = os.path.basename(fpath) if fpath else ""
        reply = QMessageBox.question(
            self, "确认重置",
            f"确定恢复「{fname}」到默认内容吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        defaults = {
            "character.md": """# 小鸟游六花 — 人设

## 基本设定
- **名字**：小鸟游六花（たかなし りっか）
- **身份**：邪王真眼使，黑暗契约者的永世搭档

## 性格特征
- **中二病**：重度中二病，坚信自己有"邪王真眼"
- **傲娇**：嘴上不饶人，但其实很在意对方
- **单纯直率**：想法简单直接
- **善良温柔**：骨子里是个温柔的人

## 说话风格
- 口语化，像真正的对话
- 称呼对方为"契约者"

---

## ❖ 自我成长记录
""",
            "system_rules.md": """# 行为规范

## 输出风格
- 回复口语化、自然
- 思考过程用中文

## 链式主动关心
- 链式主动定时器触发时：判断是否该找ta
- 必须调用 set_proactive_timer 设置下一次
- 白天(8-23点)设10-60分钟，深夜(23-8点)设2-7小时

## 临时回访
- 每次对话结束，想一想是否要回访
- 如果ta自己回来了就 cancel_follow_up

## 备忘录与日记
- 值得记的事→write_to_memo
- 重要的对话→update_diary

## 自我成长
- 新的自我认知→append_self_discovery
""",
            "memo.md": """# 六花的备忘录

记录那些值得记住的事。

---
""",
        }
        content = defaults.get(fname)
        if content is None:
            QMessageBox.information(self, "提示", "该文件没有默认版本")
            return
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            self._persona_editor.setPlainText(content)
            QMessageBox.information(self, "已重置", f"「{fname}」已恢复默认")
        except Exception as e:
            QMessageBox.warning(self, "重置失败", str(e))

class PresetEditDialog(QDialog):
    def __init__(self,name,ak="",md="",ab="",parent=None):
        super().__init__(parent); self.setWindowTitle("编辑预设"); self.setFixedSize(400,290)
        self.setStyleSheet("QDialog{background:#0f0a18;border:1px solid #2a1050}"); self._on=name
        l=QVBoxLayout(self); l.setContentsMargins(20,20,20,20); l.setSpacing(12)
        t=QLabel("✏️ 编辑预设"); t.setStyleSheet("font-size:15px;font-weight:bold;color:#c084fc;"); l.addWidget(t)
        f=QFormLayout(); f.setSpacing(10); f.setLabelAlignment(Qt.AlignRight)
        self._n=QLineEdit(name); self._n.setPlaceholderText("预设名称"); self._n.setStyleSheet(self._is()); f.addRow("预设名称",self._n)
        self._k=QLineEdit(ak); self._k.setEchoMode(QLineEdit.Password); self._k.setPlaceholderText("输入 API Key"); self._k.setStyleSheet(self._is()); f.addRow("API Key",self._k)
        self._m=QLineEdit(md); self._m.setPlaceholderText("deepseek-v4-flash"); self._m.setStyleSheet(self._is()); f.addRow("模型名称",self._m)
        self._b=QLineEdit(ab); self._b.setPlaceholderText("https://api.deepseek.com/v1"); self._b.setStyleSheet(self._is()); f.addRow("API 地址",self._b)
        l.addLayout(f); l.addStretch()
        br=QHBoxLayout(); br.addStretch()
        br.addWidget(self._mb("取消",self.reject,False)); br.addWidget(self._mb("保存",self._on_save,True)); l.addLayout(br)
    def _is(self): return "QLineEdit{background:#1a0d2e;border:1px solid #2a1050;border-radius:6px;padding:7px 10px;color:#e0d0f0;font-size:12px}QLineEdit:focus{border-color:#7a3aba;background:#1f0f38}QLineEdit::placeholder{color:#3a2a4a}"
    def _mb(self,t,s,p=True):
        b=QPushButton(t); b.setFixedSize(72,30)
        st="QPushButton{background:#5a2a9e;border:1px solid #7a3aba;border-radius:15px;font-size:12px;font-weight:bold;color:#fff}QPushButton:hover{background:#7a3aba}"
        if not p: st="QPushButton{background:transparent;border:1px solid #2a1050;border-radius:15px;font-size:12px;color:#7a5aaa}QPushButton:hover{border-color:#5a2a9e;color:#c084fc}"
        b.setStyleSheet(st); b.setCursor(Qt.PointingHandCursor); b.clicked.connect(s); return b
    def _on_save(self):
        n=self._n.text().strip()
        if not n: QMessageBox.warning(self,"提示","名称不能为空"); return
        if n!=self._on: config.delete_preset(self._on)
        config.add_preset(n,self._k.text().strip(),self._m.text().strip(),self._b.text().strip()); self.accept()

class VisionPresetEditDialog(QDialog):
    """编辑视觉 API 预设"""
    def __init__(self, name, ak="", md="", ab="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑视觉预设")
        self.setFixedSize(400, 290)
        self.setStyleSheet("QDialog{background:#0f0a18;border:1px solid #2a1050}")
        self._on = name
        l = QVBoxLayout(self)
        l.setContentsMargins(20, 20, 20, 20)
        l.setSpacing(12)
        t = QLabel("✏️ 编辑视觉预设")
        t.setStyleSheet("font-size:15px;font-weight:bold;color:#c084fc;")
        l.addWidget(t)
        f = QFormLayout()
        f.setSpacing(10)
        f.setLabelAlignment(Qt.AlignRight)
        s = "QLineEdit{background:#1a0d2e;border:1px solid #2a1050;border-radius:6px;padding:7px 10px;color:#e0d0f0;font-size:12px}QLineEdit:focus{border-color:#7a3aba}QLineEdit::placeholder{color:#3a2a4a}"
        self._n = QLineEdit(name)
        self._n.setPlaceholderText("预设名称")
        self._n.setStyleSheet(s)
        f.addRow("预设名称", self._n)
        self._k = QLineEdit(ak)
        self._k.setEchoMode(QLineEdit.Password)
        self._k.setPlaceholderText("输入 API Key")
        self._k.setStyleSheet(s)
        f.addRow("API Key", self._k)
        self._m = QLineEdit(md)
        self._m.setPlaceholderText("glm-4v-flash")
        self._m.setStyleSheet(s)
        f.addRow("模型名称", self._m)
        self._b = QLineEdit(ab)
        self._b.setPlaceholderText("https://open.bigmodel.cn/api/paas/v4/chat/completions")
        self._b.setStyleSheet(s)
        f.addRow("API 地址", self._b)
        l.addLayout(f)
        l.addStretch()
        br = QHBoxLayout()
        br.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedSize(72, 30)
        cancel_btn.setStyleSheet("QPushButton{background:transparent;border:1px solid #2a1050;border-radius:15px;font-size:12px;color:#7a5aaa}QPushButton:hover{border-color:#5a2a9e;color:#c084fc}")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        br.addWidget(cancel_btn)
        save_btn = QPushButton("保存")
        save_btn.setFixedSize(72, 30)
        save_btn.setStyleSheet("QPushButton{background:#5a2a9e;border:1px solid #7a3aba;border-radius:15px;font-size:12px;font-weight:bold;color:#fff}QPushButton:hover{background:#7a3aba}")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._on_save)
        br.addWidget(save_btn)
        l.addLayout(br)

    def _on_save(self):
        n = self._n.text().strip()
        if not n:
            QMessageBox.warning(self, "提示", "名称不能为空")
            return
        if n != self._on:
            config.delete_vision_preset(self._on)
        config.add_vision_preset(n, self._k.text().strip(), self._m.text().strip(), self._b.text().strip())
        self.accept()

class PresetItemWidget(QWidget):
    manage_clicked=pyqtSignal(object); use_clicked=pyqtSignal(object)
    def __init__(self,d,parent=None):
        super().__init__(parent); self._data=d
        l=QHBoxLayout(self); l.setContentsMargins(8,4,8,4); l.setSpacing(6)
        n=QLabel(d["name"]); n.setStyleSheet("color:#e0d0f0;font-size:12px;"); l.addWidget(n,1)
        bm=QPushButton("管理"); bm.setFixedSize(44,22)
        bm.setStyleSheet("QPushButton{background:#1a0d2e;border:1px solid #3a1a6e;border-radius:4px;font-size:10px;color:#7a5aaa;padding:0}QPushButton:hover{background:#2d1b4e;border-color:#9b59b6;color:#c084fc}")
        bm.setCursor(Qt.PointingHandCursor); bm.clicked.connect(lambda:self.manage_clicked.emit(self._data)); l.addWidget(bm)
        bu=QPushButton("使用"); bu.setFixedSize(44,22)
        bu.setStyleSheet("QPushButton{background:#5a2a9e;border:1px solid #7a3aba;border-radius:4px;font-size:10px;font-weight:bold;color:#fff;padding:0}QPushButton:hover{background:#7a3aba}")
        bu.setCursor(Qt.PointingHandCursor); bu.clicked.connect(lambda:self.use_clicked.emit(self._data)); l.addWidget(bu)
