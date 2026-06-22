# Design Document

## Overview

为 D0-3 跟函函证过程控制创建专用组件 `GtConfirmationFollowup`（componentType=`confirmation-followup`），把"散落 `[XX]` 占位符的叙事性跟函模板"重构为 **多笔 master-detail + 结构化字段填空 + 备忘录文本自动生成 + 条件场景 + 三项控制清单红线 + 电子签名留痕 + 双视图**。与 D0-1（confirmation-summary）/D0-2（confirmation-entity-verify）同构，最大化复用其已建基础能力，仅实现 D0-3 特有的"跟函过程记录 + 备忘录生成"逻辑。

D0-3 与 D0-1/D0-2 的本质差异：D0-1/D0-2 是"多列宽表"，核心痛点是横向滚动；D0-3 是"叙事备忘录"，核心痛点是**占位符埋在 prose 里易漏填 + 两套话术混在一段**。因此 D0-3 的精修重心是"结构化字段 → 自动拼装备忘录文本"（左字段表单 / 右成稿预览分栏，对齐报表模块编辑区+预览习惯），而非列分组。跟函是通用函证程序，componentType 循环无关（不止收入循环 D）。

## Architecture

```
htmlRendererRegistry 新注册：confirmation-followup → GtConfirmationFollowup
后端 _WP_CODE_OVERRIDE / render-config 对 D0-3 sheet 标 componentType=confirmation-followup

GtConfirmationFollowup.vue（主组件）
├── props: wpId / sheetName / schema / htmlData / readonly
├── emit: save / open-formula / restore
│
├── 视图切换：备忘录视图(默认) / 清单表格视图（localStorage 记忆）
├── FollowupDashboard.vue    跟函看板（记录数/控制达标率/签名完成率/异常数）
├── 【备忘录视图】FollowupMaster.vue + FollowupDetail.vue（左字段表单 / 右备忘录预览分栏 + 6 区分组 + 条件场景 + 控制清单 + 签名）
│     └── FollowupMemoPreview.vue  备忘录正文实时预览（字段拼装 / 缺漏占位高亮 / 可覆盖编辑 / 复制导出 / 后收回补记段）
├── 【清单表格视图】复用/同构通用宽表网格（约 12 关键列 + useCellSelection）
│
├── useFollowupData.ts       数据核心（rows/dirty/CRUD/buildPayload/进度指标/控制结论派生）
├── useMemoCompose.ts        备忘录文本生成（场景话术模板 + 字段插值 + 缺漏占位 + override 守卫）
├── useCellSelection.ts      复用：选区/复制/粘贴
├── CellContextMenu.vue      复用：右键菜单
├── useDictStore             复用：枚举
├── useExcelIO               复用：导入/导出
├── followupEnums.ts         枚举 dictKey 映射
└── followupTypes.ts         类型定义（FollowupRow / ControlConclusion / SignStatus）

单位主数据共享（需求 11）：D0-1/D0-2/D0-3 同一 confirm_index 共享单位字段，
  通过既有跨底稿引用机制（cross_wp_references / address_registry wp 域），不存多份副本

保存链路（复用既有）：emit('save', payload) → GtWpRenderer.onSave → WorkpaperEditor → POST /save
  payload = { rows, _format: 'confirmation-followup-v1' }

后端：system_dicts._DICTS 增 confirmation_followup_scenario（现场即时确认/无法即时确认）+ yes_no_na（是/否/不适用）
编制指引：backend/data/wp_guidance/D0-3.json 补准则程序文本（跟函控制要求/身份权限确认/正常流程观察/防串通舞弊）
```

## Components and Interfaces

### GtConfirmationFollowup.vue（新，主组件）
- Props: `{ wpId, sheetName, schema, htmlData, readonly }`；Emit: `save / open-formula / restore`
- 旧格式（无 `_format`）降级 GtGridSheet 只读

### FollowupMaster.vue（新）
- Props: `{ rows, readonly, expandedRowId }`；Emit: `expand / add / delete / context-menu`
- el-table 关键列（函证索引/被函证单位/跟函人员/跟函日期/确认场景/控制结论徽章/签名状态）+ 多选 + 工具栏（新增/删除/保存/导入/导出备忘录）
- 空态引导（D0-3 为可选底稿）

### FollowupDetail.vue（新）
- Props: `{ row, readonly, enumOptions }`；Emit: `field-change`
- **左右分栏布局**（对齐报表模块编辑区+预览习惯）：左 = 结构化字段表单，右 = FollowupMemoPreview 成稿预览
- 左侧 6 区分组（el-collapse 或分段卡片）：① 跟函基本信息 ② 现场确认记录（条件场景）③ 三项控制检查 ④ 控制证据 ⑤ 签名 ⑥ 回函收回补记（条件）
- 条件 v-show：scenario === 'deferred' 展开后续电话核实字段；later_received === '是' 展开寄回字段
- 字段旁 el-tooltip 注入提示（逐项：控制检查①②③ 各自专属提示 / 对外公开电话独立来源提示 / 控制证据 名片员工卡系统核对）

### FollowupMemoPreview.vue（新，需求 2）
- Props: `{ row, readonly }`；Emit: `memo-change / regenerate`
- 实时展示 useMemoCompose 拼装的备忘录正文；缺漏字段以 `〔字段名〕` 高亮
- 切换"自动生成 / 手动编辑"；手动编辑置 memo_overridden；"重新生成"按钮放弃覆盖
- 复制/导出文本（末尾保留手书签名留位）

### FollowupDashboard.vue（新）
- Props: `{ metrics, collapsed }`
- 跟函记录数 / 控制达标率 / 签名完成率 / 控制不达标（异常）笔数（异常高亮）

### useFollowupData.ts（新 composable）
```ts
interface FollowupRow {
  id: string; confirm_index: string          // 函证索引（关联 D0-1/D0-2，兼作后收回补记的函证索引号）
  // ① 跟函基本信息
  entity_name: string; entity_address: string
  followup_staff: string; followup_date: string
  scenario: string                            // 现场即时确认 / 无法即时确认
  // ② 现场确认记录（即时确认）
  handle_dept: string; handler_name: string; handler_emp_id: string
  //   （留函后续电话核实，场景②条件）
  deferred_date: string; deliver_handler: string; deliver_emp_id: string; envelope_left: string
  callback_date: string; public_phone: string; phone_confirm_person: string; reception_date: string
  // ⑥ 回函收回补记（条件，两场景可用 — 对应模板"注：完成本备忘录后才收回函证"）
  later_received: string; reply_back_date: string; back_office: string
  // ③ 三项控制检查（是/否/不适用）
  ctrl_know_process: string; ctrl_verify_identity: string; ctrl_normal_process: string
  // ④ 控制证据
  control_evidence: string
  // ⑤ 签名 + 备忘录
  signature: string; sign_date: string
  memo_text: string; memo_overridden: boolean
  remark: string
}

useFollowupData(htmlData, readonly) => {
  rows, addRow, deleteRow, updateField, importRows
  controlConclusion(row)   // computed: 'pass' | 'fail' | 'incomplete'
  signStatus(row)          // computed: 'signed' | 'unsigned'
  progressMetrics          // computed: 记录数/控制达标率/签名完成率/异常数
  dirty, buildPayload
}
```

### useMemoCompose.ts（新 composable，需求 2/3）
```ts
// 两套场景话术模板（占位用 {field}，缺漏渲染为 〔字段名〕高亮）
const MEMO_TEMPLATES = {
  immediate: `审计项目组成员{followup_staff}于{followup_date}直接至{entity_name}（{entity_address}）实施函证程序。`
           + `该函证在{handle_dept}办理，确认函证的被函证单位工作人员姓名为{handler_name}`
           + `（工号{handler_emp_id}）。`,
  deferred:  `审计项目组成员{followup_staff}于{followup_date}至{entity_name}（{entity_address}）实施函证程序，`
           + `被函证单位人员告知无法现场即时确认，需详细查询后确认并将函证直接寄回事务所。`
           + `{followup_staff}于{deferred_date}亲自将函证交给经办人{deliver_handler}（工号{deliver_emp_id}），并留存回邮信封。`
           + `跟函人员于{callback_date}致电{entity_name}对外公开电话{public_phone}（取自独立公开来源），`
           + `与{phone_confirm_person}确认其确实于{reception_date}接待跟函人员、确认本函证。`,
}
// 后收回补记段（later_received=是 时追加，两场景通用）
const LATER_RECEIVED_TPL = `注：该函证于{reply_back_date}寄回{back_office}，函证索引号为{confirm_index}。`
useMemoCompose(row) => {
  composedMemo   // computed: 按 scenario 选模板插值 + later_received=是 追加注记段；缺漏字段以 〔name〕 高亮
  missingFields  // computed: 必填但为空的字段名列表
  applyToRow()   // 把 composedMemo 写入 row.memo_text（仅当 !memo_overridden）
  regenerate()   // 放弃 override，重置 memo_overridden=false 并重写
}
```

## Data Models

### FollowupRow（约 24 字段，见上）

### ControlConclusion / SignStatus（需求 4/6）
```ts
type ControlConclusion = 'pass' | 'fail' | 'incomplete'  // 绿/橙红/灰
//   三项控制全为"是" → pass；任一为"否" → fail；有空项 → incomplete
type SignStatus = 'signed' | 'unsigned'
//   signature 与 sign_date 均非空 → signed
```

### ProgressMetrics
```ts
{
  total: number              // 跟函记录数
  pass_count: number         // 控制达标（三项全是）
  control_pass_rate: number  // 控制达标率
  signed_count: number       // 已签名
  sign_rate: number          // 签名完成率
  abnormal_count: number     // 控制不达标（任一为否）
}
```

### 保存载荷（`_format: 'confirmation-followup-v1'`）
`{ "_format": "confirmation-followup-v1", "rows": [FollowupRow...] }`

### F0-3 支撑数据源（需求 11）
D0-3 暴露按 confirm_index 索引的跟函控制结论摘要供 D0-1/D0-2 引用：
`{ confirm_index, control_conclusion, followup_staff, followup_date, d0_3_record_id }`，通过既有跨底稿引用机制解析，不重复存储。

## Correctness Properties

### Property 1: 备忘录文本由字段派生且可覆盖
当 memo_overridden=false 时，结构化字段变化 SHALL 实时重拼备忘录正文；用户手动编辑后置 memo_overridden=true，字段变化不再覆盖；点"重新生成"复位 memo_overridden=false 并重写。
**Validates: Requirements 2.2, 2.3**

### Property 2: 缺漏字段占位不静默
当必填字段为空时，备忘录正文 SHALL 以 `〔字段名〕` 高亮占位，missingFields 列出缺漏项，不生成残缺自然文本。
**Validates: Requirements 2.4**

### Property 3: 条件场景字段不丢数据
当 scenario 在"现场即时确认"与"无法即时确认"间切换、或 later_received 切换时，场景②字段与⑥回函收回补记字段 SHALL 保留值但按条件显隐，不清除已填数据；备忘录正文随场景套用对应段落，later_received=是 追加注记段。
**Validates: Requirements 3.2, 3.3, 3.4, 3.7, 3.8**

### Property 4: 控制结论派生
controlConclusion SHALL 由三项控制检查派生：全为"是"→pass(绿)；任一为"否"→fail(橙/红)+计入异常；有空项→incomplete(灰)。
**Validates: Requirements 4.2, 4.4**

### Property 5: 进度指标实时性
rows 增删/修改后 progressMetrics 同一 tick 重算（记录数/控制达标率/签名完成率/异常数）。
**Validates: Requirements 12.1**

### Property 6: 签名状态派生
signStatus SHALL 由 signature 与 sign_date 派生：均非空→signed，否则 unsigned；签名默认带入跟函人员可改。
**Validates: Requirements 6.2, 6.3**

### Property 7: 旧格式兼容
htmlData 无 `_format` 时降级 GtGridSheet 只读，不崩。
**Validates: Requirements 14.2**

### Property 8: 只读不可编辑
readonly=true 时所有控件不可编辑，工具栏增删/保存/导入禁用，导出备忘录可用。
**Validates: Requirements 1.3, 9.5**

### Property 9: 函证索引关联一致
D0-3 行的 confirm_index 与 D0-1/D0-2 同源；同一索引在三底稿表示同一笔函证，单位字段单源共享，单侧缺失各自独立可用。
**Validates: Requirements 11.1, 11.2, 11.5**

## Error Handling

- 枚举字典缺失 → 降级 el-input
- 导入缺列行 → 预览标错跳过，不中断
- 备忘录字段缺漏 → 占位高亮 + missingFields 提示，不阻塞保存（草稿态）
- 保存失败 → console.warn + dirty 保留
- 旧格式 → 降级只读网格
- 跨底稿引用解析失败（D0-1/D0-2 不存在）→ 不显示跳转链接，本底稿独立可用

## Testing Strategy

- **useFollowupData 单测**：CRUD + progressMetrics 实时 + buildPayload 格式 + controlConclusion/signStatus 派生（P4/P5/P6）
- **useMemoCompose 单测**：两场景模板插值 / 缺漏 `〔字段名〕` 占位 / later_received=是 追加注记段 / override 守卫不被字段覆盖 / regenerate 复位（P1/P2）
- **条件场景 spec**：scenario 切换 + later_received 切换字段显隐 + 字段值保留（P3）
- **控制清单 spec**：三项任一为否→橙红警示 + 异常计数；全空→未完成（P4）
- **签名 spec**：签名+日期完整性 → signStatus；默认带入跟函人员（P6）
- **字段提示 spec**：提示就近落到控制检查/控制证据 tooltip；完整准则在 guidance 侧栏
- **后端枚举测试**：confirmation_followup_scenario / yes_no_na 返回完整
- **回归**：render-config 冒烟零回归
- **Playwright**：D0-3 新增跟函记录 → 选场景填字段 → 备忘录实时生成 → 切场景字段保留 → 控制检查否→警示 → 签名 → 导出备忘录 → 保存 → 重开持久化 + 跳 D0-1/D0-2
