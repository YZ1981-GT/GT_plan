# Requirements Document

## Introduction

模板库「公式管理」页签（`FormulaTab.vue`）目前是**纯只读展示**（预填充公式 / 报表公式 / 跨底稿引用），既没有把「平台通用预设公式」明确框出来，也没有给用户新建/管理「自定义公式」的入口。用户诉求：**公式管理要预设一套所有企业通用的公式；自定义的交给用户自己设置。**

**🔴 关键前提（收敛，不重造）**：平台通用预设公式**已经存在且成熟**——`formula_presets_seed.json`（876+ 条）+ `preset_library.py`（seed ∪ prefill ∪ check_presets ∪ wide_table 读时收敛去重）+ Preset Inventory 逐页登记 + 覆盖度 + `GtFormulaPresetDialog.vue`（预设浏览/编辑）+ `GtFormulaEditDialog.vue`（统一公式编辑器）。本 spec 的任务是**把已有能力在「公式管理」页签正确 surface + 明确「通用 vs 自定义」边界 + 让用户能设置自定义公式**，**严禁**新建第二套预设系统/存储/编辑器。

「通用预设」= 平台内置、所有企业/项目共享的一套公式（`formula_presets_seed.json` 收敛库），只读展示。
「自定义公式」= 用户在通用基线之上新增/编辑的公式，独立于通用基线存储（不覆盖、不污染平台通用 seed）。

## Glossary

| 术语 | 含义 |
|------|------|
| 通用预设公式 | 平台内置、所有企业通用的一套公式，源 = `formula_presets_seed.json` 经 `preset_library.build_preset_library()` 收敛去重 |
| 自定义公式 | 用户在通用基线之上新增/编辑的公式，与通用基线隔离存储 |
| Preset Inventory | 逐页登记（page_key → formula_count + preset_status），`preset_library.build_inventory()` |
| page_key | 页面/sheet 标识：`workpaper:{wp_code}` / `report:{...}` / `note:{...}` |
| 三类型 | 公式类型：`auto_calc`（自动运算回填）/ `logic_check`（逻辑判断不改值）/ `reasonability`（合理性提示） |
| FormulaTab | 模板库「公式管理」页签组件 `FormulaTab.vue`（现只读三子页） |
| GtFormulaPresetDialog | 已有的公式预设库弹窗（说明文档 + 逐页预设浏览 + ➕新建公式） |
| GtFormulaEditDialog | 已有的统一公式编辑器（三类型 + 选址 + 校验） |

## Requirements

### Requirement 1: 公式管理页签明确区分「通用预设」与「自定义公式」

**User Story:** 作为审计人员，我打开模板库「公式管理」时，希望一眼看清哪些是平台内置、所有企业通用的预设公式，哪些是可以自己设置的自定义公式，避免误以为「只能看不能设」。

#### Acceptance Criteria

1. WHEN 用户进入「公式管理」页签 THEN 系统 SHALL 展示明确的「平台通用预设公式（所有企业通用）」区域，并标注其为只读、平台内置、跨项目共享。
2. WHEN 用户进入「公式管理」页签 THEN 系统 SHALL 提供「自定义公式」入口，说明自定义公式由用户自行设置、与通用基线隔离。
3. WHERE 现有三子页（预填充公式 / 报表公式 / 跨底稿引用）只读展示 THE 系统 SHALL 保留其现状不变（零回归），仅在其上层/入口处增加「通用 vs 自定义」的框架说明与入口。

### Requirement 2: 通用预设公式来自现有预设库（不重造）

**User Story:** 作为平台维护者，我希望「通用预设」直接复用已建成的 `formula_presets_seed.json` 收敛库，不要再造一套并行数据源导致漂移。

#### Acceptance Criteria

1. WHEN 展示通用预设公式 THEN 系统 SHALL 经现有 `preset_library`（`build_preset_library` / Preset Inventory / 覆盖度）或其既有 API 取数，不新增第二套预设存储。
2. WHEN 用户浏览通用预设 THEN 系统 SHALL 复用现有 `GtFormulaPresetDialog`（说明文档 + 逐页预设浏览），不新建等价弹窗组件。
3. IF 通用预设某页 `preset_status = pending`（承载公式但未预设）THEN 系统 SHALL 如实标注 pending，不臆造公式。

### Requirement 3: 自定义公式由用户自行设置，隔离于通用基线

**User Story:** 作为审计人员，我希望能在通用预设之外新建/编辑自己的公式，且我的自定义不会覆盖或污染平台通用预设。

#### Acceptance Criteria

1. WHEN 用户新建/编辑自定义公式 THEN 系统 SHALL 复用现有 `GtFormulaEditDialog`（三类型 + 选址 + 校验），不新建等价编辑器。
2. WHEN 自定义公式保存 THEN 系统 SHALL 将其持久化到与平台通用 seed 隔离的位置（复用现有自定义/用户公式存储通道），不写入平台通用 `formula_presets_seed.json` 覆盖通用基线。
3. WHEN 自定义公式与某通用预设作用于同一 page_key/target_cell THEN 系统 SHALL 明确以何者为准（自定义覆盖或并存），并向用户可见其来源（通用/自定义）。
4. IF 自定义公式引用无效（悬空引用/无法解析）THEN 系统 SHALL 在保存前拦截并提示，不静默落库错误公式。

### Requirement 4: 权限——通用只读、自定义受控

**User Story:** 作为平台管理者，我希望所有人都能查看通用预设，但只有具备权限的角色能新建/编辑公式，避免误改平台主数据。

#### Acceptance Criteria

1. WHERE 通用预设公式展示 THE 系统 SHALL 对所有可访问模板库的角色只读可见。
2. WHILE 用户角色不具备编辑权（非 admin / 业务合伙人 / 具备编辑权的项目角色）THE 系统 SHALL 禁用/隐藏新建、编辑自定义公式的入口。
3. WHERE 后端已有权限门控 THE 系统 SHALL 复用现有权限校验，前端隐藏与后端校验双层一致（前端隐藏不作为唯一防线）。

### Requirement 5: 零回归与复用约束

**User Story:** 作为平台维护者，我要求本次改动不破坏现有公式系统、模板库其他页签与既有预设/编辑弹窗的调用点。

#### Acceptance Criteria

1. WHEN 本次改动完成 THEN 系统 SHALL 不改动 `preset_library` 的收敛口径、`formula_presets_seed.json` 的既有条目语义、`GtFormulaPresetDialog` / `GtFormulaEditDialog` 在其它调用点（NoteTemplateTab / ReportConfigTab / WpTemplateDetail）的既有行为。
2. WHEN 未使用新入口 THEN 现有「公式管理」三子页只读展示 SHALL 与改动前逐字节等价。
3. WHERE 新增前端组件 THE 系统 SHALL 优先复用而非复制现有组件/composable（`useFormulaImportExport` / `GtFormulaPresetDialog` / `GtFormulaEditDialog`）。

### Requirement 6: 正确性属性可测

**User Story:** 作为质量负责人，我希望「通用 vs 自定义」的边界、来源标注、隔离存储有可测的正确性属性。

#### Acceptance Criteria

1. WHEN 编写测试 THEN 系统 SHALL 覆盖以下属性：通用预设来源单一（源自 preset_library）、自定义不写入通用 seed、来源标注正确（通用/自定义）、权限门控（无编辑权时入口禁用）、无效引用被拦截、现有三子页只读零回归。
2. WHERE 涉及后端 THE 系统 SHALL 以既有测试框架（pytest）补充契约/属性测试；WHERE 涉及前端 THE 系统 SHALL 以 vitest 覆盖纯逻辑（来源判定/边界/权限门控），组件渲染以 diagnostics + Vite transform 200 验证，关键路径 Playwright round-trip。
