# 实施计划：ADJ 取数修复与调整分录确认门接线

> 关联需求：#[[file:.kiro/specs/adj-formula-repair-and-approval-gate-wiring/requirements.md]]
> 关联设计：#[[file:.kiro/specs/adj-formula-repair-and-approval-gate-wiring/design.md]]
> 任务约定：`[ ]` 未开始 / `[x]` 完成 / `[ ]*` 可选或待外部环境。
> 铁律：测试先行见红 → 再改实现 · 判据禁写死行号与计数（一律现算）·
> 结构性零必配双向变异证明 · service 只 flush / router 层 commit ·
> 事件在 commit 之后 publish · `hypothesis` PBT `max_examples=5`。
> 分阶段理由：阶段 1 是纯 bugfix（风险最低、收益最大），阶段 4 口径收紧风险最高故置后。

## 阶段 0：守卫先行（见红）

- [ ] 0.1 新建 `backend/tests/test_adj_formula_resolution.py`：**真正执行** `ADJ()` 求值
  - AJE 取数 / RJE 取数 / **AJE 与 RJE 结果必不相等** / 贷方类符号归一 / 无数据返 `Decimal("0")`
  - 断言当前**必红**（`ImportError`），提交时在文件头写明「修复前红、修复后绿」
  - _需求：7.1, 7.2, 7.5_ _属性：P1, P2_

- [ ] 0.2 新建 `_FORMULA_RESOLVERS` 全成员冒烟守卫
  - 遍历 registry **每个** resolver 各调一次（最小合法入参），断言不抛 `ImportError`/`AttributeError`
  - registry 成员数**现算**，禁写死；新增 resolver 未配用例即红
  - _需求：7.4_ _属性：P1, P12_

- [ ] 0.3 新建口径对账守卫 `test_adj_amount_source_parity.py`
  - 同 `(project_id, year, account_code, adj_type)` 下，批量路径与单点路径逐值相等
  - 双向变异：存在 workpaper 来源分录时，`exclude_origins={"workpaper"}` 与空集**必不相等**
  - _需求：3.3_ _属性：P5, P6, P12_

- [ ] 0.4 新建名实相符守卫
  - 扫 `event_handlers/` 中 handler 函数名含 `approved` 者，断言其订阅 `ADJUSTMENT_APPROVED`
  - 变异证明：把断言施加于同组 `on_event_ledger_activated` / `on_event_workpaper_reviewed`
    应通过（二者名实已相符）⇒ 证明扫描器不是恒红
  - _需求：5.1, 5.2_ _属性：P10, P12_

## 阶段 1：最小修复（import + 类型归一）

- [ ] 1.1 修 `prefill_engine._resolve_adj_formula` 的 import 路径
  - 改为 `from app.models.audit_platform_models import Adjustment, AdjustmentEntry`
  - 判据：任务 0.1 转绿；对外签名与 `_FORMULA_RESOLVERS` 注册形态不变
  - _需求：1.1, 1.2, 1.3, 1.4_ _属性：P1_

- [ ] 1.2 全仓触类旁通：grep 同类错误 lazy import
  - 扫全部 `from app.models.<mod> import <Name>` 的**函数体内** import，逐个验证可解析
  - 命中数**现算**写进任务勾选记录；0 命中也要写「现算 0 + 已配变异证明」
  - _需求：1.5_ _属性：P1, P12_

- [ ] 1.3 新建 `normalize_adj_type`（类型归一，含非法入参 raise）
  - 归一表容纳 `aje_net`/`AJE`/`审计调整` → `"aje"`，`rje_net`/`RJE`/`重分类` → `"rje"`
  - 不可归一 → **raise**，禁退化为「不加 `adjustment_type` 过滤」
  - _需求：2.1, 2.2, 2.3_ _属性：P2, P3_

- [ ] 1.4 `_resolve_adj_formula` 接入 `normalize_adj_type`
  - 判据：任务 0.1 的「AJE 与 RJE 必不相等」转绿
  - 与 `wp_cross_check_service._get_adj_value` 的归一结果逐值一致
  - _需求：2.4_ _属性：P2_

- [ ] 1.5 幂等脚本修正预设中的占位符第二参
  - 新建 `backend/scripts/fix/fix_adj_preset_type_literals.py`（`--dry-run`/`--check`/`--apply`，带 round-trip 自检）
  - 修正现算命中的占位符（编写时为 1 处 `'类型'`，**交付时重算**）
  - `--check` 须归零；控制台输出禁 emoji
  - _需求：2.5_ _属性：P3_

- [ ] 1.6 CI 守卫：预设第二参必在归一白名单内
  - 新增 `ADJ()` 预设若第二参不可归一 → CI 失败
  - 双向变异：故意注入非法字面量应红、现有合法预设应绿
  - _需求：7.6_ _属性：P3, P12_

- [ ] 1.7 阶段 1 回归 + 真实项目验证
  - `rtk python -m pytest backend/tests/ -k "adj or prefill or formula" -v --tb=short`
  - 在真实 PG 项目上跑一次 prefill，断言返回 `errors` 数组中 ADJ 相关条目**归零**
  - 记录本阶段前后「ADJ 预设求出非空值的格数」对比（现算，禁写死）
  - _需求：1.2, 7.5_ _属性：P1, P2_ _风险：R1_

## 阶段 2：单一取数函数收敛

- [ ] 2.1 新建 `backend/app/services/adjustment_amount_source.py`
  - `adj_net(db, *, project_id, year, account_code, adj_type, include_statuses=None, exclude_origins=frozenset())`
  - 科目列走 `adjustment_entries.standard_account_code` + JOIN `adjustments`（`origin`/`review_status` 只在主表）
  - 符号归一复用 `ledger_import.direction_resolver.resolve_account_direction`
  - 只读、只 flush 不 commit
  - _需求：3.1, 3.2_ _属性：P4_ _ADR：ADR-ADJ-001_

- [ ] 2.2 `_resolve_adj_formula` 改调 `adj_net`
  - 传 `exclude_origins=frozenset()` 并在调用点注释说明**为何与 TB 列口径不同**
  - _需求：3.1, 3.4_ _属性：P6_ _ADR：ADR-ADJ-002_

- [ ] 2.3 `wp_cross_check_service._get_adj_value` 改调 `adj_net`
  - 口径与 `ADJ()` 一致（底稿显示与核对同源）
  - _需求：3.1, 3.4_ _ADR：ADR-ADJ-002_

- [ ] 2.4 `recalc_adjustments` 替换口径判定逻辑（保留批量 SQL 形态）
  - 只替换 `review_status`/`origin`/类型归一/符号四项判定，**不改批量聚合为 N+1**
  - 传 `exclude_origins={"workpaper"}` 保 V124 防双计
  - 判据：任务 0.3 的批量↔单点逐值相等转绿
  - _需求：3.1, 3.5_ _属性：P5_ _ADR：ADR-ADJ-001_

- [ ] 2.5 删除三处自称「同口径」的失效注释，改写为参数化差异说明
  - 判据：全仓不再出现声称一致而实际不同的注释（人工复核 + grep 关键短语）
  - _需求：3.5_ _属性：P4_

- [ ] 2.6 P4 守卫：禁第二份净额实现
  - AST/正则扫「JOIN adjustments 求 `debit_amount - credit_amount` 净额」的实现
  - 除 `adjustment_amount_source` 外命中即红；双向变异（故意复制一份应红）
  - _需求：3.1_ _属性：P4, P12_

- [ ] 2.7 性能实测（JOIN 改造）
  - 真实 PG 现查 `adjustments` / `adjustment_entries` 行数（现算）
  - `explain_query` 对比改造前后；必要时加 `adjustment_entries.standard_account_code` 索引
  - _需求：3.1_ _风险：R3_

## 阶段 3：确认门事件接线

- [ ] 3.1 `EventType` 新增 `ADJUSTMENT_APPROVED = "adjustment.approved"`
  - 位置与注释格式对齐既有 `ELIMINATION_APPROVED`（含 payload 说明注释）
  - _需求：4.1_ _属性：P7_

- [ ] 3.2 `_change_review_status` 转 `approved` 时发布事件
  - payload 含 `project_id` / `year` / `account_codes`（受影响科目）/ `entry_group_id`
  - **发布位置在 router 层 commit 之后**（service 只 flush），照搬 `routers/consolidation.py` 样板
  - _需求：4.2, 4.3_ _属性：P7_

- [ ] 3.3 新建 `backend/app/services/adjustment_approved_recalc_handler.py`
  - `handle_adjustment_approved` + `register_adjustment_approved_recalc_handler`
  - 失败记 error **不抛**（不阻断审批）；幂等靠按科目覆盖写
  - 结构逐项照搬 `consol_elimination_recalc_handler.py`
  - _需求：4.5, 4.6_ _属性：P8_

- [ ] 3.4 `main.py` 注册 handler
  - 位置与既有 `register_consol_elimination_recalc_handler` 同处
  - 判据：启动日志出现注册记录；**FastAPI 不热加载，改后须重启 `start-dev.bat`**
  - _需求：4.2_ _属性：P7_

- [ ] 3.5 `on_event_adjustment_approved` 改订阅 `ADJUSTMENT_APPROVED`
  - 同时更新其 docstring（当前写 `ADJUSTMENT_BATCH_COMMITTED →`，与函数名矛盾）
  - 判据：任务 0.4 转绿
  - _需求：5.1_ _属性：P10_

- [ ] 3.6 新建 `on_event_adjustment_batch_committed` 保留批量提交标 stale 行为
  - 订阅 `ADJUSTMENT_BATCH_COMMITTED`，行为与原实现一致（行为保留、命名纠正）
  - 同组 `on_event_ledger_activated` / `on_event_workpaper_reviewed` **保持不动**
  - _需求：5.2, 5.3_ _属性：P10_ _设计：§四.3_

- [ ] 3.7 扩订 SSE / 底稿 stale / 报表 stale 到 `ADJUSTMENT_APPROVED`
  - `_notify_adjustment_event_sse` / `_mark_workpapers_stale_by_account` /
    `_mark_reports_stale_on_adjustment` 增订该事件
  - 按 `account_codes` 增量，禁全量刷（防事件风暴）
  - _需求：8.3, 8.4_ _风险：R6_

- [ ] 3.8 幂等 PBT
  - 同一 `entry_group_id` 连续触发 2 次 → 试算表结果不变（`max_examples=5`）
  - _需求：4.6_ _属性：P8_

- [ ] 3.9 撤回语义守卫
  - 断言「纳入口径常量」与「已订阅事件集合」自洽：口径含 `pending_review` 时必须存在撤回事件
  - 现口径为「仅 approved」故断言无需撤回事件；口径放宽后该守卫自动变红
  - _需求：4.4_ _ADR：ADR-ADJ-005_

## 阶段 4：口径收紧（风险最高，置后）

- [ ] 4.1 真实 PG 实测 `review_status` 分布（先测后改）
  - 现查各 `review_status` 的 entry_group 数与金额量级，按项目分组
  - 若 `draft`/`pending_review` 占比过高 ⇒ **回到设计重议 ADR-ADJ-003**，不硬改
  - _需求：6.5_ _ADR：ADR-ADJ-003_ _风险：R2_

- [ ] 4.2 `recalc_adjustments` 加 `review_status == approved` 过滤
  - 通过 `adj_net` 的 `include_statuses` 参数传入，不散写 SQL 条件
  - _需求：6.1, 6.2_ _属性：P5_ _ADR：ADR-ADJ-003_

- [ ] 4.3 `check_consistency` 不变式回归
  - `audited == unadjusted + rje + aje` 在新口径下仍成立
  - _需求：6.3_

- [ ] 4.4 差额可观测验证
  - 存在未纳入（draft）分录时，`trial_balance_full_view_service.other_adjustment` 非零
  - 双向变异：全部 approved 时该列为 0
  - _需求：6.4_ _属性：P11, P12_

- [ ] 4.5 下游全量回归（现算清单逐个）
  - `wp_formula_eval_service` / `wp_mapping_service` / `wp_fill/_note_draft` /
    `wp_data_rules` / `wp_cross_check_service` / `wp_audit_sheet_tb_service` /
    `triple_format_adapter` / `trial_balance_service` / `trial_balance_full_view_service`
  - 清单**交付时现算**（禁写死）；每个消费点确认口径变更后语义仍正确
  - _需求：6.5_ _风险：R4_

- [ ] 4.6 既有测试红项逐条判定
  - 每个红项记录「测试固化了错口径」或「实现改错了」，禁改断言凑绿
  - 判定结论写进本 tasks 的勾选记录
  - _需求：6.6_ _风险：R4_

## 阶段 5：端到端验证与收尾

- [ ] 5.1 端到端集成测试（本 spec 的验收核心）
  - 建分录（draft）→ 断言调整列**未**变 → 确认（approved）→ 断言调整列与审定数已变
    → 断言 `TRIAL_BALANCE_UPDATED` 已发布
  - 真 SQLite + 真 ORM 行 + 真 service（不 mock 相邻层——合并模块四阶段的教训）
  - _需求：8.5_ _属性：P9_

- [ ] 5.2 整链贯通验证（不新建、只验证）
  - 确认门 → 试算表 → `TRIAL_BALANCE_UPDATED` → `ReportEngine` → `REPORTS_UPDATED`
    → `DisclosureEngine` 各段被实际调用
  - _需求：8.1, 8.2_ _属性：P9_

- [ ]* 5.3 Playwright 实测（需 `start-dev.bat` 环境）
  - 分录大厅确认一笔 → 试算表页调整列与审定数变化 → 底稿审定表调整列取到值
  - 环境不可用时如实标 `[ ]*` + 写「代码已改但未实测」，**禁标完成**
  - _需求：8.6_

- [ ] 5.4 清理探针文件
  - 删 `backend/scripts/analyze/_adjp_*.py` 与 `_adj_*.txt`（`_` 前缀 = 用完即删）
  - _设计：§十_

- [ ] 5.5 交付前自查（逐项对 design §十 清单）
  - 脚本化检查「每条需求 / 每条 P1~P12 / 每条 ADR 至少被某 task 引用」
  - 光数编号连续不算（B 轮教训：18 条判据悬空正是这样漏掉的）
  - 无写死行号、无写死计数
  - _设计：§十_

- [ ] 5.6 沉淀
  - `#dev-history` 追加本轮结论（ADJ 三层缺陷 + 测试盲区模式 + 口径矩阵）
  - `memory.md` 只更新状态行（≤200 行约束）
  - 归档 spec 勘误**不回填**，保留在本 spec §八

---

## 判据引用闭合性对照（交付前须脚本复核）

| 判据 | 被引用任务 |
|---|---|
| 需求 1.1~1.5 | 1.1, 1.2, 1.7 |
| 需求 2.1~2.5 | 1.3, 1.4, 1.5 |
| 需求 3.1~3.5 | 2.1~2.6, 0.3 |
| 需求 4.1~4.6 | 3.1~3.4, 3.8, 3.9 |
| 需求 5.1~5.4 | 0.4, 3.5, 3.6（5.4 由 design §八 承接）|
| 需求 6.1~6.6 | 4.1~4.6 |
| 需求 7.1~7.6 | 0.1, 0.2, 1.6, 1.7 |
| 需求 8.1~8.6 | 3.7, 5.1, 5.2, 5.3 |
| P1 | 0.1, 0.2, 1.1, 1.2, 1.7 |
| P2 | 0.1, 1.3, 1.4, 1.7 |
| P3 | 1.3, 1.5, 1.6 |
| P4 | 2.1, 2.5, 2.6 |
| P5 | 0.3, 2.4, 4.2 |
| P6 | 0.3, 2.2 |
| P7 | 3.1, 3.2, 3.4 |
| P8 | 3.3, 3.8 |
| P9 | 5.1, 5.2 |
| P10 | 0.4, 3.5, 3.6 |
| P11 | 4.4 |
| P12 | 0.2, 0.3, 0.4, 1.2, 1.6, 2.6, 4.4 |
| ADR-ADJ-001 | 2.1, 2.4 |
| ADR-ADJ-002 | 2.2, 2.3 |
| ADR-ADJ-003 | 4.1, 4.2 |
| ADR-ADJ-004 | 范围外（requirements「范围外」节 + design §七 登记收口路径）|
| ADR-ADJ-005 | 3.9 |
| R1~R6 | 1.7, 2.7, 3.7, 4.1, 4.5, 4.6 |
