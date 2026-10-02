# 需求：全链条闭环 · 阶段三（推送引擎入库 + 单一写入方收口 + 铺开）

## 背景

用户诉求（2026-09-28，原话节选）：四表库项目数据入库后，经公式管理模块自动刷新到试算表未审数、
底稿明细表 / 披露表 / 审定表；项目组确认调整分录后，自动推送到底稿审定表和披露表、报表审定数、
试算表审计调整、调整分录大厅；披露表按国企或上市推送到附注科目数据。**推送都经公式管理模块，
链条一定要完全打通。**

上游：阶段一 `chain-closure-phase1-root-cause-fixes`（已归档 `_archive/06-engineering-governance/`）；
阶段二 `chain-closure-phase2-formula-push-engine`（推送引擎 + E1 canary，17/18，**整体未入库**）。

2026-10-01 用户对四项决策「按倾向」拍板：

1. 单一确认点 = 调整分录大厅复核通过
2. 试算表审定数单一写入方 = 发布门写分量列（不再整列覆盖）
3. 附注按章节交接给后端（E1 主表先行）
4. 试算表未审数保持映射聚合（不改成公式驱动）

## 现状实证（2026-10-01 现读 / 真库现查；计数均为现算值，禁写死进判据）

| 编号 | 事实 | 口径 / 证据 |
|---|---|---|
| S1 | 推送引擎不在仓库里 | `git ls-files backend/app/services/formula_push` = 0；memory 记「已提交」是错记 |
| S2 | E1 写死三处 | `bindings/__init__.py` `if wp_code == "E1"` · `triggers._watched_prefixes` · 前端 `PUSH_WP_CODES=['E1']`（测试还钉了字面量） |
| S3 | 审定数直写方不止重算 | 可达：发布门 handler、S 估计 / S 交易 / M9 / N2 回写端点（前端 0 调用方）、高级查询 TB 回写；0 调用方：N1~N4 `writeback_tb`、`AdjudicationMutationAdapter`（唯一入口 `execute_refresh` 无调用方）、`AdjudicationWritebackService` |
| S4 | 发布值被重算抹掉（阶段一冲突①） | `recalc_audited` / `recalc_unadjusted` 恒写 `未审+RJE+AJE`；发布门只写 `audited_amount` ⇒ 审批或重导入一次即丢底稿发布值 |
| S5 | 发布门 UPDATE 不限 `is_deleted` / `company_code` | `_on_d_audit_determination_saved`；真库 (项目,年度,科目) 跨公司重复 0 组 ⇒ 今天零影响 |
| S6 | 发布令牌按进程随机 | 端点用 `abs(hash(...))`，重启 / 多 worker 同内容不同 token |
| S7 | M9 / N2 回写端点只校验登录 | 依赖 `get_current_user`；按 `wp_id` 反查项目后直接写；取 `year` 最大的一行而非审计年度 |
| S8 | 真库试算表 | 未删 1393 行；审定数 ≠ 未审+RJE+AJE 的 9 行（全是测试项目）；`tb_publish_ack` 8 行 |
| S9 | 大厅到不了「复核通过」 | 状态机 draft 只能 → pending_review，大厅无「提交复核」入口、批量复核只认 pending_review；approved 无出口 |
| S10 | 审计助理能批准调整 | `/review` 用 `require_project_access("review")`，层级 edit(3) > review(2) |
| S11 | 复核 / 同步 SSE 从未发出 | `adjustments.py` 两处 `from app.core.event_bus import`（模块不存在）且 `broadcast_raw` 传 3 个位置参，异常被 `except: pass` 吞；同类守卫 `test_event_call_site_guards.py` 在 HEAD 上 7 红（5 个文件） |
| S12 | 底稿→大厅每同步一次烧一个编号 | 重同步软删旧组再新建；`_next_adjustment_no` 把已删组计入 |
| S13 | 底稿调整不自动进大厅 | `useAdjustmentCentralSync` 的 `autoSync` 默认 false，消费方无一开启 |
| S14 | 真库调整分录 | 34 行全部软删（draft 32 / approved 2），从未出现 pending_review / rejected |
| S15 | 附注主表依赖前端打开 E1 页 | 引擎对未与底稿同步的章节跳过（`note_writer.locate_table`）；附注由前端 `buildE1SyncPayload` 推送 |
| S16 | 报表公式「应用」假成功 | `/api/report-config/batch-update` 给 `ReportConfig` 设不存在的 `current_period_amount`，返回「已更新 N 行」实际未写，且查询不带项目条件 |
| S17 | 单体报表过期标记只标不清 | `report_engine.py` 中 `is_stale` 出现 0 次 |
| S18 | 推送从未在真库运行 | `formula_push_run` / `formula_push_state` 0 行；当前工作树迁移最高 V175（V174/V175 已被合并快照占用），真库 `schema_version` 仍为 173；本阶段新增审定数分量迁移必须使用 V176/R176 |

补充：S16 已由并行 spec `consol-elimination-single-source-push` 任务 8.1 在工作树删除（端点、`apiPaths.reportConfig.batchUpdate`、
公式管理弹窗回写段，未提交）⇒ 本 spec 不重做，只在收尾核对它与本 spec 的提交互不夹带。

## 需求

### 需求 1：推送引擎入库，干净检出自洽

**用户故事**：作为平台维护者，我要推送引擎真正在仓库里，任何人新克隆后都能跑通，而不是只在某台机器的工作树里存在。

#### 验收标准
1. THE 阶段二交付物（引擎、路由、模型、迁移、规则、前端面板与 E1 配套、对应测试）SHALL 提交入库；共享文件只提交本链的修改块，SHALL NOT 夹带并行工作的修改。
2. WHEN 在 HEAD 的干净检出（临时 `git worktree`）上运行推送全套测试 THEN SHALL 全部通过；干净检出上的结果是入库判据，工作树上通过不算。
3. THE 提交前 SHALL 核对分支 HEAD 未被并发提交移动（原子比较后再移动分支指针），SHALL NOT 改写他人提交。

### 需求 2：接入清单单一真源

#### 验收标准
1. THE 已接入公式推送的底稿清单 SHALL 只在后端 binding 注册表登记一处；触发器关心的科目前缀 SHALL 由各 binding 自报并从注册表派生。
2. THE 前端 SHALL 从后端接口取得接入清单，SHALL NOT 再写死 `PUSH_WP_CODES`。
3. WHEN 注册表新增一个 binding THEN 规则校验、触发判定、公式管理页签 SHALL 无需改其他文件即生效（测试以临时注册的假 binding 证明）。

### 需求 3：单一确认点 = 调整分录大厅复核通过

**用户故事**：作为项目经理，我在调整分录大厅点「复核通过」后，调整自动推到试算表、报表、底稿与附注；发现批错了可以撤回复核，下游随之回退。

#### 验收标准
1. THE 状态机 SHALL 允许 草稿 → 复核通过 / 驳回 直接流转（大厅没有「提交复核」入口）；SHALL 允许 复核通过 → 草稿（撤回复核）；其余非法流转仍拒绝并给中文原因。
2. WHEN 撤回复核 THEN SHALL 清除复核人与复核时间、发布 `ADJUSTMENT_REVIEW_REVOKED` 事件（登记年度补齐集合），并与「复核通过」走同一套重算与过期标记（试算表调整列、报表、附注、底稿）；试算表历史记录的触发标签 SHALL 区分「撤回复核」。
3. THE 复核 / 撤回端点 SHALL 只允许具 `adjustment:review` 权限者调用（与前端 `/my-permissions` 同一张权限表）；审计助理、质控、只读成员与非成员 SHALL 被拒（403），端点级真请求测试覆盖。
4. THE 大厅 SHALL 提供「复核通过 / 驳回 / 撤回复核」入口，按钮按 `adjustment:review` 权限显示；批量操作只作用于状态合法的分录并报告跳过数。
5. THE 复核状态变化 SHALL 经 SSE `adjustment:review-changed` 实时通知大厅与底稿页（当前该广播因错误 import 与错误参数从未发出）。
6. WHEN 底稿调整重新同步到大厅 THEN 内容未变 SHALL 不写库、不换编号；内容变化 SHALL 原地更新（保留分录组与编号），已驳回 / 待复核的分录回到草稿；已复核通过 SHALL 拒绝并提示先撤回复核。
7. THE 底稿调整页 SHALL 在用户编辑后自动同步到大厅（防抖、静默，失败给一次可见提示）；首次载入 SHALL NOT 触发同步；借贷不平衡或无有效行时不同步。

### 需求 4：试算表审定数单一写入方

**用户故事**：作为审计人员，我从底稿发布到试算表的审定数，不会因为之后批了一笔调整或重新导入四表就被悄悄抹掉。

#### 验收标准
1. THE 试算表 SHALL 新增「底稿调整」分量（发布时的审定数与 未审+RJE+AJE 之差）及其发布基准（发布时的未审数）与发布时间；全平台审定数口径 SHALL 统一为 `未审 + RJE + AJE + 底稿调整`。
2. WHEN 审定表发布到试算表 THEN 分量 SHALL 与审定数在同一条 UPDATE 内按行现算写入，且只作用于未删除行；同一科目命中多个公司编码 SHALL 跳过并报告，不写。
3. WHEN 调整审批 / 撤回、四表重新导入、映射变更触发重算 THEN 审定数 SHALL 按统一口径重算，保留底稿调整分量；未审数相对发布基准已变化时 SHALL 在试算表页标示「发布后未审数已变化，建议重新发布」。
4. THE 其余可达的审定数直写方 SHALL 改经同一写入函数；无调用方的直写方 SHALL 冻结为基线（只许减少），新增直写方即打红。
5. THE 一致性校验、汇总、交叉核对、取数解析、快照等读取口径 SHALL 同步改为统一口径（逐处测试，修复前红）。
6. THE 发布令牌 SHALL 用稳定摘要（跨进程、跨重启一致）。
7. THE 迁移 SHALL 为既有「审定数 ≠ 未审+RJE+AJE」的行回填分量，使审定数在下一次重算后保持不变。

### 需求 5：附注按章节交接（E1 主表先行）

#### 验收标准
1. WHEN 推送 E1 附注且目标章节没有「货币资金」主表 THEN 后端 SHALL 按附注模板（上市 五、1 / 国企 八、1）建主表骨架（行标签、列定义与前端推送逐字一致）后写值；SHALL 只交接项目模板类型对应的那一章。
2. IF 章节里有会被遮住的数据（主表以外的非空值）THEN SHALL 跳过并报告原因，SHALL NOT 建骨架。
3. THE 骨架合并 SHALL 与 `sync_from_workpaper` 同为浅合并（保留其余子表、叙述与原有 `rows` / `_tables`）。
4. WHEN 章节已由后端交接 THEN 前端 E1 页 SHALL 不再推送主表，只推受限表与叙述；主表的唯一写入方是后端。
5. THE 骨架 SHALL 有前后端共享夹具对拍，任一侧改行标签或列定义即红。

### 需求 6：K1 其他应收款上行接入

#### 验收标准
1. WHEN 四表入库或试算表更新 THEN K1 审定表的性质分类与组合行（r0~r3）的期初、未审数，以及 FS 三项（应收利息 / 应收股利 / 其他应收款合计），SHALL 由后端按与前端逐式一致的算式推送；审定合计 SHALL 由后端派生。
2. THE 取数 SHALL 用 strict 模式（失败上抛、零写入、留失败运行记录）；人工改值按三态规则保留。
3. THE 前端 SHALL 保存时过滤后端独占键，并以提示条告知「后台已更新」。
4. THE 前后端 SHALL 以共享夹具守卫算式与舍入一致。

### 需求 7：链上缺陷

#### 验收标准
1. WHEN 单体报表重算（全量生成或增量更新）THEN 被重算的报表行 SHALL 清除过期标记。
2. THE 事件调用点守卫（`test_event_call_site_guards.py`）在 HEAD 上的既有红 SHALL 清零（错误 import / 未 await 的 publish / await 了同步的 broadcast_raw / broadcast_raw 参数错位）。

### 需求 8：横切

#### 验收标准
1. 每个判据 SHALL 有修复前会红的测试；「零 / 非零」类判据 SHALL 配反向样本；变异改回即红。
2. 涉及 SQL 方言的写入 SHALL 有真 PG 验证（一次性 schema，结束删除）。
3. 真实项目验证 SHALL 以事务内试跑 + 回滚完成；真实数据写入须经用户确认。
4. 回归 SHALL 用 HEAD 干净检出对照归因，预存红与本 spec 引入的红分开报告。

## 非目标

- 试算表未审数改为公式驱动（决策 4：保持映射聚合，见 design ADR-P3-004）。
- 反转 V124 以大厅为审定数唯一真源（推翻 ADR-ADJ-002 与发布门流程）。
- F1 / D4 / L 等其他循环接入（F1 需先让前端落来源标记；D4 是动态行需行集 binding；L 前端无种子路径）。
- phase2 遗留三件待用户决定的事（3 个唯一索引重复键、附注 五、49 事故复原、和平药房_2025 试算表重算）。
- prefill 路径 B 调 `FormulaEngine.execute` 不传公式（真库 0 张底稿走该路径）。
