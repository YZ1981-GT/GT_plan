# GT 平台组件选型指南

**版本**：v1.0（R10 Spec B / Sprint 3.1.7）
**最后更新**：2026-05-16

---

## 1. 表格类组件决策树（Sprint 3.1）

| 场景 | 用什么 | 关键能力 |
|------|--------|---------|
| 纯展示 + 排序/筛选/复制粘贴 | **`GtTableExtended`** | 紫色表头 / 字号 class / 千分位 / 分组折叠 / 右键复制 |
| 行内编辑 + dirty 标记 + 校验 + 撤销 | **`GtFormTable`** | 上述 + 编辑切换 / 撤销栈 / 校验 / 多选删除 |
| 兼容已有代码（60 天观察期） | **`GtEditableTable`** | wrapper（内部基于上面两个），保留向后兼容 |
| 极简表头 + 标准 el-table 行为 | **`<el-table>`**（受 CI baseline 控制） | 不推荐新代码裸用，必须走 GtTableExtended/GtFormTable |

### 1.1 三问决策

```
是否需要行内编辑（dirty/撤销/校验）？
  ├─ 是 → GtFormTable
  └─ 否 → 是否需要复制粘贴/分组折叠/右键菜单？
       ├─ 是 → GtTableExtended
       └─ 否 → 仍推荐 GtTableExtended（统一表头风格）
```

### 1.2 不要做的事

- ❌ 新视图直接用 `<el-table>`：CI baseline 卡点会拦截（baseline 100，超出 fail）
- ❌ 在 GtTableExtended 上手写 `editable`/`@edit-change`：用 GtFormTable
- ❌ 在 GtFormTable 上 disable 编辑工具栏：本身就是编辑型，需要只读改用 GtTableExtended

---

## 2. 三个组件对比

| 维度 | GtTableExtended | GtFormTable | GtEditableTable |
|------|-----------------|-------------|-----------------|
| editable 默认值 | false | true | false（用户可改 true） |
| 工具栏（编辑/查看切换） | 否 | 是 | 用户控制 |
| 行内编辑控件 | 否 | 是 | 用户控制 |
| 复制粘贴右键菜单 | 是 | 是 | 是 |
| 分组折叠（groupBy） | 是 | 是 | 是 |
| dirty 标记 + 撤销栈 | 否 | 是 | 用户控制 |
| 推荐使用场景 | 列表展示（试算表/报表/底稿列表） | 调整分录、错报、抽样、内部交易等编辑表 | 仅旧代码兼容；新代码不要用 |

---

## 3. 使用示例

### 3.1 GtTableExtended：列表展示

```vue
<template>
  <GtTableExtended
    v-model="rows"
    :columns="cols"
    group-by="cycle"
    show-summary
    :summary-method="onSummary"
  >
    <template #toolbar-left>
      <el-button @click="onRefresh">刷新</el-button>
    </template>
    <template #col-amount="{ row }">
      <span class="gt-amt">{{ fmtAmount(row.amount) }}</span>
    </template>
  </GtTableExtended>
</template>

<script setup lang="ts">
import GtTableExtended, { type GtColumn } from '@/components/common/GtTableExtended.vue'
import { fmtAmount } from '@/utils/formatters'

const cols: GtColumn[] = [
  { prop: 'cycle', label: '循环', width: 80 },
  { prop: 'wp_code', label: '编码', width: 100 },
  { prop: 'wp_name', label: '名称', minWidth: 200 },
  { prop: 'amount', label: '金额', width: 120, align: 'right' },
]
</script>
```

### 3.2 GtFormTable：行内编辑（如调整分录）

```vue
<template>
  <GtFormTable
    v-model="entries"
    :columns="adjColumns"
    show-selection
    :default-row="() => ({ debit: 0, credit: 0 })"
    @save="onSave"
    @dirty-change="(d) => isDirty = d"
  >
    <template #toolbar-right>
      <el-button @click="onSave" type="primary">保存</el-button>
    </template>
    <template #col-debit="{ row }">
      <el-input-number v-model="row.debit" :precision="2" />
    </template>
  </GtFormTable>
</template>

<script setup lang="ts">
import GtFormTable, { type GtColumn } from '@/components/common/GtFormTable.vue'

const adjColumns: GtColumn[] = [
  { prop: 'account_code', label: '科目编码', width: 120 },
  { prop: 'account_name', label: '科目名称', minWidth: 200 },
  { prop: 'debit', label: '借方', width: 120, editType: 'number' },
  { prop: 'credit', label: '贷方', width: 120, editType: 'number' },
]
</script>
```

### 3.3 GtEditableTable（兼容 wrapper）

**仅当迁移困难时使用**。新代码不要新增引用。

```vue
<!-- 旧代码 -->
<GtEditableTable
  v-model="rows"
  :columns="cols"
  editable
/>
```

迁移路径：
- `editable=true` → 改用 `GtFormTable`
- `editable=false` → 改用 `GtTableExtended`

---

## 4. CI 卡点（baseline）

`.github/workflows/baselines.json`：
```json
{
  "el-table-naked-vue-files": 100
}
```

新视图裸用 `<el-table>` 会让 baseline 计数 +1 → CI fail。

**例外清单**（已注释 `<!-- allow-el-table: ... -->` 的）：
- 极简组件（`Login.vue` / `NotFound.vue`）
- 第三方包内部（`@vue-office/excel`）

---

## 5. 60 天观察期

- 2026-05-16 起：GtEditableTable 加入 `console.warn`（dev 模式 5 分钟节流）
- 2026-07-16：观察 console.warn 频率，无残留 → 删除 GtEditableTable
- 2026-07-16：监控 console.warn 频率，无残留 → 删除 GtEditableTable

---

## 6. 关联文档

- `audit-platform/frontend/src/components/common/GtTableExtended.vue`
- `audit-platform/frontend/src/components/common/GtFormTable.vue`
- `audit-platform/frontend/src/components/common/GtEditableTable.vue`
- `.github/workflows/baselines.json`
- `.kiro/specs/v3-r10-linkage-and-tokens/design.md` D3
