<template>
  <!--
    Sprint C.3 — NoteTableEditor (D1/D2/D4/D5)
    
    覆盖任务：
    - C.3.2: 动态行视觉（黄底 + ★）
    - C.3.3: 动态列视觉（紫底 + +）+ 拖动调宽 + 合并表头 + 冻结列
    - C.3.4: 添加明细行/列按钮
    - C.3.5: 删除右键 + 公式栏多源选项 + 数据源 chip
  -->
  <div class="note-table-editor" :class="{ 'editor-edit-mode': editMode }">
    <!-- 工具栏：添加按钮 + 公式栏 -->
    <div v-if="editMode" class="editor-toolbar">
      <el-button-group size="small">
        <el-button @click="handleAddDynamicRow" :disabled="!hasDynamicRowRegion">
          ➕ 添加明细行
        </el-button>
        <el-button @click="handleAddDynamicColumn">
          ➕ 添加列
        </el-button>
      </el-button-group>

      <!-- 公式栏（多源选项） -->
      <div v-if="selectedCell" class="formula-bar">
        <span class="formula-label">{{ selectedCellLabel }}:</span>
        <el-input
          v-model="formulaInput"
          size="small"
          placeholder="输入公式或值"
          style="flex: 1"
          @change="onFormulaChange"
        />
        <el-select
          v-model="dataSourceType"
          size="small"
          style="width: 150px"
          placeholder="数据源"
        >
          <el-option label="手动输入" value="manual" />
          <el-option label="试算表" value="trial_balance" />
          <el-option label="底稿数据" value="wp_data" />
          <el-option label="辅助账" value="aux_balance" />
          <el-option label="公式" value="formula" />
          <el-option label="上年附注" value="prior_year_note" />
          <el-option label="合并汇总" value="consol_aggregation" />
        </el-select>
      </div>
    </div>

    <!-- 表格主体 -->
    <div class="editor-table-wrap">
      <el-table
        :data="rowsData"
        border
        size="small"
        :max-height="maxHeight"
        :cell-class-name="cellClassName"
        :header-cell-class-name="headerCellClassName"
        @cell-click="onCellClick"
        @cell-contextmenu="onCellContextMenu"
        ref="tableRef"
      >
        <!-- 动态生成列 -->
        <el-table-column
          v-for="(col, colIdx) in columnDefs"
          :key="col.id"
          :prop="String(colIdx)"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth || 100"
          :fixed="col.is_frozen ? 'left' : false"
          :resizable="true"
          show-overflow-tooltip
        >
          <!-- 合并表头：多级 header_path -->
          <template v-if="col.header_path && col.header_path.length > 1" #header>
            <div class="multi-header">
              <div v-for="(seg, idx) in col.header_path" :key="idx" class="header-seg">
                {{ seg }}
              </div>
            </div>
          </template>

          <template #default="{ row, $index }">
            <div class="cell-content">
              <!-- 数据源 chip -->
              <el-tag
                v-if="getCellSourceTag(rowIndex2($index), colIdx)"
                :type="getCellSourceTagType(rowIndex2($index), colIdx)"
                size="small"
                class="source-chip"
              >
                {{ getCellSourceTag(rowIndex2($index), colIdx) }}
              </el-tag>
              <span class="cell-value">{{ row[colIdx] }}</span>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 右键菜单 -->
    <div
      v-if="contextMenu.visible"
      class="context-menu"
      :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
      @click.stop
    >
      <div class="menu-item" @click="handleDeleteRow">
        🗑️ 删除行
      </div>
      <div class="menu-item" @click="handleDeleteColumn">
        ❌ 删除列
      </div>
      <div class="menu-item" @click="handleClearCell">
        🧹 清空单元格
      </div>
      <div class="menu-item" @click="handleCopyCell">
        📋 复制
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'

interface ColumnDef {
  id: string
  label: string
  header_path?: string[]
  col_type?: 'fixed' | 'dynamic'
  value_type?: string
  width?: number
  minWidth?: number
  is_frozen?: boolean
}

interface Props {
  modelValue: any  // table_data
  editMode?: boolean
  maxHeight?: string | number
}

const props = withDefaults(defineProps<Props>(), {
  editMode: false,
  maxHeight: 'calc(100vh - 280px)',
})

const emit = defineEmits<{
  'update:modelValue': [val: any]
  'add-dynamic-row': [regionName: string]
  'add-dynamic-column': []
  'delete-row': [rowIndex: number]
  'delete-column': [colId: string]
  'cell-update': [rowIndex: number, colIdx: number, value: any, source: string]
}>()

const tableRef = ref()
const selectedCell = ref<{ rowIndex: number; colIdx: number } | null>(null)
const formulaInput = ref('')
const dataSourceType = ref('manual')
const contextMenu = ref({ visible: false, x: 0, y: 0, rowIndex: -1, colIdx: -1, colId: '' })

// ─── Computed ──────────────────────────────────────────────────────────────

const columnDefs = computed<ColumnDef[]>(() => {
  const td = props.modelValue
  if (!td) return []

  // 优先使用 _columns_meta（D2 sidecar）
  if (td._columns_meta && Array.isArray(td._columns_meta)) {
    return td._columns_meta
  }

  // Fallback: headers 数组
  const headers = td.headers || []
  return headers.map((h: any, idx: number) => ({
    id: `col_${idx}`,
    label: typeof h === 'string' ? h : (h.label || `列${idx + 1}`),
    col_type: 'fixed',
    width: undefined,
  }))
})

const rowsData = computed(() => {
  const td = props.modelValue
  if (!td?.rows) return []
  return td.rows.map((row: any, rowIdx: number) => {
    const cells = row.cells || row.values || []
    const obj: any = { _row_idx: rowIdx, _row_type: row.row_type, _label: row.label }
    cells.forEach((cell: any, idx: number) => {
      obj[idx] = typeof cell === 'object' ? cell?.value : cell
    })
    return obj
  })
})

const dynamicRegions = computed<any[]>(() => {
  return props.modelValue?._dynamic_regions || []
})

const hasDynamicRowRegion = computed(() =>
  dynamicRegions.value.some(r => r.axis === 'row')
)

const selectedCellLabel = computed(() => {
  if (!selectedCell.value) return ''
  const col = columnDefs.value[selectedCell.value.colIdx]
  return `${col?.label || '列'} 行${selectedCell.value.rowIndex + 1}`
})

// ─── Helpers ───────────────────────────────────────────────────────────────

function rowIndex2(i: number): number {
  return rowsData.value[i]?._row_idx ?? i
}

function isRowDynamic(rowIdx: number): boolean {
  const row = props.modelValue?.rows?.[rowIdx]
  if (!row) return false
  const rt = row.row_type || ''
  return rt.startsWith('dynamic_')
}

function isColDynamic(colIdx: number): boolean {
  const col = columnDefs.value[colIdx]
  return col?.col_type === 'dynamic'
}

function cellClassName({ row, columnIndex }: { row: any; columnIndex: number }): string {
  const classes: string[] = []
  const rowIdx = row?._row_idx ?? -1
  if (isRowDynamic(rowIdx)) classes.push('cell-dynamic-row')
  if (isColDynamic(columnIndex)) classes.push('cell-dynamic-col')
  if (
    selectedCell.value?.rowIndex === rowIdx &&
    selectedCell.value?.colIdx === columnIndex
  ) {
    classes.push('cell-selected')
  }
  // 数据源样式
  const provenance = getCellProvenance(rowIdx, columnIndex)
  if (provenance?.source === 'wp_data') classes.push('cell-source-wp')
  if (provenance?.source === 'trial_balance') classes.push('cell-source-tb')
  if (provenance?.source === 'manual') classes.push('cell-source-manual')
  return classes.join(' ')
}

function headerCellClassName({ columnIndex }: { columnIndex: number }): string {
  return isColDynamic(columnIndex) ? 'header-dynamic-col' : ''
}

function getCellProvenance(rowIdx: number, colIdx: number): any {
  const provenance = props.modelValue?._cell_provenance || {}
  const key = `${rowIdx}:${colIdx}`
  return provenance[key]
}

function getCellSourceTag(rowIdx: number, colIdx: number): string {
  const p = getCellProvenance(rowIdx, colIdx)
  if (!p?.source || p.source === 'manual') return ''
  const map: Record<string, string> = {
    wp_data: '底稿',
    trial_balance: 'TB',
    aux_balance: '辅助账',
    formula: 'Σ',
    prior_year_note: '上年',
    consol_aggregation: '汇总',
  }
  return map[p.source] || p.source
}

function getCellSourceTagType(rowIdx: number, colIdx: number): 'success' | 'warning' | 'info' | 'primary' | 'danger' {
  const p = getCellProvenance(rowIdx, colIdx)
  if (!p) return 'info'
  if (p.source === 'wp_data') return 'success'
  if (p.source === 'trial_balance') return 'primary'
  if (p.source === 'formula') return 'warning'
  if (p.fallback_used) return 'warning'
  return 'info'
}

// ─── Event handlers ────────────────────────────────────────────────────────

function onCellClick(row: any, _column: any, _cell: any, _event: MouseEvent) {
  const rowIdx = row._row_idx ?? -1
  const colIdx = _column?.no ?? -1
  if (rowIdx < 0 || colIdx < 0) return

  selectedCell.value = { rowIndex: rowIdx, colIdx }
  // Load cell value into formula bar
  const cell = row[colIdx]
  formulaInput.value = String(cell ?? '')
  // Load existing data source
  const prov = getCellProvenance(rowIdx, colIdx)
  dataSourceType.value = prov?.source || 'manual'
}

function onCellContextMenu(row: any, column: any, _cell: any, event: MouseEvent) {
  event.preventDefault()
  const rowIdx = row?._row_idx ?? -1
  const colIdx = column?.no ?? -1
  contextMenu.value = {
    visible: true,
    x: event.clientX,
    y: event.clientY,
    rowIndex: rowIdx,
    colIdx,
    colId: columnDefs.value[colIdx]?.id || '',
  }
}

function hideContextMenu() {
  contextMenu.value.visible = false
}

function onFormulaChange(val: string) {
  if (!selectedCell.value) return
  const { rowIndex, colIdx } = selectedCell.value
  emit('cell-update', rowIndex, colIdx, val, dataSourceType.value)
}

function handleAddDynamicRow() {
  const region = dynamicRegions.value.find(r => r.axis === 'row')
  if (!region) {
    ElMessage.warning('当前章节无动态行区域，无法添加')
    return
  }
  emit('add-dynamic-row', region.name || '')
}

function handleAddDynamicColumn() {
  emit('add-dynamic-column')
}

async function handleDeleteRow() {
  hideContextMenu()
  const rowIdx = contextMenu.value.rowIndex
  if (rowIdx < 0) return
  if (!isRowDynamic(rowIdx)) {
    ElMessage.warning('仅支持删除动态行')
    return
  }
  try {
    await ElMessageBox.confirm('确定删除此行？', '确认删除', { type: 'warning' })
    emit('delete-row', rowIdx)
  } catch {
    // cancelled
  }
}

async function handleDeleteColumn() {
  hideContextMenu()
  const colIdx = contextMenu.value.colIdx
  if (colIdx < 0) return
  if (!isColDynamic(colIdx)) {
    ElMessage.warning('仅支持删除动态列')
    return
  }
  try {
    await ElMessageBox.confirm('确定删除此列？此列所有数据将丢失', '确认删除', { type: 'warning' })
    emit('delete-column', contextMenu.value.colId)
  } catch {
    // cancelled
  }
}

function handleClearCell() {
  hideContextMenu()
  const { rowIndex, colIdx } = contextMenu.value
  if (rowIndex < 0 || colIdx < 0) return
  emit('cell-update', rowIndex, colIdx, '', 'manual')
}

async function handleCopyCell() {
  hideContextMenu()
  const { rowIndex, colIdx } = contextMenu.value
  if (rowIndex < 0 || colIdx < 0) return
  const row = props.modelValue?.rows?.[rowIndex]
  if (!row) return
  const cell = (row.cells || [])[colIdx]
  const value = typeof cell === 'object' ? cell?.value : cell
  try {
    await navigator.clipboard.writeText(String(value ?? ''))
    ElMessage.success('已复制')
  } catch (e) {
    handleApiError(e, '保存')
  }
}

// Click outside to close context menu
function onDocClick() {
  if (contextMenu.value.visible) hideContextMenu()
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
})

watch(() => props.modelValue, () => {
  selectedCell.value = null
  formulaInput.value = ''
})

defineExpose({ tableRef, selectedCell })
</script>

<style scoped>
.note-table-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 8px;
  background: #f8f9fb;
  border-radius: 4px;
}

.formula-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.formula-label {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
}

/* 动态行：浅黄底色 + ★ */
:deep(.cell-dynamic-row) {
  background-color: #fffbe6 !important;
}
:deep(.cell-dynamic-row .cell-value::before) {
  content: '★ ';
  color: #e6a23c;
  font-size: 11px;
}

/* 动态列：浅紫底色 */
:deep(.cell-dynamic-col) {
  background-color: #f3eaff !important;
}
:deep(.header-dynamic-col) {
  background-color: #e8d5ff !important;
}

/* 选中单元格 */
:deep(.cell-selected) {
  outline: 2px solid #6c4cff;
  outline-offset: -2px;
}

/* 数据源样式 */
:deep(.cell-source-wp) {
  border-left: 2px solid #67c23a;
}
:deep(.cell-source-tb) {
  border-left: 2px solid #6c4cff;
}
:deep(.cell-source-manual) {
  /* default */
}

/* 合并表头 */
.multi-header {
  display: flex;
  flex-direction: column;
}
.header-seg {
  padding: 2px 0;
  border-bottom: 1px solid #ebeef5;
}
.header-seg:last-child {
  border-bottom: none;
}

/* 单元格内容 */
.cell-content {
  display: flex;
  align-items: center;
  gap: 4px;
}
.source-chip {
  flex-shrink: 0;
  font-size: 10px;
  height: 16px;
  padding: 0 4px;
  line-height: 14px;
}
.cell-value {
  flex: 1;
  text-align: right;
}

/* 右键菜单 */
.context-menu {
  position: fixed;
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  z-index: 9999;
  min-width: 140px;
  padding: 4px 0;
}
.menu-item {
  padding: 6px 16px;
  cursor: pointer;
  font-size: 13px;
}
.menu-item:hover {
  background: #f5f7fa;
}
</style>
