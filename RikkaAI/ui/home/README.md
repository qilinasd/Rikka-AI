# RikkaAI Web 首页

这是由 `PyQtWebEngine` 加载的本地桌面首页，不需要 HTTP 服务，也不会打开浏览器。

- `index.html`：页面语义结构
- `styles/tokens.css`：颜色、圆角、阴影等设计变量
- `styles/layout.css`：三栏布局与响应式规则
- `styles/components.css`：导航、输入框、卡片和状态组件
- `scripts/components.js`：界面组件及数据渲染
- `scripts/app.js`：交互与 `QWebChannel` 通信
- `gui/web_home_widget.py`：Python 数据和原生窗口桥接

设置环境变量 `RIKKAAI_NATIVE_HOME=1` 可以临时切回原生 PyQt 首页。

