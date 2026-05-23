<!--
  SheetCellRangePicker — Sheet 单元格区域选择器弹窗

  用户在左树点击具体 sheet 叶子时弹出，提供网格界面供用户框选要查询的单元格区域。

  Phase 1（当前）：空白 grid（60 行 × 27 列 A~AA）+ 鼠标拖选记录起止 cell + 确认 range
  Phase 2（后续）：接入真实 Univer 模板 cellData，展示底稿真实内容

  Emits:
    confirm: { wp_code, sheet_name, range }  → 父组件用 range 作为查询过滤条件
    update:visible: 关闭弹窗
-->
<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="80%"
    top="5vh"
    append-to-body
    destroy-on-close
    class="gt-sheet-picker-dialog"
  >
    <div class="gt-sheet-picker-toolbar">
      <span class="gt-sheet-picker-tab">📄 {{ sheetName || wpCode }}</span>
      <span style="flex:1" />
      <span v-if="selectedRange" class="gt-sheet-picker-range">
        已选区域：<strong>{{ selectedRange }}</strong>
      </span>
      <el-button size="small" @click="resetSelection" :disabled="!selectedRange">↺ 清除</el-button>
    </div>

    <div class="gt-sheet-picker-hint">
      💡 鼠标拖动框选要查询的单元格区域（Phase 1：空白网格，后续接入真实模板内容）
    </div>

    <div class="gt-sheet-picker-grid-wrap" @mouseup="onMouseUp" @mouseleave="onMouseUp">
      <table class="gt-sheet-picker-grid" @selectstart.prevent>
        <thead>
          <tr>
            <th class="gt-corner"></th>
            <th v-for="(col, ci) in COLS" :key="ci" class="gt-col-header">{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in ROWS" :key="row">
            <th class="gt-row-header">{{ row }}</th>
            <td
              v-for="(col, ci) in COLS"
              :key="ci"
              :class="['gt-cell', { 'gt-cell-selected': isCellSelected(row, ci) }]"
              @mousedown="onMouseDown(row, ci)"
              @mouseenter="onMouseEnter(row, ci)"
            ></td>
          </tr>
        </tbody>
      </table>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="!selectedRange" @click="onConfirm">
        ✓ 确认选区{{ selectedRange ? `（${selectedRange}）` : '' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

const props = defineProps<{
  modelValue: boolean
  wpCode: string
  sheetName?: string
}>()
const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  confirm: [payload: { wp_code: string; sheet_name?: string; range: string }]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const dialogTitle = computed(() => `📐 选择单元格区域 — ${props.wpCode}${props.sheetName ? ' / ' + props.sheetName : ''}`)

// 网格规模：A~AA 27 列 × 60 行（覆盖大多数底稿首屏）
const ROW_COUNT = 60
const COL_COUNT = 27
const ROWS = Array.from({ length: ROW_COUNT }, (_, i) => i + 1)
const COLS = Array.from({ length: COL_COUNT }, (_, i) => _colLabel(i))

function _colLabel(i: number): string {
  // A=0, B=1, ..., Z=25, AA=26
  if (i < 26) return String.fromCharCode(65 + i)
  return 'A' + String.fromCharCode(65 + (i - 26))
}

// 拖选状态
const dragging = ref(false)
const startCell = ref<{ row: number; col: number } | null>(null)
const endCell = ref<{ row: number; col: number } | null>(null)

const selectedRange = computed(() => {
  if (!startCell.value || !endCell.value) return ''
  const r1 = Math.min(startCell.value.row, endCell.value.row)
  const r2 = Math.max(startCell.value.row, endCell.value.row)
  const c1 = Math.min(startCell.value.col, endCell.value.col)
  const c2 = Math.max(startCell.value.col, endCell.value.col)
  const a1 = `${COLS[c1]}${r1}`
  const a2 = `${COLS[c2]}${r2}`
  return r1 === r2 && c1 === c2 ? a1 : `${a1}:${a2}`
})

function isCellSelected(row: number, col: number): boolean {
  if (!startCell.value || !endCell.value) return false
  const r1 = Math.min(startCell.value.row, endCell.value.row)
  const r2 = Math.max(startCell.value.row, endCell.value.row)
  const c1 = Math.min(startCell.value.col, endCell.value.col)
  const c2 = Math.max(startCell.value.col, endCell.value.col)
  return row >= r1 && row <= r2 && col >= c1 && col <= c2
}

function onMouseDown(row: number, col: number) {
  dragging.value = true
  startCell.value = { row, col }
  endCell.value = { row, col }
}

function onMouseEnter(row: number, col: number) {
  if (dragging.value) endCell.value = { row, col }
}

function onMouseUp() {
  dragging.value = false
}

function resetSelection() {
  startCell.value = null
  endCell.value = null
}

function onConfirm() {
  if (!selectedRange.value) return
  emit('confirm', {
    wp_code: props.wpCode,
    sheet_name: props.sheetName,
    range: selectedRange.value,
  })
  visible.value = false
}

// 弹窗关闭时清空选区，下次打开是干净状态
watch(visible, (v) => {
  if (!v) resetSelection()
})
</script>

<style scoped>
.gt-sheet-picker-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--gt-color-border-purple);
  margin-bottom: 8px;
}
.gt-sheet-picker-tab {
  font-size: var(--gt-font-size-md);
  font-weight: 600;
  color: var(--gt-color-primary);
  background: var(--gt-color-bg-purple-light, #f5f0ff);
  padding: 4px 12px;
  border-radius: 4px 4px 0 0;
  border-bottom: 2px solid var(--gt-color-primary);
}
.gt-sheet-picker-range {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-regular);
}
.gt-sheet-picker-range strong {
  color: var(--gt-color-primary);
  font-family: 'Consolas', 'Monaco', monospace;
}
.gt-sheet-picker-hint {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  margin-bottom: 6px;
}
.gt-sheet-picker-grid-wrap {
  max-height: calc(100vh - 280px);
  overflow: auto;
  border: 1px solid var(--gt-color-border);
  user-select: none;
}
.gt-sheet-picker-grid {
  border-collapse: collapse;
  font-size: 12px;
  table-layout: fixed;
}
.gt-sheet-picker-grid th,
.gt-sheet-picker-grid td {
  border: 1px solid #e0e0e0;
  width: 80px;
  height: 22px;
  padding: 0;
  text-align: center;
  background: #fff;
}
.gt-corner {
  width: 40px !important;
  background: #f5f5f5 !important;
  position: sticky;
  left: 0;
  top: 0;
  z-index: 3;
}
.gt-col-header {
  background: #f5f5f5 !important;
  position: sticky;
  top: 0;
  z-index: 2;
  font-weight: 600;
  color: var(--gt-color-text-secondary);
}
.gt-row-header {
  width: 40px !important;
  background: #f5f5f5 !important;
  position: sticky;
  left: 0;
  z-index: 1;
  font-weight: 600;
  color: var(--gt-color-text-secondary);
}
.gt-cell {
  cursor: cell;
}
.gt-cell:hover {
  background: rgba(124, 58, 237, 0.06) !important;
}
.gt-cell-selected {
  background: rgba(124, 58, 237, 0.18) !important;
  border-color: var(--gt-color-primary) !important;
}
</style>
