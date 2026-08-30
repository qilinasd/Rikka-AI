# RikkaAI 升级说明（Phase 0–5）

> 本文件记录对六花的升级（Phase 0–5，不含 Phase 6 的编排器精化与自我修改）。
> 所有新能力都挂在 `memory_data/user_config.json` 的**特性开关**后面，可单独开关/回滚；
> 不开启时不影响现有对话、主动、记忆主链路。

## 一、新增模块一览（全部在 `brain/` 下，纯逻辑、可测试）

| 阶段 | 模块 | 能力 | 对应开关 |
|---|---|---|---|
| P0 | `brain/costlog.py` | 执行记录 + token/成本核算（JSONL，可聚合） | `costlog_enabled` |
| P0 | `brain/features.py` | 统一升级开关读取 | —（依赖 config） |
| P1 | `brain/memory/markdown_store.py` | 记忆导出为 Markdown 真源 + git 版本化（可迁移/可 obsidian） | `memory_markdown_enabled` |
| P1 | `brain/memory/tags.py` | 正交多维标签（user/agent/app/project/session） | `memory_orthogonal_tags_enabled` |
| P1 | `brain/memory/surprise.py` | surprise 加权遗忘（越意外越记得牢） | `memory_surprise_weight_enabled` |
| P1 | `brain/memory/gap.py` | gap analysis（主动提示"我还不知道什么"） | `memory_gap_analysis_enabled` |
| P1 | `brain/memory/wiki.py` | 知识 wiki 自动梳理（可编辑 Markdown 百科） | `memory_wiki_enabled` |
| P2 | `brain/dream.py` | 后台"做梦"引擎（合并记忆/消解矛盾/更新画像/快照/wiki） | `dream_enabled` `dream_consolidate_enabled` `dream_interval_hours` |
| P2 | `brain/scheduler.py` | 自然语言定时自动化（"每天23点…""每周日…"） | `cron_enabled` |
| P2 | `brain/autofetch.py` | 个人数据自动拉取（本地 inbox 摄入 + 可插拔连接器） | `autofetch_enabled` `autofetch_interval_min` |
| P2 | `brain/background.py` | 后台服务聚合入口（做梦/自动拉取/定时统一启动，daemon 线程） | 受 dream/autofetch/cron 开关 |
| P3 | `brain/needs.py` | 需求体系/精力池/孤独感，驱动主动意愿 | `emotion_needs_enabled` |
| P3 | `brain/planner.py` | 概率主动决策（P(success) + 冷却 + 随机决策） | `decision_planner_enabled` |
| P3 | `brain/segmenter.py` | 莲心式分段发送（一条回复按句号分成多条短消息，随机1~3s） | `split_reply_enabled` |
| P4 | `brain/mcp_client.py` | MCP 客户端（接入外部工具，优雅降级） | `mcp_enabled` |
| P4 | `brain/model_routing.py` | 按能力路由模型（chat/vision/image/asr/tts/embedding） | `per_model_routing_enabled` |
| P5 | `brain/compressor.py` | TokenJuice 式工具输出压缩 | `tool_compress_enabled` |
| P5 | `brain/verify.py` | 确定性校验（AST/JSON/node，写文件前） | `verify_enabled` |
| P5 | `brain/netsentinel.py` | 离线自动切换（本地模型 fallback + 待重放队列） | `netsentinel_enabled` |
| P5 | （config） | 隐私模式开关（所有推理不出机） | `privacy_mode_enabled`（默认关） |

## 二、开关位置

所有开关在 `memory_data/user_config.json`，默认值见 `config.py` 的 `UPGRADE_FLAGS_DEFAULTS`。
读取入口：`from brain import features; features.is_enabled("mcp_enabled")`。
持久化：`features.set_flags({"mcp_enabled": False})`（会写回 user_config.json）。

## 三、已接入主链路的部分

- `brain/agent.py::_build_dynamic_suffix`：注入 **需求体系**（`emotion_needs_enabled`）与 **gap analysis**（`memory_gap_analysis_enabled`）到 system prompt。
- `brain/agent.py::_run_tool`：每次工具调用写入 **costlog** 执行记录。
- `brain/agent.py::tool_definitions`：**并入 MCP 工具**（`mcp_enabled`，带缓存/上限，受限模式不暴露）。
- `brain/agent.py`（工具消息写入处）：**工具输出压缩**（`tool_compress_enabled`，TokenJuice 式）。
- `main.py`：启动后台 **做梦/自动拉取/定时**（`brain/background.start_background_services()`，各自受开关控制）。
- `main_window.py::_build_proactive_prompt`：**主动"脑子"**——把需求状态/主动意愿/planner 建议注入主动判断上下文（`emotion_needs_enabled` + `decision_planner_enabled`）。
- `main_window.py::_on_response_finished`：**分段发送**——回复完成后按句号拆成多条短消息，随机 1~3s 逐条作为气泡发出（`split_reply_enabled`；历史仍存完整版）。
- `brain/agent.py`：互动时更新需求/精力/孤独（`emotion_needs_enabled`）。

## 四、备用挂点（你或我可按需再接）

以下能力已封装成独立函数，你可在调用侧接上（不影响已有逻辑）：

1. **写入前的确定性校验**：在 `write_file`/`edit_file` 工具逻辑里，写入前
   ```python
   from brain import verify
   ok, reason = verify.verify_text(content, filename)
   if not ok: return {"status": "failure", "content": reason}
   ```
2. **按能力路由模型**：用 `model_routing.resolve("vision")` 替换现有 `cfg.VISION_*` 使用点。
3. **记忆写入后的标签/加权/snapshot 钩子**：Scribe 保存记忆后调用
   ```python
   from brain.memory import tags, surprise, markdown_store
   tags.tag_fragment_multi(fragment_id, {"session": [session_id]})
   surprise.boost(fragment_id)
   markdown_store.full_snapshot_and_commit()   # 或由 dream 后台做
   ```
4. **隐私模式消费点**：读 `features.is_enabled("privacy_mode_enabled")`，为真时把推理钉到本地模型。

> 说明：`main_window.py`（GUI 定时器）和 `tools.py`（64 个工具）我没直接改——它们是大而敏感的主链路，我没法在这里跑 GUI 验证。上面的挂点都封装成独立函数，接上即可，不影响已有逻辑。

## 五、测试

```
# 用项目 venv 运行（PYTHONPATH 需指向项目根）
$env:PYTHONPATH = "RikkaAI"
python tests/test_upgrade_phase0.py     # config 开关 + features + costlog
python tests/test_upgrade_phase1.py     # 记忆层（tags/surprise/gap/wiki/markdown）
python tests/test_upgrade_phase35.py    # needs + compressor + verify + netsentinel
python tests/test_upgrade_phase24.py    # dream + scheduler + autofetch + mcp + routing
python tests/test_upgrade_wiring.py     # background 聚合 + mcp 缓存 + agent 接线
python tests/test_decision.py           # 既有回归（覆盖 agent 聊天路径）
```

全部通过（导入 OK，Phase0/1/35/24/wiring + test_decision 均 OK）。

## 六、默认状态

- 除 `privacy_mode_enabled=False` 外，其余升级开关默认开启。
- 想让某个能力先关掉，在 user_config.json 里把它置 false，或 `features.set_flags({...})`。
