# 设计：全链条闭环 · 阶段三（推送引擎入库 + 单一写入方收口 + 铺开）

## 一、总览

```
四表入库 ─┬→ 试算表未审数（映射聚合，决策 4 不变）──→ TRIAL_BALANCE_UPDATED
          │                                              │
大厅「复核通过 / 撤回复核」（决策 1，唯一确认点）           ├→ 报表审定数（既有，R3）+ 清过期标记（需求 7.1）
   └→ ADJUSTMENT_APPROVED / ADJUSTMENT_REVIEW_REVOKED     ├→ formula_push.engine.run（P0）
        └→ 试算表 AJE/RJE 重算 → 审定数 = 未审+RJE+AJE+底稿调整（决策 2）
                                                          │   ├→ E1：明细 / 审定表 / 披露表 → 附注主表（决策 3 后端交接）
审定表「发布到试算表」（发布门）                            │   └→ K1：期初 / 未审数 / FS 三项 / 审定合计（P1）
   └→ 写底稿调整分量（同一 UPDATE 现算），不再整列覆盖        └→ 附注过期标记（既有）
底稿调整页 ──自动同步（原地更新，无变化不写）──→ 调整分录大厅
```

推送统一落点仍是 `formula_push`（阶段二 ADR）：规则登记在公式管理、引擎读规则写目标、面板可见可控。

## 二、P0：入库与接入注册表

### 2.1 入库（需求 1）

- 清单以阶段二 tasks.md 为准，入库前现算：`git status` 未跟踪项按文件暂存；共享文件按块暂存
  （取 HEAD 版 → 只应用本链的修改块 → `git add` → 按字节还原工作树），不夹带并行工作的修改。
- 判据：在 HEAD 干净检出上叠加暂存内容（`git worktree add` + `git checkout-index` 暂存区导出）跑推送全套测试。
- 提交用 `git commit` 前核对 `HEAD` 未移动；移动则重新核对暂存与新 HEAD 的冲突后再提交。

### 2.2 注册表（需求 2）

`formula_push/bindings/__init__.py` 改为唯一登记表：

```python
_REGISTRY: dict[str, str] = {"E1": "app.services.formula_push.bindings.e1:E1Binding", ...}
def get_binding(code) / supported_wp_codes() / watched_prefixes() -> {code: binding.account_prefixes}
def register_binding(code, factory)   # 仅测试用，返回撤销函数
```

- 每个 binding 声明 `wp_code` / `account_prefixes` / `derivations`；`triggers._watched_prefixes` 改调 `watched_prefixes()`。
- `GET /formula-push/rules` 响应增加 `supported_wp_codes`；新增只读 `GET /formula-push/bindings`（无项目上下文的接入清单，
  公式管理弹窗打开时取一次）。前端 `PUSH_WP_CODES` 删除，改为响应式 `pushWpCodes`（取数失败 = 空清单 = 不显示页签，fail-closed）。
- 判据：测试注册一个假 binding（`Z9`）后，规则校验接受 `Z9.*` 规则、`TRIAL_BALANCE_UPDATED` 带 `Z9` 前缀科目触发、
  `/bindings` 返回 `Z9`；撤销后三者都不再出现。

### 2.3 入库提交流程（多会话并发下）

1. 现算清单：未跟踪文件逐个确认归属本链；共享文件逐块（hunk）判定归属，只取本链的块。
2. 用**临时索引**（`GIT_INDEX_FILE=%TEMP%\p3.index`，`read-tree HEAD` 起步）组装提交内容，不碰共享索引里他人已暂存的内容。
3. 临时 worktree 检出 HEAD，按临时索引的 blob 覆盖对应路径，跑推送全套测试（入库判据）。
4. `GIT_INDEX_FILE=... git commit`（钩子照常运行；HEAD 被并发移动时 git 的 ref 事务会失败，重做第 1 步）。
5. 提交后对本链路径执行 `git reset -q -- <paths>`，让共享索引与新 HEAD 一致 —— 否则共享索引里这些路径仍是旧 blob，
   他人下一次 `git commit` 会把本次提交悄悄回退。执行前先查 `git diff --cached --name-only`，这些路径上若有他人暂存则先告知。

## 三、决策 1：单一确认点 = 大厅复核通过（需求 3）

### 3.1 状态机

| 当前 | 允许转到 | 说明 |
|---|---|---|
| draft | pending_review / approved / rejected | 新增 draft→approved / rejected（大厅没有提交复核入口） |
| pending_review | approved / rejected | 不变 |
| rejected | draft | 不变 |
| approved | draft | 新增「撤回复核」：清复核人 / 复核时间 |

### 3.2 端点与事件

- `POST /adjustments/{group}/review`：只处理 approved / rejected（及既有 rejected→draft）；
  `POST /adjustments/{group}/revoke-review`：approved→draft。两者权限 = `require_project_permission("adjustment:review")`。
- 撤回提交后发布 `ADJUSTMENT_REVIEW_REVOKED`（`adjustment.review_revoked`，进 `YEAR_SCOPED_EVENT_TYPES`）。订阅：
  重算 handler（`handle_adjustment_approved`，下游 `TRIAL_BALANCE_UPDATED.extra.trigger=adjustment_review_revoked`）、
  底稿过期、报表过期、附注过期、调整 SSE —— 与 `ADJUSTMENT_APPROVED` 逐一对齐（守卫：两事件订阅集合相等）。
- 复核 / 撤回后 `broadcast_raw("adjustment:review-changed", {project_id, year, entry_group_id, new_status})`
  （修正现状的错误 import 与三个位置参数）；前端用 `subscribeProjectEvent` 订阅（原 mitt 监听收不到 SSE）。

### 3.3 权限（ADR-P3-007）

`permission_matrix_service` 的 7 个操作码不含 `adjustment:review`，`require_operation("adjustment:review")` 会拒绝所有人。
改为抽出 `project_permissions.resolve_project_permissions(db, user, project_id) -> set[str]`（`/my-permissions` 改调它），
新依赖 `require_project_permission(perm)`：先 `assert_project_permission(..., "review")`（成员、未归档、级别≥review），
再要求 `perm ∈ 合并权限`；admin 放行。前端大厅按钮用 `useProjectRole().projectCan('adjustment:review')`（同一端点）。

### 3.4 底稿 → 大厅镜像（ADR-P3-008）

- 后端 `sync_from_workpaper`：已有分录组时先比内容签名（类型、摘要、逐行 科目 / 名称 / 报表行 / 借 / 贷）——
  相同 ⇒ 不写库原样返回；不同 ⇒ 原地更新（同一 `entry_group_id` 与编号，软删旧行写新行，与 `update_entry` 同法），
  pending_review / rejected 回到 draft 并清复核信息；approved 仍 `APPROVED_LOCKED`。
- `_next_adjustment_no` 的咨询锁键改用稳定摘要（现为进程随机 `hash()`，跨进程互斥失效，与发布令牌同病）。
- 前端 `useAdjustmentCentralSync`：按 `itemId` 记录分录组签名，签名变化即防抖 5 秒静默同步（默认开启，消费方不改）；
  无有效行 / 借贷不平衡不同步；403 静默；同一错误同一签名只提示一次；协作补充过的分录组不自动覆盖（提示手动同步）；
  卸载时有待发同步则立即发出。

## 四、决策 2：试算表审定数单一写入方（需求 4，ADR-P3-002）

- 新列（V176）：`wp_adjustment NUMERIC(20,2) NOT NULL DEFAULT 0`、`wp_publish_base NUMERIC(20,2)`、`wp_published_at TIMESTAMPTZ`；
  回填 `wp_adjustment = audited − (未审+RJE+AJE)`（仅不等的行），R176 删列。
- 统一口径 `audited = COALESCE(未审,0) + RJE + AJE + 底稿调整`：`recalc_audited` / `recalc_unadjusted` 同改。
- 唯一写入函数 `tb_audited_writer.publish_rows(session, project_id, year, rows, *, source)`：每科目先查未删行，
  0 行跳过、多公司编码跳过并报告、1 行按 id 执行同一条 UPDATE（`wp_adjustment = :audited − (COALESCE(未审,0)+RJE+AJE)`，
  `audited_amount = :audited`，`wp_publish_base = 未审`，`wp_published_at = now()`）。发布门 handler、S 估计 / S 交易、M9 / N2 回写端点、
  高级查询 TB 单元格回写改调它；M9 / N2 端点补项目级编辑权（现只校验登录）并改按项目审计年度定位（现取最大年度）。
- 分量是**增量语义**：重新导入后保留，审定数 = 新未审 + 调整 + 底稿调整；`未审 ≠ wp_publish_base` 时试算表页标「发布后未审数已变化」。
- 无调用方的直写（N1~N4 `writeback_tb`、`AdjudicationMutationAdapter`、`AdjudicationWritebackService`）冻结为基线：
  AST 扫描「对 `audited_amount` 赋值 / `SET audited_amount`」的站点，基线只许减少；新增直写即红。
- 发布令牌（ADR-P3-005）：`sha256(规范化行内容 + 目标行当前审定数)` 前 24 位。同一确认重复提交去重；内容相同但中间被改过的再次发布不会被误判为重复。
- 发布事件带 `account_codes`（实际更新的科目），下游报表按科目增量重算而不是全量。
- 读口径同改（逐处测试）：`check_consistency`、`summary_with_adjustments`、`data_validation_engine`、`wp_cross_check_service`、
  `module_cell_resolver`、`linkage_service`、`adjustment_service`、`trial_balance_full_view_service`、`tb_snapshot_service`（快照与恢复带分量）。
- 前端试算表页：AJE 后加「底稿调整」列与「发布后未审数已变化」标记；小计 / 合计、复制导出表头、单元格选择的硬编码列号同步顺移。

## 五、决策 3：附注主表交接给后端（需求 5，ADR-P3-003）

- `note_writer.build_main_skeleton(template_type, table)`：读 `note_template_{listed,soe}.json` 对应章节该表的行标签，
  产出 `rows=[{label, end_amount: None, prior_amount: None, is_total?}]` 与 `columns`（与前端 `buildE1{Listed,Soe}Columns()` 逐字一致）。
- `engine._push_note`：章节存在、未确认、`sub_table_data` 缺该表时 —— 若 `_source ∉ {workpaper, workpaper_html}` 且原表格
  （`rows` / `_tables`）有非空非零数值或人工 / 锁定单元格 ⇒ 跳过并报告；否则浅合并骨架（保留其余子表、叙述、原 `rows`），
  置 `_source=workpaper`、缺省 `_current_standard`，然后照常逐单元格写值。
- `sync_from_workpaper` 查章节加 `with_for_update()`：前端同步与引擎写同一行时串行，消除丢失更新（只加这一处）。
- 前端 `buildE1SyncPayload(..., { mainTable: false })`：E1 页同步只推受限表与叙述；构造函数缺省仍产出主表（契约测试与覆盖率扫描不变）。
- 夹具 `backend/tests/fixtures/e1_note_skeleton.json`：前端由真 builder 产出、后端骨架逐字比对（行标签、合计标记、列定义）。

## 六、P1：K1 其他应收款（需求 6）

- `bindings/k1.py` + `k1_calc.py`：取数直接调 `_k1_other_receivables` 的内层纯构造函数（不经 `render()` —— 它有「已持久化就不预填」
  的门且取数 fail-open），三处取数加 `strict`；推送目标为性质 n0~n4 与组合 r0~r3 的期初 / 未审数、FS 三项，
  派生审定合计 `K1-1-audited-{receivable,baddebt,net}`；舍入对齐 `Math.round(n*100)/100`。账龄行用随机行 id，不推送（报告列出）。
- 规则进 `formula_push_rules.json`（`K1.*`），注册表登记 `K1`；前端保存过滤后端独占键 + 「后台已更新」提示条（复用 E1 的纯函数形态）。
- 双侧夹具：前端真 composable 产出、后端同夹具校验。

## 七、链上缺陷（需求 7，ADR-P3-009）

- 报表过期标记：`generate_all_reports` 写行时清 `is_stale`；`regenerate_affected` 清本次重算的行；调整事件的标记按受影响行
  （与增量重算同一判定函数）而非整表，事件无科目时才整表标。
- 事件调用点守卫在 HEAD 上 7 红：`adjustments.py` / `review_workflow_service.py` / `independence_signing_service.py` 的错误 import、
  `dispatch_records.py` 未 await 的 publish、`s_transaction_calculation.py` await 了同步的 `broadcast_raw` 且参数错位 —— 逐处修正。

## 八、ADR

- **ADR-P3-001 单一确认点**：大厅复核通过是唯一确认点；撤回复核回到草稿（否决回到待复核：底稿重同步会覆盖、大厅状态矛盾；
  否决新增枚举值：需 `ALTER TYPE`）；新事件而非复用 `ADJUSTMENT_UPDATED`（后者漏标附注过期、历史标签错）。
- **ADR-P3-002 审定数分量化**：发布门写分量、重算保留分量（否决端点内现算：与审批重算抢数据；否决反转 V124 以大厅为唯一真源：
  推翻 ADR-ADJ-002 与发布门流程）。分量取增量语义（否决「发布值为绝对值、重导入不变」：未审数更正后审定数不跟随是错数）。
- **ADR-P3-003 附注按章节交接**：骨架模仿 `sync_from_workpaper` 浅合并（否决模仿迁移脚本：会删 rows/_tables、产出 F3 形态）；
  只建主表（受限表是动态行，仍由前端推）；触发条件是「缺该表」不是 `_source≠workpaper`；否决后端重建 69 个 builder / 无头执行前端 JS。
- **ADR-P3-004 未审数保持映射聚合**：否决公式驱动（会重新引入父子双计、漏映射、无符号存储三类已修事故）。
- **ADR-P3-005 发布令牌**：见 §四。否决进程随机 `hash()`（重启 / 多 worker 失效）；否决纯内容摘要（A→B→A 第二次发布 A 被误判重复）。
- **ADR-P3-006 接入清单单一真源**：见 §2.2。
- **ADR-P3-007 复核权限与 `/my-permissions` 同源**：见 §3.3。
- **ADR-P3-008 底稿→大厅镜像**：见 §3.4。否决逐个改 81 个消费方。
- **ADR-P3-009 过期标记按行标、按行清**：见 §七。

## 九、测试与变异（每项修复前红 / 修复后绿 / 改回即红）

| 判据 | 测试 | 关键变异 |
|---|---|---|
| 干净检出自洽 | 临时 worktree 跑推送全套 | — |
| 注册表 | 假 binding 注册 / 撤销 | 触发器写死 E1、前端写死清单 |
| 状态机 / 撤回 | service + 端点真请求（助理 / 质控 / 只读 / 非成员 403） | 撤回不清复核人、不发事件、权限降级 |
| 两事件订阅对齐 | AST 扫描 subscribe | 漏订阅一个 |
| 镜像 | service（相同不写 / 不同原地更新保号）+ vitest（签名、静默、去重） | 恢复软删重建、去掉无变化判断 |
| 分量 | SQLite + 真 PG：发布后审批 / 重导入审定数保留 | recalc 去掉分量、发布不写分量 |
| 直写基线 | AST 扫描 | 新增一处直写 |
| 附注交接 | 引擎 + 夹具对拍 + 行锁 | 骨架行标签改一字、跳过隐藏数据检查 |
| K1 | binding + 双侧夹具 + strict | 舍入、取数退回 fail-open |
| 过期标记 | 报表引擎清标记 | 不清 / 整表标 |
| 事件守卫 | `test_event_call_site_guards.py` 转绿 | — |
