<template>
  <table class="tw-grid">
    <tbody>
      <tr v-for="(row, rowIndex) in rows" :key="rowIndex">
        <td
          v-for="(cell, cellIndex) in row"
          :key="cellIndex"
          :class="cellClass(cell)"
          :colspan="cell.colSpan"
          :rowspan="cell.rowSpan"
          :title="tooltip(cell)"
          @click="startEdit(cell)"
        >
          <input
            v-if="editing && cell.ref && editing === cell.ref"
            ref="inputRef"
            v-model="draft"
            class="tw-grid__input"
            :aria-label="`填写 ${cell.ref}`"
            @keydown.enter.prevent="commit"
            @keydown.esc.prevent="cancel"
            @blur="commit"
          />
          <template v-else>{{ display(cell) }}</template>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<script setup lang="ts">
/**
 * 税审底稿单段表格：按单元格矩阵渲染；有 ref 的格子显示后端值，role=e 的格子可点开填写。
 * 本组件不发请求：值、来源说明、草稿都由父组件传入，改动经 edit 事件交回。
 */
import { nextTick, ref } from 'vue'
import type { TaxWorkpaperCell } from './taxWorkpaperSheets'
import { editTextOf, formatTaxValue, parseTaxInput, type TaxCellMeta, type TaxValue } from './taxWorkpaperApi'

const props = defineProps<{
  rows: TaxWorkpaperCell[][]
  values: Record<string, TaxValue>
  cells: Record<string, TaxCellMeta>
  /** 未保存的修改：{ref: 值} */
  drafts: Record<string, number | string | null>
  readonly: boolean
}>()

const emit = defineEmits<{ (e: 'edit', ref: string, value: number | string | null): void }>()

const editing = ref<string | null>(null)
const draft = ref('')
const inputRef = ref<HTMLInputElement[] | null>(null)

function currentValue(cell: TaxWorkpaperCell): TaxValue | undefined {
  if (!cell.ref) return undefined
  if (cell.ref in props.drafts) {
    const v = props.drafts[cell.ref]
    if (v === null) return null
    return typeof v === 'number' ? { n: String(v) } : { s: v }
  }
  return props.values[cell.ref]
}

function display(cell: TaxWorkpaperCell): string {
  if (!cell.ref) return cell.text ?? ''
  const v = currentValue(cell)
  return v === undefined ? (cell.text ?? '') : formatTaxValue(v, cell.fmt)
}

function cellClass(cell: TaxWorkpaperCell) {
  const meta = cell.ref ? props.cells[cell.ref] : undefined
  const v = currentValue(cell)
  return [
    cell.kind ? `tw-cell--${cell.kind}` : '',
    cell.ref && cell.fmt ? 'tw-cell--number' : '',
    cell.role === 'f' ? 'tw-cell--formula' : '',
    cell.role === 'e' && !props.readonly ? 'tw-cell--editable' : '',
    meta?.origin === 'rule' ? `tw-cell--rule-${meta.status ?? 'auto'}` : '',
    meta?.origin === 'input' || (cell.ref && cell.ref in props.drafts) ? 'tw-cell--manual' : '',
    meta?.issue && meta.origin === 'rule' ? 'tw-cell--issue' : '',
    v && 'e' in v ? 'tw-cell--error' : '',
  ].filter(Boolean)
}

const STATUS_TEXT: Record<string, string> = { auto: '按规则取数', confirm: '按规则取数，待确认', manual: '需人工填写' }

function tooltip(cell: TaxWorkpaperCell): string | undefined {
  if (!cell.ref) return undefined
  const meta = props.cells[cell.ref]
  const lines: string[] = []
  if (cell.role === 'f') lines.push('公式计算，不能直接填写')
  if (meta?.status) lines.push(STATUS_TEXT[meta.status] ?? '')
  if (meta?.origin === 'input' && meta.auto !== undefined) lines.push(`已手工修改，原取数值：${formatTaxValue(meta.auto, cell.fmt) || '空'}`)
  if (meta?.issue) lines.push(`说明：${meta.issue}`)
  if (meta?.rule) lines.push(`取数规则：${meta.rule}`)
  return lines.length ? lines.join('\n') : undefined
}

async function startEdit(cell: TaxWorkpaperCell) {
  if (props.readonly || cell.role !== 'e' || !cell.ref || editing.value === cell.ref) return
  editing.value = cell.ref
  draft.value = editTextOf(currentValue(cell))
  await nextTick()
  inputRef.value?.[0]?.focus()
  inputRef.value?.[0]?.select()
}

function commit() {
  const refName = editing.value
  if (!refName) return
  editing.value = null
  const value = parseTaxInput(draft.value)
  const before = editTextOf(props.values[refName])
  // 没改动不记草稿（避免点开即算修改）
  if (!(refName in props.drafts) && draft.value.trim() === before.trim()) return
  emit('edit', refName, value)
}

function cancel() {
  editing.value = null
}
</script>

<style scoped>
/* 列宽随内容自适应：底稿列宽差异大，固定布局会把长文本挤成一条 */
.tw-grid {
  border-collapse: collapse;
  font-size: var(--gt-font-size-sm);
  table-layout: auto;
}

.tw-grid td {
  padding: 6px 9px;
  border: 1px solid var(--tw-line-strong);
  vertical-align: middle;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--tw-text);
}

.tw-grid .tw-cell--title {
  font-size: var(--gt-font-size-base);
  font-weight: 700;
  text-align: center;
  background: var(--tw-accent-hover);
  color: var(--tw-accent-deep);
}

.tw-grid .tw-cell--header {
  font-weight: 700;
  text-align: center;
  background: var(--tw-subnav-bg);
}

.tw-grid .tw-cell--meta {
  font-size: var(--gt-font-size-xs);
  color: var(--tw-text-muted);
}

.tw-grid .tw-cell--number {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.tw-grid .tw-cell--total {
  font-weight: 700;
  background: var(--tw-accent-soft);
}

.tw-grid .tw-cell--input {
  min-width: 90px;
  background: var(--tw-input-bg);
}

.tw-grid .tw-cell--formula {
  background: var(--tw-formula-bg);
}

.tw-grid .tw-cell--editable {
  min-width: 90px;
  cursor: text;
}

.tw-grid .tw-cell--editable:hover {
  outline: 1px solid var(--tw-accent-light);
  outline-offset: -1px;
}

.tw-grid .tw-cell--rule-auto {
  background: var(--tw-rule-auto-bg);
}

.tw-grid .tw-cell--rule-confirm {
  background: var(--tw-rule-confirm-bg);
}

.tw-grid .tw-cell--rule-manual {
  background: var(--tw-rule-manual-bg);
}

.tw-grid .tw-cell--manual {
  background: var(--tw-manual-bg);
  color: var(--tw-accent-deep);
}

.tw-grid .tw-cell--issue {
  box-shadow: inset 3px 0 0 var(--tw-issue-mark);
}

.tw-grid .tw-cell--error {
  color: var(--tw-mark-absent);
}

.tw-grid__input {
  width: 100%;
  min-width: 80px;
  box-sizing: border-box;
  padding: 2px 4px;
  border: 1px solid var(--tw-accent);
  font: inherit;
  text-align: inherit;
  background: var(--tw-surface);
  color: var(--tw-text);
}
</style>
