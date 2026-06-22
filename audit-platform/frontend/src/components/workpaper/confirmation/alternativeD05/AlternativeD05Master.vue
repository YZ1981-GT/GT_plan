<template>
  <div class="alternative-master">
    <!-- 工具栏 -->
    <div class="alternative-master__toolbar">
      <el-button v-if="!readonly" size="small" type="primary" @click="$emit('add-company')">
        <el-icon><Plus /></el-icon> 新增公司
      </el-button>
      <el-button v-if="!readonly" size="small" plain @click="$emit('import-d01')">
        从 D0-1 带入
      </el-button>
      <el-button v-if="!readonly" size="small" plain @click="$emit('import-excel')">
        导入 Excel
      </el-button>
      <el-button size="small" plain @click="$emit('export-excel')">
        导出模板
      </el-button>
      <el-button v-if="isDirty && !readonly" size="small" type="success" @click="$emit('save')">
        <el-icon><Check /></el-icon> 保存
      </el-button>
    </div>

    <!-- 公司主表 -->
    <el-table
      :data="companies"
      border
      stripe
      size="small"
      highlight-current-row
      @current-change="handleSelect"
      :row-class-name="rowClassName"
      class="alternative-master__table"
    >
      <el-table-column prop="seq" label="序号" width="50" align="center" />
      <el-table-column prop="entity_name" label="供应商/客户名称" min-width="160">
        <template #default="{ row }">
          <span>{{ row.entity_name || '—' }}</span>
          <el-tag v-if="row._source === 'auto'" size="small" type="info" class="ml-4">
            自动带入
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="confirm_index" label="函证索引号" width="110" />
      <el-table-column label="完成度" width="100" align="center">
        <template #default="{ row }">
          <span :class="completionClass(row)">
            {{ getCompletionStatus(row).completed }}/4
          </span>
        </template>
      </el-table-column>
      <el-table-column label="异常" width="70" align="center">
        <template #default="{ row }">
          <el-tag v-if="hasAbnormal(row)" type="danger" size="small">是</el-tag>
          <span v-else class="text-secondary">—</span>
        </template>
      </el-table-column>
      <el-table-column label="收款比例" width="95" align="right">
        <template #default="{ row }">
          {{ formatRatio(getCheckRatio(row, 'receipt')) }}
        </template>
      </el-table-column>
      <el-table-column label="出库比例" width="95" align="right">
        <template #default="{ row }">
          {{ formatRatio(getCheckRatio(row, 'shipment')) }}
        </template>
      </el-table-column>
      <el-table-column label="结论" width="80" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="row.conclusion?.conclusion_type"
            :type="row.conclusion.conclusion_type === 'A' ? 'success' : row.conclusion.conclusion_type === 'B' ? 'warning' : 'danger'"
            size="small"
          >
            {{ row.conclusion.conclusion_type }}
          </el-tag>
          <span v-else class="text-secondary">—</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!readonly" label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button
            size="small"
            type="danger"
            link
            @click.stop="$emit('delete-company', row._company_id)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空态 -->
    <div v-if="companies.length === 0" class="alternative-master__empty">
      <el-empty description="暂无公司记录，请新增或从 D0-1 带入未回函公司" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Check } from '@element-plus/icons-vue'
import type { AlternativeCompany, BlockType } from './alternativeD05Types'

const props = defineProps<{
  companies: AlternativeCompany[]
  readonly: boolean
  isDirty: boolean
  getCompletionStatus: (c: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (c: AlternativeCompany) => boolean
  getCheckRatio: (c: AlternativeCompany, type: 'receipt' | 'shipment') => number | null
}>()

const emit = defineEmits<{
  (e: 'select', companyId: string): void
  (e: 'add-company'): void
  (e: 'delete-company', companyId: string): void
  (e: 'import-d01'): void
  (e: 'import-excel'): void
  (e: 'export-excel'): void
  (e: 'save'): void
}>()

function handleSelect(row: AlternativeCompany | null) {
  if (row?._company_id) {
    emit('select', row._company_id)
  }
}

function rowClassName({ row }: { row: AlternativeCompany }) {
  if (props.hasAbnormal(row)) return 'alternative-master__row--abnormal'
  const status = props.getCompletionStatus(row)
  if (status.completed === 0) return 'alternative-master__row--empty'
  return ''
}

function completionClass(row: AlternativeCompany) {
  const status = props.getCompletionStatus(row)
  if (status.completed === 4) return 'text-success'
  if (status.completed === 0) return 'text-danger'
  return 'text-warning'
}

function formatRatio(val: number | null): string {
  if (val === null) return 'N/A'
  return `${val.toFixed(1)}%`
}
</script>

<style scoped>
.alternative-master__toolbar {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.alternative-master__table {
  font-size: 12px;
}

.alternative-master__empty {
  padding: 20px 0;
}

.ml-4 { margin-left: 4px; }
.text-secondary { color: var(--el-text-color-secondary); }
.text-success { color: var(--el-color-success); font-weight: 600; }
.text-warning { color: var(--el-color-warning); font-weight: 600; }
.text-danger { color: var(--el-color-danger); font-weight: 600; }

:deep(.alternative-master__row--abnormal) {
  background-color: var(--el-color-danger-light-9) !important;
}
:deep(.alternative-master__row--empty) {
  background-color: var(--el-color-warning-light-9) !important;
}
</style>
