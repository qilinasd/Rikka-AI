# 🌸 RikkaAI Design System v1.0

日系治愈风 · 樱花 × 二次元 × 轻拟物

## 目录结构

```
ui_assets/
├── 01_Foundation/              ← 设计基础
│   ├── Colors/                 品牌色板
│   ├── Typography/             字体规范
│   ├── Shadows/                阴影层级
│   ├── Radius/                 圆角规范
│   ├── Spacing/                间距规范
│   └── Design_Tokens/          design_tokens.json
│
├── 02_Logo/                    ← Logo 系列
│   ├── Horizontal/             横版 Logo SVG
│   ├── Vertical/               竖版 Logo SVG
│   ├── Icon/                   App 图标 SVG
│   ├── Splash/                 启动页 Logo
│   ├── Dark/                   深色版
│   └── Light/                  浅色版
│
├── 03_Icons/                   ← 图标库（150+）
│   ├── Outline/                线框风格
│   ├── Filled/                 填充风格
│   ├── Sakura/                 樱花主题
│   └── AI/                     AI 相关
│
├── 04_Illustration/            ← 插画素材
│   ├── Sakura/                 樱花
│   ├── Clouds/                 云
│   ├── Stars/                  星星
│   ├── Mountains/              山
│   ├── Torii/                  鸟居
│   └── Decoration/             装饰元素
│
├── 05_Components/              ← UI 组件
│   ├── Button/                 按钮（Primary/Secondary/Ghost）
│   ├── Card/                   卡片
│   ├── Input/                  输入框
│   ├── Search/                 搜索框
│   ├── Switch/                 开关
│   ├── Tabs/                   标签页
│   ├── Sidebar/                侧边栏
│   ├── Dialog/                 对话框
│   ├── Avatar/                 头像
│   ├── BottomBar/              底部栏
│   └── Navigation/             导航
│
├── 06_Pages/                   ← 页面模板
│   ├── Splash/                 启动页
│   ├── Login/                  登录
│   ├── Home/                   首页
│   ├── Chat/                   聊天
│   ├── AIDrawing/              AI 绘画
│   ├── AIMusic/                AI 音乐
│   ├── Workflow/               工作流
│   ├── Knowledge/              知识库
│   ├── Plugin/                 插件
│   ├── Profile/                个人中心
│   └── Settings/               设置
│
└── 07_Export/                  ← 导出资源
    ├── SVG/                    矢量
    ├── PNG/                    位图
    ├── PDF_Spec/               设计规范 PDF
    ├── Tokens/                 代码 Tokens
    └── HarmonyOS/              ArkTS 代码
```

## 如何使用

找到对应的文件夹，直接替换里面的 SVG/PNG 文件即可。

**例如：**
- 想换 Logo → 替换 `02_Logo/` 下的 svg
- 想换图标 → 替换 `03_Icons/Outline/` 下的 svg
- 想改颜色 → 改 `01_Foundation/Design_Tokens/design_tokens.json`
- 想改按钮样式 → 改 `05_Components/Button/` 下的素材

## 配色规范

| 名称 | HEX | 用途 |
|------|:---:|------|
| 樱粉 | `#FF7D7D` | 主色、按钮、强调 |
| 淡紫 | `#EEC9FF` | 背景装饰 |
| 深紫 | `#C8BBFF` | 标题、选中态 |
| 图标紫 | `#A478FF` | 图标默认色 |
| 奶油 | `#FFF3E6` | 悬停、气泡 |
