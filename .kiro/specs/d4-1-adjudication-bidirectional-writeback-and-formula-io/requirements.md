# Requirements Document

## Introduction
D4-1 是 D4 收入循环的审定枢纽，连接 D4-2/D4-3 明细、D4-4 调整、四表取数、`trial_balance` 与审计说明。本文只描述 D4-1 的 HTML 结构化视图、OnlyOffice 表征、公式定义、导入导出和审定回写；不预设模板与其他表同册。实施前必须由运行时模板 finder 与索引核定真实 sheet、行身份、列映射和可插桩性。

## Glossary
- **F-SHELL**：公式壳层，保存 `wp_formula` 的 effective definition（preset/custom 单一真源）。
- **快照**：D4-1 页面审定数快照，是审定发布来源，不偷换为 TB。
- **per-field 键**：`D4-1-{rowId}-{field}` 六类金额字段键；清单键 `D4-1-rows`。

## 约束与术语
- HTML、Excel、平台内容存储均是同一内容的表征，写入统一经过 `ContentMutationService` 的版本校验、三方合并和 durable callback；禁止 Excel 优先和 last-write-wins。
- 公式的 preset/custom/effective definition 统一进入 F-SHELL 与 `wp_formula`。表达式、引用、参数共同参与定义哈希和版本；不得使用 `field_overrides` 或 remark 伪造公式库。
- OOXML 公式列使用 projection mask 仅防普通值投影覆盖；有权限的公式编辑必须解析为 effective definition，不能被 mask 禁止。
- 纯取数使用 `app/services/four_table/` 的 `ReportLineAccountSpec`、`select_leaves`、`aggregate_leaves` 和运行时 `tb_source_codes`；缺码必须拒绝或转人工确认，不臆测科目。
- TB 发布是独立的人工动作，不因切换 HTML/Excel 模式触发。D4-1 审定来源取 D4-1 底稿快照，不偷换为 TB。

## Requirements

### Requirement 1: 内容表征与冲突治理
**User Story:** 作为审计助理，我希望 D4-1 的 HTML 与 Excel 是同一内容的表征，以便双向编辑不丢改、冲突可见可恢复。

#### Acceptance Criteria
1. WHEN 实施 D4-1 THEN 必须先由运行时模板 finder/index 核定真实 workbook、tab、表头、行身份、公式格和字段映射；未核定不得预设同册或固定 cell。
2. WHEN HTML 或 Excel 写入 THEN 两者必须提交同一 `ContentMutationService` 契约，带基线版本并执行三方合并；冲突须保留、可见、可恢复，禁止 Excel 优先或 last-write-wins。
3. WHEN Excel 普通值投影 THEN 只能写受管字段，OO 公式 mask 保护公式字节；WHEN 用户编辑公式 THEN 必须走 F-SHELL 公式解析、权限、引用、DAG 和版本校验。
4. WHEN 任一写入失败或行身份缺失/重复/公式不支持 THEN 必须 fail-closed，保留原内容、标记失败或 blocked、展示中文错误，不得 markSynced 或把 null 转 0。
5. WHEN HTML/Excel 切换 THEN 不得自动发布 TB；只有用户明确执行“确认审定”且通过差异确认后才能发布。

### Requirement 2: 审定表业务数据与回写
**User Story:** 作为审计助理，我希望 D4-1 的取数、审定计算与 TB 发布来源可追溯，以便审定数不被偷换、发布是明确的人工动作。

#### Acceptance Criteria
1. WHEN D4-1 读取未审数、AJE、RJE 或 TB 核对数 THEN 必须使用四表服务和运行时 account scope；缺少合法 scope/code 时拒绝或进入人工选择。
2. WHEN 计算审定数、小计、合计、差异、变动率 THEN HTML 与 OO 必须消费同一 effective definition，结果逐 cell 一致；D4-1 审定快照是页面来源，不得以 TB 替代。
3. WHEN 用户编辑动态行 THEN 使用 `D4-1-rows` 清单及 `D4-1-{rowId}-{field}` 六类 per-field 键，保留 `accountCode`、`sectionKey`、`source`；禁止写旧整行 JSON。
4. WHEN 用户执行确认审定 THEN 先比较 D4-1 快照审定合计与 TB 核对值；差异绝对值大于 0.005 必须二次确认，取消不写，确认后独立人工发布 `6001`/`6051`，切模式不触发。
5. WHEN 只读或发布失败 THEN 编辑、增删行和发布入口均禁用/不写库，并给出可追溯错误。

### Requirement 3: 公式治理
**User Story:** 作为现场经理，我希望公式在预设基础上支持用户二次编辑且是单一真源，以便打通表间提取与表内计算、失败不静默转零。

#### Acceptance Criteria
1. WHEN D4-1 公式定义存在 THEN 必须覆盖本期/上期未审、AJE、RJE、审定数、小计、合计、TB核对、差异、变动率和 D4-2/D4-3 WP 引用；每条 `(sheet, cell_ref)` 唯一。
2. WHEN 公式被预设、修改、恢复默认或从 Excel 导入 THEN 均生成同一 effective definition 的 `wp_formula` 版本；custom 不覆盖 preset，恢复默认生成新版本。
3. WHEN 公式引用四表科目 THEN 必须通过 per-cycle account scope 与叶子聚合；缺码拒绝或人工，不允许以 `6001~6099` 等未核定范围臆测。
4. WHEN 公式求值失败 THEN 该公式及依赖项为 failed/blocked，不 ApplyValue、不转零；无依赖公式可继续。
5. WHEN 下游通过 WP 引用 D4-1 THEN 必须读取可审计快照或有效公式结果；业务导航 refs 不要求等于公式 refs，但二者都必须可追溯且不得互相冒充。

### Requirement 4: 导入导出
**User Story:** 作为审计助理，我希望 D4-1 导入导出用 per-field 键并对缺码拒绝，以便 round-trip 逐字段一致、不写孤儿数据。

#### Acceptance Criteria
1. WHEN 导入/导出 D4-1 THEN 使用 `D4-1-rows` 与 per-field 键；数据列包含区块、行键、项目、科目码及六个金额字段，派生列不作为最终输入。
2. WHEN 科目码缺失或无法映射 THEN 拒绝该行或转人工，并报告原因；不得归主营或自动猜测。
3. WHEN round-trip THEN label、accountCode、六个金额、rowId/source 逐字段一致，sectionKey 由已确认 scope 计算；派生小计/合计/差异/变动率重算。
4. WHEN 导入后刷新 THEN 清单和全部 per-field 键原子刷新，HTML 与 Excel 读取同一快照。

### Requirement 5: 证据与守卫
**User Story:** 作为质量控制复核合伙人，我希望双向链路、公式与导入导出都有行为守卫和实测证据，以便验收不假绿。

#### Acceptance Criteria
1. WHEN 验收双向链路 THEN 必须浏览器实测 OO 改值→HTML显示→真库 per-field 快照，并覆盖冲突、只读、失败和公式修改。
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
动态行经导出再导入后，清单、rowId、accountCode、source 和六个金额逐字段一致，派生列重算。
### Property 4
**Validates: Requirements 2.4, 3.4**
模式切换不发布 TB；只有人工确认动作可发布，且发布来源是 D4-1 审定快照。
### Property 5
**Validates: Requirements 2.1, 3.3**
缺码、缺 scope 或非法引用不会猜测取数，而是拒绝或进入人工路径。
### Property 6
**Validates: Requirements 1.3, 3.4**
普通值投影不改变 OO 公式字节，授权公式编辑经 F-SHELL 后可提交新定义。
