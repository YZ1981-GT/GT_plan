# Implementation Plan: 公式管理库（Formula Management Library）

## Overview

本实施计划把设计文档的统一公式治理层拆解为可增量交付、可独立验证的编码任务。实现语言遵循设计：后端 Python 3.12（FastAPI + asyncpg + SQLAlchemy async），前端 TypeScript + Vue 3 + Element Plus。

组织原则：
- 按交付物分组（数据层 → 引擎 → WpFormula → logic_check 收编 → 一键刷新编排器 → 审定表回写 → 报表 → 附注 → 交付 → 前端），每组末尾设 Checkpoint。
- 每个任务引用具体需求条款（`_Requirements: X.Y_`）与设计属性（Property N）以便追溯。
- 属性测试（后端 Hypothesis / 前端 vitest）作为独立子任务，逐条映射 P1–P18；用 `*` 标记可选（按约定仍会完成，但保留 `*` 标记以便 UI 区分）。
- 三层一致性铁律：迁移（V100）+ ORM（workpaper_models.py）+ service 同步落地。
- 边界协调（不重写）：地址解析/选址器/NoteFormulaDialog 修复引用 `acnr-consumer-wiring` Req 9/14/15，仅通过依赖说明协调，不新建重复任务。

---

## Tasks

- [ ] 1. 数据层与三层一致性（V100 迁移 + ORM 同步）
  - [x] 1.1 编写 V100 迁移脚本
    - 在 `backend/migrations/V100.sql` 中：① 用 `DO $$ ... information_schema.columns` 检测列存在性后 `ALTER TABLE wp_formula ADD COLUMN` 补齐 `formula_type VARCHAR(20) NOT NULL DEFAULT 'auto_calc'` / `last_computed_at TIMESTAMPTZ` / `refs JSONB NOT NULL DEFAULT '[]'::jsonb` / `issue_description TEXT` / `hint_text TEXT`
    - ② `CREATE TABLE IF NOT EXISTS draft_marker`（含 `uq_draft_marker_unit` 唯一索引 on project_id, year, unit_scope）
    - ③ `CREATE TABLE IF NOT EXISTS draft_refresh_audit`（append-only 审计留痕 + `idx_draft_audit_project_year`）
    - ④ `CREATE TABLE IF NOT EXISTS draft_refresh_snapshot`（回滚快照，FK→draft_refresh_audit + `idx_draft_snapshot_refresh`）
    - 全部索引在 `IF NOT EXISTS` 与列存在性检测之后创建，确保重复运行幂等
    - _Requirements: 3.2, 3.5, 4.1, 4.2, 4.6_

  - [-] 1.2 同步 ORM 模型（workpaper_models.py）
    - 在 `backend/app/models/workpaper_models.py:WpFormula` 补 `formula_type` / `last_computed_at` / `refs` / `issue_description` / `hint_text` 的 `Mapped[]` 声明
    - 新增 `DraftMarker` / `DraftRefreshAudit` / `DraftRefreshSnapshot` ORM 模型，字段与 V100 表结构逐列对齐
    - _Requirements: 14.5_

  - [ ]* 1.3 编写 V100 迁移幂等测试
    - 断言 `wp_formula` 五个新列 + 三张新表建成；重复执行迁移不报错（IF NOT EXISTS + information_schema 守护）
    - _Requirements: 3.2, 4.1, 4.2_

- [ ] 2. 公式引擎类型分派层（formula_management/engine.py）
  - [-] 2.1 实现 resolve_ref 引用解析封装
    - 在 `backend/app/services/formula_management/engine.py` 新建 `resolve_ref(*, formula_ref=None, addr_id=None, project_id, db)` 封装 ACNR `full_resolve`
    - found=true → 返回 canonical addr_id 作引用身份；基础设施异常 → 记 WARNING 结构化日志 + fail-open 回退既有解析路径（不吞异常、不阻断）
    - 禁止拼接 `wp_code+sheet+cell` 裸字符串
    - 依赖说明：复用 `acnr-consumer-wiring` Req 9 的 ACNR 校验路径，不新增并行校验
    - _Requirements: 11.1, 11.2, 11.3, 11.5_

  - [~] 2.2 实现 execute_formula 三类型分派 + 结果结构
    - 定义 `IssueItem` / `HintItem` / `FormulaExecResult` dataclass
    - `execute_formula` 按 `formula_type` 分派：auto_calc → 求值回填目标单元 + 记 `last_computed_at`（求值失败保留原值不写时间戳）；logic_check → 条件不通过追加 Issue_List（无法求值时追加"公式无法求值"项，不静默跳过）；reasonability → 触发追加 Hint_List（无法求值记 WARNING 跳过不中断）
    - logic_check / reasonability 分支绝不修改任何数据单元值
    - _Requirements: 5.1, 5.2, 5.4, 5.5, 6.1, 6.2, 6.6, 7.1, 7.2, 7.5_

  - [~] 2.3 实现四表库叶子源只读守卫与取数契约
    - 定义校验：目标地址为四表库（trial_balance/tb_balance/tb_ledger/tb_aux_balance）单元时拒绝定义 auto_calc 回填公式
    - `TB()`/`PREV()`/`AUX()` 取数经 `get_active_filter` 统一入口；tb_balance 保留 direction v1 借正贷负；损益类取 tb_ledger 发生额；辅助维度按 aux_type 分组读 tb_aux_balance
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ]* 2.4 编写属性测试 P8（引用一律经 ACNR full_resolve）
    - **Property 8: 公式引用一律经 ACNR full_resolve 解析**
    - **Validates: Requirements 5.3, 6.5, 7.4, 11.1, 11.2, 16.3, 17.2**
    - Hypothesis：随机三类型公式 + 有效/悬空引用；桩注入 full_resolve（含抛基础设施异常分支验证 fail-open）
    - 文件：`backend/tests/formula_management/test_pbt_p08_resolve_ref.py`

  - [ ]* 2.5 编写属性测试 P5（logic_check/reasonability 绝不改值）
    - **Property 5: logic_check 与 reasonability 绝不改值**
    - **Validates: Requirements 6.3, 7.3**
    - 文件：`backend/tests/formula_management/test_pbt_p05_no_mutation.py`

  - [ ]* 2.6 编写属性测试 P12（四表库叶子源只读）
    - **Property 12: 四表库叶子源只读**
    - **Validates: Requirements 12.1, 12.2**
    - 文件：`backend/tests/formula_management/test_pbt_p12_readonly.py`

  - [ ]* 2.7 编写属性测试 P13（单条公式失败不阻断批次其余执行）
    - **Property 13: 单条公式失败不阻断批次其余执行**
    - **Validates: Requirements 6.6, 7.5, 15.5, 16.5**
    - 文件：`backend/tests/formula_management/test_pbt_p13_isolation.py`

  - [ ]* 2.8 编写属性测试 P9（auto_calc 成功执行记录最近计算时间）
    - **Property 9: auto_calc 成功执行记录最近计算时间**
    - **Validates: Requirements 5.4, 13.3, 15.3, 16.4, 17.5**
    - 文件：`backend/tests/formula_management/test_pbt_p09_last_computed.py`

- [ ] 3. 底稿 WpFormula 编辑/计算/保存契约扩展
  - [~] 3.1 扩展 WpFormulaService（三类型 + full_resolve 校验 + 跨 sheet）
    - 在 `backend/app/services/wp_formula_service.py` 扩展 `save()`：保持返回 `(WpFormula | None, list[issues])` 契约；持久化 formula_type/target_cell/expression/refs；提交前经 resolve_ref 校验引用，悬空（found=false）→ 返回 `(None, issues)`（router 转 HTTP 422）不写库
    - 跨 sheet 引用经 `CrossSheetResolver` 追溯解析后求值；执行写目标单元 + 记 last_computed_at；支持三类型 category
    - service 只 flush 不 commit
    - _Requirements: 9.1, 9.2, 9.4, 14.1, 14.2, 14.3, 14.4, 14.5_

  - [ ]* 3.2 编写属性测试 P6（公式保存往返字段保真）
    - **Property 6: 公式保存往返字段保真**
    - **Validates: Requirements 9.1, 9.4, 14.1**
    - 文件：`backend/tests/formula_management/test_pbt_p06_save_roundtrip.py`

  - [ ]* 3.3 编写属性测试 P7（悬空引用拒绝保存并返回问题清单）
    - **Property 7: 悬空引用拒绝保存并返回问题清单**
    - **Validates: Requirements 8.4, 9.5, 13.4, 14.4**
    - 文件：`backend/tests/formula_management/test_pbt_p07_dangling_reject.py`

- [ ] 4. logic_check 收编 useReportCrossCheck 7 条勾稽
  - [~] 4.1 落库 7 条勾稽为 logic_check 公式 + 执行端点
    - 新建 `backend/app/services/formula_management/logic_check.py`：把 `useReportCrossCheck` 的 7 条硬编码勾稽（资产=负债+权益、利润总额−所得税=净利润、有效税率≈25% 等）种子为 7 条 logic_check 公式，表达式引用经 ACNR REPORT 域 row_code，问题描述沿用原 description
    - 新增后端 logic_check 执行端点返回 Issue_List（在 router 注册，router 层 commit）
    - 保持勾稽语义不变，仅从"硬编码不可编辑"变为"可编辑 logic_check 公式"
    - _Requirements: 6.4_

  - [ ]* 4.2 编写属性测试 P17（logic_check 收编等价于原硬编码勾稽）
    - **Property 17: logic_check 收编等价于原硬编码勾稽**
    - **Validates: Requirements 6.4**
    - model-based：随机报表数据下，7 条 logic_check 执行结果的 passed 判定与原 `computeCrossCheckResults` 逐条一致
    - 文件：`backend/tests/formula_management/test_pbt_p17_crosscheck_equiv.py`

- [ ] 5. 合伙人一键刷新编排器（Draft Refresh Service）
  - [~] 5.1 实现 precheck 四表库完整度前置校验
    - 新建 `backend/app/services/draft_refresh_service.py`，实现 `precheck(db, *, project_id, year)`：复用 `report_trace.py` 数据完整度前置校验口径，返回 blocking（缺失清单含表名+说明）与 warnings（非阻断告警如个别 aux 缺失）；blocking 非空时不执行任何写入
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [~] 5.2 实现 preview_overwrites 团队编辑清单
    - 实现 `preview_overwrites(db, *, project_id, year, scope)`：返回将被覆盖的人工编辑清单（底稿/单元/editor_id），供合伙人确认
    - _Requirements: 4.3_

  - [~] 5.3 实现 refresh 幂等编排 + Draft 标记 + 审计留痕
    - 实现 `refresh(...)`：① 计算 `tb_snapshot_hash`（四表库快照指纹）→ 命中相同 hash+scope 成功记录则幂等短路；② 未 confirm_overwrite 时仅刷新未被人工编辑单元；③ 覆盖前写 draft_refresh_snapshot 回滚快照；④ 生成初稿写 draft_marker `state='draft'`；⑤ 写不可篡改 draft_refresh_audit（操作者/时间/project_id/year/scope/affected_count）
    - 单元被人工修改时 draft_marker 更新为 `state='human_edited'`
    - service 只 flush，router commit
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.4, 4.6_

  - [~] 5.4 实现 rollback 回滚
    - 实现 `rollback(db, *, refresh_id, operator)`：依据该次刷新的 draft_refresh_snapshot 恢复刷新前数据状态；审计记录标 `result_status='rolled_back'`
    - _Requirements: 4.5_

  - [~] 5.5 施加 require_role 门禁与统一入口
    - 在 `backend/app/routers/wp_render_config.py` 将 `refresh_audit_sheet_from_ledger` 的 `Depends(get_current_user)` 换为 `Depends(require_role(["partner","signing_partner"]))`；detail 补"仅合伙人可触发一键刷新"
    - 新增 `POST /draft-refresh` 统一入口（一次生成未审报表+底稿+附注初稿），同施加 require_role 门禁；使所有一键刷新入口授权语义一致
    - 复用 `deps.py` 的 require_role，不新增并行角色判断
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 5.6 编写属性测试 P1（合伙人门禁授权且拒绝时不写数据）
    - **Property 1: 合伙人门禁授权且拒绝时不写数据**
    - **Validates: Requirements 1.1, 1.2, 1.5**
    - 文件：`backend/tests/formula_management/test_pbt_p01_role_gate.py`

  - [ ]* 5.7 编写属性测试 P2（前置校验阻断残缺数据）
    - **Property 2: 前置校验阻断残缺数据**
    - **Validates: Requirements 2.1, 2.2**
    - 文件：`backend/tests/formula_management/test_pbt_p02_precheck.py`

  - [ ]* 5.8 编写属性测试 P3（一键刷新幂等）
    - **Property 3: 一键刷新幂等**
    - **Validates: Requirements 3.1**
    - 文件：`backend/tests/formula_management/test_pbt_p03_idempotent.py`

  - [ ]* 5.9 编写属性测试 P4（未确认覆盖仅刷新非人工编辑单元）
    - **Property 4: 未确认覆盖仅刷新非人工编辑单元**
    - **Validates: Requirements 3.3, 4.4**
    - 文件：`backend/tests/formula_management/test_pbt_p04_overwrite_guard.py`

  - [ ]* 5.10 编写属性测试 P10（一键刷新回滚往返）
    - **Property 10: 一键刷新回滚往返**
    - **Validates: Requirements 4.2, 4.5**
    - round-trip：rollback(refresh(s)) == s
    - 文件：`backend/tests/formula_management/test_pbt_p10_rollback_roundtrip.py`

  - [ ]* 5.11 编写属性测试 P18（审计留痕完整且不可篡改）
    - **Property 18: 审计留痕完整且不可篡改**
    - **Validates: Requirements 4.1, 4.6**
    - 文件：`backend/tests/formula_management/test_pbt_p18_audit_trail.py`

- [~] 6. Checkpoint - 一键刷新编排器与引擎核心
  - 运行 `python -m pytest backend/tests/formula_management/ -v --tb=short`，确保 P1–P9、P12、P13、P17、P18 全通过；如有疑问询问用户。

- [ ] 7. 审定表回写契约（Adjudication Writeback）
  - [~] 7.1 实现审定表回写 + ACNR 失效链
    - 新建 `backend/app/services/formula_management/adjudication_writeback.py`：`xxx-1` 审定表 auto_calc 公式执行 → 回写 `trial_balance.audited_amount`（仅 audited，不动 unadjusted）；记 last_computed_at；悬空引用拒写返 Issue_List
    - 审定数变更后经 ACNR 失效链触发下游报表/附注失效（复用 ACNR 失效链，不自建）
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

- [ ] 8. 报表引擎契约（增量重算 + 生成）
  - [~] 8.1 实现 generate 报表公式生成契约
    - 在 `backend/app/services/report_engine.py`：`generate_all_reports` 依 TB()/SUM_TB()/ROW()/PREV() 从审定数生成四张报表；`generate_unadjusted_report` 从四表库未审数生成未审报表；ROW() 引用经 resolve_ref（ACNR full_resolve）；每报表单元记来源公式 + last_computed_at；解析失败标注失败行不产空报表
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

  - [~] 8.2 实现 regenerate_affected 调整分录增量重算
    - AJE/RJE 改 aje_adjustment→audited_amount 后，按 changed_accounts 只重算受影响报表行 + ROW() 传递闭包；更新受影响单元 last_computed_at；调整撤销/修改时依最新审定数重算；悬空引用记 Issue_List 并继续重算其余行
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [ ]* 8.3 编写属性测试 P11（增量重算等价于全量重算且非受影响行不变）
    - **Property 11: 增量重算等价于全量重算且非受影响行不变**
    - **Validates: Requirements 15.1, 15.2, 15.4**
    - 文件：`backend/tests/formula_management/test_pbt_p11_incremental_equiv.py`

- [ ] 9. 附注公式执行器协调
  - [~] 9.1 对齐 execute_note_formulas 引用解析与刷新
    - 在 `backend/app/services/note_formula_generator.py`：`execute_note_formulas` 执行 `vertical_sum`/`horizontal_balance`/`book_value`/`cross_table`/`generic` 仅回填 `mode=auto` 单元；跨表 REPORT/TB/NOTE 域引用经 resolve_ref（ACNR full_resolve）；记 evaluated_at；合并附注 reaggregate 后按 addr_id 精准刷新受影响单元
    - 依赖说明：NoteFormulaDialog 的加载/编辑/持久化缺陷修复由 `acnr-consumer-wiring` Req 15 负责，本任务不重写该修复，仅对齐执行器契约
    - _Requirements: 17.1, 17.2, 17.4, 17.5, 17.6_

- [ ] 10. 交付导出契约（公式解析为值 + RFC5987）
  - [~] 10.1 实现导出公式解析为静态值
    - 在 `backend/app/services/word_export.py`（审计报告/财报）与 `report_excel_exporter`：导出前将公式引用解析为当前计算值再输出；产物不保留可重算表达式；悬空引用以最近一次成功计算值（last_computed）导出并在导出日志标注；中文文件名按 RFC 5987 `filename*=UTF-8''` 编码
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5_

  - [ ]* 10.2 编写属性测试 P15（交付导出无残留公式表达式）
    - **Property 15: 交付导出无残留公式表达式**
    - **Validates: Requirements 18.1, 18.2, 18.3**
    - 文件：`backend/tests/formula_management/test_pbt_p15_no_residual_formula.py`

  - [ ]* 10.3 编写属性测试 P16（中文文件名 RFC 5987 编码往返）
    - **Property 16: 中文文件名 RFC 5987 编码往返**
    - **Validates: Requirements 18.5**
    - round-trip：随机含非 ASCII 文件名编码后可解码还原
    - 文件：`backend/tests/formula_management/test_pbt_p16_rfc5987_roundtrip.py`

- [~] 11. Checkpoint - 全链路后端契约
  - 运行 `python -m pytest backend/tests/formula_management/ -v --tb=short` 与相关报表/附注/导出契约测试，确保 P11、P15、P16 及全链路契约通过；如有疑问询问用户。

- [ ] 12. 前端统一公式体验组件
  - [~] 12.1 实现 GtFormulaEditDialog 三类型统一弹窗
    - 新建 `audit-platform/frontend/src/components/formula/GtFormulaEditDialog.vue`：formulaType 选择器（auto_calc/logic_check/reasonability）+ 类型差异字段 v-if 分派（auto_calc：目标单元+表达式；logic_check：条件+问题描述；reasonability：触发条件+提示文案）
    - 引用地址选择接 `acnr-consumer-wiring` Req 14 的 ACNR 选址器（消费其候选地址，不自建）；提交前调 full_resolve，悬空 found=false → 提示且不保存
    - 统一用于底稿/报表/附注三处，收敛现有 6 碎片化组件的编辑体验
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [~] 12.2 实现 GtFormulaSourceTooltip 统一来源提示
    - 新建 `audit-platform/frontend/src/components/formula/GtFormulaSourceTooltip.vue`：虚线下划线 + cursor:help；悬停展示表达式 + 来源地址 + 最近计算时间；来源地址用 full_resolve 返回的 canonical semantic_label（非前端拼接）；未计算过显示"尚未计算"占位
    - 统一挂载到底稿表格/报表/附注三处
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [~] 12.3 实现初稿/已审定区分展示 + Issue/Hint 面板
    - 前端按 draft_marker `state` 区分展示"初稿"与"已审定"；新增 logic_check 问题清单面板与 reasonability 提醒清单面板，消费后端 Issue_List / Hint_List
    - 依赖说明：draft 状态查询与选址器数据源迁移协调 `acnr-consumer-wiring` Req 14
    - _Requirements: 3.5, 6.2, 7.2_

  - [ ]* 12.4 编写 vitest 示例测试（GtFormulaEditDialog）
    - 三类型可选与类型差异字段条件渲染（Req 8.1, 8.2）；选址器数据源为 ACNR（Req 8.3）；悬空提交不保存（Req 8.4）
    - 文件：`audit-platform/frontend/src/components/formula/__tests__/GtFormulaEditDialog.spec.ts`

  - [ ]* 12.5 编写 vitest 示例测试（GtFormulaSourceTooltip，含 P14）
    - **Property 14: 来源提示地址保真（前端侧）**
    - **Validates: Requirements 10.5**
    - 虚线下划线 + cursor:help（Req 10.1）、悬停三要素（Req 10.2）、"尚未计算"占位（Req 10.4）、三处统一挂载（Req 10.3）；tooltip 地址取 full_resolve 返回 semantic_label 而非拼接
    - 文件：`audit-platform/frontend/src/components/formula/__tests__/GtFormulaSourceTooltip.spec.ts`

- [ ] 13. 前端公式引擎治理 + 求值内核收口（Req 19-20）
  - [~] 13.1 建前端公式引擎清单 + 三类型映射元数据
    - 新建 `audit-platform/frontend/src/components/workpaper/composables/formulaEngineInventory.ts`：登记所有 `useXFormulaEngine`/`useXCrossSheet`（useS34FormulaEngine/useD3FormulaEngine/useD3CrossSheet 等），标注三类型映射（createSumFormula/createRatioFormula→auto_calc、createThresholdFormula→reasonability、勾稽→logic_check）与"已接入/待接入"状态
    - 映射为元数据标注，不改变现有计算数值
    - _Requirements: 19.1, 19.2_

  - [~] 13.2 试点接入 useD3FormulaEngine + useS34FormulaEngine（悬停 + ACNR 引用）
    - 试点两引擎：`isFormulaCell` 单元包 `GtFormulaSourceTooltip` 展示表达式+来源；跨表/跨底稿引用经 `useAcnr` 解析（协调 acnr-consumer-wiring Req14），禁前端拼坐标
    - 其余 `useXFormulaEngine` 保留现状（inventory 标待接入，无回归）
    - _Requirements: 19.3, 19.4, 19.5, 19.6_

  - [~] 13.3 求值内核收口 + recalc/一键刷新语义区分
    - 后端求值单一入口收口到 `formula_engine.execute`；将 `formula_parse_utils.evaluate_formula`/`FormulaEvaluator` 的调用方（consol_report_service 18 处）迁移到 L1 内核或 `report_engine.evaluate_formula`；新代码禁并行求值
    - DraftRefreshService 生成初稿后触发受影响单元 recalc/stale 刷新（复用 `prefill_stale`+`/trial-balance/recalc`，不自建）；明确 recalc（团队/不生成初稿/不打 Draft）与一键刷新（合伙人/生成初稿/打 Draft/门禁）语义区分
    - _Requirements: 20.1, 20.2, 20.4, 20.5, 20.6_

  - [ ]* 13.4 编写属性测试 P19/P20/P21
    - **Property 19: 前端引擎三类型映射非破坏计算**（Validates: 19.2, 19.6）— vitest：接入前后引擎产出数值逐一相等
    - **Property 20: 求值内核单一性**（Validates: 20.1, 20.2）— Hypothesis：随机公式经收口路径都委托 L1 内核
    - **Property 21: recalc 与一键刷新语义区分**（Validates: 20.4, 20.6）— recalc 不打 Draft、一键刷新打 Draft，既有公式重算结果一致
    - 文件：`backend/tests/formula_management/test_pbt_p20_single_kernel.py` / `test_pbt_p21_recalc_vs_refresh.py`；前端 `__tests__/formulaEngineInventory.spec.ts`（P19）

  - [~] 13.5 tooltip 收敛（增量）
    - 将散落的 `.formula-cell`+`title="=..."` 内联实现（如 J2TabDetail）逐步替换为统一 `GtFormulaSourceTooltip`；未收敛前保留现状不回归
    - _Requirements: 20.3_

- [ ] 14. 公式预设库 + 导入导出 + 模板库入口（Req 22-25）
  - [~] 14.1 建预设库结构 + Preset Inventory + 覆盖度
    - 新建 `backend/data/formula_presets/inventory.json`（登记每个承载公式页面/sheet：page_key + preset_status + formula_count）+ `formula_presets_seed.json`（预设条目：page_key/target_cell/expression/formula_type/refs(ACNR addr_id)）+ 幂等 seed 脚本（按 page_key+target_cell 去重，遵循 seed_note_account_mappings 模式）
    - 收敛 `prefill_formula_mapping`/`check_presets`/`wide_table_presets` 到预设库口径（适配读取层）；扩展 `get_formula_coverage` 返回 presetted/pending 分布
    - _Requirements: 22.1, 22.3, 22.5, 22.7_

  - [~] 14.2 预设套用到一键刷新/底稿生成
    - DraftRefreshService / 底稿生成按 page_key 查预设库套用为初稿公式；pending 页跳过保留现状（无回归）
    - _Requirements: 22.4, 22.6_

  - [~] 14.3 逐页预设（增量·按循环分批，试点核心页）
    - 按循环/模块逐页读取实际结构预设公式，产出 `formula_presets_seed.json` 分片；试点 D 循环 + 报表 + 附注核心页面；引用一律 ACNR addr_id
    - inventory 标注已预设/待预设，进度可见
    - _Requirements: 22.1, 22.2, 22.6, 22.7_

  - [~] 14.4 公式模块导入导出（导出模板含编报说明）
    - 新建 `useFormulaImportExport` composable + 后端三端点（export-template/export-data/import-data）；前端 `el-dropdown "导入导出▾"`（导出模板/导出数据/导入数据）
    - 导出模板首区块=编报说明（三类型填法/引用格式/注意事项，与说明文档同源）；导入逐条 full_resolve 校验，悬空报告并跳过；http(axios) 带 Authorization + 中文文件名 RFC 5987
    - _Requirements: 23.1, 23.2, 23.3, 23.4, 23.5, 23.6_

  - [~] 14.5 模板库 ACNR 地址坐标名称库更新
    - 模板库预设公式引用改 ACNR addr_id/formula_ref；候选地址经 useAcnr（协调 acnr-consumer-wiring Req14）；纳入 acnr-consumer-wiring Coverage Ledger + drift guard；硬编码旧格式归一化，未迁移项 Ledger 标待迁移
    - _Requirements: 24.1, 24.2, 24.3, 24.4_

  - [~] 14.6 公式预设库入口 + 说明文档弹窗
    - 在 TemplateLibraryButton 所在区（NoteTemplateTab/ReportConfigTab/WpTemplateDetail）加"公式预设库"入口；点击弹 `GtFormulaPresetDialog` 展示公式管理说明文档（单一文档源，与编报说明同源）；可导航到预设浏览/编辑（复用 GtFormulaEditDialog + inventory）；附加入口无回归
    - _Requirements: 25.1, 25.2, 25.3, 25.4, 25.5_

  - [ ]* 14.7 编写属性/单元测试 P22/P23/P24
    - **Property 22: 预设引用 grammar_v1 闭合**（Validates: 22.7, 24.1）— 预设条目引用 full_resolve 可解析或标 pending
    - **Property 23: 导入导出往返 + 编报说明存在**（Validates: 23.2, 23.4）— 导出含编报说明区；导入→导出往返一致；悬空报告不入库
    - **Property 24: 说明文档单一源**（Validates: 23.6, 25.3）— 编报说明与弹窗文档同源不分叉
    - 文件：`backend/tests/formula_management/test_pbt_p22_preset_grammar.py` / `test_pbt_p23_import_export_roundtrip.py`；前端 `__tests__/GtFormulaPresetDialog.spec.ts`（P24）

- [~] 15. 最终 Checkpoint - 全量测试
  - 运行 `python -m pytest backend/tests/formula_management/ -v --tb=short` 与 `npx vitest --run src/components/formula/`，确保 P1–P24 全绿；如有疑问询问用户。

## Notes

- 标 `*` 的子任务为测试类（属性测试/单元/vitest），按约定仍会实现，UI 中可视化区分。
- 属性 P1–P18 一一映射到独立测试子任务，每个属性用单一 property-based 测试实现，测试文件按属性拆分以支持并行执行。
- PBT 后端用 Hypothesis（每属性 ≥100 迭代，CI 快跑档可调 max_examples 但覆盖不减），前端用 vitest；full_resolve 用桩注入（含基础设施异常分支验证 fail-open）。
- 三层一致性：V100 迁移（Task 1.1）+ ORM（Task 1.2）+ service（各引擎/编排任务）必须同步落地。
- 边界协调（引用不重写）：地址解析走 ACNR full_resolve（`acnr` spec）；公式校验路径复用 `acnr-consumer-wiring` Req 9；选址器数据源迁移复用 Req 14；NoteFormulaDialog 加载/编辑/持久化修复复用 Req 15。
- Checkpoint（Task 6/11/13）不纳入依赖图，仅作阶段性验证节点。
- 工程铁律：service 只 flush、router 层 commit；四表库取数经 get_active_filter；中文文件名 RFC 5987 编码；迁移用 IF NOT EXISTS + information_schema 守护幂等。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1", "5.1", "8.1"] },
    { "id": 3, "tasks": ["2.3", "4.1", "5.2", "7.1", "8.2"] },
    { "id": 4, "tasks": ["5.3", "9.1", "10.1", "12.1", "12.2"] },
    { "id": 5, "tasks": ["5.4", "5.5", "12.3"] },
    { "id": 6, "tasks": ["1.3", "2.4", "2.5", "2.6", "2.7", "2.8", "3.2", "3.3", "4.2"] },
    { "id": 7, "tasks": ["5.6", "5.7", "5.8", "5.9", "5.10", "5.11", "8.3", "10.2", "10.3"] },
    { "id": 8, "tasks": ["12.4", "12.5", "13.1", "13.3"] },
    { "id": 9, "tasks": ["13.2", "13.5", "14.1"] },
    { "id": 10, "tasks": ["13.4", "14.2", "14.4", "14.5"] },
    { "id": 11, "tasks": ["14.3", "14.6"] },
    { "id": 12, "tasks": ["14.7"] }
  ]
}
```
