<!--
  GtCustomGridSheet.vue — 自定义底稿**可编辑**网格（componentType=custom）

  ## 为什么新建而不改 GtGridSheet

  `GtGridSheet.vue` 是 40+ 处只读消费方的共享件，且其
  `withDefaults(..., { readonly: true })` 的 `readonly` prop 只输出到 `data-readonly`
  属性、不参与任何渲染分支（全文 `emit(` 与 `defineEmits` 计数均为 0）
  ⇒ 传 `readonly=false` 也不可编辑。改它半径过大（视觉规则被全平台依赖）。

  本组件复用其视觉规则（合并格 / 粘顶表头 / 冻结首列 / 分组带配色 / 空值淡化 /
  斑马纹 / 公式标注），追加：单击选中、双击编辑、脏格防抖批量提交。

  ## 坐标恒等

  自定义底稿的投影坐标 ≡ xlsx 坐标（`custom_workpaper_projection` 的恒等投影，
  不剥表头 / 不重编行号 / 不裁空列）⇒ 本组件产出的 `B6` 可直接作为
  `PUT /custom-cells` 的 body 键写回 xlsx。
  🔴 这是为什么自定义底稿不能走 `wp_grid_extract.extract_grid` ——
  它 `row_offset = data_start_row - 1` 重编行号（实测 xlsx `B6` → 投影 `B2`），
  按投影坐标写回会写进表头区覆盖别的格。

  ## header_rows 恒 0

  恒等投影不剥表头 ⇒ `header_rows = 0` ⇒ 全部行都是可编辑数据行。
  表头本身就是用户可改的内容（自定义底稿无固定模板）。

  spec: .kiro/specs/custom-workpaper-dual-mode-formula-and-batch/ Wave 2 Task 7
-->
<template>
  <div class="gt-cgs" :data-readonly="readonly ? 'true' : 'false'">
    <!-- 空态：区分「文件异常」与「确实是空底稿」（R1.4） -->
    <div v-if="!hasData" class="gt-cgs__empty">
      <el-empty
        :description="emptyDescription"
        :image-size="80"
      >
        <el-alert
          v-if="emptyReason === 'source-unavailable'"
          type="warning"
          :closable="false"
          show-icon
          title="底稿文件异常"
          description="未能读取底稿的 Excel 文件，录入的内容可能无法保存。请重新生成或上传底稿文件。"
        />
      </el-empty>
    </div>

    <div v-else class="gt-cgs__wrapper">
      <!-- 脏格状态条：保存中 / 失败保留 -->
      <div v-if="dirtyCount > 0 || saving || saveError" class="gt-cgs__statusbar">
        <el-tag v-if="saving" type="info" size="small" effect="plain">保存中…</el-tag>
        <el-tag v-else-if="saveError" type="danger" size="small" effect="plain">
          保存失败，已保留 {{ dirtyCount }} 处未保存修改
        </el-tag>
        <el-tag v-else type="warning" size="small" effect="plain">
          {{ dirtyCount }} 处待保存
        </el-tag>
        <el-button
          v-if="saveError"
          size="small"
          type="primary"
          text
          @click="flushNow"
        >
          重试保存
        </el-button>
      </div>

      <div class="gt-cgs__scroll">
        <table class="gt-cgs__table">
          <colgroup>
            <col v-for="c in maxCol" :key="c" :style="colStyle(c)" />
          </colgroup>
          <tbody>
            <tr v-for="r in allRows" :key="r" :class="rowClass(r)">
              <template v-for="c in maxCol" :key="c">
                <td
                  v-if="!isCovered(r, c)"
                  :colspan="spanOf(r, c).colspan"
                  :rowspan="spanOf(r, c).rowspan"
                  :class="tdClass(r, c)"
                  :style="tdStyle(r, c)"
                  :title="cellTooltip(r, c)"
                  :data-cell="coord(r, c)"
                  @click="onCellClick(r, c)"
                  @dblclick="onCellDblClick(r, c)"
                >
                  <!-- 编辑态 -->
                  <el-input
                    v-if="isEditing(r, c)"
                    ref="editorRef"
                    :model-value="editingText"
                    size="small"
                    class="gt-cgs__editor"
                    @input="onEditorInput"
                    @blur="commitEdit"
                    @keyup.enter="commitEdit"
                    @keyup.esc="cancelEdit"
                  />
                  <!-- 只读态 -->
                  <template v-else>
                    <span v-if="isFormulaCell(r, c)" class="gt-cgs__fx">ƒ</span>
                    {{ cellText(r, c) }}
                  </template>
                </td>
              </template>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="gt-cgs__legend">
        <span class="gt-cgs__legend-item gt-cgs__legend-item--formula">
          <span class="gt-cgs__legend-dot"></span>公式计算（不可手工改）
        </span>
        <span class="gt-cgs__legend-item gt-cgs__legend-item--dirty">
          <span class="gt-cgs__legend-dot"></span>待保存
        </span>
        <span v-if="!readonly" class="gt-cgs__legend-hint">双击单元格编辑，Enter 确认 / Esc 取消</span>
        <span v-else class="gt-cgs__legend-hint">当前为只读模式</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
// 🔴 `DisplayPrefs_Key` 的真源是 `composables/displayPrefsKey.ts`，**不是** stores/displayPrefs。
// 从后者连带 import 会让整页崩成「页面渲染出错：does not provide an export named
// 'DisplayPrefs_Key'」，而 get_diagnostics / vitest / Vite transform 四层全绿。
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { inject } from 'vue'
import {
  buildCellPatch,
  classifyEmptyGrid,
  gridHasContent,
  normalizeCellRef,
} from './customWpCellEdit'

interface CellStyle {
  bold?: boolean
  align?: string
  font_size?: number
  font_color?: string
  numeric?: boolean
  formula_hint?: string
}
interface GridCell {
  v: string | number | null
  r: number
  c: number
  style?: CellStyle
  formula?: string
}
interface MergedRange {
  s: { r: number; c: number }
  e: { r: number; c: number }
}
export interface CustomGridHtmlData {
  cells?: Record<string, GridCell>
  merged_cells?: MergedRange[]
  col_widths?: Record<string, number>
  max_row?: number
  max_col?: number
  header_rows?: number
  source_unavailable?: boolean
}

const props = withDefaults(
  defineProps<{
    wpId: string
    sheetName: string
    htmlData?: CustomGridHtmlData
    /** 只读态（OO 模式下 / 底稿已归档 / 无编辑权限） */
    readonly?: boolean
    /** 公式目标格集合（存在 wp_formula 记录的格），这些格不可手工编辑 */
    formulaCells?: Record<string, string> | string[]
    /** 从公式清单点击定位时需高亮的目标格（R6.3） */
    highlightCell?: string
    /** 防抖毫秒，测试可传 0 */
    debounceMs?: number
  }>(),
  { readonly: false, debounceMs: 800 },
)

const emit = defineEmits<{
  /** 单击选中格（供 FormulaEditDialog 作目标格） */
  'select-cell': [cellRef: string]
  /** 保存成功后下发新投影，宿主可据此替换本地 htmlData */
  saved: [grid: CustomGridHtmlData]
}>()

// 🔴 fmtAmount 是 store 成员不是模块级导出；必须 setup 顶层取
// （写成 `import { fmtAmount } from '@/stores/displayPrefs'` 会整页崩）
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// ─── 本地叠加层：脏格覆盖投影值 ───
const dirty = ref<Map<string, unknown>>(new Map())
const saving = ref(false)
const saveError = ref(false)
const dirtyCount = computed(() => dirty.value.size)

const baseCells = computed<Record<string, GridCell>>(() => props.htmlData?.cells ?? {})
const merged = computed<MergedRange[]>(() => props.htmlData?.merged_cells ?? [])
const colWidths = computed<Record<string, number>>(() => props.htmlData?.col_widths ?? {})
const maxRow = computed(() => Number(props.htmlData?.max_row ?? 0))
const maxCol = computed(() => Number(props.htmlData?.max_col ?? 0))

// 🔴 与后端 grid_has_content / GtGridSheet.hasData 三侧同口径
const hasData = computed(() => gridHasContent(props.htmlData))
const emptyReason = computed(() => classifyEmptyGrid(props.htmlData))
const emptyDescription = computed(() =>
  emptyReason.value === 'source-unavailable'
    ? '底稿文件读取失败'
    : '底稿暂无内容，可切换到「在线编辑」录入或先生成底稿',
)

// 恒等投影不剥表头 ⇒ 全部行皆可编辑
const allRows = computed(() => {
  const arr: number[] = []
  for (let i = 1; i <= maxRow.value; i++) arr.push(i)
  return arr
})

// ─── 公式格集合（数据驱动，不靠 CSS） ───
const formulaCellSet = computed<Set<string>>(() => {
  const out = new Set<string>()
  const fc = props.formulaCells
  if (!fc) return out
  const keys = Array.isArray(fc) ? fc : Object.keys(fc)
  for (const k of keys) {
    const ref = normalizeCellRef(String(k))
    if (ref) out.add(ref)
  }
  return out
})

function isFormulaCell(r: number, c: number): boolean {
  return formulaCellSet.value.has(coord(r, c))
}

function formulaExpr(r: number, c: number): string {
  const fc = props.formulaCells
  if (!fc || Array.isArray(fc)) return ''
  return String(fc[coord(r, c)] ?? '')
}

// ─── 坐标工具 ───
function colLetter(c: number): string {
  let s = ''
  let n = c
  while (n > 0) {
    const m = (n - 1) % 26
    s = String.fromCharCode(65 + m) + s
    n = Math.floor((n - 1) / 26)
  }
  return s
}
function coord(r: number, c: number): string {
  return `${colLetter(c)}${r}`
}
function cellAt(r: number, c: number): GridCell | undefined {
  return baseCells.value[coord(r, c)]
}

function rawValue(r: number, c: number): unknown {
  const ref = coord(r, c)
  if (dirty.value.has(ref)) return dirty.value.get(ref)
  return cellAt(r, c)?.v ?? ''
}

function cellText(r: number, c: number): string {
  const v = rawValue(r, c)
  const isNumeric = !!cellAt(r, c)?.style?.numeric
  if (v == null || v === '') return isNumeric ? '-' : ''
  if (isNumeric && typeof v === 'number') {
    if (v === 0) return '-'
    return displayPrefs.fmtAmount(v)
  }
  return String(v)
}

function cellTooltip(r: number, c: number): string {
  if (isFormulaCell(r, c)) {
    const expr = formulaExpr(r, c)
    return expr ? `该格由公式计算：${expr}` : '该格由公式计算，不可手工覆盖'
  }
  if (props.readonly) return ''
  return '双击编辑'
}

// ─── 合并区域（恒等坐标，不做行偏移） ───
function isCovered(r: number, c: number): boolean {
  for (const m of merged.value) {
    if (
      r >= m.s.r &&
      r <= m.e.r &&
      c >= m.s.c &&
      c <= m.e.c &&
      !(r === m.s.r && c === m.s.c)
    ) {
      return true
    }
  }
  return false
}
function spanOf(r: number, c: number): { colspan: number; rowspan: number } {
  for (const m of merged.value) {
    if (r === m.s.r && c === m.s.c) {
      return { colspan: m.e.c - m.s.c + 1, rowspan: m.e.r - m.s.r + 1 }
    }
  }
  return { colspan: 1, rowspan: 1 }
}

// ─── 编辑态 ───
const editingRef = ref<string | null>(null)
const editingText = ref('')
const editorRef = ref<unknown>(null)

function isEditing(r: number, c: number): boolean {
  return editingRef.value === coord(r, c)
}

/** 该格是否允许进入编辑态（数据驱动三闸） */
function canEdit(r: number, c: number): boolean {
  if (props.readonly) return false
  if (isFormulaCell(r, c)) return false
  if (isCovered(r, c)) return false
  return true
}

function onCellClick(r: number, c: number) {
  emit('select-cell', coord(r, c))
}

async function onCellDblClick(r: number, c: number) {
  if (!canEdit(r, c)) {
    if (isFormulaCell(r, c)) {
      ElMessage.info('该单元格由公式计算，如需手工填写请先删除该公式')
    }
    return
  }
  const ref = coord(r, c)
  const v = rawValue(r, c)
  editingText.value = v == null ? '' : String(v)
  editingRef.value = ref
  await nextTick()
  const el = editorRef.value as { focus?: () => void; select?: () => void } | null
  el?.focus?.()
  el?.select?.()
}

// 🔴 必须绑 @input：只绑 @change 会被 EP 在 nextTick 重置回 modelValue，抹掉用户键入
function onEditorInput(val: string) {
  editingText.value = val
}

function commitEdit() {
  const ref = editingRef.value
  if (!ref) return
  editingRef.value = null
  const original = baseCells.value[ref]?.v ?? ''
  const next = editingText.value
  // 值未变则不产生脏格（避免无意义写盘 + file_version 空转递增）
  if (String(original) === next) {
    dirty.value.delete(ref)
    dirty.value = new Map(dirty.value)
    return
  }
  dirty.value.set(ref, next)
  dirty.value = new Map(dirty.value)
  scheduleFlush()
}

function cancelEdit() {
  editingRef.value = null
  editingText.value = ''
}

// ─── 防抖批量提交 ───
let timer: ReturnType<typeof setTimeout> | null = null

function scheduleFlush() {
  if (timer) clearTimeout(timer)
  const ms = Math.max(0, Number(props.debounceMs ?? 800))
  timer = setTimeout(() => {
    void flushNow()
  }, ms)
}

async function flushNow(): Promise<void> {
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
  if (saving.value) return
  if (dirty.value.size === 0) return

  const { updates, overflow, invalid } = buildCellPatch(dirty.value)
  if (invalid.length) {
    ElMessage.error(`单元格引用非法，未提交：${invalid.slice(0, 3).join('、')}`)
  }
  if (overflow) {
    ElMessage.warning('待保存单元格超过 500 格，请分批保存')
    return
  }
  if (Object.keys(updates).length === 0) return

  saving.value = true
  saveError.value = false
  try {
    const res = (await api.put(`/api/workpapers/${props.wpId}/custom-cells`, {
      sheet_name: props.sheetName,
      updates,
    })) as { grid?: CustomGridHtmlData; updated?: number }
    // 成功：清掉已提交的脏格（保留提交期间新产生的）
    const submitted = new Set(Object.keys(updates))
    const remain = new Map<string, unknown>()
    for (const [k, v] of dirty.value.entries()) {
      const nk = normalizeCellRef(k)
      if (nk && !submitted.has(nk)) remain.set(k, v)
    }
    dirty.value = remain
    if (res?.grid) emit('saved', res.grid)
    ElMessage.success(`已保存 ${res?.updated ?? Object.keys(updates).length} 处修改`)
  } catch (e) {
    // 🔴 保存失败必须可见 + 保留脏格（纯 catch {} 会让数据丢了没人发现）
    saveError.value = true
    const msg = (e as { message?: string })?.message || '未知错误'
    ElMessage.error(`保存失败，修改已保留在本地：${msg}`)
  } finally {
    saving.value = false
  }
}

// 切走前把未保存的推上去（避免关页丢数据）
onBeforeUnmount(() => {
  if (dirty.value.size > 0) void flushNow()
})

// 只读态切入时退出编辑
watch(
  () => props.readonly,
  (ro) => {
    if (ro) cancelEdit()
  },
)

// ─── 样式 ───
function rowClass(r: number): string {
  const v = String(cellAt(r, 1)?.v || '')
  if (/^[一二三四五六七八九十]、/.test(v)) return 'gt-cgs__row--section'
  if (/小\s*计|合\s*计/.test(v)) return 'gt-cgs__row--total'
  return ''
}

function tdClass(r: number, c: number): string {
  const classes = ['gt-cgs__td']
  const ref = coord(r, c)
  if (isFormulaCell(r, c)) classes.push('gt-cgs__td--formula')
  else if (canEdit(r, c)) classes.push('gt-cgs__td--editable')
  if (dirty.value.has(ref)) classes.push('gt-cgs__td--dirty')
  // 公式清单点击定位（R6.3）：归一化后比较，避免 `b5` / `$B$5` 比不上
  if (props.highlightCell && normalizeCellRef(props.highlightCell) === ref) {
    classes.push('gt-cgs__td--highlight')
  }
  if (c === 1) classes.push('gt-cgs__td--label')
  const txt = cellText(r, c)
  if (!txt || txt === '-') classes.push('gt-cgs__td--empty')
  return classes.join(' ')
}

function tdStyle(r: number, c: number): Record<string, string> {
  const st = cellAt(r, c)?.style
  const out: Record<string, string> = {}
  if (st?.bold) out.fontWeight = '700'
  if (st?.font_color) out.color = st.font_color
  if (st?.align && ['left', 'right', 'center', 'justify'].includes(st.align)) {
    out.textAlign = st.align
  } else if (st?.numeric && c > 1) {
    out.textAlign = 'right'
  }
  if (st?.numeric) out.fontVariantNumeric = 'tabular-nums'
  return out
}

function colStyle(c: number): Record<string, string> {
  const w = colWidths.value[colLetter(c)]
  if (c === 1) return { width: '140px', minWidth: '140px' }
  if (w) return { width: `${Math.round(w * 7)}px`, minWidth: '72px' }
  return { minWidth: '72px' }
}

defineExpose({ flushNow, dirtyCount })
</script>

<style scoped>
.gt-cgs {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.gt-cgs__empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.gt-cgs__wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 8px 16px 12px;
  gap: 6px;
}
.gt-cgs__statusbar {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.gt-cgs__scroll {
  flex: 1;
  overflow: auto;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
.gt-cgs__table {
  border-collapse: collapse;
  font-size: var(--wp-font-size, 13px);
  background: #fff;
  table-layout: fixed;
  width: 100%;
  line-height: 1.5;
}
.gt-cgs__td {
  border: 1px solid #e8e8e8;
  padding: 5px 8px;
  vertical-align: middle;
  white-space: pre-wrap;
  word-break: break-word;
  color: #303133;
  line-height: 1.4;
  position: relative;
}
.gt-cgs__td--label {
  font-weight: 500;
  color: #1f2329;
  background: #fafafa;
  border-right: 2px solid #d4d0dc;
  position: sticky;
  left: 0;
  z-index: 1;
}
.gt-cgs__td--empty {
  color: #c5c8ce;
}
.gt-cgs__td--editable {
  cursor: cell;
}
.gt-cgs__td--editable:hover {
  background: #f5f2fa;
  outline: 1px solid #b9a5da;
}
.gt-cgs__td--formula {
  border: 1px dashed #00c853;
  background: #f5fff8;
  cursor: not-allowed;
}
.gt-cgs__td--dirty {
  background: #fffbe6;
  outline: 1px solid #f0c419;
}
/* 公式清单点击定位高亮（R6.3） */
.gt-cgs__td--highlight {
  outline: 2px solid #7c4dff;
  background: #f3edff;
}
.gt-cgs__fx {
  display: inline-block;
  font-size: 10px;
  opacity: 0.6;
  margin-right: 2px;
  vertical-align: middle;
}
.gt-cgs__editor :deep(.el-input__wrapper) {
  padding: 0 4px;
  box-shadow: 0 0 0 1px #7c4dff inset;
}
.gt-cgs__table tbody tr:nth-child(even) > td {
  background: #fbfafc;
}
.gt-cgs__table tbody tr:nth-child(even) > .gt-cgs__td--label {
  background: #f4f2f7;
}
.gt-cgs__table tbody tr:nth-child(even) > .gt-cgs__td--dirty {
  background: #fffbe6;
}
.gt-cgs__row--section td {
  font-weight: 700;
  color: #4b2d77;
  border-bottom: 2px solid #d4d0dc;
}
.gt-cgs__row--total td {
  font-weight: 700;
  border-top: 1px solid #bbb;
  border-bottom: 2px solid #333;
}
.gt-cgs__legend {
  display: flex;
  gap: 16px;
  padding: 4px 2px;
  font-size: 11px;
  color: #666;
  flex-wrap: wrap;
  align-items: center;
}
.gt-cgs__legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.gt-cgs__legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  display: inline-block;
}
.gt-cgs__legend-item--formula .gt-cgs__legend-dot {
  background: #f5fff8;
  border: 1px dashed #00c853;
}
.gt-cgs__legend-item--dirty .gt-cgs__legend-dot {
  background: #fffbe6;
  border: 1px solid #f0c419;
}
.gt-cgs__legend-hint {
  margin-left: auto;
  color: #909399;
}
</style>
