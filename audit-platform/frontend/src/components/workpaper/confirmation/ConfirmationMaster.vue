<template>
  <div class="confirmation-master">
    <div v-if="!readonly" class="confirmation-master__toolbar">
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
    <el-table
      :data="rows"
      @selection-change="onSelectionChange"
      @row-click="(row) => $emit('row-click', row)"
      highlight-current-row
      border
      size="small"
      class="confirmation-master__table"
    >
      <el-table-column v-if="!readonly" type="selection" width="40" />
      <el-table-column prop="seq" label="序号" width="60" align="center" />
      <el-table-column prop="confirm_index" label="索引号" width="100" />
      <el-table-column prop="entity_name" label="被询证单位" min-width="160" show-overflow-tooltip />
      <el-table-column prop="account_type" label="科目" width="120" />
      <el-table-column prop="amount" label="函证金额" width="120" align="right">
        <template #default="{ row }">
          {{ formatAmount(row.amount) }}
        </template>
      </el-table-column>
      <el-table-column prop="match_status" label="相符情况" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.match_status === '相符'" type="success" size="small">相符</el-tag>
          <el-tag v-else-if="row.match_status === '不符'" type="danger" size="small">不符</el-tag>
          <el-tag v-else-if="row.match_status === '未回函'" type="warning" size="small">未回函</el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="is_replied" label="回函" width="70" align="center">
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
  (e: 'row-click', row: ConfirmationRow): void
  (e: 'update:selectedIds', ids: string[]): void
}>()

function onSelectionChange(selection: ConfirmationRow[]) {
  emit('update:selectedIds', selection.map((r) => r._row_id!))
}

function formatAmount(amount: number | undefined | null): string {
  if (amount == null) return '—'
  return amount.toLocaleString() + '元'
}
</script>

<style scoped>
.confirmation-master__toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.confirmation-master__table {
  width: 100%;
}
</style>
