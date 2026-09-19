# Requirements Document

## Introduction

本特性合并「自定义底稿公式绑定 + 编制信息表头」两条需求线，**已于 2026-06-03 在代码库落地**（spec `custom-workpaper-formula-binding`），**复用既有能力而非重建**：

- 既有 `FormulaEditDialog.vue`（1185 行）已完整实现"弹窗选址"机制（8 类取数函数 TB/ROW/NOTE/WP/REPORT/AUX/PREV/SUM_* 点击弹窗鼠标选单元格 + 🎯 目标单元格定位弹窗 + 数据源一览 + `PICKER_FUNCTIONS` 机制）。
- 既有 `AddressRegistryService`（`backend/app/services/address_registry.py`，841 行）已实现统一地址坐标注册表（按 project×year×template_type×domain 缓存，L1 内存 + L2 Redis，`AddressEntry` 含 uri/domain/source/path/cell/label/formula_ref/row_code/account_code/wp_code）。
- 既有 `formula_engine` + `WP()/NOTE()/REPORT()` 联动函数已实现底稿↔报表↔附注联动。

本特性聚焦"**打通链路**"：让自定义上传底稿解析出的真实单元格地址坐标进入地址注册表、被公式编辑器弹窗选到、自定义底稿进入委派人员可编辑库、并纳入联动重算；以及把编制信息表头从 B-Index 提升到 workpaper 级所有页签共享。

本特性分为两大需求群：
- **需求群 A — 底稿编制信息表头改造**（Requirements 1-3）
- **需求群 B — 自定义底稿公式绑定 + 地址坐标弹窗选择**（Requirements 4-9）

> **实现说明（2026-06-03）**：设计阶段 9 个集成点已在 `design.md`「现状勘察」中实证并落地；下文 AC 以**当前代码行为**为准。与 AC 字面略有差异处见各 Req 脚注（如复核人数据源、网格只读）。

## Glossary

- **Workpaper（底稿）**: 一份审计底稿文件，对应 `working_paper` 表一行，可含多个 sheet（页签）。
- **WP_Renderer（底稿渲染器）**: 前端 `GtWpRenderer.vue`，按 componentType 分发到子组件渲染底稿内容区，多 sheet 共享。
- **Preparation_Header（编制信息表头）**: 展示被审计单位/编制人/复核人/截止日/编制时间/复核日期/索引号等元信息的区域。当前仅存在于 B-Index（`GtBIndex.vue`）。
- **WP_Preparation_Header_Component（编制信息表头组件）**: 已实现 `GtWpPreparationHeader.vue`，挂在 `GtWpRenderer` 内容区上方、所有 sheet 共享、可折叠。
- **Address_Registry（地址坐标注册表）**: 后端 `AddressRegistryService`，统一管理可引用数据坐标，供公式编辑、溯源跳转、有效性校验使用。
- **Address_Entry（地址条目）**: 注册表中的一条可引用坐标，`AddressEntry` dataclass，含 uri/domain/source/path/cell/label/formula_ref 等字段。
- **WP_Domain（底稿域）**: 地址注册表中 domain='wp' 的条目集合，URI 形如 `wp://{wp_code}/{cell}`（path 承载单元格；legacy `#` 仅兼容解析）。
- **Formula_Edit_Dialog（公式编辑器）**: 前端 `FormulaEditDialog.vue`，提供公式配置 + 取数函数弹窗选址 + 目标单元格定位。
- **Picker_Functions（弹窗选址函数）**: `FormulaEditDialog` 中需弹窗鼠标选址的函数集合，当前为 `['TB','SUM_TB','ROW','SUM_ROW','NOTE','WP','REPORT','AUX','PREV']`。
- **Custom_Workpaper（自定义底稿）**: 用户通过"自定义新增程序 + 上传模板"创建、上传 Excel 解析入库的底稿，其单元格与标准底稿固定列不同。
- **Parsed_Data（解析数据）**: `working_paper.parsed_data`（JSONB），存储自定义上传底稿 Excel 解析后的单元格内容（含单元格地址如 B5/C12 及行名称）。
- **Standard_WP_Mapping（标准底稿映射）**: `backend/data/wp_account_mapping.json`，206 条标准底稿固定列定义（审定数/未审数/期末等），当前 `build_workpaper_entries` 唯一数据源。
- **Formula_Engine（公式引擎）**: 后端公式求值单内核 `formula_engine`，支撑 WP/NOTE/REPORT 等联动函数。
- **Delegated_Editable_Library（委派可编辑库）**: 委派人员可在编辑器中打开编辑的"待执行底稿"集合，对应已真正生成 `working_paper` 记录的底稿。
- **Period_End（截止日）**: 项目审计期末日，来源 `projects.audit_period_end`。
- **Preparer（编制人）**: 底稿编制人，来源 `project_assignments` 中 preparer 角色派单人员姓名（`staff_members.name` 经 `project_assignments.staff_id`）。
- **Reviewer（复核人）**: 编制信息表头「复核人」；**实现**取 `project_assignments` 中 `reviewer`/`manager` 角色姓名（`staff_members.name`），非底稿复核操作审计轨迹。
- **WP_Code（索引号）**: 底稿索引编码，存于 `wp_index.wp_code`。

## Requirements

---

## 需求群 A — 底稿编制信息表头改造

### Requirement 1: 编制信息表头提升到 workpaper 级共享

**User Story:** As an 审计助理, I want 编制信息表头在底稿所有页签共享展示, so that 无论查看哪个 sheet 都能看到统一的编制元信息，不再局限于 B-Index 页签。

#### Acceptance Criteria

1. WHEN WP_Renderer 渲染一份底稿, THE WP_Preparation_Header_Component SHALL 显示在 WP_Renderer 内容区的所有 sheet 之上（sheet 切换不重置其显示）。
2. WHEN 用户在同一底稿内切换 sheet, THE WP_Preparation_Header_Component SHALL 保持显示且内容不随 sheet 变化。
3. WHEN 用户点击折叠控件, THE WP_Preparation_Header_Component SHALL 在展开与折叠状态之间切换，折叠后仅占用最小高度。
4. WHILE WP_Preparation_Header_Component 处于折叠状态, THE WP_Preparation_Header_Component SHALL 保留再次展开的入口控件。
5. THE WP_Preparation_Header_Component SHALL 使用 GT 紫设计令牌（`--gt-color-primary` 等 `gt-tokens.css` 定义的变量）进行样式渲染，不使用 Element 默认蓝作为颜色来源。

### Requirement 2: 编制信息字段自动填充

**User Story:** As an 审计助理, I want 编制信息表头各字段从项目与底稿数据自动填充, so that 我无需手工录入即可看到准确的编制元信息。

#### Acceptance Criteria

1. WHEN WP_Preparation_Header_Component 加载某底稿的编制信息, THE WP_Preparation_Header_Component SHALL 将"编制人"填充为该项目 `project_assignments` 中 preparer 角色派单人员的姓名（取自 `staff_members.name`）。
2. WHEN WP_Preparation_Header_Component 加载某底稿的编制信息, THE WP_Preparation_Header_Component SHALL 将"截止日"填充为 `projects.audit_period_end`。
3. WHEN WP_Preparation_Header_Component 加载某底稿的编制信息, THE WP_Preparation_Header_Component SHALL 将"复核人"填充为项目派单复核相关人员姓名（`project_assignments` 中 reviewer/manager → `staff_members.name`；**非**底稿级复核操作留痕）。
4. WHEN WP_Preparation_Header_Component 加载某底稿的编制信息, THE WP_Preparation_Header_Component SHALL 将"编制时间"填充为该底稿首次编制的编辑时间（`working_paper.created_at`）。
5. WHEN WP_Preparation_Header_Component 加载某底稿的编制信息, THE WP_Preparation_Header_Component SHALL 将"索引号"填充为该底稿模板的 `wp_index.wp_code`。
6. IF 某字段对应的数据源记录缺失（如无 preparer 派单、`audit_period_end` 为 NULL、底稿尚无复核人）, THEN THE WP_Preparation_Header_Component SHALL 对该字段显示占位符"—"且不影响其他字段与页面渲染。

### Requirement 3: 删除"会计期间"字段

**User Story:** As an 审计助理, I want 编制信息表头不再包含"会计期间"字段, so that 表头信息精简、避免与"截止日"语义重复。

#### Acceptance Criteria

1. THE WP_Preparation_Header_Component SHALL 不展示"会计期间"字段。
2. WHEN 编制信息表头从 B-Index 迁移到 workpaper 级, THE 系统 SHALL 移除 B-Index 原有的"会计期间"字段展示。
3. WHERE 底稿数据中存在历史"会计期间"值, THE WP_Preparation_Header_Component SHALL 忽略该值而不渲染对应字段。

---

## 需求群 B — 自定义底稿公式绑定 + 地址坐标弹窗选择

### Requirement 4: 自定义上传底稿解析单元格注册进地址注册表

**User Story:** As a 委派编制人员, I want 自定义上传底稿解析出的真实单元格地址坐标与名称进入地址注册表的底稿域, so that 公式编辑器能够选到这些自定义底稿的单元格。

#### Acceptance Criteria

1. WHEN Address_Registry 构建某项目的 WP_Domain 条目, THE Address_Registry SHALL 在保留 Standard_WP_Mapping（`wp_account_mapping.json`）固定列条目的同时，追加该项目自定义底稿 `working_paper.parsed_data` 中解析出的单元格条目。
2. WHEN Address_Registry 为一个自定义底稿解析单元格生成 Address_Entry, THE Address_Entry SHALL 包含该单元格的地址坐标（如 B5）作为 cell、行名称作为 label 的组成部分、以及对应底稿的 wp_code。
3. WHEN Address_Registry 为自定义底稿单元格生成 Address_Entry, THE Address_Entry SHALL 设置 domain 为 'wp' 且 uri 形如 `wp://{wp_code}/{cell}`，并生成对应的 `WP('{wp_code}','{cell}')` formula_ref。
4. IF 某自定义底稿 `parsed_data` 为空或缺失, THEN THE Address_Registry SHALL 跳过该底稿的单元格注册且不影响标准底稿条目与其他底稿条目的构建。
5. WHERE 自定义底稿单元格地址与标准底稿固定列存在相同 wp_code, THE Address_Registry SHALL 同时保留两类条目而不相互覆盖。

### Requirement 5: 公式编辑器弹窗选择自定义底稿单元格

**User Story:** As a 委派编制人员, I want 在公式编辑器中点击 WP 函数按钮时能弹窗浏览并鼠标选定自定义底稿的真实单元格, so that 我无需手记单元格地址即可绑定公式引用。

#### Acceptance Criteria

1. WHEN 用户在 Formula_Edit_Dialog 中点击 WP 取数函数按钮, THE Formula_Edit_Dialog SHALL 弹出底稿选择弹窗并列出包含自定义底稿单元格在内的可选 Address_Entry。
2. WHEN 弹窗展示自定义底稿单元格, THE Formula_Edit_Dialog SHALL 同时显示单元格的地址坐标与行名称标签，供用户辨识。
3. WHEN 用户在弹窗中点击某个自定义底稿单元格, THE Formula_Edit_Dialog SHALL 将对应的 `WP('{wp_code}','{cell}')` 引用插入到当前激活的公式表达式中。
4. WHILE 弹窗处于打开状态, THE Formula_Edit_Dialog SHALL 提供按编码或名称搜索过滤的能力。
5. IF 当前项目地址注册表中无可选的自定义底稿单元格, THEN THE Formula_Edit_Dialog SHALL 显示空态提示且保留标准底稿固定列的可选项。

### Requirement 6: 公式编辑器接入自定义底稿编辑场景

**User Story:** As a 委派编制人员, I want 在编辑自定义底稿时也能打开公式编辑器配置公式并写入目标单元格, so that 自定义底稿可像报表/附注行一样具备公式能力。

#### Acceptance Criteria

1. WHEN 用户在自定义底稿编辑视图中触发公式编辑, THE Formula_Edit_Dialog SHALL 以该自定义底稿为上下文打开。
2. WHEN Formula_Edit_Dialog 在自定义底稿场景打开, THE Formula_Edit_Dialog SHALL 允许用户通过目标单元格定位弹窗选择该自定义底稿的写入目标单元格。
3. WHEN 用户保存公式, THE 系统 SHALL 将公式表达式与目标单元格持久化到独立表 `wp_formula`（`PUT /api/workpapers/{wp_id}/formulas`），并按表达式求值结果写回 `parsed_data.html_data[sheet].cells[target_cell]` 供网格展示。
4. IF 用户保存的公式引用了地址注册表中不存在的地址, THEN THE 系统 SHALL 返回 422 + `issues` 列表且不写库（`validate_formula_refs`）。

### Requirement 7: 自定义底稿进入委派可编辑库

**User Story:** As a 项目经理, I want 自定义新增的底稿在裁剪处理后真正生成可编辑的底稿记录, so that 委派人员能在编辑器中打开并编辑该自定义底稿。

#### Acceptance Criteria

1. WHEN 一个自定义底稿完成裁剪处理并被指派, THE 系统 SHALL 为其生成可在编辑器中打开的 `working_paper` 记录，纳入 Delegated_Editable_Library。
2. WHEN 委派人员打开已生成的自定义底稿, THE WP_Renderer SHALL 通过 `componentType=custom` 的 `GtCustomWpEditor` 展示网格并允许配置公式（**网格只读** `GtGridSheet`；公式经工具栏「公式」按钮编辑，非 Excel 式单元格直编）。
3. WHERE 自定义底稿已关联 `wp_index` 占位记录但尚未生成 `working_paper`, THE 系统 SHALL 在底稿列表中以"未生成"状态标识且提供生成入口。
4. IF 自定义底稿尚未生成 `working_paper` 记录, THEN THE 系统 SHALL 阻止公式编辑器以该底稿为编辑上下文打开并显示友好提示。

### Requirement 8: 自定义底稿单元格纳入联动重算

**User Story:** As a 委派编制人员, I want 自定义底稿单元格被其他公式引用后参与联动重算与失效传播, so that 自定义底稿与现有底稿/报表/附注模块的衔接保持数据一致。

#### Acceptance Criteria

1. WHEN 某自定义底稿单元格（`WP('{wp_code}','{cell}')`）取值因保存公式/写回 `parsed_data` 而变更, THE 系统 SHALL 将同项目其它 `wp_formula` 表达式中引用该单元格的底稿标记 `working_paper.prefill_stale=true`（`wp_formula_linkage_service` 动态扫描），并 best-effort 调用 `StalePropagationEngine.on_change` 走静态依赖图 BFS。
2. WHEN 自定义底稿单元格被注册进 WP_Domain 后某公式引用它, THE Formula_Engine（`WPExecutor`）SHALL 能按单元格地址 `^[A-Z]+\d+$` 从 `parsed_data` 解析取值。
3. WHEN 自定义底稿的 `parsed_data` 更新并 commit, THE 系统 SHALL 调用 `touch_wp_registry`/`touch_after_parsed_data_commit` 使 WP 域注册表缓存失效（router 层写路径已接；service 层裸 SQL 写仍靠 TTL 120s）。
4. IF 被引用的单元格在 `parsed_data` 中不存在, THEN `WPExecutor` SHALL 返回 `0` 且 trace 记 `not_found`，不中断整体求值。

### Requirement 9: 降级与友好提示

**User Story:** As a 委派编制人员, I want 在底稿未生成或解析数据缺失等异常场景下系统给出友好提示而非崩溃, so that 我能理解当前状态并采取下一步操作。

#### Acceptance Criteria

1. IF 自定义底稿尚未生成或 `parsed_data` 缺失, THEN THE Formula_Edit_Dialog SHALL 在 WP 选择弹窗中显示空态提示并保留标准底稿固定列选项，而不抛出运行时错误。
2. IF Address_Registry 在构建 WP_Domain 条目时读取某底稿 `parsed_data` 失败, THEN THE Address_Registry SHALL 记录告警日志、跳过该底稿并继续构建其余条目。
3. WHEN 任一编制信息字段或自定义底稿单元格数据缺失, THE 相关组件 SHALL 显示占位提示且保持页面其余部分正常渲染。
4. THE 降级行为 SHALL 在中文场景（中文底稿名、中文行名称、中文项目名）下保持一致，不出现编码错误或崩溃。

---

## 正确性属性（Correctness Properties，供后续 PBT）

> 以下属性供设计阶段细化为 hypothesis 属性测试（用户铁律：`max_examples=5`，禁默认 100）。每条标注属性类型与对应需求。

### P1 — WP_Domain 条目并集不丢失（Invariant，Req 4）
对任意项目，`build_workpaper_entries` 构建结果中标准底稿固定列条目集合恒为结果的子集；追加自定义底稿单元格后，标准条目数量不减少。
- 形式：`set(standard_entries) ⊆ set(build_workpaper_entries(project))`

### P2 — URI / formula_ref 往返一致（Round-Trip，Req 4 / Req 5）
对任意自定义底稿单元格生成的 Address_Entry，其 `uri` 与 `formula_ref` 经现有 `formula_ref_to_uri` / `uri_to_formula_ref` 互转应回到等价表示。
- 形式：`uri_to_formula_ref(formula_ref_to_uri(e.formula_ref)) == e.formula_ref`（对 WP 域条目）；`uri` 为 `wp://{wp_code}/{cell}`，`formula_ref` 为 `WP('{wp_code}','{cell}')`
- 这是解析/序列化往返属性，是地址互转正确性的核心守护。

### P3 — 注册幂等（Idempotence，Req 4 / Req 8）
对同一份未变化的 `parsed_data` 重复构建 WP_Domain，产出的 Address_Entry 集合恒等（去重后数量与内容一致）。
- 形式：`build(parsed_data) == build(build_then_rebuild(parsed_data))`

### P4 — 弹窗可选项 ⊆ 注册表条目（Metamorphic，Req 5）
公式编辑器 WP 弹窗展示的可选单元格集合，恒为该项目 Address_Registry WP_Domain 条目集合的子集（不凭空出现未注册地址）。
- 形式：`set(picker_options) ⊆ set(registry.wp_domain_entries)`

### P5 — 解析数据缺失不崩（Error Condition，Req 4 / Req 9）
对任意 `parsed_data ∈ {None, {}, 结构异常的 dict}`，`build_workpaper_entries` 恒不抛异常，且仍返回包含标准底稿固定列条目的结果。
- 形式：`∀ bad_input. build_workpaper_entries(bad_input) does not raise ∧ standard_entries ⊆ result`

### P6 — 公式引用有效性校验完备（Metamorphic，Req 6 / Req 8）
对任意公式，若其引用的某 WP 地址不在注册表中，则 `validate_formula_refs` 必返回包含该引用的 `not_found` 项；若全部引用均已注册，则返回空问题列表。
- 形式：`(∃ ref ∉ registry) ⟺ (validate_formula_refs(formula) 含该 ref 的 not_found)`

### P7 — 编制信息字段缺失降级为占位符（Invariant，Req 2 / Req 9）
对任意项目/底稿元数据组合（含缺失字段），编制信息表头的每个字段渲染值要么为真实数据，要么为占位符"—"，永不为 `null`/`undefined`/抛错。
- 形式：`∀ field. render(field) ∈ {real_value, "—"}`

### P8 — "会计期间"字段恒不渲染（Invariant，Req 3）
对任意底稿数据（含历史含"会计期间"值的数据），编制信息表头渲染输出中恒不包含"会计期间"字段。
- 形式：`∀ data. "会计期间" ∉ rendered_fields(data)`

### P9 — 缓存失效后读到最新（Round-Trip / Metamorphic，Req 8）
当某项目自定义底稿 `parsed_data` 更新并触发 WP_Domain 缓存失效后，下一次读取该项目 WP_Domain 条目应反映更新后的单元格集合（不返回陈旧缓存）。
- 形式：`update(parsed_data) ; invalidate(wp) ; get(wp) == build(updated_parsed_data)`

### P10 — 自定义单元格条目完备性（Invariant，Req 4）
- 测试：`test_custom_entry_complete_pbt.py`

### P11 — WP() 单元格地址求值（Req 8.2）
- 测试：`test_wp_eval_cell.py`

### P12 — 公式持久化往返（Req 6.3）
- 测试：`test_wp_formula_roundtrip_pbt.py`

### P13 — 弹窗搜索过滤（Req 5.4）
- 测试：`wpFormulaPicker.spec.ts`（vitest）

### P14 — working_paper 幂等生成（Req 7.1）
- 测试：`test_ensure_wp_idempotent_pbt.py`

---

## 实现状态与验收（2026-06-03）

| 集成点 | 状态 | 主要产物 |
|--------|------|----------|
| ① 注册表扩展 parsed_data | ✅ | `extract_custom_cells`、`_build_custom_wp_cell_entries` |
| ② WP 弹窗选址 | ✅ | `FormulaEditDialog` + address-registry |
| ③ working_paper 生成 | ✅ | `WorkpaperGenerationService`、`assign` 钩子 |
| ④ wp_formula 表 | ✅ | V052、`WpFormula`、`wp_formula` router |
| ⑤ WP() 单元格求值 | ✅ | `WPExecutor` + `extract_custom_cells` |
| ⑥ 编制信息表头 | ✅ | `GtWpPreparationHeader`、`preparation-info` |
| ⑦ 求值写回 + 联动 | ✅ | `wp_formula_eval_service`、`wp_formula_linkage_service` |
| ⑧ touch 缓存失效 | ✅ router 层全覆盖 + `test_touch_wp_registry_wiring.py` |

**测试证据**：后端 spec 相关 pytest **44 passed / 2 skipped**；vitest `wpFormulaPicker` **4 passed**；Playwright `test:e2e:custom-wp` **3 passed**（9980+3030）。

**部署残留**：目标环境须手工执行 **V052**（本地 PG 已应用）；`wopi`/`ocr` 等 service 层写 `parsed_data` 未接 `touch`（TTL 兜底）。

---

## 迭代说明

- 本 spec 三件套已与实现对齐；后续增强（全量依赖图运行时建边、复核人改审计轨迹、网格可编辑）应新开 spec 或任务，勿在本文件混写「待实施」。
