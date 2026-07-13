# Requirements Document

## Introduction

本需求文档定义"公式管理库"的统一治理范围，覆盖公式的**编辑、计算、保存**三大能力，并贯穿审计平台全链路：四表库 → 试算表/审定表 → 底稿 → 调整分录 → 报表 → 附注 → 交付。

平台现状（已用 codegraph 全库核查，见 §溯源）存在三类问题，本 spec 逐一治理、无死角：

1. **一键刷新缺角色门禁**：`backend/app/routers/wp_render_config.py:417-420` 的"一键刷新"从四表库预填审定表/明细表，当前仅 `Depends(get_current_user)`，任何团队成员都可触发，导致互相覆盖初稿且刷完不复核。需收敛为**合伙人专属**（partner / signing_partner），并补齐"初稿(draft)"语义、幂等、前置校验、审计留痕、可回滚与团队编辑区分。
2. **三种公式类型未统一**：自动运算（auto_calc）已实现（WpFormula / ReportEngine / execute_note_formulas）；逻辑判断（logic_check）零散硬编码（`useReportCrossCheck` 7 条勾稽 / balance-check）未作可编辑类型；提示（reasonability/hint）几乎缺失。三类型都需可定义、可弹窗编辑、可保存、可执行、可复用。
3. **前端公式体验碎片化**：6 个公式组件（FormulaRefPicker / FormulaEditDialog / FormulaManagerDialog / FormulaBar / NoteFormulaDialog / CellSelector）交互不一致；公式来源悬停提示仅底稿表格有，报表/附注缺失；`NoteFormulaDialog` 加载/编辑/持久化损坏。

**与 ACNR 的边界（引用而非重写）**：公式引用地址的解析、校验、选址树、失效链统一走 ACNR（地址坐标名称注册中心，见 `.kiro/specs/acnr/`）的 `full_resolve`；公式选址器组件迁移与 `NoteFormulaDialog` 加载/编辑/持久化修复已在 `.kiro/specs/acnr-consumer-wiring/` 的 Requirement 14 / Requirement 15 中定义。本 spec **聚焦公式管理三能力（编辑/计算/保存）的语义统一与全链路契约**，对上述地址解析与组件 wiring 采取**引用协调**，不重复造轮子。

**技术栈**：Python 后端（FastAPI + asyncpg + SQLAlchemy）+ TypeScript/Vue 前端（Element Plus）。

---

## 本次修订说明（编号厘清 + P0/P1 缺口补齐）

> 本 spec 经多轮追加后，**Req 19-25 曾存在三套语义冲突的定义**（主序列 = 勾选弹窗/Module_Refresh/作用域过滤/公式三来源/三能力显式化；"深化核验补充" = 前端引擎治理/内核收口；"预设库补充" = 预设库/导入导出/模板库入口），且 tasks.md Task13/14 又按第四套编号（Req19-20=前端引擎治理、Req22-25=预设库四件），导致 design §13-15 那批（Refresh_Scope_Dialog / 全局公式页 / 公式三来源）从未变成任务、从未实现。
>
> 本次修订将全部真实特性**重排为单一自洽序列（Req 1-32），每条需求语义唯一、不重复**，并为每条标注实现状态。后续 design.md / tasks.md 阶段将按本编号对齐（本次仅改 requirements.md）。

### 需求编号总览（实现状态）

| 编号 | 需求 | 实现状态 |
|------|------|----------|
| Req 1 | 全局一键刷新合伙人角色门禁（分层刷新权限） | ✅ 已实现 |
| Req 2 | 一键刷新前置校验四表库完整度 | ✅ 已实现 |
| Req 3 | 一键刷新幂等与初稿语义标记 | ✅ 已实现 |
| Req 4 | 一键刷新审计留痕与团队编辑区分 | ✅ 已实现 |
| Req 5 | 自动运算（auto_calc）公式类型 | ✅ 已实现 |
| Req 6 | 逻辑判断（logic_check）公式类型 | ✅ 已实现（后端；前端消费见 Req 23） |
| Req 7 | 提示（reasonability）公式类型 | ✅ 已实现 |
| Req 8 | 三类型公式统一弹窗编辑 | ✅ 已实现 |
| Req 9 | 公式保存与复用 | ✅ 已实现 |
| Req 10 | 公式来源悬停显示统一 | ✅ 已实现 |
| Req 11 | 公式引用地址解析走 ACNR full_resolve | ✅ 已实现 |
| Req 12 | 四表库取数契约（叶子源只读） | ✅ 已实现 |
| Req 13 | 审定表回写契约 | ✅ 已实现 |
| Req 14 | 底稿 WpFormula 编辑/计算/保存契约 | ✅ 已实现 |
| Req 15 | 调整分录触发报表增量重算契约 | ✅ 已实现 |
| Req 16 | 报表公式生成契约 | ✅ 已实现 |
| Req 17 | 附注公式回填契约与 NoteFormulaDialog 修复协调 | ✅ 已实现 |
| Req 18 | 交付导出公式解析为值契约 | ✅ 已实现 |
| Req 19 | 合伙人全局刷新勾选弹窗（前端入口） | 🔴 待实现（P0） |
| Req 20 | 全局刷新范围动态发现（Refresh_Scope_Discovery） | 🔴 待实现（P1） |
| Req 21 | 全局刷新按勾选范围编排生成初稿 | 🔴 待实现（P0·核心） |
| Req 22 | 模块/循环级局部刷新对其他角色开放 | ✅ 已实现 |
| Req 23 | 报表勾稽前端消费后端 logic_check（收编闭环） | 🔴 待实现（P1） |
| Req 24 | 公式作用域过滤与全局公式管理页 | 🔴 待实现 |
| Req 25 | 公式三来源（预设 / 自定义 / 参照已有） | 🟡 部分实现（数据模型就绪，来源消费/参照失效链待接） |
| Req 26 | 公式三能力显式化（可视化 / 可编辑保存 / 可运算刷新） | ✅ 已实现（派生自 Req 5-10） |
| Req 27 | 前端 per-cycle 公式引擎纳入三类型治理（增量） | 🟡 部分实现（试点 D3/S34，其余增量推进） |
| Req 28 | 求值内核收口 + 悬停 tooltip 收敛 + recalc 衔接 | ✅ 已实现（tooltip 增量收敛） |
| Req 29 | 公式预设库（逐页分析 + 预设，作为公式库一部分） | 🟡 部分实现（groundwork 就绪，逐页预设增量推进） |
| Req 30 | 公式模块导入导出（导出模板含编报说明） | ✅ 已实现 |
| Req 31 | 模板库 ACNR 地址坐标名称库更新 | ✅ 已实现 |
| Req 32 | 公式预设库入口 + 公式管理说明文档弹窗 | ✅ 已实现 |

> P0/P1 缺口（Req 19-21、Req 23、及 Req 29 的"全局刷新消费预设"部分）均已用实读代码确认：`draft_refresh.py` 的 `/draft-refresh` 调 `DraftRefreshService.refresh()` 时不传 `units`、不调 `refresh_with_presets`、不传 `page_keys`、不调用报表引擎/审定表回写/附注生成器 → 合伙人触发全局刷新只写审计、affected_count=0、零初稿；前端无 `GtRefreshScopeDialog.vue`、无任何组件调 `/draft-refresh`；`RefreshScopeDiscovery` 未实现（scopes 仅字符串透传）；前端 `useReportCrossCheck.ts` 仍硬编码纯函数、从不消费后端 logic_check 端点。

## Glossary

- **公式管理库 (Formula_Management_Library)**：统一治理公式编辑/计算/保存三能力及其全链路契约的功能域。
- **四表库 (Four_Table_Store)**：`trial_balance` / `tb_balance` / `tb_ledger` / `tb_aux_balance` 四张表，公式取数的叶子源，被 `TB()` / `PREV()` / `AUX()` 读取，无公式编辑能力。
- **未审数 (Unadjusted_Amount)**：`trial_balance.unadjusted_amount`，四表库直接导入的未经审计调整的数据。
- **审定数 (Audited_Amount)**：`trial_balance.audited_amount`，报表/审定表取数的权威字段。
- **一键刷新服务 (Draft_Refresh_Service)**：基于四表库未审数一键生成初稿（未审报表/底稿/附注等）的服务，当前入口在 `wp_render_config.py` 与 `draft_refresh.py`。
- **初稿 (Draft)**：由一键刷新生成、尚未经人工复核的数据状态语义标记。
- **初稿单元 (Draft_Unit)**：由一键刷新按范围实际生成并落库的一个数据/公式单元（报表行、审定表回写项、底稿单元或附注单元），带 Draft 标记与最近计算时间。
- **合伙人 (Partner_Role)**：角色 `partner` 或 `signing_partner`；全局一键刷新的唯一授权触发者。
- **角色门禁 (Role_Gate)**：基于 `require_role`（`backend/app/deps.py:125`）的角色准入校验机制。
- **编辑权门禁 (Edit_Permission_Gate)**：基于 `require_wp_edit_permission`（`deps.py`，依据 `permission_service.Permission.WORKPAPER_WRITE` 与 `project_assignments.staff_id`）的按项目成员编辑权准入机制，用于 Module_Refresh。
- **前置校验 (Precheck)**：一键刷新执行前对四表库数据完整度的校验，参考 `report_trace.py` 的子公司数据完整度前置校验。
- **公式类型 (Formula_Type)**：`auto_calc`（自动运算，计算并回填值）、`logic_check`（逻辑判断，产出问题清单不改值）、`reasonability`（提示/合理性，产出提醒不改值）三类。
- **公式引擎 (Formula_Engine)**：执行公式求值/校验的后端引擎（`formula_engine` / `ReportFormulaParser` / `execute_note_formulas` 等）。
- **公式编辑弹窗 (Formula_Edit_Dialog)**：前端统一的三类型公式弹窗编辑界面（收敛现有 6 个碎片化组件的编辑体验）。
- **公式来源提示 (Formula_Source_Tooltip)**：鼠标悬停显示公式表达式、来源、最近计算时间的 UI（虚线下划线 + `cursor:help` + tooltip）。
- **WpFormula**：底稿自定义单元格公式实体（`backend/app/services/wp_formula_service.py`），`save` 返回 `(WpFormula | None, list[issues])`。
- **审定表回写 (Adjudication_Writeback)**：审定表（`xxx-1`）公式回写 `trial_balance.audited_amount` 的动作。
- **报表引擎 (Report_Engine)**：`ReportEngine`（`backend/app/services/report_engine.py`），执行 `TB()`/`SUM_TB()`/`ROW()`/`PREV()` 生成四张报表；`generate_unadjusted_report` 从四表未审数生成未审报表。
- **附注公式执行器 (Note_Formula_Executor)**：`execute_note_formulas`（`backend/app/services/note_formula_generator.py:314`），执行 `vertical_sum`/`horizontal_balance`/`book_value`/`cross_table`/`generic` 类公式。
- **交付导出器 (Delivery_Exporter)**：`word_export`（审计报告/财报）+ `report_excel_exporter`（审定/未审导出），导出时将公式解析为值。
- **ACNR**：地址坐标名称注册中心（`.kiro/specs/acnr/`）；公式引用地址的统一解析真源。
- **full_resolve**：ACNR 统一解析入口，输入 formula_ref 返回 canonical addr_id + 物理格 + 是否命中。
- **问题清单 (Issue_List)**：logic_check 类公式产出的勾稽/校验不通过项集合，不修改任何数据值。
- **提醒清单 (Hint_List)**：reasonability 类公式产出的合理性提醒集合，不修改任何数据值。
- **审计留痕 (Audit_Trail)**：记录操作者身份、时间、触发范围、影响结果的不可篡改日志。
- **全局一键刷新 (Global_Refresh)**：合伙人专属的跨模块整体刷新入口（`/draft-refresh`），带勾选弹窗按选定范围批量刷数。
- **模块/循环级刷新 (Module_Refresh)**：模块或循环内的局部刷新入口，如 `audit-sheet-refresh`（`wp_render_config.py:414 refresh_audit_sheet_from_ledger`，逐底稿从四表库/辅助余额刷新）、报表模块内刷新、D 类底稿某循环的一键刷新；对项目内有编辑权的角色开放。
- **全局刷新勾选弹窗 (Refresh_Scope_Dialog)**：合伙人点击全局一键刷新后弹出的页面弹窗，列出可刷新内容分类供合伙人自行勾选子集，按勾选范围执行。
- **刷新范围项 (Refresh_Scope_Item)**：Refresh_Scope_Dialog 中的一个可勾选刷新分类（如报表、底稿按循环、调整分录、附注），来源应可发现而非硬编码。
- **刷新范围发现 (Refresh_Scope_Discovery)**：从平台既有模块注册 + `cycleDialogRegistry` 循环集合 + `wp_index` 循环前缀动态发现可刷新范围项的服务，供弹窗与后端共用。
- **公式作用域 (Formula_Scope)**：`FormulaManagerScope` 的 7 类页面作用域 `note` / `consol_note` / `consol_worksheet` / `consol_report` / `report` / `tb` / `workpaper`，标识公式所属页面类别；`SCOPE_LABEL_MAP` 提供中文标签。
- **全局公式管理页 (Global_Formula_Page)**：跨作用域展示全部公式的公式管理界面（`FormulaManagerDialog.vue` 树形导航 selectedNodeKey/selectedPath），可浏览所有 Formula_Scope。
- **公式来源 (Formula_Source)**：一条公式的来源方式，分为 `preset`（一键预设）、`custom`（自定义编辑）、`reference`（参照其他已保存公式）三类。
- **预设公式库 (Preset_Formula_Library)**：平台内置的预设公式集合（`check_presets` / 预设库 / `build_preset_draft_units` / `refresh_with_presets`），供一键套用（preset 来源）。
- **参照已有公式 (Reference_Existing)**：复用另一条已保存公式的表达式/定义作为新公式来源（reference 来源）。
- **用户自定义公式 (User_Formula)**：底稿单元的用户覆盖公式（`user_formulas`，`wp_user_formulas.py`），实体含 `cell_key` / `formula` / `formula_type` / `is_preset_override` / `edited_at`，支持恢复预设（restore preset）语义。
- **报表跨表勾稽 (Report_Cross_Check)**：报表页面的 7 条跨表勾稽校验，前端 `useReportCrossCheck.computeCrossCheckResults` 硬编码实现，后端已落库为可编辑 logic_check 公式并提供执行端点。

## Requirements

---

### Requirement 1: 全局一键刷新合伙人角色门禁（分层刷新权限）

> **实现状态**：✅ 已实现（`/draft-refresh` 施加 `require_role(partner/signing_partner)`；模块级 `audit-sheet-refresh` 施加 `require_wp_edit_permission`）。

**User Story:** 作为业务合伙人，我想让"全局一键刷新数据"仅合伙人可触发，以便避免团队每个人各自全局刷新后互相覆盖初稿且刷完无人复核；同时不锁死模块内的局部刷新，让其他角色仍能在自己负责的模块/循环内局部刷新。

#### Acceptance Criteria

1. WHEN 用户调用全局一键刷新接口（Global_Refresh，`/draft-refresh`）, THE Draft_Refresh_Service SHALL 通过 Role_Gate 校验调用者角色是否属于 {partner, signing_partner}。
2. IF 调用者角色不属于 {partner, signing_partner} 且调用的是 Global_Refresh 入口, THEN THE Draft_Refresh_Service SHALL 返回 HTTP 403 并附带提示"仅合伙人可触发全局一键刷新"，且不执行任何数据写入。
3. THE Draft_Refresh_Service SHALL 复用 `backend/app/deps.py` 的 `require_role` 机制实现角色门禁，而非新增并行的角色判断逻辑。
4. WHEN Global_Refresh 入口收到合法合伙人调用, THE Draft_Refresh_Service SHALL 依据合伙人在全局刷新勾选弹窗（Requirement 19）选定的范围，执行从四表库未审数预填审定表/明细表/初稿的流程（生成契约见 Requirement 21）。
5. THE Role_Gate 的合伙人限制 SHALL 仅适用于 Global_Refresh 入口；模块/循环级局部刷新入口（Module_Refresh，如 `audit-sheet-refresh` 逐底稿刷新、报表模块内刷新、D 类底稿某循环的一键刷新）的授权由 Requirement 22 定义，不受合伙人限制，避免模块级刷新被一并锁死。

---

### Requirement 2: 一键刷新前置校验四表库完整度

> **实现状态**：✅ 已实现（`DraftRefreshService.precheck` 复用 `report_trace.py` 口径，返回 blocking/warnings）。

**User Story:** 作为业务合伙人，我想在生成初稿前先校验四表库数据完整度，以便避免基于残缺数据生成错误初稿。

#### Acceptance Criteria

1. WHEN 合伙人触发一键刷新, THE Precheck SHALL 在执行数据写入前校验四表库（trial_balance / tb_balance / tb_ledger / tb_aux_balance）在目标 project_id 与 year 下的数据完整度。
2. IF 四表库缺少目标 project_id 与 year 的必需数据, THEN THE Precheck SHALL 阻止刷新并返回缺失项清单（含表名与缺失说明），且不执行任何数据写入。
3. THE Precheck SHALL 复用 `report_trace.py` 中已有的数据完整度前置校验逻辑作为实现参考，保持校验口径一致。
4. WHEN Precheck 全部通过, THE Draft_Refresh_Service SHALL 继续执行初稿生成流程。
5. WHERE 四表库数据完整但存在非阻断性告警（如个别辅助维度缺失）, THE Precheck SHALL 在响应中返回告警清单并允许合伙人继续执行刷新。

---

### Requirement 3: 一键刷新幂等与初稿语义标记

> **实现状态**：✅ 已实现（`refresh` 计 `tb_snapshot_hash` 幂等短路 + `draft_marker` 状态标记）。

**User Story:** 作为业务合伙人，我想让重复触发一键刷新产生一致结果并明确标记初稿状态，以便区分自动初稿与人工审定内容。

#### Acceptance Criteria

1. WHEN 合伙人在同一 project_id 与 year 下以相同四表库快照重复触发一键刷新, THE Draft_Refresh_Service SHALL 产生与首次执行等价的结果（幂等）。
2. WHEN Draft_Refresh_Service 生成初稿数据, THE Draft_Refresh_Service SHALL 为生成的记录写入 Draft 语义标记（标识数据来源为自动初稿、未经人工复核）。
3. WHERE 某数据单元已被标记为人工编辑, THE Draft_Refresh_Service SHALL 依据 Requirement 4 的团队编辑区分规则决定是否覆盖，而非无条件覆盖。
4. WHEN 初稿数据被人工修改, THE Formula_Management_Library SHALL 将该数据单元的 Draft 标记更新为已人工介入状态。
5. THE Draft_Refresh_Service SHALL 使 Draft 语义标记可被前端查询，以便界面区分展示"初稿"与"已审定"数据。

---

### Requirement 4: 一键刷新审计留痕与团队编辑区分

> **实现状态**：✅ 已实现（`draft_refresh_audit` append-only + `draft_refresh_snapshot` 回滚快照 + `preview_overwrites`）。

**User Story:** 作为质量控制复核合伙人，我想让每次一键刷新都留痕并可回滚，且能区分被覆盖的团队编辑，以便追溯责任并避免误删团队成果。

#### Acceptance Criteria

1. WHEN 合伙人成功执行一键刷新, THE Audit_Trail SHALL 记录操作者身份、操作时间、目标 project_id 与 year、触发范围与受影响记录数。
2. WHEN 一键刷新即将覆盖已存在的人工编辑数据, THE Draft_Refresh_Service SHALL 在覆盖前将被覆盖内容纳入可回滚快照。
3. WHERE 存在将被覆盖的团队人工编辑, THE Draft_Refresh_Service SHALL 在执行前向合伙人返回受影响的人工编辑清单（含底稿/单元与编辑者标识），供合伙人确认。
4. IF 合伙人未确认覆盖团队人工编辑, THEN THE Draft_Refresh_Service SHALL 保留既有人工编辑数据、仅刷新未被人工编辑的数据单元。
5. WHEN 合伙人请求回滚某次一键刷新, THE Draft_Refresh_Service SHALL 依据该次刷新的可回滚快照恢复刷新前的数据状态。
6. THE Audit_Trail SHALL 使一键刷新记录不可被普通用户删除或篡改。

---

### Requirement 5: 自动运算（auto_calc）公式类型

> **实现状态**：✅ 已实现（`formula_management/engine.py:execute_formula` auto_calc 分派回填 + `last_computed_at`）。

**User Story:** 作为审计助理，我想定义并执行自动运算公式，以便系统自动计算并回填数值单元。

#### Acceptance Criteria

1. THE Formula_Management_Library SHALL 支持 auto_calc 公式类型的定义，包含目标单元、表达式与所属公式类型标识。
2. WHEN auto_calc 公式被执行, THE Formula_Engine SHALL 依表达式求值并将结果回填到目标单元。
3. WHEN auto_calc 公式引用其他地址, THE Formula_Engine SHALL 通过 ACNR full_resolve 解析引用地址后再取值。
4. WHEN auto_calc 公式执行完成, THE Formula_Engine SHALL 记录该公式的最近计算时间。
5. IF auto_calc 表达式求值失败, THEN THE Formula_Engine SHALL 返回描述性错误并保留目标单元原值不变。

---

### Requirement 6: 逻辑判断（logic_check）公式类型

> **实现状态**：✅ 已实现（后端 `logic_check.py` 收编 7 条勾稽为可编辑公式 + 执行端点）；前端消费闭环见 Requirement 23。

**User Story:** 作为现场经理，我想定义可编辑的逻辑判断公式，以便统一管理勾稽校验并产出问题清单而不改动数据值。

#### Acceptance Criteria

1. THE Formula_Management_Library SHALL 支持 logic_check 公式类型的定义，包含判断条件表达式与不通过时的问题描述。
2. WHEN logic_check 公式被执行, THE Formula_Engine SHALL 对条件表达式求值并在条件不通过时向 Issue_List 追加一条问题项。
3. THE Formula_Engine SHALL 在执行 logic_check 公式时不修改任何数据单元的值。
4. WHEN 现有硬编码勾稽规则（如 `useReportCrossCheck` 的 7 条勾稽 / balance-check）被纳入治理, THE Formula_Management_Library SHALL 将其表达为可编辑的 logic_check 公式，使勾稽规则可在弹窗中查看与编辑。
5. WHEN logic_check 公式引用其他地址, THE Formula_Engine SHALL 通过 ACNR full_resolve 解析引用地址后再求值。
6. IF logic_check 条件表达式无法求值, THEN THE Formula_Engine SHALL 向 Issue_List 追加一条标注"公式无法求值"的问题项，而非静默跳过。

---

### Requirement 7: 提示（reasonability）公式类型

> **实现状态**：✅ 已实现（`execute_formula` reasonability 分派产 Hint_List 不改值）。

**User Story:** 作为审计助理，我想定义合理性提示公式，以便在数值可疑时收到提醒而不强制阻断或改值。

#### Acceptance Criteria

1. THE Formula_Management_Library SHALL 支持 reasonability 公式类型的定义，包含提示触发条件与提示文案。
2. WHEN reasonability 公式被执行且触发条件成立, THE Formula_Engine SHALL 向 Hint_List 追加一条提醒项。
3. THE Formula_Engine SHALL 在执行 reasonability 公式时不修改任何数据单元的值。
4. WHEN reasonability 公式引用其他地址, THE Formula_Engine SHALL 通过 ACNR full_resolve 解析引用地址后再求值。
5. IF reasonability 触发条件无法求值, THEN THE Formula_Engine SHALL 记录一条告警日志并跳过该提示，且不中断其他公式执行。

---

### Requirement 8: 三类型公式统一弹窗编辑

> **实现状态**：✅ 已实现（`GtFormulaEditDialog.vue` 三类型 v-if 分派 + FormulaRefPicker 选址 + 提交 full_resolve 悬空拦截）。

**User Story:** 作为审计助理，我想在统一的弹窗界面编辑三类公式，以便无需在碎片化组件间切换即可完成编辑。

#### Acceptance Criteria

1. THE Formula_Edit_Dialog SHALL 支持在同一弹窗界面创建与编辑 auto_calc、logic_check、reasonability 三种公式类型。
2. WHEN 用户在 Formula_Edit_Dialog 选择公式类型, THE Formula_Edit_Dialog SHALL 展示与该类型对应的编辑字段（auto_calc：目标单元+表达式；logic_check：条件+问题描述；reasonability：条件+提示文案）。
3. WHEN 用户在 Formula_Edit_Dialog 选择引用地址, THE Formula_Edit_Dialog SHALL 依据 `.kiro/specs/acnr-consumer-wiring/` Requirement 14 的公式选址器从 ACNR 数据源取候选地址。
4. WHEN 用户提交公式编辑, THE Formula_Edit_Dialog SHALL 先通过 ACNR full_resolve 校验引用地址，IF 引用地址为悬空（found=false）THEN THE Formula_Edit_Dialog SHALL 向用户提示悬空引用且不保存。
5. THE Formula_Edit_Dialog SHALL 统一到底稿、报表、附注三处使用，使三处编辑三类公式的交互一致。

---

### Requirement 9: 公式保存与复用

> **实现状态**：✅ 已实现（`WpFormulaService.save` 保持 `(WpFormula|None, list[issues])` 契约 + service flush/router commit）。

**User Story:** 作为现场经理，我想保存已定义的公式并在其他底稿复用，以便相同勾稽/计算逻辑不必重复编写。

#### Acceptance Criteria

1. WHEN 用户保存一条公式, THE Formula_Management_Library SHALL 持久化该公式的目标单元、表达式、公式类型与引用地址。
2. THE Formula_Management_Library SHALL 遵循"service 只 flush 不 commit、router 层 commit"的既有约定持久化公式。
3. WHEN 用户在另一底稿引用一条已保存的公式, THE Formula_Management_Library SHALL 允许复用该公式定义而无需重新录入表达式。
4. WHEN 公式保存成功, THE Formula_Management_Library SHALL 返回可供前端回显的公式标识与最新表达式。
5. IF 公式保存时引用地址校验失败, THEN THE Formula_Management_Library SHALL 返回 HTTP 422 与问题清单，保持 `WpFormulaService.save` 的 `(None, issues)` 契约不变。

---

### Requirement 10: 公式来源悬停显示统一

> **实现状态**：✅ 已实现（`GtFormulaSourceTooltip.vue` 虚线下划线 + cursor:help + semantic_label 懒解析 + "尚未计算"占位）。

**User Story:** 作为审计助理，我想将鼠标悬停到公式单元上查看公式来源，以便在底稿、报表、附注任意位置都能追溯取数逻辑。

#### Acceptance Criteria

1. WHERE 某单元由公式产生, THE Formula_Source_Tooltip SHALL 以虚线下划线加 `cursor:help` 样式标识该单元。
2. WHEN 用户将鼠标悬停到公式单元, THE Formula_Source_Tooltip SHALL 显示该公式的表达式、来源地址与最近计算时间。
3. THE Formula_Source_Tooltip SHALL 统一应用到底稿表格、报表与附注三处，使三处公式来源展示一致。
4. WHERE 公式尚未执行过（无最近计算时间）, THE Formula_Source_Tooltip SHALL 显示"尚未计算"占位而非空白。
5. THE Formula_Source_Tooltip 显示的来源地址 SHALL 使用 ACNR full_resolve 返回的规范地址名称，而非前端自行拼接的坐标字符串。

---

### Requirement 11: 公式引用地址解析走 ACNR full_resolve

> **实现状态**：✅ 已实现（`engine.py:resolve_ref` 封装 full_resolve + fail-open 回退）。

**User Story:** 作为公式管理库开发者，我想让所有公式引用地址都经 ACNR full_resolve 解析，以便公式寻址与平台其余部分共用单一权威解析器。

#### Acceptance Criteria

1. WHEN Formula_Engine 需要解析公式引用地址, THE Formula_Engine SHALL 调用 ACNR full_resolve 获取 canonical addr_id 与物理格。
2. WHEN full_resolve 返回 found=true, THE Formula_Engine SHALL 使用返回的 canonical addr_id 作为引用身份。
3. IF full_resolve 因基础设施不可用而抛出异常, THEN THE Formula_Engine SHALL 记录告警并回退到既有解析路径（fail-open），不因解析器故障阻断公式执行。
4. THE Formula_Management_Library SHALL 复用 `.kiro/specs/acnr-consumer-wiring/` Requirement 9 定义的 ACNR 校验路径进行公式引用校验，而非新增并行校验实现。
5. THE Formula_Management_Library SHALL NOT 在公式引用中拼接 `wp_code + sheet + cell` 裸字符串，而通过 addr_id 或 formula_ref 引用地址。

---

### Requirement 12: 四表库取数契约（叶子源只读）

> **实现状态**：✅ 已实现（`four_table_source.py` 叶子源只读守卫 + TB/PREV/AUX 取数契约）。

**User Story:** 作为公式管理库开发者，我想明确四表库作为公式取数叶子源且不可经公式编辑，以便取数口径统一且原始数据不被公式污染。

#### Acceptance Criteria

1. WHEN 公式经 `TB()` / `PREV()` / `AUX()` 从四表库取数, THE Formula_Engine SHALL 通过 `get_active_filter` 统一入口读取，而非裸写 `is_deleted==False`。
2. THE Formula_Management_Library SHALL NOT 允许对四表库（trial_balance / tb_balance / tb_ledger / tb_aux_balance）单元定义回填型（auto_calc）公式。
3. WHEN 公式从 tb_balance 取数, THE Formula_Engine SHALL 保留借贷方向（direction）字段口径（v1 借正贷负），使备抵类科目取数不失真。
4. WHEN 公式取损益类科目, THE Formula_Engine SHALL 从 tb_ledger 取发生额，而非期末余额。
5. WHEN 公式取辅助维度数据, THE Formula_Engine SHALL 按 aux_type 分组读取 tb_aux_balance，避免维度冗余重复计数。

---

### Requirement 13: 审定表回写契约

> **实现状态**：✅ 已实现（`adjudication_writeback.py` 回写 audited_amount + ACNR 失效链）。

**User Story:** 作为审计助理，我想让审定表公式将结果回写 audited_amount，以便审定数成为报表取数的权威来源。

#### Acceptance Criteria

1. WHEN 审定表（`xxx-1`）的 auto_calc 公式执行, THE Adjudication_Writeback SHALL 将结果回写到 `trial_balance.audited_amount`。
2. THE Adjudication_Writeback SHALL 仅回写审定表对应科目的 audited_amount，而不修改 unadjusted_amount。
3. WHEN 审定表回写完成, THE Formula_Management_Library SHALL 记录该次回写的最近计算时间供 Formula_Source_Tooltip 展示。
4. IF 审定表公式引用地址悬空, THEN THE Adjudication_Writeback SHALL 拒绝回写并返回问题清单。
5. WHEN 审定数发生回写变更, THE Formula_Management_Library SHALL 触发依赖该审定数的下游（报表/附注）失效，复用 ACNR 失效链而非自建失效逻辑。

---

### Requirement 14: 底稿 WpFormula 编辑/计算/保存契约

> **实现状态**：✅ 已实现（`WpFormulaService` 扩展三类型 + full_resolve 校验 + CrossSheetResolver 跨 sheet）。

**User Story:** 作为审计助理，我想在底稿中编辑自定义单元格公式并跨 sheet 追溯求值，以便底稿计算逻辑可维护且可校验。

#### Acceptance Criteria

1. WHEN 用户保存一条 WpFormula, THE WpFormula SHALL 经 full-resolve 校验后持久化，保持 `WpFormulaService.save` 返回 `(WpFormula | None, list[issues])` 的契约。
2. WHEN WpFormula 引用其他 sheet 的单元, THE Formula_Engine SHALL 经跨 sheet 追溯解析引用链后再求值。
3. WHEN WpFormula 被执行, THE Formula_Engine SHALL 将求值结果写入底稿目标单元并记录最近计算时间。
4. IF WpFormula 引用地址悬空（full_resolve found=false）, THEN THE WpFormula SHALL 拒绝保存并返回问题清单（HTTP 422）。
5. THE WpFormula SHALL 支持 auto_calc、logic_check、reasonability 三种公式类型的 category 标识，使底稿单元可承载三类公式。

---

### Requirement 15: 调整分录触发报表增量重算契约

> **实现状态**：✅ 已实现（`ReportEngine.regenerate_affected` 按 changed_accounts 增量重算 + 悬空记 Issue 续算）。

**User Story:** 作为审计助理，我想让调整分录（AJE/RJE）自动触发受影响报表增量重算，以便调整后报表与底稿保持一致。

#### Acceptance Criteria

1. WHEN 调整分录（AJE/RJE）修改 `aje_adjustment` 进而影响 `audited_amount`, THE Report_Engine SHALL 增量重算受影响的报表（regenerate_affected），而非全量重算。
2. THE Report_Engine SHALL 仅重算引用了变更审定数的报表行，未受影响的报表行保持不变。
3. WHEN 增量重算执行, THE Report_Engine SHALL 更新受影响报表单元的最近计算时间。
4. WHEN 调整分录被撤销或修改, THE Report_Engine SHALL 依据变更后的审定数重新触发增量重算，使报表反映最新调整。
5. IF 增量重算过程中某报表公式引用地址悬空, THEN THE Report_Engine SHALL 记录该悬空引用到 Issue_List 并继续重算其余报表单元。

---

### Requirement 16: 报表公式生成契约

> **实现状态**：✅ 已实现（`generate_all_reports` / `generate_unadjusted_report` ROW 经 resolve_ref + 失败标注行不产空报表）。

**User Story:** 作为审计助理，我想让报表引擎依公式生成审定报表与未审报表，以便四张报表由公式统一驱动。

#### Acceptance Criteria

1. WHEN Report_Engine 执行 `generate_all_reports`, THE Report_Engine SHALL 依 `TB()`/`SUM_TB()`/`ROW()`/`PREV()` 公式从审定数生成四张报表。
2. WHEN Report_Engine 执行 `generate_unadjusted_report`, THE Report_Engine SHALL 从四表库未审数生成未审报表。
3. WHEN 报表公式引用其他报表行, THE Report_Engine SHALL 经 ACNR full_resolve 解析 `ROW()` 引用后再取值。
4. THE Report_Engine SHALL 为每个报表单元记录其来源公式与最近计算时间，供 Formula_Source_Tooltip 在报表处展示。
5. IF 报表公式解析失败, THEN THE Report_Engine SHALL 返回描述性错误并标注失败的报表行，而非产出空报表。

---

### Requirement 17: 附注公式回填契约与 NoteFormulaDialog 修复协调

> **实现状态**：✅ 已实现（`execute_note_formulas` 对齐 resolve_ref + `note:{section}!{r}:{c}` addr_id + reaggregate 精准刷新；NoteFormulaDialog 修复引用 acnr-consumer-wiring Req 15）。

**User Story:** 作为附注编制人，我想让附注公式正确执行并回填 auto 单元，且附注公式管理弹窗能加载与保存编辑，以便附注取数可维护、编辑不丢失。

#### Acceptance Criteria

1. WHEN Note_Formula_Executor 执行附注公式, THE Note_Formula_Executor SHALL 执行 `vertical_sum` / `horizontal_balance` / `book_value` / `cross_table` / `generic` 类公式并仅回填 `mode=auto` 的单元。
2. WHEN 附注公式跨表引用 REPORT / TB / NOTE 域, THE Note_Formula_Executor SHALL 经 ACNR full_resolve 解析引用地址后再取值。
3. THE Formula_Management_Library SHALL 依据 `.kiro/specs/acnr-consumer-wiring/` Requirement 15 修复 NoteFormulaDialog 的加载/编辑/持久化缺陷（当前 formulas 空 ref 从不加载、编辑不持久化、onApply 从 check_presets 重生成丢编辑），而非在本 spec 重写该修复。
4. WHEN 用户在附注公式弹窗保存编辑, THE Formula_Management_Library SHALL 持久化编辑后的公式集并使其在弹窗关闭后重开仍存在。
5. WHEN 附注公式回填完成, THE Note_Formula_Executor SHALL 记录该附注单元的最近计算时间供 Formula_Source_Tooltip 展示。
6. WHEN 合并附注需要重聚合（reaggregate）, THE Note_Formula_Executor SHALL 在重聚合后按 addr_id 精准刷新受影响的附注单元。

---

### Requirement 18: 交付导出公式解析为值契约

> **实现状态**：✅ 已实现（`delivery_export.py` 公式→静态值 + `content_disposition_attachment` RFC5987 单一 helper）。

**User Story:** 作为业务合伙人，我想让交付导出时公式被解析为静态值，以便交付的审计报告与财报不含可变公式引用。

#### Acceptance Criteria

1. WHEN Delivery_Exporter 导出审计报告或财报（word_export）, THE Delivery_Exporter SHALL 将文档中的公式引用解析为当前计算值后再输出。
2. WHEN Delivery_Exporter 导出审定/未审报表（report_excel_exporter）, THE Delivery_Exporter SHALL 将报表公式解析为值后写入导出文件。
3. THE Delivery_Exporter SHALL NOT 在交付产物中保留可被下游重新求值的公式表达式。
4. IF 导出时某公式单元引用地址悬空, THEN THE Delivery_Exporter SHALL 以最近一次成功计算值导出并在导出日志中标注该悬空引用。
5. WHEN 导出的中文文件名包含非 ASCII 字符, THE Delivery_Exporter SHALL 按 RFC 5987 编码文件名，避免下载文件名乱码。

---

### Requirement 19: 合伙人全局刷新勾选弹窗（前端入口）

> **实现状态**：🔴 待实现（P0）。实读代码确认：无 `GtRefreshScopeDialog.vue`、无任何前端组件调 `/draft-refresh`，design §13 的勾选弹窗链不存在 → 合伙人 UI 无从触发全局刷新，功能不可达。

**User Story:** 作为业务合伙人，我想在点击"全局一键刷新"后弹出勾选弹窗自行勾选要刷新的内容，以便按需刷新报表/底稿/调整分录/附注等子集，而非每次都被迫全量刷新，也不必依赖后端直接调用。

#### Acceptance Criteria

1. THE Formula_Management_Library SHALL 在页面上向合伙人提供全局一键刷新入口（Global_Refresh 触发按钮）。
2. IF 当前用户角色不属于 {partner, signing_partner}, THEN THE Formula_Management_Library SHALL 不向该用户展示全局一键刷新入口（合伙人门禁在前端不可见、后端 Requirement 1 二次拦截）。
3. WHEN 合伙人点击全局一键刷新入口, THE Refresh_Scope_Dialog SHALL 弹出并列出可刷新内容分类（Refresh_Scope_Item），至少包含报表、底稿（按循环）、调整分录、附注。
4. WHERE 底稿类刷新范围按循环组织, THE Refresh_Scope_Dialog SHALL 允许合伙人按循环（如 D 类）勾选，而非只能整体勾选全部底稿。
5. IF 合伙人未勾选任何 Refresh_Scope_Item, THEN THE Refresh_Scope_Dialog SHALL 禁止提交并提示"请至少勾选一项刷新内容"，且不触发任何刷新。
6. WHEN 合伙人勾选一个 Refresh_Scope_Item 子集并确认, THE Refresh_Scope_Dialog SHALL 以选定范围调用 `POST /draft-refresh`（请求体含 project_id、year、scopes、confirm_overwrite）。

---

### Requirement 20: 全局刷新范围动态发现（Refresh_Scope_Discovery）

> **实现状态**：🔴 待实现（P1）。实读代码确认：当前 scopes 仅字符串透传，无发现服务/端点；`refresh` 里 scope 仅用于审计键/幂等键/preview_overwrites 前缀，不驱动范围发现，新增循环/模块不会自动出现在勾选项。

**User Story:** 作为公式管理库开发者，我想让可刷新范围项从平台既有模块/循环注册动态发现，以便新增模块或循环自动出现在勾选项而不遗漏刷新。

#### Acceptance Criteria

1. THE Refresh_Scope_Discovery SHALL 从平台既有来源动态发现可刷新范围项：模块注册（报表 / 调整分录 / 附注等固定顶层域）、`cycleDialogRegistry` 派生的循环集合、`wp_index` 现存 wp_code 的循环前缀。
2. THE Refresh_Scope_Discovery SHALL NOT 使用硬编码的固定范围清单。
3. WHEN 平台新增一个模块或循环, THE Refresh_Scope_Discovery SHALL 使该模块/循环在无需修改 Refresh_Scope_Dialog 代码的情况下自动出现在可勾选范围项中。
4. THE Refresh_Scope_Discovery SHALL 对底稿类范围项按循环粒度产出（如"底稿:循环D"），并对多来源发现结果按范围键去重。
5. THE Refresh_Scope_Dialog SHALL 消费 Refresh_Scope_Discovery 的产出渲染可勾选项，而非自行拼装范围清单。
6. THE Refresh_Scope_Discovery SHALL 供勾选弹窗与后端范围执行（Requirement 21）共用同一发现口径，避免前后端范围清单漂移。

---

### Requirement 21: 全局刷新按勾选范围编排生成初稿

> **实现状态**：🔴 待实现（P0·核心）。实读代码确认：`draft_refresh.py` 的 `/draft-refresh` 调 `DraftRefreshService.refresh()` 时不传 `units`（默认空）、不调 `refresh_with_presets`、不传 `page_keys`、不调用报表引擎/审定表回写/附注生成器 → 合伙人触发全局刷新只写审计、affected_count=0、零初稿。`DraftRefreshService` 是治理编排层，缺少驱动各生成器产出 Draft_Unit 的上游编排。

**User Story:** 作为业务合伙人，我想让全局一键刷新真正按我勾选的范围生成报表/底稿/附注初稿，以便触发刷新后得到可复核的初稿而非空结果。

#### Acceptance Criteria

1. WHEN Draft_Refresh_Service 收到含非空 scopes 的全局刷新请求, THE Draft_Refresh_Service SHALL 对每个被勾选的 Refresh_Scope_Item 调用其对应生成器产出 Draft_Unit：报表域调用 Report_Engine、审定/底稿域调用 Adjudication_Writeback 与底稿生成、附注域调用 Note_Formula_Executor。
2. WHEN Draft_Refresh_Service 为被勾选范围生成初稿公式, THE Draft_Refresh_Service SHALL 依据 Preset_Formula_Library（`refresh_with_presets` / `build_preset_draft_units`）按 page_key 套用预设公式作为初稿公式来源。
3. THE Draft_Refresh_Service SHALL NOT 对未被勾选的 Refresh_Scope_Item 执行任何生成或数据写入。
4. WHEN 全局刷新完成, THE Draft_Refresh_Service SHALL 返回本次实际生成的初稿单元数量，使 affected_count 反映真实生成量而非恒为 0。
5. WHEN 全局刷新生成 Draft_Unit, THE Draft_Refresh_Service SHALL 为生成单元写入 Draft 语义标记与最近计算时间（复用 Requirement 3 的初稿语义），并在覆盖人工编辑前遵循 Requirement 4 的团队编辑区分与回滚快照。
6. WHEN 按勾选范围执行的全局刷新完成, THE Audit_Trail SHALL 记录本次刷新实际覆盖的 Refresh_Scope_Item 清单与受影响记录数（依据 Requirement 4 的留痕契约）。

---

### Requirement 22: 模块/循环级局部刷新对其他角色开放

> **实现状态**：✅ 已实现（`audit-sheet-refresh` 换 `require_wp_edit_permission` 编辑权门禁，复用 DraftRefreshService 的 precheck/snapshot/draft/audit 编排，仅门禁与 scope 范围不同）。

**User Story:** 作为审计助理或现场经理，我想在自己负责的模块或循环内触发局部刷新，以便无需等待合伙人即可刷新本模块数据，同时保持刷新数据的初稿语义与留痕。

#### Acceptance Criteria

1. WHEN 项目内具有该底稿/模块编辑权的用户调用 Module_Refresh 入口（如 `audit-sheet-refresh` 逐底稿刷新、报表模块内刷新、D 类循环刷新）, THE Module_Refresh SHALL 允许执行，而不要求调用者为合伙人。
2. IF 调用者对目标底稿/模块不具备编辑权, THEN THE Module_Refresh SHALL 返回 HTTP 403 并不执行任何数据写入。
3. WHEN Module_Refresh 执行完成, THE Module_Refresh SHALL 为刷新生成的数据单元写入 Draft 语义标记与最近计算时间，与 Global_Refresh 保持一致的初稿语义。
4. WHEN Module_Refresh 执行完成, THE Audit_Trail SHALL 记录本次局部刷新，留痕粒度按被刷新的模块/循环组织（记录目标模块/循环、底稿标识、操作者与受影响记录数）。
5. THE Module_Refresh SHALL 限定其刷新范围在被调用的模块/循环内，而不触发跨模块的全局刷新。
6. WHERE Module_Refresh 即将覆盖已存在的人工编辑数据, THE Module_Refresh SHALL 沿用 Requirement 4 的团队编辑区分规则，仅在确认后覆盖人工编辑单元。

---

### Requirement 23: 报表勾稽前端消费后端 logic_check（收编闭环）

> **实现状态**：🔴 待实现（P1）。实读代码确认：后端 `logic_check.py` 已把 7 条勾稽落库为可编辑 logic_check 公式并建了执行端点，但前端 `useReportCrossCheck.ts` 仍是硬编码纯函数、从不消费后端、无法在 Formula_Edit_Dialog 编辑，Requirement 6.4 只兑现了后端半环。

**User Story:** 作为现场经理，我想让报表勾稽由前端消费后端 logic_check 端点返回的问题清单并可在统一弹窗编辑，以便 7 条勾稽真正成为可编辑公式而非前端硬编码。

#### Acceptance Criteria

1. WHEN 报表页面执行跨表勾稽校验（Report_Cross_Check）, THE Formula_Management_Library SHALL 调用后端 logic_check 执行端点获取 Issue_List，并以其结果驱动前端勾稽展示。
2. THE Formula_Management_Library SHALL 保留 `useReportCrossCheck.computeCrossCheckResults` 的纯函数勾稽实现作为后端不可用时的降级路径。
3. IF 后端 logic_check 端点不可用, THEN THE Formula_Management_Library SHALL 回退到纯函数勾稽实现，且不阻断报表页面渲染。
4. THE Formula_Management_Library SHALL 使收编的 7 条勾稽可在 Formula_Edit_Dialog 中以 logic_check 类型查看与编辑，编辑后的定义经后端持久化并参与后续勾稽执行。
5. THE 前端消费后端 logic_check 后的勾稽判定语义 SHALL 与原 `computeCrossCheckResults` 硬编码实现保持一致（收编不改变勾稽含义）。

---

### Requirement 24: 公式作用域过滤与全局公式管理页

> **实现状态**：🔴 待实现。design §15 定义的作用域过滤/全局公式页因编号撞车从未变成任务、从未实现。

**User Story:** 作为审计助理，我想在某个页面打开公式弹窗时只看到并只能编辑当前页面的公式，同时保留一个能浏览全部公式的全局公式管理页，以便页面内聚焦本页公式、需要总览时又能跨页查看。

#### Acceptance Criteria

1. WHEN 用户在某页面内打开公式弹窗, THE Formula_Management_Library SHALL 依据当前页面对应的 Formula_Scope（`note` / `consol_note` / `consol_worksheet` / `consol_report` / `report` / `tb` / `workpaper` 之一）仅加载该作用域的公式。
2. WHERE 公式弹窗以某 Formula_Scope 打开, THE Formula_Edit_Dialog SHALL NOT 展示或允许编辑其他无关 Formula_Scope 页面的公式。
3. WHEN 用户打开 Global_Formula_Page, THE Global_Formula_Page SHALL 跨全部 Formula_Scope 展示所有公式，供用户总览与导航。
4. THE Formula_Management_Library SHALL 复用 `FormulaManagerDialog.vue` 既有的 `scope` prop（默认 `report`）与树形导航（selectedNodeKey / selectedPath / `SCOPE_LABEL_MAP` 中文标签）实现作用域过滤，而非新增并行的作用域机制。
5. WHEN 用户在不同 Formula_Scope 之间切换, THE Formula_Management_Library SHALL 使各作用域的公式集互不串扰（一个作用域的编辑不影响另一作用域的公式列表）。
6. THE Formula_Scope 过滤后展示的公式来源地址 SHALL 使用 ACNR full_resolve 返回的规范地址名称（与 Requirement 10 一致）。

---

### Requirement 25: 公式三来源（预设 / 自定义 / 参照已有）

> **实现状态**：🟡 部分实现。数据模型就绪（`WpFormula.formula_source` / `reference_formula_id` 列已建），但 preset/custom/reference 三来源的完整选择流与 reference 失效链尚未在前端/编排层接通。

**User Story:** 作为审计助理，我想通过一键预设、自定义编辑、参照已有公式三种方式设置公式，以便快速套用标准公式、灵活自定义、或复用已设置好的公式而不重复录入。

#### Acceptance Criteria

1. THE Formula_Management_Library SHALL 支持三种 Formula_Source：`preset`（一键预设）、`custom`（自定义编辑）、`reference`（参照已有公式）。
2. WHEN 用户选择 `preset` 来源, THE Formula_Management_Library SHALL 从 Preset_Formula_Library（`check_presets` / 预设库）套用预设公式到目标单元。
3. WHEN 用户以 `custom` 来源覆盖某单元的预设公式, THE Formula_Management_Library SHALL 持久化为 User_Formula 并标记 `is_preset_override=true`，且保留将该单元恢复为预设公式（restore preset）的能力。
4. WHEN 用户请求将某 `custom` 覆盖单元恢复为预设, THE Formula_Management_Library SHALL 删除该单元的 User_Formula 覆盖并使其回退到预设公式，复用 `wp_user_formulas.py` 既有的 restore/delete 语义（`/api/workpapers/{wpId}/user-formulas/{cell_key}`）。
5. WHEN 用户选择 `reference` 来源, THE Formula_Management_Library SHALL 允许引用另一条已保存公式的表达式/定义作为新公式来源，扩展 Requirement 9 的公式复用能力。
6. THE Formula_Management_Library SHALL 为每条公式记录其 Formula_Source 标识，使前端可区分展示公式来自预设、自定义还是参照。
7. WHEN 被参照的源公式发生变更, THE Formula_Management_Library SHALL 依据 reference 引用关系使引用方公式失效并可重算，复用 ACNR 失效链而非自建失效逻辑。

---

### Requirement 26: 公式三能力显式化（可视化 / 可编辑保存 / 可运算刷新）

> **实现状态**：✅ 已实现（派生自 Requirement 10 / 8-9 / 5-7，作为跨三处一致性的总括契约）。

**User Story:** 作为审计助理，我想让每条公式都同时具备可视化、可编辑保存、可运算刷新三种能力，以便查看来源、修改定义并触发重算，形成完整的公式操作闭环。

#### Acceptance Criteria

1. THE Formula_Management_Library SHALL 使每条公式可视化：通过 Formula_Source_Tooltip（悬停）与公式列表展示其表达式、来源与最近计算时间（与 Requirement 10 一致）。
2. THE Formula_Management_Library SHALL 使每条公式可编辑保存：通过 Formula_Edit_Dialog 编辑并按 Requirement 9 持久化。
3. THE Formula_Management_Library SHALL 使每条公式可运算刷新：由 Formula_Engine 按公式类型执行（auto_calc 回填值 / logic_check 产出问题清单 / reasonability 产出提醒），并更新最近计算时间。
4. WHEN 用户对一条公式触发运算刷新, THE Formula_Engine SHALL 依 Requirement 5/6/7 的类型语义执行，且 logic_check 与 reasonability 类型 SHALL NOT 修改任何数据单元的值。
5. THE Formula_Management_Library SHALL 使可视化、可编辑保存、可运算刷新三能力在底稿、报表、附注三处一致可用。

---

### Requirement 27: 前端 per-cycle 公式引擎纳入三类型治理（增量）

> **实现状态**：🟡 部分实现（`formulaEngineInventory.ts` 清单 + 三类型映射就绪，试点 D3/S34 已接入悬停与 ACNR 引用；其余 `useXFormulaEngine` 按同模式增量推进，未接入者保留现状不回归）。

**User Story:** 作为公式管理库开发者，我想让分散在各循环的前端公式引擎纳入三类型语义与统一体验，以便客户端计算的公式也可被识别、悬停查看、并逐步统一，而非各写一套硬编码。

#### Acceptance Criteria

1. THE Formula_Management_Library SHALL 建立前端 per-cycle 公式引擎清单（`useXFormulaEngine` / `useXCrossSheet` composable，如 useS34FormulaEngine / useD3FormulaEngine / useD3CrossSheet 等），作为公式管理触点的可核查真源（inventory）。
2. THE Formula_Management_Library SHALL 将前端公式引擎的计算原语映射到三类型语义：求和/比率/账面价值类（createSumFormula/createRatioFormula 等）→ auto_calc；阈值/合理性判断类（createThresholdFormula 等）→ reasonability；勾稽/平衡校验类 → logic_check。
3. WHERE 前端公式引擎产生的单元由公式计算得出, THE Formula_Source_Tooltip SHALL 可挂载于该单元展示表达式与来源（复用 Requirement 10 的统一组件）。
4. THE Formula_Management_Library SHALL 采取增量收敛：以 useD3FormulaEngine + useS34FormulaEngine 为试点接入统一三类型语义/悬停，其余 `useXFormulaEngine` 后续按同一模式接入（不要求一次性重写全部循环引擎）。
5. WHEN 前端公式引擎需要解析跨表/跨底稿引用地址, THE 引擎 SHALL 经 ACNR 前端 SDK（useAcnr）解析而非前端自行拼接坐标字符串（协调 `acnr-consumer-wiring` Req 14）。
6. WHEN 某前端公式引擎尚未接入统一治理, THE Formula_Management_Library SHALL 保留其现有客户端计算行为不变（无回归），仅在清单中标注"待接入"。

---

### Requirement 28: 求值内核收口 + 悬停 tooltip 收敛 + recalc 衔接

> **实现状态**：✅ 已实现（求值内核收口稳定：`formula_parse_utils.evaluate_formula`/`FormulaEvaluator` 已标 DeprecationWarning 并委托 `formula_engine.execute`；tooltip 内联实现按增量收敛到 `GtFormulaSourceTooltip`；recalc 与一键刷新语义区分已落地）。

**User Story:** 作为公式管理库开发者，我想收口重复的求值实现、统一散落的公式悬停展示、并明确重算与一键刷新的衔接，以便公式计算有单一内核、展示一致、过时可控。

#### Acceptance Criteria

1. THE Formula_Engine SHALL 以 `formula_engine.execute`（L1 内核）作为后端求值的单一入口；`formula_parse_utils.evaluate_formula` / `FormulaEvaluator` SHALL 标注为废弃并逐步由调用方（如 consol_report_service 的调用）迁移到 L1 内核或 `report_engine.evaluate_formula`。
2. THE Formula_Engine SHALL NOT 新增并行的求值实现；新代码一律走 L1 内核。
3. WHEN 组件当前以内联 `.formula-cell` + `title=` 展示公式, THE Formula_Source_Tooltip SHALL 作为统一替代（Requirement 10），散落内联实现逐步收敛到统一组件；未收敛前保留现状不回归。
4. WHEN 审定数/底稿单元因编辑或一键刷新变更导致下游公式过时, THE Formula_Management_Library SHALL 通过既有 `prefill_stale` 标记与 `/trial-balance/recalc` 重算机制反映过时状态，而非新建并行的过时追踪。
5. WHERE 合伙人执行一键刷新, THE Draft_Refresh_Service SHALL 在生成初稿后触发受影响单元的重算/过时刷新，使初稿与四表库未审数一致（复用 recalc/stale 机制，不自建）。
6. THE Formula_Management_Library SHALL 使一键刷新（合伙人专属，Requirement 1）与普通 `recalc`（团队成员可触发的试算表重算）语义清晰区分：recalc 仅重算既有公式不生成初稿、不打 Draft 标记；一键刷新生成初稿并受角色门禁约束。

---

### Requirement 29: 公式预设库（逐页分析 + 预设，作为公式库一部分）

> **实现状态**：🟡 部分实现（`preset_library.py` 的 `build_preset_library`/`build_inventory`/`compute_preset_coverage` groundwork 就绪，收敛 `prefill_formula_mapping`/`check_presets`/`wide_table_presets`；逐页预设仅试点 D 循环/报表/附注核心页，inventory 大量 pending；全局刷新按 page_key 套用预设的消费链见 Requirement 21.2）。

**User Story:** 作为公式管理库维护者，我想按每个页面的实际结构与内容逐一分析并预设公式，把预设沉淀为公式库的一部分，以便新项目/一键刷新时可直接套用成熟公式而非从零编写。

#### Acceptance Criteria

1. THE Formula_Management_Library SHALL 建立"页面/sheet 公式预设清单（Preset Inventory）"，逐一登记程序中每个承载公式的页面/sheet（底稿各 sheet、报表、附注各 section），作为预设覆盖的可核查真源。
2. THE Formula_Management_Library SHALL 针对每个页面按其实际结构与内容预设公式定义（含目标单元、表达式、公式类型 auto_calc/logic_check/reasonability、引用地址），部分页面公式数量较多时允许一个页面承载多条预设。
3. THE Preset_Formula_Library SHALL 以 seed 数据形式持久化（遵循现有 seed 模式，如 `formula_presets_seed.json` + 幂等 seed 脚本），并收敛已有的 `prefill_formula_mapping` / `check_presets` / `wide_table_presets` 到统一预设库口径。
4. WHEN 合伙人一键刷新或底稿生成时, THE Formula_Management_Library SHALL 依据预设库为目标页面套用预设公式（作为初稿公式的来源之一，与 Requirement 21.2 一致）。
5. THE Preset_Formula_Library SHALL 提供预设覆盖度视图（复用/扩展 `get_formula_coverage`），标注每个页面"已预设/待预设"，使逐页预设工作可增量推进、进度可见。
6. THE 逐页预设工作 SHALL 采取增量交付（按循环/模块分批预设，如先 D/报表/附注核心页面），未预设页面保留现状不回归，并在清单中标注待预设。
7. THE Preset_Formula_Library 中预设公式的引用地址 SHALL 使用 ACNR addr_id / formula_ref，经 full_resolve 可解析，而非硬编码坐标字符串（协调 Requirement 11）。

---

### Requirement 30: 公式模块导入导出（导出模板含编报说明）

> **实现状态**：✅ 已实现（`useFormulaImportExport` + 后端三端点 export-template/export-data/import-data；导出模板首区块=编报说明；导入 full_resolve 校验悬空跳过；中文文件名 RFC5987）。

**User Story:** 作为审计助理，我想在公式模块导出模板/导出数据/导入数据，且导出模板内含编报说明，以便离线批量编辑公式并按说明正确填报后回导。

#### Acceptance Criteria

1. THE Formula_Management_Library SHALL 在公式模块提供"导入导出"入口（遵循平台统一规范：`el-dropdown "导入导出▾"` 含 导出模板 / 导出数据 / 导入数据 三项，复用 `useXImportExport` composable + 后端三端点）。
2. WHEN 用户导出模板, THE Formula_Management_Library SHALL 生成含空白/示例公式行的模板文件，且模板中 SHALL 包含"编报说明"区（说明各公式类型填法、引用地址格式、三类型语义、注意事项）。
3. WHEN 用户导出数据, THE Formula_Management_Library SHALL 导出当前页面/模块已有公式（含目标单元、表达式、公式类型、引用、最近计算时间）。
4. WHEN 用户导入数据, THE Formula_Management_Library SHALL 解析导入文件并对每条公式引用经 ACNR full_resolve 校验，悬空引用项 SHALL 报告并跳过（不静默入库错误公式）。
5. THE 导入导出 SHALL 用 http(axios) 携带 Authorization，导出中文文件名按 RFC 5987 编码（遵循平台铁律）。
6. THE 编报说明 SHALL 与 Requirement 32 的公式管理说明文档口径一致（同一份说明的模板内嵌版本），避免说明两套漂移。

---

### Requirement 31: 模板库 ACNR 地址坐标名称库更新

> **实现状态**：✅ 已实现（`preset_acnr_migration.py` 归一化引用 + LEGACY_ALIAS_MAP + drift guard，纳入 acnr-consumer-wiring Coverage Ledger）。

**User Story:** 作为模板库维护者，我想让模板库中的地址坐标名称库按近期 ACNR 改动更新，以便模板库预设公式的引用地址与 ACNR 单一真源一致。

#### Acceptance Criteria

1. THE 模板库 SHALL 使其地址坐标名称引用与 ACNR（`.kiro/specs/acnr/`）及 `acnr-consumer-wiring` 的近期改动对齐，预设公式引用改用 ACNR addr_id / formula_ref。
2. WHEN 模板库展示可选地址/字段, THE 模板库 SHALL 经 ACNR 前端 SDK（useAcnr）取候选地址，而非硬编码地址列表（协调 `acnr-consumer-wiring` Req 14）。
3. THE 模板库地址坐标更新 SHALL 复用 `acnr-consumer-wiring` 的 Coverage Ledger 与 CI drift guard，纳入无死角清单，不新建并行地址源。
4. WHERE 模板库存在硬编码地址/坐标名称（如预设映射中的旧格式引用）, THE 更新 SHALL 将其归一化为 ACNR addr_id，未归一化项在 Ledger 标注待迁移（增量，无回归）。

---

### Requirement 32: 公式预设库入口 + 公式管理说明文档弹窗

> **实现状态**：✅ 已实现（`GtFormulaPresetDialog` 复用 TemplateLibraryButton 入口区；说明文档单一源 `reporting_instructions` 同端点）。

**User Story:** 作为审计助理，我想在模板库合适位置点击进入公式预设库并查看公式管理说明文档，以便理解三类型公式与预设的用法。

#### Acceptance Criteria

1. THE 模板库 SHALL 在合适位置（复用 `TemplateLibraryButton` 所在的 NoteTemplateTab / ReportConfigTab / WpTemplateDetail 入口区）提供公式预设库的可点击入口。
2. WHEN 用户点击公式预设库入口, THE Formula_Management_Library SHALL 弹出弹窗展示公式管理说明文档（说明三类型公式 auto_calc/logic_check/reasonability 的用法、引用地址格式、预设库用法、导入导出与编报说明、一键刷新与初稿语义）。
3. THE 说明文档弹窗 SHALL 以单一文档源渲染，与 Requirement 30.6 的导出模板编报说明同源，避免多处说明漂移。
4. WHERE 用户在弹窗内, THE 弹窗 SHALL 可导航到公式预设库的浏览/编辑（复用 Requirement 8 的统一 Formula_Edit_Dialog 与 Requirement 29 的预设清单）。
5. THE 入口与弹窗 SHALL 不改变模板库既有功能行为（附加入口，无回归）。

---

## 溯源（Traceability，codegraph/postgres 实证）

> 单一编号序列（Req 1-32）的实证锚点。已实现项标注落地位置；待实现/部分实现项标注缺口证据。

| 需求 | 状态 | 实证锚点 |
|------|------|----------|
| Req 1 | ✅ | `wp_render_config.py:417-420` 一键刷新原 `Depends(get_current_user)` 无角色限制；`deps.py:125 require_role`；`/draft-refresh` 施加 `require_role(partner/signing_partner)`，`audit-sheet-refresh` 施加 `require_wp_edit_permission` |
| Req 2 | ✅ | `DraftRefreshService.precheck` 复用 `report_trace.py` 子公司数据完整度前置校验口径 |
| Req 3/4 | ✅ | `refresh` 计 `tb_snapshot_hash` 幂等；`draft_marker` 状态；`draft_refresh_audit` append-only；`draft_refresh_snapshot` 回滚快照；`preview_overwrites` |
| Req 5 | ✅ | auto_calc：`formula_management/engine.py:execute_formula` 分派回填 + last_computed_at |
| Req 6 | ✅ 后端 | `logic_check.py` 收编 `useReportCrossCheck` 7 条勾稽为可编辑公式 + 执行端点（前端消费=Req 23 待实现） |
| Req 7 | ✅ | reasonability 分派产 Hint_List 不改值 |
| Req 8 | ✅ | `GtFormulaEditDialog.vue` 三类型 v-if 分派 + FormulaRefPicker 选址 |
| Req 9 | ✅ | `wp_formula_service.py:44 save() -> tuple[WpFormula\|None, list[dict]]` |
| Req 10 | ✅ | `GtFormulaSourceTooltip.vue` 虚线下划线 + cursor:help + semantic_label 懒解析 |
| Req 11 | ✅ | `engine.py:resolve_ref` 封装 ACNR full_resolve + fail-open；acnr-consumer-wiring Req9 校验路径 |
| Req 12 | ✅ | `four_table_source.py` 叶子源只读守卫；`get_active_filter`；tb_balance 借正贷负；损益取发生额；aux_type 分组 |
| Req 13 | ✅ | `adjudication_writeback.py` 回写 `trial_balance.audited_amount` + ACNR 失效链 |
| Req 14 | ✅ | `WpFormulaService.save` full_resolve 校验；CrossSheetResolver 跨 sheet 追溯；三类型 category |
| Req 15 | ✅ | AJE/RJE → aje_adjustment → audited_amount → `ReportEngine.regenerate_affected` 增量 + 悬空记 Issue 续算 |
| Req 16 | ✅ | `report_engine.py generate_all_reports`/`generate_unadjusted_report`；ROW 经 resolve_ref；失败标注行不产空报表 |
| Req 17 | ✅ | `note_formula_generator.py:314 execute_note_formulas` 对齐 resolve_ref + `note:{section}!{r}:{c}` addr_id + reaggregate 精准刷新；NoteFormulaDialog 修复引用 acnr-consumer-wiring Req15 |
| Req 18 | ✅ | `delivery_export.py` 公式→静态值 + `content_disposition_attachment` RFC5987 单一 helper |
| Req 19 | 🔴 P0 | **缺口**：无 `GtRefreshScopeDialog.vue`、无组件调 `/draft-refresh`；design §13 勾选弹窗链不存在，合伙人 UI 无从触发 |
| Req 20 | 🔴 P1 | **缺口**：scopes 仅字符串透传，无 RefreshScopeDiscovery 发现服务/端点；`refresh` 里 scope 仅作审计键/幂等键/preview 前缀 |
| Req 21 | 🔴 P0 | **缺口**：`draft_refresh.py /draft-refresh` 调 `service.refresh()` 不传 units（默认空）、不调 refresh_with_presets、不传 page_keys、不调报表引擎/审定回写/附注生成器 → affected_count=0、零初稿 |
| Req 22 | ✅ | `audit-sheet-refresh` 换 `require_wp_edit_permission`；复用 DraftRefreshService precheck/snapshot/draft/audit，仅门禁与 scope 不同 |
| Req 23 | 🔴 P1 | **缺口**：后端 `logic_check.py` 落库+端点已建，但前端 `useReportCrossCheck.ts` 仍硬编码纯函数、从不消费后端、无法在弹窗编辑（Req 6.4 只兑现后端半环） |
| Req 24 | 🔴 待实现 | design §15 作用域过滤/全局公式页因编号撞车未变任务；`FormulaManagerDialog.vue:453 FormulaManagerScope`（7 类）+ `scope` prop + 树形导航 selectedNodeKey/selectedPath + `SCOPE_LABEL_MAP` 为复用锚点 |
| Req 25 | 🟡 部分 | `WpFormula.formula_source`/`reference_formula_id` 列已建（数据模型就绪）；preset=`check_presets`/预设库；custom=`user_formulas` override（is_preset_override + `/api/workpapers/{wpId}/user-formulas/{cell_key}`）；reference 完整流与失效链待接 |
| Req 26 | ✅ 派生 | 可视化=Req 10 tooltip+列表；可编辑保存=Req 8/9；可运算刷新=Req 5/6/7 Formula_Engine 执行 |
| Req 27 | 🟡 部分 | `formulaEngineInventory.ts` 清单 + PRIMITIVE_TYPE_MAP 三类型映射；试点 D3/S34 已接入；其余 `useXFormulaEngine` 增量待接（标 pending，无回归） |
| Req 28 | ✅ | `formula_parse_utils.evaluate_formula`/`FormulaEvaluator` 已标 DeprecationWarning 委托 `formula_engine.execute`（P20 稳）；内联 `.formula-cell`+`title=` 增量收敛 GtFormulaSourceTooltip；`useStaleStatus.recalc`→`/trial-balance/recalc`+`prefill_stale` 与一键刷新语义区分 |
| Req 29 | 🟡 部分 | `preset_library.py build_preset_library`/`build_inventory`/`compute_preset_coverage` 收敛 prefill/check/wide + `formula_presets_seed.json` + `inventory.json` + `seed_formula_presets.py`；逐页预设仅试点 D/报表/附注核心页，inventory 大量 pending；全局刷新消费=Req 21.2 待接 |
| Req 30 | ✅ | `useFormulaImportExport` + 后端三端点 export-template/export-data/import-data；导出模板首区块编报说明；导入 full_resolve 校验悬空跳过；RFC5987 |
| Req 31 | ✅ | `preset_acnr_migration.py normalize_ref + LEGACY_ALIAS_MAP + PENDING_FUNCTION_ALLOWLIST + drift guard`，纳入 acnr-consumer-wiring Coverage Ledger |
| Req 32 | ✅ | `GtFormulaPresetDialog` 复用 TemplateLibraryButton（NoteTemplateTab/ReportConfigTab/WpTemplateDetail）入口区；说明文档单一源 `reporting_instructions` 同端点 |

## 修订影响与后续对齐（本阶段不改 design/tasks）

- **本次仅改 requirements.md**。编号从"三套冲突"收敛为单一序列（Req 1-32），后续 design.md / tasks.md 阶段需按本编号对齐：
  - design.md §13-15「当前需求权威设计」原对应旧 Req 19-23（勾选弹窗/Module_Refresh/作用域过滤/公式三来源），现映射为新 Req 19-22 / Req 24-25；design §7-8 及 P19-P21（前端引擎治理/内核收口）原旧 Req 24-25，现映射为新 Req 27-28。
  - tasks.md Task13（原标「Req 19-20」前端引擎治理+内核收口）应重挂新 Req 27-28；Task14（原标「Req 22-25」预设库四件）应重挂新 Req 29-32。
  - P0/P1 缺口新增 Req 19-21、Req 23、及 Req 29 的全局刷新消费部分，需在 design/tasks 阶段新增对应组件与任务（Refresh_Scope_Dialog / Refresh_Scope_Discovery / 全局刷新编排生成初稿 / 前端接 logic_check 端点）。
- **边界铁律沿用**（不重写）：地址解析/选址器/NoteFormulaDialog 修复引用 ACNR + acnr-consumer-wiring（Req 9/14/15）；四表库叶子源只读；service 只 flush、router commit；中文文件名 RFC5987；合伙人门禁仅施加于全局刷新（Req 1/19/21），Module_Refresh 走编辑权门禁（Req 22）。
