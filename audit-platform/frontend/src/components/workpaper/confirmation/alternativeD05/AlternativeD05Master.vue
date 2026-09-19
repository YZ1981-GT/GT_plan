<template>
  <div class="alternative-master">
    <!-- 工具栏 -->
    <div class="alternative-master__toolbar">
      <el-button v-if="!readonly" size="small" type="primary" @click="$emit('add-company')">
        <el-icon><Plus /></el-icon> {{ labelsResolved.addButton }}
      </el-button>
      <el-button v-if="!readonly" size="small" plain @click="$emit('import-d01')">
        {{ labelsResolved.importFromSummary }}
      </el-button>
      <el-button v-if="!readonly" size="small" plain @click="$emit('import-excel')">
        导入 Excel
      </el-button>
      <el-button size="small" plain @click="$emit('export-template')">
        导出模板
      </el-button>
      <el-button size="small" plain @click="$emit('export-data')">
        导出数据
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
      table-layout="auto"
      @current-change="handleSelect"
      :row-class-name="rowClassName"
      class="alternative-master__table"
    >
      <el-table-column prop="seq" label="序号" min-width="40" align="center" />
      <el-table-column prop="entity_name" :label="labelsResolved.entityColumn" min-width="130">
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.entity_name"
            size="small"
            :placeholder="labelsResolved.entityPlaceholder"
            @change="(val: string) => $emit('update-field', row._company_id, 'entity_name', val)"
          />
          <template v-else>
            <span>{{ row.entity_name || '—' }}</span>
            <el-tag v-if="row._source === 'auto'" size="small" type="info" class="ml-4">自动带入</el-tag>
          </template>
        </template>
      </el-table-column>
      <el-table-column prop="confirm_index" label="函证索引号" min-width="85">
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.confirm_index"
            size="small"
            :placeholder="labelsResolved.confirmIndexPlaceholder"
            @change="(val: string) => $emit('update-field', row._company_id, 'confirm_index', val)"
          />
          <span v-else>{{ row.confirm_index || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="完成度" min-width="65" align="center">
        <template #default="{ row }">
          <span :class="completionClass(row)">
            {{ getCompletionStatus(row).completed }}/4
          </span>
        </template>
      </el-table-column>
      <el-table-column label="异常" min-width="55" align="center">
        <template #default="{ row }">
          <el-tag v-if="hasAbnormal(row)" type="danger" size="small">是</el-tag>
          <span v-else class="text-secondary">—</span>
        </template>
      </el-table-column>
      <!--
        两个检查比例列按循环取标签（`type` 仍是 `'receipt' | 'shipment'` → 本组件的
        `getCheckRatio` prop 签名不变；各循环用自己的 `getCheckRatioForMaster` 适配器
        把这两个键映射到本循环口径，G0-6 即 receipt→payment / shipment→inbound）。
      -->
      <el-table-column
        v-for="col in labelsResolved.ratioColumns"
        :key="col.type"
        :label="col.label"
        min-width="70"
        align="right"
      >
        <template #default="{ row }">
          {{ formatRatio(getCheckRatio(row, col.type)) }}
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="55" align="center">
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
      <el-table-column v-if="!readonly" label="操作" min-width="50" align="center">
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
      {{ labelsResolved.emptyText }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Plus, Check } from '@element-plus/icons-vue'
import type { AlternativeCompany, BlockType } from './alternativeD05Types'
import {
  resolveAlternativeMasterLabels,
  type AlternativeMasterLabels,
} from './alternativeMasterLabels'

const props = defineProps<{
  companies: AlternativeCompany[]
  readonly: boolean
  isDirty: boolean
  getCompletionStatus: (c: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (c: AlternativeCompany) => boolean
  getCheckRatio: (c: AlternativeCompany, type: 'receipt' | 'shipment') => number | null
  /**
   * 按循环覆盖主表文案（**可选**）。
   * 不传 = 套 `DEFAULT_ALTERNATIVE_MASTER_LABELS`，与改造前逐字节相同（零回归）。
   */
  labels?: Partial<AlternativeMasterLabels> | null
}>()

const labelsResolved = computed(() => resolveAlternativeMasterLabels(props.labels))

const emit = defineEmits<{
  (e: 'select', companyId: string): void
  (e: 'add-company'): void
  (e: 'delete-company', companyId: string): void
  (e: 'update-field', companyId: string, field: string, value: any): void
  (e: 'import-d01'): void
  (e: 'import-excel'): void
  (e: 'export-template'): void
  (e: 'export-data'): void
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
  font-size: var(--wp-font-size, 13px);
}

/* 表头折行 */
.alternative-master__table :deep(.el-table__header th .cell) {
  white-space: normal;
  word-break: break-all;
  line-height: 1.3;
  font-size: var(--wp-font-size, 13px);
}

.alternative-master__table :deep(.el-table__body td .cell) {
  font-size: var(--wp-font-size, 13px);
}

.alternative-master__empty {
  padding: 12px 0;
  text-align: center;
  color: #909399;
  font-size: 12px;
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
