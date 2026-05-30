<!--
  CNoteSubTableCard.vue — 单张子表卡片渲染器

  从 GtCNoteTable.vue 原 static_rows / dynamic_rows el-table 块抽出。
  渲染单张 SubTableSchema：
  - static_rows：el-table + CNoteCell
  - dynamic_rows：新增行按钮 + el-table + 删除列 + footer_total 合计行

  props 接收 shell 计算好的数据，emit 通知 shell 触发 debounceSave。
  不持有 saveTimer / 不直接发 API（design D3）。

  spec: gt-c-note-table-shrink Task 7
  Validates: Requirements 3
-->
<template>
  <div class="gt-cnt__sub-body">
    <!-- ── static_rows 渲染 ── -->
    <template v-if="subTable.type === 'static_rows'">
      <el-table
        :data="rows"
        border
        size="small"
        :row-class-name="staticRowClass"
        class="gt-cnt__sub-table"
      >
        <el-table-column
          v-for="col in visibleColumns"
          :key="col._cellKey"
          :label="col.label"
          :min-width="col.width || 130"
          :align="isLabelField(col.field) ? 'left' : 'right'"
          resizable
        >
          <template #default="{ row }">
            <CNoteCell
              :row="row"
              :col="col"
              :readonly="readonly"
              :computed-value="cellComputedValue(subTable, row, col)"
              @change="emit('cell-change', row, col)"
            />
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ── dynamic_rows 渲染 ── -->
    <template v-else-if="subTable.type === 'dynamic_rows'">
      <div v-if="!readonly" class="gt-cnt__sub-toolbar">
        <el-button
          size="small"
          :icon="PlusIcon"
          :disabled="reachedMax"
          @click="emit('add-row')"
        >
          新增行
        </el-button>
      </div>

      <el-table
        :data="rows"
        border
        size="small"
        class="gt-cnt__sub-table"
        empty-text="暂无数据，点击「新增行」开始填写"
      >
        <el-table-column
          v-for="col in visibleColumns"
          :key="col._cellKey"
          :label="col.label"
          :min-width="col.width || 130"
          resizable
        >
          <template #default="{ row }">
            <CNoteCell
              :row="row"
              :col="col"
              :readonly="readonly"
              :computed-value="cellComputedValue(subTable, row, col)"
              @change="emit('cell-change', row, col)"
            />
          </template>
        </el-table-column>

        <el-table-column
          v-if="!readonly"
          label="操作"
          width="70"
          fixed="right"
        >
          <template #default="{ $index }">
            <el-button
              link
              type="danger"
              size="small"
              @click="emit('remove-row', $index)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 子表底部合计行 -->
      <div
        v-if="subTable.footer_total?.enabled"
        class="gt-cnt__sub-footer"
      >
        <span class="gt-cnt__footer-label">{{ subTable.footer_total.label || '合计' }}：</span>
        <span
          v-for="col in footerColumns"
          :key="col.field"
          class="gt-cnt__footer-cell"
        >
          <span class="gt-cnt__footer-col-label">{{ col.label }}</span>
          <span class="gt-amt">{{ formatAmount(footerValue(col)) }}</span>
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { Plus as PlusIcon } from '@element-plus/icons-vue'
import CNoteCell from './CNoteCell.vue'
import { isLabelField } from './cnoteHelpers'
import { formatAmount } from '@/utils/formatAmount'
import type { SubTableSchema, ColumnDef, ColumnDefWithKey, RowData } from '../GtCNoteTable.types'

const props = defineProps<{
  subTable: SubTableSchema
  rows: RowData[]
  readonly?: boolean
  visibleColumns: ColumnDefWithKey[]
  cellComputedValue: (st: SubTableSchema, row: RowData, col: ColumnDefWithKey) => number | string | null
  footerColumns: ColumnDef[]
  footerValue: (col: ColumnDef) => number
  reachedMax: boolean
}>()

const emit = defineEmits<{
  'cell-change': [row: RowData, col: ColumnDefWithKey]
  'add-row': []
  'remove-row': [index: number]
}>()

function staticRowClass({ row }: { row: RowData }): string {
  if (row._is_grand_total) return 'gt-cnt-row-grand-total'
  if (row._is_subtotal) return 'gt-cnt-row-subtotal'
  return ''
}
</script>

<style scoped>
.gt-cnt__sub-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gt-cnt__sub-toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.gt-cnt__sub-table {
  width: 100%;
}

.gt-cnt__sub-table :deep(.gt-cnt-row-grand-total) {
  background: var(--el-color-primary-light-9);
  font-weight: 600;
}

.gt-cnt__sub-table :deep(.gt-cnt-row-subtotal) {
  background: var(--el-color-info-light-9);
  font-weight: 500;
}

.gt-cnt__cell-readonly {
  display: inline-block;
  width: 100%;
  padding: 0 4px;
  color: var(--el-text-color-regular);
  font-variant-numeric: tabular-nums;
}

.gt-cnt__indent-1 {
  padding-left: 16px;
}

.gt-cnt__indent-2 {
  padding-left: 32px;
}

.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.gt-cnt__amount-input :deep(.el-input__inner) {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.gt-cnt__sub-footer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding: 8px 12px;
  background: var(--el-color-primary-light-9);
  border-radius: 4px;
  font-size: 13px;
}

.gt-cnt__footer-label {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.gt-cnt__footer-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.gt-cnt__footer-col-label {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
