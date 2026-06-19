# 子底稿弹窗式联动 Design

## Overview

A1 程序表（GtAProgramConsole）中引用的子底稿（A1-11/A1-12/A1-17/A1-18）以弹窗形式在关联步骤旁展示并完成操作，无需跳转到独立页面。体现审计程序的关联性。

## 架构设计

### 触发机制

GtAProgramConsole 已有子底稿链接（如步骤 6 旁的 "A1-17" 标签、步骤 15 旁的 "A1-12"）。当前点击这些标签会路由跳转到子底稿编辑页。改为：

```typescript
// GtAProgramConsole.vue 中
function handleWpRefClick(wpCode: string) {
  // 如果是弹窗式子底稿，弹窗展示
  if (INLINE_POPUP_WP_CODES.has(wpCode)) {
    popupWpCode.value = wpCode
    showPopupDialog.value = true
  } else {
    // 其他底稿仍然路由跳转
    router.push({ name: 'WorkpaperEditor', params: { wpId: findWpId(wpCode) } })
  }
}

const INLINE_POPUP_WP_CODES = new Set(['A1-11', 'A1-12', 'A1-17', 'A1-18'])
```

### 弹窗容器组件

**File**: `audit-platform/frontend/src/components/workpaper/WpInlinePopup.vue`（新建）

```vue
<template>
  <el-dialog v-model="visible" :title="popupTitle" :width="popupWidth">
    <component :is="popupComponent" v-bind="popupProps" @save="onSave" />
  </el-dialog>
</template>
```

根据 wpCode 动态加载对应子组件：
- `A1-11` → `WpPopupSigning.vue`（签字审批链）
- `A1-12` → `WpPopupChecklist.vue`（适用性核查）
- `A1-17` → `WpPopupProcedure.vue`（程序步骤）
- `A1-18` → `WpPopupMixedForm.vue`（混合型：Tab 式）

### 子组件设计

#### WpPopupSigning（A1-11 签字流转）
```
┌─────────────────────────────────────────┐
│ 业务报告签发流转控制表                    │
├─────────────────────────────────────────┤
│ 审批人         │ 签字    │ 日期          │
├────────────────┼─────────┼──────────────┤
│ 项目负责经理    │ [签字]  │ [日期选择]    │
│ 项目合伙人      │ [签字]  │ [日期选择]    │
│ 质量控制复核人  │ [签字]  │ [日期选择]    │
│ IT专家         │ [签字]  │ [日期选择]    │
│ 税务专家        │ [签字]  │ [日期选择]    │
│ 报告翻译复核人  │ [签字]  │ [日期选择]    │
└─────────────────────────────────────────┘
宽度：500px
```

#### WpPopupChecklist（A1-12 核查表）
```
┌─────────────────────────────────────────────────────────────┐
│ 重大事项决定程序的履行情况核查表                               │
│ 业务分类: [A类] ✓  是否首次承接: [否]                         │
├─────────────────────────────────────────────────────────────┤
│ 一、需提交专业技术委员会讨论的情形        │是否适用│索引号     │
├───────────────────────────────────────────┼────────┼─────────┤
│ 1. 首次承接后的境内上市公司...            │ [Y/N] │ [     ]  │
│ 2. 首次承接的新三板...                   │ [Y/N] │ [     ]  │
│ ...共14条                                │        │          │
├─────────────────────────────────────────────────────────────┤
│ 二、提交讨论的重大业务咨询或分歧事项                          │
│ [富文本编辑区]                                               │
├─────────────────────────────────────────────────────────────┤
│ 注: 本表仅适用于审计业务，适用于A、B类...                     │
└─────────────────────────────────────────────────────────────┘
宽度：700px
```

#### WpPopupProcedure（A1-17 程序步骤）
```
┌─────────────────────────────────────────────────────┐
│ 对应数据程序表                                       │
├─────────────────────────────────────────────────────┤
│ □ 1. 如果以前针对上期财务报表发了保留意见...          │
│     是否适用: [是/否]  执行说明: [        ]          │
│ □ 2. 如果已经获取上期财务报表存在重大错报的审计证据...│
│     是否适用: [是/否]  执行说明: [        ]          │
│ □ 3. 如果上期财务报表未经审计...                     │
│     是否适用: [是/否]  执行说明: [        ]          │
└─────────────────────────────────────────────────────┘
宽度：600px
```

#### WpPopupMixedForm（A1-18 混合型）
```
┌─────────────────────────────────────────────────────────┐
│ 采用新金融工具准则衔接影响数核对                          │
│ [目标] [审计过程] [表一-权益] [表二-分类] [表三-明细] [结论]│
├─────────────────────────────────────────────────────────┤
│ (当前Tab内容)                                            │
└─────────────────────────────────────────────────────────┘
宽度：80vw
```

### 数据持久化

复用 `checklist_responses` 表（V085 已建）：

```
item_id 格式:
- A1-11: "A1-11-sign-{role}" (如 "A1-11-sign-pm", "A1-11-sign-partner")
- A1-12: "A1-12-{seq}" (如 "A1-12-001" ~ "A1-12-014")
- A1-17: "A1-17-{seq}" (如 "A1-17-001" ~ "A1-17-003")
- A1-18: 调节表存 working_paper.parsed_data.a1_18_data (JSONB)
         程序步骤: "A1-18-{seq}"
```

API 复用：
- GET/PUT `/api/workpapers/{wp_id}/checklist-responses` 同一端点
- A1-18 调节表额外用 PUT `/api/workpapers/{wp_id}/parsed-data` 保存 JSONB

### 完成状态回显

GtAProgramConsole 中的子底稿标签加完成状态徽章：

```typescript
// 完成判定
const COMPLETION_RULES: Record<string, (responses: Record<string, any>) => boolean> = {
  'A1-11': (r) => ['pm', 'partner', 'qc'].every(role => r[`A1-11-sign-${role}`]?.conclusion),
  'A1-12': (r) => Array.from({length: 14}, (_, i) => `A1-12-${String(i+1).padStart(3, '0')}`).every(id => r[id]?.conclusion),
  'A1-17': (r) => ['001', '002', '003'].every(seq => r[`A1-17-${seq}`]?.conclusion),
  'A1-18': (r) => !!r['A1-18-conclusion']?.conclusion,
}
```

完成状态在 A1 程序表渲染时从 `checklist_responses` 批量查询（按 project_id 取所有子底稿响应数据）。

### GtAProgramConsole 修改点

1. 子底稿链接点击事件改为弹窗（INLINE_POPUP_WP_CODES 命中时）
2. 引入 WpInlinePopup 组件
3. 加载子底稿完成状态数据（一次查询所有 A1-1x 的 checklist_responses）
4. 标签旁显示完成徽章（✓绿色 / ◐进行中）

## Testing Strategy

1. WpInlinePopup 弹窗渲染测试（vitest）
2. 各子组件独立 vitest（props + emit）
3. GtAProgramConsole 修改后回归测试
4. Playwright E2E：A1 程序表 → 点击 A1-17 → 弹窗 → 填写 → 关闭 → 绿色徽章
