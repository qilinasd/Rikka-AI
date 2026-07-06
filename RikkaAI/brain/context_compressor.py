"""
RikkaAI - 上下文压缩器
长对话智能压缩，节省 token
"""
import json
import time
from datetime import datetime
from openai import OpenAI
import config as cfg

# 阈值配置
COMPRESS_AFTER = 30        # 超过30条消息触发压缩
KEEP_RECENT = 20            # 保留最近20条完整消息
COOLDOWN_SECONDS = 600      # 两次压缩之间至少间隔600秒

_last_compress_time = 0


def _get_client():
    return OpenAI(api_key=cfg.API_KEY, base_url=cfg.API_BASE)


def _count_messages(history: list) -> int:
    """统计非 system 的消息数"""
    return sum(1 for m in history if m.get("role") in ("user", "assistant"))


def should_compress(history: list) -> bool:
    if not cfg.COMPRESSION_ENABLED:
        return False
    global _last_compress_time
    if time.time() - _last_compress_time < COOLDOWN_SECONDS:
        return False
    return _count_messages(history) >= cfg.COMPRESSION_THRESHOLD


def compress(history: list) -> list:
    """压缩历史，返回新的 history 列表"""
    global _last_compress_time

    all_msgs = [m for m in history if m.get("role") in ("user", "assistant")]
    system_msgs = [m for m in history if m.get("role") == "system"]

    threshold = cfg.COMPRESSION_THRESHOLD
    keep = cfg.COMPRESSION_KEEP

    if len(all_msgs) <= threshold:
        return history

    compress_count = len(all_msgs) - keep
    to_compress = all_msgs[:compress_count]
    to_keep = all_msgs[compress_count:]

    summary = _generate_summary(to_compress)

    # 保存摘要用于跨会话继承
    cfg.save_last_summary(summary)

    new_history = list(system_msgs)
    new_history.append({"role": "system", "content": f"【历史对话摘要】{summary}"})
    new_history.extend(to_keep)

    _last_compress_time = time.time()
    return new_history


def _generate_summary(messages: list) -> str:
    """用 LLM 生成对话摘要"""
    try:
        text = ""
        for m in messages[-50:]:  # 最多取最近50条做摘要
            role = "用户" if m["role"] == "user" else "六花"
            content = m["content"][:200]
            text += f"{role}: {content}\n"

        prompt = (
            "请将以下对话压缩为一段详细的中文摘要（300~500字），"
            "涵盖：讨论的核心话题、用户的关键需求或偏好、达成的结论、涉及的具体内容。\n\n"
            f"{text[:4000]}"
        )

        resp = _get_client().chat.completions.create(
            model=cfg.MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )
        return resp.choices[0].message.content or ""
    except Exception:
        # 压缩失败时简单截取
        return f"共{len(messages)}条对话记录，涉及{sum(1 for m in messages if m['role']=='user')}轮对话"
