"""
RikkaAI - 全局配置
"""
import os, json
from datetime import datetime
import secret_store

APP_NAME = "RikkaAI"; APP_VERSION = "0.3.0"
WINDOW_WIDTH = 1672; WINDOW_HEIGHT = 941; WINDOW_MIN_WIDTH = 980; WINDOW_MIN_HEIGHT = 680

MODEL = "deepseek-v4-flash"; API_BASE = "https://api.deepseek.com/v1"
API_KEY = ""; TEMPERATURE = 0.8

# twitter-cli 直连 X 的代理（国内需走 VPN；VPN 端口变了改这里）
TWITTER_PROXY = "http://127.0.0.1:7897"

PROACTIVE_ENABLED = True; PROACTIVE_INTERVAL = 15; PROACTIVE_PERSIST = 3; PROACTIVE_COOLDOWN = 60
PROACTIVE_SLACK_ENABLED = True; PROACTIVE_SLACK_PROB = 30; PROACTIVE_SLACK_COOLDOWN = 60  # 观察冷却（分钟），独立于主动聊天
PROACTIVE_QQ_ENABLED = True  # 主动关心时同步发 QQ（多通道交付）
# ── 主动行为微调（内驱引擎/窥屏/QQ 体验） ──
PROACT_DND_START = 23  # 免打扰起始小时（含）。此时段内不冲浪不冒泡不窥屏
PROACT_DND_END = 8     # 免打扰结束小时（不含）
PROACTIVE_UNANSWERED_MAX = 3  # 连续主动 N 次没被理会就停止打扰（0=不限制）
SCREEN_SENSE_ENABLED = True   # LingChat 式主动窥屏：定期感知桌面状态（工作/游戏/挂机…）
SCREEN_SENSE_INTERVAL_MIN = 12  # 窥屏感知间隔（分钟）
QQ_SEGMENT_REPLY = True  # QQ 消息分段发送，段间模拟打字间隔
QQ_SEGMENT_MAX = 3       # 单条消息最多切成几段
QQ_GROUP_MODE = "smart"  # 群聊模式：smart=智能插话（评分闸门）；at_only=仅@我和点名才回
QQ_GROUP_SCORE_THRESHOLD = 60  # 智能插话模式的回复评分阈值（越高越沉默）
MEMORY_CUE_ENABLED = True  # 记忆唤起：主动翻旧账关心契约者（完整版，对齐莲心）
MEMORY_CUE_MAX_CANDIDATES = 8  # 每轮评估的候选上限
WEEKLY_AUTO_ENABLED = True  # 自动周记：每周日固定时间自动生成本周周记
WEEKLY_AUTO_HOUR = 21  # 触发小时（0-23）
WEEKLY_AUTO_RETRIES = 3  # 失败后每小时重试次数（含首次共 3 次机会）
DIARY_AUTO_FLOW_ENABLED = True  # 实时流水日记：每轮对话结束自动追加到当天日记
DIARY_AUTO_FLOW_MAX = 120  # 每条流水记录单方内容最大长度（字符）
DIARY_AUTO_SUMMARY_ENABLED = True  # 日记自动收尾：每天定时把当天流水提炼成六花视角的日记
DIARY_AUTO_SUMMARY_HOUR = 23  # 自动收尾触发小时（0-23），默认每晚 23 点
SURF_AUTO_ENABLED = True  # 内驱引擎总闸：六花自主去B站冲浪（偷偷逛+聊天带出/安静时冒泡）
SURF_AUTO_INTERVAL_MIN = 15  # 主动冲浪平均间隔（分钟），实际带 ±35% 随机抖动（约 10-20 分钟）
SURF_TAGS_PER_ROUND = 4  # 每次冲浪随机挑几个兴趣标签去搜（1-10）
SURF_SEARCH_LIMIT = 2  # 单个标签最多返回几条视频（星级高的拿满配额，默认 2 条）
SURF_TAG_COOLDOWN_HOURS = 24  # 同一兴趣标签搜索冷却（小时）
SURF_TAG_DECAY_PER_7_DAYS = 3  # 兴趣标签分数每 7 天衰减
SURF_REACTION_LIKED = 10  # 对推荐点 👍 时给标签加的分
SURF_REACTION_DISLIKED = 5  # 对推荐点 👎 时给标签扣的分（正数，扣分取负）
# ── 内驱引擎（brain/inner_drive.py，麦麦式自主性）微调项 ──
SURF_JITTER = 0.35  # 冲浪间隔随机抖动幅度（0-0.9），避免整点式机械触发
SURF_SPEAK_IDLE_MIN = 5  # 契约者安静多久（分钟）后六花才允许主动冒泡分享
SURF_SPEAK_COOLDOWN_MIN = 30  # 两次主动冒泡的最小间隔（分钟）
SURF_STASH_FRESH_HOURS = 8  # 冲浪见闻存货的新鲜期（小时），过期不再在聊天中带出
ROTATION_THRESHOLD = 20
COMPRESSION_ENABLED = True; COMPRESSION_THRESHOLD = 30; COMPRESSION_KEEP = 20
AUTO_START = False
SEARXNG_BASE_URL = "http://localhost:8080"

# ── 视觉 API（由“识图模型方案”提供；不设默认服务商） ──
VISION_API_KEY = ""
VISION_MODEL = ""
VISION_API_BASE = ""

# ── QQ 权限控制 ──
QQ_ALLOWED_USERS = []  # 允许操作电脑的 QQ 号列表，空 = 无人有权限
QQ_WS_HOST = "127.0.0.1"   # NapCat WebSocket 地址（可在 user_config.json 用 qq_ws_host 覆盖）
QQ_WS_PORT = 3001          # NapCat WebSocket 端口（可在 user_config.json 用 qq_ws_port 覆盖）

# ── QQ 回复节奏 ──
QQ_REPLY_THINK_DELAY = 3   # 收到对方消息后，六花先思考这么多秒再开始回复（像真人那样）

# ── LLM 对话超时（防止流式回复挂死） ──
LLM_STREAM_STALL_TIMEOUT = 600   # 流式生成中若超过 N 秒没收到新内容，判定为卡死并中止（默认 SDK 是 600s，一卡就是十分钟）
QQ_MAX_REPLY_TIME = 60          # QQ 回复的总时限（秒）：超过后无论卡在哪，都强制发一条兜底，不让对方干等

# 智能搜图设置
SMART_SEARCH_MAX_RESULTS = 3       # 返回几张图（1-10）
SMART_SEARCH_MAX_ANALYZE = 10      # 最多看几张候选图（3-30）
SMART_SEARCH_MAX_CANDIDATES = 20   # 从SearXNG取多少候选（5-50）

CHARACTER_PANEL_WIDTH = 380
CHARACTER_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "assets", "images", "character_full.png")

ROOT_DIR = os.path.dirname(__file__)
ASSETS_DIR = os.path.join(ROOT_DIR, "assets"); IMAGES_DIR = os.path.join(ASSETS_DIR, "images")
STYLES_DIR = os.path.join(ASSETS_DIR, "styles")
MEMORY_DIR = os.path.join(ROOT_DIR, "memory_data")
USER_CONFIG_DIR = os.path.join(ROOT_DIR, "memory_data"); USER_CONFIG_PATH = os.path.join(USER_CONFIG_DIR, "user_config.json")
SUMMARY_DIR = os.path.join(ROOT_DIR, "summaries", "sessions")  # 会话轮转摘要专属目录
IMAGES_DIR_ROOT = os.path.join(ROOT_DIR, "images"); IMAGES_SENT_DIR = os.path.join(IMAGES_DIR_ROOT, "sent"); IMAGES_RECEIVED_DIR = os.path.join(IMAGES_DIR_ROOT, "received"); SCREENSHOTS_DIR = os.path.join(IMAGES_DIR_ROOT, "screenshots"); IMAGES_DOWNLOADED_DIR = os.path.join(IMAGES_DIR_ROOT, "downloaded")
CONVERSATIONS_DIR = os.path.join(ROOT_DIR, "conversations")
SURF_DIR = os.path.join(ROOT_DIR, "surf_records")  # 六花冲浪记录（搜索历史）保存目录

# ── 语音设置（GPT-SoVITS 定制音色） ──
# 🚫 语音功能暂时下线（GitHub 发布版）： False 时引擎/服务/UI/工具全部停用。
#    恢复方法：改回 True，并配置下方 GPT-SoVITS 相关参数（参考音频路径等）。
VOICE_ENABLED = False

# ── GPT-SoVITS 定制音色（绕过 TTS+DDSP，直接用六花微调模型合成） ──
GPT_SOVITS_URL = "http://127.0.0.1:9880"      # api_v2.py 本地服务地址
GPT_SOVITS_REF_AUDIO = r"F:\GPT-SoVITS\refs\rikka_emotions\【六花-默认】それと、実は私の中にもう一人の人格が.wav"   # 六花参考音频（推理音色条件，neutral 默认）
GPT_SOVITS_REF_TEXT = "それと、実は私の中にもう一人の人格が"  # 参考音频对应文字（务必与音频内容一致）
GPT_SOVITS_TIMEOUT = 180
GPT_SOVITS_SPEED_FACTOR = 0.9   # 合成语速（<1 放慢，>1 加快）。六花素材偏急促，默认放慢 10%
GPT_SOVITS_TEMPERATURE = 0.7    # s1 语义采样温度：服务端默认 1.0，偏高易沙哑/不稳；0.5~0.8 更稳更干净
GPT_SOVITS_TOP_K = 5            # top-k 采样（服务端默认 5）
GPT_SOVITS_TOP_P = 1.0          # top-p 采样（服务端默认 1）
GPT_SOVITS_SAMPLE_STEPS = 32            # s2 采样步数（v4 CFM）：越大越精细圆润、但越慢越吃显存
GPT_SOVITS_REPETITION_PENALTY = 1.35    # 重复惩罚：越大越避免复读/卡词，但可能生硬
GPT_SOVITS_TEXT_SPLIT_METHOD = "cut5"   # 文本切分：cut0=按标点整句 / cut5=智能切分（推荐）

# ── 六花语言 + 情感参考（GPT-SoVITS v4 情感音色） ──
PERSONA_LANGUAGE = "ja"   # 六花回复/语音语言：ja=日语(默认) / zh=中文。设置页可切换，下一条消息生效
GPT_SOVITS_PROMPT_LANG = "ja"   # 所有情感参考音频都是日语片段
# 情感参考音频默认值（neutral 独立处理：跟随 gptsovits_ref_audio/text 的最新配置）。
# 可在 user_config.json 用 gptsovits_emotion_refs 覆盖某个情感，例如：
# "gptsovits_emotion_refs": {"happy": {"audio": "...", "text": "..."}}
_GPT_SOVITS_EMOTION_REF_DEFAULTS = {
    "happy":   {"audio": r"F:\GPT-SoVITS\refs\rikka_emotions\【六花-高兴】わくわくする！わくわくする！わからない！.wav",
                "text": "わくわくする！わくわくする！わからない！"},
    "sad":     {"audio": r"F:\GPT-SoVITS\refs\rikka_emotions\【六花-消沉】でも想像以上、こいつ何を考えているのかわからない.wav",
                "text": "でも想像以上、こいつ何を考えているのかわからない"},
}


def get_gptsovits_emotion_refs():
    """运行时解析情感参考音频，每次合成时取最新配置（避免 import 时绑定旧默认值）。"""
    refs = {name: dict(ref) for name, ref in _GPT_SOVITS_EMOTION_REF_DEFAULTS.items()}
    refs["neutral"] = {"audio": GPT_SOVITS_REF_AUDIO, "text": GPT_SOVITS_REF_TEXT}
    overrides = (_USER_CONFIG or {}).get("gptsovits_emotion_refs") or {}
    if isinstance(overrides, dict):
        for name, ref in overrides.items():
            if isinstance(ref, dict) and name in refs:
                refs[name]["audio"] = str(ref.get("audio") or refs[name]["audio"])
                refs[name]["text"] = str(ref.get("text") or refs[name]["text"])
    return refs

# ── GPT-SoVITS 本地服务（voice_server.py 进程管理） ──
GPT_SOVITS_ROOT = r"F:\GPT-SoVITS\GPT-SoVITS-v4-20250529-nvidia50"   # api_v2.py 整合包根目录
# HOST/PORT 从 GPT_SOVITS_URL 派生（单一真源，避免服务启动地址与客户端地址脱节）
from urllib.parse import urlparse as _gs_urlparse
_gs_parsed = _gs_urlparse(GPT_SOVITS_URL)
GPT_SOVITS_HOST = _gs_parsed.hostname or "127.0.0.1"
GPT_SOVITS_PORT = _gs_parsed.port or 9880
GPT_SOVITS_START_TIMEOUT = 90     # 模型加载约 30-60s，给足余量

VOICE_MAX_CHARS = 80
VOICE_CACHE_DIR = os.path.join(ROOT_DIR, "voice_cache")

_USER_CONFIG = None

CHAT_SETTINGS_DEFAULTS = {
    "chat_max_tokens": 4096,
    "chat_memory_enabled": True,
    "chat_web_search_enabled": True,
    "chat_citations_enabled": True,
}

def _save_autostart(enabled):
    try:
        import sys; startup = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        lnk = os.path.join(startup, "RikkaAI.bat")
        if enabled:
            with open(lnk, "w") as f: f.write(f'@echo off\nstart "" /D "{ROOT_DIR}" "{sys.executable}" "{os.path.join(ROOT_DIR, "main.py")}"\n')
        else:
            if os.path.exists(lnk): os.remove(lnk)
    except: pass


def load_user_config():
    global _USER_CONFIG, API_KEY, MODEL, API_BASE, TEMPERATURE, PROACTIVE_ENABLED, PROACTIVE_INTERVAL, PROACTIVE_PERSIST, PROACTIVE_COOLDOWN, PROACTIVE_SLACK_ENABLED, PROACTIVE_SLACK_PROB, PROACTIVE_SLACK_COOLDOWN, PROACTIVE_QQ_ENABLED, PROACT_DND_START, PROACT_DND_END, PROACTIVE_UNANSWERED_MAX, SCREEN_SENSE_ENABLED, SCREEN_SENSE_INTERVAL_MIN, QQ_SEGMENT_REPLY, QQ_SEGMENT_MAX, QQ_GROUP_MODE, QQ_GROUP_SCORE_THRESHOLD, MEMORY_CUE_ENABLED, MEMORY_CUE_MAX_CANDIDATES, WEEKLY_AUTO_ENABLED, WEEKLY_AUTO_HOUR, WEEKLY_AUTO_RETRIES, DIARY_AUTO_FLOW_ENABLED, DIARY_AUTO_FLOW_MAX, DIARY_AUTO_SUMMARY_ENABLED, DIARY_AUTO_SUMMARY_HOUR, SURF_AUTO_ENABLED, SURF_AUTO_INTERVAL_MIN, SURF_TAGS_PER_ROUND, SURF_SEARCH_LIMIT, SURF_TAG_COOLDOWN_HOURS, SURF_TAG_DECAY_PER_7_DAYS, SURF_REACTION_LIKED, SURF_REACTION_DISLIKED, ROTATION_THRESHOLD, COMPRESSION_ENABLED, COMPRESSION_THRESHOLD, COMPRESSION_KEEP, AUTO_START, SMART_SEARCH_MAX_RESULTS, SMART_SEARCH_MAX_ANALYZE, SMART_SEARCH_MAX_CANDIDATES, SEARXNG_BASE_URL, VISION_API_KEY, VISION_MODEL, VISION_API_BASE, QQ_ALLOWED_USERS, QQ_WS_HOST, QQ_WS_PORT, VOICE_ENABLED, VOICE_MAX_CHARS, PERSONA_LANGUAGE, GPT_SOVITS_URL, GPT_SOVITS_REF_AUDIO, GPT_SOVITS_REF_TEXT, GPT_SOVITS_PROMPT_LANG, GPT_SOVITS_START_TIMEOUT, GPT_SOVITS_SPEED_FACTOR, GPT_SOVITS_TEMPERATURE, GPT_SOVITS_TOP_K, GPT_SOVITS_TOP_P, GPT_SOVITS_SAMPLE_STEPS, GPT_SOVITS_REPETITION_PENALTY, GPT_SOVITS_TEXT_SPLIT_METHOD
    _USER_CONFIG = {}
    API_KEY = secret_store.get("global_api_key", API_KEY)
    VISION_API_KEY = secret_store.get("vision_api_key", VISION_API_KEY)
    if os.path.exists(USER_CONFIG_PATH):
        try:
            with open(USER_CONFIG_PATH, "r", encoding="utf-8") as f: _USER_CONFIG = json.load(f)
            API_KEY = secret_store.get("global_api_key", _USER_CONFIG.get("api_key", API_KEY)); MODEL = _USER_CONFIG.get("model", MODEL)
            API_BASE = _USER_CONFIG.get("api_base", API_BASE); TEMPERATURE = _USER_CONFIG.get("temperature", TEMPERATURE)
            PROACTIVE_ENABLED = _USER_CONFIG.get("proactive_enabled", PROACTIVE_ENABLED)
            PROACTIVE_INTERVAL = _USER_CONFIG.get("proactive_interval", PROACTIVE_INTERVAL)
            PROACTIVE_PERSIST = _USER_CONFIG.get("proactive_persist", PROACTIVE_PERSIST)
            PROACTIVE_COOLDOWN = _USER_CONFIG.get("proactive_cooldown", PROACTIVE_COOLDOWN)
            PROACTIVE_SLACK_ENABLED = _USER_CONFIG.get("proactive_slack_enabled", PROACTIVE_SLACK_ENABLED)
            PROACTIVE_SLACK_PROB = _USER_CONFIG.get("proactive_slack_prob", PROACTIVE_SLACK_PROB)
            PROACTIVE_SLACK_COOLDOWN = _USER_CONFIG.get("proactive_slack_cooldown", PROACTIVE_SLACK_COOLDOWN)
            PROACTIVE_QQ_ENABLED = _USER_CONFIG.get("proactive_qq_enabled", PROACTIVE_QQ_ENABLED)
            PROACT_DND_START = int(_USER_CONFIG.get("proactive_dnd_start", PROACT_DND_START))
            PROACT_DND_END = int(_USER_CONFIG.get("proactive_dnd_end", PROACT_DND_END))
            PROACTIVE_UNANSWERED_MAX = int(_USER_CONFIG.get("proactive_unanswered_max", PROACTIVE_UNANSWERED_MAX))
            SCREEN_SENSE_ENABLED = _USER_CONFIG.get("screen_sense_enabled", SCREEN_SENSE_ENABLED)
            SCREEN_SENSE_INTERVAL_MIN = int(_USER_CONFIG.get("screen_sense_interval_min", SCREEN_SENSE_INTERVAL_MIN))
            QQ_SEGMENT_REPLY = _USER_CONFIG.get("qq_segment_reply", QQ_SEGMENT_REPLY)
            QQ_SEGMENT_MAX = int(_USER_CONFIG.get("qq_segment_max", QQ_SEGMENT_MAX))
            QQ_GROUP_MODE = str(_USER_CONFIG.get("qq_group_mode", QQ_GROUP_MODE))
            QQ_GROUP_SCORE_THRESHOLD = int(_USER_CONFIG.get("qq_group_score_threshold", QQ_GROUP_SCORE_THRESHOLD))
            MEMORY_CUE_ENABLED = _USER_CONFIG.get("memory_cue_enabled", MEMORY_CUE_ENABLED)
            MEMORY_CUE_MAX_CANDIDATES = _USER_CONFIG.get("memory_cue_max_candidates", MEMORY_CUE_MAX_CANDIDATES)
            WEEKLY_AUTO_ENABLED = _USER_CONFIG.get("weekly_auto_enabled", WEEKLY_AUTO_ENABLED)
            WEEKLY_AUTO_HOUR = _USER_CONFIG.get("weekly_auto_hour", WEEKLY_AUTO_HOUR)
            WEEKLY_AUTO_RETRIES = _USER_CONFIG.get("weekly_auto_retries", WEEKLY_AUTO_RETRIES)
            DIARY_AUTO_FLOW_ENABLED = _USER_CONFIG.get("diary_auto_flow_enabled", DIARY_AUTO_FLOW_ENABLED)
            DIARY_AUTO_FLOW_MAX = _USER_CONFIG.get("diary_auto_flow_max", DIARY_AUTO_FLOW_MAX)
            DIARY_AUTO_SUMMARY_ENABLED = _USER_CONFIG.get("diary_auto_summary_enabled", DIARY_AUTO_SUMMARY_ENABLED)
            DIARY_AUTO_SUMMARY_HOUR = int(_USER_CONFIG.get("diary_auto_summary_hour", DIARY_AUTO_SUMMARY_HOUR))
            SURF_AUTO_ENABLED = _USER_CONFIG.get("surf_auto_enabled", SURF_AUTO_ENABLED)
            SURF_AUTO_INTERVAL_MIN = int(_USER_CONFIG.get("surf_auto_interval_min", SURF_AUTO_INTERVAL_MIN))
            SURF_TAGS_PER_ROUND = int(_USER_CONFIG.get("surf_tags_per_round", SURF_TAGS_PER_ROUND))
            SURF_SEARCH_LIMIT = int(_USER_CONFIG.get("surf_search_limit", SURF_SEARCH_LIMIT))
            SURF_TAG_COOLDOWN_HOURS = int(_USER_CONFIG.get("surf_tag_cooldown_hours", SURF_TAG_COOLDOWN_HOURS))
            SURF_TAG_DECAY_PER_7_DAYS = int(_USER_CONFIG.get("surf_tag_decay_per_7_days", SURF_TAG_DECAY_PER_7_DAYS))
            SURF_REACTION_LIKED = int(_USER_CONFIG.get("surf_reaction_liked", SURF_REACTION_LIKED))
            SURF_REACTION_DISLIKED = int(_USER_CONFIG.get("surf_reaction_disliked", SURF_REACTION_DISLIKED))
            ROTATION_THRESHOLD = _USER_CONFIG.get("rotation_threshold", ROTATION_THRESHOLD)
            COMPRESSION_ENABLED = _USER_CONFIG.get("compression_enabled", COMPRESSION_ENABLED)
            COMPRESSION_THRESHOLD = _USER_CONFIG.get("compression_threshold", COMPRESSION_THRESHOLD)
            COMPRESSION_KEEP = _USER_CONFIG.get("compression_keep", COMPRESSION_KEEP)
            AUTO_START = _USER_CONFIG.get("auto_start", AUTO_START)
            SMART_SEARCH_MAX_RESULTS = _USER_CONFIG.get("smart_search_max_results", SMART_SEARCH_MAX_RESULTS)
            SMART_SEARCH_MAX_ANALYZE = _USER_CONFIG.get("smart_search_max_analyze", SMART_SEARCH_MAX_ANALYZE)
            SMART_SEARCH_MAX_CANDIDATES = _USER_CONFIG.get("smart_search_max_candidates", SMART_SEARCH_MAX_CANDIDATES)
            SEARXNG_BASE_URL = _USER_CONFIG.get("searxng_base_url", SEARXNG_BASE_URL)
            VISION_API_KEY = secret_store.get("vision_api_key", _USER_CONFIG.get("vision_api_key", VISION_API_KEY))
            VISION_MODEL = _USER_CONFIG.get("vision_model", VISION_MODEL)
            VISION_API_BASE = _USER_CONFIG.get("vision_api_base", VISION_API_BASE)
            QQ_ALLOWED_USERS = _USER_CONFIG.get("qq_allowed_users", QQ_ALLOWED_USERS)
            QQ_WS_HOST = _USER_CONFIG.get("qq_ws_host", QQ_WS_HOST)
            QQ_WS_PORT = int(_USER_CONFIG.get("qq_ws_port", QQ_WS_PORT))
            VOICE_ENABLED = bool(VOICE_ENABLED and _USER_CONFIG.get("voice_enabled", VOICE_ENABLED))
            VOICE_MAX_CHARS = _USER_CONFIG.get("voice_max_chars", VOICE_MAX_CHARS)
            GPT_SOVITS_URL = _USER_CONFIG.get("gptsovits_url", GPT_SOVITS_URL)
            GPT_SOVITS_REF_AUDIO = _USER_CONFIG.get("gptsovits_ref_audio", GPT_SOVITS_REF_AUDIO)
            GPT_SOVITS_REF_TEXT = _USER_CONFIG.get("gptsovits_ref_text", GPT_SOVITS_REF_TEXT)
            GPT_SOVITS_PROMPT_LANG = _USER_CONFIG.get("gptsovits_prompt_lang", GPT_SOVITS_PROMPT_LANG)
            GPT_SOVITS_START_TIMEOUT = _USER_CONFIG.get("gptsovits_start_timeout", GPT_SOVITS_START_TIMEOUT)
            GPT_SOVITS_SPEED_FACTOR = _USER_CONFIG.get("gptsovits_speed_factor", GPT_SOVITS_SPEED_FACTOR)
            GPT_SOVITS_TEMPERATURE = _USER_CONFIG.get("gptsovits_temperature", GPT_SOVITS_TEMPERATURE)
            GPT_SOVITS_TOP_K = _USER_CONFIG.get("gptsovits_top_k", GPT_SOVITS_TOP_K)
            GPT_SOVITS_TOP_P = _USER_CONFIG.get("gptsovits_top_p", GPT_SOVITS_TOP_P)
            GPT_SOVITS_SAMPLE_STEPS = _USER_CONFIG.get("gptsovits_sample_steps", GPT_SOVITS_SAMPLE_STEPS)
            GPT_SOVITS_REPETITION_PENALTY = _USER_CONFIG.get("gptsovits_repetition_penalty", GPT_SOVITS_REPETITION_PENALTY)
            GPT_SOVITS_TEXT_SPLIT_METHOD = _USER_CONFIG.get("gptsovits_text_split_method", GPT_SOVITS_TEXT_SPLIT_METHOD)
        except: _USER_CONFIG = {}

def save_user_config(updates):
    global _USER_CONFIG, API_KEY, MODEL, API_BASE, TEMPERATURE, PROACTIVE_ENABLED, PROACTIVE_INTERVAL, PROACTIVE_PERSIST, PROACTIVE_COOLDOWN, PROACTIVE_SLACK_ENABLED, PROACTIVE_SLACK_PROB, PROACTIVE_SLACK_COOLDOWN, PROACTIVE_QQ_ENABLED, PROACT_DND_START, PROACT_DND_END, PROACTIVE_UNANSWERED_MAX, SCREEN_SENSE_ENABLED, SCREEN_SENSE_INTERVAL_MIN, QQ_SEGMENT_REPLY, QQ_SEGMENT_MAX, MEMORY_CUE_ENABLED, MEMORY_CUE_MAX_CANDIDATES, WEEKLY_AUTO_ENABLED, WEEKLY_AUTO_HOUR, WEEKLY_AUTO_RETRIES, DIARY_AUTO_FLOW_ENABLED, DIARY_AUTO_FLOW_MAX, DIARY_AUTO_SUMMARY_ENABLED, DIARY_AUTO_SUMMARY_HOUR, SURF_AUTO_ENABLED, SURF_AUTO_INTERVAL_MIN, SURF_TAGS_PER_ROUND, SURF_SEARCH_LIMIT, SURF_TAG_COOLDOWN_HOURS, SURF_TAG_DECAY_PER_7_DAYS, SURF_REACTION_LIKED, SURF_REACTION_DISLIKED, ROTATION_THRESHOLD, COMPRESSION_ENABLED, COMPRESSION_THRESHOLD, COMPRESSION_KEEP, AUTO_START, SMART_SEARCH_MAX_RESULTS, SMART_SEARCH_MAX_ANALYZE, SMART_SEARCH_MAX_CANDIDATES, VISION_API_KEY, VISION_MODEL, VISION_API_BASE, QQ_ALLOWED_USERS, VOICE_ENABLED, VOICE_MAX_CHARS, PERSONA_LANGUAGE, GPT_SOVITS_URL, GPT_SOVITS_REF_AUDIO, GPT_SOVITS_REF_TEXT, GPT_SOVITS_PROMPT_LANG, GPT_SOVITS_START_TIMEOUT, GPT_SOVITS_SPEED_FACTOR, GPT_SOVITS_TEMPERATURE, GPT_SOVITS_TOP_K, GPT_SOVITS_TOP_P, GPT_SOVITS_SAMPLE_STEPS, GPT_SOVITS_REPETITION_PENALTY, GPT_SOVITS_TEXT_SPLIT_METHOD
    try:
        if _USER_CONFIG is None: _USER_CONFIG = {}
        updates = dict(updates or {})
        for key, ref in (("api_key", "global_api_key"), ("vision_api_key", "vision_api_key")):
            if key in updates:
                value = str(updates.pop(key) or "").strip()
                if value and not secret_store.set_secret(ref, value, overwrite=True):
                    return False
                runtime_key = {
                    "api_key": "API_KEY",
                    "vision_api_key": "VISION_API_KEY",
                }[key]
                globals()[runtime_key] = value
        nested = updates.get("sleep_compute_settings")
        if isinstance(nested, dict) and isinstance(nested.get("model_preset"), dict):
            preset = dict(nested["model_preset"])
            if preset.get("api_key"):
                ref = preset.get("secret_ref") or secret_store.preset_name(preset.get("name") or preset.get("model"))
                if not secret_store.set_secret(ref, preset["api_key"], overwrite=True):
                    return False
                preset["secret_ref"] = ref
            preset.pop("api_key", None)
            nested["model_preset"] = preset
            updates["sleep_compute_settings"] = nested
        _USER_CONFIG.update(updates)
        mapping = [("api_key","API_KEY"),("model","MODEL"),("api_base","API_BASE"),("temperature","TEMPERATURE"),
                   ("proactive_enabled","PROACTIVE_ENABLED"),("proactive_interval","PROACTIVE_INTERVAL"),
                   ("proactive_persist","PROACTIVE_PERSIST"),("proactive_cooldown","PROACTIVE_COOLDOWN"),
                   ("proactive_slack_enabled","PROACTIVE_SLACK_ENABLED"),("proactive_slack_prob","PROACTIVE_SLACK_PROB"),("proactive_slack_cooldown","PROACTIVE_SLACK_COOLDOWN"),("proactive_qq_enabled","PROACTIVE_QQ_ENABLED"),("proactive_dnd_start","PROACT_DND_START"),("proactive_dnd_end","PROACT_DND_END"),("proactive_unanswered_max","PROACTIVE_UNANSWERED_MAX"),("screen_sense_enabled","SCREEN_SENSE_ENABLED"),("screen_sense_interval_min","SCREEN_SENSE_INTERVAL_MIN"),("qq_segment_reply","QQ_SEGMENT_REPLY"),("qq_segment_max","QQ_SEGMENT_MAX"),("qq_group_mode","QQ_GROUP_MODE"),("qq_group_score_threshold","QQ_GROUP_SCORE_THRESHOLD"),("memory_cue_enabled","MEMORY_CUE_ENABLED"),("memory_cue_max_candidates","MEMORY_CUE_MAX_CANDIDATES"),("weekly_auto_enabled","WEEKLY_AUTO_ENABLED"),("weekly_auto_hour","WEEKLY_AUTO_HOUR"),("weekly_auto_retries","WEEKLY_AUTO_RETRIES"),("diary_auto_flow_enabled","DIARY_AUTO_FLOW_ENABLED"),("diary_auto_flow_max","DIARY_AUTO_FLOW_MAX"),("diary_auto_summary_enabled","DIARY_AUTO_SUMMARY_ENABLED"),("diary_auto_summary_hour","DIARY_AUTO_SUMMARY_HOUR"),
                   ("surf_auto_enabled","SURF_AUTO_ENABLED"),("surf_auto_interval_min","SURF_AUTO_INTERVAL_MIN"),
                   ("surf_tags_per_round","SURF_TAGS_PER_ROUND"),
                   ("surf_search_limit","SURF_SEARCH_LIMIT"),("surf_tag_cooldown_hours","SURF_TAG_COOLDOWN_HOURS"),
                   ("surf_tag_decay_per_7_days","SURF_TAG_DECAY_PER_7_DAYS"),("surf_reaction_liked","SURF_REACTION_LIKED"),
                   ("surf_reaction_disliked","SURF_REACTION_DISLIKED"),
                   ("rotation_threshold","ROTATION_THRESHOLD"),
                   ("compression_enabled","COMPRESSION_ENABLED"),("compression_threshold","COMPRESSION_THRESHOLD"),
                   ("compression_keep","COMPRESSION_KEEP"),("auto_start","AUTO_START"),
                   ("smart_search_max_results","SMART_SEARCH_MAX_RESULTS"),
                   ("smart_search_max_analyze","SMART_SEARCH_MAX_ANALYZE"),
                   ("smart_search_max_candidates","SMART_SEARCH_MAX_CANDIDATES"),
                   ("searxng_base_url","SEARXNG_BASE_URL"),
                   ("vision_api_key","VISION_API_KEY"),("vision_model","VISION_MODEL"),("vision_api_base","VISION_API_BASE"),
                   ("qq_allowed_users","QQ_ALLOWED_USERS"),
                   ("qq_ws_host","QQ_WS_HOST"),("qq_ws_port","QQ_WS_PORT"),
                   ("voice_enabled","VOICE_ENABLED"),("voice_max_chars","VOICE_MAX_CHARS"),
                   ("persona_language","PERSONA_LANGUAGE"),
                   ("gptsovits_url","GPT_SOVITS_URL"),("gptsovits_ref_audio","GPT_SOVITS_REF_AUDIO"),
                   ("gptsovits_ref_text","GPT_SOVITS_REF_TEXT"),("gptsovits_prompt_lang","GPT_SOVITS_PROMPT_LANG"),
                   ("gptsovits_start_timeout","GPT_SOVITS_START_TIMEOUT"),
                   ("gptsovits_speed_factor","GPT_SOVITS_SPEED_FACTOR"),
                   ("gptsovits_temperature","GPT_SOVITS_TEMPERATURE"),
                   ("gptsovits_top_k","GPT_SOVITS_TOP_K"),("gptsovits_top_p","GPT_SOVITS_TOP_P"),
                   ("gptsovits_sample_steps","GPT_SOVITS_SAMPLE_STEPS"),
                   ("gptsovits_repetition_penalty","GPT_SOVITS_REPETITION_PENALTY"),
                   ("gptsovits_text_split_method","GPT_SOVITS_TEXT_SPLIT_METHOD")]
        for k,v in mapping:
            if k in updates: globals()[v] = updates[k]
        if "gptsovits_url" in updates:
            # URL 被覆盖时同步派生 HOST/PORT，保持服务启动地址与客户端一致
            global GPT_SOVITS_HOST, GPT_SOVITS_PORT
            _gs_re = _gs_urlparse(GPT_SOVITS_URL)
            GPT_SOVITS_HOST = _gs_re.hostname or "127.0.0.1"
            GPT_SOVITS_PORT = _gs_re.port or 9880
        if "auto_start" in updates: _save_autostart(updates["auto_start"])
        os.makedirs(USER_CONFIG_DIR, exist_ok=True)
        with open(USER_CONFIG_PATH, "w", encoding="utf-8") as f: json.dump(_USER_CONFIG, f, ensure_ascii=False, indent=2)
        return True
    except: return False

def get_chat_settings():
    if _USER_CONFIG is None:
        load_user_config()
    values = dict(CHAT_SETTINGS_DEFAULTS)
    if _USER_CONFIG:
        for key in values:
            values[key] = _USER_CONFIG.get(key, values[key])
    values["temperature"] = TEMPERATURE
    return values


# ── 识图 API 预设 ──
def get_vision_presets():
    """Return vision presets with keys resolved from the local secret store."""
    result = []
    for raw in (_USER_CONFIG.get("vision_presets", []) if _USER_CONFIG else []):
        preset = dict(raw)
        ref = preset.get("secret_ref") or secret_store.vision_preset_name(preset.get("name"))
        preset["secret_ref"] = ref
        # ``api_key`` remains as a read-only compatibility fallback for old configs.
        preset["api_key"] = secret_store.get(ref, preset.get("api_key", ""))
        result.append(preset)
    return result


def get_active_vision_preset():
    active_name = (_USER_CONFIG or {}).get("active_vision_preset", "")
    return next(
        (preset for preset in get_vision_presets() if preset.get("name") == active_name),
        None,
    )


def add_vision_preset(name, api_key, model, api_base):
    """Save one vision provider; its API key never enters user_config.json."""
    global _USER_CONFIG
    if _USER_CONFIG is None:
        load_user_config()
    name = str(name or "").strip()
    if not name:
        return False
    presets = _USER_CONFIG.setdefault("vision_presets", [])
    existing = next((preset for preset in presets if preset.get("name") == name), None)
    ref = (
        existing.get("secret_ref") or secret_store.vision_preset_name(name)
        if existing else secret_store.new_preset_ref("vision_preset")
    )
    api_key = str(api_key or "").strip()
    if api_key and not secret_store.set_secret(ref, api_key, overwrite=True):
        return False
    value = {
        "name": name,
        "secret_ref": ref,
        "model": str(model or "").strip(),
        "api_base": str(api_base or "").strip(),
    }
    if existing:
        existing.update(value)
    else:
        presets.append(value)
    return save_user_config({})


def delete_vision_preset(name):
    global VISION_API_KEY, VISION_MODEL, VISION_API_BASE
    if _USER_CONFIG is None:
        load_user_config()
    was_active = _USER_CONFIG.get("active_vision_preset") == name
    removed = [preset for preset in _USER_CONFIG.get("vision_presets", []) if preset.get("name") == name]
    _USER_CONFIG["vision_presets"] = [
        preset for preset in _USER_CONFIG.get("vision_presets", []) if preset.get("name") != name
    ]
    for preset in removed:
        ref = preset.get("secret_ref") or secret_store.vision_preset_name(preset.get("name"))
        secret_store.delete(ref)
    if was_active:
        _USER_CONFIG["active_vision_preset"] = ""
        secret_store.delete("vision_api_key")
        VISION_API_KEY = ""
        VISION_MODEL = ""
        VISION_API_BASE = ""
        _USER_CONFIG["vision_model"] = VISION_MODEL
        _USER_CONFIG["vision_api_base"] = VISION_API_BASE
    return save_user_config({})


def set_active_vision_preset(name):
    """Apply a selected vision provider to the runtime vision configuration."""
    preset = next((item for item in get_vision_presets() if item.get("name") == name), None)
    if not preset or not all(preset.get(key) for key in ("api_key", "model", "api_base")):
        return False
    return save_user_config({
        "active_vision_preset": preset["name"],
        "vision_api_key": preset["api_key"],
        "vision_model": preset.get("model", ""),
        "vision_api_base": preset.get("api_base", ""),
    })

def reload_from_file():
    global _USER_CONFIG, API_KEY, MODEL, API_BASE, TEMPERATURE, PROACTIVE_ENABLED, PROACTIVE_INTERVAL, PROACTIVE_PERSIST, PROACTIVE_COOLDOWN, PROACTIVE_SLACK_ENABLED, PROACTIVE_SLACK_PROB, ROTATION_THRESHOLD, COMPRESSION_ENABLED, COMPRESSION_THRESHOLD, COMPRESSION_KEEP, AUTO_START, SMART_SEARCH_MAX_RESULTS, SMART_SEARCH_MAX_ANALYZE, SMART_SEARCH_MAX_CANDIDATES, SEARXNG_BASE_URL, VISION_API_KEY, VISION_MODEL, VISION_API_BASE, QQ_ALLOWED_USERS, PERSONA_LANGUAGE, GPT_SOVITS_URL, GPT_SOVITS_REF_AUDIO, GPT_SOVITS_REF_TEXT, GPT_SOVITS_PROMPT_LANG, GPT_SOVITS_START_TIMEOUT, GPT_SOVITS_SPEED_FACTOR, GPT_SOVITS_TOP_K, GPT_SOVITS_TOP_P, GPT_SOVITS_SAMPLE_STEPS, GPT_SOVITS_REPETITION_PENALTY, GPT_SOVITS_TEXT_SPLIT_METHOD
    if os.path.exists(USER_CONFIG_PATH):
        try:
            with open(USER_CONFIG_PATH, "r", encoding="utf-8") as f: _USER_CONFIG = json.load(f)
            load_user_config()
        except: pass

# ── QQ 权限辅助 ──
def get_qq_allowed_users():
    """获取允许操作电脑的QQ号列表"""
    return list(QQ_ALLOWED_USERS) if QQ_ALLOWED_USERS else []

def set_qq_allowed_users(user_ids):
    """设置允许操作电脑的QQ号列表"""
    global QQ_ALLOWED_USERS
    QQ_ALLOWED_USERS = list(user_ids) if user_ids else []
    save_user_config({"qq_allowed_users": QQ_ALLOWED_USERS})

def set_voice_enabled(enabled):
    """开/关六花语音（静音按钮用）"""
    global VOICE_ENABLED
    VOICE_ENABLED = bool(enabled)
    save_user_config({"voice_enabled": VOICE_ENABLED})

def load_last_session(): return _USER_CONFIG.get("last_session_id") if _USER_CONFIG else None

# ── 对话 API 预设 ──
def get_presets():
    result = []
    for raw in (_USER_CONFIG.get("presets", []) if _USER_CONFIG else []):
        preset = dict(raw)
        ref = preset.get("secret_ref") or (secret_store.preset_name(preset.get("name")) if preset.get("name") else "")
        preset["secret_ref"] = ref
        preset["api_key"] = secret_store.get(ref, preset.get("api_key", "")) if ref else preset.get("api_key", "")
        result.append(preset)
    return result
def add_preset(name, ak, md, ab):
    if _USER_CONFIG is None:
        load_user_config()
    if _USER_CONFIG is None:
        return False
    name = str(name or "").strip()
    if not name:
        return False
    p = _USER_CONFIG.setdefault("presets", [])
    existing = next((preset for preset in p if preset.get("name") == name), None)
    ref = (
        existing.get("secret_ref") or secret_store.preset_name(name)
        if existing else secret_store.new_preset_ref()
    )
    if ak and not secret_store.set_secret(ref, ak, overwrite=True):
        return False
    value = {"name":name,"secret_ref":ref,"model":md,"api_base":ab}
    if existing:
        existing.update(value)
    else:
        p.append(value)
    return save_user_config({})
def delete_preset(name):
    if _USER_CONFIG is None:
        load_user_config()
    if _USER_CONFIG is None:
        return False
    removed = [p for p in _USER_CONFIG.get("presets",[]) if p.get("name") == name]
    _USER_CONFIG["presets"] = [p for p in _USER_CONFIG.get("presets",[]) if p.get("name") != name]
    for preset in removed:
        ref = preset.get("secret_ref") or secret_store.preset_name(preset.get("name"))
        if ref: secret_store.delete(ref)
    return save_user_config({})


# ── 生图 API 预设 ──
def get_image_generation_presets():
    result = []
    for raw in (_USER_CONFIG.get("image_generation_presets", []) if _USER_CONFIG else []):
        preset = dict(raw)
        ref = preset.get("secret_ref") or secret_store.image_generation_preset_name(preset.get("name"))
        preset["secret_ref"] = ref
        preset["api_key"] = secret_store.get(ref, preset.get("api_key", ""))
        result.append(preset)
    return result


def get_active_image_generation_preset():
    active_name = (_USER_CONFIG or {}).get("active_image_generation_preset", "")
    return next(
        (preset for preset in get_image_generation_presets() if preset.get("name") == active_name),
        None,
    )


def add_image_generation_preset(name, api_key, model, api_base):
    if _USER_CONFIG is None:
        load_user_config()
    name = str(name or "").strip()
    if not name:
        return False
    presets = _USER_CONFIG.setdefault("image_generation_presets", [])
    existing = next((preset for preset in presets if preset.get("name") == name), None)
    ref = (
        existing.get("secret_ref") or secret_store.image_generation_preset_name(name)
        if existing else secret_store.new_preset_ref("image_generation_preset")
    )
    api_key = str(api_key or "").strip()
    if api_key and not secret_store.set_secret(ref, api_key, overwrite=True):
        return False
    value = {"name": name, "secret_ref": ref, "model": str(model or "").strip(), "api_base": str(api_base or "").strip()}
    if existing:
        existing.update(value)
    else:
        presets.append(value)
    if not _USER_CONFIG.get("active_image_generation_preset"):
        _USER_CONFIG["active_image_generation_preset"] = name
    return save_user_config({})


def delete_image_generation_preset(name):
    if _USER_CONFIG is None:
        load_user_config()
    removed = [preset for preset in _USER_CONFIG.get("image_generation_presets", []) if preset.get("name") == name]
    _USER_CONFIG["image_generation_presets"] = [
        preset for preset in _USER_CONFIG.get("image_generation_presets", []) if preset.get("name") != name
    ]
    for preset in removed:
        if preset.get("secret_ref"):
            secret_store.delete(preset["secret_ref"])
    if _USER_CONFIG.get("active_image_generation_preset") == name:
        remaining = _USER_CONFIG["image_generation_presets"]
        _USER_CONFIG["active_image_generation_preset"] = remaining[0].get("name", "") if remaining else ""
    return save_user_config({})


def set_active_image_generation_preset(name):
    if not any(preset.get("name") == name for preset in get_image_generation_presets()):
        return False
    return save_user_config({"active_image_generation_preset": name})


def get_tags(): return _USER_CONFIG.get("interest_tags", []) if _USER_CONFIG else []
def add_tag(t):
    if not _USER_CONFIG: return
    ts = _USER_CONFIG.setdefault("interest_tags", [])
    if t not in ts: ts.append(t); save_user_config({})
def remove_tag(t):
    if not _USER_CONFIG: return
    ts = _USER_CONFIG.get("interest_tags", [])
    if t in ts: ts.remove(t); save_user_config({})
def save_last_summary(s):
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    with open(os.path.join(SUMMARY_DIR, f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"), "w", encoding="utf-8") as f: f.write(s)
def load_last_summary():
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    for fname in sorted(os.listdir(SUMMARY_DIR), reverse=True):
        if fname.startswith("summary_") and fname.endswith(".txt"):
            with open(os.path.join(SUMMARY_DIR, fname), "r", encoding="utf-8") as f: return f.read().strip()
    return ""


# ── 🆕 Sleep-time Compute 设置 ──
SLEEP_COMPUTE_PRESET_SECRET = "sleep_compute_model_preset"  # 当前方案密钥在凭据管理器中的引用名
SLEEP_COMPUTE_DEFAULTS = {
    "enabled": True,
    "execution_time": "23:00",
    "lookback_days": 7,
    # 不设默认模型：未选择任何方案时跟随主对话模型（cfg.MODEL）
}

def get_sleep_compute_settings():
    """获取 Sleep-time Compute 设置（model_preset 的 api_key 从凭据管理器解析）。"""
    if _USER_CONFIG is None:
        load_user_config()
    settings = dict(SLEEP_COMPUTE_DEFAULTS)
    if _USER_CONFIG and "sleep_compute" in _USER_CONFIG:
        settings.update(_USER_CONFIG["sleep_compute"])
    preset = settings.get("model_preset")
    if isinstance(preset, dict):
        preset = dict(preset)
        ref = preset.get("secret_ref") or SLEEP_COMPUTE_PRESET_SECRET
        preset["api_key"] = secret_store.get(ref, preset.get("api_key", "")) or ""
        preset["secret_ref"] = ref
        settings["model_preset"] = preset
    return settings

def save_sleep_compute_settings(settings):
    """保存 Sleep-time Compute 设置；model_preset 的 api_key 只写入凭据管理器。"""
    if _USER_CONFIG is None:
        load_user_config()
    settings = dict(settings or {})
    preset = settings.get("model_preset")
    if isinstance(preset, dict):
        preset = dict(preset)
        api_key = str(preset.pop("api_key", "") or "").strip()
        ref = str(preset.get("secret_ref") or "").strip() or SLEEP_COMPUTE_PRESET_SECRET
        if api_key and not secret_store.set_secret(ref, api_key, overwrite=True):
            return False
        preset["secret_ref"] = ref
        settings["model_preset"] = preset
    if _USER_CONFIG is not None:
        _USER_CONFIG["sleep_compute"] = settings
        return save_user_config({})
    return False

def get_sleep_compute_custom_models():
    """自定义记忆整合模型方案列表（api_key 从凭据管理器解析，JSON 不落盘）。"""
    result = []
    for raw in (_USER_CONFIG.get("sleep_compute_custom_models", []) if _USER_CONFIG else []):
        if not isinstance(raw, dict):
            continue
        preset = dict(raw)
        ref = preset.get("secret_ref") or secret_store.sleep_preset_name(preset.get("name"))
        preset["secret_ref"] = ref
        preset["api_key"] = secret_store.get(ref, preset.get("api_key", "")) or ""
        result.append(preset)
    return result

def save_sleep_compute_custom_models(presets):
    """保存自定义模型方案；api_key 写入凭据管理器，JSON 里只保留 secret_ref。"""
    if _USER_CONFIG is None:
        load_user_config()
    cleaned = []
    for raw in presets or []:
        if not isinstance(raw, dict):
            continue
        preset = dict(raw)
        api_key = str(preset.pop("api_key", "") or "").strip()
        name = str(preset.get("name") or "").strip()
        ref = str(preset.get("secret_ref") or "").strip() or secret_store.sleep_preset_name(name)
        if api_key and not secret_store.set_secret(ref, api_key, overwrite=True):
            return False
        preset["secret_ref"] = ref
        cleaned.append(preset)
    if _USER_CONFIG is not None:
        _USER_CONFIG["sleep_compute_custom_models"] = cleaned
        return save_user_config({})
    return False


# ── 🆕 升级特性开关（Phase 0-5）─────────────────────────────────────────────
# 每个新能力一个开关，默认"谨慎关闭"（不影响现有主链路），可在 user_config.json 覆盖。
# 通过 brain/features.py 统一读取；设置页也可持久化这些键。
UPGRADE_FLAGS_DEFAULTS = {
    # Phase 0
    "costlog_enabled": True,            # 执行记录 & token/成本核算
    # Phase 1 记忆层
    "memory_markdown_enabled": True,     # Markdown 真源记忆（可 git/可迁移）
    "memory_surprise_weight_enabled": True,  # surprise 加权遗忘
    "memory_gap_analysis_enabled": True,     # gap analysis（告诉契约者"我还不知道什么"）
    "memory_orthogonal_tags_enabled": True,  # 正交多维标签检索(user/agent/app/project/session)
    "memory_wiki_enabled": True,             # 知识 wiki 自动梳理
    "memory_semantic_enabled": True,         # 语义向量召回（复用 vector_memory）
    # Phase 2 后台做梦/定时/拉取
    "dream_enabled": True,               # 后台蒸馏/做梦引擎
    "dream_interval_hours": 6,           # 做梦运行间隔（小时）
    "dream_consolidate_enabled": True,   # 整合记忆/消解矛盾/更新画像与图谱
    "cron_enabled": True,                # 自然语言定时自动化
    "autofetch_enabled": True,           # 个人数据自动拉取（邮箱/日历等）
    "autofetch_interval_min": 20,        # 自动拉取间隔（分钟）
    # Phase 3 情感 + 主动决策
    "emotion_needs_enabled": True,       # 需求体系（社交/掌控/新奇/休息）+ 精力池 + 孤独感
    "decision_planner_enabled": True,    # 概率规划器（前置条件 + P(success) + 分支）
    # Phase 4 外部世界
    "mcp_enabled": True,                 # MCP client（接入外部工具/服务器）
    # Phase 5 稳健与效率
    "tool_compress_enabled": True,       # TokenJuice 式工具输出压缩
    "split_reply_enabled": False,        # 📱 莲心式分段发送：默认关闭（会把回复拆碎、暴露内部叙述，已停用）
    "privacy_mode_enabled": False,       # 隐私模式：所有推理不出机
}

_UPGRADE_FLAGS = {}


def get_upgrade_flag(name, default=None):
    """取升级开关当前值。未初始化时懒加载。"""
    if name not in _UPGRADE_FLAGS and default is None:
        default = UPGRADE_FLAGS_DEFAULTS.get(name)
    if name not in _UPGRADE_FLAGS:
        # 尚未 load（例如被外部在 import 早期调用）：回退默认值
        return UPGRADE_FLAGS_DEFAULTS.get(name, default)
    return _UPGRADE_FLAGS[name]


def get_all_upgrade_flags() -> dict:
    """当前全部升级开关快照。"""
    if not _UPGRADE_FLAGS:
        load_upgrade_flags()
    return dict(_UPGRADE_FLAGS)


def load_upgrade_flags():
    """从 user_config 读取覆盖值，叠加默认值。"""
    global _UPGRADE_FLAGS
    if _USER_CONFIG is None:
        load_user_config()
    merged = dict(UPGRADE_FLAGS_DEFAULTS)
    if _USER_CONFIG:
        for k in UPGRADE_FLAGS_DEFAULTS:
            if k in _USER_CONFIG:
                merged[k] = _USER_CONFIG.get(k, UPGRADE_FLAGS_DEFAULTS[k])
    _UPGRADE_FLAGS = merged


def save_upgrade_flags(updates):
    """更新并持久化一批升级开关。返回是否成功。"""
    global _UPGRADE_FLAGS
    if not _UPGRADE_FLAGS:
        load_upgrade_flags()
    updates = dict(updates or {})
    for k, v in updates.items():
        if k in UPGRADE_FLAGS_DEFAULTS:
            _UPGRADE_FLAGS[k] = v
    # 写回 user_config.json（save_user_config 会把未识别键也存进 JSON）
    return save_user_config(updates)


def in_dnd(hour=None):
    """免打扰时段判断（PROACT_DND_START..END，支持跨午夜）。内驱/窥屏/概率决策共用。"""
    import datetime as _dt
    hour = _dt.datetime.now().hour if hour is None else int(hour)
    start = int(globals().get("PROACT_DND_START", 23))
    end = int(globals().get("PROACT_DND_END", 8))
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


load_user_config()
load_upgrade_flags()
