<template>
  <details class="rb-amounts" :open="dirty || undefined">
    <summary>
      摘录表金额{{ canManualEdit ? '（可修改）' : '' }}<span v-if="manualCount" class="rb-amounts__badge">{{ manualCount }} 项手工修改</span>
    </summary>
    <div v-if="canManualEdit" class="citar-toolbar">
      <button class="citar-btn" type="button" :disabled="!dirty || saving" @click="discard">放弃修改</button>
      <button class="citar-btn citar-btn--primary" type="button" :disabled="!dirty || saving" @click="save">
        {{ saving ? '保存中…' : '保存金额' }}
      </button>
      <span class="citar-toolbar__hint">金额取自申报主表 A100000；改过的金额不再随申报表更新，可「恢复」。与税审底稿 1-01 是同一处</span>
    </div>
    <table class="sheet-table rb-amounts__table">
      <thead><tr><th>序号</th><th>项目</th><th>金额</th><th>说明</th></tr></thead>
      <tbody>
        <tr v-for="line in lines" :key="line.row" :class="{ 'rb-amounts__row--manual': isManual(line) }">
          <td class="citar-center">{{ line.no }}</td>
          <td>{{ line.item }}</td>
          <td class="is-numeric rb-amounts__cell" :class="{ 'rb-amounts__cell--editable': canManualEdit }" @click="startEdit(line)">
            <input
              v-if="editing === line.row"
              ref="inputRef"
              v-model="editText"
              class="citar-search rb-amounts__input"
              :aria-label="`修改 ${line.item}`"
              @keydown.enter.prevent="commit"
              @keydown.esc.prevent="editing = null"
              @blur="commit"
            />
            <template v-else>{{ display(line) }}</template>
          </td>
          <td class="rb-amounts__note">
            <template v-if="restored.has(line.row)">已恢复，保存后生效</template>
            <template v-else-if="isManual(line)">
              手工修改，原值 {{ format(line.manual ? line.auto : line.amount, line) || '空' }}
              <button v-if="canManualEdit" class="citar-btn rb-amounts__restore" type="button" :disabled="saving" @click="restore(line)">恢复</button>
            </template>
          </td>
        </tr>
      </tbody>
    </table>
  </details>
</template>

<script setup lang="ts">
/**
 * 报告正文摘录表 25 行金额的手工修改（spec citar-table-manual-edit R9）。
 * 点金额改 → 草稿；「保存金额」整份提交（未提交的行恢复为公式值），后端写底稿 1-01 的手工值。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { formatTaxValue, parseTaxInput, type TaxValue } from '@/views/tax-workpapers/taxWorkpaperApi'
import { numberOf, saveReportBodyAmounts, type ReportBodyData, type ReportBodyLine } from '../taxAssuranceApi'
import { useManualEditPermission } from '@/composables/useManualEditPermission'

const props = defineProps<{ data: ReportBodyData; projectId: string; year: number }>()
const emit = defineEmits<{ saved: [data: ReportBodyData] }>()
const { canManualEdit } = useManualEditPermission()

const lines = computed(() => props.data.lines)
/** 未保存的修改：{行号: 输入原文} */
const drafts = ref<Record<number, string>>({})
/** 已点「恢复」的手工行 */
const restored = ref<Set<number>>(new Set())
const editing = ref<number | null>(null)
const editText = ref('')
const inputRef = ref<HTMLInputElement[] | null>(null)
const saving = ref(false)

const dirty = computed(() => Object.keys(drafts.value).length > 0 || restored.value.size > 0)
const manualCount = computed(() => lines.value.filter(isManual).length)

watch(() => props.data, () => {
  drafts.value = {}
  restored.value = new Set()
})

function format(v: TaxValue | undefined, line: ReportBodyLine): string {
  return formatTaxValue(v, line.is_rate ? 'pct' : 'money')
}

function isManual(line: ReportBodyLine): boolean {
  if (line.row in drafts.value) return true
  return line.manual && !restored.value.has(line.row)
}

function display(line: ReportBodyLine): string {
  if (line.row in drafts.value) return drafts.value[line.row]
  if (restored.value.has(line.row)) return format(line.auto, line)
  return format(line.amount, line)
}

/** 编辑框里不带千分位；税率行按百分数 */
function plainText(line: ReportBodyLine): string {
  if (line.row in drafts.value) return drafts.value[line.row]
  const n = numberOf(restored.value.has(line.row) ? line.auto : line.amount)
  if (n === null) return ''
  return line.is_rate ? `${+(n * 100).toFixed(4)}%` : String(n)
}

async function startEdit(line: ReportBodyLine) {
  if (!canManualEdit.value || saving.value || editing.value === line.row) return
  editing.value = line.row
  editText.value = plainText(line)
  await nextTick()
  inputRef.value?.[0]?.focus()
  inputRef.value?.[0]?.select()
}

function commit() {
  const row = editing.value
  if (row === null) return
  editing.value = null
  const line = lines.value.find(l => l.row === row)
  if (!line || editText.value.trim() === plainText(line).trim()) return
  drafts.value = { ...drafts.value, [row]: editText.value.trim() }
  if (restored.value.has(row)) {
    const next = new Set(restored.value)
    next.delete(row)
    restored.value = next
  }
}

function restore(line: ReportBodyLine) {
  const next = { ...drafts.value }
  delete next[line.row]
  drafts.value = next
  if (line.manual) restored.value = new Set([...restored.value, line.row])
}

function discard() {
  drafts.value = {}
  restored.value = new Set()
}

/** 输入原文 → 金额；税率行没写 % 且大于 1 按百分数（填 25 即 25%） */
function parse(line: ReportBodyLine, text: string): number | null | undefined {
  const v = parseTaxInput(text)
  if (v === null) return null
  if (typeof v !== 'number') return undefined
  if (line.is_rate && !text.trim().endsWith('%') && Math.abs(v) > 1) return v / 100
  return v
}

async function save() {
  const values: Record<string, number | null> = {}
  for (const line of lines.value) {
    if (restored.value.has(line.row)) continue
    if (line.row in drafts.value) {
      const v = parse(line, drafts.value[line.row])
      if (v === undefined) {
        ElMessage.warning(`「${line.item}」只能填数字`)
        return
      }
      values[String(line.row)] = v
    } else if (line.manual) {
      values[String(line.row)] = numberOf(line.amount)
    }
  }
  saving.value = true
  try {
    const res = await saveReportBodyAmounts(props.projectId, props.year, props.data.amounts_version, values)
    ElMessage.success('摘录表金额已保存')
    emit('saved', res)
  } catch (e: any) {
    if (e?.response?.status === 409) ElMessage.warning('底稿 1-01 已被他人修改，请刷新后再改')
    else handleApiError(e, '保存摘录表金额')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>

<style scoped>
.rb-amounts {
  margin: 0 0 14px;
  border: 1px solid #eadff3;
  border-radius: var(--gt-radius-sm);
  background: var(--citar-c-fbf9fe);
}

.rb-amounts summary {
  padding: 8px 12px;
  color: var(--citar-c-4c1273);
  font-size: var(--citar-fs-13);
  font-weight: 600;
  cursor: pointer;
  user-select: none;
}

.rb-amounts[open] summary {
  border-bottom: 1px solid #eadff3;
}

.rb-amounts .citar-toolbar {
  margin: 10px 12px;
}

.rb-amounts__table {
  margin: 0 12px 12px;
  width: calc(100% - 24px);
}

.rb-amounts__badge {
  margin-left: 8px;
  font-weight: 400;
  color: var(--citar-c-8a5300);
}

.rb-amounts__cell {
  min-width: 160px;
}

.rb-amounts__cell--editable {
  cursor: text;
}

.rb-amounts__input {
  width: 100%;
  text-align: right;
}

.rb-amounts__row--manual .rb-amounts__cell {
  color: var(--citar-c-6e0ba6);
  background: #f6efff;
}

.rb-amounts__note {
  font-size: var(--citar-fs-12);
  color: var(--citar-c-8c8c96);
}

.rb-amounts__restore {
  margin-left: 6px;
  padding: 1px 8px;
}
</style>
