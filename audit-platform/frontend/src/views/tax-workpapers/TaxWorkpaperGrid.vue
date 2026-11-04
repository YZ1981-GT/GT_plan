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
          <span v-if="editing && cell.ref && editing === cell.ref" class="tw-grid__editor">
            <input
              ref="inputRef"
              v-model="draft"
              class="tw-grid__input"
              :aria-label="`填写 ${cell.ref}`"
              @keydown.enter.prevent="commit"
              @keydown.esc.prevent="cancel"
              @blur="commit"
            />
            <!-- mousedown.prevent：不让输入框先失焦提交 -->
            <button
              v-if="isManual(cell)"
              type="button"
              class="tw-grid__restore"
              title="去掉手工值，恢复为取数 / 公式 / 样表原值"
              @mousedown.prevent
              @click.stop="restore(cell)"
            >恢复自动值</button>
          </span>
          <template v-else>{{ display(cell) }}</template>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<script setup lang="ts">
/**
 * 税审底稿单段表格：按单元格矩阵渲染；有 ref 的格子显示后端值，可点开填写（spec citar-table-manual-edit R1）：
 * - e 填写格 / 取数格、f 公式格、c 样表预置数字都可改；手工值盖过取数、公式与预置值；
 * - 改过的格（已保存或草稿）编辑时可「恢复自动值」，经 restore 事件交回，保存时不再提交该格；
 * - `manualEdit` 为 false（账号未开通「允许修改」，spec citar-manual-edit-permission）：只有手填格与「需人工填写」的取数格可点。
 * 本组件不发请求：值、来源说明、草稿都由父组件传入，改动经 edit / restore 事件交回。
 */
import { nextTick, ref } from 'vue'
import type { TaxWorkpaperCell } from './taxWorkpaperSheets'
import { editTextOf, formatTaxValue, parseTaxInput, type TaxCellMeta, type TaxValue } from './taxWorkpaperApi'

const props = withDefaults(defineProps<{
  rows: TaxWorkpaperCell[][]
  values: Record<string, TaxValue>
  cells: Record<string, TaxCellMeta>
  /** 未保存的修改：{ref: 值} */
  drafts: Record<string, number | string | null>
  /** 已点「恢复自动值」、尚未保存的格 */
  restored?: ReadonlySet<string>
  readonly: boolean
  /** 账号「允许修改」：false 时只能填手填格与「需人工填写」的取数格（与后端 is_auto_cell 同口径）。
   *  🔴 布尔 prop 不传会被 Vue 转成 false ⇒ 必须给默认值 true，否则不传的调用方全变成只读 */
  manualEdit?: boolean
}>(), { manualEdit: true })

const emit = defineEmits<{
  (e: 'edit', ref: string, value: number | string | null): void
  (e: 'restore', ref: string): void
}>()

const editing = ref<string | null>(null)
const draft = ref('')
/** 打开编辑框时的文字：没改动不记草稿 */
const initialText = ref('')
const inputRef = ref<HTMLInputElement[] | null>(null)

function isRestored(cell: TaxWorkpaperCell): boolean {
  return Boolean(cell.ref && props.restored?.has(cell.ref))
}

function currentValue(cell: TaxWorkpaperCell): TaxValue | undefined {
  if (!cell.ref) return undefined
  if (cell.ref in props.drafts) {
    const v = props.drafts[cell.ref]
    if (v === null) return null
    return typeof v === 'number' ? { n: String(v) } : { s: v }
  }
  if (isRestored(cell)) {
    // 恢复后、保存前：显示原自动值（取数 / 公式值，预置数字回到样表原文）
    const auto = props.cells[cell.ref]?.auto
    if (auto !== undefined) return auto
    return cell.role === 'c' ? undefined : null
  }
  return props.values[cell.ref]
}

/** 有手工值（已保存且未恢复，或有草稿） */
function isManual(cell: TaxWorkpaperCell): boolean {
  if (!cell.ref) return false
  if (cell.ref in props.drafts) return true
  return props.cells[cell.ref]?.origin === 'input' && !isRestored(cell)
}

/** 自动生成的格：公式格、样表预置数字、按规则自动取数的格（「需人工填写」除外） */
function isAutoCell(cell: TaxWorkpaperCell): boolean {
  if (cell.role === 'f' || cell.role === 'c') return true
  const meta = cell.ref ? props.cells[cell.ref] : undefined
  return Boolean(meta?.status && meta.status !== 'manual')
}

/** 本格可否点开填写：账号未开通「允许修改」时自动生成的格只读 */
function canEdit(cell: TaxWorkpaperCell): boolean {
  if (props.readonly || !cell.role || !cell.ref) return false
  return props.manualEdit !== false || !isAutoCell(cell)
}

function display(cell: TaxWorkpaperCell): string {
  if (!cell.ref) return cell.text ?? ''
  const v = currentValue(cell)
  return v === undefined ? (cell.text ?? '') : formatTaxValue(v, cell.fmt)
}

function cellClass(cell: TaxWorkpaperCell) {
  const meta = cell.ref ? props.cells[cell.ref] : undefined
  const v = currentValue(cell)
  const isEditing = Boolean(cell.ref) && editing.value === cell.ref
  const manual = isManual(cell)
  return [
    !isEditing && display(cell).trim() === '' ? 'tw-cell--blank' : '',
    cell.kind ? `tw-cell--${cell.kind}` : '',
    cell.ref && cell.fmt ? 'tw-cell--number' : '',
    cell.role === 'f' && !manual ? 'tw-cell--formula' : '',
    cell.ref && canEdit(cell) ? 'tw-cell--editable' : '',
    meta?.origin === 'rule' && !manual ? `tw-cell--rule-${meta.status ?? 'auto'}` : '',
    manual ? 'tw-cell--manual' : '',
    meta?.issue && meta.origin === 'rule' && !manual ? 'tw-cell--issue' : '',
    v && 'e' in v ? 'tw-cell--error' : '',
  ].filter(Boolean)
}

const STATUS_TEXT: Record<string, string> = { auto: '智能取数（按取数规则）', confirm: '智能取数（按取数规则），待确认', manual: '需人工填写' }
const AUTO_LABEL: Record<string, string> = { f: '原公式值', c: '样表原值', e: '原取数值' }

function tooltip(cell: TaxWorkpaperCell): string | undefined {
  if (!cell.ref) return undefined
  const meta = props.cells[cell.ref]
  const lines: string[] = []
  if (isRestored(cell)) lines.push('已恢复自动值，保存后生效')
  else if (isManual(cell)) {
    const auto = meta?.auto ?? (cell.role === 'c' && cell.text ? { s: cell.text } : undefined)
    const label = AUTO_LABEL[cell.role ?? 'e'] ?? '原值'
    lines.push(auto !== undefined ? `已手工修改，${label}：${formatTaxValue(auto, cell.fmt) || '空'}` : '已手工修改')
  } else if (cell.role === 'f') lines.push('公式计算，可手工修改（改后不再随公式更新）')
  else if (cell.role === 'c') lines.push('样表预置值，可修改')
  if (props.manualEdit === false && isAutoCell(cell)) lines.push('账号未开通「允许修改」，此格只读')
  if (meta?.status) lines.push(STATUS_TEXT[meta.status] ?? '')
  if (meta?.issue) lines.push(`说明：${meta.issue}`)
  if (meta?.rule) lines.push(`取数规则：${meta.rule}`)
  return lines.length ? lines.join('\n') : undefined
}

/** 编辑框初值：预置数字没有接口值，取样表原文 */
function editText(cell: TaxWorkpaperCell): string {
  const v = currentValue(cell)
  if (v === undefined && cell.role === 'c') return (cell.text ?? '').replace(/,/g, '')
  return editTextOf(v)
}

async function startEdit(cell: TaxWorkpaperCell) {
  if (!canEdit(cell) || editing.value === cell.ref) return
  editing.value = cell.ref ?? null
  draft.value = editText(cell)
  initialText.value = draft.value
  await nextTick()
  inputRef.value?.[0]?.focus()
  inputRef.value?.[0]?.select()
}

function commit() {
  const refName = editing.value
  if (!refName) return
  editing.value = null
  // 没改动不记草稿（避免点开即算修改）
  if (draft.value.trim() === initialText.value.trim()) return
  emit('edit', refName, parseTaxInput(draft.value))
}

function restore(cell: TaxWorkpaperCell) {
  if (!cell.ref) return
  editing.value = null
  emit('restore', cell.ref)
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

/*
 * 空格子照样占一行字高：没有字的格子只剩内边距，整行全空时压成一条细线，与有字的行不一样高。
 * 放一个零宽空格撑出行框（生成内容不进复制、不改 textContent），空格子与有字格子同高。
 */
.tw-grid .tw-cell--blank::before {
  content: "\200b";
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

.tw-grid__editor {
  display: flex;
  align-items: center;
  gap: 4px;
}

.tw-grid__restore {
  flex: 0 0 auto;
  padding: 1px 6px;
  border: 1px solid var(--tw-line-accent);
  background: var(--tw-surface);
  font: inherit;
  font-size: var(--gt-font-size-xs);
  color: var(--tw-accent-deep);
  cursor: pointer;
  white-space: nowrap;
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
