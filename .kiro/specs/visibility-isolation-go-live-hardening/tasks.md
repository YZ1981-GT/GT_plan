# Implementation Plan

## Overview

本计划把 Parent_Spec（`procedure-delegation-visibility-isolation`）的 6 个上线 GAP 转为 LIVE/ACCEPTED，并以独立 Closeout Evidence + Go_Live_Gate 门禁。全部为必做任务，无 optional。任务先建证据基线，再启用/挂载运行时、审计入口，随后真实容量与浏览器验收，最后提交与终局门。

不重建可见性系统；如发现机制缺陷回 Parent_Spec 修复。真实 SQL/事务/gate 语义一律 PostgreSQL `audit_platform` + 真实 FastAPI app；环境依赖项（6000 并发、Playwright）达不到字面目标时以诚实外推 / API-gate 回退并如实记 GAP，不冒充通过。迁移 head 保持 V113，本 spec 不新增迁移。

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 1, "tasks": ["1"]},
    {"wave": 2, "tasks": ["2", "3", "4"]},
    {"wave": 3, "tasks": ["5"]},
    {"wave": 4, "tasks": ["6"]},
    {"wave": 5, "tasks": ["7"]},
    {"wave": 6, "tasks": ["8"]}
  ]
}
```

依赖：Task 1 建证据基线；Task 2/3/4 启用令牌强制 / 挂载 dispatcher / 审计 native_authz（互相独立）；Task 5 真实容量 + 冻结限流（需运行时稳定）；Task 6 Playwright 角色验收（需 Task 2/3 已 LIVE + dev 服务）；Task 7 PR 提交 + 依赖交互（需 2–6 落地）；Task 8 Go_Live_Gate 仅在全部证据通过后关闭。

## Tasks

- [x] 1. 建立 Closeout Evidence 基线与 Go_Live_Gate 骨架
  - 复用 `app.security.evidence_manifest` 与 `manifest.schema.json`，在 `.kiro/specs/visibility-isolation-go-live-hardening/evidence/` 建独立 append-only manifest + schema；实现/接入 append writer 与 precheck。
  - 记录 6 个 Go_Live_Item 的基线状态为 `built-not-live`（引用 Parent_Spec 证据佐证"已构建"），明确区分"已构建" vs "LIVE/ACCEPTED"。
  - 搭 `H7 GoLiveGate` 骨架：复用 `completion_guard` 的 latest-run-per-task + SHA-256/size 重算 + 路径安全；先能对本 spec manifest 跑出"未 LIVE"结论（此时应阻断）。
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 2. 启用编辑器令牌强制（R1）并验证 LIVE 与回退
  - 将 `settings.ONLYOFFICE_JWT_ENFORCE` 改为环境求值：prod/staging 或显式 env=`true` → `True`，dev（JWT disabled）保持 `False`；不硬翻转默认值以免破坏本地编辑。提供纯配置 Rollback_Path。
  - 不改 `editor_security` 校验逻辑；仅确保 `enforce=True` 时 `wp_onlyoffice_router.py` / `api/wopi.py` 的门拒绝分支统一 404、secret 缺失 fail-closed、callback/PutFile 落盘前重校验版本/action/撤权。
  - 真实 app 集成测试（enforce 两态）：签名失败/过期/claim 不一致/只读令牌写/secret 缺失/已撤权会话 → 404；有效令牌放行；`enforce=false` dev 可编辑；Rollback 可逆。追加 Closeout Evidence run。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12_

- [x] 3. 挂载 InvalidationDispatcher 到 app.main lifespan（R2）
  - 在 `app/main.py` lifespan（`_start_workers` 范式）新增 `asyncio.create_task(run_invalidation_subscriber(stop_event))` 并确保 publisher 侧提交后 fan-out；可选 `VISIBILITY_INVALIDATION_DISPATCHER_ENABLED`（默认 True）门控。
  - Graceful_Degradation：Redis 启动不可用 → 记 warning、应用照常启动、订阅进入指数退避重连；运行期断连 → 重连并 resubscribe；lifespan 退出优雅停止。不改 `epoch_cache` 语义。
  - 真实 app + PostgreSQL 测试：Fast_Path 撤权 ≤1s 收敛；Redis 不可用时应用仍启动且 DB_Epoch_Safety_Net ≤1s 拒绝、无 stale-allow；重连恢复；关闭优雅停止。追加 Closeout Evidence run。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_

- [x] 4. 审计 72 条 native_authz 入口（R3）
  - 实现审计工具（`app/security/native_authz_audit.py` 或扩展 `coverage_guard`）遍历 ledger `native_authz` 条目，按"能否泄漏 scope-internal-not-delegated / unmapped-sheet 正文"分类为 Leak_Risk 或 Justified_Allowlist；无法判定默认按 Leak_Risk（fail-closed）。
  - Leak_Risk 入口接 `enforce_wp_gate`/`dedicated_wp_gate`（强制 scope_cycles/Sheet_Key/委派隔离），ledger 该条更新 gate/matrix/test；其余写入 Justified_Allowlist（entry/route/method/reason/reviewer）。
  - 扩展 `coverage_guard`：断言每条 native_authz 要么 gated 要么 allowlist（无 silent pass），漏项阻断 CI；挂 CI job。真实 app 测试接门入口 allow/deny/cross-project/sheet。追加 Closeout Evidence run。
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11_

- [x] 5. 真实容量验收与冻结生产 Rate_Limit_Profile（R4）
  - 定义版本化 Performance_Profile（工具/ramp/项目分布/动作组合/数据规模），跑真实 6000 并发已认证用户基线；不可字面达成时以 Honest_Extrapolation 达到最大真实并发并记录外推方法与局限。
  - 产出 `CapacityReport`（p95/错误率/拒绝正确率/限流/缓存一致性）；`freeze_rate_limit_profile` 以 `Capacity_Report_Hash` 绑定冻结生产 profile；缺报告/哈希拒绝激活；生产仅从 frozen profile 读阈值。
  - 验收 list p95≤2s / gate p95≤1s / 成功错误率≤1% / 错误允许数=0 / 阈内不误限 / 超阈 429+Retry-After；易变计时以 Deterministic_Summary hash-pin。追加 Closeout Evidence run。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12_

- [x] 6. Playwright 8 角色 fresh-context 验收（R5）
  - 经后台进程起 backend 9980 + frontend 3030（非阻塞），探活后为 Admin/Supervisor/Workpaper_Lead/Row_Assignee/Operation_Reviewer/History_Lead/History_Row/Restricted 各建全新 browser context + fresh navigation。
  - 断言：scope-internal-not-delegated 与 scope-external-delegated 均拒绝；覆盖 list/tab/URL/write/review/attachment/AI/version/OnlyOffice-WOPI；撤权刷新 ≤1s；404 显"资源不存在或不可访问"无名称/正文闪现；console error=0。
  - 某 lane 因环境阻塞（服务起不来）→ 降级为 API/gate + PostgreSQL 级证明并如实记该 criterion GAP，不标 passed 冒充浏览器验收。追加 Closeout Evidence run。
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9_

- [-] 7. PR 提交与依赖 spec 交互验证（R6）
  - 推送新分支（`-u` 远程跟踪），`gh pr create` 走 PR 不直推 main/master；仅 stage 本次交付文件；疑似 secret 文件提交前标记。PR 描述含变更摘要/测试/阻塞项。
  - 跑 `procedure-delegation-notification` 相关套件，以基线快照区分其既有 `service_identities` create_all 失败与本次新增回归；确认两 spec 互不引入新回归。
  - 追加 Closeout Evidence run 记录 PR 标识、分支名与 Interaction_Validation 结果。
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

- [ ] 8. 执行 Go_Live_Gate 并关闭规格（R7）
  - 汇总 Task 1–7 最新 run；`H7 GoLiveGate` 逐一确认 6 个 Go_Live_Item 为 LIVE/ACCEPTED（非"仅已构建"），latest-run-per-task 重算 SHA-256/size、拒绝 `..`/绝对路径/缺 artifact/旧 run/smoke 冒充。
  - 仅在全部门禁通过时将 Task 8 标 `[x]` 并关闭 spec，更新 INDEX/memory（记录启用方式、Rate_Limit_Profile 版本、PR 标识）；任一项仅"已构建"未 LIVE → 阻断并列出失败证据。
  - _Requirements: 7.5, 7.6, 7.7, 7.8, 7.9, 7.10_

## Notes

- 本 feature 只启用/挂载/审计/验收既有机制，不重建可见性系统、不改 `resolve_wp_binding_and_access()`/Action_Matrix/epoch_cache 语义、不新增迁移（head 保持 V113）。
- 环境依赖型验收（6000 并发、Playwright）达不到字面目标时以诚实外推 / API-gate 回退并如实记 GAP，禁止假绿。
- async service 只 flush（router 提交）；PowerShell 不触碰 Vue/Markdown；asyncpg 用 `= ANY(:list)`；真实 PostgreSQL 不以 sqlite/mock 替代。
- Closeout Evidence 独立于 Parent_Spec manifest；易变 artifact 仅 hash-pin 确定性摘要；Go_Live_Gate 为唯一完成判定权威。
- git 走 PR 不直推 main；push 前先 fetch；仅 stage 本次交付文件。
