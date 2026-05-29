# 表格统一化 — 设计文档

## D1 el-table 双行表头实现方案

试算平衡表的双行表头（审计调整 借方/贷方）用嵌套 column 实现：

```vue
<el-table :data="rows" border>
  <el-table-column prop="row_code" label="行次" width="80" />
  <el-table-column prop="row_name" label="项目" min-width="200" />
  <el-table-column prop="unadjusted" label="未审数" width="140" align="right" />
  <el-table-column label="审计调整">
    <el-table-column prop="aje_dr" label="借方" width="120" align="right" />
    <el-table-column prop="aje_cr" label="贷方" width="120" align="right" />
  </el-table-column>
  <el-table-column label="重分类调整">
    <el-table-column prop="rcl_dr" label="借方" width="120" align="right" />
    <el-table-column prop="rcl_cr" label="贷方" width="120" align="right" />
  </el-table-column>
  <el-table-column prop="audited" label="审定数" width="140" align="right" />
</el-table>
```

## D2 矩阵表（权益变动表）实现方案

动态列用 `v-for` 生成：

```vue
<el-table :data="rows" border :span-method="equitySpanMethod">
  <el-table-column prop="row_name" label="项目" fixed width="200" />
  <el-table-column v-for="col in dynamicColumns" :key="col.key" :label="col.label" width="130" align="right">
    <template #default="{ row }">{{ fmt(row[col.key]) }}</template>
  </el-table-column>
</el-table>
```

## D3 统一样式方案

全局 scoped style（放在 App.vue 或 global.css）：

```css
/* 所有 el-table 统一紫色表头 */
.el-table thead th { background: #f0edf5 !important; }
.el-table--border td, .el-table--border th { border-color: #e8e4f0 !important; }

/* 字号动态 class */
.gt-tb-font-xs .el-table__body, .gt-tb-font-xs th .cell, .gt-tb-font-xs td .cell { font-size: 11px !important; }
.gt-tb-font-sm ... { font-size: 12px !important; }
.gt-tb-font-md ... { font-size: 13px !important; }
.gt-tb-font-lg ... { font-size: 14px !important; }
```

## D4 useCellSelection 接入策略

- 核心表格（试算平衡表/报表/合并试算表）：完整接入（单元格选中+拖拽+右键+复制）
- 辅助表格（OCR/知识库/风险矩阵）：仅接入行选择，不接入单元格级选中

## D5 可编辑列实现

试算平衡表的"重分类调整"列用 el-table 的 `#default` slot + 条件渲染：

```vue
<el-table-column label="借方" width="120" align="right">
  <template #default="{ row, $index }">
    <el-input-number v-if="editingCell === `${$index}_rcl_dr`" v-model="row.rcl_dr" size="small" :controls="false" @blur="stopEdit" />
    <span v-else class="gt-tb-editable" @click="startEdit($index, 'rcl_dr')">{{ fmt(row.rcl_dr) }}</span>
  </template>
</el-table-column>
```

## D6 风险点

1. **权益变动表列数动态**：合并报表可能有 10+ 列，el-table 横向滚动需要设置 `width` 或 `min-width`
2. **合并单元格**：`span-method` 需要精确计算 rowspan/colspan，逻辑复杂
3. **打印预览**：GtPrintPreview 的 table 用于打印输出，el-table 打印效果可能不如原生 table（需验证）
4. **性能**：合并报表矩阵可能有 200+ 行 × 10+ 列，el-table 渲染性能需关注


## D7 合并报表动态列 + 弹窗编辑 + 冻结首列

```vue
<el-table :data="consolRows" border max-height="600">
  <!-- 冻结首列 -->
  <el-table-column prop="row_name" label="项目" fixed="left" width="200" />
  <!-- 动态子公司列 -->
  <el-table-column v-for="company in companies" :key="company.id" :label="company.name" min-width="130" align="right">
    <template #default="{ row }">
      <span class="gt-amt clickable" @click="openConsolEditDialog(row, company)">
        {{ fmt(row[company.id]) }}
      </span>
    </template>
  </el-table-column>
  <!-- 合计列 -->
  <el-table-column label="合计" width="140" align="right" fixed="right">
    <template #default="{ row }">{{ fmt(row._total) }}</template>
  </el-table-column>
</el-table>

<!-- 弹窗编辑器（单元格点击触发） -->
<el-dialog v-model="consolEditVisible" title="编辑抵消分录" width="600px">
  ...
</el-dialog>
```

动态新增列：`companies` 是响应式数组，用户点击"新增子公司"按钮 push 新元素，el-table 自动渲染新列。

## D8 合并试算表（ConsolTrialBalanceTab）

```vue
<el-table :data="consolTbRows" border max-height="500">
  <el-table-column prop="account_code" label="科目编码" width="120" />
  <el-table-column prop="account_name" label="科目名称" min-width="180" />
  <el-table-column v-for="company in companies" :key="company.id" :label="company.name" width="140" align="right">
    <template #default="{ row }">{{ fmt(row[`balance_${company.id}`]) }}</template>
  </el-table-column>
  <el-table-column label="合计" width="140" align="right">
    <template #default="{ row }">{{ fmt(row._total) }}</template>
  </el-table-column>
</el-table>
```

支持展开/折叠：el-table 原生 `row-key` + `default-expand-all` + `expand-change` 事件。

## D9 选中样式（无边框，仅高亮背景）

```css
/* 全局选中样式 */
.gt-ucell--selected {
  background: rgba(75, 45, 119, 0.08) !important;
  border-color: transparent !important;
}
.gt-ucell--single-selected {
  background: rgba(75, 45, 119, 0.12) !important;
  border-color: transparent !important;
}
/* 试算平衡表行选中 */
.gt-tb-sum-selected td {
  background: rgba(75, 45, 119, 0.08) !important;
}
```
