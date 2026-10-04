# Requirements Document

## Introduction

D4-1「营业收入审定表」是 D4 收入循环的审定枢纽，连接 D4-2/D4-3 明细、D4-4 调整、四表取数、`trial_balance` 与审计说明。本 spec 描述 D4-1 的 HTML 结构化视图与 OnlyOffice 表征之间的双向回写、公式定义、导入导出和审定回写。目标是让 D4-1 从 legacy 单向 `GtOnlyOfficeSheet` 升级为走统一 `useWorkpaperSyncBridge` + `ContentMutationService` 的真双向 sheet（HTML↔OO 经同一 content version、三方合并、durable callback 往返），与 D4-2/D4-3/D4-5/D4-15/D4-16 等已做实 sheet 同 adapter `d4.revenue_detail`、同 entry `xlsx/gt-d4-operating-revenue`。

模板几何已于 2026-09-19 用 openpyxl 直读权威模板核定（见下），本 spec 据此确定 D4-1 走 **static-cell 模式**（固定单元格坐标），而非 D4-2 的行 UUID 模式。

## Glossary

| 术语 | 含义 |
|------|------|
| static-cell 模式 | 受管字段用绝对单元格坐标（`static_row`）定位读写，非按行 UUID；适用于固定行骨架、不插行的 sheet（参照 D4-5） |
| 受管字段 | HTML↔OO 双向同步的输入格；普通值 projection 只写这些格 |
| formula_mask | Excel 内部公式格集合；普通值投影不覆盖，保留公式字节 |
| effective definition | F-SHELL 的公式有效定义（preset ∪ custom），带版本与哈希 |
| D4-1 审定快照 | D4-1 底稿自身的审定合计（`D4-1-rows` + per-field），TB 发布的权威来源 |
| entry / adapter | `xlsx/gt-d4-operating-revenue` / `d4.revenue_detail`（D4 收入底稿共用） |

## 模板几何核定结果

来源：openpyxl 直读 `backend/wp_templates/D/D4 收入底稿.xlsx`（sha256 `b8fb92d4…167b5f`），sheet `营业收入审定表D4-1`（dims A1:I80）。

- 表头：行 5「项目 / 本期数 / 上期数」+ 行 6「未审数 / 账项调整 / 重分类调整 / 审定数」（两级）；本期列 B–E，上期列 F–I。
- 主营业务收入段：数据行 **8–11**（4 行固定骨架）；行 12「小计」。
- 其他业务收入段：数据行 **14–17**（4 行固定骨架）；行 18「小计」。
- 行 19「合计」、行 20「试算平衡表数」、行 21「差异数」、行 22+ 审计说明/结论（HTML-only）。
- 列：A=项目名 · **B/C/D=本期 未审/账项调整/重分类调整（输入）** · E=本期审定（Excel 公式 `=SUM(B:D)`）· **F/G/H=上期三输入** · I=上期审定（公式）。
- 小计/合计/差异行（12/18/19/21）全为 Excel 内部公式。

**关键裁决 DEC0：D4-1 走「同 sheet 双区动态行」模式（行 UUID + 插行），参照 D4-9，不是 static-cell。**

> 🔴 纠正记录（2026-09-19）：初判据 openpyxl「模板当前只有 4+4 行」误裁为 static-cell 固定骨架。经核实前端 `useD4Adjudication` + `d4AdjudicationRows.ts` 与源模板注释，**D4-1 主营/其他两段是「4 行空白可扩行」（R8:R11 / R14:R17），必须是动态行**——9 个在册项目有业务板块级子科目（批发/零售/物流/物业与租赁/医疗/服务费等），会超过 4 行。static-cell 裁决作废。

- 依据①：**前端已是动态行模型**——`useD4Adjudication` 走平台共享件 `shared/dynamicAdjudicationRows`（`D4_ADJ_ROWS_SPEC` prefix=`D4-1`），有 `addRow`/`dropRow`/`seedRowsFromPrefill`/`renameRowLabel`；store 键 = `D4-1-rows`（新模型，`rowsItemId`）+ per-field `D4-1-{rowId}-{field}`（6 类金额）；旧键 `D4-1-adj-rows` 仅迁移兼容。
- 依据②：D4-1 是**同 sheet 内两个受管区**（主营段 + 其他段，中间夹小计行 12/段标题行 13），与 D4-9（本期区/上期区同 sheet）**同构**。全平台同 sheet 双区的前置阻塞 = `excel_instrumentation._attach_table_part` 对同 sheet 二次注入产出非法双 `<tableParts>`（第二区 Table 被 openpyxl 丢弃 = 假双向）。
- 依据③：**D4-1 依赖 D4-9 spec 的 `_attach_table_part` 修复**（同 sheet 合并 `<tableParts count>`，路径 A）。D4-9 owner spec 当前 0/15 未做——若该修复未落地，D4-1 的双区注入同样阻塞，Task 里须显式标 BLOCKED，不得绕过。
- 与 D4-4（已裁 single_html）区别：D4-4 是「hub store 被 A13/借贷平衡占用」不可双向；D4-1 是标准动态行审定表，可双向。

**契约结构（DEC0，参照 D4-9 单 sheet 多 table）**：
- **table 1 主营动态行**：row_identity（field rowId），anchor 主营段表头，受管列 A(label)/B/C/D(本期未审/账项调整/重分类)/F/G/H(上期三输入)；UUID 列取一空列。
- **table 2 其他动态行**：同结构，anchor 其他段表头，UUID 用**另一空列**（双区不同 UUID 列，同 D4-9 W/X）。
- **formula_mask（不回写）**：E/I 列审定数（`=SUM`）+ 小计/合计/差异行（12/18/19/21）的 B–I 公式格。
- store：`D4-1-rows`（含 sectionKey 区分 main-revenue/other-revenue）+ per-field 键；TB 核对行 `D4-1-adj-tb-6001`/`-6051` 只读回显（不入受管）。
- 🔴 未审数**不从四表库填**（presets.py 已声明 R3.4 宁缺勿造：TB 6001/6051 只有科目总额、无产品/项目维度）；明细行由 D4-2/D4-3 SUMIF 派生 + 人工。可从四表干净取的仅 `D4-1-adj-tb-6001/6051` 标量（已作 Tier A 可编辑公式）。

## 全局约束

- HTML、Excel、平台内容存储均是同一内容的表征，写入统一经过 `ContentMutationService` 的版本校验、三方合并和 durable callback；禁止 Excel 优先和 last-write-wins。
- 公式的 preset/custom/effective definition 统一进入 F-SHELL 与 `wp_formula`；表达式、引用、参数共同参与定义哈希和版本；不得用 `field_overrides` 或 remark 伪造公式库。
- OOXML 公式列用 projection mask 仅防普通值投影覆盖；有权限的公式编辑必须解析为 effective definition，不被 mask 禁止。
- 纯取数用 `app/services/four_table/` 的 `ReportLineAccountSpec`、`select_leaves`、`aggregate_leaves` 和运行时 `tb_source_codes`；缺码必须拒绝或转人工，不臆测科目。
- TB 发布是独立人工动作，不因切换 HTML/Excel 模式触发；D4-1 审定来源取 D4-1 底稿快照，不偷换为 TB。

## Requirements

### Requirement 1: 内容表征与冲突治理

**User Story:** 作为审计人员，我希望 D4-1 的 HTML 视图与 OnlyOffice 视图是同一份内容的两个表征，在任一侧的修改都能安全、可审计地同步到另一侧，以免两侧数据各自为政、静默覆盖。

#### Acceptance Criteria

1. 模板几何已核定（见「模板几何核定结果」，DEC0=同 sheet 双区动态行）：provider 的两区 anchor/UUID 列/受管列映射与 formula_mask 必须与核定一致，运行时经 `authoritative_template_path` + `TEMPLATE_SHA256` 哨兵校验；模板字节变更即 fail-closed。同 sheet 双区注入依赖 D4-9 spec 的 `_attach_table_part` 合并修复，未落地则 BLOCKED。
2. WHEN HTML 或 Excel 写入 THEN 两者必须提交同一 `ContentMutationService` 契约，带基线版本并执行三方合并；冲突须保留、可见、可恢复，禁止 Excel 优先或 last-write-wins。
3. WHEN Excel 普通值投影 THEN 只能写受管字段，OO 公式 mask 保护公式字节；WHEN 用户编辑公式 THEN 必须走 F-SHELL 公式解析、权限、引用、DAG 和版本校验。
4. WHEN 任一写入失败或行身份缺失/重复/公式不支持 THEN 必须 fail-closed，保留原内容、标记失败或 blocked、展示中文错误，不得 markSynced 或把 null 转 0。
5. WHEN HTML/Excel 切换 THEN 不得自动发布 TB；只有用户明确执行"确认审定"且通过差异确认后才能发布。

### Requirement 2: 审定表业务数据与回写

**User Story:** 作为审计人员，我希望审定表的未审数、调整、审定数按四表口径取数并逐格一致地在两侧呈现，且"确认审定"是与模式切换分离的人工动作。

#### Acceptance Criteria

1. WHEN D4-1 读取未审数、AJE、RJE 或 TB 核对数 THEN 必须使用四表服务和运行时 account scope；缺少合法 scope/code 时拒绝或进入人工选择。
2. WHEN 计算审定数、小计、合计、差异、变动率 THEN HTML 与 OO 必须消费同一 effective definition，结果逐 cell 一致；D4-1 审定快照是页面来源，不得以 TB 替代。
3. WHEN 用户编辑数据行 THEN 使用新模型 `D4-1-rows` 清单（`rowsItemId`）+ per-field 键 `D4-1-{rowId}-{field}`（六类金额），每行保留 `rowKey`/`label`/`accountCode`/`sectionKey`/`source`；旧整行 JSON `D4-1-adj-rows` 仅迁移兼容不再新写。行是**动态增删行**（主营/其他两段各可扩行超模板预留 4 行），行身份为稳定 `rowId`（禁下标兜底），受管 projection 按行 UUID 定位；超预留行时经 `excel_row_shift` 插行。
4. WHEN 用户执行确认审定 THEN 先比较 D4-1 快照审定合计与 TB 核对值；差异绝对值大于 0.005 必须二次确认，取消不写，确认后独立人工发布 `6001`/`6051`，切模式不触发。
5. WHEN 只读或发布失败 THEN 编辑与发布入口均禁用/不写库，并给出可追溯错误。

### Requirement 3: 公式治理

**User Story:** 作为审计人员，我希望审定数、小计、合计、差异、变动率等公式在 HTML 与 OO 两侧由同一有效定义驱动，可预设、可自定义、可追溯，失败时不静默转零。

#### Acceptance Criteria

1. WHEN D4-1 公式定义存在 THEN 必须覆盖本期/上期未审、AJE、RJE、审定数、小计、合计、TB核对、差异、变动率和 D4-2/D4-3 WP 引用；每条 `(sheet, cell_ref)` 唯一。
2. WHEN 公式被预设、修改、恢复默认或从 Excel 导入 THEN 均生成同一 effective definition 的 `wp_formula` 版本；custom 不覆盖 preset，恢复默认生成新版本。
3. WHEN 公式引用四表科目 THEN 必须通过 per-cycle account scope 与叶子聚合；缺码拒绝或人工，不以 `6001~6099` 等未核定范围臆测。
4. WHEN 公式求值失败 THEN 该公式及依赖项为 failed/blocked，不 ApplyValue、不转零；无依赖公式可继续。
5. WHEN 下游通过 WP 引用 D4-1 THEN 必须读取可审计快照或有效公式结果；业务导航 refs 与公式 refs 都必须可追溯且不得互相冒充。

### Requirement 4: 导入导出

**User Story:** 作为审计人员，我希望 D4-1 的导入导出与新键模型一致，缺科目码时拒绝而非猜测，往返后受管字段逐字段一致。

#### Acceptance Criteria

1. WHEN 导入/导出 D4-1 THEN 使用 `D4-1-rows` 与 per-field 键；数据列包含区块、行键、项目、科目码及六个金额字段，派生列不作为最终输入。
2. WHEN 科目码缺失或无法映射 THEN 拒绝该行或转人工并报告原因；不得归主营或自动猜测。
3. WHEN round-trip THEN label、accountCode、六个金额、rowId/source 逐字段一致，sectionKey 由已确认 scope 计算；派生小计/合计/差异/变动率重算。
4. WHEN 导入后刷新 THEN 清单和全部 per-field 键原子刷新，HTML 与 Excel 读取同一快照。

### Requirement 5: 证据与守卫

**User Story:** 作为交付负责人，我希望 D4-1 的双向链路、公式、导入导出都有真栈证据与可复现守卫，杜绝"标注绿而实际断裂"。

#### Acceptance Criteria

1. WHEN 验收双向链路 THEN 必须浏览器实测进在线编辑走 USER_SYNC_PREFIX（store-projection/materialize 200 + callback 四项）、OO 挂载、OO 改值→HTML 显示→真库 per-field 快照，并覆盖冲突、只读、失败。
2. WHEN 验收公式 THEN 必须测试 effective definition、preset/custom/version/hash、F-SHELL 调用链、DAG 失败隔离及 HTML/OO 数值一致。
3. WHEN 验收导入导出和 scope THEN 必须测试三方合并、缺码拒绝、其他业务收入不丢失、round-trip 和 D4-1 快照不被 TB 偷换。
4. WHEN 交付 THEN 三件套必须通过 AC→Property→task 引用检查，tasks 的 waves JSON 唯一且所有任务为数字、未开发任务不得勾选。

## Correctness Properties

### Property 1
**Validates: Requirements 1.2, 1.4**
同一基线的 HTML/Excel 并发修改必须按版本三方合并；冲突不得静默覆盖。

### Property 2
**Validates: Requirements 2.2, 3.2**
任一 cell 的 HTML 与 OO 结果来自同一 effective definition，preset/custom 版本和哈希一致。

### Property 3
**Validates: Requirements 2.3, 4.3**
主营/其他两区动态行（各带稳定 rowId）经 materialize→extract 往返后，label、accountCode、source、sectionKey 和六个金额逐字段一致；两区 rowId 各自唯一、按 table_key 归属不串区；E/I/小计/合计/差异派生列由公式重算，不参与回写比对。

### Property 4
**Validates: Requirements 2.4, 3.4**
模式切换不发布 TB；只有人工确认动作可发布，且发布来源是 D4-1 审定快照。

### Property 5
**Validates: Requirements 2.1, 3.3**
缺码、缺 scope 或非法引用不会猜测取数，而是拒绝或进入人工路径。

### Property 6
**Validates: Requirements 1.3, 3.4**
普通值投影不改变 OO 公式字节，授权公式编辑经 F-SHELL 后可提交新定义。
