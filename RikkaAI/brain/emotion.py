"""
RikkaAI - 情感状态系统
追踪对话情绪，动态影响回复风格
"""

# 可锁定的字段：锁定的数值不会被日常互动自动更新（设置弹窗仍可手动改）
LOCKABLE_KEYS = ("mood", "emotion_energy", "affection",
                 "social", "mastery", "novelty", "rest", "loneliness")
EMOTION_LOCK_KEYS = ("mood", "emotion_energy", "affection")
NEEDS_LOCK_KEYS = ("social", "mastery", "novelty", "rest", "loneliness")


class EmotionState:
    """六花的情感状态"""

    # 情感词库（简版）
    POSITIVE_WORDS = [
        "开心", "高兴", "哈哈", "喜欢", "爱", "棒", "好", "厉害",
        "赞", "谢谢", "感谢", "太好", "nice", "不错", "优秀", "可爱",
        "嘻嘻", "嘿嘿", "wow", "哇", "真棒", "太好了", "完美",
    ]
    NEGATIVE_WORDS = [
        "难过", "伤心", "生气", "烦", "讨厌", "差", "烂", "糟糕",
        "有病", "滚", "无聊", "没意思", "烦死", "气死", "可恶",
        "郁闷", "哭了", "伤心", "失望", "垃圾",
    ]

    def __init__(self):
        # 情感维度
        self.mood = "neutral"       # 情绪: happy / neutral / sad / angry
        self.energy = 50            # 精力值 0-100
        self.affection = 30         # 好感度 0-100
        self._last_mood = "neutral"
        self.locked = set()         # 被锁定的字段（mood/emotion_energy/affection）

    def analyze(self, text: str):
        """分析用户输入，更新情感状态（锁定字段跳过对应更新）"""
        text_lower = text.lower()
        locked = getattr(self, "locked", set())

        # 计算情感分数
        score = 0
        for word in self.POSITIVE_WORDS:
            if word in text_lower:
                score += 1
        for word in self.NEGATIVE_WORDS:
            if word in text_lower:
                score -= 1.5

        # 更新好感度（缓慢变化）
        if "affection" not in locked:
            if score > 0:
                self.affection = min(100, self.affection + score * 2)
            elif score < 0:
                self.affection = max(0, self.affection + score * 3)

        # 更新精力
        if "emotion_energy" not in locked:
            if score >= 2:
                self.energy = min(100, self.energy + 5)
            elif score <= -2:
                self.energy = max(0, self.energy - 10)
            elif score > 0:
                self.energy = min(100, self.energy + 2)
            elif score < 0:
                self.energy = max(0, self.energy - 5)
            else:
                self.energy = min(100, self.energy + 1)

        # 更新情绪
        if "mood" in locked:
            return
        if score >= 2:
            self.mood = "happy"
        elif score <= -2:
            self.mood = "sad" if score > -4 else "angry"
        elif score > 0:
            if self.mood == "neutral":
                self.mood = "happy"
        elif score < 0:
            self.mood = "sad"
        else:
            # 中性消息，缓慢恢复
            if self.mood != "neutral":
                self._last_mood = self.mood
            self.mood = "neutral"

    def apply_llm_mood(self, mood=None, energy_delta=0, affection_delta=0):
        """LLM 情绪判定的落账入口（brain/emotion_llm.py 调用）。

        尊重锁定字段；delta 夹在安全范围内，防止单轮情绪被拉爆。"""
        locked = getattr(self, "locked", set())
        if mood in ("happy", "neutral", "sad", "angry") and "mood" not in locked:
            self.mood = mood
        if "emotion_energy" not in locked:
            self.energy = max(0, min(100, self.energy + max(-15, min(15, int(energy_delta or 0)))))
        if "affection" not in locked:
            self.affection = max(0, min(100, self.affection + max(-10, min(10, int(affection_delta or 0)))))

    def get_prompt_suffix(self) -> str:
        """生成情感状态文本，注入到 system prompt"""
        mood_emoji = {
            "happy": "😊",
            "neutral": "😐",
            "sad": "😢",
            "angry": "😠",
        }
        mood_desc = {
            "happy": "心情很好",
            "neutral": "心情平淡",
            "sad": "有点低落",
            "angry": "有点生气",
        }

        # 根据情感调整回复风格
        style_notes = ""
        if self.mood == "happy":
            style_notes = "你今天心情不错，回复要更活泼热情一些，多用感叹号和语气词"
        elif self.mood == "sad":
            style_notes = "你察觉到了用户的低落，回复要温柔体贴一些，适当安慰"
        elif self.mood == "angry":
            style_notes = "你感觉到用户有点情绪，回复要耐心温和，不要顶撞"

        emoji = mood_emoji.get(self.mood, "😐")
        desc = mood_desc.get(self.mood, "心情平淡")

        return (
            f"\n【当前情感】{emoji} 你{desc}，好感度{self.affection}%，精力{self.energy}%\n"
            f"【风格提示】{style_notes}"
        )

    def snapshot(self, needs=None, planner_enabled=False) -> dict:
        """Return a UI-safe read-only snapshot of the current emotional state."""
        mood_meta = {
            "happy": ("开心", "😊", "今天的心情亮晶晶的，想和契约者分享好消息。"),
            "neutral": ("平静", "😐", "情绪平稳，安静地陪在契约者身边。"),
            "sad": ("低落", "😢", "有一点低落，但仍然愿意温柔地陪伴。"),
            "angry": ("生气", "😠", "情绪有些起伏，正在努力保持耐心。"),
        }
        label, emoji, note = mood_meta.get(self.mood, mood_meta["neutral"])
        data = {
            "mood": self.mood,
            "mood_label": label,
            "mood_emoji": emoji,
            "mood_note": note,
            "emotion_energy": int(max(0, min(100, self.energy))),
            "affection": int(max(0, min(100, self.affection))),
            "needs_enabled": bool(needs is not None),
            "needs": {},
            "initiative_drive": None,
            "proactive_success_probability": None,
        }
        if needs is not None:
            data["needs"] = {
                key: int(max(0, min(100, getattr(needs, key, 0))))
                for key in ("social", "mastery", "novelty", "rest", "energy", "loneliness")
            }
            try:
                data["initiative_drive"] = round(float(needs.initiative_drive()), 3)
            except Exception:
                data["initiative_drive"] = None
            if planner_enabled:
                try:
                    from brain.planner import decide_proactive
                    data["proactive_success_probability"] = round(
                        float(decide_proactive(needs, last_proactive_min=None)["p_success"]), 3
                    )
                except Exception:
                    data["proactive_success_probability"] = None
        return data
