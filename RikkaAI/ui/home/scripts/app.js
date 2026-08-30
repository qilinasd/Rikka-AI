(function () {
  "use strict";

  const input = document.getElementById("home-input");
  const toast = document.getElementById("toast");
  let bridge = null;
  let toastTimer = null;
  let appearanceRequestId = 0;

  const fallbackData = {
    greeting: "欢迎回来，主人",
    subtitle: "今天想和我聊些什么呢？",
    sessions: [],
    stats: { messages: 0, images: 0, sessions: 0, summaries: 0 }
  };

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () { toast.classList.remove("visible"); }, 2200);
  }

  function parsePayload(payload) {
    try {
      return typeof payload === "string" ? JSON.parse(payload) : payload;
    } catch (error) {
      showToast("首页数据暂时无法读取");
      return fallbackData;
    }
  }

  function refresh() {
    if (!bridge) {
      window.RikkaComponents.renderData(fallbackData);
      return;
    }
    bridge.getHomeData(function (payload) {
      window.RikkaComponents.renderData(parsePayload(payload));
    });
  }

  function setAppearance(theme) {
    if (!theme) return;
    const root = document.documentElement;
    const requestId = ++appearanceRequestId;
    root.dataset.appearanceTheme = theme.themeId || "";
    root.style.setProperty("--season-accent", theme.accent);
    root.style.setProperty("--season-accent-hover", theme.accentHover);
    root.style.setProperty("--season-accent-soft", theme.accentSoft);
    root.style.setProperty("--season-accent-foreground", theme.accentForeground);
    root.style.setProperty("--season-wash", theme.wash);
    root.style.setProperty("--violet-700", theme.accentHover);
    root.style.setProperty("--violet-600", theme.accent);
    const tokens = theme.tokens || {};
    const tokenVars = {
      surface: "--season-surface",
      surface_strong: "--season-surface-strong",
      surface_soft: "--season-surface-soft",
      data_surface: "--season-data-surface",
      field: "--season-field",
      border: "--season-border",
      border_accent: "--season-border-accent",
      text: "--season-text",
      muted: "--season-muted",
      subtle: "--season-subtle",
      nav: "--season-nav",
      nav_text: "--season-nav-text",
      chart: "--season-chart",
      focus: "--season-focus"
    };
    Object.keys(tokenVars).forEach(function (key) {
      if (tokens[key]) root.style.setProperty(tokenVars[key], tokens[key]);
    });
    root.style.setProperty("--ink-950", tokens.text || theme.text);
    root.style.setProperty("--ink-800", tokens.text || theme.text);
    root.style.setProperty("--ink-650", tokens.muted || theme.text);
    root.style.setProperty("--ink-500", tokens.subtle || theme.text);
    root.style.setProperty("--glass", tokens.surface || theme.card);
    root.style.setProperty("--glass-strong", tokens.surface_strong || theme.card);
    root.style.setProperty("--glass-soft", tokens.surface_soft || theme.card);
    root.style.setProperty("--glass-border", tokens.border || theme.accentSoft);
    root.style.setProperty("--line", tokens.border_accent || theme.accentSoft);
    if (theme.background) {
      root.dataset.appearanceReady = "0";
      const background = new Image();
      background.onload = function () {
        const decoded = typeof background.decode === "function"
          ? background.decode().catch(function () {})
          : Promise.resolve();
        decoded.then(function () {
          if (requestId !== appearanceRequestId) return;
          root.style.setProperty("--season-background", 'url("' + theme.background + '")');
          root.dataset.appearanceBackground = theme.background;
          const shell = document.querySelector(".app-shell");
          if (shell) void shell.offsetWidth;
          window.requestAnimationFrame(function () {
            window.requestAnimationFrame(function () {
              if (requestId === appearanceRequestId) {
                root.dataset.appearanceReady = "1";
              }
            });
          });
        });
      };
      background.onerror = function () {
        if (requestId === appearanceRequestId) {
          root.style.setProperty("--season-background", "none");
          root.dataset.appearanceBackground = "";
          root.dataset.appearanceReady = "error";
        }
      };
      background.src = theme.background;
    } else {
      root.dataset.appearanceBackground = "";
      root.dataset.appearanceReady = "1";
    }
  }

  function submit() {
    const text = input.value.trim();
    if (!text) {
      showToast("先告诉六花你想聊些什么吧");
      input.focus();
      return;
    }
    if (!bridge) {
      showToast("当前是界面预览模式，桌面版中可直接发送");
      return;
    }
    bridge.startChat(text);
    input.value = "";
  }

  function openSection(section) {
    if (section === "home") return;
    if (section === "drawing") {
      input.value = "请帮我画一张：";
      input.focus();
      return;
    }
    if (!bridge) {
      showToast("当前是界面预览模式");
      return;
    }
    bridge.openSection(section);
  }

  function windowAction(action) {
    if (bridge && bridge.windowAction) bridge.windowAction(action);
  }

  document.getElementById("send-button").addEventListener("click", submit);
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  });

  document.addEventListener("click", function (event) {
    const windowButton = event.target.closest("[data-window-action]");
    if (windowButton) {
      windowAction(windowButton.dataset.windowAction);
      return;
    }

    const focusButton = event.target.closest("[data-focus-input]");
    if (focusButton) {
      input.focus();
      return;
    }

    const promptButton = event.target.closest("[data-prompt]");
    if (promptButton) {
      input.value = promptButton.dataset.prompt;
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
      return;
    }

    const sessionButton = event.target.closest("[data-session-id]");
    if (sessionButton) {
      if (bridge) bridge.openSession(Number(sessionButton.dataset.sessionId));
      else showToast("当前是界面预览模式");
      return;
    }

    const sectionButton = event.target.closest("[data-section]");
    if (sectionButton) openSection(sectionButton.dataset.section);
  });

  let draggingWindow = false;
  document.querySelectorAll(".window-drag-region, .toolbar-drag-handle").forEach(function (surface) {
    surface.addEventListener("pointerdown", function (event) {
      if (!bridge || !bridge.windowDrag || event.button !== 0) return;
      draggingWindow = true;
      surface.setPointerCapture(event.pointerId);
      bridge.windowDrag(Math.round(event.screenX), Math.round(event.screenY), "start");
    });
    surface.addEventListener("pointermove", function (event) {
      if (draggingWindow) bridge.windowDrag(Math.round(event.screenX), Math.round(event.screenY), "move");
    });
    surface.addEventListener("pointerup", function (event) {
      if (!draggingWindow) return;
      draggingWindow = false;
      bridge.windowDrag(Math.round(event.screenX), Math.round(event.screenY), "end");
    });
    surface.addEventListener("dblclick", function () {
      windowAction("maximize");
    });
  });

  document.addEventListener("keydown", function (event) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      input.focus();
    }
  });

  window.rikkaHome = {
    refresh: refresh,
    showToast: showToast,
    setAppearance: setAppearance
  };

  if (window.qt && window.qt.webChannelTransport && window.QWebChannel) {
    new QWebChannel(window.qt.webChannelTransport, function (channel) {
      bridge = channel.objects.rikkaBridge;
      refresh();
    });
  } else {
    refresh();
  }
}());
