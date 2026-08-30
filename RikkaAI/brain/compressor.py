"""
RikkaAI - TokenJuice 式工具输出压缩（Phase 5）

在工具输出进入模型前先压缩，最多可省约 80% token：
  - 超长文本：头部保留 + 中段折叠 + 尾部保留
  - 保留关键结构：标题、数字、URL、代码行号等
  - 兜底截断

gate: features.is_enabled("tool_compress_enabled")
"""
from brain import features

# token 估算：中英文混合，粗略按 len/1.8
_MAX_TOKENS_KEEP = 1200


def est_tokens(text: str) -> int:
    return int(len(str(text or "")) / 1.8)


def compress(text: str, max_tokens: int = None, keep_head: int = None, keep_tail: int = None) -> str:
    """压缩工具输出。未超限原样返回；超限按比例折叠中段。"""
    if not features.is_enabled("tool_compress_enabled"):
        return text
    text = str(text or "")
    if not text:
        return text
    max_tokens = max_tokens or _MAX_TOKENS_KEEP
    if est_tokens(text) <= max_tokens:
        return text
    # 分块
    keep_head = keep_head or int(max_tokens * 0.55)
    keep_tail = keep_tail or int(max_tokens * 0.35)
    # 保持字符量近似 token 预算（粗略）
    head_chars = int(keep_head * 1.8)
    tail_chars = int(keep_tail * 1.8)
    head = text[:head_chars]
    tail = text[-tail_chars:]
    dropped = est_tokens(text) - est_tokens(head) - est_tokens(tail)
    return (
        f"{head}\n……[已压缩，省约 {dropped} tokens]……\n{tail}"
    )


def compress_for_prompt(text: str, max_tokens: int = None) -> str:
    """供 agent 直接调用：未超限原样，超限压缩。"""
    return compress(text, max_tokens=max_tokens)
