"""
RikkaAI - Procedural Memory（程序性记忆）

存储"如何做某事"的步骤模板，类似 SOP 或技能库。
这是 RikkaAI 与 2026 最佳实践（Mem0/Letta/LangMem）的最大缺口。

核心思想：
- 存储成功完成任务的步骤序列
- Agent 遇到类似任务时检索模板
- 根据执行结果更新置信度（强化学习思想）
"""
import sqlite3
import json
import os
from typing import List, Dict, Optional


class ProceduralMemory:
    """程序性记忆管理"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            import config as cfg
            db_path = os.path.join(cfg.USER_CONFIG_DIR, "rikkai.db")

        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self):
        """创建 procedural_memory 表"""
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS procedural_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                trigger_pattern TEXT,
                steps TEXT NOT NULL,
                success_count INTEGER DEFAULT 0,
                total_count INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0.5,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_used TEXT
            )
        """)
        self._db.commit()

    def save_procedure(self, task_type: str, steps: List[Dict],
                      trigger_pattern: str = None) -> int:
        """保存一个步骤模板

        Args:
            task_type: 任务类型（如 "搜索网页"）
            steps: 步骤列表 [{"step": 1, "action": "调用 web_search", "tool": "web_search"}]
            trigger_pattern: 触发条件（可选）

        Returns:
            procedure_id
        """
        cursor = self._db.execute(
            """INSERT INTO procedural_memory
               (task_type, trigger_pattern, steps, confidence)
               VALUES (?, ?, ?, 0.5)""",
            (task_type, trigger_pattern, json.dumps(steps, ensure_ascii=False))
        )
        self._db.commit()
        return cursor.lastrowid

    def get_procedure(self, task_type: str) -> Optional[Dict]:
        """获取置信度最高的步骤模板"""
        row = self._db.execute(
            """SELECT * FROM procedural_memory
               WHERE task_type = ?
               ORDER BY confidence DESC, success_count DESC
               LIMIT 1""",
            (task_type,)
        ).fetchone()

        if not row:
            return None

        return {
            "id": row["id"],
            "task_type": row["task_type"],
            "steps": json.loads(row["steps"]),
            "confidence": row["confidence"],
            "success_count": row["success_count"],
            "total_count": row["total_count"],
        }

    def search_procedures(self, query: str, top_k=3) -> List[Dict]:
        """模糊搜索步骤模板"""
        rows = self._db.execute(
            """SELECT * FROM procedural_memory
               WHERE task_type LIKE ? OR trigger_pattern LIKE ?
               ORDER BY confidence DESC
               LIMIT ?""",
            (f"%{query}%", f"%{query}%", top_k)
        ).fetchall()

        return [
            {
                "id": r["id"],
                "task_type": r["task_type"],
                "steps": json.loads(r["steps"]),
                "confidence": r["confidence"],
            }
            for r in rows
        ]

    def record_execution(self, procedure_id: int, success: bool):
        """记录执行结果，更新置信度"""
        self._db.execute(
            """UPDATE procedural_memory
               SET success_count = success_count + ?,
                   total_count = total_count + 1,
                   confidence = CAST(success_count + ? AS REAL) / (total_count + 1),
                   last_used = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (1 if success else 0, 1 if success else 0, procedure_id)
        )
        self._db.commit()

    def list_all(self) -> List[Dict]:
        """列出所有步骤模板"""
        rows = self._db.execute(
            """SELECT * FROM procedural_memory
               ORDER BY confidence DESC, success_count DESC"""
        ).fetchall()

        return [
            {
                "id": r["id"],
                "task_type": r["task_type"],
                "trigger_pattern": r["trigger_pattern"],
                "steps": json.loads(r["steps"]),
                "confidence": r["confidence"],
                "success_count": r["success_count"],
                "total_count": r["total_count"],
            }
            for r in rows
        ]


def seed_default_procedures():
    """初始化常见任务模板"""
    pm = ProceduralMemory()

    # 检查是否已初始化
    existing = pm.list_all()
    if existing:
        print(f"[ProceduralMemory] 已有 {len(existing)} 个模板，跳过初始化")
        return

    # 模板 1：网页搜索
    pm.save_procedure(
        task_type="搜索网页",
        trigger_pattern="搜|查|找",
        steps=[
            {"step": 1, "action": "调用 web_search 或 argo_search", "tool": "web_search"},
            {"step": 2, "action": "解析搜索结果", "tool": None},
            {"step": 3, "action": "基于结果回答用户", "tool": None},
            {"step": 4, "action": "用 save_memory 记住关键信息", "tool": "save_memory"},
        ]
    )

    # 模板 2：截图识图
    pm.save_procedure(
        task_type="截图识图",
        trigger_pattern="看|截图|屏幕",
        steps=[
            {"step": 1, "action": "调用 screenshot 截屏", "tool": "screenshot"},
            {"step": 2, "action": "调用 describe_image 识图", "tool": "describe_image"},
            {"step": 3, "action": "基于识图结果回答", "tool": None},
        ]
    )

    # 模板 3：记忆检索
    pm.save_procedure(
        task_type="记忆检索",
        trigger_pattern="之前|上次|记得",
        steps=[
            {"step": 1, "action": "调用 read_memories 检索", "tool": "read_memories"},
            {"step": 2, "action": "如果检索为空，诚实告知", "tool": None},
            {"step": 3, "action": "如果检索到结果，引用回答", "tool": None},
        ]
    )

    # 模板 4：重要信息记忆
    pm.save_procedure(
        task_type="重要信息记忆",
        trigger_pattern="喜欢|讨厌|计划|习惯|约定",
        steps=[
            {"step": 1, "action": "提取关键信息（偏好/计划/习惯）", "tool": None},
            {"step": 2, "action": "调用 save_memory 记住", "tool": "save_memory"},
            {"step": 3, "action": "确认已记住", "tool": None},
        ]
    )

    # 模板 5：天气查询
    pm.save_procedure(
        task_type="天气查询",
        trigger_pattern="天气|温度|冷不冷|下雨",
        steps=[
            {"step": 1, "action": "调用 get_weather 查询天气", "tool": "get_weather"},
            {"step": 2, "action": "基于天气结果回答", "tool": None},
        ]
    )

    # 模板 6：图片搜索
    pm.save_procedure(
        task_type="图片搜索",
        trigger_pattern="找图|搜图|壁纸",
        steps=[
            {"step": 1, "action": "调用 search_images 搜索图片", "tool": "search_images"},
            {"step": 2, "action": "从结果中选择合适的图片", "tool": None},
            {"step": 3, "action": "调用 download_image 下载", "tool": "download_image"},
        ]
    )

    # 模板 7：B站搜索
    pm.save_procedure(
        task_type="B站搜索",
        trigger_pattern="B站|bilibili|哔哩",
        steps=[
            {"step": 1, "action": "调用 bilibili_search 搜索视频", "tool": "bilibili_search"},
            {"step": 2, "action": "从结果中推荐合适的视频", "tool": None},
        ]
    )

    # 模板 8：时间查询
    pm.save_procedure(
        task_type="时间查询",
        trigger_pattern="几点|时间|现在|日期",
        steps=[
            {"step": 1, "action": "调用 get_current_time 获取时间", "tool": "get_current_time"},
            {"step": 2, "action": "回答当前时间", "tool": None},
        ]
    )

    print(f"[ProceduralMemory] ✅ 初始化完成，预置 8 个任务模板")


# 模块加载时自动初始化
try:
    seed_default_procedures()
except Exception as e:
    print(f"[ProceduralMemory] 初始化失败: {e}")


if __name__ == "__main__":
    # 测试代码
    pm = ProceduralMemory()
    seed_default_procedures()

    # 测试搜索
    results = pm.search_procedures("搜索", top_k=3)
    print("\n搜索结果：")
    for r in results:
        print(f"  - {r['task_type']} (置信度 {r['confidence']:.0%})")
        for s in r["steps"]:
            print(f"    {s['step']}. {s['action']}")
