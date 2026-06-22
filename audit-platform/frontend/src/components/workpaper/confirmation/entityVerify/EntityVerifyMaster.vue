<template>
  <div class="entity-verify-master">
    <div v-if="!readonly" class="entity-verify-master__toolbar">
      <el-button type="primary" size="small" @click="$emit('add')">
        <el-icon><Plus /></el-icon> 新增
      </el-button>
      <el-button type="danger" size="small" :disabled="!selectedIds.length" @click="$emit('delete')">
        删除选中
      </el-button>
      <el-button type="success" size="small" @click="$emit('save')">
        保存
      </el-button>
      <el-button size="small" @click="$emit('import')">
        导入
      </el-button>
      <el-button size="small" @click="$emit('export')">
        导出模板
      </el-button>
    </div>
    <el-table
      :data="rows"
      @selection-change="onSelectionChange"
      @row-click="(row) => $emit('row-click', row)"
      highlight-current-row
      border
      size="small"
      class="entity-verify-master__table"
    >
      <el-table-column v-if="!readonly" type="selection" width="40" />
      <el-table-column prop="seq" label="序号" width="60" align="center" />
      <el-table-column prop="confirm_index" label="索引号" width="100" />
      <el-table-column prop="entity_name" label="被询证单位" min-width="160" show-overflow-tooltip />
      <el-table-column prop="account_type" label="科目" width="120" />
      <el-table-column prop="first_result" label="发函结果" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.first_result === '送抵'" type="success" size="small">送抵</el-tag>
          <el-tag v-else-if="row.first_result === '退回'" type="danger" size="small">退回</el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="row_status" label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-badge
            v-if="row.row_status === 'fraud_flag'"
            is-dot
            class="entity-verify-master__badge entity-verify-master__badge--red"
          >
            <span class="entity-verify-master__status entity-verify-master__status--red">舞弊</span>
          </el-badge>
          <el-badge
            v-else-if="row.row_status === 'suspect'"
            is-dot
            class="entity-verify-master__badge entity-verify-master__badge--orange"
          >
            <span class="entity-verify-master__status entity-verify-master__status--orange">疑似</span>
          </el-badge>
          <span v-else class="entity-verify-master__status entity-verify-master__status--green">正常</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import type { EntityVerifyRow } from './entityVerifyTypes'

defineProps<{
  rows: EntityVerifyRow[]
  readonly: boolean
  selectedIds: string[]
}>()

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'delete'): void
  (e: 'save'): void
  (e: 'import'): void
  (e: 'export'): void
  (e: 'row-click', row: EntityVerifyRow): void
  (e: 'update:selectedIds', ids: string[]): void
}>()

function onSelectionChange(selection: EntityVerifyRow[]) {
  emit('update:selectedIds', selection.map((r) => r._row_id!))
}
</script>

<style scoped>
.entity-verify-master__toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.entity-verify-master__table {
  width: 100%;
}

.entity-verify-master__status {
  font-size: 12px;
  font-weight: 500;
}

.entity-verify-master__status--green {
  color: var(--el-color-success);
}

.entity-verify-master__status--orange {
  color: var(--el-color-warning);
}

.entity-verify-master__status--red {
  color: var(--el-color-danger);
}

.entity-verify-master__badge--red :deep(.el-badge__content) {
  background-color: var(--el-color-danger);
}

.entity-verify-master__badge--orange :deep(.el-badge__content) {
  background-color: var(--el-color-warning);
}
</style>
