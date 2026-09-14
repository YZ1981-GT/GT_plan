# Design Document

## Overview

在模板库「公式管理」页签（`FormulaTab.vue`）把**已建成的通用预设能力** surface 出来，并新增「自定义公式」入口。核心原则是**复用不重造**：通用预设 = `formula_presets_seed.json` 经 `preset_library` 收敛库（已存在）；浏览/编辑复用 `GtFormulaPresetDialog` + `GtFormulaEditDialog`（已存在）。**唯一实质新增**是「自定义预设的隔离存储 + 写入通道」——一个与致同基线 seed 隔离的 `formula_custom_presets.json`，作为 `preset_library` 的额外收敛源（`source='custom'`，同键优先于通用），并镜像已有 `upsert_seed_presets` 加一个 `upsert_custom_presets` + 一个受权限门控的写端点。

**范围边界**：本 spec 处理**平台级**通用/自定义预设（模板库是全局跨项目页）。项目级 per-project 自定义公式仍走既有 `wp_formula`（底稿页内编辑），不在本 spec。

**🔴 平台级作用面（治理依据）**：`build_preset_library` 的结果被 `draft_refresh_service`（一键刷新/底稿生成套用预设）+ `report_note_linkage` / `report_note_references`（报表↔附注勾稽）消费。因此平台级自定义预设一经加入，会**对所有项目的底稿生成/刷新平台级生效**（与通用预设一致，这正是「所有企业通用 + 自定义扩充」的语义）。正因作用面是平台级，写入端点 `require_role`（admin/业务合伙人）为硬门控——普通角色只读浏览、不能新增平台级自定义预设。

## Architecture

```
FormulaTab.vue（公式管理页签）
  ├─ 顶部「通用 vs 自定义」框架条（新增，说明+入口，只读三子页不动）
  ├─ 现有三子页：预填充/报表/跨底稿引用（只读，零回归）
  └─ 「公式预设库」按钮 → 复用 GtFormulaPresetDialog
                              ├─ 说明文档 tab（GET /reporting-instructions，单一源）
                              └─ 预设浏览 tab（GET /presets/inventory + /presets/page）
                                   每条带 source → tag「通用/自定义」
                                   ➕新建/编辑 → GtFormulaEditDialog（三类型+选址+校验）
                                   @edit-formula → 宿主调 POST /presets/custom 持久化到 custom

后端 formula_management router
  ├─ GET /presets/inventory        （已存在，条目 source 已含）
  ├─ GET /presets/page             （已存在，条目 source 已含）
  ├─ GET /reporting-instructions   （已存在，单一源）
  └─ POST /presets/custom          （新增，require edit role，full_resolve 校验后 upsert_custom_presets）

preset_library.py
  build_preset_library():
    ordered = [ load_custom_presets(),   ← 新增源，置最前 → 同键覆盖通用
                load_seed_presets(),      ← 致同基线（通用）
                convert_prefill/check/wide_table ]  ← 通用收敛源
    去重 (page_key, target_cell) 首个赢 → 自定义优先
  load_custom_presets()  ← 读 formula_custom_presets.json（source='custom'）
  upsert_custom_presets()← 镜像 upsert_seed_presets，只写 formula_custom_presets.json

数据文件
  formula_presets_seed.json      （通用基线，本 spec 不写不改语义）
  formula_custom_presets.json    （新增，自定义，初始空 presets:[]）
```

## Components and Interfaces

### 后端

**`preset_library.py`（改，additive）**
- `CUSTOM_PATH = PRESET_DIR / "formula_custom_presets.json"`
- `load_custom_presets() -> list[PresetEntry]`：读 `formula_custom_presets.json`，每条 `source='custom'`（镜像 `load_seed_presets`，文件缺失/空返 `[]`）。
- `build_preset_library(...)`：`ordered` 列表**把 `load_custom_presets()` 置于 `load_seed_presets()` 之前**，去重「首个赢」使自定义同键覆盖通用；`source:custom` 计入 stats。**🔴 custom 与 `include_sources` 正交、恒前置**（`include_sources` 只控制 prefill/check/wide_table 三个**收敛源**是否并入；custom 与 seed 同属**显式预设源**，两个分支都含）。**零回归依据 = custom 初始为空**：空 custom 时 `[custom=[], seed, ...]` 去重结果与改前 `[seed, ...]` 逐字节一致 → `include_sources=False` 的既有调用方（`seed_formula_presets.py --seed-only` + `test_seed_pilot_covers_d_cycle_report_note` / `test_seed_ref_grammar`）不受影响（characterization 锁定）。
- `upsert_custom_presets(entries) -> dict[str,int]`：镜像 `upsert_seed_presets`，按 `(page_key,target_cell)` 幂等写 `formula_custom_presets.json`，**绝不触碰 `formula_presets_seed.json`**。

**`formula_import_export.py` router（改，additive；prefix `/api/formula-management`，presets/import-export 端点均在此）**
- `POST /api/formula-management/presets/custom`：body = `{page_key, target_cell, expression, formula_type, refs, description}`。`require_role`（admin/partner，与既有编辑门控一致）。落库前**复用 `import-data` 的逐条 `full_resolve`/引用校验路径**（不另造校验），悬空引用返 422（携悬空清单，不落库）；通过则 `upsert_custom_presets` 写入 `formula_custom_presets.json`，返回 `{inserted, updated, total}`。
- `GET /presets/inventory` / `GET /presets/page`：**已返回 `source` 字段**，无需改结构；前端据 `source` 判「通用（seed/prefill/check_presets/wide_table）/ 自定义（custom）」。附加只读派生 `is_custom = source=='custom'`（additive，前端亦可直接由 source 派生）。
- **🔴 边界（不动既有 import 行为）**：现有 `POST /import-export/import-data` 仍走 `upsert_seed_presets`（批量导入写入**通用基线 seed**，属既有 admin 批量流，本 spec 不改）。新增 `POST /presets/custom` 走 `upsert_custom_presets`（隔离 custom 文件）。二者持久化目标不同：import-data=基线扩充、presets/custom=自定义隔离。

### 前端

**`FormulaTab.vue`（改，additive）**
- 顶部新增框架条：「平台通用预设公式（所有企业通用，只读）」说明 + 「公式预设库」按钮。按钮打开 `GtFormulaPresetDialog`。
- 现有三子页（预填充/报表/跨底稿引用）**保持不变**（Req 5.2）。
- 引入 `GtFormulaPresetDialog`，监听 `@edit-formula`：调新增 `saveCustomPreset` 持久化到 custom（现有默认只 `ElMessage`）。
- 权限：非编辑角色隐藏「公式预设库」的新建/编辑入口（浏览只读仍可）。用既有权限来源（`usePermissionMatrix` 或模板库现有角色判断）。

**`useFormulaImportExport.ts`（改，additive）**
- 新增 `saveCustomPreset(payload) -> {inserted,updated,total} | null`：`POST /api/formula-management/presets/custom`，走 http（带 Authorization），错误 `ElMessage.error`。

**`GtFormulaPresetDialog.vue` / `GtFormulaEditDialog.vue`（复用，尽量不改）**
- 预设列表每条按 `source` 显示「通用/自定义」tag（若 dialog 未显示 source，加一列/一个 tag，additive）。
- `edit-formula` 事件已存在，宿主（FormulaTab）接管持久化。

## Data Models

**PresetEntry（已存在，不改字段）**：`page_key / target_cell / expression / formula_type / refs / source / description / variant`。自定义条目 `source='custom'`。

**`formula_custom_presets.json`（新增）**：
```json
{
  "description": "公式预设库自定义条目（用户在致同通用基线之上新增，与 formula_presets_seed.json 隔离）。",
  "version": "2025-R1",
  "presets": []
}
```
结构与 `formula_presets_seed.json` 一致，独立文件。

## Correctness Properties

### Property 1: 通用预设来源单一
所有非自定义预设条目均来自 `preset_library` 的既有源（seed/prefill/check_presets/wide_table），不引入第二套通用数据源。
**Validates: Requirements 2.1, 2.2**

### Property 2: 自定义不写入通用基线
`upsert_custom_presets` 任意调用后，`formula_presets_seed.json` 内容逐字节不变；自定义只写 `formula_custom_presets.json`。
**Validates: Requirements 3.2, 5.1**

### Property 3: 来源标注正确
每条预设的 `source` 唯一确定其归属：`custom` → 自定义；其余（seed/prefill/check_presets/wide_table）→ 通用。前端 tag 与之一致。
**Validates: Requirements 1.1, 1.2, 3.3**

### Property 4: 自定义同键覆盖通用
当自定义与通用预设作用于同一 `(page_key, target_cell)` 时，`build_preset_library` 结果中该键的条目为自定义条目（custom 置于 seed 之前，去重首个赢）。
**Validates: Requirements 3.3**

### Property 5: 权限门控双层
无编辑权角色调 `POST /presets/custom` 返 403；前端对无编辑权角色隐藏/禁用新建、编辑入口。
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 6: 无效引用拦截
`POST /presets/custom` 对悬空/无法解析引用的公式返 422 且不落库（`formula_custom_presets.json` 不变）。
**Validates: Requirements 3.4**

### Property 7: 零回归
未使用新入口时，`FormulaTab` 三子页只读展示与改动前逐字节等价；`build_preset_library` 的既有收敛口径（seed∪prefill∪check∪wide_table 去重）在 custom 为空时结果不变；`GtFormulaPresetDialog`/`GtFormulaEditDialog` 在 NoteTemplateTab/ReportConfigTab/WpTemplateDetail 的既有行为不变。
**Validates: Requirements 5.1, 5.2, 5.3**

## Error Handling

- `POST /presets/custom` 权限不足 → 403（复用 `require_role`）；引用悬空 → 422 携悬空引用清单，不落库。
- `formula_custom_presets.json` 缺失/损坏 → `load_custom_presets` 容错返 `[]`（与 `load_seed_presets` 一致），不阻断 `build_preset_library`。
- 前端 `saveCustomPreset` 失败 → `ElMessage.error` 展示后端 detail，不静默。
- 前端隐藏入口仅为体验，后端 `require_role` 为唯一防线（Req 4.3）。

## Testing Strategy

- **后端 pytest**：`load_custom_presets`/`upsert_custom_presets` 幂等 + seed 不被写（P2）；`build_preset_library` custom 优先（P4）+ custom 为空时口径不变（P7）；`POST /presets/custom` 权限（P5）+ 悬空拦截（P6）契约测试；来源标注（P3）。
- **后端 characterization 安全网**：Wave0 先锁 `build_preset_library` 现有 stats/去重、`formula_presets_seed.json` 只读、三子页所依赖端点响应形状。
- **前端 vitest**：来源判定（source→通用/自定义）纯逻辑、权限门控（无编辑权入口禁用）纯逻辑。
- **前端组件**：`FormulaTab.vue` diagnostics 全清 + Vite transform 200。
- **Playwright round-trip**：模板库 → 公式管理 → 打开公式预设库 → 浏览通用预设（tag=通用）→ 新建自定义（tag=自定义）→ 落 `formula_custom_presets.json` → 复查 seed 未变 → 清理，0 console error。
