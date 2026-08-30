# RikkaAI（六花）升级说明 · Phase 0–5

> 本文档汇总对六花的一轮升级：在**保留原有**流式对话、链式主动、临时回访、多层记忆、
> 情感系统、语音、QQ 桥接等全部功能的前提下，新增并接入了一批"让六花更像一个有记性、
> 会自己成长、能接外部世界的小伙伴"的能力。
> 范围：**Phase 0–5**（不含 Phase 6 的编排器精化与自我修改）。
>
> 技术实现细节、开关清单、测试命令见同目录的 [`UPGRADE_README.md`](UPGRADE_README.md)。

---

## 一、这次升级的动机（参照的六个项目）

这轮升级不是凭空加的，而是参照你之前给我的六个开源项目的核心思路，各取所长：

| 来源项目 | 借鉴的核心 |
|---|---|
| [GBrain](https://github.com/garrytan/gbrain)（YC 总裁的记忆层） | 综合检索 + **gap analysis**（主动告诉你"脑子里还不知道什么"）、24/7 后台"做梦"蒸馏机制 |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent)（We 的自进化 agent） | 定时自动化、跨会话记忆与用户建模的雏形 |
| [CowAgent](https://github.com/zhayujie/CowAgent) | 三层记忆 + **Deep Dream 蒸馏**、知识 wiki、按能力路由模型 |
| [genesis-agent](https://github.com/Garrus800-stack/genesis-agent) | surprise 加权遗忘、需求体系（社交/掌控/新奇/休息）+ 精力池 + 孤独感、**LLM 提案/机器验证**、离线自动切换 |
| [EverOS](https://github.com/EverMind-AI/EverOS) | **Markdown 真源记忆**（可读/可 diff/可 git/归你所有）、正交多维检索、后台 reflection 整合 |
| [OpenHuman](https://github.com/tinyhumansai/openhuman) | MCP 接入、个人数据自动拉取、TokenJuice 式**工具输出压缩**、隐私模式 |

一句话：**六花最缺的不是"会聊天"，而是"后台自主成长"和"接外部世界的口子"，这次就是补这两块。**

---

## 二、新增了什么（按阶段）

全部新能力都是**独立模块**（在 `brain/` 下），各自挂在配置开关后面，可单独开/关、可回滚，不影响已有主链路。

### 🧩 Phase 0 · 底座
| 模块 | 作用 | 开关 |
|---|---|---|
| `config.py` 升级开关框架 | 一套统一的"升级特性开关"，可持久化到 user_config.json | — |
| [`brain/features.py`](brain/features.py) | 统一读取开关：`features.is_enabled("xxx")` | — |
| [`brain/costlog.py`](brain/costlog.py) | **执行记录 + token/成本核算**：记录每次工具调用/LLM 调用，聚合今日/按模型/按工具成本 | `costlog_enabled` |

### 🧠 Phase 1 · 记忆层（让"记得住"变"记得准 + 可迁移"）
| 模块 | 作用 | 开关 |
|---|---|---|
| [`brain/memory/markdown_store.py`](brain/memory/markdown_store.py) | 把记忆导出成 **Markdown 真源**（碎片/段落/实体），支持 git 版本化——记忆归你、可迁移、可 obsidian 打开编辑 | `memory_markdown_enabled` |
| [`brain/memory/tags.py`](brain/memory/tags.py) | **正交多维标签**：按 user/agent/app/project/session 多维度检索 | `memory_orthogonal_tags_enabled` |
| [`brain/memory/surprise.py`](brain/memory/surprise.py) | **surprise 加权遗忘**：越"意外/有情绪"的瞬间记得越牢 | `memory_surprise_weight_enabled` |
| [`brain/memory/gap.py`](brain/memory/gap.py) | **gap analysis**：主动提示"关于这个主题我还不知道什么" | `memory_gap_analysis_enabled` |
| [`brain/memory/wiki.py`](brain/memory/wiki.py) | **知识 wiki**：把高价值记忆自动整理成可编辑的 Markdown 百科页 | `memory_wiki_enabled` |

### 🌙 Phase 2 · 后台能力（"六花会自己成长"的关键）
| 模块 | 作用 | 开关 |
|---|---|---|
| [`brain/dream.py`](brain/dream.py) | **后台"做梦"引擎**：安静时自动合并记忆、消解矛盾、更新实体画像、给重要碎片加权重、重建 Markdown/知识库、生成叙事日记 | `dream_enabled` / `dream_consolidate_enabled` / `dream_interval_hours` |
| [`brain/scheduler.py`](brain/scheduler.py) | **自然语言定时自动化**：用一句话安排长期任务（"每天23点生成日报""每周日21点写周记"） | `cron_enabled` |
| [`brain/autofetch.py`](brain/autofetch.py) | **个人数据自动拉取**：定期扫描 inbox 把生活数据吸进记忆 | `autofetch_enabled` / `autofetch_interval_min` |
| [`brain/background.py`](brain/background.py) | 把上面三者**统一启动**的聚合入口（daemon 线程，随应用退出） | 受 dream/autofetch/cron 开关 |

### 💗 Phase 3 · 情感 / 主动（让"要不要找你"更有脑子）
| 模块 | 作用 | 开关 |
|---|---|---|
| [`brain/needs.py`](brain/needs.py) | **需求体系**：社交/掌控/新奇/休息 + 精力池 + 孤独感，并给出主动意愿信号 | `emotion_needs_enabled` |
| [`brain/planner.py`](brain/planner.py) | **概率主动决策**：估算该不该主动找（P(success)+冷却+深夜/精力压制+随机性） | `decision_planner_enabled` |

### 🌐 Phase 4 · 接外部世界（扩能力最快）
| 模块 | 作用 | 开关 |
|---|---|---|
| [`brain/mcp_client.py`](brain/mcp_client.py) | **MCP 客户端**：接入外部 MCP 服务器/工具，带缓存、优雅降级 | `mcp_enabled` |
| [`brain/model_routing.py`](brain/model_routing.py) | **按能力路由模型**：chat/vision/image/asr/tts/embedding 各走不同厂商 | `per_model_routing_enabled` |

### 🛠 Phase 5 · 稳健 / 效率
| 模块 | 作用 | 开关 |
|---|---|---|
| [`brain/compressor.py`](brain/compressor.py) | **TokenJuice 式工具输出压缩**：省 token、提速 | `tool_compress_enabled` |
| [`brain/verify.py`](brain/verify.py) | **确定性校验**：写文件前用 AST/JSON/node 检查（LLM 提案、机器验证） | `verify_enabled` |
| [`brain/netsentinel.py`](brain/netsentinel.py) | **离线自动切换**：断网建议切本地模型 + 待重放队列 | `netsentinel_enabled` |
| config | **隐私模式**：所有推理不出机 | `privacy_mode_enabled`（默认关） |

---

## 三、已经接到主链路的

这些是安全、受控的增量改造，重启六花即可生效：

- [`brain/agent.py`](brain/agent.py)：
  - 注入 **需求体系** 与 **gap analysis** 到 system prompt（受开关控制）
  - 每次**工具调用写 costlog**（执行记录 + 成本）
  - **并入 MCP 工具**到工具列表（带缓存/上限，受限模式不暴露）
  - 工具消息写入前做**输出压缩**
- [`main.py`](main.py)：应用启动时拉起后台 **做梦 / 自动拉取 / 定时**（`background.start_background_services()`）

---

## 四、备用挂点（已封装好、未硬接，按需再接）

下面这些需要动到 GUI/视觉代码、要真机运行才能验证，所以先封装成函数，没硬接（README 第四节有说明）：

1. **写文件前的确定性校验**：接进 `write_file`/`edit_file`，写入前 `verify.verify_text(...)`。
2. **按能力路由模型**：用 `model_routing.resolve("vision")` 替换现有视觉调用点。
3. **记忆写入后的打标/加权**：Scribe 保存记忆后可调 `tags.tag_fragment_multi(...)`、`surprise.boost(...)`。
4. **隐私模式消费点**：`features.is_enabled("privacy_mode_enabled")` 为真时把推理钉到本地模型。

---

## 五、如何开关 / 回滚

所有升级开关默认值在 `config.py` 的 `UPGRADE_FLAGS_DEFAULTS`，可在 `memory_data/user_config.json` 覆盖：

```python
# 关闭某个能力（例如先关掉 MCP，避免每轮联网探测）
from brain import features
features.set_flags({"mcp_enabled": False})
```

想让某个能力先关掉，在 `memory_data/user_config.json` 把对应键改成 `false` 即可。

> 注意：`privacy_mode_enabled` 默认是**关**，其余升级开关默认**开**。新注入的"需求/gap"提示会出现在对话里，不喜欢可直接关掉对应开关。

---

## 六、测试验证（全部通过）

用项目 venv 运行（`PYTHONPATH` 指向项目根）：

```
python tests/test_upgrade_phase0.py     # config 开关 + features + costlog
python tests/test_upgrade_phase1.py     # 记忆层（tags/surprise/gap/wiki/markdown）
python tests/test_upgrade_phase35.py    # needs/planner + compressor + verify + netsentinel
python tests/test_upgrade_phase24.py    # dream + scheduler + autofetch + mcp + routing
python tests/test_upgrade_wiring.py     # background 聚合 + mcp 缓存 + agent 接线
python tests/test_decision.py           # 既有回归（覆盖 agent 聊天路径）
```

**结果**：以上全部 **OK**，全模块导入 **OK**。测试产生的临时目录已清理干净。

---

## 七、你需要注意的两点

1. **`git status` 里大量 `M`（如 `brain/emotion.py`、`brain/memory_vault.py`、`gui/*`）是项目原本就有的未提交改动（你的 WIP）**，不是我改的。我这次只动了 `brain/agent.py`、`config.py`、`main.py` 三个文件，其余都是**新增**模块。我没有改动或回退任何既有的 WIP。
2. **建议真机验证**：沙箱里起不了 PyQt GUI，所以请在你的机器上 `python main.py` 启动，确认后台引擎正常、观察 prompt 里的需求/gap 注入效果。若某些能力不想默认开启，先关掉对应开关即可。
