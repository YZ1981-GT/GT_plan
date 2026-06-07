# GtEditableTable 退役计划

> 创建时间：2026-06-07
> 关联 spec：`platform-ui-editing-consistency` P2-2
> 当前状态：**调研完成，待逐步迁移**

## 1. 背景

`GtEditableTable` 是历史遗留的高阶可编辑表格 wrapper，内部已输出 deprecation 警告（60 天观察期）。
新架构拆分为：

- **`GtTableExtended`** — 展示型（只读、排序、筛选、复制粘贴）
- **`GtFormTable`** — 编辑型（行内编辑、dirty 标记、校验、撤销）

两者底层仍基于 `GtEditableTable`，但暴露更简洁的 API。
退役目标：**当 `GtEditableTable` 直接引用归零后，将其标记为 internal-only（仅 GtTableExtended/GtFormTable 内部使用），最终内联合并。**

---

## 2. 现有调用方统计

### 2.1 直接 import/使用（非 GtTableExtended/GtFormTable 内部）

| # | 文件 | 用途 | editable | 迁移目标 |
|---|------|------|----------|---------|
| 1 | `views/Adjustments.vue` | 调整分录表（行编辑+校验+右键+公式详情） | `true` | `GtFormTable` |
| 2 | `components/consolidation/worksheets/InternalCashFlowSheet.vue` | 内部现金流量工作底稿（行编辑+导入） | `true` | `GtFormTable` |
| 3 | `components/consolidation/worksheets/InternalTradeSheet.vue` | 内部交易工作底稿（行编辑+导入） | `true` | `GtFormTable` |

### 2.2 间接引用（内部使用，不需迁移）

| 文件 | 关系 |
|------|------|
| `components/common/GtFormTable.vue` | 封装层，内部 import `GtEditableTable` |
| `components/common/GtTableExtended.vue` | 封装层，内部 import `GtEditableTable` |

### 2.3 类型/文档引用（仅 type import）

| 文件 | 说明 |
|------|------|
| `components.d.ts` | 自动生成的全局组件声明 |
| `stories/common/GtEditableTable.stories.ts` | Storybook 故事（退役后删除） |
| `utils/operationHistory.ts` | 注释引用（无实际依赖） |
| `composables/useGlobalTableLayout.ts` | 文档注释 |

### 2.4 统计汇总

- **直接业务调用方：3 处**
- **全部为 editable=true 场景**
- **editable=false 场景：0 处**（均已通过 `GtTableExtended` 使用）

---

## 3. 迁移方案

### 3.1 `Adjustments.vue` → `GtFormTable`

**复杂度：高**

当前使用的 `GtEditableTable` 特性：
- `editable=true` + `columns` 定义含 `editType: 'input' | 'number' | 'select'`
- `ref` 访问内部 `fullscreen` 和 `cellSelection.contextMenu`
- 自定义 slot：`col-adjustment_no`、`col-review_status`、`footer-left`、`footer-right`
- 外部 `useEditMode` + `markDirty`

迁移步骤：
1. 将 `<GtEditableTable>` 替换为 `<GtFormTable>`
2. 移除 `:editable="true"` prop（GtFormTable 默认 editable）
3. 验证 `ref` 访问兼容性（GtFormTable 透传 attrs 给 GtEditableTable）
4. 确保 fullscreen / contextMenu ref 链路不断

**风险**：GtFormTable 是 GtEditableTable 的薄 wrapper（强制 editable=true），迁移几乎零破坏。

### 3.2 `InternalCashFlowSheet.vue` → `GtFormTable`

**复杂度：中**

当前使用的特性：
- `editable=true` + columns 含 `editType: 'number' | 'select'`
- `ref` 访问 `editableTableRef`（用于 doLayout）
- 自定义 slot：`col-company_name`、`col-amount`、`footer-left`
- 外部 `useDecimalCalc` 计算

迁移步骤：
1. 替换 `<GtEditableTable>` 为 `<GtFormTable>`
2. 移除 `:editable="true"`
3. 类型更新：`InstanceType<typeof GtEditableTable>` → `InstanceType<typeof GtFormTable>`
4. import 路径更新

### 3.3 `InternalTradeSheet.vue` → `GtFormTable`

**复杂度：中**（与 InternalCashFlowSheet 结构相同）

迁移步骤同 3.2。

---

## 4. 迁移后清理

当上述 3 处迁移完成后，执行以下清理：

### 4.1 验证零引用

```bash
# 在 audit-platform/frontend/src/ 下执行
grep -r "GtEditableTable" --include="*.vue" --include="*.ts" \
  | grep -v "GtFormTable.vue" \
  | grep -v "GtTableExtended.vue" \
  | grep -v "components.d.ts" \
  | grep -v ".stories.ts" \
  | grep -v "useGlobalTableLayout.ts" \
  | grep -v "operationHistory.ts"
```

预期输出：**空**（零直接业务引用）

### 4.2 清理步骤

1. ✅ 确认 grep 输出为空
2. 删除 `stories/common/GtEditableTable.stories.ts`
3. 将 `GtEditableTable.vue` 移入 `components/common/internal/` 目录
4. 更新 `GtFormTable.vue` 和 `GtTableExtended.vue` 的 import 路径
5. 从 `components.d.ts` 移除全局注册（改为仅内部 import）
6. 更新 `operationHistory.ts` 和 `useGlobalTableLayout.ts` 中的注释引用
7. 更新 `docs/frontend/component-usage.md` 移除 `GtEditableTable` 公开文档

### 4.3 最终阶段（可选，长期）

当 `GtTableExtended` 和 `GtFormTable` 功能稳定后：
- 将 `GtEditableTable` 的核心逻辑内联到两个子组件中
- 完全删除 `GtEditableTable.vue` 文件
- 这是**低优先级**操作，不影响用户功能

---

## 5. 时间线

| 阶段 | 内容 | 预计时间 |
|------|------|---------|
| ✅ 阶段 1 | 调研统计（本文档） | 已完成 |
| 阶段 2 | 迁移 3 处直接调用方 | 1-2 天 |
| 阶段 3 | grep 验证 0 引用 + 清理 | 0.5 天 |
| 阶段 4 | 内联合并（可选） | 视需求 |

---

## 6. 注意事项

- **GtFormTable 是 GtEditableTable 的薄 wrapper**（强制 `editable=true`），迁移几乎无破坏性
- 所有 slot 透传，所有 attrs 透传，ref 链路不断
- 迁移前应在对应页面执行 Playwright E2E 验证表格编辑功能
- `GtEditableTable` 内部的 deprecation console.warn 仅在 DEV 模式输出，生产环境无影响
- **不要在迁移完成前删除 `GtEditableTable.vue`**——GtFormTable 和 GtTableExtended 仍依赖它
