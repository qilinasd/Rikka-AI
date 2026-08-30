"""
RikkaAI - QQ 桥接模块
通过 NapCat (OneBot v11) WebSocket 连接 QQ
"""
import json
import random
import re
import threading
import time
import logging
import uuid

logger = logging.getLogger("QQBridge")


def _segment_message(text: str) -> list:
    """把长消息切成短句列表（分段回复 + 模拟打字间隔用，proactive_chat 式）。

    规则：先按换行拆；超长行按句读切分；段数不超过 QQ_SEGMENT_MAX。
    关闭开关或文本本身够短时原样返回。"""
    try:
        import config as _cfg
        if not getattr(_cfg, "QQ_SEGMENT_REPLY", False):
            return [text] if text else []
        max_segments = max(1, int(getattr(_cfg, "QQ_SEGMENT_MAX", 3)))
    except Exception:
        max_segments = 3
    text = str(text or "").strip()
    if not text or len(text) <= 60:
        return [text]
    lines = [p.strip() for p in re.split(r"[\n]+", text) if p.strip()]
    fine = []
    for line in lines:
        if len(line) <= 40:
            fine.append(line)
            continue
        buf = ""
        for ch in line:
            buf += ch
            if ch in "。！？!?~…；;" and len(buf) >= 8:
                fine.append(buf.strip())
                buf = ""
        if buf.strip():
            fine.append(buf.strip())
    if len(fine) <= 1:
        return [text]
    if len(fine) > max_segments:
        per = -(-len(fine) // max_segments)  # 向上取整分组
        return ["".join(fine[i:i + per]) for i in range(0, len(fine), per)][:max_segments]
    return fine

# 消息回调
_on_message = None
_on_error = None
_on_connected = None
_on_disconnected = None


def set_message_handler(handler):
    """注册消息处理器：handler(user_id, group_id, message, msg_type, sender_name) -> str（回复）

    sender_name 为群名片/昵称（私聊为昵称，拿不到时为空串）。"""
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
        """发送私聊消息（开启分段回复时切短句，段间模拟打字间隔）"""
        try:
            ok = True
            chunks = _segment_message(message)
            for i, chunk in enumerate(chunks):
                if i > 0:
                    time.sleep(random.uniform(1.2, 3.2))  # 像真人一样"打字"再发下一条
                result = self._api_call("send_private_msg", {
                    "user_id": user_id, "message": chunk
                })
                ok = ok and result is not None
            return ok
        except:
            return False

    def send_group_msg(self, group_id: int, message: str) -> bool:
        """发送群消息（分段策略同私聊）"""
        try:
            ok = True
            chunks = _segment_message(message)
            for i, chunk in enumerate(chunks):
                if i > 0:
                    time.sleep(random.uniform(1.2, 3.2))
                result = self._api_call("send_group_msg", {
                    "group_id": group_id, "message": chunk
                })
                ok = ok and result is not None
            return ok
        except:
            return False

    def send_image(self, user_id: int, image_path: str) -> bool:
        """发送图片到私聊（OneBot v11 消息段格式）"""
        try:
            import os as _os
            if not _os.path.exists(image_path):
                logger.error(f"图片文件不存在: {image_path}")
                return False
            # 优先用 file:// URI（NapCat 原生支持）
            file_uri = f"file:///{image_path.replace(_os.sep, '/')}"
            msg_array = [{"type": "image", "data": {"file": file_uri}}]
            result = self._api_call("send_private_msg", {
                "user_id": user_id, "message": msg_array
            })
            if result is not None:
                return True
            # 回退：base64 编码
            import base64
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            msg_array = [{"type": "image", "data": {"file": f"base64://{b64}"}}]
            result = self._api_call("send_private_msg", {
                "user_id": user_id, "message": msg_array
            })
            return result is not None
        except Exception as e:
            logger.error(f"发送图片失败: {e}")
            return False

    def send_group_image(self, group_id: int, image_path: str) -> bool:
        """发送图片到群聊（OneBot v11 消息段格式）"""
        try:
            import os as _os
            if not _os.path.exists(image_path):
                logger.error(f"图片文件不存在: {image_path}")
                return False
            file_uri = f"file:///{image_path.replace(_os.sep, '/')}"
            msg_array = [{"type": "image", "data": {"file": file_uri}}]
            result = self._api_call("send_group_msg", {
                "group_id": group_id, "message": msg_array
            })
            if result is not None:
                return True
            import base64
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            msg_array = [{"type": "image", "data": {"file": f"base64://{b64}"}}]
            result = self._api_call("send_group_msg", {
                "group_id": group_id, "message": msg_array
            })
            return result is not None
        except Exception as e:
            logger.error(f"发送群图片失败: {e}")
            return False

    def send_voice(self, user_id: int, audio_path: str) -> bool:
        """发送语音到私聊（NapCat 会自动转成 QQ 的 Silk 格式）"""
        try:
            import os as _os
            if not _os.path.exists(audio_path):
                logger.error(f"语音文件不存在: {audio_path}")
                return False
            msg_array = [{"type": "record", "data": {"file": audio_path}}]
            result = self._api_call("send_private_msg", {
                "user_id": user_id, "message": msg_array
            })
            return result is not None
        except Exception as e:
            logger.error(f"发送语音失败: {e}")
            return False

    def send_group_voice(self, group_id: int, audio_path: str) -> bool:
        """发送语音到群聊（NapCat 会自动转成 QQ 的 Silk 格式）"""
        try:
            import os as _os
            if not _os.path.exists(audio_path):
                logger.error(f"语音文件不存在: {audio_path}")
                return False
            msg_array = [{"type": "record", "data": {"file": audio_path}}]
            result = self._api_call("send_group_msg", {
                "group_id": group_id, "message": msg_array
            })
            return result is not None
        except Exception as e:
            logger.error(f"发送群语音失败: {e}")
            return False

    def get_login_info(self) -> dict:
        """获取机器人自己的 QQ 信息"""
        return self._api_call("get_login_info") or {}

    def get_friend_list(self) -> list:
        """获取好友列表（OneBot v11 get_friend_list）"""
        return self._api_call("get_friend_list", {}) or []

    def get_group_list(self) -> list:
        """获取群列表（OneBot v11 get_group_list）"""
        return self._api_call("get_group_list", {}) or []

    def get_self_qq(self):
        """返回当前登录的 QQ 号（登录事件未到时可能为 0）。"""
        return getattr(self, "_self_qq", 0) or 0

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
        # 获取机器人信息（失败重试：NapCat 刚握手完可能还没准备好应答 API）
        self._fetch_login_info_with_retry()
        if _on_connected:
            try: _on_connected()
            except: pass

    def _fetch_login_info_with_retry(self):
        """拉取机器人 QQ 号；失败后台重试（SelfQQ=None 会导致群聊 @检测完全失效）。"""
        def _work():
            for attempt in range(6):
                try:
                    info = self.get_login_info()
                    uid = (info or {}).get("user_id")
                    if uid:
                        self._self_qq = int(uid)
                        self._self_name = (info or {}).get("nickname", "六花")
                        logger.info(f"[WS] 已获取机器人 QQ: {uid}（第 {attempt + 1} 次尝试）")
                        return
                except Exception as e:
                    logger.warning(f"[WS] get_login_info 第 {attempt + 1} 次失败: {e}")
                time.sleep(2)
            logger.error("[WS] 多次尝试后仍未获取机器人 QQ 号，群聊 @检测将失效")
        threading.Thread(target=_work, daemon=True, name="QQSelfInfo").start()

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
            # OneBot v11 每个事件都带 self_id（机器人自己的 QQ）——
            # 即使启动时 get_login_info 失败，也从这里自愈
            try:
                if data.get("self_id") and not self._self_qq:
                    self._self_qq = int(data["self_id"])
                    logger.info(f"[WS] 从事件 self_id 自愈机器人 QQ: {self._self_qq}")
            except Exception:
                pass
            user_id = data.get("user_id", 0)
            group_id = data.get("group_id", 0)
            raw_msg = str(data.get("raw_message", ""))
            msg_type = data.get("message_type", "private")

            logger.info(
                f"[WS] 消息事件 user={user_id} group={group_id} type={msg_type} "
                f"self_qq={self._self_qq} msg={raw_msg[:40]!r}"
            )
            if user_id == self._self_qq:
                logger.info(f"[WS] 过滤自己发的消息 user={user_id}")
                return

            sender = data.get("sender") or {}
            sender_name = str(sender.get("card") or sender.get("nickname") or "")[:24]

            if _on_message:
                try:
                    reply = _on_message(user_id, group_id, raw_msg, msg_type, sender_name)
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
        host, ws_port = "127.0.0.1", 3001
        try:
            import config as _cfg
            host = getattr(_cfg, "QQ_WS_HOST", host)
            ws_port = int(getattr(_cfg, "QQ_WS_PORT", ws_port))
        except Exception:
            pass
        _bridge = NapCatBridge(host=host, ws_port=ws_port)
    return _bridge
