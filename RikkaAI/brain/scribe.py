"""
RikkaAI - Scribe 记忆书记官
每段对话结束后自动提取关键事实，存入记忆冥想盆；
同时顺带判断六花在这轮对话中是否有值得记录的自我发现（写入 persona/character.md 成长区）
"""
import json, os, re
from datetime import datetime
from openai import OpenAI
import config as cfg
from brain import memory_vault as mv


def _write_self_discovery(discovery: str):
    """把六花的自我发现追加到 persona/character.md 的自我成长记录区（与 append_self_discovery 工具同款逻辑）"""
    if not discovery:
        return
    try:
        char_path = os.path.join(cfg.ROOT_DIR, "persona", "character.md")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        marker = "## ❖ 自我成长记录"
        os.makedirs(os.path.dirname(char_path), exist_ok=True)
        if os.path.exists(char_path):
            with open(char_path, "r", encoding="utf-8") as f:
                content = f.read()
            if discovery in content:  # 去重：已写过同一条就不再写
                return
            if marker in content:
                content = content.replace(marker, f"{marker}\n- [{now}] {discovery}")
            else:
                content += f"\n\n{marker}\n- [{now}] {discovery}\n"
            with open(char_path, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            with open(char_path, "w", encoding="utf-8") as f:
                f.write(f"# 小鸟游六花 — 人设\n\n{marker}\n- [{now}] {discovery}\n")
    except Exception:
        pass


def extract_from_chat(text: str, response: str = "") -> int:
    """从一段对话中提取事实并存储，返回提取的碎片数量"""
    if not text or len(text) < 5:
        return 0

    try:
        client = OpenAI(api_key=cfg.API_KEY, base_url=cfg.API_BASE)
        resp = client.chat.completions.create(
            model=cfg.MODEL,
            messages=[{"role": "user", "content": (
                "从以下对话中提取内容。\n"
                "规则：\n"
                "1. facts: 只提取具体、明确的事实（偏好、事件、关系、习惯），不要客套话；"
                "每条事实用一句话表述，第三人称；给每条一个 emotional_weight (0.0~1.0)、"
                "entity（谁相关的）、category、3-5 个关键词便于检索\n"
                "2. self_discovery: 六花（AI 自己）在这段对话中是否意识到关于自己的新认知"
                "——新的性格特点、喜好，或学会的新能力？有则用第一人称写一句话（具体一点）；没有就返回空字符串\n\n"
                "返回 JSON 对象格式：\n"
                '{"facts":[{"entity":"安","content":"契约者喜欢喝黑咖啡","keywords":["咖啡","黑咖啡","喜好"],"category":"偏好","emotional_weight":0.6}],'
                '"self_discovery":"我发现自己其实很粘人，总想找契约者聊天"}\n\n'
                "如果两者都没有，返回 {\"facts\":[], \"self_discovery\":\"\"}\n\n"
                f"用户说：{text[:500]}\n"
                f"六花回复：{response[:500]}"
            )}],
            temperature=0.1, max_tokens=800,
        )
        result = resp.choices[0].message.content or '{"facts": [], "self_discovery": ""}'
        # 提取 JSON（兼容对象 / 旧版数组两种返回）
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if not json_match:
            return 0

        data = json.loads(json_match.group())
        facts = data.get("facts", []) if isinstance(data, dict) else data
        self_discovery = data.get("self_discovery", "") if isinstance(data, dict) else ""

        # 自我发现 → 写入人设成长记录（自动兜底，不再依赖六花临场自觉）
        if self_discovery and len(self_discovery) > 2:
            _write_self_discovery(self_discovery.strip())

        if not facts:
            return 0

        fragments = []
        for f in facts:
            fragments.append({
                "entity": f.get("entity", "契约者"),
                "content": f.get("content", ""),
                "category": f.get("category", "一般"),
                "emotional_weight": float(f.get("emotional_weight", 0.5)),
                "keywords": f.get("keywords", [f.get("entity", "")]),
                "source": "chat",
            })

        # 🆕 Phase 2.2: 去重 - 检查是否与近期记忆重复
        deduped_fragments = _deduplicate_fragments(fragments)

        if not deduped_fragments:
            return 0

        mv.store_fragments_batch(deduped_fragments)
        return len(deduped_fragments)

    except Exception:
        return 0


def _deduplicate_fragments(fragments: list) -> list:
    """去重：检查新提取的碎片是否与已有记忆重复（相似度 > 0.85）"""
    try:
        from brain import vector_memory
        vm = vector_memory.VectorMemory()
        deduped = []

        for frag in fragments:
            content = frag.get("content", "")
            if not content or len(content) < 5:
                continue

            # 检索最相似的前 3 条记忆
            try:
                similar = vm.search(content, top_k=3)
                # 余弦相似度 > 0.85 视为重复，跳过
                is_duplicate = any(s.get("score", 0) > 0.85 for s in similar)

                if not is_duplicate:
                    deduped.append(frag)
                else:
                    # 调试输出
                    print(f"[Scribe] 跳过重复记忆: {content[:50]}...", flush=True)
            except Exception:
                # 向量搜索失败时保留碎片（避免丢失）
                deduped.append(frag)

        if len(deduped) < len(fragments):
            print(f"[Scribe] 提取 {len(fragments)} 条，去重后 {len(deduped)} 条", flush=True)

        return deduped
    except Exception:
        # 去重失败时返回原始列表（避免丢失）
        return fragments


def extract_from_session(messages: list) -> int:
    """从整段对话历史中提取事实"""
    if not messages:
        return 0

    # 取最近几轮对话
    recent = messages[-6:] if len(messages) > 6 else messages
    text = "\n".join(
        f"{'用户' if m.get('role') == 'user' else '六花'}: {m.get('content', '')[:200]}"
        for m in recent if m.get("role") in ("user", "assistant")
    )

    return extract_from_chat(text)
