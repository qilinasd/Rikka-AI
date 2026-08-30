# 首页组件结构

- `page.py`: 首页总布局与信号转发
- `background.py`: 背景图等比铺满与圆角裁切
- `sidebar.py`: 左侧导航、账户与升级入口
- `composer.py`: 欢迎输入框、发送与模式快捷键
- `quick_actions.py`: 快速开始功能卡
- `recent_sessions.py`: 最近会话列表
- `right_rail.py`: 使用统计与常用工具
- `assets.py`: 首页图标和图片路径

首页样式位于 `assets/styles/home.qss`，背景素材位于
`assets/images/home/home_background.png`。修改单个区域时，优先编辑对应模块，
无需改动 `page.py`。
