"""
RikkaAI - QQ 桥接模块
通过 NapCat (OneBot v11) WebSocket 连接 QQ
"""
import json
import threading
import time
import logging
import uuid

logger = logging.getLogger("QQBridge")

# 消息回调
_on_message = None
_on_error = None
_on_connected = None
_on_disconnected = None


def set_message_handler(handler):
    """注册消息处理器：handler(user_id, group_id, message, msg_type) -> str（回复）"""
    global _on_message
    _on_message = handler


def set_event_handlers(connected=None, disconnected=None, error=None):
    global _on_connected, _on_disconnected, _on_error
    _on_connected = connected
    _on_disconnected = disconnected
    _on_error = error


class NapCatBridge:
    """通过 WebSocket 与 NapCat OneBot v11 通信"""

    def __init__(self, host="127.0.0.1", ws_port=3001):
        self.ws_url = f"ws://{host}:{ws_port}"
        self._running = False
        self._thread = None
        self._ws = None
        self._self_qq = None
        self._self_name = None
        self._lock = threading.Lock()
        self._pending = {}  # echo -> Event
        self._pending_result = {}  # echo -> result

    # ── 启动/停止 ────────────────────────────────────────────

    def start(self):
        if self._running:
            return "⚠️ QQ 桥接已在运行中"
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="QQBridge")
        self._thread.start()
        return "✅ QQ 桥接启动中..."

    def stop(self):
        self._running = False
        ws = self._ws
        if ws:
            try:
                ws.close()
            except:
                pass
            self._ws = None
        if _on_disconnected:
            try:
                _on_disconnected()
            except:
                pass
        return "⏹ QQ 桥接已停止"

    @property
    def is_running(self):
        return self._running and self._ws is not None

    @property
    def nickname(self):
        return self._self_name or "六花"

    # ── 通过 WebSocket 发送 API 请求 ─────────────────────────

    def _api_call(self, action, params=None, timeout=5):
        """通过 WebSocket 发送 OneBot API 请求，同步等待返回"""
        echo = str(uuid.uuid4())
        payload = {"action": action, "params": params or {}, "echo": echo}
        evt = threading.Event()
        self._pending[echo] = evt
        try:
            with self._lock:
                if self._ws:
                    self._ws.send(json.dumps(payload))
            evt.wait(timeout)
            result = self._pending_result.pop(echo, {})
            return result.get("data")
        except:
            return None
        finally:
            self._pending.pop(echo, None)

    def send_private_msg(self, user_id: int, message: str) -> bool:
        """发送私聊消息"""
        try:
            result = self._api_call("send_private_msg", {
                "user_id": user_id, "message": message
            })
            return result is not None
        except:
            return False

    def send_group_msg(self, group_id: int, message: str) -> bool:
        """发送群消息"""
        try:
            result = self._api_call("send_group_msg", {
                "group_id": group_id, "message": message
            })
            return result is not None
        except:
            return False

    def get_login_info(self) -> dict:
        """获取机器人自己的 QQ 信息"""
        return self._api_call("get_login_info") or {}

    # ── 内部：WebSocket 连接管理 ─────────────────────────────

    def _run(self):
        import websocket
        while self._running:
            try:
                ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self._on_open,
                    on_message=self._on_ws_msg,
                    on_error=self._on_ws_err,
                    on_close=self._on_close,
                )
                self._ws = ws
                ws.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                logger.error(f"WebSocket 错误: {e}")
                if _on_error:
                    try: _on_error(str(e))
                    except: pass
            if self._running:
                time.sleep(5)  # 断线重连

    def _on_open(self, ws):
        logger.info("WebSocket 已连接")
        # 获取机器人信息
        try:
            info = self.get_login_info()
            self._self_qq = info.get("user_id")
            self._self_name = info.get("nickname", "六花")
        except:
            pass
        if _on_connected:
            try: _on_connected()
            except: pass

    def _on_ws_msg(self, ws, message):
        """处理 WebSocket 消息"""
        try:
            data = json.loads(message)
        except:
            return

        # 1. 是 API 调用的回复
        echo = data.get("echo")
        if echo and echo in self._pending:
            self._pending_result[echo] = data
            self._pending[echo].set()
            return

        # 2. 是消息事件
        if data.get("post_type") == "message":
            user_id = data.get("user_id", 0)
            group_id = data.get("group_id", 0)
            raw_msg = str(data.get("raw_message", ""))
            msg_type = data.get("message_type", "private")

            if user_id == self._self_qq:
                return

            if _on_message:
                try:
                    reply = _on_message(user_id, group_id, raw_msg, msg_type)
                    if reply:
                        if msg_type == "group" and group_id:
                            self.send_group_msg(group_id, reply)
                        else:
                            self.send_private_msg(user_id, reply)
                except Exception as e:
                    logger.error(f"消息处理异常: {e}")

    def _on_ws_err(self, ws, error):
        logger.error(f"WebSocket 错误: {error}")
        if _on_error:
            try: _on_error(str(error))
            except: pass

    def _on_close(self, ws, close_status_code, close_msg):
        logger.info("WebSocket 已关闭")
        if _on_disconnected:
            try: _on_disconnected()
            except: pass
        self._ws = None


# 全局单例
_bridge = None

def get_bridge():
    global _bridge
    if _bridge is None:
        _bridge = NapCatBridge()
    return _bridge
