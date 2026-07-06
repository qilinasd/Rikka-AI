"""
RikkaAI - 全局配置模板
复制为 config.py 并填入你自己的 API Key
"""
import os, json
from datetime import datetime

APP_NAME = "RikkaAI"; APP_VERSION = "0.1.0"

# ── 对话 API（用于聊天） ──
MODEL = "deepseek-v4-flash"
API_BASE = "https://api.deepseek.com/v1"
API_KEY = "your-deepseek-api-key-here"
TEMPERATURE = 0.8

# ── 视觉 API（用于看图/OCR/搜图，智谱 GLM-4V-Flash 免费） ──
ZHIPU_API_KEY = "your-zhipu-api-key-here"

# ── 搜索服务（SearXNG 自建搜索引擎） ──
SEARXNG_BASE_URL = "http://localhost:8080"

# ── 以下一般不需要修改 ──
CHARACTER_PANEL_WIDTH = 220
CHARACTER_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "assets", "images", "character_full.png")
ROOT_DIR = os.path.dirname(__file__)
ASSETS_DIR = os.path.join(ROOT_DIR, "assets"); IMAGES_DIR = os.path.join(ASSETS_DIR, "images")
STYLES_DIR = os.path.join(ASSETS_DIR, "styles")
MEMORY_DIR = os.path.join(ROOT_DIR, "memory_data")
USER_CONFIG_DIR = os.path.join(ROOT_DIR, "memory_data")
USER_CONFIG_PATH = os.path.join(USER_CONFIG_DIR, "user_config.json")
DIARY_DIR = os.path.join(ROOT_DIR, "diaries")
SUMMARY_DIR = os.path.join(ROOT_DIR, "summaries")
MEMORIES_DIR = os.path.join(ROOT_DIR, "memories")
IMAGES_DIR_ROOT = os.path.join(ROOT_DIR, "images")
IMAGES_SENT_DIR = os.path.join(IMAGES_DIR_ROOT, "sent")
IMAGES_RECEIVED_DIR = os.path.join(IMAGES_DIR_ROOT, "received")
SCREENSHOTS_DIR = os.path.join(IMAGES_DIR_ROOT, "screenshots")
IMAGES_DOWNLOADED_DIR = os.path.join(IMAGES_DIR_ROOT, "downloaded")
CONVERSATIONS_DIR = os.path.join(ROOT_DIR, "conversations")
