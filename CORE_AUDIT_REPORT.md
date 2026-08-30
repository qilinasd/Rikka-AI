# RikkaAI 核心体检报告（第一阶段基线）

## 已修复

| 等级 | 问题 | 修复 |
|---|---|---|
| 高 | `TimerManager.cancel_by_type()` 比较了时间字段 `t[0]`，按类型取消无效。 | 改为比较类型字段 `t[2]`，并加入回归测试。 |
| 高 | 新用户没有 `user_config.json` 时，不会从安全存储加载全局、智谱和视觉 Key。 | `load_user_config()` 现在先独立读取安全存储，再读取用户配置。 |
| 中 | 核心测试依赖未声明，项目虚拟环境没有 `pytest`。 | 在 `requirements.txt` 增加 `pytest` 和 `keyring`。 |

## 高风险待处理

1. 线程关闭路径分散在 `main_window.py`，同时使用 `QThread` 和普通 daemon thread；需要在真实关闭窗口测试中确认没有遗留线程、子进程或回调已销毁控件。
2. 多个记忆模块直接连接 `memory_data/rikkai.db`，存在并发写入、锁等待和连接关闭不一致风险。
3. 核心模块仍有大量宽泛 `except Exception` 和空 `pass`，可能把数据写入失败、API 错误和线程异常隐藏掉。
4. 真实 API 调用分散在 agent、archivist、diary、memory summary、knowledge page 和 tools 中，超时、重试和错误结构不统一。
5. `.secret-backup` 是回滚备份，必须保持仓库外/被忽略，不能上传 GitHub；Git 历史仍需单独清理。

## 中风险待处理

1. `requirements.txt` 与实际导入模块需要在干净虚拟环境中逐项验证。
2. README 的新用户安装流程没有覆盖 Windows Credential Manager、环境变量、视觉服务和本地语音服务。
3. 项目包含大量未提交 GUI、资源和 Argo 文件；在完成导入图和运行入口分析前，不能判断为多余代码。
4. 根目录存在临时 JSON、视觉脚本、CSV 和调试文件，需要归类为发布文件、开发工具或仓库外文件。
5. `brain/argo` 应独立运行离线测试，不应与核心应用测试结果混为一谈。

## 第二阶段 Argo 检查项

- 离线测试收集、失败/跳过统计；
- 引擎环境变量和认证头检查；
- 并发、重试、熔断、缓存和 SQLite 锁；
- URL/TLS/robots 安全边界；
- 与主应用的异常、日志和依赖隔离。

### Argo 本次实测记录

- 文件恢复后测试可完整收集：`830 tests collected`。
- 在隔离用户目录、跳过 live 标记并排除 integration 文件后：`752 passed, 21 skipped, 44 failed`。
- 失败不能整体视为业务缺陷，主要分类如下：
  - 缓存/配额仍有默认路径写入用户目录，隔离环境权限不足；
  - Ego/WebBridge 测试缺少登录态运行时；
  - 个别配置读取使用系统默认编码，遇到 UTF-8 文件时触发 `UnicodeDecodeError`；
  - 路由断言依赖引擎可用性和动态状态；
  - TLS spoof 测试依赖特定网络/客户端能力。
- `research.py` 恢复后静态检查未发现 `subprocess`、`os.system`、`eval/exec`、删除文件或 `shell=True`。
- Argo 仍不能标记为通过；下一步应先修复测试隔离路径和 UTF-8 读取，再分别运行无运行时、无网络和 live 测试组。

### 编译检查说明

- `gui/home` 的 8 个 Python 文件 AST 解析全部通过；Windows `py_compile` 写入现有 `__pycache__` 时被权限/占用拒绝，不能把这类文件系统错误误报为语法错误。

### 本轮追加验证（Windows）

- 新增 `brain/argo/scripts/state_paths.py`，支持 `ARGO_STATE_DIR` 显式指定缓存、配额、健康探针、自适应数据库、语言偏好和遥测目录。这样测试/CI 不再依赖修改 `HOME`（Windows 的 `Path.home()` 不跟随该变量）。
- `cache.py` 的 SQLite 文件连接改为显式 `close()`；原实现使用 SQLite 上下文管理器只提交事务、不关闭连接，Windows 下会锁住临时数据库，导致测试清理失败。
- Argo 关键脚本编译检查通过；核心测试 `18 passed`。
- 隔离状态目录下 Argo 全套重新执行：`771 passed, 21 skipped, 38 failed`。失败主要是：
  - Ego/WebBridge 登录态运行时未安装，相关 mock 测试仍在运行时选择阶段退出；
  - `curl_cffi`/TLS 或 URL/DNS 环境不可用；
  - CLI 集成测试依赖外部搜索命令/网络；
  - 部分测试源码自身用 `open()` 默认编码读取 UTF-8 JSON，在中文 Windows locale 下失败；
  - 动态引擎可用性/配额导致个别路由断言不稳定。
- 针对缓存连接修复后的专项结果：`test_unit.py` 为 `63 passed, 1 failed`；唯一失败是 HTTP 重定向测试被当前 URL 安全/DNS 环境拦截，未发现缓存锁残留。

这些失败不能统一判定为核心业务回归；应将登录态、live、网络/TLS 和外部 CLI 测试分组，并在 CI 中显式标记前置条件。

## 当前限制

- 本环境的 `.venv` 尚未安装 `pytest`，完整测试需先安装依赖。
- 本轮没有执行真实 API 调用，避免把用户额度和对话数据写入测试输出。
- 没有删除用户文件、数据库、图片、备份或 Argo 代码。

## 安全软件事件

- Windows 安全中心在执行 Argo 测试收集时将 `brain/argo/scripts/research.py`
  标记为 `HEUR:HackTool/VulnScan.a` 并移除。
- 该文件属于当前未跟踪的工作区内容，无法由 Git 恢复；不要关闭防护或从未知来源下载替换。
- 在从 Windows 安全中心隔离区或可信备份恢复并人工审查前，暂停 Argo 测试和运行。
