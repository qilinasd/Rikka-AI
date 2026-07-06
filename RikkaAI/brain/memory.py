"""
RikkaAI - 记忆系统（文件存储）
每条记忆存为一个独立文件在 memories/ 文件夹
"""
import os
from datetime import datetime
import config


class MemorySystem:
    """六花的记忆系统 — 文件存储"""

    def __init__(self):
        os.makedirs(config.MEMORIES_DIR, exist_ok=True)

    def _path(self, memory_id: int) -> str:
        return os.path.join(config.MEMORIES_DIR, f"mem_{memory_id}.txt")

    def _next_id(self) -> int:
        files = [f for f in os.listdir(config.MEMORIES_DIR) if f.startswith("mem_")]
        if not files:
            return 1
        ids = [int(f.replace("mem_", "").replace(".txt", "")) for f in files]
        return max(ids) + 1

    def add_memory(self, content: str, category: str = "📝 日常"):
        mid = self._next_id()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(self._path(mid), "w", encoding="utf-8") as f:
            f.write(f"{content}\n---\n{category}\n{now}")

    def delete_memory(self, memory_id: int):
        p = self._path(memory_id)
        if os.path.exists(p):
            os.remove(p)

    def get_all(self) -> list:
        result = []
        for fname in sorted(os.listdir(config.MEMORIES_DIR), reverse=True):
            if fname.startswith("mem_") and fname.endswith(".txt"):
                try:
                    mid = int(fname.replace("mem_", "").replace(".txt", ""))
                    with open(os.path.join(config.MEMORIES_DIR, fname), "r", encoding="utf-8") as f:
                        content = f.read()
                    parts = content.split("\n---\n")
                    text = parts[0]
                    category = "📝 日常"
                    created_at = ""
                    if len(parts) >= 2:
                        meta = parts[1].split("\n")
                        category = meta[0] if meta[0] else "📝 日常"
                        created_at = meta[1] if len(meta) > 1 else ""
                    result.append({"id": mid, "content": text, "category": category, "created_at": created_at})
                except:
                    pass
        return result

    def get_recent(self, limit: int = 50) -> list:
        return self.get_all()[:limit]

    def search(self, query: str) -> list:
        return [m for m in self.get_all() if query in m["content"]]
