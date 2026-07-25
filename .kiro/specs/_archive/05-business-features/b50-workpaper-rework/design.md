# B50 风险评估底稿改造 — Design

## Overview

保持单一专属组件 `GtB50RiskAssessment`（whole-wp）渲染模型，通过新增后端 render 策略（防 grid 兜底）、前端程序表 Tab、Tab3 结构扩列、双模式 toolbar 与引导弹窗，对齐源模板并补齐双模式，全程零回归。

## Architecture

保持"**单一专属组件 `GtB50RiskAssessment`（whole-wp）**"渲染模型不变，不拆包、不将 B50 转为 account_package（避免 4-Tab 组件被碎片化）。改造集中在：

```
render-config (GET /workpapers/{id}/render-config)
   └─ 新增 _b50_risk_assessment.py render 策略（返回结构化 dict，无 cells → 防 grid 兜底 shadow）
        ├─ component_type = "b50-risk-assessment"
        ├─ project_context = { client_name, audit_year, oo_sheet_map, program_available }
        └─ (无 html_data.cells)
   ↓
GtWpRenderer 据 componentType 分发 → GtB50RiskAssessment.vue
   ├─ Tab0 汇总程序表   → GtAProgramConsole（自加载 /procedure-tables/B50）
   ├─ Tab1 风险因素      → 现有（自加载 checklist_responses B50-T1-*）
   ├─ Tab2 报表层次      → 现有（B50-T2-*）
   ├─ Tab3 认定矩阵      → 扩列（余额/类别/会计估计）+ 引导弹窗（B50-T3-*）
   ├─ Tab4 特别风险      → 现有（B50-T4-*）
   └─ 双模式 toolbar：结构化 ↔ OnlyOffice（per-tab 源 sheet，健康检查 gate）
```

**🔴 关键防坑（B19/B2 同款）**：B50 是纯前端整册专属组件，若无后端 render 策略、且模板（程序表 43 行）产出 `html_data.cells`，会被 GtWpRenderer 的 `noRendererGridFallback` 用 `GtGridSheet` 兜底 shadow 掉专属组件（memory 记录 B19/B2 中招）。因此**必须**新增返回"无 cells 的结构化 dict"的 render 策略，并把 `b50-risk-assessment` 加入 `DEDICATED_COMPONENT_TYPES`。

## Components and Interfaces

### 后端

#### 2.1 新增 `backend/app/routers/wp_render_strategies/_b50_risk_assessment.py`

```python
async def render(ctx) -> dict:
    pc = await _load_project_context(ctx)   # client_name / audit_year
    return {
        "component_type": "b50-risk-assessment",
        "project_context": {
            "client_name": pc.client_name,
            "audit_year": pc.audit_year,
            "program_available": True,          # 程序表由 GtAProgramConsole 自加载
            "oo_sheet_map": {                    # 双模式 per-tab 源 sheet 解析
                "program":  {"source_wp_code": "B50",   "oo_sheet_name": "B50 汇总风险评估结果"},
                "tab1":     {"source_wp_code": "B50-1", "oo_sheet_name": "B50-1 汇总识别出的风险因素"},
                "tab2":     {"source_wp_code": "B50-2", "oo_sheet_name": "B50-2 财务报表层次风险"},
                "tab3":     {"source_wp_code": "B50-3", "oo_sheet_name": "B50-3认定层次风险评估"},
                "tab4":     {"source_wp_code": "B50-4", "oo_sheet_name": "B50-4 特别风险"},
            },
        },
        # 显式不返回 cells / html_data → 不触发 grid 兜底
    }
```

- 注册：`wp_render_strategies/__init__.py` 的 `RENDERER_DISPATCH["b50-risk-assessment"] = render`。
- `oo_sheet_name` 值必须与源 xlsx tab 名**完全一致**（已核对：`B50 汇总风险评估结果` / `B50-1 汇总识别出的风险因素` / `B50-2 财务报表层次风险` / `B50-3认定层次风险评估` / `B50-4 特别风险`）。

#### 2.2 注册表更新（防 grid shadow + OnlyOffice 白名单）

- `dedicated_component_types.py`：`DEDICATED_COMPONENT_TYPES`（WHOLE 集）加 `"b50-risk-assessment"`。
- `wp_classification_service.py`：`b50-risk-assessment` 已在 VALID 集（无需改）。
- render-config `_ONLYOFFICE_HTML_WHITELIST`：加 `"b50-risk-assessment"`（WHOLE−DISPATCH⊆WHITELIST 契约；此处 B50 有 DISPATCH，按现有契约核对是否需要加入，以契约测试为准）。
- 契约测试 `test_dedicated_component_registry_contract.py` 须仍通过。

#### 2.3 扩展 `/api/b50/scope-accounts`（Tab3 余额）

`backend/app/routers/b50_scope.py`（已存在）的 `scope-accounts` 返回结构扩为每项含 `balance`：

```python
{"accounts": [{"name": "货币资金", "cycle": "E", "balance": 609659228.53}, ...]}
```

- 数据源：`trial_balance` 按报表项目聚合期末审定额（audited 优先，回退 unadjusted），仅取重要科目（沿用既有阈值/聚合逻辑）。
- 前端 `importAccounts` 消费 balance 写入矩阵行。

### 前端

#### 3.1 `GtB50RiskAssessment.vue`（改造）

**新增 Tab0 汇总程序表**（activeTab 默认仍 tab3 不变，程序表插入首位）：
```vue
<el-tab-pane label="📋 汇总程序表" name="program">
  <GtAProgramConsole :wp-id="props.wpId" :project-id="props.projectId"
    :html-data="{}" :is-readonly="isReadonly" @navigate-sheet="onProgramIndexJump" />
</el-tab-pane>
```
- `GtAProgramConsole` 自加载 `/procedure-tables/B50`（memory 确认该 fallback 存在，`extractTableCode` 对 "B50" 命中）。
- `onProgramIndexJump(idx)`：B50-1→activeTab='tab1'、B50-2→'tab2'、B50-3→'tab3'、B50-4→'tab4'。

**双模式 toolbar**（复用 `useWorkpaperEntryDualMode`）：
```vue
<div class="b50-mode-toolbar">
  <el-segmented v-model="renderMode" :options="renderModeOptions" size="small" />
  <el-tag v-if="!dualMode.ooAvailable.value" type="warning" size="small">OO不可用</el-tag>
</div>
<GtOnlyOfficeSheet v-if="renderMode==='onlyoffice' && ooSourceWpId"
  :wp-id="ooSourceWpId" :sheet-name="ooSheetName" :project-id="props.projectId"
  :readonly="isReadonly" @fallback="() => dualMode.switchMode('html')" />
<div v-else-if="renderMode==='onlyoffice'" class="oo-not-instantiated">该子表未实例化，请用结构化模式</div>
<template v-else> ...现有 el-tabs... </template>
```
- `renderMode==='onlyoffice'` 时按 `activeTab` 从 `oo_sheet_map` 取 `source_wp_code`+`oo_sheet_name`，经 `wp-id-by-code` 解析 `ooSourceWpId`（见 3.4）。
- 切回 html 时 `reloadAllResponses = loadAll`。

#### 3.2 `useB50RiskMatrix.ts`（扩展 AccountRow）

新增字段（持久化到 checklist_responses，向后兼容）：
- `balance: number | null` ← `B50-T3-balance-{account}`（remark 存数字字符串）
- `category: '' | 'scot' | 'amount_only' | 'other'` ← `B50-T3-category-{account}`（conclusion）
- `isEstimate: 'Y' | 'N' | ''` ← `B50-T3-estimate-{account}`（conclusion）
- `importAccounts(list)` 扩为接受 `{name, cycle?, balance?}`。
- `suggestedApproach(row)` computed：category='amount_only' 且无 H 综合风险 → '实质性方案'；category='scot' 或有 H → '综合性方案'（仅建议）。
- 常量 `CATEGORY_OPTIONS` = SCOT+ / 仅金额重大 / 其他。

#### 3.3 `useB50DetailColumnPrefs.ts`（新建，Tab3 列显隐）

- 列组：核心（科目/余额/类别/6 认定/综合）、扩展（会计估计/相关业务循环/应对方案/拟信赖控制）。
- localStorage key `b50-t3-column-prefs`；默认显示余额/类别，隐藏会计估计。
- 纯前端 UI 偏好，不入 checklist_responses。

#### 3.4 `useB50OoSheetMap.ts`（新建，双模式源 sheet 解析）

- 入参：`projectId`、`oo_sheet_map`（来自 project_context）、`activeTab`。
- `resolveSourceWpId(source_wp_code)`：经 `GET /api/custom-query/wp-id-by-code?project_id=&wp_code=` 解析（复用 H1/H2/G5 范式），结果缓存（Map）。
- 暴露 `ooSourceWpId`（ref，随 activeTab 变化）、`ooSheetName`；解析失败或未实例化 → `ooSourceWpId=null`。

#### 3.5 `B50AccountRiskDialog.vue`（新建，引导式录入，optional*）

- 分组卡片：① 审计范围 ② 认定层次风险（6 认定 IR/CR/RMM）③ 特别风险 ④ 应对方案。
- 右侧实时联动面板（computed 提示）。
- `save()`：收集全字段 → 一次性 `saveImmediate(batch)`（**批量，不混用 debounce**，避免 clearTimeout 丢数据）。

## Data Models

item_id 契约：

| item_id | 存储位 | 语义 | 新/旧 |
|---|---|---|---|
| `B50-T3-accounts` | remark(JSON) | 科目清单 | 旧 |
| `B50-T3-matrix-{acc}-{assertion}-{RMM/IR/CR/SR}` | conclusion | 认定风险 | 旧 |
| `B50-T3-cycle-{acc}` | conclusion | 业务循环 | 旧 |
| `B50-T3-plan-{acc}-{reliance/subonly/approach}` | conclusion | 应对方案 | 旧 |
| `B50-T3-balance-{acc}` | remark | 科目余额 | **新** |
| `B50-T3-category-{acc}` | conclusion | 类别 scot/amount_only/other | **新** |
| `B50-T3-estimate-{acc}` | conclusion | 是否会计估计 Y/N | **新** |

程序表 Tab 由 GtAProgramConsole 用自身 item_id（`procedure_status` / a-program-console 既有键），不与 B50-T* 冲突。`b50_risk_reader` 只读 `B50-T3-matrix/cycle/plan` 与 `B50-T2-*`，新增 3 个 suffix 不影响其解析（零回归）。

## Correctness Properties

- **Property 1**：render 策略输出恒不含 `cells`/`html_data.cells`（防 grid shadow）。∀ ctx。
- **Property 2**：`oo_sheet_map` 五个 key（program/tab1..tab4）恒存在且 oo_sheet_name 非空。
- **Property 3**：`suggestedApproach`：category='amount_only'∧无 H → '实质性方案'；category='scot'∨有 H → '综合性方案'；否则 ''。纯函数。
- **Property 4**：新增 3 个 item_id suffix 不改变 `b50_risk_reader.load_b50_accounts` 对同一输入的既有输出（新增键被忽略）。
- **Property 5**：`importAccounts` 幂等——重复导入同名科目不新增行，balance 仅在空值时填入不覆盖手工。
- **Property 6**：`scope-accounts` 返回的每项 balance 为 number 或缺省（不为 NaN/字符串）。
- **Property 7**：程序表索引跳转映射 B50-1→tab1 … B50-4→tab4 为全射且稳定。
- **Property 8**：`resolveSourceWpId` 对未实例化 wp_code 返回 null（不抛异常）。
- **Property 9**：Tab3 incompleteAccounts 判定在新增列存在时与改造前对同一认定数据结果一致（不因新列变未完成）。
- **Property 10**：双模式 `switchMode('onlyoffice')` 在 `!ooAvailable` 时为 no-op（保持 html）。

## Error Handling

- render 策略内任何 DB 异常 → 返回最小 dict（component_type + 空 project_context），不 500。
- `/procedure-tables/B50` 加载失败 → 程序表 Tab 显示降级提示，其余 Tab 正常。
- `wp-id-by-code` 解析失败 / 未实例化 → OnlyOffice 视图降级提示，不崩。
- OnlyOffice 健康检查失败 → `ooAvailable=false`，"在线编辑"禁用（已有范式）。

## Testing Strategy

- 后端 PBT（hypothesis, max_examples≤5）：P1 无 cells / P2 oo_sheet_map / P6 balance number / P4 reader 兼容。
- 前端 vitest（fast-check numRuns≤20）：P3 suggestedApproach / P5 importAccounts 幂等 / P7 索引映射 / P8 未实例化 null / P9 incomplete 一致 / P10 switchMode no-op。
- 集成：get_diagnostics + Vite transform 200 + 后端 AST + 既有 b50 套件 + Playwright round-trip。

## Task → Requirement 映射

| Wave | Task | Req | 属性 |
|---|---|---|---|
| W0 后端 | render 策略 + 注册 + scope-accounts 余额 | R1.1,R2.1,R6 | P1,P2,P6 |
| W1 P0 前端 | 程序表 Tab + 索引跳转 | R1 | P7 |
| W1 P0 前端 | Tab3 扩列 + 建议方案 + 列设置 | R2 | P3,P5,P9 |
| W2 P1 | 双模式 toolbar + per-tab OnlyOffice | R4 | P8,P10 |
| W3 P1* | 引导式弹窗 B50AccountRiskDialog | R3 | — |
| W4 P2* | 美化统一（13px/EP变量/审计目标/方法论块） | R5 | — |
| W5 | PBT + 契约 + get_diagnostics/Vite/pytest + Playwright | R6 | P1-P10 |

## 8. 迁移与零回归

- 无 DB 迁移（新增 item_id 走既有 checklist_responses 表 freeform）。
- `checklist_responses.py` 白名单：`B50-` 前缀已 pass（memory 记录），新增 suffix 自动覆盖。
- 现有 4-Tab 数据键、事件、审批、版本链、复核对话不动。
