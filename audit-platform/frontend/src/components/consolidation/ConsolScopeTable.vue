<template>
  <div class="gt-consol-scope-table">
    <!-- Toolbar -->
    <div class="table-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="batchInclude" :disabled="!selectedRows.length">
          批量纳入
        </el-button>
        <el-button size="small" @click="batchExclude" :disabled="!selectedRows.length">
          批量排除
        </el-button>
        <el-button size="small" @click="handleExport" plain>导出</el-button>
      </div>
      <div class="toolbar-right">
        <el-button size="small" @click="handleSave" type="primary" :loading="saving" :disabled="!hasChanges">
          保存变更
        </el-button>
        <el-button size="small" @click="refresh" :loading="loading" plain>刷新</el-button>
      </div>
    </div>

    <!-- Summary -->
    <div class="scope-summary">
      <el-tag type="primary" size="small">
        纳入合并范围: {{ summary.included }} 家
      </el-tag>
      <el-tag type="info" size="small">
        排除: {{ summary.excluded }} 家
      </el-tag>
      <el-tag v-if="summary.scopeChanges > 0" type="warning" size="small">
        范围变更: {{ summary.scopeChanges }} 项
      </el-tag>
    </div>

    <!-- Table -->
    <el-table
      ref="tableRef"
      :data="tableData"
      v-loading="loading"
      border
      stripe
      size="small"
      row-key="id"
      @selection-change="handleSelectionChange"
      class="gt-scope-table"
    >
      <el-table-column type="selection" width="40" />

      <el-table-column prop="companyCode" label="公司代码" width="140" />
      <el-table-column prop="companyName" label="公司名称" min-width="200" show-overflow-tooltip />

      <el-table-column label="合并方法" width="130">
        <template #default="{ row }">
          <el-tag :type="consolMethodTagType(row.scopeChangeType || row.consolMethod)" size="small">
            {{ consolMethodLabel(row.scopeChangeType || row.consolMethod) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="纳入状态" width="110" align="center">
        <template #default="{ row }">
          <el-switch
            v-model="row.isIncluded"
            active-text="纳入"
            inactive-text="排除"
            :loading="row._loading"
            @change="onIncludeToggle(row)"
          />
        </template>
      </el-table-column>

      <el-table-column label="变更类型" width="120">
        <template #default="{ row }">
          <el-tag
            v-if="row.scopeChangeType && row.scopeChangeType !== 'none'"
            :type="scopeChangeTagType(row.scopeChangeType)"
            size="small"
          >
            {{ scopeChangeLabel(row.scopeChangeType) }}
          </el-tag>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="200">
        <template #default="{ row }">
          <el-input
            v-model="row.notes"
            size="small"
            placeholder="输入备注"
            @change="markChanged(row)"
          />
        </template>
      </el-table-column>

      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text @click="handleViewDetails(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Summary Footer -->
    <div class="table-footer">
      <span>共 {{ tableData.length }} 条记录</span>
      <span v-if="hasChanges" class="unsaved-hint">有未保存的变更</span>
    </div>

    <!-- Details Dialog -->
    <el-dialog v-model="detailsVisible" title="合并范围详情" width="560px">
      <el-descriptions v-if="detailsRow" :column="2" border size="small">
        <el-descriptions-item label="公司代码">{{ detailsRow.companyCode }}</el-descriptions-item>
        <el-descriptions-item label="公司名称">{{ detailsRow.companyName }}</el-descriptions-item>
        <el-descriptions-item label="纳入状态">
          <el-tag :type="detailsRow.isIncluded ? 'success' : 'info'" size="small">
            {{ detailsRow.isIncluded ? '纳入' : '排除' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="变更类型">
          {{ scopeChangeLabel(detailsRow.scopeChangeType) }}
        </el-descriptions-item>
        <el-descriptions-item label="纳入原因" :span="2">{{ detailsRow.inclusionReason || '—' }}</el-descriptions-item>
        <el-descriptions-item label="排除原因" :span="2">{{ detailsRow.exclusionReason || '—' }}</el-descriptions-item>
        <el-descriptions-item label="变更说明" :span="2">{{ detailsRow.scopeChangeDescription || '—' }}</el-descriptions-item>
        <el-descriptions-item label="备注" :span="2">{{ detailsRow.notes || '—' }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import type { ElTable } from 'element-plus'
import { getConsolScope, batchUpdateConsolScope, type ConsolScopeRow } from '@/services/consolidationApi'

// ─── Types ─────────────────────────────────────────────────────────────────────
interface ScopeRow extends ConsolScopeRow {
  _loading?: boolean
  _changed?: boolean
}

// ─── Props & Emits ─────────────────────────────────────────────────────────────
const props = defineProps<{
  projectId: string
  year: number
}>()

// ─── State ────────────────────────────────────────────────────────────────────
const tableRef = ref<InstanceType<typeof ElTable>>()
const tableData = ref<ScopeRow[]>([])
const loading = ref(false)
const saving = ref(false)
const selectedRows = ref<ScopeRow[]>([])
const changedRows = ref<Set<string>>(new Set())

const detailsVisible = ref(false)
const detailsRow = ref<ScopeRow | null>(null)

// ─── Summary ──────────────────────────────────────────────────────────────────
const summary = computed(() => ({
  included: tableData.value.filter(r => r.isIncluded).length,
  excluded: tableData.value.filter(r => !r.isIncluded).length,
  scopeChanges: tableData.value.filter(r => r.scopeChangeType && r.scopeChangeType !== 'none').length,
}))

const hasChanges = computed(() => changedRows.value.size > 0)

// ─── Helpers ─────────────────────────────────────────────────────────────────
function consolMethodLabel(method: string | null | undefined): string {
  if (!method) return '—'
  const map: Record<string, string> = {
    full: '完全合并',
    proportional: '比例合并',
    equity: '权益法',
    exclude: '排除',
    new_inclusion: '新纳入',
    exclusion: '已排除',
    method_change: '方法变更',
  }
  return map[method] || method
}

function consolMethodTagType(method: string | null | undefined): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  if (!method) return ''
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    full: 'primary',
    proportional: 'success',
    equity: 'warning',
    exclude: 'info',
    new_inclusion: 'success',
    exclusion: 'danger',
    method_change: 'warning',
  }
  return map[method] || ''
}

function scopeChangeLabel(type: string | null): string {
  if (!type || type === 'none') return '无变更'
  const map: Record<string, string> = {
    new_inclusion: '新纳入',
    exclusion: '已排除',
    method_change: '方法变更',
  }
  return map[type] || type
}

function scopeChangeTagType(type: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    new_inclusion: 'success',
    exclusion: 'danger',
    method_change: 'warning',
  }
  return map[type] || ''
}

// ─── Data Loading ─────────────────────────────────────────────────────────────
async function refresh() {
  loading.value = true
  try {
    const rows = await getConsolScope(props.projectId, props.year)
    tableData.value = rows.map(r => ({ ...r, _changed: false }))
    changedRows.value.clear()
  } catch (e) {
    ElMessage.error('加载合并范围失败')
  } finally {
    loading.value = false
  }
}

// ─── Row Tracking ──────────────────────────────────────────────────────────────
function markChanged(row: ScopeRow) {
  row._changed = true
  changedRows.value.add(row.id)
}

function onIncludeToggle(row: ScopeRow) {
  row.scopeChangeType = row.isIncluded ? 'new_inclusion' : 'exclusion'
  markChanged(row)
}

// ─── Batch Operations ──────────────────────────────────────────────────────────
function handleSelectionChange(selection: ScopeRow[]) {
  selectedRows.value = selection
}

async function batchInclude() {
  for (const row of selectedRows.value) {
    if (!row.isIncluded) {
      row.isIncluded = true
      row.scopeChangeType = 'new_inclusion'
      markChanged(row)
    }
  }
  ElMessage.success('已批量纳入')
}

async function batchExclude() {
  for (const row of selectedRows.value) {
    if (row.isIncluded) {
      row.isIncluded = false
      row.scopeChangeType = 'exclusion'
      markChanged(row)
    }
  }
  ElMessage.success('已批量排除')
}

// ─── Save ─────────────────────────────────────────────────────────────────────
async function handleSave() {
  saving.value = true
  try {
    const changedItems = tableData.value
      .filter(r => r._changed)
      .map(r => ({
        year: r.year,
        company_code: r.companyCode,
        is_included: r.isIncluded,
        inclusion_reason: r.inclusionReason,
        exclusion_reason: r.exclusionReason,
        scope_change_type: r.scopeChangeType || 'none',
        scope_change_description: r.scopeChangeDescription,
        notes: r.notes,
      }))

    await batchUpdateConsolScope(props.projectId, props.year, changedItems)
    changedRows.value.clear()
    tableData.value.forEach(r => { r._changed = false })
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

// ─── Export ───────────────────────────────────────────────────────────────────
function handleExport() {
  const csv = [
    ['公司代码', '公司名称', '纳入状态', '合并方法', '变更类型', '备注'].join(','),
    ...tableData.value.map(r =>
      [
        r.companyCode,
        r.companyName,
        r.isIncluded ? '纳入' : '排除',
        consolMethodLabel(r.scopeChangeType || r.consolMethod),
        scopeChangeLabel(r.scopeChangeType),
        (r.notes || '').replace(/,/g, '，'),
      ].join(','),
    ),
  ].join('\n')

  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `合并范围_${props.year}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('导出成功')
}

// ─── Details ───────────────────────────────────────────────────────────────────
function handleViewDetails(row: ScopeRow) {
  detailsRow.value = row
  detailsVisible.value = true
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(() => refresh())
</script>

<style scoped>
.gt-consol-scope-table {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-3);
}

.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  gap: var(--gt-space-2);
}

.scope-summary {
  display: flex;
  gap: var(--gt-space-2);
}

.gt-scope-table :deep(.el-table__row) {
  height: 40px;
}

.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  color: #666;
}

.unsaved-hint {
  color: var(--gt-color-coral);
  font-weight: 500;
}

.text-muted {
  color: #aaa;
}
</style>
