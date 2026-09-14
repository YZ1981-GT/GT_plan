# Design Document

## Overview

本设计将 E1 已验证的「逐 sheet 六项标准打磨」推广到 F/G/H/I 四循环共 **512 个 sheet 级组件**（现仅 7 个全达标，505 个待打磨）。核心不是新架构，而是一套**可机械复用的打磨配方（polish recipe）+ sheet 分类处置矩阵 + 严格的非回归守卫**，让每个 sheet 结合自身业务结构补齐六项标准清单，且不破坏既有数据流。

### 事实基线（来自组件清单实测）

| 循环 | sheet 总数 | 已全达标 | 待打磨 | 整循环 OA 缺口 | AI composable |
|------|-----------|---------|--------|---------------|---------------|
| F 存货 | 92 | 7 | 85 | — | 有（useF2/F2Valuation/F2Stocktake/F2Special/F3AiGenerate） |
| G 投资 | 177 | 0 | 177 | g5/g6*/g8/g10/g11 | **无** |
| H 固定资产 | 171 | 0 | 171 | h3/h5/h8 | **无** |
| I 无形资产 | 72 | 0 | 72 | — | **无** |
| 合计 | 512 | 7 | 505 | | |

**最大共性缺口**：①审计结论（AC）几乎全循环非审定表 sheet 缺失 ②tab-toolbar（TT）在 G/H/I 广泛缺失。

### 关键设计判断

1. **不臆造 AI**：仅 F 循环存在 per-entry AiGenerate composable → F 的审计说明/结论卡片接 🤖AI 按钮；G/H/I 一律纯 textarea（Req4.5）。虽有通用 `POST /ai/generate-text` 端点，但不为 G/H/I 新接 AI（避免范围蔓延，遵循 E1 既定决策）。
2. **sheet 分类处置**：不是所有 sheet 都要六项全上。按 sheet 类型分 5 类，各有处置配方（见 §Sheet 分类处置矩阵）。Directory/Index/Procedure 导航页与静态方法论文档豁免 Req3/Req4。
3. **配方机械化**：打磨代码高度模式化（alert/details/textarea/toolbar 片段固定），可由子代理按配方逐 entry 施工，降低出错。
4. **顺带修 bug 不扩围**：仅修打磨中暴露的既有渲染 bug（SQL 列漂移 / responses_snapshot 未解析 / navigate 事件名 / ref-unwrap），不做新功能。

## Architecture

### 打磨的最小单位与施工边界

- 施工单位 = **sheet 组件**（`{cycle}/{sub}/{Entry}Tab{Name}.vue`）。
- entry 主入口（`Gt{Entry}.vue`）仅在需修 `_mergeResponses`/navigate 事件/provide saveResponse 时改动。
- composable 只读不改（除非发现 ref 契约/import 深度 bug）。
- 后端仅在 Req7 既有 bug 范围内改 render 策略裸 SQL。

### 数据流（沿用既有，不改）

```
render-config(后端) → htmlData.responses_snapshot
   → entry selfLoad _mergeResponses → allResponses Map(props 下传)
   → sheet 组件 onMounted 从 allResponses.get(item_id)?.remark 恢复
   → 用户编辑 → saveImmediate([item]) → PUT /checklist-responses → 落库
```

审计说明/结论走 `checklist_responses`，`conclusion: null`（白名单豁免路径），`item_id = {code}-{sheet}-audit-note|-audit-conclusion`。

## Components and Interfaces

### 打磨配方（Polish Recipe，E1 蓝本固化）

每个「表单类」sheet 按此顺序渲染（缺什么补什么，已有不重复）：

**① 编制提示 details**（Req2）
```vue
<details class="guidance-details">
  <summary>📋 编制提示</summary>
  <div class="guidance-content">
    <p>...源模板提炼的编制要点 + CAS 依据...</p>
  </div>
</details>
```

**② 审计目标 alert**（Req1）
```vue
<el-alert type="info" :closable="false"
  title="审计目标：<源模板一、审计目标 提炼>" class="objective-alert" />
```
多变体（按 sheetCode）→ `SHEET_META` 映射动态 title（参照 E1TabIpoSpecial）。

**③ tab-toolbar + GtIndexChip**（Req5，仅动态行表格）
```vue
<div class="tab-toolbar">
  <div class="toolbar-left"><!-- 新增行按钮等 --></div>
  <div class="toolbar-right">
    <span class="chip-wrap"><GtIndexChip value="wp:{code}" :context-project-id="projectId" /></span>
    <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
  </div>
</div>
```

**④ 主表列补全**（Req3）：对照源模板"三、XX表"列，补缺列；可编辑列用对应控件，计算列 `class-name="auto-calc-col"` 只读 + tooltip。字段名对齐 composable 数据模型。

**⑤ 审计说明卡**（Req4）
```vue
<el-card shadow="never" class="audit-note-card">
  <template #header><div class="card-header"><span>审计说明</span>
    <!-- F循环: <AiConclusionButton …> ; G/H/I: 无 --></div></template>
  <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly"
    :autosize="{ minRows: 5 }" @change="saveAuditNote" />
</el-card>
```

**⑥ 审计结论卡**（Req4）：同上，`minRows: 3`，item_id `-audit-conclusion`。

**script 侧标准块**（复制自 E1TabCashDetail）：
```ts
const NOTE_KEY = '{code}-{sheet}-audit-note'
const CONCLUSION_KEY = '{code}-{sheet}-audit-conclusion'
const auditNote = ref(''); const auditConclusion = ref('')
function saveAuditNote(val: string){ if(props.isReadonly) return
  auditNote.value=val; const item={item_id:NOTE_KEY,conclusion:null,remark:val}
  props.allResponses.set(NOTE_KEY,item); void props.saveImmediate([item]) }
// saveAuditConclusion 同构
onMounted(()=>{ const n=props.allResponses.get(NOTE_KEY); if(n?.remark)auditNote.value=n.remark
  const c=props.allResponses.get(CONCLUSION_KEY); if(c?.remark)auditConclusion.value=c.remark })
```

### AI 辅助注入规则（Req4.5）

| 循环 | 规则 |
|------|------|
| F | entry 已有 AiGenerate composable → 审计说明/结论 header 接 🤖AI 按钮，调该 composable 的 section |
| G/H/I | 无 composable → **纯 textarea，不加 AI 按钮** |

sheet 组件判定：若同 entry 的其他 sheet 已用某 `useX{Entry}AiGenerate` 且该 composable 有匹配 section，则接；否则纯 textarea。

### item_id 命名与多变体

- 单变体：`{code}-{sheet}-audit-note` / `-audit-conclusion`（如 `F1-detail-audit-note`）。
- 多变体（按 sheetCode/版本区分，如 H7 成本/公允双版本、Disclosure 上市/国企）：追加后缀 `-{variant}`（如 `H1-impairment-audit-note-cost`），`watch(variant)` 重载，防串写。

## Sheet 分类处置矩阵

按 sheet 类型决定处置强度（解决"不是所有 sheet 都要六项全上"）：

| 类别 | 识别特征 | OA | GD | 主表补列 | AN | AC | TT | 备注 |
|------|---------|----|----|---------|----|----|----|------|
| **A 明细/检查/测试表** | `*Detail/Check/Test/Analysis/Inspection/Calc/Rollforward` 等动态行表 | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | 六项全上，主战场 |
| **B 审定表** | `*Adjudication` | ✔ | ✔ | 验证 | ✔ | ✔ | ✔ | 多数已达标，补缺项即可 |
| **C 附注披露** | `*Disclosure(Listed|Soe|SOE|Base)` | ✔ | ✔ | ✔(对照附注模板字段) | ✔ | ✔ | 可选 | 字段完整性重点；披露项按版本区分 |
| **D 调整分录** | `*Adjustment` | ✔ | ✔ | 验证(分录表) | ✔ | ✔ | 可选 | AJE/RJE 结构保留 |
| **E 导航/程序/索引/静态文档** | `*Index/Directory/Procedure/ConfirmationProcedure/Ref*` | 若源模板有则补 | 若有则补 | **豁免** | **豁免** | **豁免** | 豁免 | 纯导航/程序控制台/方法论文档，不塞审计说明结论 |

判定顺序：先按文件名后缀归类 → E 类豁免 Req3/Req4 → A/B/C/D 类走完整配方。清单中 `00000`/`01000` 的 Directory/Index/Procedure 多属 E 类，非真缺口。

## Data Models

无新数据模型。复用 `checklist_responses`：

```
checklist_responses(
  project_id, wp_id, item_id, conclusion=null, remark=<textarea 内容>
)
```

item_id 前缀白名单：F/G/H/I 各 entry 的 item_id 前缀需确认已在 `backend/app/routers/.../checklist_responses.py` 白名单（多数以 `{code}-` pass 分支存在；缺失前缀补 `elif ... pass`）。

## Error Handling

（非回归守卫，Req6）

1. **只用 str_replace 编辑 .vue**——禁 PowerShell（防 UTF-8 中文损坏）。
2. **ref-unwrap 契约**：props 声明解包类型（`Map`/`string`/`boolean`），需 ref 时 `toRef(props,'x')` 重包喂 composable；禁 `props.x.value`。`check_wp_ref_contract.py --strict` exit 0。
3. **import 深度**：`fix_wp_composables_import_depth.py --check` 通过。
4. **嵌套-ref**：composable 返回值解构到顶层或显式 `.value`；禁 `:data="obj.rows"` 无 `.value`。
5. **改动文件**：`get_diagnostics` 零错误 + Vite transform（curl `/src/.../X.vue`）200。

### Req7 既有 bug 顺带修

- render 策略裸 SQL `applicable_standards` → `applicable_standard_v2 AS applicable_standards` + `isinstance` dict 防御。
- entry 未解析 `htmlData.responses_snapshot` → 补 `_mergeResponses`。
- navigate 事件名 `navigate` vs `navigate-sheet` 不匹配 → 对齐 `navigate-sheet`。
- i2（研发支出）17/19 sheet 为空壳 `00000` → 按配方从零补 A 类内容（比照 i1 同构 sheet）。

## Correctness Properties

（PBT / 结构契约）以静态扫描/契约测试形式验证（非运行时随机，属结构断言 + 少量 hypothesis）。

### Property 1: 六项覆盖
A/B/C/D 类每个已打磨 sheet 同时含 objective-alert + guidance-details + `-audit-note` + `-audit-conclusion`（TT 仅 A/B 强制）。
**Validates: Requirements 1.1, 2.1, 4.1, 9.1**

### Property 2: item_id 唯一性
同一 entry 内所有 audit-note/conclusion item_id 互不重复（多变体后缀保证）。由新增结构扫描脚本 `check_fghi_sheet_completion.py` 断言。
**Validates: Requirements 4.4**

### Property 3: ref 契约不回归
改动文件不引入 `props.(allResponses|wpId|projectId|htmlData|isReadonly).value` 反模式（复用 `check_wp_ref_contract.py --strict`）。
**Validates: Requirements 6.2, 6.4**

### Property 4: import 深度不回归
`fix_wp_composables_import_depth.py --check` 全绿。
**Validates: Requirements 6.3**

### Property 5: 持久化往返幂等
给定任意 remark 文本 s，save 后 `allResponses.get(item_id).remark === s`（前端 vitest + fast-check，numRuns=20）。
**Validates: Requirements 4.2, 4.3**

### Property 6: E 类豁免正确
Index/Directory/Procedure/Ref 类 sheet 不被 Property 1 要求 audit-note/conclusion（分类白名单驱动）。
**Validates: Requirements 9.2**

### Property 7: AI 注入合规
仅 F 循环 sheet 出现 AiConclusionButton/AI 调用；G/H/I 改动文件不含新增 AI 按钮（结构扫描）。
**Validates: Requirements 4.5**

### Property 8: 编码完整性
改动 .vue 文件无 U+FFFD replacement char（`check_utf8_integrity` 复用）。
**Validates: Requirements 6.1, 6.5**

## Testing Strategy

- **结构契约扫描**（主）：新增 `backend/scripts/check/check_fghi_sheet_completion.py`，按 Sheet 分类矩阵校验 A/B/C/D 类 sheet 六项覆盖（P1/P2/P6/P7），`--strict` 可挂 CI；复用 `check_wp_ref_contract.py --strict`（P3）、`fix_wp_composables_import_depth.py --check`（P4）、UTF-8 完整性检查（P8）。
- **前端 vitest + fast-check**（P5 持久化往返幂等，numRuns=20）：抽样 F/G/H/I 各 1 个代表 sheet 组件挂载 + save/hydrate 往返断言。
- **Vite transform 冒烟**：每改动文件 curl `/src/.../X.vue` 断言 200（防结构损坏/import 崩）。
- **get_diagnostics**：每改动文件零错误。
- **Playwright 实测**（Req8）：每循环完成后 admin/admin123 登录 → 导航代表底稿 → 抽验 ≥2 sheet，断言审计目标/编制提示/审计说明/审计结论渲染 + console 0 error。服务未起先 `start-dev.bat`。

## Execution Strategy

- **分波按循环+entry**：F → G → H → I，每循环内按 entry 分组，entry 内 sheet 批量施工。
- **并发**：子代理并发 ≤3，stagger 5s（避免竞态写同文件）。
- **每 entry 完成即验证**：get_diagnostics + Vite transform 200；每循环完成 Playwright 抽验 ≥2 sheet（Req8）。
- **顺序建议**：先做缺口最系统的（AC 补全 + TT 补全全覆盖），i2 空壳单独重点。
- **tasks.md 承载逐 entry 覆盖清单**（Req9.3），每 entry 一个任务组，sheet 明细在任务体内列出，标状态。

## 参照

- 源模板：`基础数据/致同通用审计程序及底稿模板（2025年修订）/BCD类底稿md/{F存货|G投资|H固定资产|I无形资产}循环/*底稿模板库.md`
- 蓝本组件：`e1/E1TabCashDetail.vue`（配方源）、`e1/E1TabIpoSpecial.vue`（多变体 SHEET_META）
- 守卫脚本：`backend/scripts/check/check_wp_ref_contract.py`、`fix_wp_composables_import_depth.py`
- 质量标杆：`.kiro/specs/e1-sheet-content-completion/`（已完成 25/25）
