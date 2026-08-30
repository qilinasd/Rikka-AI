"""
RikkaAI - LLM 情绪自动判定（对标 LingChat 的情绪识别）
====================================================
对话结束后异步让小模型判定六花的心情与能量/好感微调，替代单一关键词法
（关键词 analyze() 仍作回复前的即时兜底）。失败静默，绝不影响对话。

设计要点：
- 异步 fire-and-forget：不阻塞 worker 线程、不延迟输入框解锁
- 尊重锁定字段（情感面板锁定的 mood/energy/affection 不被判定覆盖）
- delta 有硬上限（能量 ±15、好感 ±10），防止单轮情绪被 LLM 拉爆
"""

import json
import re
import threading


def judge_async(agent, user_text, reply_text):
    """启动后台判定线程（守护线程，进程退出不等待）。"""
    if not user_text or not reply_text:
        return
    threading.Thread(
        target=_judge, args=(agent, str(user_text), str(reply_text)), daemon=True
    ).start()


def _judge(agent, user_text, reply_text):
    try:
        from openai import OpenAI
        import config as cfg
        client = OpenAI(api_key=cfg.API_KEY, base_url=cfg.API_BASE)
        resp = client.chat.completions.create(
            model=cfg.MODEL,
            messages=[{"role": "user", "content": (
                "判断这段对话结束后，AI 伴侣六花的心情状态。只输出 JSON：\n"
                '{"mood":"happy|neutral|sad|angry","energy_delta":-15到15的整数,"affection_delta":-10到10的整数}\n'
                "依据用户语气与对话走向：温和愉快→happy/正delta；被冷落、被怼→sad或angry/负delta；"
                "无明确情绪信号→neutral、delta≈0。不要过度反应。\n\n"
                f"用户说：{user_text[:300]}\n六花回：{reply_text[:200]}"
            )}],
            temperature=0.1, max_tokens=80, timeout=15,
        )
        m = re.search(r"\{.*\}", resp.choices[0].message.content or "", re.DOTALL)
        if not m:
            return
        data = json.loads(m.group())
        agent.emotion.apply_llm_mood(
            data.get("mood"), data.get("energy_delta"), data.get("affection_delta")
        )
    except Exception:
        pass
