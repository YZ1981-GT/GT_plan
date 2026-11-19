# 六、三天源码阅读清单（主链路）

> 目标：亲自读懂「数是怎么来的、在什么时点触发、可能在哪出错」。范围只限主链路，约 55 个函数、4700 行，占后端代码不到 0.5%。
> 路径省略前缀 `backend/app/`。行号按 2026-11-18 的代码（`dev1.0` `3a9c0db4f`），代码改动后会偏移，偏移了就按函数名搜。
> 打开方式：VS Code 里 `Ctrl+P` 输入文件名打开，`Ctrl+G` 输入行号跳转。

## 读法

1. **按清单顺序读**。遇到被调用的辅助函数，跳进去看完再回来；清单外的模块（各循环底稿、在线编辑同步、AI、证据归档）先跳过。
2. **每读完一个函数，在「笔记」列写一句话**：谁触发、读什么表、写什么表、有什么疑点。三天下来这一列就是你自己的规则清单。
3. **对照文档**：每个函数后面标了 [02 规则清单](02-rules.md) 的编号（R）和 [03 发现](03-findings.md) 的编号（F），读的时候顺便确认这些结论对不对。
4. **追一个真实科目**：第 3 天下午用文末的只读 SQL，在【测试】项目里把应收账款 1122 从余额表一路追到附注，验证这三天读到的逻辑。

---

## 第 1 天：数据进来到试算表（约 2480 行）

当天读完要能讲清：
- 一份账套导入后，四张账表的数据存在哪一版？旧版本怎么失效？回滚时会发生什么？
- 客户科目怎么变成标准科目？哪些映射是系统自动猜的？
- 试算表的未审数、调整数、审定数各自怎么算？哪些操作会触发重算？

| ☐ | 函数 | 位置（行号） | 行数 | 看什么 | 对照 | 笔记 |
|---|---|---|---:|---|---|---|
| ☐ | `ImportJobRunner._execute_v2` | `services/import_job_runner.py` 648–973 | 326 | 导入作业的状态怎么流转（校验中 → 写入中 → 激活中 → 完成 / 失败），失败时怎么清理 | R1.5 | |
| ☐ | `execute_pipeline` | `services/ledger_import/pipeline.py` 222–930 | 709 | 分段读：建 staged 数据集（约 441 行）、写四表（约 455 行）、列映射的采纳阈值（约 520 行）、L1 校验（约 603 行）、激活闸门（约 730–760 行） | R1.2、R1.5、R1.6 | |
| ☐ | `DatasetService.create_staged` | `services/dataset_service.py` 107–133 | 27 | 新数据集怎么记住上一版 | R2.1 | |
| ☐ | `DatasetService.activate` | `services/dataset_service.py` 136–302 | 167 | 新旧版本怎么切换；行数不符为什么拒绝激活；激活后发什么事件 | R2.1 | |
| ☐ | `DatasetService.rollback` | `services/dataset_service.py` 305–473 | 169 | 回滚的前提；为什么已定稿报表绑定的数据集不能回滚 | R2.2 | |
| ☐ | `get_active_filter` | `services/dataset_query.py` 27–115 | 89 | 所有读账表的地方怎么只取当前版本；查询失败时怎么退化 | R2.3、F5 | |
| ☐ | `_make_handler`、`_make_tb_handler` | `services/event_handlers/_impl.py` 44–98 | 53 | 事件处理器怎么开会话、怎么防重复、提交后再发下一个事件 | R4.4 | |
| ☐ | `register_event_handlers`（只读开头） | `services/event_handlers/_impl.py` 397–490 | 约 94 | 导入 / 映射 / 调整 → 试算表 → 报表 → 附注的订阅关系。其余 2000 行按需查 [附录 B](appendix-b-events.md) | R4.4、F1、F7 | |
| ☐ | `_auto_map_on_dataset_activated` | `services/event_handlers/_impl.py` 101–155 | 55 | 账套激活后自动做科目映射 | R3.1、F7 | |
| ☐ | `auto_match` | `services/mapping_service.py` 383–471 | 89 | 缺客户科目表、缺标准科目时怎么补；匹配结果直接入库 | R3.1、F2 | |
| ☐ | `_match_single` | `services/mapping_service.py` 543–660 | 118 | 匹配顺序与置信度：坏账准备子科目 → 编码 → 前缀 → 名称 → 模糊 0.7 | R3.1、F2 | |
| ☐ | `save_mapping`、`_publish_mapping_changed` | `services/mapping_service.py` 668–720、104–124 | 74 | 人工改映射后发什么事件、重算哪些科目 | R3.2 | |
| ☐ | `leaf_condition`、`resolved_standard_code`、`period_movement_query` | `services/tb_balance_rollup.py` 25–89 | 61 | 只汇总叶子科目；没映射的叶子继承父科目；损益类发生额从哪取 | R4.1、F2、F3 | |
| ☐ | `TrialBalanceService.recalc_unadjusted` | `services/trial_balance_service.py` 59–298 | 240 | 未审数口径：方向归一、损益类取发生额、贷方类取绝对值、全量时清零旧行 | R4.1 | |
| ☐ | `TrialBalanceService.recalc_adjustments` | `services/trial_balance_service.py` 303–404 | 102 | 只计已批准、排除底稿来源；贷方类取反；只更新已有行 | R4.2、F8 | |
| ☐ | `recalc_audited`、`full_recalc` | `services/trial_balance_service.py` 409–460 | 48 | 审定数 = 未审 + RJE + AJE + 底稿调整差额 | R4.3 | |
| ☐ | `on_adjustment_changed`、`on_mapping_changed`、`on_data_imported` | `services/trial_balance_service.py` 1125–1186 | 60 | 三种事件分别重算哪几列 | R4.4 | |

---

## 第 2 天：调整分录、审定数发布、报表（约 1450 行）

当天读完要能讲清：
- 一笔调整分录从录入到影响试算表要经过哪几步？哪些分录不进试算表？
- 审定表「发布到试算表」写了哪些列？为什么之后重算不会把它冲掉？
- 报表里一行的数是怎么算出来的？缺科目时会怎样？试算表变了，哪些报表行会重算？

| ☐ | 函数 | 位置（行号） | 行数 | 看什么 | 对照 | 笔记 |
|---|---|---|---:|---|---|---|
| ☐ | `entry_rule_errors` | `services/adjustment_entry_rules.py` 38–77 | 40 | 录入校验：科目必填、借贷平衡、同一行不能同时有借贷 | R5.1 | |
| ☐ | `AdjustmentService.create_entry` | `services/adjustment_service.py` 105–180 | 76 | 编号规则；写哪两张表；发什么事件 | R5.1、R5.2 | |
| ☐ | `effective_groups_clause` | `services/adjustment_treatment_service.py` 256–265 | 10 | 「客户已入账」「不予更正」的分录怎么被排除 | R5.6 | |
| ☐ | `AdjustmentReviewCoordinator.decide` | `services/adjustment_review_coordinator.py` 96–217 | 122 | 批准 / 驳回的前提；批准后同一事务里补试算表行、重算 | R5.3 | |
| ☐ | `AdjustmentReviewCoordinator.revoke` | `services/adjustment_review_coordinator.py` 219–281 | 63 | 撤回复核后试算表怎么回退 | R5.3、F8 | |
| ☐ | `_maybe_publish_determination_writeback` | `routers/wp_html_save.py` 473–570 | 98 | 普通保存审定表为什么不动试算表 | R6.2 | |
| ☐ | `publish_determination_to_tb` | `routers/wp_html_save.py` 696–884 | 189 | 显式发布的门槛：权限、合并锁、审定表子码、客户已入账确认、幂等令牌 | R6.1 | |
| ☐ | `validate_workpaper_adjustments_approved`、`publish_workpaper_rows` | `services/tb_publish_service.py` 35–170 | 134 | 来源底稿的调整分录必须先批准；有行写不进去就整体取消 | R6.1 | |
| ☐ | `publish_rows` | `services/tb_audited_writer.py` 203–308 | 106 | 写审定数的同时写 `wp_adjustment`，所以重算后结果不变 | R6.1、03 第五节 | |
| ☐ | `ReportEngine.generate_all_reports` | `services/report_engine.py` 1269–1441 | 173 | 生成前先重算试算表；报表类型的计算顺序；写缓存与版本戳 | R7.3、F7 | |
| ☐ | `ReportFormulaParser._resolve_tb`、`_tb_amount_reader` | `services/report_engine.py` 644–695 | 51 | `TB('科目','列')` 怎么按前缀只计叶子；列名对应哪一列 | R7.4 | |
| ☐ | `evaluate_formula_result` | `services/report_engine.py` 937–1098 | 162 | 报表公式支持哪些函数；为什么不支持 PREV / AUX；WP / NOTE 缺数报错 | R7.4、F4 | |
| ☐ | `compute_row`、`_missing_account_notes` | `services/report_row_compute.py` 163–208、278–289 | 58 | 一行的计算结果怎么分成功 / 失败；缺科目「按 0 计」写在哪 | R7.4、F4 | |
| ☐ | `ReportEngine.on_trial_balance_updated` | `services/report_engine.py` 2639–2685 | 47 | 试算表变了以后按项目真实准则增量重算 | R7.5 | |
| ☐ | `ReportEngine.regenerate_affected`、`_is_affected` | `services/report_engine.py` 2251–2376 | 126 | 哪些行算「受影响」；为什么增量重算不建新行 | R7.5 | |

---

## 第 3 天：公式推送、附注、合并、签字门禁（约 830 行 + 汇总）

当天读完要能讲清：
- 试算表变了以后，底稿和附注怎么被更新？公式推送和「报表更新后刷新附注」两条路谁先谁后？
- 附注某一格被人手工改过，系统还会不会覆盖它？
- 合并数是怎么来的？差额表、合并试算、合并报表、合并附注的先后顺序？
- 签字前的一致性门禁查了哪些东西？

| ☐ | 函数 | 位置（行号） | 行数 | 看什么 | 对照 | 笔记 |
|---|---|---|---:|---|---|---|
| ☐ | `on_trial_balance_updated`、`on_workpaper_saved` | `services/formula_push/triggers.py` 174–210 | 35 | 推送在什么条件下才跑；合并项目为什么跳过 | R9.2 | |
| ☐ | `run_and_commit`（顺着读同文件的 `_execute`） | `services/formula_push/engine.py` 959–982 | 24 + | 推送规则怎么加载、写底稿明细和附注、记运行结果 | R9.1、R9.2 | |
| ☐ | `DisclosureEngine._load_templates` | `services/disclosure_engine.py` 958–1057 | 100 | 国企 / 上市模板怎么选；读不到模板时退回 6 条旧种子 | R13.1、F12 | |
| ☐ | `DisclosureEngine.generate_notes` | `services/disclosure_engine.py` 1735–2009 | 275 | 正文取上年还是模板；表格怎么构建；已有章节怎么合并、哪些格不覆盖 | R13.2、R13.3 | |
| ☐ | `DisclosureEngine.update_note_values`、`on_reports_updated` | `services/disclosure_engine.py` 2014–2092、2783–2800 | 97 | 报表更新后按变化科目刷新附注 | R13.4、F6 | |
| ☐ | `WriteGate.check` | `services/note_write_ownership.py` 187–210 | 24 | 写权判定顺序：锁定 → 手工 → 推送 → 治理域外 → 容器 → 推送写定格 → 基础条目 | R13.3、F6 | |
| ☐ | `build_group_tree`（顺着读 `build_entity_graph`） | `services/consol_group_tree.py` 755–764 | 10 + | 企业树怎么按三码现算 | R14.1 | |
| ☐ | `_push_one` | `services/consol_push_service.py` 266–386 | 121 | 合并推送四步的顺序；关键步骤失败后跳过后续 | R14.2 | |
| ☐ | `recalculate_trial` | `services/consol_trial_service.py` 138–194 | 57 | 合并数 = 个别数汇总 + 调整 + 抵销 | R14.4 | |
| ☐ | `trial_amounts` | `services/consol_calc_basis.py` 738–770 | 33 | 调整与抵销的符号规则；哪些分录进调整列 | R14.4 | |
| ☐ | `ConsistencyGate.run_all_checks`（再挑 `check_tb_balance` 读一个） | `services/consistency_gate/_impl.py` 50–104 | 55 | 40 项检查的清单；阻断类检查不通过时整体判失败 | R15.8 | |

**第 3 天下午：汇总**
- ☐ 用下面的 SQL 在【测试】项目里追一遍应收账款 1122，核对读到的逻辑。
- ☐ 把三天的「笔记」列整理成一页，按「数据进来 → 试算表 → 调整与发布 → 报表 → 附注 / 合并 → 门禁」讲一遍。
- ☐ 对着 [03 发现](03-findings.md) 逐条标出「已确认 / 不同意 / 没读到」。

---

## 追一个科目：应收账款 1122（只读 SQL）

只用 `SELECT`，在【测试】项目上跑。如果连的是生产库，只看不改。把 `:pid`、`:year`、`:ds` 换成实际值。

```sql
-- 0. 找一个【测试】项目
SELECT id, client_name, audit_year, report_scope, template_type
FROM projects WHERE client_name LIKE '%测试%' AND is_deleted = false;

-- 1. 当前生效的数据集（status = 'active' 的那条就是 :ds）
SELECT id, status, activated_at, record_summary
FROM ledger_datasets WHERE project_id = :pid AND year = :year ORDER BY created_at DESC;

-- 2. 余额表里 1122 及下级（只看生效版本）
SELECT account_code, account_name, closing_direction, closing_balance, debit_amount, credit_amount
FROM tb_balance
WHERE project_id = :pid AND year = :year AND dataset_id = :ds AND account_code LIKE '1122%'
ORDER BY account_code;

-- 3. 这些客户科目映射到哪个标准科目，是自动猜的还是人工确认的
SELECT original_account_code, standard_account_code, mapping_type
FROM account_mapping
WHERE project_id = :pid AND is_deleted = false AND original_account_code LIKE '1122%';

-- 4. 试算表这一行（审定数应 = 未审 + RJE + AJE + 底稿调整差额）
SELECT standard_account_code, unadjusted_amount, rje_adjustment, aje_adjustment, wp_adjustment,
       audited_amount, wp_published_at
FROM trial_balance
WHERE project_id = :pid AND year = :year AND standard_account_code LIKE '1122%' AND is_deleted = false;

-- 5. 影响它的调整分录（只有 approved 且 origin 不是 workpaper 的才进 AJE / RJE 列）
SELECT a.adjustment_no, a.adjustment_type, a.review_status, a.origin,
       e.standard_account_code, e.debit_amount, e.credit_amount
FROM adjustment_entries e JOIN adjustments a ON a.id = e.adjustment_id
WHERE a.project_id = :pid AND a.year = :year AND a.is_deleted = false
  AND e.is_deleted = false AND e.standard_account_code LIKE '1122%';

-- 6. 报表里用到它的行
SELECT report_type, row_code, row_name, current_period_amount, formula_used, is_stale, calc_error
FROM financial_report
WHERE project_id = :pid AND year = :year AND formula_used LIKE '%1122%';

-- 7. 附注章节（国企「八、5」，上市「五、5」）
SELECT note_section, section_title, is_stale, stale_source, updated_at
FROM disclosure_notes
WHERE project_id = :pid AND year = :year AND section_title LIKE '%应收账款%' AND is_deleted = false;
```

每一步对照前面读过的函数：第 2→3 步是 `resolved_standard_code`，第 3→4 步是 `recalc_unadjusted`，第 5→4 步是 `recalc_adjustments`，第 4→6 步是 `_resolve_tb`，第 6→7 步是 `update_note_values` 和公式推送。

## 三天内不读的部分

| 模块 | 规模 | 需要时从哪入手 |
|---|---|---|
| 各循环底稿（D~N 等） | 804 个接口 | [附录 D](appendix-d-api-list.md) 按底稿编码搜接口，再看 [02](02-rules.md) R10、R11 |
| 底稿在线编辑同步 | 30 张表、52 个接口 | [02](02-rules.md) R12；入口 `routers/wp_sync_router.py::post_room_onlyoffice_callback` |
| AI 与知识库 | 33 张表、191 个接口 | [附录 D](appendix-d-api-list.md) 的 D14 |
| 附件、证据、函证、归档 | 47 张表、130 个接口 | [05 关系图](05-diagrams.md) D12 的 ER 图 |
| 复核、质控 | 29 张表、186 个接口 | [02](02-rules.md) R15 |
