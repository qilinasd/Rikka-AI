"""
RikkaAI - Function Calling 工具集
"""
import os, glob, subprocess, platform, re, base64, sys, time
from datetime import datetime
import config
import secret_store

# ⚠️ 默认不走任何系统/环境代理（避免误走 VPN/代理导致请求失败）。
# 需要代理的（如 Twitter CLI）在其子进程 env 里单独设置，不影响这里的通用请求。
import requests as _requests
_HTTP = _requests.Session()
try:
    _HTTP.trust_env = False  # 屏蔽 HTTP_PROXY / HTTPS_PROXY / NO_PROXY 等环境代理
except Exception:
    pass
def _http_get(url, **kwargs):
    kwargs.setdefault("timeout", 12)
    return _HTTP.get(url, **kwargs)

def _norm_cat(c): return re.sub(r'([\U0001F000-\U0001FFFF☀-➿⭐❤]) ', r'\1', c)

def _image_mime(path):
    """按文件头判断真实图片格式，供视觉模型的 data URI 使用。"""
    with open(path, "rb") as f:
        head = f.read(16)
    if head[:3] == b"\xff\xd8\xff": return "jpeg"
    if head[:4] == b"\x89PNG": return "png"
    if head[:4] in (b"GIF8",): return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP": return "webp"
    if head[:2] == b"BM": return "bmp"
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext if ext in ("png", "jpeg", "jpg", "gif", "webp", "bmp") else "png"

def _encode_image(path, max_side=2048, max_bytes=5_000_000):
    """读出图片字节，返回 (base64, mime)，过大时先用 PIL 压缩。"""
    if os.path.getsize(path) <= max_bytes:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode(), _image_mime(path)
    try:
        from PIL import Image
        import io
        img = Image.open(path).convert("RGB")
        w, h = img.size
        if max(w, h) > max_side:
            r = max_side / max(w, h)
            img = img.resize((int(w * r), int(h * r)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        data = buf.getvalue()
        if len(data) > max_bytes:
            buf = io.BytesIO(); img.save(buf, "JPEG", quality=60)
            data = buf.getvalue()
        return base64.b64encode(data).decode(), "jpeg"
    except Exception:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode(), _image_mime(path)

def _vision(prompt, path, temp=0.3, maxt=1024):
    if not os.path.exists(path): return "文件不存在"
    b64, mime = _encode_image(path)
    import requests
    vision_key = config.VISION_API_KEY or secret_store.get("vision_api_key")
    vision_model = config.VISION_MODEL
    vision_base = config.VISION_API_BASE
    if not all((vision_key, vision_model, vision_base)):
        return "识图失败：未启用识图模型方案，请在「设置 → 方案设置」中配置并启用。"
    try:
        r = requests.post(vision_base,
            headers={"Authorization":f"Bearer {vision_key}","Content-Type":"application/json"},
            json={"model":vision_model,"messages":[{"role":"user","content":[
                {"type":"text","text":prompt},{"type":"image_url","image_url":{"url":f"data:image/{mime};base64,{b64}"}}
            ]}],"temperature":temp,"max_tokens":maxt},timeout=60)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return f"识图失败：视觉模型 HTTP {r.status_code}: {r.text[:150]}"
    except Exception as e:
        return f"识图失败：视觉模型异常: {str(e)[:150]}"

# ═══ 工具信任声明制（借鉴 NoneBot/Koishi 的权限模型）═══════════════
# 访客（未授权 QQ 用户）仅可使用显式列入 GUEST_TOOLS 的公开只读工具；
# 未声明的工具一律视为契约者专属——新工具默认对访客不可见，杜绝黑名单漏新。
# 原则：本机/私人数据/记忆/定时/联系方式类能力永不对访客开放。
GUEST_TOOLS = frozenset({
    "get_current_time", "get_weather",
    "web_search", "argo_search", "bilibili_search",
    "search_wiki", "search_news", "read_rss", "read_twitter",
    "youtube_transcript", "github_repo", "read_url",
    "describe_image",   # 访客发图想让她看 → 只描述该图，无本机访问
})


def is_guest_allowed(tool_name) -> bool:
    """该工具是否对访客（未授权 QQ 用户）开放。"""
    return tool_name in GUEST_TOOLS


TOOL_DEFINITIONS = [
    {"type":"function","function":{"name":"read_file","description":"读取指定文件的内容","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"write_file","description":"写入内容到指定文件","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}},
    {"type":"function","function":{"name":"edit_file","description":"精确替换文件中的字符串","parameters":{"type":"object","properties":{"path":{"type":"string"},"old_string":{"type":"string"},"new_string":{"type":"string"}},"required":["path","old_string","new_string"]}}},
    {"type":"function","function":{"name":"list_directory","description":"列出目录中的文件和子目录","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":[]}}},
    {"type":"function","function":{"name":"search_files","description":"按通配符模式搜索文件","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"}},"required":["pattern"]}}},
    {"type":"function","function":{"name":"grep_file","description":"在文件中搜索文本","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"},"glob":{"type":"string"}},"required":["pattern","path"]}}},
    {"type":"function","function":{"name":"get_current_time","description":"【必须调用】获取当前精确的日期和时间。用户问'几点'、'现在'、'时间'、'日期'、'今天几号'、'星期几'时必须调用此工具，禁止凭记忆或训练数据猜测！","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"get_system_info","description":"获取系统状态","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"get_network_status","description":"获取实时网络状态","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"read_summaries","description":"读取保存的对话摘要","parameters":{"type":"object","properties":{"limit":{"type":"number"}},"required":[]}}},
    {"type":"function","function":{"name":"screenshot","description":"【必须调用】截取契约者的屏幕。用户说'看看屏幕'、'截图'、'看下画面'、'看一下'、'瞅瞅'、'屏幕上有什么'时必须调用，不要口头说截图。调用后返回图片路径，之后再用send_image发送。","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"send_image","description":"【必须调用】把指定路径的图片发送给契约者看。先调用screenshot截图拿到路径，再把路径传进来。不要口头告诉契约者图片已发送，调用完成后自然能看到图片。","parameters":{"type":"object","properties":{"path":{"type":"string","description":"screenshot返回的图片完整路径"}},"required":["path"]}}},
    {"type":"function","function":{"name":"game_guide","description":"邪王真眼·攻略术","parameters":{"type":"object","properties":{"game_name":{"type":"string"}},"required":[]}}},
    {"type":"function","function":{"name":"describe_image","description":"【必须调用】识别和描述图片内容。用户发图片或说'这个图'、'图片上有什么'、'看看这张图'时必须调用，不要说看不到图。参数path是图片路径。","parameters":{"type":"object","properties":{"path":{"type":"string"},"prompt":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"ocr_image","description":"识别图片中的文字","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"open_app","description":"打开应用程序或文件","parameters":{"type":"object","properties":{"target":{"type":"string"}},"required":["target"]}}},
    {"type":"function","function":{"name":"save_memory","description":"【重要信息必存】保存记忆碎片。用户提到偏好、习惯、约定、计划、重要信息时必须调用记住，不要只是回应'好的'或'知道了'。content是要记住的内容，category是分类。","parameters":{"type":"object","properties":{"content":{"type":"string"},"category":{"type":"string"}},"required":["content"]}}},
    {"type":"function","function":{"name":"read_memories","description":"【不确定就查】检索记忆碎片。用户问'之前'、'上次'、'记得吗'、'我说过什么'或你不确定某个信息时，必须调用此工具检索确认，不要凭印象猜测！category是可选的分类筛选。","parameters":{"type":"object","properties":{"category":{"type":"string"}},"required":[]}}},
    {"type":"function","function":{"name":"manage_user_state","description":"【用户状态管理】记录契约者的即时状态（生理期/搬家/压力/备考/生病/近期忙什么等有时效的信息）。有三种操作：set=新增状态（必须给过期时间，默认90天）；update=修改已有状态（给 state_id 和修改内容）；resolve=结束一条状态（给 state_id 和原因）。这些状态会自动过期，让六花永远知道契约者『现在』的处境，而不是历史旧账。","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["set","update","resolve"],"description":"set=新增；update=修改；resolve=结束"},"content":{"type":"string","description":"状态内容，如：契约者最近在赶项目/契约者感冒了。set 时必填"},"state_id":{"type":"number","description":"状态ID。update/resolve 时必填"},"expires_at":{"type":"string","description":"可选，过期时间 'YYYY-MM-DD HH:MM'，不填默认90天后；传 'none' 永不过期"}},"required":["action"]}}},
    {"type":"function","function":{"name":"correct_memory","description":"【记忆纠错】契约者指出六花记错了时调用！比如契约者说『你记错了，我不喜欢喝咖啡』。按关键词找到那条错误记忆，修正内容或删除。如果契约者给了正确说法就传 correct_content 更新；没有就只传关键词删除旧记忆。","parameters":{"type":"object","properties":{"query":{"type":"string","description":"描述记错的内容关键词，如：喜欢喝咖啡"},"correct_content":{"type":"string","description":"可选，正确的说法。不传则删除旧记忆"}},"required":["query"]}}},
    {"type":"function","function":{"name":"web_search","description":"【立即调用】搜索互联网信息。用户说'搜'、'查'、'找'、'帮我搜索'、'查一下'时必须立即调用，不要凭训练数据回答旧知识！返回最新的网页结果。★路由规则★：搜索对象是以下平台/类型时，必须改用对应专门工具，绝不要用本工具——B站视频→bilibili_search；YouTube视频/总结→youtube_transcript；GitHub仓库/文件→github_repo；维基百科/百科词条→search_wiki；新闻/时事/资讯→search_news；RSS/博客/播客订阅→read_rss；Twitter/X→read_twitter；图片/壁纸→search_images/search_images_smart；天气→get_weather；给链接读正文→read_url。★专业深度搜索（股价行情/学术论文/深度调研/多语言/事实核验）→ argo_search★。只有当这些都是普通网页、概念、综合资料、网站内容时才用本工具。","parameters":{"type":"object","properties":{"query":{"type":"string"},"max_results":{"type":"number"}},"required":["query"]}}},
    {"type":"function","function":{"name":"bilibili_search","description":"【必须调用】B站专用搜索。契约者提到「B站/Bilibili/哔哩哔哩/视频」上搜索或找视频时，必须用本工具，不要用 web_search 或 argo_search。返回匹配的视频标题、UP主、播放量和链接。","parameters":{"type":"object","properties":{"keyword":{"type":"string"},"page":{"type":"number"}},"required":["keyword"]}}},
    # ── 图片下载 ────────────────────────────────────────────────
    {"type":"function","function":{"name":"download_image","description":"从网络URL下载图片并保存到本地，支持各种图片格式（jpg/png/gif/webp等）。图片会自动显示给契约者看，下载后你不用再调 send_image。注意：如果下载失败（比如网站要登录/验证码），换个网站或者换个关键词让契约者重新搜。","parameters":{"type":"object","properties":{"url":{"type":"string","description":"图片的完整URL地址（必须以 .jpg/.png/.gif/.webp 结尾，或确保是可直接访问的图片链接）"},"filename":{"type":"string","description":"可选，自定义文件名（不含扩展名）。不传则自动按时间命名"}},"required":["url"]}}},
    {"type":"function","function":{"name":"search_images","description":"【必须调用】搜图专用。搜索互联网图片，返回可直接下载的图片链接列表。契约者要「图片/壁纸/表情包/某物的照片」时用本工具，不要用 web_search。搜到后选一张喜欢的，用 download_image 下载下来就能自动发给契约者看。注意：不要去打开这些网页（用 read_url），直接从返回的URL中选一个图片链接下载就行。如果网站要登录或验证码就换一张。","parameters":{"type":"object","properties":{"query":{"type":"string","description":"搜索关键词，越具体越好。中文英文都行，例如：可爱猫猫 壁纸 4k / cute cat wallpaper"},"max_results":{"type":"number","description":"返回多少张图片（默认5，最多10）"}},"required":["query"]}}},
    {"type":"function","function":{"name":"search_images_smart","description":"【智能搜图·专用】搜索图片并用AI理解图片内容，不只是看文件名/标题。适合搜那种关键词说不清楚、但一看图就知道的题材，也是「找图片」的首选。比如：「睡觉的照片」（即使图片文件名没写sleeping也能识别出来）、「在吃东西的猫」、「看起来很悲伤的画」。契约者要图时用本工具，不要用 web_search。","parameters":{"type":"object","properties":{"what":{"type":"string","description":"你能想到的描述。用自然语言说清楚你想看什么样的图片"},"keywords":{"type":"string","description":"可选，额外关键词辅助搜索。不填的话六花会自己想合适的关键词去搜"},"max_results":{"type":"number","description":"返回多少张图片（默认取设置里的值，可在设置面板调节。每张图都会用AI看内容，越多越慢）"}},"required":["what"]}}},
    # ── 联网扩展能力 ────────────────────────────────────────────
    {"type":"function","function":{"name":"read_url","description":"读取指定URL的网页正文内容。适用于查看新闻、文章、文档等。","parameters":{"type":"object","properties":{"url":{"type":"string","description":"要读取的网页完整URL"}},"required":["url"]}}},
    {"type":"function","function":{"name":"get_weather","description":"【必须调用】查询某个地点的当前天气、温度、湿度、风速。★只要契约者问天气/气温/冷不冷/热不热/下不下雨/下不下雪，就用本工具，不要用 web_search 或 argo_search★。不传地点则根据IP自动定位到当前城市。","parameters":{"type":"object","properties":{"location":{"type":"string","description":"城市名，如：北京、东京、London（可选，不传则自动定位）"}},"required":[]}}},
    {"type":"function","function":{"name":"search_news","description":"【新闻专用】搜索最新新闻资讯，返回标题和摘要。契约者要「最新新闻/时事/资讯/热点/行业动态」时用本工具，不要用 web_search 或 argo_search。","parameters":{"type":"object","properties":{"query":{"type":"string","description":"新闻搜索关键词"},"max_results":{"type":"number"}},"required":["query"]}}},
    {"type":"function","function":{"name":"search_wiki","description":"【维基百科专用】查询维基百科（Wikipedia）的内容摘要。契约者提到 Wikipedia/维基百科，或想要百科词条式/知识性答案时用本工具，不要用 web_search 或 argo_search。","parameters":{"type":"object","properties":{"query":{"type":"string","description":"要查询的关键词"}},"required":["query"]}}},
    {"type":"function","function":{"name":"read_rss","description":"【RSS专用】订阅并阅读一个 RSS/Atom 源的最近条目，返回标题和摘要。契约者要订阅/追更某个博客、新闻、播客的更新时用本工具，不要用 web_search。","parameters":{"type":"object","properties":{"feed_url":{"type":"string","description":"RSS/Atom 源的 URL"}},"required":["feed_url"]}}},
    {"type":"function","function":{"name":"youtube_transcript","description":"【YouTube专用】获取 YouTube 视频的字幕/简介/时长等信息，用来总结视频讲了什么。契约者提到 YouTube/油管 视频，或给了一个 YouTube 链接要总结时用本工具，不要用 web_search。","parameters":{"type":"object","properties":{"url":{"type":"string","description":"YouTube 视频的完整 URL"}},"required":["url"]}}},
    {"type":"function","function":{"name":"github_repo","description":"【GitHub专用】查看 GitHub 仓库的信息（简介、star、最近提交等）、README 或仓库里某个文件的内容。契约者提到 GitHub/某个开源项目/仓库时用本工具，不要用 web_search 或 argo_search。","parameters":{"type":"object","properties":{"repo":{"type":"string","description":"仓库名，owner/repo 格式，如 browser-use/browser-use"},"path":{"type":"string","description":"可选，仓库内文件路径，如 README.md 或 src/main.py；不填则返回仓库概览+README"}},"required":["repo"]}}},
    {"type":"function","function":{"name":"argo_search","description":"【专业深度搜索】Argo 搜索引擎：垂直源优先+证据评分，比 web_search 准。★只在这类情况用它★：股价/基金/油价/金价等实时行情；学术论文；深度调研/综述；日韩英等多语言内容；需要可信度评估的事实核验。★绝不要用它★（有更快的专门工具）：天气→get_weather；B站→bilibili_search；维基→search_wiki；新闻→search_news；GitHub→github_repo；YouTube→youtube_transcript；RSS→read_rss；Twitter→read_twitter；图片→search_images/search_images_smart；给链接读内容→read_url；日常查概念/综合网页→web_search。拿不准用哪个时，先想清楚场景再选，别把普通搜索丢给 Argo。","parameters":{"type":"object","properties":{"query":{"type":"string","description":"搜索关键词或完整问题，越具体越好"},"max_results":{"type":"number","description":"返回条数，默认5，最多10"},"mode":{"type":"string","enum":["auto","fast","deep","budget"],"description":"搜索深度：auto=默认；fast=快而省；deep=深度调研（拆子问题多源并行）；budget=省额度。调研/综述类用 deep"}},"required":["query"]}}},
    {"type":"function","function":{"name":"browser_task","description":"【六花亲自上网操作】驾驶真实浏览器完成网页任务：点按钮、填表单、登录、抓取需要 JS 渲染的页面、多步网页流程。适合：登录某个网站查东西、填一个表单、跑一个需要点击/翻页的流程、抓动态网页内容。任务描述越具体越好（要访问哪个网站、做什么、最后要得到什么）。注意：会真的打开一个无头浏览器执行，需要联网，可能较慢；网站要验证码/强登录时可能失败。","parameters":{"type":"object","properties":{"task":{"type":"string","description":"要完成的网页任务，描述得越具体越好"},"max_steps":{"type":"number","description":"最多执行多少步（默认12，越大越能完成复杂任务但越慢）"}},"required":["task"]}}},
    {"type":"function","function":{"name":"read_twitter","description":"【Twitter/X 专用】读取 Twitter/X 的内容（需要契约者在 Chrome 里登录了 X，且 OpenCLI 扩展已连接）。契约者提到 Twitter/X/推特、要看某人的推文或热搜时用本工具，不要用 web_search。可以看首页时间线、某个用户的资料或最近推文、搜推文、读单条推文或长文、看热门趋势。只读操作，不能发帖/点赞/关注。如果契约者没登录 X 就提示他先登录。","parameters":{"type":"object","properties":{"action":{"type":"string","enum":["timeline","profile","tweets","search","tweet","article","trending"],"description":"timeline=首页时间线；profile=用户资料（target填用户名）；tweets=用户最近推文（target填用户名）；search=搜推文（target填关键词）；tweet=读单条推文（target填推文URL或ID）；article=读长文（target填推文URL或ID）；trending=热门趋势（不需要target）"},"target":{"type":"string","description":"action 需要的参数：profile/tweets 填用户名（如 elonmusk），search 填关键词，tweet/article 填推文URL或ID，timeline/trending 留空"},"limit":{"type":"number","description":"返回条数，默认10，最多20"}},"required":["action"]}}},
    # ═══════════════════════════════════════════════════════════════
    # ── QQ 消息发送 ─────────────────────────────────────────
    {"type":"function","function":{"name":"send_qq_message","description":"给契约者的 QQ 发送一条消息。当你想主动告诉契约者什么、或者契约者在 QQ 上找你但你想直接在这里回复时使用。必须把要发送的完整文字放进 message 字段，message 不能为空；不能只调用工具名或在普通回复里写待发送内容。发之前想一想：「这话值不值得发到 QQ 上？」","parameters":{"type":"object","properties":{"message":{"type":"string","description":"要发送的 QQ 消息内容，必须为非空字符串"},"user_id":{"type":"number","description":"可选的 QQ 号，不填则发给契约者自己"}},"required":["message"]}}},
    {"type":"function","function":{"name":"send_qq_image","description":"给契约者的 QQ 发送一张图片。先截图或下载图片拿到图片路径，再发给契约者。比如：「把我桌面截图发到QQ上」「把这张猫猫图片发给契约者」","parameters":{"type":"object","properties":{"image_path":{"type":"string","description":"图片文件的完整路径"},"caption":{"type":"string","description":"可选，配图文字说明"},"user_id":{"type":"number","description":"可选的 QQ 号，不填则发给契约者"}},"required":["image_path"]}}},
    {"type":"function","function":{"name":"query_qq_contacts","description":"查询六花的 QQ 联系人列表：好友或群。当契约者问「你QQ上有谁」「把XX的联系方式找出来」「你在哪些群里」，或你想找到某个 QQ 号发消息时调用。","parameters":{"type":"object","properties":{"scope":{"type":"string","enum":["friends","groups","all"],"description":"friends=好友列表, groups=群列表, all=两者都要"},"keyword":{"type":"string","description":"可选，按昵称/备注/群名模糊筛选"}},"required":["scope"]}}},
    # ── 图片生成 ────────────────────────────────────────────
    # ── 记忆总结 ────────────────────────────────────────────
    {"type":"function","function":{"name":"build_summary","description":"生成记忆总结报告！写日报/周记/月报/年鉴。当契约者说「写日报」「写周记」「总结一下这周」「写月报」「写年鉴」时调用。会读取日记和记忆自动生成，保存到 summaries/ 目录下的对应文件夹。","parameters":{"type":"object","properties":{"level":{"type":"string","description":"总结级别：weekly=周记, monthly=月报, yearly=年鉴"},"period_key":{"type":"string","description":"可选，时间段标识，如 2026-W29（周）、2026-07（月）、2026（年），不填自动当前时段"}},"required":["level"]}}},
    {"type":"function","function":{"name":"generate_image","description":"AI 画图！使用设置中启用的生图模型方案，生成图片保存到 images/generated/ 目录，自动显示在聊天窗口+自动发QQ。契约者说画几张就设 n=几（严格按要求的数量，默认1，最多4）","parameters":{"type":"object","properties":{"prompt":{"type":"string","description":"图片描述，越详细越好！比如：一只坐在月亮上的黑猫，星空背景，动漫风格"},"model":{"type":"string","description":"可选，临时覆盖当前生图方案的模型名称"},"n":{"type":"number","description":"契约者要求的图片数量（严格按此值，默认1，最多4）"}},"required":["prompt"]}}},

    #  主动性工具（链式主动 + 临时回访 + 备忘录 + 人设成长）
    # ═══════════════════════════════════════════════════════════════
    {"type":"function","function":{"name":"set_proactive_timer","description":"【核心主动性】设置下一次主动找契约者的定时器。每次链式主动触发后你必须调用本工具重建链条。白天(8-23点)设10-60分钟，深夜(23-8点)设2-7小时，每次加随机性。","parameters":{"type":"object","properties":{"delay_minutes":{"type":"number","description":"多少分钟后主动找契约者"},"reason":{"type":"string","description":"为什么设这个时间？你的考虑是什么"}},"required":["delay_minutes","reason"]}}},
    {"type":"function","function":{"name":"set_follow_up","description":"【临时回访】每次对话结束时调用。想一想要不要过一会儿再找契约者？累了→15分钟，去开会→1小时，等下试→5分钟，吃饭→40分钟。用 --prompt 模式让定时器触发时重新思考。","parameters":{"type":"object","properties":{"delay_minutes":{"type":"number","description":"多少分钟后回访"},"reason":{"type":"string","description":"回访原因，当时的情景"}},"required":["delay_minutes","reason"]}}},
    {"type":"function","function":{"name":"cancel_follow_up","description":"取消临时回访。如果契约者自己已经回来告诉你结果了，就取消对应的回访——不要他已经说了你还去问。","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"write_to_memo","description":"写入一条备忘录（追加到 persona/memo.md）。觉得某件事值得记住就直接写，不用问。比如：契约者的喜好、习惯、重要约定、特别时刻。","parameters":{"type":"object","properties":{"content":{"type":"string","description":"要记住的内容"}},"required":["content"]}}},
    {"type":"function","function":{"name":"append_self_discovery","description":"记录一个关于你自己的新发现。当你意识到关于自己的新认知（性格、喜好、能力、成长），调用本工具追加到人设文件。不要改已有内容，只追加。","parameters":{"type":"object","properties":{"discovery":{"type":"string","description":"新的自我发现"}},"required":["discovery"]}}},
    {"type":"function","function":{"name":"update_diary","description":"记录今天的重要对话到日记。有意义的对话结束后调用。","parameters":{"type":"object","properties":{"summary":{"type":"string","description":"今天发生了什么"},"mood":{"type":"string","description":"你现在的感受/心情（开心/温暖/难过/担心等）"}},"required":["summary","mood"]}}},
    {"type":"function","function":{"name":"write_diary","description":"【写日记】写今天的日记。当你觉得今天值得记下来、或想记录和契约者的一天时主动调用（比如深夜、重要的事情发生之后、心情很想记录的时刻）。会通读今天的所有流水，以第一人称写一篇随笔风格的小作文存入今天的日记。","parameters":{"type":"object","properties":{"mood":{"type":"string","description":"写这篇日记时你的心情（如：温暖、开心、心疼、思考、中二）"}},"required":[]}}},
]

# ═══════════════════════════════════════════════════════════════
#  ask 询问档（allow/ask/deny 三档权限）
#  敏感工具调用前弹窗询问用户，用户可：允许一次 / 拒绝
# ═══════════════════════════════════════════════════════════════

# 需要询问的敏感工具（写文件、编辑、打开程序、浏览器操作、下载）
ASK_TOOLS = {
    "write_file", "edit_file", "open_app", "browser_task", "download_image",
}

# 询问回调：由 GUI 层注册（main_window），签名 ask_fn(name, args) -> bool
_ASK_HANDLER = None


def register_ask_handler(fn):
    """注册询问回调（GUI 层弹窗）。fn(name, args) -> True=允许 / False=拒绝"""
    global _ASK_HANDLER
    _ASK_HANDLER = fn


def _needs_ask(name: str) -> bool:
    return name in ASK_TOOLS and _ASK_HANDLER is not None


# ═══════════════════════════════════════════════════════════
#  四态 outcome（对齐 CyreneHarness）：
#  success / failure / unknown / not_executed
#  非幂等工具（发消息/写文件/改远端等）：结果可能"未知"，需副作用记账防重放
# ═══════════════════════════════════════════════════════════

# 非幂等工具：副作用不可安全重复执行（结果未知时暂停后续同类重放）
NON_IDEMPOTENT_TOOLS = {
    "send_qq_message", "send_qq_image",   # 发消息，中断后可能已发出
    "write_file", "edit_file",            # 改文件，中断后可能已改一半
    "browser_task",                       # 浏览器操作，副作用不可控
    "download_image",                     # 下载，可能已开始
    "open_app",                           # 打开程序
}


def handle_tool_call(name, args, memory=None, trusted=True):
    """执行工具，返回四态 outcome 字典。

    返回: {"status": "success|failure|unknown|not_executed", "content": ...,
           "tool": name, "non_idempotent": bool}
    兼容：内部仍把文本放到 content 里，调用方可直接取 content 展示。

    trusted=False（访客会话）时执行护栏：非 GUEST_TOOLS 白名单内的工具
    一律硬拒（not_executed），不经模型协商、不触发询问弹窗。
    访问级别由消息入口的通道身份（QQ user_id）决定，对话内容无法改变。
    """
    if not trusted and name not in GUEST_TOOLS:
        return {"status": "not_executed", "content": "该操作未对当前对话开放。", "tool": name, "non_idempotent": name in NON_IDEMPOTENT_TOOLS}
    h = _HANDLERS.get(name)
    non_idem = name in NON_IDEMPOTENT_TOOLS
    if not h:
        return {"status": "failure", "content": f"未知工具: {name}", "tool": name, "non_idempotent": non_idem}
    # ask 询问档：敏感工具先问用户（拒绝 → not_executed）
    if _needs_ask(name):
        try:
            allowed = _ASK_HANDLER(name, args)
        except Exception:
            allowed = True
        if not allowed:
            return {"status": "not_executed", "content": f"⛔ 用户拒绝了 {name} 操作", "tool": name, "non_idempotent": non_idem}
    try:
        result = h(args, memory=memory)
        # 工具内部主动标记 unknown（如网络中断但可能已生效）
        if isinstance(result, dict) and result.get("__unknown__"):
            return {"status": "unknown", "content": result.get("content", "结果未知"), "tool": name, "non_idempotent": non_idem}
        content = str(result)
        status = "failure" if content.lstrip().startswith("❌") else "success"
        return {"status": status, "content": content, "tool": name, "non_idempotent": non_idem}
    except Exception as e:
        return {"status": "failure", "content": f"执行出错: {e}", "tool": name, "non_idempotent": non_idem}

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
        if os.name=="nt":
            c=["findstr","/s","/n",args["pattern"],args["path"]]
        else:
            c=["rg","-n",args["pattern"],args["path"]]
        r=subprocess.run(c,capture_output=True,encoding='utf-8',errors='replace',timeout=10)
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
        proc_start = len(lines)
        for p in sorted(psutil.process_iter(['name','cpu_percent','memory_percent']),key=lambda p:p.info['cpu_percent'] or 0,reverse=True)[:3]:
            lines.append(f"  {p.info['name'] or '?'} (CPU:{p.info['cpu_percent'] or 0:.1f}% MEM:{p.info['memory_percent'] or 0:.1f}%)")
        if len(lines) > proc_start:
            lines.insert(proc_start, "活跃进程:")
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
        resp = _http_get(url, headers=headers, timeout=30, stream=True)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if _STOP_REQUESTED:
                    f.close()
                    try: os.remove(save_path)
                    except OSError: pass
                    return "⏹ 下载已停止"
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
            import requests
            resp = _http_get(
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
            resp = _http_get(
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
    import requests
    MAX_CANDIDATES = config.SMART_SEARCH_MAX_CANDIDATES
    candidates = []  # [(title, img_url, engine)]
    if config.SEARXNG_BASE_URL:
        try:
            resp = _http_get(
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
        return "🔍 搜索没找到图片，试试换换关键词？"

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
        if _STOP_REQUESTED:
            return "⏹ 智能搜图已停止"
        # 下载到临时文件
        ext = os.path.splitext(img_url.split("?")[0])[1] or ".jpg"
        tmp_path = os.path.join(config.IMAGES_DOWNLOADED_DIR, f"_tmp_analyze_{idx}{ext}")
        try:
            r = _http_get(img_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, stream=True)
            r.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    if _STOP_REQUESTED:
                        f.close()
                        try: os.remove(tmp_path)
                        except OSError: pass
                        return "⏹ 智能搜图已停止"
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

def _describe_qq_images(message):
    """把消息里的 [CQ:image,...url=...] 段替换成视觉描述，让六花能"看到"QQ 发来的图。
    返回 (清理后的消息, 是否成功描述了图片)。无图 / 下载失败时不改动原消息。"""
    segs = re.findall(r"\[CQ:image[^\]]*?url=([^,\]]+)(?:[,\]]|$)", message)
    if not segs:
        return message, False
    import requests
    os.makedirs(config.IMAGES_DOWNLOADED_DIR, exist_ok=True)
    descs = []
    for i, url in enumerate(segs[:3]):
        try:
            p = os.path.join(config.IMAGES_DOWNLOADED_DIR,
                             f"qq_img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}.jpg")
            r = _http_get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            with open(p, "wb") as f:
                f.write(r.content)
            descs.append(f"[QQ图片{i+1}] {_vision('用中文简要描述这张图片（契约者从QQ发来的）', p, 0.2, 300)}")
        except Exception:
            descs.append(f"[QQ图片{i+1}]（下载失败，无法识别）")
    clean = re.sub(r"\[CQ:[^\]]*\]", "", message).strip()
    if clean:
        return ("\n".join(descs) + "\n" + clean).strip(), True
    return "\n".join(descs), True

def _open_app(args,**kwargs):
    try:
        t=args["target"]
        if os.name=="nt": os.startfile(t)
        else: subprocess.Popen(["open" if platform.system()=="Darwin" else "xdg-open",t])
        return f"已打开: {t}"
    except: return "打开失败"

def _save_memory(args,**kwargs):
    from brain import memory_vault as _mv
    _mv.store_fragment("契约者", args["content"], _norm_cat(args.get("category","一般")), 0.5)
    return f"已记住: {args['content'][:60]}"


def _read_memories(args,**kwargs):
    from brain import memory_vault as _mv
    cat=_norm_cat(args.get("category",""))
    all_m = _mv.search(cat if cat else "", top_k=20)
    filtered = [m for m in all_m if cat in (m.get("category",""))] if cat else all_m
    if not filtered:
        return "记忆里还没有内容" if not cat else "[" + cat + "]还没有记忆"
    r = ["找到 %d 条记忆:" % len(filtered)]
    for m in filtered[:10]:
        r.append("[" + m["category"] + "] " + m["content"][:100])
    return "\n".join(r)


def _manage_user_state(args,**kwargs):
    from brain import memory_vault as _mv
    action = args.get("action", "set")
    try:
        if action == "set":
            content = args.get("content", "").strip()
            if not content:
                return "需要提供状态内容"
            expires = args.get("expires_at", "")
            sid = _mv.set_user_state(content, state_type="general", expires_at=expires)
            return f"已记录状态 #{sid}: {content[:60]}" + (f"（过期 {expires}）" if expires else "（默认90天后过期）")
        if action == "update":
            sid = int(args.get("state_id", 0))
            content = args.get("content", "")
            if not sid:
                return "需要提供 state_id"
            ok = _mv.update_user_state(sid, content=content or None)
            return "状态已更新" if ok else "未找到该状态"
        if action == "resolve":
            sid = int(args.get("state_id", 0))
            if not sid:
                return "需要提供 state_id"
            ok = _mv.resolve_user_state(sid)
            return "状态已结束" if ok else "未找到该状态"
        return "未知操作"
    except Exception as e:
        return f"状态操作失败: {e}"


def _correct_memory(args,**kwargs):
    from brain import memory_vault as _mv
    query = args.get("query", "").strip()
    if not query:
        return "需要提供记错的内容关键词"
    correct = args.get("correct_content", "").strip()
    n = _mv.correct_by_keyword(query, correct)
    if n == 0:
        return f"没找到与「{query}」相关的记忆（可能还没记过）"
    if correct:
        return f"已纠正 {n} 条记忆，改为: {correct[:60]}"
    return f"已删除 {n} 条记错的记忆"


_searxng_cache = {"ts": 0.0, "ok": None}

def _searxng_ok(ttl: float = 60.0, timeout: float = 3.0) -> bool:
    """探测 SearXNG 是否可用（短超时 + 60s 缓存）。没配置/连不上/非200 → 视为不可用，调用方立即切 Argo。"""
    if not config.SEARXNG_BASE_URL:
        return False
    import time as _t
    now = _t.time()
    if _searxng_cache["ok"] is not None and (now - _searxng_cache["ts"]) < ttl:
        return _searxng_cache["ok"]
    ok = False
    try:
        import requests
        resp = _http_get(f"{config.SEARXNG_BASE_URL}/search",
                            params={"q": "测试", "format": "json"}, timeout=timeout)
        ok = resp.status_code == 200
    except Exception:
        ok = False
    _searxng_cache["ts"] = now
    _searxng_cache["ok"] = ok
    return ok


def _web_search(args,**kwargs):
    q=args["query"]; mr=int(args.get("max_results",5)); results=[]
    # SearXNG 可用性探测（短超时+缓存）：没开/连不上就立刻切 Argo，避免每次干等 15s
    searxng_on = _searxng_ok() if config.SEARXNG_BASE_URL else False
    searxng_down = bool(config.SEARXNG_BASE_URL) and not searxng_on
    # 方案一：SearXNG（自建元搜索引擎，聚合 Google/Bing/Wikipedia 等 70+ 引擎）
    if searxng_on:
        try:
            import requests
            resp=_http_get(f"{config.SEARXNG_BASE_URL}/search",params={"q":q,"format":"json","language":"zh-CN","categories":"general","pageno":1},timeout=8)
            data=resp.json()
            for r in data.get("results",[])[:mr]:
                results.append(f"{r.get('title','')}\n   {r.get('url','')}\n   {r.get('content','')[:200]}")
        except: pass
    # 方案二：Argo 专业搜索（SearXNG 无结果/不可用 → 切换）
    if not results:
        try:
            argo_result = str(_argo_search(
                {"query": q, "max_results": mr, "mode": "auto"},
                **kwargs,
            ) or "")
            if argo_result and not argo_result.startswith((
                "Argo 搜索无结果", "Argo 搜索出错", "Argo 未安装",
            )):
                reason = "SearXNG 未开启或连不上" if searxng_down else "SearXNG 无结果"
                return f"{reason}，已切换到 Argo 搜索：\n" + argo_result
        except Exception:
            pass
    # 方案三：ddgs（新版 DuckDuckGo Search API）
    if not results:
        try:
            from ddgs import DDGS
            ddgs=DDGS()
            for r in ddgs.text(q,max_results=mr):
                results.append(f"{r.get('title','')}\n   {r.get('href','')}\n   {r.get('body','')[:200]}")
        except: pass
    # 方案四：旧版 duckduckgo_search 库
    if not results:
        try:
            from duckduckgo_search import DDGS as DDGS_old
            ddgs=DDGS_old(timeout=20)
            for r in ddgs.text(q,max_results=mr):
                results.append(f"{r.get('title','')}\n   {r.get('href','')}\n   {r.get('body','')[:200]}")
        except: pass
    # 方案五：DuckDuckGo HTML 直接抓取
    if not results:
        try:
            import requests,re; from urllib.parse import quote
            resp=_http_get(f"https://html.duckduckgo.com/html/?q={quote(q)}",headers={"User-Agent":"Mozilla/5.0"},timeout=20)
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

_ARGO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "argo")
_ARGO_SEARCH_PY = os.path.join(_ARGO_DIR, "scripts", "search.py")

def _argo_search(args,**kwargs):
    """Argo 全能搜索：调 Argo CLI（brain/argo/scripts/search.py）拿结构化结果。"""
    q=args.get("query","").strip()
    if not q: return "请提供搜索关键词"
    mr=int(args.get("max_results",5)); mr=max(1,min(mr,10))
    mode=args.get("mode","auto")
    if mode not in ("auto","fast","deep","budget"): mode="auto"
    if not os.path.exists(_ARGO_SEARCH_PY):
        return "Argo 未安装（brain/argo/ 缺失）"
    try:
        import subprocess, json as _json
        proc=subprocess.run(
            [sys.executable, _ARGO_SEARCH_PY, q, "--json", "--max-results", str(mr), "--mode", mode],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=90, cwd=_ARGO_DIR,
        )
        out=proc.stdout or ""
        # CLI 可能把日志打到 stdout 前面，从第一个 { 开始解析
        try:
            idx=out.find("{")
            data=_json.loads(out[idx:]) if idx>=0 else {}
        except Exception:
            data={}
        if not data or not data.get("results"):
            err=(proc.stderr or "").strip().splitlines()
            tail=err[-1][:200] if err else ""
            return f"Argo 搜索无结果（{tail or '可能被反爬或引擎不可用'}）"
        domain=data.get("domain","")
        lines=[f"🔍 Argo 搜索「{q}」" + (f"（{domain}）" if domain else "")]
        for r in data.get("results", [])[:mr]:
            title=str(r.get("title") or "")
            url=str(r.get("url") or "")
            snippet=str(r.get("snippet") or r.get("content") or "")
            score=r.get("score")
            lines.append(f"· {title}")
            if snippet: lines.append(f"    {snippet[:220]}")
            lines.append(f"    {url}")
            if score is not None:
                lines.append(f"    可信度 {float(score):.2f}")
        note=data.get("recovery") or data.get("login_hint") or {}
        if isinstance(note, dict) and note.get("needs_login"):
            lines.append("（部分源需登录，未取到登录墙内容）")
        try: from brain.surf import save_record; save_record("argo",q,lines[1][:60] if len(lines)>1 else q,"", "\n".join(lines)[:400])
        except Exception: pass
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return "Argo 搜索超时（60秒）"
    except Exception as e:
        return f"Argo 搜索出错: {e}"

def _bilibili_search(args,**kwargs):
    keyword=args["keyword"]
    try:
        from brain.surf import search_bilibili,save_record,get_store
        v=search_bilibili(keyword)
        if not v: return "B站搜索无结果"
        # 兴趣标签：搜索词自动记入（供主动冲浪优先推荐），并进入搜索冷却
        try:
            store = get_store()
            store.add_tag(keyword, source="auto")
            store.mark_tag_searched(keyword)
        except Exception:
            pass
        r=[f"B站搜索「{keyword}」结果:"]; 
        for x in v[:5]:
            meta = " · ".join(str(x.get(k) or "") for k in ("author","play") if x.get(k))
            r.append(f"  {x['title']}" + (f"（{meta}）" if meta else "") + f"\n  {x['url']}")
        try:
            save_record("bilibili",keyword,v[0]["title"],v[0]["url"],results=v)
        except Exception:
            pass  # 冲浪记录失败不影响搜索结果
        return "\n".join(r)
    except Exception as e:
        return f"B站搜索出错: {e}"

	# ═══════════════════════════════════════════════════════════════════
#  联网扩展工具
# ═══════════════════════════════════════════════════════════════════

def _read_url(args,**kwargs):
    url=args["url"]
    # 1) 优先 Jina Reader：能渲染 JS、返回干净正文
    try:
        import requests
        r=_http_get("https://r.jina.ai/"+url,headers={"User-Agent":"Mozilla/5.0","X-Return-Format":"text"},timeout=30)
        if r.status_code==200 and r.text.strip():
            t=r.text.strip()
            return t[:3000]+("\n...(截断)" if len(t)>3000 else "")
    except Exception: pass
    # 2) 回退：直接抓 HTML 剥标签
    try:
        import requests,re
        resp=_http_get(url,headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},timeout=15)
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
        import requests
        if location:
            from urllib.parse import quote
            resp=_http_get(f"https://wttr.in/{quote(location)}?format=j1",headers={"User-Agent":"curl/8.0"},timeout=12)
        else:
            resp=_http_get("https://wttr.in?format=j1",headers={"User-Agent":"curl/8.0"},timeout=12)
        data=resp.json()
        c=data["current_condition"][0]; area=data["nearest_area"][0]
        place=f"{area['areaName'][0]['value']}, {area['country'][0]['value']}"
        lines=[f"🌤 {place}",
               f"🌡 {c['temp_C']}°C (体感 {c['FeelsLikeC']}°C)",
               f"☁ {c['weatherDesc'][0]['value']}",
               f"💧 湿度 {c['humidity']}% | 🌬 风速 {c['windspeedKmph']}km/h"]
        # 🆕 未来几天预报（wttr.in j1 自带 weather[]，约 3 天）：不再依赖联网搜索
        try:
            forecast=data.get("weather",[]) or []
            if forecast:
                lines.append("")
                lines.append("📅 未来几天：")
                for d in forecast[:4]:
                    date=str(d.get("date",""))[5:]  # MM-DD
                    desc=(d.get("weatherDesc") or [{}])[0].get("value","")
                    lines.append(f"  · {date}  {d.get('mintempC','?')}~{d.get('maxtempC','?')}°C  {desc}")
        except Exception:
            pass
        return "\n".join(lines)
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
        resp=_http_get(search_url,params=params,headers={"User-Agent":"RikkaAI/1.0"},timeout=10)
        pages=resp.json().get("query",{}).get("search",[])
        if not pages: return f"维基百科未找到「{q}」"
        title=pages[0]["title"]
        params2={"action":"query","format":"json","titles":title,"prop":"extracts","exintro":1,"explaintext":1,"utf8":1}
        resp2=_http_get(search_url,params=params2,headers={"User-Agent":"RikkaAI/1.0"},timeout=10)
        for pid,page in resp2.json().get("query",{}).get("pages",{}).items():
            if pid=="-1": continue
            text=page.get("extract","")[:2000]
            if len(page.get("extract",""))>2000: text+="\n...(截断)"
            return f"📖 {title}\n{text}\n\n详见: https://zh.wikipedia.org/wiki/{quote(title)}"
        return f"维基百科未找到「{q}」"
    except Exception as e:
        return f"维基百科查询失败: {e}"

def _read_rss(args,**kwargs):
    feed_url=args["feed_url"]
    try:
        import feedparser
        d=feedparser.parse(feed_url)
        if not d.entries: return f"RSS 源无内容或解析失败: {feed_url}"
        lines=[f"📡 {d.feed.get('title',feed_url)}（{len(d.entries)} 条）:"]
        for e in d.entries[:8]:
            title=e.get("title","")
            link=e.get("link","")
            pub=e.get("published","")[:16].replace(",","")
            summ=""
            s=e.get("summary") or e.get("description") or ""
            if s:
                summ=re.sub(r"<[^>]+>"," ",s)
                summ=re.sub(r"\s+"," ",summ).strip()[:160]
            lines.append(f"• {title}\n  {link}\n  {pub} {summ}")
        return "\n\n".join(lines)
    except Exception as e:
        return f"RSS 读取失败: {e}"

def _youtube_transcript(args,**kwargs):
    url=args["url"]
    try:
        import yt_dlp,requests,re
        ydl_opts={"quiet":True,"skip_download":True,"no_warnings":True,"extract_flat":False}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info=ydl.extract_info(url,download=False)
        title=info.get("title","")
        uploader=info.get("uploader","")
        dur=int(info.get("duration",0) or 0)
        dur_s=f"{dur//60}:{dur%60:02d}"
        desc=(info.get("description") or "")[:600]
        caps=info.get("subtitles") or info.get("automatic_captions") or {}
        transcript=""
        for lang in ("zh-Hans","zh-CN","zh","ja","en"):
            if lang in caps and caps[lang]:
                chosen=caps[lang][-1]
                try:
                    r=_http_get(chosen.get("url",""),timeout=15)
                    txt=re.sub(r"<[^>]+>","",r.text)
                    lines=[l.strip() for l in txt.splitlines()]
                    lines=[re.sub(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*","",l) for l in lines]
                    lines=[l for l in lines if l and not re.match(r"^\d{2}:\d{2}:\d{2}",l) and "WEBVTT" not in l and "-->" not in l]
                    transcript=" ".join(lines)[:2500]
                except Exception: pass
                break
        out=[f"🎬 {title}",f"📺 {uploader} | 时长 {dur_s}"]
        if desc: out.append(f"📝 {desc}")
        if transcript: out.append(f"🗣 字幕摘录:\n{transcript}")
        else: out.append("（无可用字幕）")
        return "\n\n".join(out)
    except Exception as e:
        return f"YouTube 获取失败: {e}"

def _jina_fetch(url):
    """用 Jina Reader 抓网页正文，成功返回文本，失败返回 None。"""
    try:
        import requests
        r=_http_get("https://r.jina.ai/"+url,headers={"User-Agent":"Mozilla/5.0"},timeout=30)
        if r.status_code==200 and r.text.strip(): return r.text.strip()
    except Exception: pass
    return None

def _github_repo(args,**kwargs):
    repo=args["repo"].strip("/")
    path=args.get("path","")
    try:
        import requests
        base=f"https://api.github.com/repos/{repo}"
        if path:
            # 1) 文件内容：先试 raw API，再试 raw.githubusercontent，最后 Jina 兜底
            h={"User-Agent":"RikkaAI/1.0","Accept":"application/vnd.github.raw"}
            r=_http_get(f"{base}/contents/{path}",headers=h,timeout=15)
            ct=(r.headers.get("content-type","") or "").lower()
            if r.status_code==200 and "json" not in ct:
                return f"📦 {repo} 文件 {path}:\n\n{r.text[:3000]}"
            for branch in ("master","main"):
                raw=_jina_fetch(f"https://raw.githubusercontent.com/{repo}/{branch}/{path}")
                if raw and len(raw)<30000:
                    return f"📦 {repo} 文件 {path}:\n\n{raw[:3000]}"
            # 目录：Jina 读 GitHub tree 页面
            tree=_jina_fetch(f"https://github.com/{repo}/tree/master/{path}")
            if not tree or "not found" in tree.lower()[:200]:
                tree=_jina_fetch(f"https://github.com/{repo}/tree/main/{path}")
            if tree:
                return f"📁 {repo}/{path}:\n\n{tree[:2500]}"
            return "获取文件失败（GitHub API 限流，Jina 兜底也失败）"
        # 仓库概览：API 优先，Jina 兜底
        d=None
        r=_http_get(base,headers={"User-Agent":"RikkaAI/1.0"},timeout=15)
        if r.status_code==200:
            d=r.json()
            readme=""
            r2=_http_get(f"{base}/readme",headers={"User-Agent":"RikkaAI/1.0","Accept":"application/vnd.github.raw"},timeout=15)
            if r2.status_code==200 and "json" not in (r2.headers.get("content-type","") or "").lower():
                readme=r2.text[:1500]
            if readme:
                return (f"📦 {d.get('full_name','')}\n"
                        f"⭐ {d.get('stargazers_count',0)} | 🍴 {d.get('forks_count',0)} | 语言 {d.get('language')} | 更新 {str(d.get('updated_at',''))[:10]}\n"
                        f"📝 {d.get('description') or '无描述'}\n"
                        f"🔗 {d.get('html_url','')}\n\n"
                        f"README:\n{readme}")
        # 限流兜底：Jina 读 GitHub 仓库页
        jina=_jina_fetch(f"https://github.com/{repo}")
        if jina:
            # Jina 对 github 页面有约定：前缀是 repo 信息行，之后是 README
            return f"📦 {repo}（Jina 抓取）:\n\n{jina[:3000]}"
        if d is not None:
            return (f"📦 {d.get('full_name','')}\n"
                    f"⭐ {d.get('stargazers_count',0)} | 🍴 {d.get('forks_count',0)} | 语言 {d.get('language')}\n"
                    f"📝 {d.get('description') or '无描述'}\n"
                    f"🔗 {d.get('html_url','')}")
        return "仓库获取失败（GitHub API 限流，Jina 兜底也失败）"
    except Exception as e:
        return f"GitHub 查询失败: {e}"

def _browser_task(args,**kwargs):
    task=args["task"]
    steps=int(args.get("max_steps",12) or 12)
    steps=max(1,min(steps,40))
    if _STOP_REQUESTED:
        return "⏹ 浏览器任务已停止"
    try:
        import asyncio,os
        os.environ.setdefault("ANONYMIZED_TELEMETRY","False")
        os.environ["BROWSER_USE_SETUP_LOGGING"]="false"  # 阻止 browser_use import 时配置 INFO 日志刷屏
        from browser_use import Agent, BrowserSession
        try:
            import logging as _logging
            _logging.getLogger("browser_use").setLevel(_logging.ERROR)  # 压掉剩余 warning
        except Exception: pass
        from browser_use.llm.deepseek.chat import ChatDeepSeek
        import config
        class _RikkaChatDeepSeek(ChatDeepSeek):
            def _client(self):
                client=super()._client()
                orig=client.chat.completions.create
                async def wrap(*a,**kw):
                    body=dict(kw.get("extra_body") or {})
                    body.setdefault("thinking",{"type":"disabled"})
                    kw["extra_body"]=body
                    return await orig(*a,**kw)
                client.chat.completions.create=wrap
                return client
        llm=_RikkaChatDeepSeek(model=config.MODEL,base_url=config.API_BASE,api_key=config.API_KEY,temperature=0.5)
        async def _run():
            agent=Agent(
                task=task,
                llm=llm,
                browser=BrowserSession(headless=True),
                use_vision=False,  # DeepSeek 是纯文本模型，不支持视觉
            )
            result=await agent.run(max_steps=steps)
            return result.final_result() or "任务执行完成，但没有总结出明确结果。"
        text=asyncio.run(_run())
        return "🌐 浏览器任务结果:\n"+str(text)[:2500]
    except Exception as e:
        return f"浏览器任务失败: {e}"

_OPENCLI_JS = os.path.join(
    os.path.expanduser("~"), "AppData", "Roaming", "npm", "node_modules",
    "@jackwener", "opencli", "dist", "src", "main.js",
)
_TWITTER_CLI = os.path.join(os.path.expanduser("~"), ".local", "bin", "twitter.exe")
_AGENT_REACH_CFG = os.path.join(os.path.expanduser("~"), ".agent-reach", "config.yaml")

# twitter-cli 能覆盖的动作：action -> (twitter-cli 命令, 需要 target, 需要 limit)
# 注意：search 走 twitter-cli 会 404（上游端点问题），trending 无对应命令——这两个固定走 OpenCLI
_TW_CLI_ACTIONS = {
    "timeline": ("feed",       False, True),
    "tweets":   ("user-posts", True,  True),
    "profile":  ("user",       True,  False),
    "tweet":    ("tweet",      True,  False),
    "article":  ("article",    True,  False),
    "whoami":   ("whoami",     False, False),
}

def _twitter_cli_env():
    """构造 twitter-cli 子进程环境：cookie 优先用进程已有 env，其次读 ~/.agent-reach/config.yaml；代理固定注入"""
    import os
    env = dict(os.environ)
    for k in ("TWITTER_AUTH_TOKEN", "TWITTER_CT0"):
        if not env.get(k):
            env.pop(k, None)
    # 从 agent-reach 配置补缺
    missing = {"TWITTER_AUTH_TOKEN", "TWITTER_CT0"} - set(env.keys())
    if missing and os.path.exists(_AGENT_REACH_CFG):
        try:
            with open(_AGENT_REACH_CFG, encoding="utf-8", errors="replace") as f:
                raw = f.read()
            for key, envk in (("twitter_auth_token", "TWITTER_AUTH_TOKEN"), ("twitter_ct0", "TWITTER_CT0")):
                if envk not in env:
                    for line in raw.splitlines():
                        line = line.strip()
                        if line.startswith(key + ":"):
                            val = line.split(":", 1)[1].strip().strip('"').strip("'")
                            if val:
                                env[envk] = val
                            break
        except Exception:
            pass
    # 代理（国内必须走 VPN）
    try:
        import config
        proxy = getattr(config, "TWITTER_PROXY", "")
    except Exception:
        proxy = ""
    if proxy:
        env.setdefault("HTTP_PROXY", proxy)
        env.setdefault("HTTPS_PROXY", proxy)
    return env

def _read_twitter(args,**kwargs):
    action=args.get("action","timeline")
    target=(args.get("target") or "").strip()
    limit=max(1,min(int(args.get("limit",10) or 10),20))
    read_actions={"timeline","profile","tweets","search","tweet","article","trending","whoami"}
    if action not in read_actions:
        return f"不支持的 Twitter 操作: {action}（只读：timeline/profile/tweets/search/tweet/article/trending）"
    import subprocess,os,shutil

    tw_cli_note = ""

    # ── 优先：twitter-cli + cookie（彻底免 Chrome，重启也不用登录）──
    if action in _TW_CLI_ACTIONS and os.path.exists(_TWITTER_CLI):
        env = _twitter_cli_env()
        if env.get("TWITTER_AUTH_TOKEN") and env.get("TWITTER_CT0"):
            tw_cmd, need_target, use_limit = _TW_CLI_ACTIONS[action]
            if need_target and not target:
                return f"Twitter {action} 需要指定 target（用户名或推文 ID）"
            cmd=[_TWITTER_CLI, tw_cmd]
            if need_target: cmd.append(target)
            if use_limit: cmd += ["-n", str(limit)]
            cmd += ["--yaml"]
            try:
                p=subprocess.run(cmd,capture_output=True,text=True,timeout=90,
                                 encoding="utf-8",errors="replace",env=env)
            except subprocess.TimeoutExpired:
                tw_cli_note = f"twitter-cli {action} 超时（cookie 或代理问题），降级 OpenCLI。"
            else:
                out=(p.stdout or "").strip()
                if out and "\nok: true" in ("\n"+out):
                    return out[:3000]+("\n...(截断)" if len(out)>3000 else "")
                tw_cli_note = f"twitter-cli {action} 未返回数据，降级 OpenCLI。{(p.stderr or '').strip()[-200:]}"
        else:
            tw_cli_note = "twitter-cli cookie 未配置，降级 OpenCLI。"
    elif action not in _TW_CLI_ACTIONS:
        tw_cli_note = ""  # search/trending 直接走 OpenCLI

    # ── 兜底：OpenCLI（Chrome 登录态）──
    if not os.path.exists(_OPENCLI_JS):
        return (tw_cli_note + " OpenCLI 未找到，请先运行 agent-reach install --system --channels opencli").strip()
    node=shutil.which("node")
    if not node:
        return (tw_cli_note + " node 未找到，无法调用 OpenCLI").strip()
    cmd=[node,_OPENCLI_JS,"twitter",action]
    if target: cmd.append(target)
    if action in ("timeline","tweets","search"): cmd+=["--limit",str(limit)]
    cmd+=["-f","yaml"]
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=120,encoding="utf-8",errors="replace")
    except subprocess.TimeoutExpired:
        return (tw_cli_note + " Twitter 读取超时（Chrome/登录态可能有问题）").strip()
    out=(p.stdout or "").strip()
    if not out:
        return f"{tw_cli_note}Twitter 读取失败: {(p.stderr or p.stdout or '')[:300]}".strip()
    return (tw_cli_note + out[:3000] + ("\n...(截断)" if len(out)>3000 else "")).strip()

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
    return "✅ 已记入备忘录"

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
        return "✅ 日记已记录"
    except Exception as e:
        return f"❌ 日记记录失败：{e}"


def _write_diary(args, **kwargs):
    """六花主动写今天的日记：通读流水 → LLM 生成第一人称随笔 → 存入 summary。"""
    mood = args.get("mood", "")
    try:
        from brain import diary as diary_module
        result = diary_module.write_diary_summary(mood=mood)
        if result.get("ok"):
            return f"✅ 今天的日记写好了：\n{result['summary']}"
        return f"❌ {result.get('error', '写日记失败')}"
    except Exception as e:
        return f"❌ 写日记失败：{e}"


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
            return "❌ QQ 消息发送失败"
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

def _query_qq_contacts(args, **kwargs):
    """查询 QQ 联系人（好友/群列表）"""
    if _QQ_BRIDGE is None:
        return "❌ QQ 桥接未连接"
    try:
        if not _QQ_BRIDGE.is_running:
            return "❌ QQ 桥接不在运行状态"
        scope = args.get("scope", "friends")
        keyword = (args.get("keyword") or "").strip().lower()
        lines = []
        if scope in ("friends", "all"):
            friends = _QQ_BRIDGE.get_friend_list()
            fs = [
                {"user_id": f.get("user_id"), "nickname": f.get("nickname", ""),
                 "remark": f.get("remark", "")}
                for f in friends
            ]
            if keyword:
                fs = [f for f in fs if keyword in str(f.get("nickname", "")).lower()
                      or keyword in str(f.get("remark", "")).lower()]
            lines.append(f"📇 好友({len(fs)}个):")
            lines.append("；".join(
                f"{f['nickname']}(备注:{f['remark']}) id={f['user_id']}" for f in fs
            ) or "无")
        if scope in ("groups", "all"):
            groups = _QQ_BRIDGE.get_group_list()
            gs = [
                {"group_id": g.get("group_id"), "group_name": g.get("group_name", ""),
                 "member_count": g.get("member_count", 0)}
                for g in groups
            ]
            if keyword:
                gs = [g for g in gs if keyword in str(g.get("group_name", "")).lower()]
            lines.append(f"👥 群({len(gs)}个):")
            lines.append("；".join(
                f"{g['group_name']}({g['member_count']}人) id={g['group_id']}" for g in gs
            ) or "无")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ QQ 联系人查询异常: {e}"

def _generate_image(args, **kwargs):
    """AI 图片生成工具"""
    prompt = args.get("prompt", "")
    n = int(args.get("n", 1))
    if not prompt:
        return "❌ 没有提供图片描述"
    try:
        import os as _os, requests, re
        preset = config.get_active_image_generation_preset()
        if not preset:
            return "❌ 未启用生图模型方案，请在设置 > 智能搜图中添加并启用方案"
        api_key = preset.get("api_key", "")
        if not api_key:
            return f"❌ 生图方案「{preset.get('name', '未命名')}」未配置 API Key"
        model = str(args.get("model") or preset.get("model") or "").strip()
        if not model:
            return f"❌ 生图方案「{preset.get('name', '未命名')}」未配置模型"
        api_base = str(preset.get("api_base") or "").strip().rstrip("/")
        if not api_base:
            return f"❌ 生图方案「{preset.get('name', '未命名')}」未配置请求地址"
        endpoint = api_base if api_base.endswith("/images/generations") else f"{api_base}/images/generations"

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "prompt": prompt, "n": min(n, 4)}

        resp = requests.post(
            endpoint,
            headers=headers, json=payload, timeout=120
        )
        result = resp.json()

        if "error" in result:
            err = result["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            return f"❌ 图片生成失败: {msg}"

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
            r = _http_get(img_url, timeout=30)
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
                msg += " 已发到你的 QQ～快去查收！📱"
            return msg
        return "❌ 图片下载失败"
    except requests.Timeout:
        return "❌ 图片生成超时（模型响应较慢），等会儿再试试～"
    except Exception as e:
        return f"❌ 图片生成出错: {e}"


def _build_summary(args, **kwargs):
    """生成记忆总结工具"""
    level = args.get("level", "weekly")
    period = args.get("period_key", "")
    try:
        from brain import memory_summary as _ms
        if level == "yearly":
            result = _ms.build_yearly(period or None)
        elif level == "monthly":
            result = _ms.build_monthly(period or None)
        elif level == "daily":
            result = _ms.build_daily(period or None)
        else:
            result = _ms.build_weekly(period or None)
        title = result.get("title", "")
        content = result.get("content", "")
        if content:
            return "OK " + title + "\n\n" + content[:500]
        elif "没有记录" in (title or ""):
            return "没有记录: " + title
        return "OK " + title
    except Exception as e:
        return "生成失败: " + str(e)

_HANDLERS = {
    "read_file":_read_file,"write_file":_write_file,"edit_file":_edit_file,
    "list_directory":_list_directory,"search_files":_search_files,"grep_file":_grep_file,
    "get_current_time":_get_current_time,"get_system_info":_get_system_info,"get_network_status":_get_network_status,
    "read_summaries":_read_summaries,
    "open_app":_open_app,"screenshot":_screenshot,"send_image":_send_image,"download_image":_download_image,"search_images":_search_images,"search_images_smart":_search_images_smart,
    "game_guide":_game_guide,
    "describe_image":_describe_image,"ocr_image":_ocr_image,
    "save_memory":_save_memory,"read_memories":_read_memories,
    "manage_user_state":_manage_user_state,"correct_memory":_correct_memory,
    "web_search":_web_search,"bilibili_search":_bilibili_search,
    # 联网扩展
    "argo_search":_argo_search,
    "read_url":_read_url,"get_weather":_get_weather,"search_news":_search_news,"search_wiki":_search_wiki,
    "read_rss":_read_rss,"youtube_transcript":_youtube_transcript,"github_repo":_github_repo,"browser_task":_browser_task,"read_twitter":_read_twitter,
    # 主动性工具
    "set_proactive_timer":_set_proactive_timer,"set_follow_up":_set_follow_up,"cancel_follow_up":_cancel_follow_up,
    "write_to_memo":_write_to_memo,"append_self_discovery":_append_self_discovery,"update_diary":_update_diary,"write_diary":_write_diary,
    # QQ 消息
    "send_qq_message":_send_qq_message,
    "send_qq_image":_send_qq_image,
    "query_qq_contacts":_query_qq_contacts,
    # AI 图片生成
    "generate_image":_generate_image,
    # 记忆总结
    "build_summary":_build_summary,
}
