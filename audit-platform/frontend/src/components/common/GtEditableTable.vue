<template>
  <div ref="containerRef" class="gt-editable-table" :class="{ 'gt-fullscreen': fullscreen.isFullscreen.value }">
    <!-- 工具栏 -->
    <GtToolbar v-if="showToolbar" variant="default">
      <template #left>
        <slot name="toolbar-left" />
        <template v-if="editable && editMode.isEditing.value">
          <el-button size="small" @click="handleAddRow">+ 新增行</el-button>
          <el-button size="small" type="danger" :disabled="!toolbar.selectedCount.value"
            @click="handleDeleteRows">
            删除{{ toolbar.selectedCount.value ? `(${toolbar.selectedCount.value})` : '' }}
          </el-button>
        </template>
      </template>
      <template #right>
        <slot name="toolbar-right" />
        <el-button-group v-if="editable" size="small">
          <el-button :type="editMode.isEditing.value ? '' : 'primary'" @click="handleExitEdit">
            📋 查看
          </el-button>
          <el-button :type="editMode.isEditing.value ? 'primary' : ''" @click="handleEnterEdit">
            ✏️ 编辑
          </el-button>
        </el-button-group>
        <el-tooltip content="全屏编辑（ESC 退出）" placement="bottom">
          <el-button size="small" @click="fullscreen.toggleFullscreen()">
            {{ fullscreen.isFullscreen.value ? '退出全屏' : '⛶ 全屏' }}
          </el-button>
        </el-tooltip>
      </template>
    </GtToolbar>

    <!-- 主表格 -->
    <el-table
      ref="tableRef"
      :data="displayData"
      border
      size="small"
      :max-height="tableMaxHeight"
      :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
      :header-cell-style="mergedHeaderStyle"
      :cell-style="mergedCellStyle"
      :cell-class-name="combinedCellClassName"
      :show-summary="showSummary"
      :summary-method="summaryMethod"
      @selection-change="onTableSelectionChange"
      @cell-click="onCellClick"
      @cell-contextmenu="onCellContextMenu"
      :span-method="groupBy ? groupSpanMethod : undefined"
      :row-class-name="groupBy ? groupRowClassName : undefined"
    >
      <!-- 展开行插槽 -->
      <el-table-column v-if="$slots.expand" type="expand" width="36">
        <template #default="{ row, $index }">
          <slot name="expand" :row="row" :index="$index" />
        </template>
      </el-table-column>

      <!-- 多选列 -->
      <el-table-column
        v-if="showSelection && editable && editMode.isEditing.value"
        type="selection"
        width="36"
      />

      <!-- 动态列 -->
      <el-table-column
        v-for="col in visibleColumns"
        :key="col.prop"
        :prop="col.prop"
        :label="col.label"
        :width="col.width"
        :min-width="col.minWidth || 120"
        :sortable="col.sortable ?? (defaultSortable ? 'custom' : false)"
        :fixed="col.fixed || false"
        :align="col.align || 'left'"
        :filters="col.filterOptions"
        :filter-method="col.filterOptions ? ((value: any, row: any) => row[col.prop] === value) : undefined"
      >
        <!-- 自定义表头插槽 -->
        <template v-if="$slots[`header-${col.prop}`]" #header>
          <slot :name="`header-${col.prop}`" :column="col" />
        </template>

        <!-- 单元格内容 -->
        <template #default="{ row, $index }">
          <!-- 优先使用外部自定义插槽
               slot props: { row, index($index in displayData), dataIndex(index in modelValue), editing, col }
               分组模式下 $index 包含分组头行，dataIndex 才是 modelValue 中的真实索引 -->
          <slot
            v-if="$slots[`col-${col.prop}`]"
            :name="`col-${col.prop}`"
            :row="row"
            :index="$index"
            :data-index="groupBy ? modelValue.indexOf(row) : $index"
            :editing="editMode.isEditing.value"
            :col="col"
          />
          <!-- 内置编辑模式 -->
          <template v-else-if="editable && editMode.isEditing.value && col.editable !== false && !isCellLocked(col, row, $index)">
            <template v-if="lazyEdit && lazyEditState">
              <!-- 懒加载编辑：点击才渲染编辑控件 -->
              <component
                v-if="lazyEditState.isEditing($index, getColIdx(col.prop))"
                :is="getEditComponent(col)"
                v-model="row[col.prop]"
                size="small"
                v-bind="getEditProps(col)"
                @blur="onEditBlur(col, row, $index)"
                @input="editMode.markDirty()"
                @change="editMode.markDirty()"
                autofocus
              />
              <span
                v-else
                class="gt-et-cell-text gt-et-cell-editable"
                @click="lazyEditState.startEdit($index, getColIdx(col.prop))"
              >{{ formatCellValue(row, col) }}</span>
            </template>
            <template v-else>
              <!-- 直接编辑模式 -->
              <component
                :is="getEditComponent(col)"
                v-model="row[col.prop]"
                size="small"
                v-bind="getEditProps(col)"
                @input="editMode.markDirty()"
                @change="editMode.markDirty()"
              />
            </template>
          </template>
          <!-- 锁定单元格（显示锁定图标） -->
          <CommentTooltip
            v-else-if="editable && editMode.isEditing.value && isCellLocked(col, row, $index)"
            :comment="getCellComment($index, getColIdx(col.prop))"
          >
            <span class="gt-et-cell-text gt-et-cell-locked" title="此单元格已锁定">🔒 {{ formatCellValue(row, col) }}</span>
          </CommentTooltip>
          <!-- 查看模式 -->
          <CommentTooltip
            v-else
            :comment="getCellComment($index, getColIdx(col.prop))"
          >
            <span class="gt-et-cell-text">{{ formatCellValue(row, col) }}</span>
          </CommentTooltip>
        </template>
      </el-table-column>

      <!-- 额外列插槽 -->
      <slot name="extra-columns" />
    </el-table>

    <!-- 表格底部 -->
    <div v-if="showFooter" class="gt-et-footer">
      <slot name="footer-left">
        <span class="gt-et-footer-info">共 {{ modelValue.length }} 行</span>
      </slot>
      <span style="flex:1" />
      <slot name="footer-right" />
    </div>

    <!-- 选中区域状态栏 -->
    <SelectionBar v-if="showSelectionBar" :stats="cellSelection.selectionStats()" />

    <!-- 右键菜单 -->
    <CellContextMenu
      :visible="cellSelection.contextMenu.visible"
      :x="cellSelection.contextMenu.x"
      :y="cellSelection.contextMenu.y"
      :item-name="contextItemName"
      :value="contextValue"
      :multi-count="cellSelection.selectedCells.value.length"
      @copy="handleCtxCopy"
      @formula="$emit('ctx-formula')"
      @sum="handleCtxSum"
      @compare="$emit('ctx-compare')"
    >
      <slot name="context-menu" :selected-cells="cellSelection.selectedCells.value" />
    </CellContextMenu>
  </div>
</template>

<script setup lang="ts">
/** GtEditableTable — 高阶可编辑表格组件 [R5.2]
 *
 * R10 Spec B / Sprint 3.1.3 兼容 wrapper：
 * - 本组件保持原有所有功能不变（避免 breaking 改动）
 * - 新代码请按场景使用 GtTableExtended（列表型）或 GtFormTable（编辑型）
 * - 60 天观察期后无新增引用即可删除
 */
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useCellSelection } from '@/composables/useCellSelection'
import { useLazyEdit } from '@/composables/useLazyEdit'
import { useEditMode } from '@/composables/useEditMode'
import { useFullscreen } from '@/composables/useFullscreen'
import { useTableToolbar } from '@/composables/useTableToolbar'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { copySelection, pasteToSelection, setupPasteListener } from '@/composables/useCopyPaste'
import { useKeyboardNav } from '@/composables/useKeyboardNav'
import SelectionBar from '@/components/common/SelectionBar.vue'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'

// ── 类型定义 ──────────────────────────────────────────────────────────────────
export interface GtColumn {
  prop: string; label: string; width?: number | string; minWidth?: number | string
  formatter?: (value: any, row: any) => string; sortable?: boolean | 'custom'
  fixed?: 'left' | 'right' | boolean; align?: 'left' | 'center' | 'right'
  editable?: boolean; editType?: 'input' | 'number' | 'select' | 'date'
  editOptions?: Array<{ label: string; value: any }>; hidden?: boolean
  headerSlot?: string; cellSlot?: string
  /** 数值范围校验 [R10.2]：{ min, max, message } */
  validator?: { min?: number; max?: number; message?: string }
  /** 单元格锁定 [R10.3]：锁定的列不可编辑（公式行/已复核行/合计行） */
  locked?: boolean | ((row: Record<string, any>, rowIndex: number) => boolean)
  /** 分组字段 [R10.4]：用于分组折叠 */
  groupBy?: boolean
  /** 是否默认开启筛选 [R10.5] */
  filterable?: boolean
  /** 筛选选项（用于 el-table-column filters） */
  filterOptions?: Array<{ text: string; value: any }>
}

// ── Props ─────────────────────────────────────────────────────────────────────
const props = withDefaults(defineProps<{
  modelValue: Record<string, any>[]; columns: GtColumn[]; editable?: boolean
  showSelection?: boolean; lazyEdit?: boolean; sheetKey?: string
  maxHeight?: string | number; showToolbar?: boolean; showSelectionBar?: boolean
  showFooter?: boolean; showSummary?: boolean
  summaryMethod?: (param: { columns: any[]; data: any[] }) => any[]
  headerCellStyle?: Record<string, any>; cellStyle?: Record<string, any>
  defaultRow?: () => Record<string, any>
  getComment?: (rowIdx: number, colIdx: number) => any
  cellClassName?: (params: { rowIndex: number; columnIndex: number }) => string
  /** 分组折叠字段 [R10.4] */
  groupBy?: string
  /** 排序筛选默认开启 [R10.5] */
  defaultSortable?: boolean
}>(), {
  editable: false, showSelection: false, lazyEdit: true, sheetKey: '',
  maxHeight: 'calc(100vh - 260px)', showToolbar: true, showSelectionBar: true,
  showFooter: true, showSummary: false, defaultSortable: true,
})

// ── Emits ─────────────────────────────────────────────────────────────────────
const emit = defineEmits<{
  (e: 'update:modelValue', data: Record<string, any>[]): void; (e: 'save'): void
  (e: 'row-click', row: any, index: number): void; (e: 'cell-click', row: any, col: GtColumn, index: number): void
  (e: 'selection-change', rows: any[]): void; (e: 'ctx-formula'): void; (e: 'ctx-compare'): void
  (e: 'edit-change', isEditing: boolean): void; (e: 'dirty-change', isDirty: boolean): void
}>()

// ── Composables ───────────────────────────────────────────────────────────────
const displayPrefs = useDisplayPrefsStore()
const cellSelection = useCellSelection()
const editMode = useEditMode({ guardRoute: false })
const fullscreen = useFullscreen()
// lazyEdit 仅在 editable=true 时初始化，editable=false 时无需创建编辑状态
const lazyEditState = (props.lazyEdit && props.editable) ? useLazyEdit() : null
const tableDataRef = computed({
  get: () => props.modelValue, set: (v) => emit('update:modelValue', v),
})
const toolbar = useTableToolbar(tableDataRef)

// ── Refs ──────────────────────────────────────────────────────────────────────
const containerRef = ref<HTMLElement | null>(null)
const tableRef = ref<any>(null)

// ── 计算属性 ──────────────────────────────────────────────────────────────────
const visibleColumns = computed(() => props.columns.filter(c => !c.hidden))
const tableMaxHeight = computed(() => fullscreen.isFullscreen.value ? 'calc(100vh - 120px)' : props.maxHeight)

// ── 分组折叠 [R10.4] ─────────────────────────────────────────────────────────
const collapsedGroups = ref(new Set<string>())

const displayData = computed(() => {
  if (!props.groupBy) return props.modelValue
  const groupField = props.groupBy
  const result: Record<string, any>[] = []
  let currentGroup = ''
  for (const row of props.modelValue) {
    const groupVal = String(row[groupField] ?? '')
    if (groupVal !== currentGroup) {
      currentGroup = groupVal
      // 插入分组头行
      result.push({ _isGroupHeader: true, _groupKey: groupVal, _groupField: groupField })
    }
    if (!collapsedGroups.value.has(groupVal)) {
      result.push(row)
    }
  }
  return result
})

function toggleGroup(groupKey: string) {
  if (collapsedGroups.value.has(groupKey)) {
    collapsedGroups.value.delete(groupKey)
  } else {
    collapsedGroups.value.add(groupKey)
  }
  // Force reactivity
  collapsedGroups.value = new Set(collapsedGroups.value)
}

/** 分组行合并列 */
function groupSpanMethod({ row, columnIndex }: { row: any; columnIndex: number }) {
  if (row._isGroupHeader) {
    if (columnIndex === 0) {
      return { rowspan: 1, colspan: visibleColumns.value.length + (props.showSelection ? 1 : 0) }
    }
    return { rowspan: 0, colspan: 0 }
  }
  return { rowspan: 1, colspan: 1 }
}

/** 分组行样式 */
function groupRowClassName({ row }: { row: any }) {
  return row._isGroupHeader ? 'gt-et-group-header-row' : ''
}

const mergedHeaderStyle = computed(() => ({
  background: '#f0edf5', fontSize: '12px', color: '#333', padding: '4px 0', ...props.headerCellStyle,
}))
const mergedCellStyle = computed(() => ({
  padding: '2px 6px', fontSize: '12px', lineHeight: '1.4', ...props.cellStyle,
}))

// 列 prop → 列索引映射
const colPropToIdx = computed(() => {
  const map = new Map<string, number>()
  const offset = (props.showSelection && props.editable && editMode.isEditing.value) ? 1 : 0
  visibleColumns.value.forEach((col, i) => map.set(col.prop, i + offset))
  return map
})
function getColIdx(prop: string): number { return colPropToIdx.value.get(prop) ?? 0 }

const contextItemName = ref('')
const contextValue = ref<any>(null)

// ── 拖拽框选 ──────────────────────────────────────────────────────────────────
cellSelection.setupTableDrag(tableRef, (rowIdx: number, colIdx: number) => {
  const row = props.modelValue[rowIdx]
  if (!row) return null
  const offset = (props.showSelection && props.editable && editMode.isEditing.value) ? 1 : 0
  const col = visibleColumns.value[colIdx - offset]
  return col ? (row[col.prop] ?? null) : null
})

// ── 粘贴监听 ──────────────────────────────────────────────────────────────────
setupPasteListener(tableRef, (event: ClipboardEvent) => {
  if (!editMode.isEditing.value) return
  const cols = visibleColumns.value.map(c => ({ key: c.prop, label: c.label }))
  const written = pasteToSelection(event, cellSelection.selectedCells.value, props.modelValue, cols, () => editMode.markDirty())
  if (written > 0) emit('update:modelValue', [...props.modelValue])
})

// ── 键盘导航（Tab/Enter/方向键）[R9.5] ──────────────────────────────────────
useKeyboardNav({
  containerRef: containerRef as any,
  rowCount: () => props.modelValue.length,
  colCount: () => visibleColumns.value.length,
  getSelection: () => {
    const cells = cellSelection.selectedCells.value
    if (!cells.length) return null
    const offset = (props.showSelection && props.editable && editMode.isEditing.value) ? 1 : 0
    return [cells[0].row, cells[0].col - offset]
  },
  selectCell: (row: number, col: number) => {
    const offset = (props.showSelection && props.editable && editMode.isEditing.value) ? 1 : 0
    const colDef = visibleColumns.value[col]
    const val = colDef ? props.modelValue[row]?.[colDef.prop] : null
    cellSelection.selectCell(row, col + offset, val, false, false)
  },
  clearSelection: () => cellSelection.clearSelection(),
  startEdit: (row: number, col: number) => {
    if (lazyEditState && editMode.isEditing.value) {
      lazyEditState.startEdit(row, col)
    }
  },
  stopEdit: () => {
    if (lazyEditState) lazyEditState.stopEdit()
  },
})

// ── 单元格样式 ────────────────────────────────────────────────────────────────
function combinedCellClassName(params: { rowIndex: number; columnIndex: number }) {
  const selClass = cellSelection.cellClassName(params)
  const extra = props.cellClassName?.(params) || ''
  return [selClass, extra].filter(Boolean).join(' ')
}

// ── 单元格点击 ────────────────────────────────────────────────────────────────
function onCellClick(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  cellSelection.closeContextMenu()
  if (editMode.isEditing.value) return
  const col = visibleColumns.value.find(c => c.label === column.label)
  if (!col) return
  const rowIdx = props.modelValue.indexOf(row)
  if (rowIdx < 0) return
  cellSelection.selectCell(rowIdx, getColIdx(col.prop), row[col.prop], event.ctrlKey || event.metaKey, event.shiftKey)
  emit('cell-click', row, col, rowIdx)
}

// ── 右键菜单 ──────────────────────────────────────────────────────────────────
function onCellContextMenu(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  if (editMode.isEditing.value) return
  const col = visibleColumns.value.find(c => c.label === column.label)
  if (!col) return
  const rowIdx = props.modelValue.indexOf(row)
  if (rowIdx < 0) return
  const colIdx = getColIdx(col.prop)
  if (!cellSelection.isCellSelected(rowIdx, colIdx)) cellSelection.selectCell(rowIdx, colIdx, row[col.prop], false)
  contextItemName.value = row[visibleColumns.value[0]?.prop] || `行${rowIdx + 1}`
  contextValue.value = row[col.prop]
  cellSelection.openContextMenu(event, contextItemName.value, row)
}

// ── 多选回调 ──────────────────────────────────────────────────────────────────
function onTableSelectionChange(selection: any[]) { toolbar.onSelectionChange(selection); emit('selection-change', selection) }

// ── 工具栏操作 ────────────────────────────────────────────────────────────────
function handleAddRow() {
  const row = props.defaultRow ? props.defaultRow() : Object.fromEntries(visibleColumns.value.map(c => [c.prop, null]))
  toolbar.addRow(row as any); editMode.markDirty(); emit('update:modelValue', [...props.modelValue])
}
async function handleDeleteRows() {
  if (await toolbar.deleteSelectedRows()) { editMode.markDirty(); emit('update:modelValue', [...props.modelValue]) }
}
function handleEnterEdit() { editMode.enterEdit(); emit('edit-change', true) }
async function handleExitEdit() { if (await editMode.exitEdit()) emit('edit-change', false) }

// ── 右键菜单操作 ──────────────────────────────────────────────────────────────
function handleCtxCopy() {
  copySelection(cellSelection.selectedCells.value, props.modelValue, visibleColumns.value.map(c => ({ key: c.prop, label: c.label })))
  cellSelection.closeContextMenu()
}
function handleCtxSum() {
  ElMessage.info(`选中区域求和：${displayPrefs.fmt(cellSelection.sumSelectedValues())}`)
  cellSelection.closeContextMenu()
}

// ── 格式化 & 编辑组件 ────────────────────────────────────────────────────────
/** 判断单元格是否锁定 [R10.3] */
function isCellLocked(col: GtColumn, row: Record<string, any>, rowIndex: number): boolean {
  if (col.locked === true) return true
  if (typeof col.locked === 'function') return col.locked(row, rowIndex)
  return false
}

/** 编辑完成时校验 [R10.2] */
function onEditBlur(col: GtColumn, row: Record<string, any>, rowIndex: number) {
  if (lazyEditState) lazyEditState.stopEdit()
  // 数值范围校验
  if (col.validator && col.editType === 'number') {
    const val = Number(row[col.prop])
    if (!isNaN(val)) {
      if (col.validator.min !== undefined && val < col.validator.min) {
        ElMessage.warning(col.validator.message || `${col.label} 不能小于 ${col.validator.min}`)
        row[col.prop] = col.validator.min
      }
      if (col.validator.max !== undefined && val > col.validator.max) {
        ElMessage.warning(col.validator.message || `${col.label} 不能大于 ${col.validator.max}`)
        row[col.prop] = col.validator.max
      }
    }
  }
}

function formatCellValue(row: Record<string, any>, col: GtColumn): string {
  if (col.formatter) return col.formatter(row[col.prop], row)
  const val = row[col.prop]; return val == null || val === '' ? '-' : String(val)
}
function getEditComponent(col: GtColumn): string {
  const map: Record<string, string> = { number: 'el-input-number', select: 'el-select', date: 'el-date-picker' }
  return map[col.editType || ''] || 'el-input'
}
function getEditProps(col: GtColumn): Record<string, any> {
  const base: Record<string, any> = { style: 'width:100%' }
  if (col.editType === 'number') { base.precision = 2; base.controls = false }
  if (col.editType === 'select') base.placeholder = '请选择'
  return base
}
function getCellComment(rowIdx: number, colIdx: number): any { return props.getComment?.(rowIdx, colIdx) ?? null }

// ── Watch & Expose ────────────────────────────────────────────────────────────
watch(() => editMode.isDirty.value, (v) => emit('dirty-change', v))

// R10 Spec B / Sprint 3.1.3：兼容 wrapper console.warn
// 60 天观察期后无新增引用即可删除（监控 console.warn 频率）
let _migrationWarnedAt = 0
onMounted(() => {
  // 节流：5 分钟内同一会话最多警告一次
  const now = Date.now()
  if (now - _migrationWarnedAt > 5 * 60 * 1000) {
    _migrationWarnedAt = now
    // 仅 dev 模式警告，避免生产 console 噪声
    if (import.meta.env.DEV) {
      console.warn(
        '[GtEditableTable] 已拆分为 GtTableExtended（列表型）+ GtFormTable（编辑型）。\n'
        + '请按场景迁移：列表展示用 GtTableExtended，行内编辑用 GtFormTable。\n'
        + '本 wrapper 60 天观察期后将删除。详见 docs/COMPONENT_USAGE_GUIDE.md',
      )
    }
  }
})

defineExpose({ editMode, fullscreen, cellSelection, toolbar, lazyEditState, tableRef })
</script>

<style scoped>
.gt-editable-table {
  position: relative;
}

.gt-et-cell-text {
  display: inline-block;
  min-height: 20px;
  line-height: 20px;
}

.gt-et-cell-editable {
  cursor: pointer;
  border-radius: 2px;
  padding: 0 2px;
  width: 100%;
}

.gt-et-cell-editable:hover {
  background: rgba(75, 45, 119, 0.06);
}

.gt-et-cell-locked {
  color: var(--gt-color-text-tertiary);
  cursor: not-allowed;
}

:deep(.gt-et-group-header-row) {
  background: var(--gt-color-primary-bg) !important;
  font-weight: 600;
  cursor: pointer;
}

:deep(.gt-et-group-header-row td) {
  background: var(--gt-color-primary-bg) !important;
}

.gt-et-footer {
  display: flex;
  align-items: center;
  padding: 6px 0;
  gap: 8px;
}

.gt-et-footer-info {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}
</style>
