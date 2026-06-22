<template>
  <div class="followup-master">
    <!-- Toolbar -->
    <div class="followup-master__toolbar">
      <el-button size="small" type="primary" :disabled="readonly" @click="$emit('add')">
        新增
      </el-button>
      <el-button
        size="small"
        type="danger"
        :disabled="readonly || selectedIds.length === 0"
        @click="$emit('delete')"
      >
        删除
      </el-button>
      <el-button size="small" :disabled="readonly || !isDirty" @click="$emit('save')">
        保存
      </el-button>
      <el-button size="small" :disabled="readonly" @click="$emit('import')">
        导入
      </el-button>
      <el-button size="small" @click="$emit('export-template')">
        导出模板
      </el-button>
      <el-button size="small" @click="$emit('export-data')">
        导出数据
      </el-button>
    </div>

    <!-- Table -->
    <el-table
      :data="rows"
      size="small"
      border
      stripe
      highlight-current-row
      table-layout="auto"
      :max-height="400"
      @selection-change="handleSelectionChange"
      @row-click="handleRowClick"
      class="followup-master__table"
    >
      <el-table-column type="selection" width="36" align="center" :selectable="() => !readonly" />
      <el-table-column prop="seq" label="序号" min-width="45" align="center" />
      <el-table-column prop="confirm_index" label="函证索引号" min-width="85" show-overflow-tooltip />
      <el-table-column prop="entity_name" label="被函证单位" min-width="120" show-overflow-tooltip />
      <el-table-column prop="followup_person" label="跟函人员" min-width="75" />
      <el-table-column prop="followup_date" label="跟函日期" min-width="85" />
      <el-table-column label="确认场景" min-width="85" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="row.scenario"
            :type="row.scenario === 'immediate' ? 'success' : 'warning'"
            size="small"
          >
            {{ row.scenario === 'immediate' ? '现场即时确认' : '留函跟踪' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="控制结论" min-width="75" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="row.control_conclusion"
            :type="conclusionTagType(row.control_conclusion)"
            size="small"
          >
            {{ conclusionLabel(row.control_conclusion) }}
          </el-tag>
          <span v-else class="followup-master__empty">—</span>
        </template>
      </el-table-column>
      <el-table-column label="签名状态" min-width="65" align="center">
        <template #default="{ row }">
          <el-tag
            :type="row.sign_status === 'signed' ? 'success' : 'info'"
            size="small"
          >
            {{ row.sign_status === 'signed' ? '已签' : '未签' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import type { FollowupRow } from './followupTypes'

defineProps<{
  rows: FollowupRow[]
  readonly: boolean
  selectedIds: string[]
  isDirty?: boolean
}>()

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'delete'): void
  (e: 'save'): void
  (e: 'import'): void
  (e: 'export-template'): void
  (e: 'export-data'): void
  (e: 'row-click', row: FollowupRow): void
  (e: 'update:selected-ids', ids: string[]): void
}>()

function handleSelectionChange(selection: FollowupRow[]) {
  emit('update:selected-ids', selection.map((r) => r._row_id!))
}

function handleRowClick(row: FollowupRow) {
  emit('row-click', row)
}

function conclusionTagType(conclusion: string): '' | 'success' | 'danger' | 'info' {
  if (conclusion === 'pass') return 'success'
  if (conclusion === 'fail') return 'danger'
  return 'info'
}

function conclusionLabel(conclusion: string): string {
  if (conclusion === 'pass') return '通过'
  if (conclusion === 'fail') return '未通过'
  return '未完成'
}
</script>

<style scoped>
.followup-master__toolbar {
  margin-bottom: 8px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.followup-master__table {
  width: 100%;
}

/* 表头折行 */
.followup-master__table :deep(.el-table__header th .cell) {
  white-space: normal;
  word-break: break-all;
  line-height: 1.3;
  font-size: 12px;
}

.followup-master__table :deep(.el-table__body td .cell) {
  font-size: 12px;
}

/* 勾选列居中 */
.followup-master__table :deep(.el-table-column--selection .cell) {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 0;
}

.followup-master__empty {
  color: #c0c4cc;
}
</style>
