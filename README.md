# 六花AI (RikkaAI) — 邪王真眼 AI 伙伴

一个具有人格设定、长期记忆、主动交互能力的桌面 AI 伙伴，基于大型语言模型构建，以「小鸟游六花」为人格原型。

## 核心能力

| 能力 | 说明 |
|------|------|
| 🧠 **智能对话** | DeepSeek API，流式输出，Function Calling 42 个工具 |
| 📚 **多层记忆** | RAG 全文检索 + 知识图谱 + 文件记忆，跨会话持久化 |
| 👁 **多模态视觉** | GLM-4V-Flash 图像识别、OCR、智能搜图 |
| 🔄 **主动交互** | AI 自主判断时机与用户互动，情感状态，自我成长记录 |
| 🎨 **完整 GUI** | PyQt5 构建，9 个交互面板，暗色哥特主题 |

## 快速开始

```bash
cd RikkaAI
pip install -r requirements.txt
cp config.example.py config.py
python main.py
```

## 技术栈

`Python` `PyQt5` `DeepSeek API` `GLM-4V-Flash` `RAG` `知识图谱` `SQLite` `SearXNG`

---

> 项目持续迭代中 🌟
