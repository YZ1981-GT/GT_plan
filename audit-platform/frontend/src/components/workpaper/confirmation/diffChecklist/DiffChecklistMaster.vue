<template>
  <div class="diff-checklist-master">
    <!-- 工具栏 -->
    <div class="diff-checklist-master__toolbar">
      <el-button-group>
        <el-button size="small" type="primary" :icon="Plus" :disabled="readonly" @click="$emit('add')">
          新增公司
        </el-button>
        <el-button size="small" type="danger" :icon="Delete" :disabled="readonly || !selectedIds.length" @click="$emit('delete', selectedIds)">
          删除
        </el-button>
        <el-button size="small" :icon="Download" :disabled="readonly" @click="$emit('import-d04')">
          从 D0-4 带入
        </el-button>
      </el-button-group>
      <el-button-group>
        <el-button size="small" :disabled="readonly" @click="$emit('import-excel')">
          导入
        </el-button>
        <el-button size="small" @click="$emit('export-template')">
          导出模板
        </el-button>
        <el-button size="small" @click="$emit('export-excel')">
          导出数据
        </el-button>
      </el-button-group>
      <div class="diff-checklist-master__toolbar-right">
        <el-button size="small" type="success" :disabled="readonly || !isDirty" @click="$emit('save')">
          保存
        </el-button>
      </div>
    </div>

    <!-- 公司列表 -->
    <el-table
      ref="tableRef"
      :data="companies"
      border
      stripe
      size="small"
      highlight-current-row
      max-height="400"
      row-key="_row_id"
      table-layout="auto"
      :row-class-name="getRowClassName"
      @selection-change="handleSelectionChange"
      @current-change="handleCurrentChange"
      class="diff-checklist-master__table"
    >
      <el-table-column v-if="!readonly" type="selection" width="36" align="center" />
      <el-table-column label="序号" prop="seq" min-width="45" align="center" />
      <el-table-column label="函证索引号" prop="confirm_index" min-width="90">
        <template #default="{ row }">
          <span class="diff-checklist-master__link" @click="$emit('jump-d04', row.confirm_index)">
            {{ row.confirm_index || '—' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="被询证单位" prop="entity_name" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="!readonly"
            :model-value="row.entity_name"
            size="small"
            placeholder="单位名称"
            @change="(val: string) => $emit('update', row._row_id, 'entity_name', val)"
          />
          <span v-else>{{ row.entity_name || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目" prop="subject" min-width="90">
        <template #default="{ row }">
          <el-select
            v-if="!readonly"
            :model-value="row.subject"
            size="small"
            filterable
            allow-create
            default-first-option
            placeholder="选择科目"
            @change="(val: string) => $emit('update', row._row_id, 'subject', val)"
          >
            <el-option
              v-for="opt in subjectOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <span v-else>{{ row.subject || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="A 回函金额" prop="a_reply_amount" min-width="90" align="right">
        <template #header>
          <el-tooltip content="取数来源：D0-1 函证汇总表中该公司的回函金额" placement="top">
            <span style="cursor:help;border-bottom:1px dashed #909399">A 回函金额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="diff-checklist-master__amount">{{ formatAmount(row.a_reply_amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="E 账面金额" prop="e_book_amount" min-width="90" align="right">
        <template #header>
          <el-tooltip content="取数来源：D0-1 函证汇总表中该公司的发函金额（即我方账面余额）" placement="top">
            <span style="cursor:help;border-bottom:1px dashed #909399">E 账面金额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="diff-checklist-master__amount">{{ formatAmount(row.e_book_amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="I 最终差异" prop="i_final_diff" min-width="90" align="right">
        <template #header>
          <el-tooltip content="自动计算：I = D - H = (A+B-C) - (E+F-G)，为0表示已平衡" placement="top">
            <span style="cursor:help;border-bottom:1px dashed #909399">I 最终差异</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span
            :class="[
              'diff-checklist-master__amount',
              { 'diff-checklist-master__amount--alert': row.status === 'over_materiality' },
              { 'diff-checklist-master__amount--diff': row.status === 'diff' },
            ]"
          >
            {{ formatAmount(row.i_final_diff) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="70" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small" effect="dark">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="来源" min-width="50" align="center">
        <template #default="{ row }">
          <el-tag v-if="row._source === 'auto'" size="small" type="primary" effect="plain">自动</el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 空态提示 -->
    <div v-if="!companies.length" class="diff-checklist-master__empty">
      <span style="color:#909399;font-size:12px">暂无数据，请新增公司或从 D0-4 带入</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Plus, Delete, Download } from '@element-plus/icons-vue'
import type { DiffChecklistCompany } from './diffChecklistTypes'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  companies: DiffChecklistCompany[]
  readonly: boolean
  isDirty: boolean
  subjectOptions: { value: string; label: string }[]
}>()

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'delete', ids: string[]): void
  (e: 'save'): void
  (e: 'update', companyId: string, field: string, value: any): void
  (e: 'import-d04'): void
  (e: 'import-excel'): void
  (e: 'export-excel'): void
  (e: 'export-template'): void
  (e: 'jump-d04', confirmIndex: string): void
  (e: 'select', company: DiffChecklistCompany | null): void
}>()

const tableRef = ref()
const selectedIds = ref<string[]>([])
const prefs = useDisplayPrefsStore()

function handleSelectionChange(selection: DiffChecklistCompany[]) {
  selectedIds.value = selection.map((c) => c._row_id!).filter(Boolean)
}

function handleCurrentChange(row: DiffChecklistCompany | null) {
  emit('select', row)
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function formatAmount(val?: number): string {
  if (val == null) return '—'
  return prefs.fmt(val)
}

function statusTagType(status?: string): string {
  if (status === 'balanced') return 'success'
  if (status === 'over_materiality') return 'danger'
  if (status === 'diff') return 'warning'
  return 'info'
}

function statusLabel(status?: string): string {
  if (status === 'balanced') return '已平衡'
  if (status === 'over_materiality') return '超重要性'
  if (status === 'diff') return '有差异'
  return '待调节'
}

function getRowClassName({ row }: { row: DiffChecklistCompany }) {
  if (row.status === 'over_materiality') return 'diff-checklist-master__row--alert'
  if (row.status === 'balanced') return 'diff-checklist-master__row--balanced'
  return ''
}
</script>

<style scoped>
.diff-checklist-master__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.diff-checklist-master__toolbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 表头折行 + 字号 */
.diff-checklist-master__table :deep(.el-table__header th .cell) {
  white-space: normal;
  word-break: break-all;
  line-height: 1.3;
  font-size: 13px;
}

.diff-checklist-master__table :deep(.el-table__body td .cell) {
  font-size: 13px;
}

/* 勾选列居中 */
.diff-checklist-master__table :deep(.el-table-column--selection .cell) {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 0;
}

.diff-checklist-master__amount {
  font-variant-numeric: tabular-nums;
}

.diff-checklist-master__amount--alert {
  color: var(--el-color-danger);
  font-weight: 600;
}

.diff-checklist-master__amount--diff {
  color: var(--el-color-warning-dark-2);
  font-weight: 500;
}

.diff-checklist-master__link {
  color: var(--el-color-primary);
  cursor: pointer;
  text-decoration: underline;
}

.diff-checklist-master__empty {
  padding: 12px;
  text-align: center;
}

:deep(.diff-checklist-master__row--alert) {
  background-color: var(--el-color-danger-light-9) !important;
}

:deep(.diff-checklist-master__row--balanced) {
  opacity: 0.7;
}
</style>
