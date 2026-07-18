"""
RikkaAI - 情感状态系统
追踪对话情绪，动态影响回复风格
"""
import re


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

    def analyze(self, text: str):
        """分析用户输入，更新情感状态"""
        text_lower = text.lower()

        # 计算情感分数
        score = 0
        for word in self.POSITIVE_WORDS:
            if word in text_lower:
                score += 1
        for word in self.NEGATIVE_WORDS:
            if word in text_lower:
                score -= 1.5

        # 更新好感度（缓慢变化）
        if score > 0:
            self.affection = min(100, self.affection + score * 2)
        elif score < 0:
            self.affection = max(0, self.affection + score * 3)

        # 更新情绪
        if score >= 2:
            self.mood = "happy"
            self.energy = min(100, self.energy + 5)
        elif score <= -2:
            self.mood = "sad" if score > -4 else "angry"
            self.energy = max(0, self.energy - 10)
        elif score > 0:
            if self.mood == "neutral":
                self.mood = "happy"
            self.energy = min(100, self.energy + 2)
        elif score < 0:
            self.mood = "sad"
            self.energy = max(0, self.energy - 5)
        else:
            # 中性消息，缓慢恢复
            if self.mood != "neutral":
                self._last_mood = self.mood
            self.mood = "neutral"
            self.energy = min(100, self.energy + 1)

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
