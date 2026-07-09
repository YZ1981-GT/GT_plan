<template>
  <div class="i2-detail">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-2 明细表 — 开发支出明细(61列4区段)</span>
      <div class="section-actions">
        <el-dropdown size="small" trigger="click">
          <el-button size="small" type="default" plain>导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" text @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
      </div>
    </div>

    <!-- 4区段 Tab 切换 -->
    <el-segmented
      v-model="activeSegmentIndex"
      :options="segmentOptions"
      class="segment-switcher"
      @change="onSegmentChange"
    />

    <!-- 数据表 -->
    <el-table
      :data="displayRows"
      border
      size="small"
      :row-class-name="getRowClassName"
      highlight-current-row
      class="detail-table"
      @current-change="onRowSelect"
    >
      <el-table-column
        v-for="col in currentColumns"
        :key="col.key"
        :prop="col.key"
        :label="col.label"
        :min-width="col.width"
        :align="col.type === 'number' || col.type === 'formula' ? 'right' : 'left'"
      >
        <template #header>
          <el-tooltip v-if="col.type === 'formula'" :content="col.tooltip" placement="top">
            <span class="formula-col-header">{{ col.label }}</span>
          </el-tooltip>
          <span v-else>{{ col.label }}</span>
        </template>
        <template #default="{ row, $index }">
          <!-- 合计行：只读 -->
          <template v-if="row._isTotal">
            <span class="total-text">
              {{ col.type === 'number' || col.type === 'formula' ? fmtAmount((row as any)[col.key]) : (row as any)[col.key] }}
            </span>
          </template>
          <!-- 公式列：只读 + 虚线 -->
          <template v-else-if="col.type === 'formula'">
            <el-tooltip :content="col.tooltip" placement="top">
              <span class="formula-value">{{ fmtAmount((row as any)[col.key]) }}</span>
            </el-tooltip>
          </template>
          <!-- 数值编辑列 -->
          <template v-else-if="col.type === 'number' && col.editable">
            <el-input-number
              :model-value="(row as any)[col.key]"
              size="small"
              :controls="false"
              @change="(v: number) => onCellChange($index, col.key, v)"
            />
          </template>
          <!-- 日期编辑列 -->
          <template v-else-if="col.type === 'date' && col.editable">
            <el-date-picker
              :model-value="(row as any)[col.key]"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              placeholder="选择日期"
              style="width: 100%"
              @change="(v: string) => onCellChange($index, col.key, v)"
            />
          </template>
          <!-- 选择列 -->
          <template v-else-if="col.type === 'select' && col.editable">
            <el-select
              :model-value="(row as any)[col.key]"
              size="small"
              placeholder="选择"
              style="width: 100%"
              @change="(v: string) => onCellChange($index, col.key, v)"
            >
              <el-option v-for="opt in (col as any).options" :key="opt" :label="opt" :value="opt" />
            </el-select>
          </template>
          <!-- 文本编辑列 -->
          <template v-else-if="col.editable">
            <el-input
              :model-value="(row as any)[col.key]"
              size="small"
              @change="(v: string) => onCellChange($index, col.key, v)"
            />
          </template>
          <!-- 只读文本 -->
          <template v-else>
            <span>{{ (row as any)[col.key] }}</span>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- 操作按钮 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain @click="handleAddRow">
        + 新增项目
      </el-button>
      <el-button
        v-if="activeRowIndex >= 0"
        size="small"
        type="danger"
        plain
        @click="handleRemoveRow"
      >
        删除选中行
      </el-button>
      <el-button size="small" type="success" @click="handleSave">
        保存
      </el-button>
    </div>

    <!-- 交叉验证提示 -->
    <div v-if="crossValidation.hasWarning" class="cross-validation-warning">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
      >
        明细表资本化期末合计({{ fmtAmount(crossValidation.detailEndTotal) }})
        与审定表期末合计({{ fmtAmount(crossValidation.adjEndTotal) }})
        差异 {{ fmtAmount(crossValidation.difference) }}，请核对。
      </el-alert>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useI2Detail } from '../../../composables/useI2Detail'
import type { ChecklistItem } from '../../../composables/useI2FormData'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
}>()

const emit = defineEmits<{
  'save': []
  'navigate-sheet': [sheetName: string]
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses as Map<string, ChecklistItem>)

const {
  rows,
  activeSegment,
  activeRowIndex,
  totalRow,
  crossValidation,
  activeColumns,
  segments,
  switchSegment,
  setActiveRow,
  updateField,
  addRow,
  removeRow,
  save: saveData,
} = useI2Detail({
  allResponses: allResponsesRef,
  saveResponses: props.saveResponse,
})

// ─── Segment Switcher ────────────────────────────────────────────────────────

const segmentOptions = segments.map((s) => s.label)
const activeSegmentIndex = ref(segmentOptions[0])

function onSegmentChange(val: string) {
  const idx = segmentOptions.indexOf(val)
  if (idx >= 0) switchSegment(idx)
}

const currentColumns = computed(() => activeColumns.value)

// ─── Display Rows ────────────────────────────────────────────────────────────

const displayRows = computed(() => {
  const dataRows = rows.value.map((r) => ({ ...r, _isTotal: false }))
  const total = { ...totalRow.value, _isTotal: true }
  return [...dataRows, total]
})

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (row._isTotal) return 'total-row'
  return ''
}

// ─── Row Select (sync across segments) ───────────────────────────────────────

function onRowSelect(row: any) {
  if (!row || row._isTotal) return
  const idx = rows.value.findIndex((r) => r.rowId === row.rowId)
  setActiveRow(idx)
}

// ─── Cell Change ─────────────────────────────────────────────────────────────

function onCellChange(displayIndex: number, field: string, value: any) {
  if (displayIndex >= rows.value.length) return
  updateField(displayIndex, field, value ?? 0)
}

// ─── Add / Remove Row ────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入研发项目名称', '新增项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：XX平台开发项目',
    })
    if (value?.trim()) {
      addRow(value.trim())
      ElMessage.success('已添加项目')
    }
  } catch {
    // cancelled
  }
}

function handleRemoveRow() {
  if (activeRowIndex.value >= 0) {
    removeRow(activeRowIndex.value)
  }
}

// ─── Save ────────────────────────────────────────────────────────────────────

async function handleSave() {
  await saveData()
  emit('save')
  ElMessage.success('明细表已保存')
}

// ─── Import/Export (placeholder) ─────────────────────────────────────────────

function handleExportTemplate() { ElMessage.info('导出模板功能开发中') }
function handleExportData() { ElMessage.info('导出数据功能开发中') }
function handleImportData() { ElMessage.info('导入数据功能开发中') }

// ─── AI ──────────────────────────────────────────────────────────────────────

function handleAiGenerate() {
  console.log('[I2-Detail] AI generate')
}

// ─── Formatter ───────────────────────────────────────────────────────────────

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '-'
  if (typeof value === 'string') return value
  if (Math.abs(value) < 0.005) return '-'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i2-detail {
  font-size: 13px;
  padding: 16px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}
.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.segment-switcher {
  margin-bottom: 14px;
}
.detail-table {
  font-size: 13px;
  margin-bottom: 12px;
}
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}
.formula-value {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  color: #409eff;
}
.total-text {
  font-weight: 600;
  color: #303133;
}
.table-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.cross-validation-warning {
  margin-top: 12px;
}
:deep(.total-row) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}
</style>
