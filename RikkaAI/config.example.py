"""
RikkaAI - 全局配置
"""
import os, json
from datetime import datetime

APP_NAME = "RikkaAI"; APP_VERSION = "0.3.0"
WINDOW_WIDTH = 1000; WINDOW_HEIGHT = 700; WINDOW_MIN_WIDTH = 800; WINDOW_MIN_HEIGHT = 600

MODEL = "deepseek-v4-flash"; API_BASE = "https://api.deepseek.com/v1"
API_KEY = "your-api-key-here"; TEMPERATURE = 0.8

PROACTIVE_ENABLED = True; PROACTIVE_INTERVAL = 15; PROACTIVE_PERSIST = 3; PROACTIVE_COOLDOWN = 60
PROACTIVE_SLACK_ENABLED = True; PROACTIVE_SLACK_PROB = 30
ROTATION_THRESHOLD = 20
COMPRESSION_ENABLED = True; COMPRESSION_THRESHOLD = 30; COMPRESSION_KEEP = 20
AUTO_START = False
SEARXNG_BASE_URL = "http://localhost:8080"

# 智能搜图设置
SMART_SEARCH_MAX_RESULTS = 3       # 返回几张图（1-10）
SMART_SEARCH_MAX_ANALYZE = 10      # 最多看几张候选图（3-30）
SMART_SEARCH_MAX_CANDIDATES = 20   # 从SearXNG取多少候选（5-50）

CHARACTER_PANEL_WIDTH = 220
CHARACTER_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "assets", "images", "character_full.png")

ROOT_DIR = os.path.dirname(__file__)
ASSETS_DIR = os.path.join(ROOT_DIR, "assets"); IMAGES_DIR = os.path.join(ASSETS_DIR, "images")
STYLES_DIR = os.path.join(ASSETS_DIR, "styles")
MEMORY_DIR = os.path.join(ROOT_DIR, "memory_data")
USER_CONFIG_DIR = os.path.join(ROOT_DIR, "memory_data"); USER_CONFIG_PATH = os.path.join(USER_CONFIG_DIR, "user_config.json")
DIARY_DIR = os.path.join(ROOT_DIR, "diaries"); SUMMARY_DIR = os.path.join(ROOT_DIR, "summaries")
MEMORIES_DIR = os.path.join(ROOT_DIR, "memories"); IMAGES_DIR_ROOT = os.path.join(ROOT_DIR, "images"); IMAGES_SENT_DIR = os.path.join(IMAGES_DIR_ROOT, "sent"); IMAGES_RECEIVED_DIR = os.path.join(IMAGES_DIR_ROOT, "received"); SCREENSHOTS_DIR = os.path.join(IMAGES_DIR_ROOT, "screenshots"); IMAGES_DOWNLOADED_DIR = os.path.join(IMAGES_DIR_ROOT, "downloaded")
CONVERSATIONS_DIR = os.path.join(ROOT_DIR, "conversations")

_USER_CONFIG = None

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
    global _USER_CONFIG, API_KEY, MODEL, API_BASE, TEMPERATURE, PROACTIVE_ENABLED, PROACTIVE_INTERVAL, PROACTIVE_PERSIST, PROACTIVE_COOLDOWN, PROACTIVE_SLACK_ENABLED, PROACTIVE_SLACK_PROB, ROTATION_THRESHOLD, COMPRESSION_ENABLED, COMPRESSION_THRESHOLD, COMPRESSION_KEEP, AUTO_START, SMART_SEARCH_MAX_RESULTS, SMART_SEARCH_MAX_ANALYZE, SMART_SEARCH_MAX_CANDIDATES
    _USER_CONFIG = {}
    if os.path.exists(USER_CONFIG_PATH):
        try:
            with open(USER_CONFIG_PATH, "r", encoding="utf-8") as f: _USER_CONFIG = json.load(f)
            API_KEY = _USER_CONFIG.get("api_key", API_KEY); MODEL = _USER_CONFIG.get("model", MODEL)
            API_BASE = _USER_CONFIG.get("api_base", API_BASE); TEMPERATURE = _USER_CONFIG.get("temperature", TEMPERATURE)
            PROACTIVE_ENABLED = _USER_CONFIG.get("proactive_enabled", PROACTIVE_ENABLED)
            PROACTIVE_INTERVAL = _USER_CONFIG.get("proactive_interval", PROACTIVE_INTERVAL)
            PROACTIVE_PERSIST = _USER_CONFIG.get("proactive_persist", PROACTIVE_PERSIST)
            PROACTIVE_COOLDOWN = _USER_CONFIG.get("proactive_cooldown", PROACTIVE_COOLDOWN)
            PROACTIVE_SLACK_ENABLED = _USER_CONFIG.get("proactive_slack_enabled", PROACTIVE_SLACK_ENABLED)
            PROACTIVE_SLACK_PROB = _USER_CONFIG.get("proactive_slack_prob", PROACTIVE_SLACK_PROB)
            ROTATION_THRESHOLD = _USER_CONFIG.get("rotation_threshold", ROTATION_THRESHOLD)
            COMPRESSION_ENABLED = _USER_CONFIG.get("compression_enabled", COMPRESSION_ENABLED)
            COMPRESSION_THRESHOLD = _USER_CONFIG.get("compression_threshold", COMPRESSION_THRESHOLD)
            COMPRESSION_KEEP = _USER_CONFIG.get("compression_keep", COMPRESSION_KEEP)
            AUTO_START = _USER_CONFIG.get("auto_start", AUTO_START)
            SMART_SEARCH_MAX_RESULTS = _USER_CONFIG.get("smart_search_max_results", SMART_SEARCH_MAX_RESULTS)
            SMART_SEARCH_MAX_ANALYZE = _USER_CONFIG.get("smart_search_max_analyze", SMART_SEARCH_MAX_ANALYZE)
            SMART_SEARCH_MAX_CANDIDATES = _USER_CONFIG.get("smart_search_max_candidates", SMART_SEARCH_MAX_CANDIDATES)
        except: _USER_CONFIG = {}

def save_user_config(updates):
    global _USER_CONFIG, API_KEY, MODEL, API_BASE, TEMPERATURE, PROACTIVE_ENABLED, PROACTIVE_INTERVAL, PROACTIVE_PERSIST, PROACTIVE_COOLDOWN, PROACTIVE_SLACK_ENABLED, PROACTIVE_SLACK_PROB, ROTATION_THRESHOLD, COMPRESSION_ENABLED, COMPRESSION_THRESHOLD, COMPRESSION_KEEP, AUTO_START, SMART_SEARCH_MAX_RESULTS, SMART_SEARCH_MAX_ANALYZE, SMART_SEARCH_MAX_CANDIDATES
    try:
        if _USER_CONFIG is None: _USER_CONFIG = {}
        _USER_CONFIG.update(updates)
        mapping = [("api_key","API_KEY"),("model","MODEL"),("api_base","API_BASE"),("temperature","TEMPERATURE"),
                   ("proactive_enabled","PROACTIVE_ENABLED"),("proactive_interval","PROACTIVE_INTERVAL"),
                   ("proactive_persist","PROACTIVE_PERSIST"),("proactive_cooldown","PROACTIVE_COOLDOWN"),
                   ("proactive_slack_enabled","PROACTIVE_SLACK_ENABLED"),("proactive_slack_prob","PROACTIVE_SLACK_PROB"),
                   ("rotation_threshold","ROTATION_THRESHOLD"),
                   ("compression_enabled","COMPRESSION_ENABLED"),("compression_threshold","COMPRESSION_THRESHOLD"),
                   ("compression_keep","COMPRESSION_KEEP"),("auto_start","AUTO_START"),
                   ("smart_search_max_results","SMART_SEARCH_MAX_RESULTS"),
                   ("smart_search_max_analyze","SMART_SEARCH_MAX_ANALYZE"),
                   ("smart_search_max_candidates","SMART_SEARCH_MAX_CANDIDATES")]
        for k,v in mapping:
            if k in updates: globals()[v] = updates[k]
        if "auto_start" in updates: _save_autostart(updates["auto_start"])
        os.makedirs(USER_CONFIG_DIR, exist_ok=True)
        with open(USER_CONFIG_PATH, "w", encoding="utf-8") as f: json.dump(_USER_CONFIG, f, ensure_ascii=False, indent=2)
        return True
    except: return False

def reload_from_file():
    global _USER_CONFIG, API_KEY, MODEL, API_BASE, TEMPERATURE, PROACTIVE_ENABLED, PROACTIVE_INTERVAL, PROACTIVE_PERSIST, PROACTIVE_COOLDOWN, PROACTIVE_SLACK_ENABLED, PROACTIVE_SLACK_PROB, ROTATION_THRESHOLD, COMPRESSION_ENABLED, COMPRESSION_THRESHOLD, COMPRESSION_KEEP, AUTO_START, SMART_SEARCH_MAX_RESULTS, SMART_SEARCH_MAX_ANALYZE, SMART_SEARCH_MAX_CANDIDATES
    if os.path.exists(USER_CONFIG_PATH):
        try:
            with open(USER_CONFIG_PATH, "r", encoding="utf-8") as f: _USER_CONFIG = json.load(f)
            load_user_config()
        except: pass

def load_last_session(): return _USER_CONFIG.get("last_session_id") if _USER_CONFIG else None
def get_presets(): return _USER_CONFIG.get("presets", []) if _USER_CONFIG else []
def add_preset(name, ak, md, ab):
    if not _USER_CONFIG: return
    p = _USER_CONFIG.setdefault("presets", [])
    for x in p:
        if x["name"] == name: x.update({"api_key":ak,"model":md,"api_base":ab}); break
    else: p.append({"name":name,"api_key":ak,"model":md,"api_base":ab})
    save_user_config({})
def delete_preset(name):
    if not _USER_CONFIG: return
    _USER_CONFIG["presets"] = [p for p in _USER_CONFIG.get("presets",[]) if p["name"] != name]
    save_user_config({})
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

load_user_config()
