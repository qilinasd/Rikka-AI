(function () {
  "use strict";

  const ROOT = "../../ui_assets/03_Icons/Outline/";
  const AVATAR = "../../assets/images/avatar.png";

  const navItems = [
    ["home", "home", "首页"],
    ["chat", "chat", "对话"],
    ["knowledge", "knowledge", "知识库"],
    ["drawing", "drawing", "AI 绘画"],
    ["tools", "workflow", "工作流"],
    ["plugin", "plugin", "插件中心"],
    ["memo", "memory", "记忆"],
    ["history", "history", "历史记录"],
    ["settings", "settings", "设置"]
  ];

  const modeItems = [
    ["chat", "chat", "AI 聊天"],
    ["tools", "workflow", "更多能力"]
  ];

  const quickItems = [
    { section: "chat", icon: "ai", title: "AI 聊天", copy: "与六花聊聊灵感、生活和那些小烦恼", cta: "开始对话", color: "#7449df" },
    { section: "tools", icon: "workflow", title: "更多功能", copy: "探索六花的工具箱与自动化能力", cta: "去探索", color: "#5267c8" }
  ];

  const toolItems = [
    ["drawing", "drawing", "AI 画图"],
    ["memo", "memory", "备忘记录"],
    ["tools", "more", "更多工具"]
  ];

  const statMeta = [
    ["messages", "chat", "对话消息", "今日专注" , "#6945e8"],
    ["images", "image", "生成图片", "灵感成画", "#ed9550"],
    ["sessions", "history", "历史会话", "持续陪伴", "#bf50df"],
    ["summaries", "knowledge", "摘要记录", "知识沉淀", "#45b878"]
  ];

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>'"]/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char];
    });
  }

  function icon(name, className) {
    return '<img class="' + (className || "") + '" src="' + ROOT + name + '.svg" alt="">';
  }

  function softColor(hex) {
    return hex + "1c";
  }

  function renderNavigation() {
    const target = document.getElementById("primary-nav");
    if (!target) return;
    target.innerHTML = navItems.map(function (item) {
      const active = item[0] === "home" ? " active" : "";
      return '<button class="' + active + '" type="button" data-section="' + item[0] + '">' +
        icon(item[1], "nav-icon") + '<span class="nav-label">' + item[2] + "</span></button>";
    }).join("");
  }

  function renderModes() {
    document.getElementById("mode-actions").innerHTML = modeItems.map(function (item) {
      return '<button class="mode-button" type="button" data-section="' + item[0] + '">' +
        icon(item[1]) + "<span>" + item[2] + "</span></button>";
    }).join("");
  }

  function renderQuickActions() {
    document.getElementById("quick-actions").innerHTML = quickItems.map(function (item) {
      const action = item.prompt ? ' data-prompt="' + escapeHtml(item.prompt) + '"' : ' data-section="' + item.section + '"';
      const style = "--accent:" + item.color + ";--accent-soft:" + softColor(item.color);
      return '<button class="quick-card" type="button"' + action + ' style="' + style + '">' +
        '<span class="quick-icon">' + icon(item.icon) + "</span>" +
        "<strong>" + item.title + "</strong><small>" + item.copy + "</small>" +
        '<span class="card-cta">' + item.cta + " →</span></button>";
    }).join("");
  }

  function renderTools() {
    document.getElementById("tool-grid").innerHTML = toolItems.map(function (item, index) {
      const colors = ["#6f4ce0", "#d457b5", "#4f9ed1", "#7961d8", "#e48b55", "#55ad83"];
      const color = colors[index];
      return '<button class="tool-button" type="button" data-section="' + item[0] + '" style="--accent:' + color + ";--accent-soft:" + softColor(color) + '">' +
        '<span class="tool-icon">' + icon(item[1]) + "</span><span>" + item[2] + "</span></button>";
    }).join("");
  }

  function formatTime(raw) {
    if (!raw) return "刚刚";
    const normalized = String(raw).replace(" ", "T");
    const date = new Date(normalized);
    if (Number.isNaN(date.getTime())) return escapeHtml(String(raw).slice(11, 16) || raw);
    const now = new Date();
    const sameDay = date.toDateString() === now.toDateString();
    if (sameDay) return String(date.getHours()).padStart(2, "0") + ":" + String(date.getMinutes()).padStart(2, "0");
    const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) return "昨天";
    return String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0");
  }

  function renderRecent(sessions) {
    const target = document.getElementById("recent-list");
    if (!sessions || !sessions.length) {
      target.innerHTML = '<div class="empty-state">还没有对话记录。<br>在上方写下第一句话，六花会一直在这里。</div>';
      return;
    }
    target.innerHTML = sessions.slice(0, 5).map(function (session) {
      const title = escapeHtml(session.title || "和六花的新对话");
      const count = Number(session.msg_count || 0);
      return '<button class="recent-row" type="button" data-session-id="' + Number(session.id) + '">' +
        '<img class="avatar" src="' + AVATAR + '" alt="六花">' +
        '<span class="recent-copy"><strong>' + title + "</strong><small>" + count + " 条消息 · 继续上次的话题</small></span>" +
        '<span class="recent-tag">AI 聊天</span><time class="recent-time">' + formatTime(session.updated_at) + "</time></button>";
    }).join("");
  }

  function renderStats(stats) {
    stats = stats || {};
    document.getElementById("stats-grid").innerHTML = statMeta.map(function (item) {
      const color = item[4];
      return '<article class="stat-card" style="--accent:' + color + ";--accent-soft:" + softColor(color) + '">' +
        '<span class="stat-label"><span class="stat-icon">' + icon(item[1]) + "</span>" + item[2] + "</span>" +
        '<strong class="stat-value">' + Number(stats[item[0]] || 0).toLocaleString("zh-CN") + "</strong>" +
        '<small class="stat-trend">' + item[3] + "</small></article>";
    }).join("");
  }

  function renderOverview(overview) {
    overview = overview || {};
    const chart = document.getElementById("overview-chart");
    const values = (overview.values || []).map(function (v) { return Number(v || 0); });
    const labels = overview.labels || [];
    if (!chart) return;
    if (!values.length || !values.some(function (v) { return v > 0; })) {
      chart.innerHTML = "<span>暂无趋势数据</span>";
    } else {
      const max = Math.max.apply(null, values.concat([1]));
      chart.innerHTML = values.map(function (value, index) {
        const height = Math.max(4, Math.round(value / max * 72));
        return '<i title="' + escapeHtml(labels[index] || "") + '：' + value + '" style="height:' + height + 'px"></i>';
      }).join("");
    }
    const summary = document.getElementById("overview-summary");
    if (summary) {
      const total = values.reduce(function (a, b) { return a + b; }, 0);
      let active = "暂无记录";
      if (values.length && Math.max.apply(null, values) > 0) {
        const index = values.indexOf(Math.max.apply(null, values));
        active = (labels[index] || "") + " · " + values[index] + " 条";
      }
      summary.innerHTML = "<span>近 7 天消息 <b>" + total.toLocaleString("zh-CN") + "</b> 条</span><span>最活跃日期 <b>" + escapeHtml(active) + "</b></span>";
    }
  }

  function renderData(data) {
    document.getElementById("greeting-title").textContent = data.greeting || "欢迎回来，主人";
    document.getElementById("greeting-subtitle").textContent = data.subtitle || "今天想和我聊些什么呢？";
    renderRecent(data.sessions || []);
    renderStats(data.stats || {});
    renderOverview(data.overview || {});
  }

  renderNavigation();
  renderModes();
  renderQuickActions();
  renderTools();

  window.RikkaComponents = { renderData: renderData, escapeHtml: escapeHtml };
}());
