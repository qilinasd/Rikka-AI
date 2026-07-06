"""
RikkaAI - 六花冲浪系统
搜索记录保存到 surf_records/ 文件夹
"""
import os
from datetime import datetime

import config


def search_bilibili(keyword: str) -> list:
    """搜索B站视频 — 用Google搜索B站链接"""
    try:
        from googlesearch import search
        urls = list(search(f"bilibili {keyword} 视频", num_results=5))
        videos = []
        for url in urls:
            if "bilibili.com/video" in url or "b23.tv" in url:
                videos.append({"title": f"B站: {keyword}", "url": url, "play": ""})
        return videos[:5]
    except Exception:
        return []


def save_record(source: str, tag: str, title: str, url: str = "", detail: str = ""):
    """保存冲浪记录到 surf_records/ 文件夹"""
    now = datetime.now()
    time_str = now.strftime("%Y-%m-%d %H:%M")
    filename = now.strftime("%Y%m%d_%H%M%S") + f"_{source}.md"

    os.makedirs(config.SURF_DIR, exist_ok=True)
    filepath = os.path.join(config.SURF_DIR, filename)

    content = (
        f"# 六花冲浪记录\n\n"
        f"**时间**: {time_str}\n"
        f"**来源**: {source}\n"
        f"**标签**: {tag}\n"
        f"**标题**: {title}\n"
        f"**链接**: {url}\n\n"
        f"{detail}\n"
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def get_records(limit: int = 30) -> list:
    """读取冲浪记录文件列表"""
    os.makedirs(config.SURF_DIR, exist_ok=True)
    files = sorted(os.listdir(config.SURF_DIR), reverse=True)[:limit]
    records = []
    for fname in files:
        if fname.endswith(".md"):
            filepath = os.path.join(config.SURF_DIR, fname)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                title = ""
                source = ""
                tag = ""
                for line in content.split("\n"):
                    if line.startswith("**标题**"):
                        title = line.replace("**标题**: ", "")
                    elif line.startswith("**来源**"):
                        source = line.replace("**来源**: ", "")
                    elif line.startswith("**标签**"):
                        tag = line.replace("**标签**: ", "")
                records.append({
                    "source": source,
                    "tag": tag,
                    "title": title,
                    "file": fname,
                    "content": content,
                })
            except Exception:
                pass
    return records
