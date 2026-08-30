"""
RikkaAI - MCP 客户端（Phase 4）

轻量 MCP（Model Context Protocol）客户端：连接外部 MCP 服务器，把它们的工具
并入六花的能力面（openhuman 的"5000+ MCP"思路）。用标准库 urllib 走 JSON-RPC
（HTTP transport），不依赖 mcp SDK；连不上时优雅降级，绝不影响主链路。

gate: features.is_enabled("mcp_enabled")
配置：user_config.json 里 mcp_servers = [{name, url, enabled, transport}]
"""
import json
import time
import urllib.request
from brain import features
import config as cfg

_JSONRPC_VER = "2.0"


def list_configured() -> list:
    """已配置的 MCP 服务器（默认只返回启用且支持 HTTP 的）。"""
    if not features.is_enabled("mcp_enabled"):
        return []
    servers = (cfg._USER_CONFIG or {}).get("mcp_servers", [])
    return [s for s in servers if s.get("enabled", True)]


class McpClient:
    """单个 MCP 服务器客户端（HTTP streamable-ish JSON-RPC）。"""

    def __init__(self, name: str, url: str, timeout: float = 15.0):
        self.name = name
        self.url = url
        self.timeout = timeout
        self._session_id = None
        self._tools = []

    # ── 底层 JSON-RPC 调用 ─────────────────────────────────────
    def _rpc(self, method: str, params: dict):
        payload = {"jsonrpc": _JSONRPC_VER, "id": 1, "method": method, "params": params or {}}
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                # 保留响应头里的 session（若服务端下发）
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self._session_id = sid
                body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body) if body.strip().startswith("{") else self._parse_sse(body)
                return data
        except Exception as e:
            return {"error": {"message": str(e)[:200]}, "_ok": False}

    @staticmethod
    def _parse_sse(body: str):
        # 简化的 SSE 解析：取最后一个 data: 行
        lines = [l for l in body.split("\n") if l.startswith("data:")]
        if lines:
            try:
                return json.loads(lines[-1][5:].strip())
            except Exception:
                pass
        return {}

    # ── 高层 API ───────────────────────────────────────────────
    def initialize(self) -> bool:
        r = self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "rikkaai", "version": cfg.APP_VERSION},
        })
        if isinstance(r, dict) and r.get("error"):
            return False
        # notifications/initialized
        self._rpc("notifications/initialized", {})
        return True

    def list_tools(self) -> list:
        r = self._rpc("tools/list", {})
        if isinstance(r, dict) and r.get("error"):
            return []
        result = r.get("result", {}) if isinstance(r, dict) and not r.get("error") else r or {}
        tools = result.get("tools", []) if isinstance(result, dict) else []
        self._tools = tools
        return tools

    def call_tool(self, name: str, args: dict) -> dict:
        r = self._rpc("tools/call", {"name": name, "arguments": args or {}})
        if isinstance(r, dict) and not r.get("error"):
            return {"status": "success", "content": r.get("result", r)}
        return {"status": "failure", "content": (r or {}).get("error", r)}


def to_openai_schemas(tools: list) -> list:
    """把 MCP 工具定义转成 OpenAI function 定义，便于并入 agent 的 tools。"""
    out = []
    for t in tools or []:
        name = t.get("name", "")
        if not name:
            continue
        out.append({
            "type": "function",
            "function": {
                "name": f"mcp_{name}",
                "description": t.get("description", "")[:500],
                "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
            },
        })
    return out


def discover_all() -> dict:
    """遍历所有已配置服务器，初始化并收集工具。返回 {server: [tools]}。"""
    if not features.is_enabled("mcp_enabled"):
        return {}
    out = {}
    for s in list_configured():
        try:
            client = McpClient(s.get("name", "?"), s.get("url", ""))
            if client.initialize():
                tools = client.list_tools()
                if tools:
                    out[s.get("name")] = tools
        except Exception:
            continue
    return out


# ── 带缓存的 OpenAI 工具定义（供 agent 高频调用，避免每轮都去连 MCP）──
_cache = {"ts": 0, "tools": []}
_cache_ttl = 300  # 5 分钟


def get_cached_openai_tools(max_tools: int = 40, ttl: int = 300, force: bool = False) -> list:
    """返回可并入 agent 的 OpenAI 工具定义（有缓存 + 上限）。"""
    global _cache
    fresh = _cache["tools"] and (time.time() - _cache["ts"]) < (ttl or _cache_ttl)
    if not fresh or force:
        try:
            disc = discover_all()
            flat = [t for tools in disc.values() for t in tools]
            _cache = {"ts": time.time(), "tools": to_openai_schemas(flat)}
        except Exception:
            _cache = {"ts": time.time(), "tools": _cache.get("tools", [])}
    return list(_cache["tools"])[: max_tools or 40]
