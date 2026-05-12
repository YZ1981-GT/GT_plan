<template>
  <div class="gt-report-config-editor gt-fade-in">
    <GtPageHeader title="报表配置" :show-back="false">
      <template #actions>
        <el-button v-if="!isEditing" size="small" @click="enterEdit">✏️ 编辑</el-button>
        <el-button v-else size="small" type="warning" @click="() => exitEdit()">退出编辑</el-button>
        <el-select v-model="selectedStandard" size="small" style="width: 160px" @change="loadConfig">
          <el-option label="国企版合并" value="soe_consolidated" />
          <el-option label="国企版单体" value="soe_standalone" />
          <el-option label="上市版合并" value="listed_consolidated" />
          <el-option label="上市版单体" value="listed_standalone" />
        </el-select>
        <el-select v-model="selectedReportType" size="small" style="width: 140px" @change="loadConfig">
          <el-option label="资产负债表" value="balance_sheet" />
          <el-option label="利润表" value="income_statement" />
          <el-option label="现金流量表" value="cash_flow_statement" />
          <el-option label="权益变动表" value="equity_statement" />
          <el-option label="现金流附表" value="cash_flow_supplement" />
          <el-option label="资产减值准备表" value="impairment_provision" />
        </el-select>
        <el-button size="small" type="primary" v-permission="'report_config:edit'" @click="onSaveAll" :loading="saving">保存修改</el-button>
        <el-button size="small" @click="onInsertAbove">↑ 在上方插入</el-button>
        <el-button size="small" @click="onAddRow">末尾新增</el-button>
        <el-button size="small" @click="onDeleteSelected" :disabled="selectedRows.length === 0" style="color: #fff; opacity: 0.8;">删除选中 ({{ selectedRows.length }})</el-button>
        <el-button size="small" @click="router.back()">返回</el-button>
      </template>
    </GtPageHeader>

    <div v-if="isEditing" class="gt-edit-mode-ribbon"><span class="gt-edit-mode-icon">✏️</span> 编辑中 · 请记得保存</div>

    <el-table :data="rows" v-loading="loading" border size="small" style="width: 100%"
      row-key="row_code" :row-class-name="rowClassName"
      @selection-change="onSelectionChange" ref="tableRef">
      <el-table-column type="selection" width="40" />
      <el-table-column prop="row_number" label="序号" width="80" align="center" />
      <el-table-column prop="row_code" label="行次编码" min-width="110">
        <template #default="{ row }">
          <span style="white-space: nowrap;">{{ row.row_code }}</span>
        </template>
      </el-table-column>
      <el-table-column label="项目名称" min-width="300">
        <template #default="{ row }">
          <div :style="{ paddingLeft: (row.indent_level || 0) * 20 + 'px', display: 'flex', alignItems: 'center', gap: '4px' }">
            <el-tag v-if="row.is_total_row" size="small" type="warning">合计</el-tag>
            <el-input v-if="row._editing" v-model="row.row_name" size="small" style="flex: 1" />
            <span v-else @dblclick="row._editing = true" style="cursor: pointer">{{ row.row_name }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="缩进" width="80" align="center">
        <template #default="{ row }">
          <el-input-number v-if="row._editing" v-model="row.indent_level" :min="0" :max="3" size="small" :controls="false" style="width: 50px" />
          <span v-else>{{ row.indent_level }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合计" width="60" align="center">
        <template #default="{ row }">
          <el-checkbox v-if="row._editing" v-model="row.is_total_row" />
          <span v-else-if="row.is_total_row" style="color: #1e8a38;">✓</span>
          <span v-else style="color: #ddd;">—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ row }">
          <div style="white-space: nowrap; display: flex; justify-content: center; gap: 4px;">
            <el-button v-if="!row._editing" size="small" link type="primary" @click="row._editing = true">编辑</el-button>
            <el-button v-if="row._editing" size="small" link type="success" @click="row._editing = false">完成</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { confirmBatch, confirmLeave } from '@/utils/confirm'
import { useEditMode } from '@/composables/useEditMode'
import { api } from '@/services/apiProxy'
import * as P from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

const router = useRouter()
const { isEditing, isDirty, enterEdit, exitEdit, markDirty, clearDirty } = useEditMode()

const selectedStandard = ref('soe_consolidated')
const selectedReportType = ref('balance_sheet')
const rows = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)

const standardLabel = computed(() => {
  const m: Record<string, string> = {
    soe_consolidated: '国企版合并',
    soe_standalone: '国企版单体',
    listed_consolidated: '上市版合并',
    listed_standalone: '上市版单体',
  }
  return m[selectedStandard.value] || ''
})

const reportTypeLabel = computed(() => {
  const m: Record<string, string> = {
    balance_sheet: '资产负债表',
    income_statement: '利润表',
    cash_flow_statement: '现金流量表',
    equity_change: '权益变动表',
  }
  return m[selectedReportType.value] || ''
})

function rowClassName({ row }: { row: any }) {
  if (row.is_total_row) return 'gt-total-row'
  if (row.indent_level === 0 && !row.formula) return 'gt-section-row'
  return ''
}

async function loadConfig() {
  loading.value = true
  try {
    const data = await api.get(P.reportConfig.list, {
      params: {
        report_type: selectedReportType.value,
        applicable_standard: selectedStandard.value,
      },
    })
    const items = Array.isArray(data) ? data : (data || [])
    rows.value = items.map((r: any) => ({ ...r, _editing: false }))
  } catch {
    rows.value = []
    ElMessage.warning('加载报表配置失败')
  } finally {
    loading.value = false
  }
}

// 多选
const selectedRows = ref<any[]>([])
const tableRef = ref<any>(null)
function onSelectionChange(selection: any[]) {
  selectedRows.value = selection
}

function _makeNewRow(number: number) {
  return {
    id: null,
    row_code: `NEW-${String(number).padStart(3, '0')}`,
    row_number: number,
    row_name: '新行',
    indent_level: 1,
    formula: null,
    is_total_row: false,
    parent_row_code: null,
    _editing: true,
    _isNew: true,
  }
}

function onAddRow() {
  const lastRow = rows.value[rows.value.length - 1]
  const nextNumber = lastRow ? (lastRow.row_number || 0) + 1 : 1
  rows.value.push(_makeNewRow(nextNumber))
}

function onInsertAbove() {
  if (selectedRows.value.length === 0) {
    ElMessage.warning('请先选中一行')
    return
  }
  // 在第一个选中行的上方插入
  const firstSelected = selectedRows.value[0]
  const idx = rows.value.indexOf(firstSelected)
  if (idx < 0) return
  const number = firstSelected.row_number || idx + 1
  rows.value.splice(idx, 0, _makeNewRow(number))
  // 重新编号
  rows.value.forEach((r, i) => { r.row_number = i + 1 })
}

async function onDeleteSelected() {
  if (selectedRows.value.length === 0) return
  await confirmBatch('删除', selectedRows.value.length)
  for (const row of selectedRows.value) {
    if (row.id && !row._isNew) {
      try {
        await api.delete(P.reportConfig.detail(row.id))
      } catch { /* ignore */ }
    }
    const idx = rows.value.indexOf(row)
    if (idx >= 0) rows.value.splice(idx, 1)
  }
  selectedRows.value = []
  rows.value.forEach((r, i) => { r.row_number = i + 1 })
  ElMessage.success('已删除')
}

async function onSaveAll() {
  saving.value = true
  try {
    let savedCount = 0
    for (const row of rows.value) {
      if (row._isNew) {
        // 新增行 — POST 创建
        const created = await api.post(P.reportConfig.list, {
          report_type: selectedReportType.value,
          applicable_standard: selectedStandard.value,
          row_number: row.row_number,
          row_code: row.row_code,
          row_name: row.row_name,
          indent_level: row.indent_level,
          formula: row.formula,
          is_total_row: row.is_total_row,
        })
        const newRow = created?.data ?? created
        if (newRow?.id) {
          row.id = newRow.id
          row._isNew = false
        }
        savedCount++
      } else if (row.id) {
        await api.put(P.reportConfig.detail(row.id), {
          row_name: row.row_name,
          formula: row.formula,
          indent_level: row.indent_level,
          is_total_row: row.is_total_row,
        })
        savedCount++
      }
    }
    ElMessage.success(`已保存 ${savedCount} 行`)
    rows.value.forEach(r => { r._editing = false })
  } catch (e: any) {
    handleApiError(e, '保存')
  } finally {
    saving.value = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.gt-report-config-editor { padding: var(--gt-space-5); }
.gt-rce-banner {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 16px 24px;
  margin-bottom: 16px;
  color: #fff;
  position: relative;
  overflow: hidden;
}
.gt-rce-banner-text h2 { margin: 0 0 2px; font-size: 18px; }
.gt-rce-banner-text p { margin: 0; font-size: 12px; opacity: 0.75; }
.gt-rce-banner-actions { display: flex; gap: 8px; align-items: center; }
.gt-rce-banner-actions .el-button { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); color: #fff; }
.gt-rce-banner-actions .el-button:hover { background: rgba(255,255,255,0.25); }

:deep(.gt-total-row) { font-weight: 700; background-color: #fafafa !important; }
:deep(.gt-section-row) { background-color: #f5f0ff !important; font-weight: 600; }
</style>
