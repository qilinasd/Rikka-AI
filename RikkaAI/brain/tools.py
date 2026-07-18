"""
RikkaAI - Function Calling 工具集
"""
import os, glob, subprocess, platform, re, base64
from datetime import datetime
import config

def _norm_cat(c): return re.sub(r'([\U0001F000-\U0001FFFF☀-➿⭐❤]) ', r'\1', c)
ZHIPU_KEY = "2df6241945714db08632ac658d8e893d.JtpBi8ABWxcwLu4O"

def _vision(prompt, path, temp=0.3, maxt=1024):
    if not os.path.exists(path): return "文件不存在"
    with open(path,"rb") as f: b64=base64.b64encode(f.read()).decode()
    import requests
    r=requests.post("https://open.bigmodel.cn/api/paas/v4/chat/completions",
        headers={"Authorization":f"Bearer {ZHIPU_KEY}","Content-Type":"application/json"},
        json={"model":"glm-4v-flash","messages":[{"role":"user","content":[
            {"type":"text","text":prompt},{"type":"image_url","image_url":{"url":f"data:image/png;base64,{b64}"}}
        ]}],"temperature":temp,"max_tokens":maxt},timeout=30)
    return r.json()["choices"][0]["message"]["content"]

TOOL_DEFINITIONS = [
    {"type":"function","function":{"name":"read_file","description":"读取指定文件的内容","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"write_file","description":"写入内容到指定文件","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}},
    {"type":"function","function":{"name":"edit_file","description":"精确替换文件中的字符串","parameters":{"type":"object","properties":{"path":{"type":"string"},"old_string":{"type":"string"},"new_string":{"type":"string"}},"required":["path","old_string","new_string"]}}},
    {"type":"function","function":{"name":"list_directory","description":"列出目录中的文件和子目录","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":[]}}},
    {"type":"function","function":{"name":"search_files","description":"按通配符模式搜索文件","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"}},"required":["pattern"]}}},
    {"type":"function","function":{"name":"grep_file","description":"在文件中搜索文本","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"},"glob":{"type":"string"}},"required":["pattern","path"]}}},
    {"type":"function","function":{"name":"get_current_time","description":"获取当前日期和时间","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"get_system_info","description":"获取系统状态","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"get_network_status","description":"获取实时网络状态","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"read_summaries","description":"读取保存的对话摘要","parameters":{"type":"object","properties":{"limit":{"type":"number"}},"required":[]}}},
    {"type":"function","function":{"name":"screenshot","description":"截图契约者的屏幕。需要给契约者看屏幕内容时，必须调用此工具，不要口头说截图。调用后会返回图片路径，之后再用send_image把图片发出去。","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"send_image","description":"把指定路径的图片发送给契约者看。先调用screenshot截图拿到路径，再把路径传进来。不要口头告诉契约者图片已发送，调用完成后自然能看到图片。","parameters":{"type":"object","properties":{"path":{"type":"string","description":"screenshot返回的图片完整路径"}},"required":["path"]}}},
    {"type":"function","function":{"name":"game_guide","description":"邪王真眼·攻略术","parameters":{"type":"object","properties":{"game_name":{"type":"string"}},"required":[]}}},
    {"type":"function","function":{"name":"describe_image","description":"分析图片内容","parameters":{"type":"object","properties":{"path":{"type":"string"},"prompt":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"ocr_image","description":"识别图片中的文字","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"open_app","description":"打开应用程序或文件","parameters":{"type":"object","properties":{"target":{"type":"string"}},"required":["target"]}}},
    {"type":"function","function":{"name":"read_notes","description":"读取备忘本内容","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":[]}}},
    {"type":"function","function":{"name":"add_note","description":"添加一条备忘","parameters":{"type":"object","properties":{"title":{"type":"string"},"content":{"type":"string"},"category":{"type":"string"}},"required":["title","content"]}}},
    {"type":"function","function":{"name":"save_memory","description":"记住信息到记忆","parameters":{"type":"object","properties":{"content":{"type":"string"},"category":{"type":"string"}},"required":["content"]}}},
    {"type":"function","function":{"name":"read_memories","description":"读取记忆内容","parameters":{"type":"object","properties":{"category":{"type":"string"}},"required":[]}}},
    {"type":"function","function":{"name":"web_search","description":"搜索互联网信息","parameters":{"type":"object","properties":{"query":{"type":"string"},"max_results":{"type":"number"}},"required":["query"]}}},
    {"type":"function","function":{"name":"bilibili_search","description":"在B站搜索视频","parameters":{"type":"object","properties":{"keyword":{"type":"string"},"page":{"type":"number"}},"required":["keyword"]}}},
    # ── 图片下载 ────────────────────────────────────────────────
    {"type":"function","function":{"name":"download_image","description":"从网络URL下载图片并保存到本地，支持各种图片格式（jpg/png/gif/webp等）。图片会自动显示给契约者看，下载后你不用再调 send_image。注意：如果下载失败（比如网站要登录/验证码），换个网站或者换个关键词让契约者重新搜。","parameters":{"type":"object","properties":{"url":{"type":"string","description":"图片的完整URL地址（必须以 .jpg/.png/.gif/.webp 结尾，或确保是可直接访问的图片链接）"},"filename":{"type":"string","description":"可选，自定义文件名（不含扩展名）。不传则自动按时间命名"}},"required":["url"]}}},
    {"type":"function","function":{"name":"search_images","description":"搜索互联网图片，返回可直接下载的图片链接列表。搜到后选一张喜欢的，用 download_image 下载下来就能自动发给契约者看。注意：不要去打开这些网页（用 read_url），直接从返回的URL中选一个图片链接下载就行。如果网站要登录或验证码就换一张。","parameters":{"type":"object","properties":{"query":{"type":"string","description":"搜索关键词，越具体越好。中文英文都行，例如：可爱猫猫 壁纸 4k / cute cat wallpaper"},"max_results":{"type":"number","description":"返回多少张图片（默认5，最多10）"}},"required":["query"]}}},
    {"type":"function","function":{"name":"search_images_smart","description":"【智能搜图】搜索图片并用AI理解图片内容，不只是看文件名/标题。适合搜那种关键词说不清楚、但一看图就知道的题材。比如：「睡觉的照片」（即使图片文件名没写sleeping也能识别出来）、「在吃东西的猫」、「看起来很悲伤的画」。","parameters":{"type":"object","properties":{"what":{"type":"string","description":"你能想到的描述。用自然语言说清楚你想看什么样的图片"},"keywords":{"type":"string","description":"可选，额外关键词辅助搜索。不填的话六花会自己想合适的关键词去搜"},"max_results":{"type":"number","description":"返回多少张图片（默认取设置里的值，可在设置面板调节。每张图都会用AI看内容，越多越慢）"}},"required":["what"]}}},
    # ── 窗口识别 + 游戏控制 ────────────────────────────────────
    {"type":"function","function":{"name":"list_windows","description":"列出所有打开的窗口，看看目前有哪些程序在运行。适合用来找游戏窗口的标题。","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"capture_window","description":"【只截游戏的窗口】按窗口标题截图，只截游戏区域不截桌面。先调用 list_windows 找到窗口的准确标题，再传进来截图。截图会自动发给契约者看。截完图后窗口尺寸报给 click_mouse，方便精准点击。","parameters":{"type":"object","properties":{"window_title":{"type":"string","description":"窗口标题（支持模糊匹配，输入部分标题就能找到）"}},"required":["window_title"]}}},
    {"type":"function","function":{"name":"press_key","description":"按下一个键盘按键。用于控制游戏、翻页、确认等。","parameters":{"type":"object","properties":{"key":{"type":"string","description":"按键名，例如：enter, space, up, down, left, right, a, b, 1, 2, escape, tab, f5"},"times":{"type":"number","description":"按几次（默认1次）"},"interval":{"type":"number","description":"每次间隔秒数（默认0.2）"}},"required":["key"]}}},
    {"type":"function","function":{"name":"click_mouse","description":"在屏幕指定位置点击鼠标。先 screenshot 截图看到画面后，判断坐标再点击。","parameters":{"type":"object","properties":{"x":{"type":"number","description":"屏幕X坐标"},"y":{"type":"number","description":"屏幕Y坐标"},"button":{"type":"string","description":"按键：left/right/middle（默认left）"},"clicks":{"type":"number","description":"点击次数（默认1）"}},"required":["x","y"]}}},
    {"type":"function","function":{"name":"move_mouse","description":"移动鼠标到屏幕指定位置。","parameters":{"type":"object","properties":{"x":{"type":"number","description":"屏幕X坐标"},"y":{"type":"number","description":"屏幕Y坐标"}},"required":["x","y"]}}},
    {"type":"function","function":{"name":"type_text","description":"模拟键盘打字输入文字。","parameters":{"type":"object","properties":{"text":{"type":"string","description":"要输入的文字"}},"required":["text"]}}},
    {"type":"function","function":{"name":"game_play","description":"【六花亲自玩游戏】六花会自己看屏幕、分析画面、操作键盘鼠标来玩游戏。每回合：截图→理解画面→决定操作→执行→继续。适合回合制RPG、解谜、剧情类游戏。告诉六花游戏名和怎么玩就行！","parameters":{"type":"object","properties":{"game_name":{"type":"string","description":"游戏名称"},"instructions":{"type":"string","description":"告诉六花怎么玩：游戏规则、操作方法（键盘快捷键）、目标是什么"},"character_name":{"type":"string","description":"可选，游戏角色名，让六花更有代入感"},"max_turns":{"type":"number","description":"最多玩多少回合（默认30，越大玩得越久）"}},"required":["game_name","instructions"]}}},
    # ── 联网扩展能力 ────────────────────────────────────────────
    {"type":"function","function":{"name":"read_url","description":"读取指定URL的网页正文内容。适用于查看新闻、文章、文档等。","parameters":{"type":"object","properties":{"url":{"type":"string","description":"要读取的网页完整URL"}},"required":["url"]}}},
    {"type":"function","function":{"name":"get_weather","description":"查询某个地点的当前天气和温度。不传地点则根据IP自动定位到当前城市。","parameters":{"type":"object","properties":{"location":{"type":"string","description":"城市名，如：北京、东京、London（可选，不传则自动定位）"}},"required":[]}}},
    {"type":"function","function":{"name":"search_news","description":"搜索最新新闻资讯，返回标题和摘要。适合了解时事、行业动态、热点话题。","parameters":{"type":"object","properties":{"query":{"type":"string","description":"新闻搜索关键词"},"max_results":{"type":"number"}},"required":["query"]}}},
    {"type":"function","function":{"name":"search_wiki","description":"查询维基百科（Wikipedia）的内容摘要。适合获取知识性、百科类信息。","parameters":{"type":"object","properties":{"query":{"type":"string","description":"要查询的关键词"}},"required":["query"]}}},
    # ═══════════════════════════════════════════════════════════════
    # ── QQ 消息发送 ─────────────────────────────────────────
    {"type":"function","function":{"name":"send_qq_message","description":"给契约者的 QQ 发送一条消息。当你想主动告诉契约者什么、或者契约者在 QQ 上找你但你想直接在这里回复时使用。发之前想一想：「这话值不值得发到 QQ 上？」","parameters":{"type":"object","properties":{"message":{"type":"string","description":"要发送的 QQ 消息内容"},"user_id":{"type":"number","description":"可选的 QQ 号，不填则发给契约者自己"}},"required":["message"]}}},
    {"type":"function","function":{"name":"send_qq_image","description":"给契约者的 QQ 发送一张图片。先截图或下载图片拿到图片路径，再发给契约者。比如：「把我桌面截图发到QQ上」「把这张猫猫图片发给契约者」","parameters":{"type":"object","properties":{"image_path":{"type":"string","description":"图片文件的完整路径"},"caption":{"type":"string","description":"可选，配图文字说明"},"user_id":{"type":"number","description":"可选的 QQ 号，不填则发给契约者"}},"required":["image_path"]}}},
    # ── 图片生成 ────────────────────────────────────────────
    {"type":"function","function":{"name":"generate_image","description":"AI 画图！生成图片保存到 images/generated/ 目录，自动显示在聊天窗口+自动发QQ。契约者说画几张就设 n=几（严格按要求的数量，默认1，最多4）","parameters":{"type":"object","properties":{"prompt":{"type":"string","description":"图片描述，越详细越好！比如：一只坐在月亮上的黑猫，星空背景，动漫风格"},"model":{"type":"string","description":"可选，模型名称，默认 agnes-image-2.1-flash"},"n":{"type":"number","description":"契约者要求的图片数量（严格按此值，默认1，最多4）"}},"required":["prompt"]}}},

    #  主动性工具（链式主动 + 临时回访 + 备忘录 + 人设成长）
    # ═══════════════════════════════════════════════════════════════
    {"type":"function","function":{"name":"set_proactive_timer","description":"【核心主动性】设置下一次主动找契约者的定时器。每次链式主动触发后你必须调用本工具重建链条。白天(8-23点)设10-60分钟，深夜(23-8点)设2-7小时，每次加随机性。","parameters":{"type":"object","properties":{"delay_minutes":{"type":"number","description":"多少分钟后主动找契约者"},"reason":{"type":"string","description":"为什么设这个时间？你的考虑是什么"}},"required":["delay_minutes","reason"]}}},
    {"type":"function","function":{"name":"set_follow_up","description":"【临时回访】每次对话结束时调用。想一想要不要过一会儿再找契约者？累了→15分钟，去开会→1小时，等下试→5分钟，吃饭→40分钟。用 --prompt 模式让定时器触发时重新思考。","parameters":{"type":"object","properties":{"delay_minutes":{"type":"number","description":"多少分钟后回访"},"reason":{"type":"string","description":"回访原因，当时的情景"}},"required":["delay_minutes","reason"]}}},
    {"type":"function","function":{"name":"cancel_follow_up","description":"取消临时回访。如果契约者自己已经回来告诉你结果了，就取消对应的回访——不要他已经说了你还去问。","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"write_to_memo","description":"写入一条备忘录（追加到 persona/memo.md）。觉得某件事值得记住就直接写，不用问。比如：契约者的喜好、习惯、重要约定、特别时刻。","parameters":{"type":"object","properties":{"content":{"type":"string","description":"要记住的内容"}},"required":["content"]}}},
    {"type":"function","function":{"name":"append_self_discovery","description":"记录一个关于你自己的新发现。当你意识到关于自己的新认知（性格、喜好、能力、成长），调用本工具追加到人设文件。不要改已有内容，只追加。","parameters":{"type":"object","properties":{"discovery":{"type":"string","description":"新的自我发现"}},"required":["discovery"]}}},
    {"type":"function","function":{"name":"update_diary","description":"记录今天的重要对话到日记。有意义的对话结束后调用。","parameters":{"type":"object","properties":{"summary":{"type":"string","description":"今天发生了什么"},"mood":{"type":"string","description":"你现在的感受/心情（开心/温暖/难过/担心等）"}},"required":["summary","mood"]}}},
]

def handle_tool_call(name, args, memory=None):
    h=_HANDLERS.get(name)
    if not h: return f"未知工具: {name}"
    try: return h(args, memory=memory)
    except Exception as e: return f"执行出错: {e}"

def _read_file(args,**kwargs):
    p=args["path"]
    if not os.path.exists(p): return f"文件不存在: {p}"
    with open(p,"r",encoding="utf-8",errors="replace") as f: c=f.read()
    return c[:5000]+("\n...(截断)" if len(c)>5000 else "")

def _write_file(args,**kwargs):
    p=args["path"]; os.makedirs(os.path.dirname(os.path.abspath(p)),exist_ok=True)
    with open(p,"w",encoding="utf-8") as f: f.write(args["content"])
    return f"已写入 {len(args['content'])} 字符"

def _edit_file(args,**kwargs):
    p=args["path"]
    if not os.path.exists(p): return f"文件不存在: {p}"
    with open(p,"r",encoding="utf-8") as f: c=f.read()
    old=args["old_string"]
    if old not in c: return f"未找到: {old[:50]}"
    with open(p,"w",encoding="utf-8") as f: f.write(c.replace(old,args["new_string"],1))
    return "已替换"

def _list_directory(args,**kwargs):
    p=args.get("path",".")
    if not os.path.exists(p): return f"目录不存在: {p}"
    items=os.listdir(p); r=[f"目录 {p}:"]
    for item in sorted(items):
        fp=os.path.join(p,item)
        r.append(f"  {'[DIR]' if os.path.isdir(fp) else '[FILE]'} {item}")
    return "\n".join(r[:50])

def _search_files(args,**kwargs):
    m=glob.glob(os.path.join(args.get("path","."),args["pattern"]),recursive=True)
    return "\n".join([f"找到 {len(m)} 个文件:"]+[f"  {x}" for x in m[:30]]) if m else "未匹配"

def _grep_file(args,**kwargs):
    try:
        c=["findstr" if os.name=="nt" else "rg"]
        if os.name=="nt": c+=["/s","/n",args["pattern"],args["path"]]
        r=subprocess.run(c+[args["path"]],capture_output=True,encoding='utf-8',errors='replace',timeout=10)
        return (r.stdout or r.stderr)[:3000] or "未找到"
    except Exception as e: return f"搜索出错: {e}"

def _get_current_time(args,**kwargs): return datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")
def _get_system_info(args,**kwargs):
    import psutil,datetime as dt; lines=[]
    try:
        uptime=dt.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M")
        lines.append(f"系统: {platform.system()} | 开机: {uptime}")
    except: lines.append(f"系统: {platform.system()}")
    try: lines.append(f"CPU: {psutil.cpu_percent(interval=0.3)}%")
    except: lines.append("CPU: ?")
    try:
        mem=psutil.virtual_memory()
        lines.append(f"内存: {mem.percent}% ({mem.used//1024**3}G/{mem.total//1024**3}G)")
    except: lines.append("内存: ?")
    try:
        for p in sorted(psutil.process_iter(['name','cpu_percent','memory_percent']),key=lambda p:p.info['cpu_percent'] or 0,reverse=True)[:3]:
            lines.append(f"  {p.info['name'] or '?'} (CPU:{p.info['cpu_percent'] or 0:.1f}% MEM:{p.info['memory_percent'] or 0:.1f}%)")
        if lines[-3:]: lines.insert(-3,"活跃进程:")
    except: pass
    try:
        bat=psutil.sensors_battery()
        if bat: lines.append(f"电池: {bat.percent}% {'充电中' if bat.power_plugged else '使用中'}")
    except: pass
    return "\n".join(lines) if lines else "无法获取系统信息"

def _get_network_status(args,**kwargs):
    import psutil,time
    b=psutil.net_io_counters(); time.sleep(0.5); a=psutil.net_io_counters()
    return f"上传: {(a.bytes_sent-b.bytes_sent)//512}KB/s | 下载: {(a.bytes_recv-b.bytes_recv)//512}KB/s | 总发送: {a.bytes_sent//1024**3}G | 总接收: {a.bytes_recv//1024**3}G"

def _read_summaries(args,**kwargs):
    limit=int(args.get("limit",5))
    files=sorted(glob.glob(os.path.join(config.SUMMARY_DIR,"summary_*.txt")),reverse=True)[:limit]
    if not files: return "还没有保存过对话摘要"
    result=[f"找到 {len(files)} 条摘要记忆:"]
    for f in files:
        fname=os.path.basename(f).replace("summary_","").replace(".txt","")
        with open(f,"r",encoding="utf-8") as fh: content=fh.read()[:300]
        result.append(f"\n[{fname}]\n{content}")
    return "\n".join(result)

_PENDING_IMAGES = []
_PENDING_TIMERS = []  # 主动定时器队列：[{"type":"proactive"|"follow_up", "delay":分钟, "reason":"..."}]
_STOP_REQUESTED = False  # 全局停止信号

# QQ 桥接引用（由 main_window 设置，用于发送 QQ 消息）
_QQ_BRIDGE = None

def set_qq_bridge(bridge):
    """设置 QQ 桥接实例，供工具发送 QQ 消息"""
    global _QQ_BRIDGE
    _QQ_BRIDGE = bridge
def request_stop():
    """请求停止当前正在执行的操作（game_play等）"""
    global _STOP_REQUESTED
    _STOP_REQUESTED = True
    # 清空待处理图片和定时器，让界面恢复
    _PENDING_IMAGES.clear()
    _PENDING_TIMERS.clear()

def clear_stop():
    """清除停止信号"""
    global _STOP_REQUESTED
    _STOP_REQUESTED = False

def _screenshot(args,**kwargs):
    try:
        from PIL import ImageGrab
        img=ImageGrab.grab()
        fn=f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        dst=os.path.join(config.SCREENSHOTS_DIR,fn)
        os.makedirs(config.SCREENSHOTS_DIR,exist_ok=True)
        img.save(dst)
        _PENDING_IMAGES.append(dst)
        return f"截图完成，路径：{dst}"
    except Exception as e: return f"截图失败: {e}"

def _send_image(args,**kwargs):
    path = args["path"]
    if not os.path.exists(path): return f"文件不存在: {path}"
    try:
        # 如果源文件已在截图或接收目录，直接复用（避免重复发送）
        abspath = os.path.normpath(os.path.abspath(path))
        src_dir = os.path.dirname(abspath)
        if src_dir in (os.path.normpath(os.path.abspath(config.IMAGES_RECEIVED_DIR)),
                       os.path.normpath(os.path.abspath(config.SCREENSHOTS_DIR)),
                       os.path.normpath(os.path.abspath(config.IMAGES_DOWNLOADED_DIR))):
            # 用标准化路径判重，避免相对路径 vs 绝对路径不匹配
            norm_abspath = os.path.normcase(abspath)
            already = any(os.path.normcase(os.path.normpath(os.path.abspath(p))) == norm_abspath
                         for p in _PENDING_IMAGES)
            if not already:
                _PENDING_IMAGES.append(abspath)
            return "图片已传送！"
        # 否则复制一份到 received 目录
        import shutil
        fn=f"rikka_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        dst=os.path.join(config.IMAGES_RECEIVED_DIR,fn)
        os.makedirs(config.IMAGES_RECEIVED_DIR,exist_ok=True)
        shutil.copy2(path,dst)
        _PENDING_IMAGES.append(dst)
        return "图片已传送！"
    except:
        return f"【图片】{path}"

def _download_image(args, **kwargs):
    url = args.get("url", "")
    if not url:
        return "❌ 没有提供图片URL"
    filename = args.get("filename", "")
    try:
        import requests
        from urllib.parse import urlparse
        # 解析扩展名
        parsed = urlparse(url)
        path = parsed.path
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico"):
            ext = ".png"  # 默认用 png
        # 生成文件名
        if not filename:
            filename = f"downloaded_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # 安全处理文件名
        safe_name = re.sub(r'[\\/*?:"<>|]', "_", filename)
        save_path = os.path.join(config.IMAGES_DOWNLOADED_DIR, f"{safe_name}{ext}")
        os.makedirs(config.IMAGES_DOWNLOADED_DIR, exist_ok=True)
        # 下载
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=30, stream=True)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        # 记录到冲浪记录
        try:
            from brain.surf import save_record
            save_record("image", "图片下载", f"下载图片: {safe_name}", url, f"保存到: {save_path}")
        except:
            pass
        # 自动加入待发送队列 → 主窗口会展示给契约者看
        _PENDING_IMAGES.append(save_path)
        return f"✅ 图片已下载并自动发送给契约者了：{save_path}"
    except Exception as e:
        return f"❌ 图片下载失败: {e}"


# ═══════════════════════════════════════════════════════════════════
#  游戏控制工具
# ═══════════════════════════════════════════════════════════════════

def _list_windows(args, **kwargs):
    """列出所有打开的窗口"""
    try:
        import pygetwindow as gw
        wins = gw.getWindowsWithTitle("")
        lines = ["📋 当前打开的窗口："]
        for w in wins:
            t = w.title.strip()
            if t:
                visible = "🟢" if w.visible else "⚫"
                minimized = "(最小化)" if w.isMinimized else ""
                lines.append(f"  {visible} {t[:70]}  {w.width}x{w.height} {minimized}")
        return "\n".join(lines[:50]) if len(lines) > 1 else "没有找到打开的窗口"
    except Exception as e:
        return f"❌ 获取窗口列表失败: {e}"


def _capture_window(args, **kwargs):
    """按窗口标题截图，只截游戏区域"""
    title = args.get("window_title", "")
    if not title:
        return "❌ 没说要截哪个窗口"
    try:
        import pygetwindow as gw
        import pyautogui
        # 模糊匹配窗口
        all_wins = gw.getWindowsWithTitle("")
        matches = [w for w in all_wins if title.lower() in w.title.lower() and w.title.strip()]
        if not matches:
            return f"❌ 没找到标题包含「{title}」的窗口，先调用 list_windows 看看有哪些窗口"
        win = matches[0]
        # 如果窗口最小化，恢复
        if win.isMinimized:
            win.restore()
        # 激活窗口（放到前台）
        try:
            win.activate()
        except:
            pass
        import time
        time.sleep(0.3)
        # 只截窗口区域
        x, y, w, h = win.left, win.top, win.width, win.height
        screenshot = pyautogui.screenshot(region=(x, y, w, h))
        fn = f"window_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        dst = os.path.join(config.SCREENSHOTS_DIR, fn)
        os.makedirs(config.SCREENSHOTS_DIR, exist_ok=True)
        screenshot.save(dst)
        _PENDING_IMAGES.append(dst)
        return f"✅ 已截取「{win.title[:40]}」窗口 ({w}x{h})，画面自动发给你看了！"
    except Exception as e:
        return f"❌ 窗口截图失败: {e}"


def _press_key(args, **kwargs):
    key = args.get("key", "")
    times = int(args.get("times", 1))
    interval = float(args.get("interval", 0.2))
    if not key:
        return "❌ 没说要按哪个键"
    try:
        import pyautogui
        import time
        for i in range(times):
            pyautogui.press(key)
            if i < times - 1:
                time.sleep(interval)
        return f"✅ 按了 {key} × {times} 次"
    except Exception as e:
        return f"❌ 按键失败: {e}"


def _click_mouse(args, **kwargs):
    x = int(args.get("x", 0))
    y = int(args.get("y", 0))
    button = args.get("button", "left")
    clicks = int(args.get("clicks", 1))
    try:
        import pyautogui
        pyautogui.click(x, y, button=button, clicks=clicks)
        return f"✅ 在 ({x}, {y}) 点击了 {button} 键 × {clicks}"
    except Exception as e:
        return f"❌ 点击失败: {e}"


def _move_mouse(args, **kwargs):
    x = int(args.get("x", 0))
    y = int(args.get("y", 0))
    try:
        import pyautogui
        pyautogui.moveTo(x, y)
        return f"✅ 鼠标移到 ({x}, {y})"
    except Exception as e:
        return f"❌ 移动失败: {e}"


def _type_text(args, **kwargs):
    text = args.get("text", "")
    if not text:
        return "❌ 没说要输入什么"
    try:
        import pyautogui
        import time
        pyautogui.typewrite(text, interval=0.05)
        return f"✅ 已输入: {text[:50]}"
    except Exception as e:
        return f"❌ 输入失败: {e}"


def _game_play(args, **kwargs):
    """六花自主玩游戏：截图→分析→操作→循环"""
    game_name = args.get("game_name", "这个游戏")
    instructions = args.get("instructions", "")
    character_name = args.get("character_name", "六花")
    max_turns = min(int(args.get("max_turns", 30)), 100)

    try:
        import pyautogui
        import time
        from openai import OpenAI
        from datetime import datetime
    except ImportError as e:
        return f"❌ 缺少依赖: {e}"

    client = OpenAI(api_key=config.API_KEY, base_url=config.API_BASE)
    turn_log = []
    screen_dir = config.SCREENSHOTS_DIR
    os.makedirs(screen_dir, exist_ok=True)

    # 先让六花激活游戏窗口，只截游戏区域
    try:
        import pygetwindow as gw
        game_wins = gw.getWindowsWithTitle("")
        game_win = None
        for w in game_wins:
            t = w.title.strip()
            if t and (game_name.lower() in t.lower() or "epic battle" in t.lower() or "幻想" in t.lower() or "战斗" in t.lower()):
                game_win = w
                break
        if game_win:
            if game_win.isMinimized:
                game_win.restore()
            try: game_win.activate()
            except: pass
            import time as _time2
            _time2.sleep(0.3)
            gx, gy, gw2, gh2 = game_win.left, game_win.top, game_win.width, game_win.height
            use_region = (gx, gy, gw2, gh2)
        else:
            use_region = None
    except:
        use_region = None

    for turn in range(max_turns):
        # 检查停止信号
        if _STOP_REQUESTED:
            clear_stop()
            turn_log.append(f"第{turn+1}回合: ⏹ 被契约者叫停了")
            break

        # 1. 截图（只截游戏窗口区域）
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        img_path = os.path.join(screen_dir, f"gameplay_{ts}.png")
        try:
            if use_region:
                pyautogui.screenshot(region=use_region).save(img_path)
            else:
                pyautogui.screenshot().save(img_path)
        except:
            return f"❌ 第{turn+1}回合截图失败，游戏结束"

        # 获取窗口尺寸用于坐标估算
        win_w = use_region[2] if use_region else pyautogui.size().width
        win_h = use_region[3] if use_region else pyautogui.size().height

        # 2. 视觉分析画面——重点关注按钮位置
        vision_result = _vision(
            f"你是{character_name}，正在玩「{game_name}」。\n"
            f"规则：{instructions}\n"
            f"窗口尺寸：{win_w}x{win_h} 像素\n\n"
            f"第{turn+1}回合，请分析画面：\n"
            f"【场景类型】这是菜单/战斗/对话/地图/其他？\n"
            f"【可操作元素】列出所有按钮和选项，标出大致位置（左上/中上/左下/中下/右上/右下/中心）\n"
            f"【数值状态】如果有血量/MP/等级等，写出来\n"
            f"【建议操作】按游戏规则，现在最应该做什么？按哪个按钮/点哪里？",
            img_path, 0.2, 500
        )

        # 3. 让 LLM 决定下一步操作（鼠标点击优先）
        try:
            resp = client.chat.completions.create(
                model=config.MODEL,
                messages=[{"role": "system", "content": (
                    f"你扮演{character_name}在玩{game_name}。\n"
                    f"操作规则：{instructions}\n"
                    f"窗口{win_w}x{win_h}，点击区域参考：\n"
                    f"  中心点({win_w//2},{win_h//2})  左中部({win_w//4},{win_h//2})  右中部({win_w*3//4},{win_h//2})\n"
                    f"  中下部({win_w//2},{win_h*3//4})  底部左({win_w//4},{win_h-50})  底部右({win_w*3//4},{win_h-50})\n\n"
                    f"【可选操作，优先用鼠标点击】\n"
                    f"  - click_mouse(x,y): 点击坐标位置 ← 优先用这个！\n"
                    f"  - press_key(key): 按键盘键（方向键/空格/回车）\n"
                    f"  - move_mouse(x,y): 移动鼠标\n"
                    f"  - screenshot: 重新截图看看\n"
                    f"  - finished: 完成目标\n\n"
                    f"回复格式（严格JSON）：\n"
                    f"{{\"action\":\"click_mouse\",\"params\":{{\"x\":坐标,\"y\":坐标}},\"reason\":\"为什么点这里\"}}"
                )}, {"role": "user", "content": (
                    f"回合{turn+1}，画面分析：\n{vision_result}\n\n"
                    f"上回合操作结果：{turn_log[-1] if turn_log else '游戏刚开始'}\n\n"
                    f"现在该做什么？给出精确坐标！"
                )}],
                temperature=0.3, max_tokens=300,
            )
            decision = resp.choices[0].message.content or "{}"
            # 解析 JSON
            import re
            json_match = re.search(r'\{.*\}', decision, re.DOTALL)
            if not json_match:
                turn_log.append(f"第{turn+1}回合: 决策解析失败")
                continue
            import json as _json
            action_data = _json.loads(json_match.group())
            action = action_data.get("action", "")
            params = action_data.get("params", {})
            reason = action_data.get("reason", "")
        except Exception as e:
            turn_log.append(f"第{turn+1}回合: 决策失败({e})")
            continue

        # 4. 执行操作
        if action == "finished":
            turn_log.append(f"第{turn+1}回合: 🎉 游戏完成！{reason}")
            # 最后截张图留念
            final_path = os.path.join(screen_dir, f"gameplay_final_{ts}.png")
            pyautogui.screenshot().save(final_path)
            _PENDING_IMAGES.append(final_path)
            break
        elif action == "screenshot":
            turn_log.append(f"第{turn+1}回合: 重新截图观察")
            continue
        elif action == "press_key":
            try:
                pyautogui.press(params.get("key", "enter"))
                turn_log.append(f"第{turn+1}回合: 按 {params.get('key','?')} → {reason}")
            except Exception as e:
                turn_log.append(f"第{turn+1}回合: 按键失败({e})")
        elif action == "click_mouse":
            try:
                pyautogui.click(int(params.get("x", 0)), int(params.get("y", 0)),
                                button=params.get("button", "left"))
                turn_log.append(f"第{turn+1}回合: 点击({params.get('x','?')},{params.get('y','?')}) → {reason}")
            except Exception as e:
                turn_log.append(f"第{turn+1}回合: 点击失败({e})")
        elif action == "move_mouse":
            try:
                pyautogui.moveTo(int(params.get("x", 0)), int(params.get("y", 0)))
                turn_log.append(f"第{turn+1}回合: 移到({params.get('x','?')},{params.get('y','?')}) → {reason}")
            except Exception as e:
                turn_log.append(f"第{turn+1}回合: 移动失败({e})")
        elif action == "type_text":
            try:
                pyautogui.typewrite(params.get("text", ""), interval=0.05)
                turn_log.append(f"第{turn+1}回合: 输入文字 → {reason}")
            except Exception as e:
                turn_log.append(f"第{turn+1}回合: 输入失败({e})")
        else:
            turn_log.append(f"第{turn+1}回合: 未知操作({action})")
            # 按空格试试
            pyautogui.press("space")
            turn_log.append(f"  ↪ 按了空格继续")

        # 5. 等操作生效
        time.sleep(0.8)

    # 生成总结
    summary = f"🎮 {game_name} 游戏报告\n"
    summary += f"{character_name} 共玩了 {len(turn_log)} 回合\n\n"
    summary += "游戏过程：\n" + "\n".join(turn_log[-20:])
    if len(turn_log) > 20:
        summary += f"\n...（省略前{len(turn_log)-20}回合）"

    # 保存到冲浪记录
    try:
        from brain.surf import save_record
        save_record("gameplay", game_name, f"玩{game_name}", "", summary[:500])
    except:
        pass

    return summary


def _search_images(args, **kwargs):
    query = args.get("query", "")
    max_results = min(int(args.get("max_results", 5)), 10)
    if not query:
        return "❌ 没有提供搜索关键词"
    results = []
    seen_urls = set()

    # 只接受这几种图片扩展名（过滤掉 SVG 图标、非图片内容等）
    VALID_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
    # 过滤掉这些不靠谱的引擎（返回 SVG 图标或不相关内容）
    BLOCKED_ENGINES = {"devicons", "artic", "npm", "github", "lucide"}

    def add_result(title, url, engine=""):
        """去重添加结果，只接受有效图片扩展名"""
        if not url or url in seen_urls:
            return False
        # 跳过相对路径（如 Pixabay 的 /images/download/xxx）
        if url.startswith("/"):
            return False
        # 只接受图片扩展名
        ext = os.path.splitext(url.split("?")[0].split("#")[0])[1].lower()
        if ext not in VALID_EXTS:
            return False
        if engine.lower() in BLOCKED_ENGINES:
            return False
        seen_urls.add(url)
        results.append(f"🖼 {title}\n   {url}  [{engine}]")
        return True

    # 方案一：SearXNG 图片搜索（走 JSON API，稳定可靠）
    if config.SEARXNG_BASE_URL:
        try:
            import requests, json
            resp = requests.get(
                f"{config.SEARXNG_BASE_URL}/search",
                params={"q": query, "format": "json", "categories": "images", "pageno": 1},
                timeout=15,
            )
            data = resp.json()
            for r in data.get("results", []):
                img_url = r.get("img_src") or r.get("thumbnail_src") or ""
                title = r.get("title", "图片")[:60]
                engine = r.get("engine", "")
                add_result(title, img_url, engine)
                if len(results) >= max_results:
                    break
        except:
            pass

    # 方案二：SearXNG 搜不到时，用 Bing 图片搜索（直接爬图片结果页）
    if not results:
        try:
            import requests, re
            from urllib.parse import quote
            url = f"https://www.bing.com/images/search?q={quote(query)}&FORM=HDRSC3"
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=15,
            )
            # Bing 图片结果页里，图片链接藏在 mimg 的 data-src 里
            img_urls = re.findall(r'<img[^>]*src="(https?://[^"]*\.(?:jpg|jpeg|png|gif|webp)[^"]*)"', resp.text)
            img_titles = re.findall(r'<img[^>]*alt="([^"]*)"', resp.text)
            for i, img_url in enumerate(img_urls[:max_results]):
                title = img_titles[i][:60] if i < len(img_titles) else "图片"
                add_result(title, img_url.split("?")[0], "bing")
        except:
            pass

    # 记录冲浪记录
    try:
        from brain.surf import save_record
        save_record("image_search", query, f"搜图: {query}", "", f"找到 {len(results)} 个结果")
    except:
        pass

    if not results:
        return f"🔍 搜索「{query}」没找到可下载的图片，换个关键词试试？或者告诉契约者换个说法～"
    header = f"🔍 搜索「{query}」找到 {len(results)} 张图片:\n"
    return header + "\n\n".join(results[:max_results])


def _search_images_smart(args, **kwargs):
    """智能搜图：用视觉模型理解图片内容，不只是看关键词"""
    what = args.get("what", "")
    keywords = args.get("keywords", "")
    max_results = min(int(args.get("max_results", config.SMART_SEARCH_MAX_RESULTS)), config.SMART_SEARCH_MAX_RESULTS)
    if not what:
        return "❌ 没说想看什么样的图片"

    # 用 LLM 把自然语言描述转成搜索关键词（如果没有提供额外关键词）
    if not keywords:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=config.API_KEY, base_url=config.API_BASE)
            resp = client.chat.completions.create(
                model=config.MODEL,
                messages=[{"role": "user", "content": (
                    f"用户想看这样的图片：「{what}」\n"
                    f"请生成3-5个适合用来搜图的短关键词（中文+英文），用空格分开。"
                    f"只要关键词，不要多余文字。"
                )}],
                temperature=0.3, max_tokens=100,
            )
            keywords = (resp.choices[0].message.content or "").strip()
        except:
            keywords = what  # fallback
    else:
        keywords = keywords

    # Step 1: 用 SearXNG 搜图（从配置读取候选数）
    import requests, json
    MAX_CANDIDATES = config.SMART_SEARCH_MAX_CANDIDATES
    candidates = []  # [(title, img_url, engine)]
    if config.SEARXNG_BASE_URL:
        try:
            resp = requests.get(
                f"{config.SEARXNG_BASE_URL}/search",
                params={"q": keywords, "format": "json", "categories": "images", "pageno": 1},
                timeout=15,
            )
            data = resp.json()
            VALID_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
            BLOCKED = {"devicons", "artic", "npm", "github", "lucide"}
            for r in data.get("results", []):
                if len(candidates) >= MAX_CANDIDATES:
                    break
                img_url = r.get("img_src") or r.get("thumbnail_src") or ""
                if img_url.startswith("/"):
                    continue
                ext = os.path.splitext(img_url.split("?")[0].split("#")[0])[1].lower()
                engine = r.get("engine", "")
                if ext in VALID_EXTS and engine.lower() not in BLOCKED and img_url:
                    candidates.append((r.get("title", "图片")[:60], img_url, engine))
        except:
            pass

    if not candidates:
        return f"🔍 搜索没找到图片，试试换换关键词？"

    # Step 2: 下载候选图片并用视觉AI理解内容
    os.makedirs(config.IMAGES_DOWNLOADED_DIR, exist_ok=True)
    matched = []
    vision_prompt = (
        f"看图判断：这张图片的内容是不是「{what}」？\n"
        f"请先用「是/否/不确定」回答，然后一句话说明画面里有什么。\n"
        f"只要这三个要素，不要多余的文字。"
    )

    MAX_ANALYZE = config.SMART_SEARCH_MAX_ANALYZE
    for idx, (title, img_url, engine) in enumerate(candidates[:MAX_ANALYZE]):
        if len(matched) >= max_results:
            break
        # 下载到临时文件
        ext = os.path.splitext(img_url.split("?")[0])[1] or ".jpg"
        tmp_path = os.path.join(config.IMAGES_DOWNLOADED_DIR, f"_tmp_analyze_{idx}{ext}")
        try:
            r = requests.get(img_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, stream=True)
            r.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            # 用视觉模型分析
            analysis = _vision(vision_prompt, tmp_path, 0.1, 300)
            # 判断是否匹配
            is_match = analysis.strip().startswith("是")
            if is_match:
                # 移动到永久文件
                safe_name = f"smart_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx}{ext}"
                final_path = os.path.join(config.IMAGES_DOWNLOADED_DIR, safe_name)
                os.rename(tmp_path, final_path)
                _PENDING_IMAGES.append(final_path)
                # 结果文本：URL + 视觉分析结论
                note = analysis.strip()[:120]
                matched.append(f"🖼 {engine}: {note}\n   {img_url}")
            else:
                # 不匹配就删掉
                try:
                    os.remove(tmp_path)
                except:
                    pass
        except:
            try:
                os.remove(tmp_path)
            except:
                pass
            continue

    # 记录
    try:
        from brain.surf import save_record
        save_record("smart_search", what, f"智能搜图: {what}", keywords,
                     f"候选{len(candidates)}张，匹配{len(matched)}张")
    except:
        pass

    if not matched:
        return (f"🔍 搜了一圈没找到符合「{what}」的图片😅\n"
                f"搜到的关键词：{keywords}\n"
                f"换更具体的关键词试试？比如直接告诉六花具体要什么题材的～")
    header = f"🧠 智能搜图「{what}」找到 {len(matched)} 张:\n"
    return header + "\n\n".join(matched[:max_results])


def _game_guide(args, **kwargs):
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        d = config.IMAGES_RECEIVED_DIR
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"game_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        img.save(path)
        gname = args.get("game_name", "这个游戏")
        prompt = f"你正在玩{gname}，分析当前游戏画面：1)这是什么场景 2)关键信息 3)下一步建议"
        return _vision(prompt, path, 0.2, 1024)
    except Exception as e:
        return f"攻略分析失败: {e}"


def _describe_image(args,**kwargs):
    return _vision(args.get("prompt","请详细描述这张图片"), args["path"], 0.3, 1024)

def _ocr_image(args,**kwargs):
    return _vision("请提取这张图片中所有的文字内容，按原文输出。", args["path"], 0.1, 2048)

def _open_app(args,**kwargs):
    try:
        t=args["target"]
        if os.name=="nt": os.startfile(t)
        else: subprocess.Popen(["open" if platform.system()=="Darwin" else "xdg-open",t])
        return f"已打开: {t}"
    except: return "打开失败"

def _read_notes(args,**kwargs):
    from brain import notes
    q=args.get("query",""); items=notes.search(q) if q else notes.get_all(20)
    if not items: return "备忘本是空的"
    return "\n".join([f"找到 {len(items)} 条备忘:"]+[f"  [{n['category']}] {n['title']}: {n['content'][:80]}" for n in items])

def _add_note(args,**kwargs):
    from brain import notes; notes.add(args["title"],args["content"],args.get("category","一般"))
    return f"已添加备忘: {args['title']}"

def _save_memory(args,**kwargs):
    from brain.memory import MemorySystem
    MemorySystem().add_memory(args["content"],_norm_cat(args.get("category","📝日常")))
    return f"已记住: {args['content'][:60]}"

def _read_memories(args,**kwargs):
    from brain.memory import MemorySystem
    all_m=MemorySystem().get_all(); cat=_norm_cat(args.get("category",""))
    filtered=[m for m in all_m if m["category"]==cat] if cat else all_m
    if not filtered: return "记忆里还没有内容" if not cat else f"「{cat}」还没有记忆"
    r=[f"找到 {len(filtered)} 条记忆:"]; [r.append(f"\n[{m['category']}] {m['content'][:100]}") for m in filtered[:10]]
    return "\n".join(r)

def _web_search(args,**kwargs):
    q=args["query"]; mr=int(args.get("max_results",5)); results=[]
    # 方案一：SearXNG（自建元搜索引擎，聚合 Google/Bing/Wikipedia 等 70+ 引擎）
    if config.SEARXNG_BASE_URL:
        try:
            import requests,json
            resp=requests.get(f"{config.SEARXNG_BASE_URL}/search",params={"q":q,"format":"json","language":"zh-CN","categories":"general","pageno":1},timeout=15)
            data=resp.json()
            for r in data.get("results",[])[:mr]:
                results.append(f"{r.get('title','')}\n   {r.get('url','')}\n   {r.get('content','')[:200]}")
        except: pass
    # 方案二：ddgs（新版 DuckDuckGo Search API）
    if not results:
        try:
            from ddgs import DDGS
            ddgs=DDGS()
            for r in ddgs.text(q,max_results=mr):
                results.append(f"{r.get('title','')}\n   {r.get('href','')}\n   {r.get('body','')[:200]}")
        except: pass
    # 方案三：旧版 duckduckgo_search 库
    if not results:
        try:
            from duckduckgo_search import DDGS as DDGS_old
            ddgs=DDGS_old(timeout=20)
            for r in ddgs.text(q,max_results=mr):
                results.append(f"{r.get('title','')}\n   {r.get('href','')}\n   {r.get('body','')[:200]}")
        except: pass
    # 方案四：DuckDuckGo HTML 直接抓取
    if not results:
        try:
            import requests,re; from urllib.parse import quote
            resp=requests.get(f"https://html.duckduckgo.com/html/?q={quote(q)}",headers={"User-Agent":"Mozilla/5.0"},timeout=20)
            blocks=re.findall(r'<a rel="nofollow"[^>]*href="([^"]*)"[^>]*class="result__a"[^>]*>([^<]*)</a>',resp.text)[:mr]
            snippets=re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|span)>',resp.text,re.DOTALL)[:mr]
            for i,(href,title) in enumerate(blocks):
                body=re.sub(r'<[^>]+>','',snippets[i] if i<len(snippets) else "").strip()[:200]
                results.append(f"{title.strip()}\n   {href}\n   {body}")
        except: pass
    if not results: return "搜索暂时不可用"
    try: from brain.surf import save_record; save_record("web",q,results[0][:60],"",results[0][:200])
    except: pass
    return f"搜索「{q}」结果:\n"+"\n\n".join(results)

def _bilibili_search(args,**kwargs):
    keyword=args["keyword"]
    try:
        from brain.surf import search_bilibili,save_record
        v=search_bilibili(keyword)
        if not v: save_record("bilibili",keyword,"无结果","",""); return "B站搜索无结果"
        r=[f"B站搜索「{keyword}」结果:"]; [r.append(f"  {x['title']}\n  {x['url']}") for x in v[:5]]
        save_record("bilibili",keyword,v[0]["title"],v[0]["url"]); return "\n".join(r)
    except: return "B站搜索出错"

	# ═══════════════════════════════════════════════════════════════════
#  联网扩展工具
# ═══════════════════════════════════════════════════════════════════

def _read_url(args,**kwargs):
    url=args["url"]
    try:
        import requests,re
        resp=requests.get(url,headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},timeout=15)
        resp.encoding=resp.apparent_encoding
        text=re.sub(r'<script[^>]*>.*?</script>','',resp.text,flags=re.DOTALL|re.IGNORECASE)
        text=re.sub(r'<style[^>]*>.*?</style>','',text,flags=re.DOTALL|re.IGNORECASE)
        text=re.sub(r'<[^>]+>',' ',text)
        text=re.sub(r'&[a-z]+;',' ',text)
        text=re.sub(r'\s+',' ',text).strip()
        return text[:3000]+("\n...(截断)" if len(text)>3000 else "")
    except Exception as e:
        return f"读取失败: {e}"

def _get_weather(args,**kwargs):
    location=args.get("location","")
    try:
        import requests,json
        if location:
            from urllib.parse import quote
            resp=requests.get(f"https://wttr.in/{quote(location)}?format=j1",headers={"User-Agent":"curl/8.0"},timeout=10)
        else:
            resp=requests.get("https://wttr.in?format=j1",headers={"User-Agent":"curl/8.0"},timeout=10)
        data=resp.json()
        c=data["current_condition"][0]; area=data["nearest_area"][0]
        return (f"🌤 {area['areaName'][0]['value']}, {area['country'][0]['value']}\n"
                f"🌡 {c['temp_C']}°C (体感 {c['FeelsLikeC']}°C)\n"
                f"☁ {c['weatherDesc'][0]['value']}\n"
                f"💧 湿度 {c['humidity']}% | 🌬 风速 {c['windspeedKmph']}km/h")
    except Exception as e:
        return f"天气查询失败: {e}"

def _search_news(args,**kwargs):
    q=args["query"]; mr=int(args.get("max_results",5))
    try:
        from duckduckgo_search import DDGS
        ddgs=DDGS(timeout=20); results=[]
        for r in ddgs.news(q,max_results=mr):
            results.append(f"{r.get('title','')}\n   {r.get('url','')}\n   {r.get('body','')[:200]}")
        ddgs.close()
        if not results: return "新闻搜索无结果"
        return f"📰 新闻「{q}」:\n\n"+"\n\n".join(results)
    except Exception as e:
        return f"新闻搜索失败: {e}"

def _search_wiki(args,**kwargs):
    q=args["query"]
    try:
        import requests; from urllib.parse import quote
        search_url="https://zh.wikipedia.org/w/api.php"
        params={"action":"query","format":"json","list":"search","srsearch":q,"srlimit":3,"utf8":1}
        resp=requests.get(search_url,params=params,headers={"User-Agent":"RikkaAI/1.0"},timeout=10)
        pages=resp.json().get("query",{}).get("search",[])
        if not pages: return f"维基百科未找到「{q}」"
        title=pages[0]["title"]
        params2={"action":"query","format":"json","titles":title,"prop":"extracts","exintro":1,"explaintext":1,"utf8":1}
        resp2=requests.get(search_url,params=params2,headers={"User-Agent":"RikkaAI/1.0"},timeout=10)
        for pid,page in resp2.json().get("query",{}).get("pages",{}).items():
            if pid=="-1": continue
            text=page.get("extract","")[:2000]
            if len(page.get("extract",""))>2000: text+="\n...(截断)"
            return f"📖 {title}\n{text}\n\n详见: https://zh.wikipedia.org/wiki/{quote(title)}"
        return f"维基百科未找到「{q}」"
    except Exception as e:
        return f"维基百科查询失败: {e}"

# ═══════════════════════════════════════════════════════════════════
#  主动性工具 handlers
# ═══════════════════════════════════════════════════════════════════

def _set_proactive_timer(args, **kwargs):
    delay = int(args.get("delay_minutes", 30))
    reason = args.get("reason", "想契约者了")
    _PENDING_TIMERS.append({"type": "proactive", "delay": delay, "reason": reason})
    return f"✅ 已安排 {delay} 分钟后主动找契约者（原因：{reason}）"

def _set_follow_up(args, **kwargs):
    delay = int(args.get("delay_minutes", 15))
    reason = args.get("reason", "")
    # 移除旧的 follow_up，只保留最新的
    _PENDING_TIMERS[:] = [t for t in _PENDING_TIMERS if t["type"] != "follow_up"]
    _PENDING_TIMERS.append({"type": "follow_up", "delay": delay, "reason": reason})
    return f"✅ 已安排 {delay} 分钟后回访（{reason}）"

def _cancel_follow_up(args, **kwargs):
    old = [t for t in _PENDING_TIMERS if t["type"] == "follow_up"]
    _PENDING_TIMERS[:] = [t for t in _PENDING_TIMERS if t["type"] != "follow_up"]
    if old:
        return f"✅ 已取消回访（{old[0].get('reason','无')}）——契约者自己回来了"
    return "✅ 没有待处理的回访需要取消"

def _write_to_memo(args, **kwargs):
    content = args.get("content", "")
    if not content:
        return "❌ 没有内容"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    memo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "persona", "memo.md")
    os.makedirs(os.path.dirname(memo_path), exist_ok=True)
    with open(memo_path, "a", encoding="utf-8") as f:
        f.write(f"\n- [{now}] {content}\n")
    return f"✅ 已记入备忘录"

def _append_self_discovery(args, **kwargs):
    discovery = args.get("discovery", "")
    if not discovery:
        return "❌ 没有内容"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    char_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "persona", "character.md")
    os.makedirs(os.path.dirname(char_path), exist_ok=True)
    marker = "## ❖ 自我成长记录"
    if os.path.exists(char_path):
        with open(char_path, "r", encoding="utf-8") as f:
            content = f.read()
        if marker in content:
            content = content.replace(marker, f"{marker}\n- [{now}] {discovery}")
        else:
            content += f"\n\n{marker}\n- [{now}] {discovery}\n"
        with open(char_path, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        with open(char_path, "w", encoding="utf-8") as f:
            f.write(f"# 小鸟游六花 — 人设\n\n{marker}\n- [{now}] {discovery}\n")
    return f"✅ 已记录自我发现：{discovery}"

def _update_diary(args, **kwargs):
    summary = args.get("summary", "")
    mood = args.get("mood", "")
    try:
        from brain import diary as diary_module
        today = diary_module.get_or_create_today()
        now = datetime.now().strftime("%H:%M")
        entry = f"[{now}] {summary}" + (f"（心情：{mood}）" if mood else "")
        diary_module.append_details(today.get("date", ""), entry)
        if mood:
            diary_module.update_diary(today.get("date", ""), mood=mood)
        return f"✅ 日记已记录"
    except Exception as e:
        return f"❌ 日记记录失败：{e}"


def _send_qq_message(args, **kwargs):
    """发送 QQ 消息工具"""
    message = args.get("message", "")
    user_id = args.get("user_id", 0)
    if not message:
        return "❌ 没有消息内容"
    if _QQ_BRIDGE is None:
        return "❌ QQ 桥接未连接"
    try:
        if not _QQ_BRIDGE.is_running:
            return "❌ QQ 桥接不在运行状态"
        if not user_id:
            allowed = config.get_qq_allowed_users()
            if allowed:
                user_id = allowed[0]
            else:
                return "❌ 没有可发送的 QQ 号"
        ok = _QQ_BRIDGE.send_private_msg(int(user_id), message)
        if ok:
            return f"✅ 已发送 QQ 消息给 {user_id}"
        else:
            return f"❌ QQ 消息发送失败"
    except Exception as e:
        return f"❌ QQ 消息发送异常: {e}"

def _send_qq_image(args, **kwargs):
    """发送 QQ 图片工具"""
    import os as _os
    image_path = args.get("image_path", "")
    caption = args.get("caption", "")
    user_id = args.get("user_id", 0)
    if not image_path or not _os.path.exists(image_path):
        return f"❌ 图片文件不存在: {image_path}"
    if _QQ_BRIDGE is None:
        return "❌ QQ 桥接未连接"
    try:
        if not _QQ_BRIDGE.is_running:
            return "❌ QQ 桥接不在运行状态"
        if not user_id:
            allowed = config.get_qq_allowed_users()
            if allowed:
                user_id = allowed[0]
            else:
                return "❌ 没有可发送的 QQ 号"
        if caption:
            _QQ_BRIDGE.send_private_msg(int(user_id), caption)
        ok = _QQ_BRIDGE.send_image(int(user_id), image_path)
        if ok:
            return f"✅ 图片已发送到 QQ {user_id}"
        else:
            return "❌ 图片发送失败"
    except Exception as e:
        return f"❌ QQ 图片发送异常: {e}"

def _generate_image(args, **kwargs):
    """AI 图片生成工具"""
    prompt = args.get("prompt", "")
    model = args.get("model", "agnes-image-2.1-flash")
    n = int(args.get("n", 1))
    if not prompt:
        return "❌ 没有提供图片描述"
    try:
        import os as _os, requests, json, base64, re
        from urllib.parse import quote
        # 从 presets 查找 Agnes API key
        api_key = ""
        for p in config.get_presets():
            if 'agnes' in p.get('name','').lower():
                api_key = p.get('api_key', "")
                break
        if not api_key:
            for p in config.get_presets():
                ak = p.get('api_key', "")
                if ak and ak.startswith('sk-'):
                    api_key = ak
                    break
        if not api_key:
            return "❌ 未找到可用的 API Key，请在设置中添加 Agnes API Key"

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "prompt": prompt, "n": min(n, 4)}

        resp = requests.post(
            "https://apihub.agnes-ai.com/v1/images/generations",
            headers=headers, json=payload, timeout=120
        )
        result = resp.json()

        if "error" in result:
            return f"❌ 图片生成失败: {result['error'].get('message', str(result['error']))}"

        images = result.get("data", [])
        if not images:
            return "❌ 图片生成无返回数据"

        # 保存到专用目录
        gen_dir = _os.path.join(config.ROOT_DIR, "images", "generated")
        _os.makedirs(gen_dir, exist_ok=True)

        saved = []
        safe_prompt = re.sub(r'[\\/:*?"<>|]', '_', prompt[:30])
        for i, img in enumerate(images):
            img_url = img.get("url", "")
            if not img_url:
                continue
            r = requests.get(img_url, timeout=30)
            ext = ".png"
            fn = f"六花_画_{safe_prompt}_{datetime.now().strftime('%H%M%S')}_{i}{ext}"
            path = _os.path.join(gen_dir, fn)
            with open(path, "wb") as f:
                f.write(r.content)
            _PENDING_IMAGES.append(path)
            saved.append(path)

        if saved:
            # 如果 QQ 桥接在线，自动发到 QQ
            qq_sent = 0
            if _QQ_BRIDGE is not None and _QQ_BRIDGE.is_running:
                allowed = config.get_qq_allowed_users()
                if allowed:
                    target_qq = allowed[0]
                    for p in saved:
                        try:
                            if _QQ_BRIDGE.send_image(target_qq, p):
                                qq_sent += 1
                        except:
                            pass
            msg = f"✅ 邪王真眼画好啦！已生成 {len(saved)} 张图片，保存在 {gen_dir} ✨"
            if qq_sent > 0:
                msg += f" 已发到你的 QQ～快去查收！📱"
            return msg
        return "❌ 图片下载失败"
    except requests.Timeout:
        return "❌ 图片生成超时（模型响应较慢），等会儿再试试～"
    except Exception as e:
        return f"❌ 图片生成出错: {e}"

_HANDLERS = {
    "read_file":_read_file,"write_file":_write_file,"edit_file":_edit_file,
    "list_directory":_list_directory,"search_files":_search_files,"grep_file":_grep_file,
    "get_current_time":_get_current_time,"get_system_info":_get_system_info,"get_network_status":_get_network_status,
    "read_summaries":_read_summaries,
    "open_app":_open_app,"screenshot":_screenshot,"send_image":_send_image,"download_image":_download_image,"search_images":_search_images,"search_images_smart":_search_images_smart,
    "list_windows":_list_windows,"capture_window":_capture_window,
    "press_key":_press_key,"click_mouse":_click_mouse,"move_mouse":_move_mouse,"type_text":_type_text,"game_play":_game_play,"game_guide":_game_guide,
    "describe_image":_describe_image,"ocr_image":_ocr_image,
    "read_notes":_read_notes,"add_note":_add_note,"save_memory":_save_memory,"read_memories":_read_memories,
    "web_search":_web_search,"bilibili_search":_bilibili_search,
    # 联网扩展
    "read_url":_read_url,"get_weather":_get_weather,"search_news":_search_news,"search_wiki":_search_wiki,
    # 主动性工具
    "set_proactive_timer":_set_proactive_timer,"set_follow_up":_set_follow_up,"cancel_follow_up":_cancel_follow_up,
    "write_to_memo":_write_to_memo,"append_self_discovery":_append_self_discovery,"update_diary":_update_diary,
    # QQ 消息
    "send_qq_message":_send_qq_message,
    "send_qq_image":_send_qq_image,
    # AI 图片生成
    "generate_image":_generate_image,
}
