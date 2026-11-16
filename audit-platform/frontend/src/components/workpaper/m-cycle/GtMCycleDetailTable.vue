<script setup lang="ts">
/**
 * GtMCycleDetailTable ? M ??????**????**???
 *
 * ???????M3/M5/M7 ?????? el-table????????**??????**
 * ?????? ≤1?M5 ?? 14 ?????????? 6 ?????????????????
 * ?????????????????????? `remark`?
 *
 * ???**????????** `mCycleDetailColumns.generated.ts`??? = provider ?
 * `DETAIL_FIELDS` / `DETAIL_SHEET` + ?? xlsx ????????????? / ?????
 * ?????????????????????
 *
 * 🔴 ????**???**?`row_identity_kind = template_row_key`??
 * ????????????M3 10 ? / M5 4 ? / M7 7 ??+ ?????
 * ??????????????????????????????????????
 * ??**??????**??????????? OO ??????????????
 * ??????????????
 */
import { computed } from 'vue'
import {
  M_CYCLE_DETAIL_COLUMNS,
  type MCycleDetailField,
} from './mCycleDetailColumns.generated'

const props = withDefaults(
  defineProps<{
    /** ?? M entry?M3 / M5 / M7??????????? */
    entry: string
    /** ?????????????????? = jsonKey? */
    rows: Array<Record<string, unknown>>
    /** ?? */
    readonly?: boolean
  }>(),
  { readonly: false },
)

const emit = defineEmits<{
  (e: 'update', payload: { index: number; jsonKey: string; value: string | number }): void
}>()

const sheet = computed(() => M_CYCLE_DETAIL_COLUMNS[props.entry])
const fields = computed<MCycleDetailField[]>(() => sheet.value?.fields ?? [])
const rowLabels = computed<string[]>(() => sheet.value?.rowLabels ?? [])
const footerMarker = computed(() => sheet.value?.footerMarker ?? '??')

/** ????????????????????????????? */
const labelField = computed<MCycleDetailField | null>(() => fields.value[0] ?? null)
const bodyFields = computed<MCycleDetailField[]>(() => fields.value.slice(1))

/** ???????? group ??????? th?colspan??? group ????? */
interface HeaderCell {
  label: string
  span: number
}
const groupCells = computed<HeaderCell[]>(() => {
  const out: HeaderCell[] = []
  for (const f of bodyFields.value) {
    const label = f.group
    const last = out[out.length - 1]
    if (last && last.label === label) {
      last.span += 1
    } else {
      out.push({ label, span: 1 })
    }
  }
  return out
})

/** ???????????????????? th? */
const hasGroupRow = computed(() => bodyFields.value.some((f) => !!f.group))

function cellValue(row: Record<string, unknown> | undefined, key: string): unknown {
  return row?.[key]
}

function fmt(value: unknown, valueType: string): string {
  if (value === null || value === undefined || value === '') return '?'
  if (valueType !== 'amount') return String(value)
  const n = Number(value)
  if (!Number.isFinite(n)) return String(value)
  if (n === 0) return '?'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onInput(index: number, field: MCycleDetailField, raw: string): void {
  if (props.readonly || field.mode !== 'editable') return
  const value = field.valueType === 'amount' ? Number(raw || 0) : raw
  emit('update', { index, jsonKey: field.jsonKey, value })
}

/** ????????????????????????? */
function labelOf(index: number): string {
  const label = rowLabels.value[index]
  return label && label.trim() ? label : `第${index + 1}行`
}
</script>

<template>
  <div class="gt-m-detail">
    <el-table
      :data="rows"
      border
      size="small"
      style="width: 100%"
      :empty-text="fields.length ? '?????' : `??? ${entry} ????`"
    >
      <!-- ??????? A ? = ???? -->
      <el-table-column v-if="labelField" :min-width="170" fixed align="left">
        <template #header>
          <span class="hdr-leaf">{{ labelField.header }}</span>
        </template>
        <template #default="{ $index }">
          <span class="row-label">{{ labelOf($index) }}</span>
        </template>
      </el-table-column>

      <el-table-column
        v-for="f in bodyFields"
        :key="f.columnKey"
        :min-width="f.valueType === 'amount' ? 118 : 132"
        align="center"
      >
        <template #header>
          <div class="hdr">
            <div v-if="hasGroupRow" class="hdr-group">{{ f.group || '　' }}</div>
            <div class="hdr-leaf" :class="{ formula: f.mode === 'formula' }">{{ f.header }}</div>
          </div>
        </template>
        <template #default="{ row, $index }">
          <el-input
            v-if="f.mode === 'editable' && !readonly"
            :model-value="cellValue(row, f.jsonKey) as string"
            size="small"
            @change="(v: string) => onInput($index, f, v)"
          />
          <span v-else :class="{ formula: f.mode === 'formula' }">
            {{ fmt(cellValue(row, f.jsonKey), f.valueType) }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ????????? OO ????????? -->
    <div class="total-hint">
      ??? {{ rowLabels.length + 1 }} ???{{ footerMarker }}???????????????????????????
    </div>
  </div>
</template>

<style scoped>
.gt-m-detail { width: 100%; }
.hdr { display: flex; flex-direction: column; line-height: 1.3; }
.hdr-group { font-size: 12px; color: var(--el-text-color-secondary); }
.hdr-leaf { font-weight: 600; }
.hdr-leaf.formula { color: var(--el-color-primary); }
.formula { color: var(--el-color-primary); font-weight: 500; }
.row-label { color: var(--el-text-color-regular); }
.total-hint { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
</style>
