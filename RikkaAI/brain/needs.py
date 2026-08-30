"""
RikkaAI - 需求体系 + 精力池 + 孤独感（Phase 3）

在既有 EmotionState（心情/精力/好感度）之上，加一层 genesis 式"有机体需求"：
  社交 / 掌控 / 新奇 / 休息 四个需求，各自 0-100。
  精力池(energy) 0-100，孤独感(loneliness) 0-100。

用这些需求驱动"该不该主动找契约者"：
  - 社交需求高 + 孤独感高 → 主动意愿强
  - 精力低 / 休息需求高 / 深夜 → 主动意愿被压制
  - 新奇需求高 → 偏好去探索新话题（冲浪）

gate: features.is_enabled("emotion_needs_enabled")（关闭时退回原 EmotionState 行为）
"""
from brain import features


class NeedsState:
    """六花的需求/活力状态。与 EmotionState 解耦，可独立读写。"""

    def __init__(self):
        # 四需求 0-100
        self.social = 40      # 想跟契约者待在一起
        self.mastery = 30     # 想掌控/把事情做好
        self.novelty = 35     # 想探索新东西
        self.rest = 80        # 想休息（越高越不想动）
        # 活力/孤独
        self.energy = 50      # 精力池 0-100
        self.loneliness = 30  # 孤独感 0-100
        self.locked = set()   # 被锁定的字段（social/mastery/novelty/rest/loneliness）

    def _apply(self, attr, new_value):
        """带锁定守卫的赋值：被锁定的字段不受自动更新影响。"""
        if attr in getattr(self, "locked", set()):
            return
        setattr(self, attr, max(0, min(100, new_value)))

    # ── 交互后更新 ─────────────────────────────────────────────
    def on_user_talk(self, valence: float = 0):
        """用户主动来找六花时：社交需求被满足、孤独感下降、耗一点精力。
        valence>0 表示正面互动。"""
        self._apply("social", self.social - 6)
        self._apply("loneliness", self.loneliness - 8 - (6 if valence > 0 else 0))
        self._apply("rest", self.rest - 2)         # 被陪伴稍微提神
        self._apply("energy", self.energy - 3)     # 互动耗能
        if valence > 0:
            self._apply("mastery", self.mastery + 1)
            self._apply("novelty", self.novelty + 1)

    def on_proactive(self, delivered: bool):
        """六花主动找了一次（成/败都要耗能）。"""
        self._apply("energy", self.energy - 5)
        if delivered:
            self._apply("loneliness", self.loneliness - 5)
            self._apply("social", self.social - 4)
        else:
            self._apply("loneliness", self.loneliness + 6)  # 没被回应更孤独
        self._apply("rest", self.rest + 3)  # 折腾完想歇

    def on_surf_round(self, found: bool):
        """六花自己偷偷冲了一轮浪：耗一点精力，逛到新东西就消化新奇需求。"""
        self._apply("energy", self.energy - 2)
        self._apply("rest", self.rest + 1)   # 逛完挺放松
        if found:
            self._apply("novelty", self.novelty - 10)  # 探索欲被满足
        else:
            self._apply("novelty", self.novelty + 3)   # 没逛到新东西更无聊了

    def tick(self, hours: float = 1.0):
        """时间流逝：需求自然演变。"""
        self._apply("rest", self.rest + 3 * hours)
        self._apply("novelty", self.novelty + 2 * hours)   # 越久越无聊/想新鲜
        self._apply("social", self.social + 3 * hours)     # 越久越想人
        self._apply("loneliness", self.loneliness + 4 * hours)
        # 休息足够会回精力
        if self.rest >= 60:
            self._apply("energy", self.energy + 2 * hours)

    # ── 主动意愿（驱动 decision planner）─────────────────────────
    def initiative_drive(self) -> float:
        """[0,1] 六花现在有多想主动找契约者。
        免打扰时段/精力低/想休息时压制；孤独、社交需求高时抬升。"""
        import datetime as _dt
        import config as _cfg
        hour = _dt.datetime.now().hour
        late = 1.0 if _cfg.in_dnd(hour) else 0.0
        base = 0.5
        drive = base
        drive += (self.social - 40) / 120.0          # 社交越高越想
        drive += (self.loneliness - 30) / 120.0      # 越孤独越想
        drive -= (self.rest - 60) / 150.0            # 越累越想歇
        drive -= (100 - self.energy) / 300.0         # 精力低减小
        drive -= late * 0.25                          # 深夜压制
        return max(0.0, min(1.0, drive))

    def wants_novelty(self) -> bool:
        """新奇需求高 → 倾向去探索新话题（冲浪）。"""
        return self.novelty >= 55 and self.energy >= 30

    def prompt_suffix(self) -> str:
        """注入 prompt 的需求说明。关闭时返回空串（不改变现有行为）。"""
        if not features.is_enabled("emotion_needs_enabled"):
            return ""
        def _bar(v):
            n = int(round(v / 10))
            return "▇" * n + "░" * (10 - n)
        return (
            f"\n【需求与本体】社交{self.social:>3} 掌控{self.mastery:>3} "
            f"新奇{self.novelty:>3} 休息{self.rest:>3} ｜ 精力{self.energy:>3} 孤独{self.loneliness:>3}\n"
            f"  · 社交 {_bar(self.social)}  掌控 {_bar(self.mastery)}  新奇 {_bar(self.novelty)}  休息 {_bar(self.rest)}"
        )
