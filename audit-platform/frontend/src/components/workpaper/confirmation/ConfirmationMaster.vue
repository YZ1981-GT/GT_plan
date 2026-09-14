<template>
  <div class="confirmation-master">
    <div v-if="!readonly" class="confirmation-master__toolbar">
      <div class="confirmation-master__toolbar-left">
        <el-button type="primary" size="small" @click="$emit('add')">
          <el-icon><Plus /></el-icon> 新增
        </el-button>
        <el-button type="danger" size="small" :disabled="!selectedIds.length" @click="$emit('delete')">
          删除选中
        </el-button>
        <el-button type="success" size="small" @click="$emit('save')">
          保存
        </el-button>
      </div>
      <div class="confirmation-master__toolbar-right">
        <el-button size="small" type="info" plain @click="$emit('show-formula')">fx 公式</el-button>
        <el-button size="small" @click="$emit('download-template')">↓ 导入模板</el-button>
        <el-button size="small" @click="$emit('import-data')">↑ 导入</el-button>
      </div>
    </div>
    <!-- 列表视图=简表概览（核心列）；完整宽表全列见「完整表格」视图（ConfirmationFullGrid）；
         点击行由下方 ConfirmationDetail 编辑全部字段（含 additive 补列） -->
    <el-table
      :data="rows"
      @selection-change="onSelectionChange"
      @row-click="(row) => $emit('row-click', row)"
      highlight-current-row
      border
      size="small"
      table-layout="auto"
      class="confirmation-master__table"
    >
      <el-table-column v-if="!readonly" type="selection" width="36" align="center" />
      <el-table-column prop="seq" label="序号" min-width="45" align="center" />
      <el-table-column prop="confirm_index" label="索引号" min-width="70" />
      <el-table-column prop="entity_name" label="被询证单位" min-width="130" show-overflow-tooltip />
      <el-table-column prop="account_type" label="科目" min-width="80" />
      <el-table-column prop="amount" label="函证金额" min-width="100" align="right">
        <template #default="{ row }">
          {{ fmtAmount(row.amount) }}
        </template>
      </el-table-column>
      <el-table-column prop="match_status" label="相符情况" min-width="70" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.match_status === '相符'" type="success" size="small">相符</el-tag>
          <el-tag v-else-if="row.match_status === '不符'" type="danger" size="small">不符</el-tag>
          <el-tag v-else-if="row.match_status === '未回函'" type="warning" size="small">未回函</el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="is_replied" label="回函" min-width="55" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.is_replied" type="success" size="small">是</el-tag>
          <el-tag v-else type="info" size="small">否</el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import type { ConfirmationRow } from './confirmationTypes'

defineProps<{
  rows: ConfirmationRow[]
  readonly: boolean
  selectedIds: string[]
}>()

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'delete'): void
  (e: 'save'): void
  (e: 'download-template'): void
  (e: 'import-data'): void
  (e: 'show-formula'): void
  (e: 'row-click', row: ConfirmationRow): void
  (e: 'update:selectedIds', ids: string[]): void
}>()

function onSelectionChange(selection: ConfirmationRow[]) {
  emit('update:selectedIds', selection.map((r) => r._row_id!))
}

/** 平台金额格式（千分符 + 两位小数），与 FullGrid/Detail 一致 */
function fmtAmount(amount: number | undefined | null): string {
  if (amount == null) return '—'
  return amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.confirmation-master__toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
  gap: 8px;
}
.confirmation-master__toolbar-left {
  display: flex;
  gap: 6px;
}
.confirmation-master__toolbar-right {
  display: flex;
  gap: 6px;
}

.confirmation-master__table {
  width: 100%;
  font-size: 13px;
}

/* 表头折行显示 */
.confirmation-master__table :deep(.el-table__header th .cell) {
  white-space: normal;
  word-break: break-all;
  line-height: 1.3;
  font-size: 12px;
}

/* 勾选列居中 */
.confirmation-master__table :deep(.el-table-column--selection .cell) {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 0;
}

.confirmation-master__table :deep(.el-table__body td .cell) {
  font-size: 12px;
}

/* 数值列等宽对齐+防折行 */
.confirmation-master__table :deep(td.is-right .cell) {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
</style>
