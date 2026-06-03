<!--
  GtGridSheet.vue — 审定表/明细表只读网格渲染器（致同风格 + 公式标注）

  设计目标（2026-06-02）：
  - 类 Excel 外观：表头粘顶、列对齐、边框、合并单元格
  - 公式单元格标注：根据 formula_hint 显示不同图标 + tooltip
  - 区分单元格类型：待取数(虚线) / 公式自动算(绿虚线) / 用户可填(实线)
  - 紧凑布局：无背景色、无标题行（由 GtWpPreparationHeader 统一处理）
  - 只读展示——真正的编辑/公式执行由 spec custom-workpaper-formula-binding 实施
-->
<template>
  <div
    class="gt-grid-sheet"
    :data-readonly="readonly ? 'true' : 'false'"
  >
    <div v-if="!hasData" class="gt-grid-sheet__empty">
      <el-empty description="此表格底稿模板暂无内容" :image-size="80" />
    </div>
    <div v-else class="gt-grid-sheet__wrapper">
      <div class="gt-grid-sheet__scroll">
        <table class="gt-grid-sheet__table">
          <colgroup>
            <col v-for="c in maxCol" :key="c" :style="colStyle(c)" />
          </colgroup>
          <!-- 表头行（粘顶） -->
          <thead class="gt-grid-sheet__thead">
            <tr v-for="hr in headerRows" :key="hr">
              <template v-for="c in maxCol" :key="c">
                <th
                  v-if="!isCovered(hr, c)"
                  :colspan="spanOf(hr, c).colspan"
                  :rowspan="spanOf(hr, c).rowspan"
                  :class="thClass(hr, c)"
                >
                  {{ cellText(hr, c) }}
                </th>
              </template>
            </tr>
          </thead>
          <!-- 数据行 -->
          <tbody>
            <tr
              v-for="r in dataRows"
              :key="r"
              :class="rowClass(r)"
            >
              <template v-for="c in maxCol" :key="c">
                <td
                  v-if="!isCovered(r, c)"
                  :colspan="spanOf(r, c).colspan"
                  :rowspan="spanOf(r, c).rowspan"
                  :class="tdClass(r, c)"
                  :style="tdStyle(r, c)"
                  :title="formulaTooltip(r, c)"
                >
                  <span v-if="formulaIcon(r, c)" class="gt-grid-sheet__formula-icon">
                    {{ formulaIcon(r, c) }}
                  </span>
                  {{ cellText(r, c) }}
                </td>
              </template>
            </tr>
          </tbody>
        </table>
      </div>
      <!-- 图例 -->
      <div class="gt-grid-sheet__legend">
        <span class="gt-grid-sheet__legend-item gt-grid-sheet__legend-item--tb">
          <span class="gt-grid-sheet__legend-dot"></span>试算表取数
        </span>
        <span class="gt-grid-sheet__legend-item gt-grid-sheet__legend-item--adj">
          <span class="gt-grid-sheet__legend-dot"></span>调整分录
        </span>
        <span class="gt-grid-sheet__legend-item gt-grid-sheet__legend-item--computed">
          <span class="gt-grid-sheet__legend-dot"></span>公式自动计算
        </span>
        <span class="gt-grid-sheet__legend-item gt-grid-sheet__legend-item--input">
          <span class="gt-grid-sheet__legend-dot"></span>手动填写
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface CellStyle {
  bold?: boolean
  align?: string
  font_size?: number
  font_color?: string
  numeric?: boolean
  formula_hint?: string
}
interface GridCell {
  v: string | number
  r: number
  c: number
  style?: CellStyle
}
interface MergedRange {
  s: { r: number; c: number }
  e: { r: number; c: number }
}
interface GridHtmlData {
  cells?: Record<string, GridCell>
  merged_cells?: MergedRange[]
  col_widths?: Record<string, number>
  max_row?: number
  max_col?: number
  column_meta?: Record<string, string>
  header_rows?: number
}

const props = withDefaults(defineProps<{
  wpId?: string
  sheetName?: string
  schema?: Record<string, any>
  htmlData?: GridHtmlData
  readonly?: boolean
}>(), { readonly: true })

const cells = computed<Record<string, GridCell>>(() => props.htmlData?.cells ?? {})
const merged = computed<MergedRange[]>(() => props.htmlData?.merged_cells ?? [])
const colWidths = computed<Record<string, number>>(() => props.htmlData?.col_widths ?? {})
const maxRow = computed(() => props.htmlData?.max_row ?? 0)
const maxCol = computed(() => props.htmlData?.max_col ?? 0)
const headerRowCount = computed(() => props.htmlData?.header_rows ?? 2)
const hasData = computed(() => Object.keys(cells.value).length > 0 && maxRow.value > 0)

// 表头行范围 & 数据行范围
const headerRows = computed(() => {
  const arr: number[] = []
  for (let i = 1; i <= headerRowCount.value; i++) arr.push(i)
  return arr
})
const dataRows = computed(() => {
  const arr: number[] = []
  for (let i = headerRowCount.value + 1; i <= maxRow.value; i++) arr.push(i)
  return arr
})

// ─── 坐标工具 ───
function colLetter(c: number): string {
  let s = '', n = c
  while (n > 0) { const m = (n - 1) % 26; s = String.fromCharCode(65 + m) + s; n = Math.floor((n - 1) / 26) }
  return s
}
function coord(r: number, c: number): string { return `${colLetter(c)}${r}` }
function cellAt(r: number, c: number): GridCell | undefined { return cells.value[coord(r, c)] }

function cellText(r: number, c: number): string {
  const cell = cellAt(r, c)
  if (!cell) return ''
  const v = cell.v
  const isNumeric = !!cell.style?.numeric
  if (v == null || v === '') return isNumeric ? '-' : ''
  if (isNumeric && typeof v === 'number') {
    if (v === 0) return '-'
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v)
}

// ─── 合并区域 ───
function isCovered(r: number, c: number): boolean {
  for (const m of merged.value) {
    if (r >= m.s.r && r <= m.e.r && c >= m.s.c && c <= m.e.c && !(r === m.s.r && c === m.s.c)) return true
  }
  return false
}
function spanOf(r: number, c: number): { colspan: number; rowspan: number } {
  for (const m of merged.value) {
    if (r === m.s.r && c === m.s.c) return { colspan: m.e.c - m.s.c + 1, rowspan: m.e.r - m.s.r + 1 }
  }
  return { colspan: 1, rowspan: 1 }
}

// ─── 公式标注 ───
const _FORMULA_TOOLTIPS: Record<string, string> = {
  tb_fetch: '=TB() 从试算表取数（导入账套后自动填充）',
  adj_sum: '=∑调整分录（录入调整分录后自动汇总）',
  reclass_sum: '=∑重分类调整（录入后自动汇总）',
  computed_sum: '=未审数 + 账项调整 + 重分类调整',
  computed_diff: '=期末审定数 - 期初审定数',
  computed_rate: '=变动额 ÷ 期初审定数',
  user_input: '手动填写（双击编辑）',
}
const _FORMULA_ICONS: Record<string, string> = {
  tb_fetch: '📊',
  adj_sum: '📝',
  reclass_sum: '📝',
  computed_sum: 'ƒ',
  computed_diff: 'ƒ',
  computed_rate: '%',
  user_input: '✏️',
}

function formulaHint(r: number, c: number): string | undefined {
  return cellAt(r, c)?.style?.formula_hint
}
function formulaTooltip(r: number, c: number): string {
  const hint = formulaHint(r, c)
  return hint ? _FORMULA_TOOLTIPS[hint] || '' : ''
}
function formulaIcon(r: number, c: number): string {
  const hint = formulaHint(r, c)
  // 只在空值单元格显示图标（有值时不遮挡）
  if (!hint) return ''
  const cell = cellAt(r, c)
  const v = cell?.v
  if (v != null && v !== '' && v !== 0) return ''
  return _FORMULA_ICONS[hint] || ''
}

// ─── 样式类 ───
function thClass(_r: number, _c: number): string {
  return 'gt-grid-sheet__th'
}

function rowClass(r: number): string {
  const cell = cellAt(r, 1)
  const v = String(cell?.v || '')
  if (/^[一二三四五六七八九十]、/.test(v)) return 'gt-grid-sheet__row--section'
  if (/小计|合计/.test(v)) return 'gt-grid-sheet__row--total'
  return ''
}

function tdClass(r: number, c: number): string {
  const classes: string[] = ['gt-grid-sheet__td']
  const hint = formulaHint(r, c)
  if (hint === 'tb_fetch') classes.push('gt-grid-sheet__td--tb')
  else if (hint === 'adj_sum' || hint === 'reclass_sum') classes.push('gt-grid-sheet__td--adj')
  else if (hint?.startsWith('computed')) classes.push('gt-grid-sheet__td--computed')
  else if (hint === 'user_input') classes.push('gt-grid-sheet__td--input')
  if (c === 1) classes.push('gt-grid-sheet__td--label')
  return classes.join(' ')
}

function tdStyle(r: number, c: number): Record<string, string> {
  const cell = cellAt(r, c)
  const st = cell?.style
  const out: Record<string, string> = {}
  if (st?.bold) out.fontWeight = '700'
  if (st?.font_color) out.color = st.font_color
  if (st?.align && ['left', 'right', 'center', 'justify'].includes(st.align)) out.textAlign = st.align
  else if (st?.numeric && c > 1) out.textAlign = 'right'
  if (st?.numeric) out.fontVariantNumeric = 'tabular-nums'
  return out
}

function colStyle(c: number): Record<string, string> {
  const w = colWidths.value[colLetter(c)]
  if (c === 1) return { width: '140px', minWidth: '140px' }
  if (w) return { width: `${Math.round(w * 7)}px`, minWidth: '72px' }
  return { minWidth: '72px' }
}
</script>

<style scoped>
.gt-grid-sheet {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.gt-grid-sheet__empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.gt-grid-sheet__wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 12px 16px;
  gap: 8px;
}
.gt-grid-sheet__scroll {
  flex: 1;
  overflow: auto;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.gt-grid-sheet__table {
  border-collapse: collapse;
  font-size: 12px;
  background: #fff;
  table-layout: fixed;
  width: 100%;
}

/* ─── 表头 ─── */
.gt-grid-sheet__thead {
  position: sticky;
  top: 0;
  z-index: 2;
}
.gt-grid-sheet__th {
  background: #f7f5fa;
  border: 1px solid #d4d0dc;
  padding: 6px 8px;
  font-weight: 600;
  font-size: 11px;
  color: #4b2d77;
  text-align: center;
  white-space: pre-wrap;
  vertical-align: middle;
}

/* ─── 数据单元格 ─── */
.gt-grid-sheet__td {
  border: 1px solid #e8e8e8;
  padding: 5px 8px;
  vertical-align: middle;
  white-space: pre-wrap;
  word-break: break-word;
  color: #303133;
  line-height: 1.4;
  position: relative;
  transition: background 0.1s;
}
.gt-grid-sheet__td--label {
  font-weight: 500;
  color: #1f2329;
  background: #fafafa;
  border-right: 2px solid #d4d0dc;
}

/* 公式类型视觉标记 */
.gt-grid-sheet__td--tb {
  border: 1px dashed #7c4dff;
  background: #faf8ff;
}
.gt-grid-sheet__td--adj {
  border: 1px dashed #ff8f00;
  background: #fffcf5;
}
.gt-grid-sheet__td--computed {
  border: 1px dashed #00c853;
  background: #f5fff8;
}
.gt-grid-sheet__td--input {
  border: 1px solid #bdbdbd;
  background: #fff;
  cursor: text;
}
.gt-grid-sheet__td--input:hover {
  background: #f5f5f5;
  border-color: #7c4dff;
}

/* 公式图标 */
.gt-grid-sheet__formula-icon {
  display: inline-block;
  font-size: 10px;
  opacity: 0.6;
  margin-right: 2px;
  vertical-align: middle;
}

/* ─── 行级样式 ─── */
.gt-grid-sheet__row--section td {
  font-weight: 700;
  color: #4b2d77;
  border-bottom: 2px solid #d4d0dc;
}
.gt-grid-sheet__row--section .gt-grid-sheet__td--label {
  background: #f4f0fa;
}
.gt-grid-sheet__row--total td {
  font-weight: 700;
  border-top: 1px solid #bbb;
  border-bottom: 2px solid #333;
}

/* 行 hover */
.gt-grid-sheet__table tbody tr:hover td {
  background: #f0ecf7;
}
.gt-grid-sheet__table tbody tr:hover .gt-grid-sheet__td--label {
  background: #ede8f5;
}

/* ─── 图例 ─── */
.gt-grid-sheet__legend {
  display: flex;
  gap: 16px;
  padding: 6px 4px;
  font-size: 11px;
  color: #666;
  flex-wrap: wrap;
}
.gt-grid-sheet__legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.gt-grid-sheet__legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  display: inline-block;
}
.gt-grid-sheet__legend-item--tb .gt-grid-sheet__legend-dot {
  background: #faf8ff;
  border: 1px dashed #7c4dff;
}
.gt-grid-sheet__legend-item--adj .gt-grid-sheet__legend-dot {
  background: #fffcf5;
  border: 1px dashed #ff8f00;
}
.gt-grid-sheet__legend-item--computed .gt-grid-sheet__legend-dot {
  background: #f5fff8;
  border: 1px dashed #00c853;
}
.gt-grid-sheet__legend-item--input .gt-grid-sheet__legend-dot {
  background: #fff;
  border: 1px solid #bdbdbd;
}
</style>
