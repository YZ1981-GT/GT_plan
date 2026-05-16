<template>
  <div class="gt-report-config-editor gt-fade-in">
    <GtPageHeader title="报表配置" :show-back="true" back-mode="history" />

    <!-- 工具栏：左侧筛选 + 右侧操作 -->
    <div class="rce-toolbar">
      <div class="rce-toolbar-left">
        <el-select v-model="selectedStandard" size="small" style="width: 140px" @change="loadConfig">
          <el-option label="国企版合并" value="soe_consolidated" />
          <el-option label="国企版单体" value="soe_standalone" />
          <el-option label="上市版合并" value="listed_consolidated" />
          <el-option label="上市版单体" value="listed_standalone" />
        </el-select>
        <el-select v-model="selectedReportType" size="small" style="width: 130px" @change="loadConfig">
          <el-option label="资产负债表" value="balance_sheet" />
          <el-option label="利润表" value="income_statement" />
          <el-option label="现金流量表" value="cash_flow_statement" />
          <el-option label="权益变动表" value="equity_statement" />
          <el-option label="现金流附表" value="cash_flow_supplement" />
          <el-option label="资产减值准备表" value="impairment_provision" />
        </el-select>
        <el-tag type="info" size="small" effect="plain">{{ rows.length }} 行</el-tag>
      </div>
      <div class="rce-toolbar-right">
        <template v-if="!isEditing">
          <el-button size="small" type="primary" plain @click="enterEdit">✏️ 进入编辑</el-button>
        </template>
        <template v-else>
          <el-button size="small" @click="onInsertAbove" :disabled="selectedRows.length === 0">↑ 上方插入</el-button>
          <el-button size="small" @click="onAddRow">+ 末尾新增</el-button>
          <el-button size="small" type="danger" plain @click="onDeleteSelected" :disabled="selectedRows.length === 0">
            删除 ({{ selectedRows.length }})
          </el-button>
          <el-divider direction="vertical" />
          <el-button size="small" type="primary" v-permission="'report_config:edit'" @click="onSaveAll" :loading="saving">
            💾 保存
          </el-button>
          <el-button size="small" @click="() => exitEdit()">退出编辑</el-button>
        </template>
      </div>
    </div>

    <!-- 编辑模式提示条 -->
    <div v-if="isEditing" class="rce-edit-ribbon">
      <span>✏️ 编辑模式 · 双击项目名称可直接修改，完成后点击"保存"</span>
    </div>

    <!-- 数据表格 -->
    <el-table
      :data="rows"
      v-loading="loading"
      border
      size="small"
      style="width: 100%"
      row-key="row_code"
      :row-class-name="rowClassName"
      @selection-change="onSelectionChange"
      ref="tableRef"
      :header-cell-style="{ background: '#f0edf5', fontWeight: '600' }"
    >
      <el-table-column v-if="isEditing" type="selection" width="40" />
      <el-table-column prop="row_number" label="序号" width="100" align="center" />
      <el-table-column prop="row_code" label="行次编码" width="120">
        <template #default="{ row }">
          <span class="rce-code">{{ row.row_code }}</span>
        </template>
      </el-table-column>
      <el-table-column label="项目名称" min-width="320">
        <template #default="{ row }">
          <div class="rce-name-cell" :style="{ paddingLeft: (row.indent_level || 0) * 20 + 'px' }">
            <el-tag v-if="row.is_total_row" size="small" type="warning" effect="plain">合计</el-tag>
            <el-input
              v-if="row._editing"
              v-model="row.row_name"
              size="small"
              style="flex: 1"
              @blur="row._editing = false"
            />
            <span v-else class="rce-name-text" @dblclick="isEditing && (row._editing = true)">
              {{ row.row_name }}
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="缩进" width="100" align="center">
        <template #default="{ row }">
          <el-input-number
            v-if="isEditing"
            v-model="row.indent_level"
            :min="0"
            :max="3"
            size="small"
            :controls="false"
            style="width: 44px"
          />
          <span v-else class="rce-indent">{{ row.indent_level }}</span>
        </template>
      </el-table-column>
      <el-table-column label="合计行" width="100" align="center">
        <template #default="{ row }">
          <el-checkbox v-if="isEditing" v-model="row.is_total_row" />
          <span v-else-if="row.is_total_row" style="color: var(--gt-color-success);">✓</span>
          <span v-else style="color: var(--gt-color-border);">—</span>
        </template>
      </el-table-column>
      <el-table-column v-if="isEditing" label="操作" width="80" align="center">
        <template #default="{ row }">
          <el-button
            v-if="!row._editing"
            size="small"
            link
            type="primary"
            @click="row._editing = true"
          >编辑</el-button>
          <el-button
            v-else
            size="small"
            link
            type="success"
            @click="row._editing = false"
          >完成</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { confirmBatch } from '@/utils/confirm'
import { useEditMode } from '@/composables/useEditMode'
import { api } from '@/services/apiProxy'
import * as P from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

const router = useRouter()
const { isEditing, isDirty, enterEdit, exitEdit, markDirty, clearDirty } = useEditMode()

const selectedStandard = ref('soe_standalone')
const selectedReportType = ref('balance_sheet')
const rows = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)

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
  const firstSelected = selectedRows.value[0]
  const idx = rows.value.indexOf(firstSelected)
  if (idx < 0) return
  const number = firstSelected.row_number || idx + 1
  rows.value.splice(idx, 0, _makeNewRow(number))
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
.gt-report-config-editor {
  padding: 16px 20px;
}

/* 工具栏 */
.rce-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  margin-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
}
.rce-toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.rce-toolbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 编辑模式提示条 */
.rce-edit-ribbon {
  background: var(--gt-bg-warning);
  border: 1px solid #faecd8;
  border-radius: 6px;
  padding: 8px 16px;
  margin-bottom: 12px;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-wheat);
}

/* 表格单元格 */
.rce-code {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  color: var(--gt-color-teal);
  white-space: nowrap;
}
.rce-name-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}
.rce-name-text {
  cursor: default;
  line-height: 1.5;
}
.rce-indent {
  color: var(--gt-color-info);
  font-size: var(--gt-font-size-xs);
}

/* 行样式 */
:deep(.gt-total-row) {
  font-weight: 700;
  background-color: var(--gt-color-bg) !important;
}
:deep(.gt-section-row) {
  background-color: var(--gt-color-primary-bg) !important;
  font-weight: 600;
}
:deep(.gt-section-row td) {
  border-bottom: 1px solid #e8e0f5 !important;
}
</style>
