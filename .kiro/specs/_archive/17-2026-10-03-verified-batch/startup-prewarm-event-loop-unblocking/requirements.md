# 启动预热不阻塞事件循环 — 需求

> 2026-09-29 新建。来源：知识库收口「逐一修复」第 3 项（~8s 延迟）。只处理**事件循环被同步 CPU 占住**与
> **客户端经 localhost 连 IPv4-only 后端**两类；workbook 物化 / 锁粒度等归 `oo-html-writeback-performance`。

## 背景（全部为现场实测）

| # | 事实 | 后果 |
|---|------|------|
| F1 | 后端 reload 后 `/api/health`：就绪后首个请求 **16.23s**，随后 45s 内还有 3.23s / 2.89s / 1.17s 尖峰 | 用户看到的「开页卡住数秒」 |
| F2 | 进程内复现第一段预热（`prewarm_sync_registration_cache`）：墙钟 20.5s，其中 **13.9s 是 Python 在事件循环线程上跑**，心跳最大滞后 **8.30s** | 预热虽是后台任务，却独占事件循环 |
| F3 | 按「协程 → 同步函数」边界归因：`attach_adapters → observe_descriptor_facts`（→ `frontend_reference_index`）**7.49s**（最长连续 7.88s）；`observe → _observe_workbook`（openpyxl 整簿解析）**3.58s**（最长连续 0.54s）；`observe_room_facts → room_service_wiring` 0.65s | 两个边界占阻塞的 85% |
| F4 | `frontend_reference_index` 首算：5199 个文件、19397 条 import，只有 7397 个不同的「拼接后路径」；原实现 6.8s，逐条 `Path.resolve()` + `is_file()` | 同一目标被重复解析 2.6 倍 |
| F5 | 第二段（基线 projection）已走 `to_thread`：最大滞后 0.24s | 不需改 |
| F6 | 后端只监听 IPv4（`0.0.0.0`）。Windows 上 `localhost` 先解析 `::1`：建连 **2043 / 2024 / 2024ms**，`127.0.0.1` 为 0–14ms；Docker 发布的依赖（PG/Redis/vLLM/OO）双栈无此问题 | 每条新连接 +2s |
| F7 | AI Agent 的 MCP 子进程 `AUDIT_API_BASE` 默认 `http://localhost:9980`，且**每次工具调用新建 httpx.Client** | 每次工具调用 +2s |
| F8 | 前端 `.env.example` 仍是 `http://localhost:9980`（实际 `.env` 与 `start-dev.bat` 已是 127.0.0.1） | 按模板新建环境即回退 |

## Requirement 1：冷注册不在事件循环上做源码事实首算

1.1 `_attach_pilot_adapters` 的冷路径（锁内、重查缓存之后、各 attach 之前）SHALL 在工作线程里把进程级源码事实缓存建好（`frontend_reference_index` / `room_service_wiring` / `doc_key_providers` / `_legacy_baseline` / 注释剥离自检）。
1.2 预热失败 SHALL NOT 在此抛出：原调用点照旧计算并以原错误、原位置 fail closed（判据与报文不变）。
1.3 缓存命中路径（绝大多数请求）不受影响：不进锁、不跳线程。

## Requirement 2：整簿观测不在事件循环上解析

2.1 `PublishedIdentityObserver.observe` SHALL 经 `asyncio.to_thread` 调用 `_observe_workbook`；观测顺序、异常类型与报文不变。
2.2 `_observe_workbook` 自身保持同步方法（离线用例直接调用它）。

## Requirement 3：入边索引首算提速且结果逐字节不变

3.1 同一「解析种类 + 拼接后路径」只解析一次；键 SHALL 含 importer 目录（`./X.vue` 在不同目录指向不同文件）。
3.2 产物（`scanned_files` / `imports` / `tags`）与原算法逐字段相等（真实前端树实测 + 合成树用例）。

## Requirement 4：连 IPv4-only 后端的客户端默认 127.0.0.1

4.1 `audit-platform/frontend/.env.example`、`dsh_engine` 的 MCP `AUDIT_API_BASE` 默认值、`tools/audit-data-mcp/server.py` 的默认值 SHALL 为 `127.0.0.1`。
4.2 守卫：上述三处不得回退到 `localhost:9980`。

## Requirement 5：验证

5.1 行为用例：源码事实预热与整簿观测确实跑在非事件循环线程。
5.2 真栈对照：同一 reload 探针改前 / 改后各跑一次，报告就绪后最大延迟与尖峰次数。
5.3 变异：回退任一修复必须打红，还原后 sha256 一致；既有 `mutate_sync_registration_prewarm_guards.py` 全部仍 KILLED。
