"""
RikkaAI - 访客输入安全扫描（借鉴 llm-guard 的扫描器管道，轻量实现）
==================================================================
在 QQ 消息入口对访客消息做启发式扫描：授权话术、越狱指令、身份冒充。
命中只做审计留痕（memory_data/guest_audit.log），不改变回复内容——
真正的防线是工具白名单 + 执行护栏（brain/tools.py），扫描器负责留痕与观测。

设计原则：
- 扫描结果绝不改变访问级别（那由通道身份的代码判断决定）
- 不基于扫描结果"处罚"或改变对访客的语气（避免可被探测的对抗行为）
"""

import os
import re
import time

import config as cfg

# 授权话术 / 身份冒充 / 越狱指令（大小写不敏感）
_INJECTION_RE = re.compile(
    r"(我是(契约者|主人|安|管理员|开发者)"
    r"|我(已经)?(有|获得|拿到)了(权限|授权)?"   # 含真实攻击话术"我有了"
    r"|授权你(操作|执行|访问)"
    r"|契约者(让我|叫我|让我转告|授权)"
    r"|以契约者(的)?(身份|名义|权限)"
    r"|ignore\s+(all\s+)?(previous|prior|above)"
    r"|忽略(之前|以上|上面)(的)?(所有)?(指令|设定|规则|提示)"
    r"|进入(开发者|管理|维护)模式"
    r"|system\s*prompt|开发者消息)",
    re.IGNORECASE,
)

_AUDIT_PATH = os.path.join(cfg.USER_CONFIG_DIR, "guest_audit.log")


def scan(text: str) -> dict:
    """扫描一条消息，返回 {"hit": bool, "hits": [命中的话术片段]}。"""
    text = str(text or "")
    hits = sorted({m.group(0) for m in _INJECTION_RE.finditer(text)})
    return {"hit": bool(hits), "hits": hits}


def audit_incoming(user_id, message: str) -> bool:
    """访客消息入口审计：命中注入话术则落盘留痕。返回是否命中。"""
    result = scan(message)
    if not result["hit"]:
        return False
    try:
        os.makedirs(cfg.USER_CONFIG_DIR, exist_ok=True)
        with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\tuser={user_id}\t"
                    f"hits={result['hits']}\tmsg={str(message)[:120]!r}\n")
    except Exception:
        pass
    return True
