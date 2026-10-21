# 设计文档：公式管理运行时完整性闭环

> 关联：#[[file:.kiro/specs/formula-manager-runtime-integrity-closure/requirements.md]]
> 当前基线：实施前以当前 HEAD 重做符号核验；路径锚点使用符号名，不写死行号。

## 1. 已证实的断点

- `/api/formula/batch-execute` 无项目鉴权且忽略后续项 project/year。
- `report_config.execute_formula` 与 `/seed` 有权限旁路；list/types 可由 `applicable_standard=project:*` 绕过。
- 函数支持矩阵只有前端生产消费；report PREV/AUX/ADJ 仍可静默 0，wp batch 保存绕过单条校验。
- WpFormula CAS 为 `SELECT → Python 比较 → flush`，expected_version 可省略，不是原子 CAS。
- draft-refresh 生产链把 FormulaMutation 转成 RefreshUnit，只写 marker，不调用 adapter.apply_many。
- standalone 真库诊断已证实：目标值未写、last_computed_at 未更新、outbox/audit 未贯穿。
- `openFormulaManagerFromLocation` 制造全允许 capability；真实 shell snapshot 未传入；dirty-pin/save gate 未进生产。
- 当前“全量门禁”主要验证纯函数、源码与测试文件存在，不是真浏览器逐页门禁，且未接 CI。

## 2. ADR

### ADR-FMRI-01：`execute_refresh` 成为运行唯一 owner

生产 orchestrator 一次生成完整 mutation plan，直接交 `DraftRefreshService.execute_refresh`。audit、snapshot、apply、last_computed_at、DraftMarker、preset marker 与 outbox 由该事务唯一负责；`confirm_overwrite` 进入 fingerprint，未确认时按 canonical unit_scope 跳过人工编辑。旧 marker-only `refresh` 仅保留无 runtime mutation 的兼容调用，生产不得双跑两套审计。

### ADR-FMRI-02：鉴权从请求身份反解

路径对象先查询所属项目；body/query/applicable_standard 中的项目必须彼此一致。全局模板种子与全局自定义函数仅 admin。批量请求禁止混合项目/年度。

### ADR-FMRI-03：能力矩阵是执行前置条件

后端提供 `validate_expression_support(expression, executor, context)`；结果为 supported/unsupported/context_required。前端只负责展示，服务端负责拒绝。report_path 在真实注入前明确不支持 PREV/AUX/ADJ。

### ADR-FMRI-04：CAS 使用数据库条件写

已有行更新采用 `UPDATE ... WHERE definition_version=:expected RETURNING`；expected_version 缺失返回 428，未返回行返回 409。新增继续受唯一索引保护。SQLite 只做契约测试，PG 双事务测试证明原子性。

### ADR-FMRI-05：真实 capability 与 scope context 分流

工作底稿打开必须使用服务端 capability snapshot 与 canonical location；缺失/过期/epoch 不一致 fail-closed。合并/report/note/tb 使用显式 scope context，不伪造 wpId。保存仍以实际 mutation endpoint 的权限与 CAS 为最终安全边界。

### ADR-FMRI-06：两层门禁

快速 CI 层验证纯契约、端点鉴权、矩阵、CAS 与生产调用；Playwright 层按 distinct componentType×host×scope 选代表项，真实点击并检查弹窗、请求、权限、console/network。真实门禁不得以 skip/测试文件存在冒充通过。

## 3. 关键实现边界

- `report_config` 全局模板表范式不改；只加 admin/project 权限和执行前置校验。
- 不重写 consolidation 值链；scope context 只收敛入口契约。
- 不新增 WpFormula.last_run_id 列：通过 `WpFormula.id → DraftRefreshSnapshot.source_formula_id → refresh_id` 关联 run。
- workpaper target 仅在载体可被显式证明时构造：当前生产 canary 为 A1 `WorkingPaper.parsed_data` 的 `sheet_name + cell_ref`；结构化 checklist 必须由 binding 给出真实 `item_id + storage_field`。缺 binding 即 scope failure，禁止从 sheet_name/category 猜写。
- all_or_nothing 的业务写、snapshot、last_computed_at、outbox 位于同一 savepoint；失败审计可在外层记录。
- report/note/cross-check 的可降级副作用若 fail-open，必须各自使用 `begin_nested()` 隔离事务失败。

## 4. 改动面

后端核心：`routers/formula.py`、`routers/report_config.py`、`routers/wp_formula.py`、`services/wp_formula_service.py`、`services/formula_management/function_support_matrix.py`、`services/formula_management/draft_refresh_orchestrator.py`、`services/formula_runtime/coordinator.py`、`services/draft_refresh_service.py`、workpaper adapter。

前端核心：`openFormulaManagerFromLocation.ts`、`WorkpaperEditor.vue`、EventBus envelope、`FormulaManagerDialog.vue` 及对应 Vitest；合并入口只经 scope facade 收敛，不伪造工作底稿 location。

治理：现有 CI/Vitest job 复用快速层；新增 blocking runtime Playwright job 前必须 provision PG/Redis/backend/frontend 和确定性 seed。RTK checker 接 governance job。warnings 基座修复若超本轮影响面，保持未完成并另立任务，禁止 `-W ignore`。

## 5. 验收矩阵

| 层级 | 必须证明 |
|---|---|
| 单元 | 函数 preflight、context_required、scope context、capability deny/expiry、CAS payload |
| TestClient | 每条旁路 403/422、零副作用、全局 seed 非 admin 403 |
| PG | 双事务 CAS 仅一成功；production draft-refresh 真写目标并全链同 run_id；失败全回滚 |
| Vitest | 真实 snapshot 传入、迟到响应不覆盖、403/409 草稿保留 |
| Playwright | fresh-DB seed 后真实验证 A1 + 普通底稿 capability/当前实例请求，以及合并工作底稿/报表/附注三 scope；deny 时入口禁用且零公式请求 |
| 文档 | delta 与 evidence 可复现，旧 spec 不假绿 |

## 6. 风险与回滚

- capability 收紧可能暴露旧页面缺 snapshot：先补真实传递，再删除 synthetic allow；测试必须覆盖 deny 初态。
- 强制 expected_version 会影响旧客户端：同一次改动更新所有生产调用方；428 文案明确要求刷新。
- execute_refresh 接线涉及真实写库：先用单一已知 anchor canary 和事务失败注入，确认回滚后再扩大 scope。
- 任何无法完成的真实环境验收保持 `[ ]`，不得把“代码已改”写成“已闭环”。

## 7. 实施后复核结论（2026-10-18）

### 7.1 会话与保存目标

`ThreeColumnLayout` 是唯一 dialog owner。`FormulaEditDialog` 的表达式、分类、说明、目标变化产生 dirty 信号；dirty 后收到新工作底稿或项目级 scope 事件时，owner 只更新 latest/banner 并暂存 pending payload，活动 project/wp/year/scope/capability 保持原值。保存请求从 `decideSaveDraft().location` 取 wpId/year/sheet，成功或显式丢弃后才切 pending。`WorkpaperEditor` 原有第二套直写 FormulaEditDialog 已删除。

### 7.2 覆盖与回滚

`execute_refresh` 以项目+年度串行化，fingerprint 含覆盖策略。runtime snapshot 的 `source_scope._runtime_before` 保存公式生命周期和 marker 前态；preset 无业务 binding 时只生成 DraftMarker，并在响应 warning 中明确不计 applied。公开 rollback 保持 `(before_value=旧值, after_value=本次值)` 方向，adapter 用 after_version CAS；业务恢复、marker、公式状态和 rollback outbox 处于同一 savepoint，冲突时 router 外层 rollback 后 HTTP 409。

### 7.3 Outbox 与门禁

公式 outbox 复用既有 `outbox_replay_worker`，即使导入 outbox 开关关闭也继续轮询；行选择使用 `FOR UPDATE SKIP LOCKED`，独立 session 提交 delivered/attempts。CI fresh DB 显式运行 consolidation seed 与 formula-manager 专用 seed，后者幂等建立 admin、standalone A1/D2-1 有效 XLSX；浏览器测试不再跨历史项目猜目标。

### 7.4 诚实未闭合项

功能 AC 已有 163 条后端目标测试、5 条 PG、527 条前端目标测试和 3 条 Playwright 证据。唯一保留 `[ ]*` 是 `FormulaManagerDialog.vue` 单文件 vue-tsc：4GB 堆仍 OOM（此前 8GB 区域检查同样 OOM）；纯契约 vue-tsc、IDE diagnostics 与 ESLint 已通过，但不能替代完整 Vue 语义检查。因此 spec 保持 active，不归档。
