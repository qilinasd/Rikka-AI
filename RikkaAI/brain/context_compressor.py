"""
RikkaAI - 上下文压缩器
长对话智能压缩，节省 token
"""
from openai import OpenAI
import config as cfg


def _get_client():
    return OpenAI(api_key=cfg.API_KEY, base_url=cfg.API_BASE)


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
