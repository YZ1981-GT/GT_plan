<!--
  GtDFormTable.vue — D 类表格型检查子组件（实现版）

  适用范围：~250 sheet（关联方矩阵 / 项目动态增删 / 字典下拉 / 审计结论）
  样本 schema：D-L5-6.yaml（关联方及交易检查表 / 16 列动态表）

  核心交互：
  - dynamic_table 全量列渲染（text/textarea/number/enum/multi_enum/date/boolean）
  - 行项目动态增删（max_rows 上限）
  - dictionary_dropdown：从 schema.dictionaries[dict_source] 拉下拉项
    + item.label 显示 + item.note tooltip 提示
  - render hints：amount(.gt-amt) / tag / checkmark / index_chip
  - composite 结论模式：审计说明 + 整体判定 radio + 备注
  - debounced auto-save（1.5s）emit 'save' 整体 payload
  - 单元格变更 emit 'field-change' { field_name, old_value, new_value }
  - 索引 chip 点击 emit 'jump-to-reference'

  锚定 spec workpaper-html-renderer Task 8.3
  Validates: Requirements 3.5（D 子模式 1：表格型检查）

  cross-ref:updated 订阅由 `useWpRenderer.ts` 集中处理（Task 13.2），本组件不直接订阅。
-->

<template>
  <div class="gt-d-form-table">
    <!-- ─── 顶部头部信息（只读展示） ─── -->
    <header v-if="hasHeaderInfo" class="gt-dft__header">
      <div class="gt-dft__header-meta">
        <span v-if="entityName" class="gt-dft__entity">{{ entityName }}</span>
        <span v-if="periodEnd" class="gt-dft__period">{{ periodEnd }}</span>
      </div>
      <div v-if="indexNo" class="gt-dft__index">
        索引号：<strong>{{ indexNo }}</strong>
      </div>
    </header>

    <!-- ─── 上下文字段区（schema.fields） ─── -->
    <section v-if="contextFields.length" class="gt-dft__context">
      <el-form
        :model="contextData"
        label-position="top"
        :disabled="readonly"
        class="gt-dft__context-form"
      >
        <el-form-item
          v-for="field in contextFields"
          :key="field.name"
          :label="field.label"
          :required="!!field.required"
          class="gt-dft__context-item"
        >
          <el-input
            v-if="field.type === 'textarea'"
            v-model="contextData[field.name]"
            type="textarea"
            :rows="3"
            :maxlength="field.max_length"
            :show-word-limit="!!field.max_length"
            :placeholder="field.hint || field.label"
            @change="onContextFieldChange(field.name)"
          />
          <el-input
            v-else
            v-model="contextData[field.name]"
            :maxlength="field.max_length"
            :show-word-limit="!!field.max_length"
            :placeholder="field.hint || field.label"
            @change="onContextFieldChange(field.name)"
          />
          <div v-if="field.hint" class="gt-dft__field-hint">
            <el-icon><InfoFilled /></el-icon>
            <span>{{ field.hint }}</span>
          </div>
        </el-form-item>
      </el-form>
    </section>

    <!-- ─── 动态表格工具栏 ─── -->
    <div class="gt-dft__toolbar">
      <h3 class="gt-dft__title">{{ tableTitle }}</h3>
      <div v-if="!readonly" class="gt-dft__toolbar-actions">
        <el-tooltip
          :content="`已添加 ${tableRows.length} / ${maxRows} 行`"
          placement="top"
        >
          <el-button
            size="small"
            :icon="PlusIcon"
            :disabled="reachedMaxRows"
            @click="handleAddRow"
          >新增行</el-button>
        </el-tooltip>
      </div>
    </div>

    <!-- ─── 动态表格 ─── -->
    <el-table
      :data="tableRows"
      border
      size="small"
      class="gt-dft__table"
      empty-text="暂无数据，点击「新增行」开始填写"
    >
      <el-table-column
        v-for="col in tableColumns"
        :key="col.field"
        :label="col.label"
        :min-width="col.width || 120"
        resizable
      >
        <template #default="{ row, $index }">
          <!-- index_chip 渲染（关联底稿） -->
          <div v-if="col.render === 'index_chip'" class="gt-dft__cell-chip">
            <el-input
              v-if="!readonly"
              v-model="row[col.field]"
              size="small"
              :maxlength="col.max_length"
              :placeholder="col.label"
              @change="onCellChange(row, col.field, $index)"
            />
            <div v-if="row[col.field]" class="gt-dft__chip-preview">
              <GtIndexChip
                v-for="ref in splitRefs(row[col.field])"
                :key="ref"
                :value="ref"
                :validate="true"
                @click="onIndexChipClick(ref)"
              />
            </div>
          </div>

          <!-- 字典下拉 dictionary_dropdown -->
          <el-select
            v-else-if="col.render === 'dictionary_dropdown'"
            v-model="row[col.field]"
            :disabled="readonly"
            size="small"
            clearable
            filterable
            :placeholder="col.label"
            @change="onCellChange(row, col.field, $index)"
          >
            <el-option
              v-for="item in resolveDictItems(col)"
              :key="item.value"
              :value="item.value"
              :label="item.label"
            >
              <el-tooltip
                v-if="item.note"
                :content="item.note"
                placement="right"
                :show-after="200"
              >
                <span class="gt-dft__dict-option">
                  <span>{{ item.label }}</span>
                  <el-icon class="gt-dft__dict-info"><InfoFilled /></el-icon>
                </span>
              </el-tooltip>
              <span v-else>{{ item.label }}</span>
            </el-option>
          </el-select>

          <!-- enum 单选 -->
          <el-select
            v-else-if="col.type === 'enum'"
            v-model="row[col.field]"
            :disabled="readonly"
            size="small"
            clearable
            :placeholder="col.label"
            :class="col.render === 'tag' ? 'gt-dft__tag-select' : ''"
            @change="onCellChange(row, col.field, $index)"
          >
            <el-option
              v-for="opt in col.enum || []"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>

          <!-- multi_enum 多选 -->
          <el-select
            v-else-if="col.type === 'multi_enum'"
            v-model="row[col.field]"
            :disabled="readonly"
            size="small"
            multiple
            collapse-tags
            collapse-tags-tooltip
            :placeholder="col.label"
            @change="onCellChange(row, col.field, $index)"
          >
            <el-option
              v-for="opt in col.enum || []"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>

          <!-- number / amount -->
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.field]"
            :disabled="readonly"
            :min="col.min"
            :max="col.max"
            :precision="col.render === 'amount' ? 2 : undefined"
            size="small"
            controls-position="right"
            :class="col.render === 'amount' ? 'gt-amt gt-dft__amount-input' : ''"
            @change="onCellChange(row, col.field, $index)"
          />

          <!-- date -->
          <el-date-picker
            v-else-if="col.type === 'date'"
            v-model="row[col.field]"
            :disabled="readonly"
            type="date"
            size="small"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            :placeholder="col.label"
            class="gt-dft__date-picker"
            @change="onCellChange(row, col.field, $index)"
          />

          <!-- boolean / checkmark -->
          <div v-else-if="col.type === 'boolean'" class="gt-dft__cell-bool">
            <el-checkbox
              v-model="row[col.field]"
              :disabled="readonly"
              @change="onCellChange(row, col.field, $index)"
            />
            <el-icon
              v-if="col.render === 'checkmark' && row[col.field]"
              class="gt-dft__check-icon"
            ><CircleCheckFilled /></el-icon>
          </div>

          <!-- textarea -->
          <el-input
            v-else-if="col.type === 'textarea'"
            v-model="row[col.field]"
            :disabled="readonly"
            type="textarea"
            :rows="2"
            size="small"
            :maxlength="col.max_length"
            :placeholder="col.label"
            @change="onCellChange(row, col.field, $index)"
          />

          <!-- text 默认 -->
          <el-input
            v-else
            v-model="row[col.field]"
            :disabled="readonly"
            size="small"
            :maxlength="col.max_length"
            :placeholder="col.label"
            @change="onCellChange(row, col.field, $index)"
          />
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column
        v-if="!readonly"
        label="操作"
        width="80"
        fixed="right"
      >
        <template #default="{ $index }">
          <el-button
            link
            type="danger"
            size="small"
            @click="handleRemoveRow($index)"
          >删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ─── composite 结论区（审计说明 + 整体判定 + 备注） ─── -->
    <section v-if="hasComposite" class="gt-dft__conclusion">
      <h3 class="gt-dft__title">审计结论</h3>

      <!-- 审计说明 -->
      <el-form-item
        v-if="explanationField"
        :label="explanationField.label"
        class="gt-dft__concl-item"
      >
        <el-input
          v-model="conclusionData.audit_explanation"
          type="textarea"
          :rows="4"
          :disabled="readonly"
          :maxlength="explanationField.max_length"
          :show-word-limit="!!explanationField.max_length"
          :placeholder="explanationField.hint || explanationField.label"
          @change="onConclusionFieldChange('audit_explanation')"
        />
        <div v-if="explanationField.hint" class="gt-dft__field-hint">
          <el-icon><InfoFilled /></el-icon>
          <span>{{ explanationField.hint }}</span>
        </div>
      </el-form-item>

      <!-- 整体判定 -->
      <el-form-item
        v-if="overallField"
        :label="overallField.label"
        :required="!!overallField.required"
        class="gt-dft__concl-item"
      >
        <el-radio-group
          v-model="conclusionData.overall_conclusion"
          :disabled="readonly"
          class="gt-dft__overall-group"
          @change="onConclusionFieldChange('overall_conclusion')"
        >
          <el-radio
            v-for="opt in overallOptions"
            :key="opt.value"
            :value="opt.value"
            :class="['gt-dft__overall-option', `is-${opt.class || 'info'}`]"
          >
            <div class="gt-dft__overall-label">
              <el-icon
                v-if="opt.icon && conclusionIcons[opt.icon]"
                class="gt-dft__overall-icon"
              >
                <component :is="conclusionIcons[opt.icon]" />
              </el-icon>
              <span>{{ opt.label }}</span>
            </div>
          </el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- 备注 -->
      <el-form-item
        v-if="remarksField"
        :label="remarksField.label"
        class="gt-dft__concl-item"
      >
        <el-input
          v-model="conclusionData.remarks"
          type="textarea"
          :rows="3"
          :disabled="readonly"
          :maxlength="remarksField.max_length"
          :show-word-limit="!!remarksField.max_length"
          :placeholder="remarksField.hint || remarksField.label"
          @change="onConclusionFieldChange('remarks')"
        />
      </el-form-item>
    </section>
  </div>
</template>


<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import {
  InfoFilled,
  CircleCheckFilled,
  CircleCheck,
  WarningFilled,
  CircleCloseFilled,
  Plus as PlusIcon,
} from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import type { DFormSchema, DFormData, FieldChangePayload } from './GtDForm.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

type ColumnType = 'text' | 'textarea' | 'number' | 'enum' | 'multi_enum' | 'date' | 'boolean'
type RenderHint =
  | 'dictionary_dropdown'
  | 'amount'
  | 'tag'
  | 'checkmark'
  | 'index_chip'
  | string

interface ColumnDef {
  field: string
  label: string
  type?: ColumnType
  enum?: string[]
  render?: RenderHint
  dict_source?: string
  width?: number
  min?: number
  max?: number
  max_length?: number
  required?: boolean
  format?: string
}

interface DictItem {
  value: string
  label: string
  note?: string
}

interface DictDef {
  description?: string
  source?: string
  items: DictItem[]
}

interface OverallOption {
  value: string
  label: string
  class?: 'success' | 'warning' | 'danger' | 'info'
  icon?: string
}

interface ContextField {
  name: string
  label: string
  type?: ColumnType
  cell?: string
  max_length?: number
  required?: boolean
  hint?: string
}

interface DynamicTableSchema {
  start_row?: number
  end_row?: number | string
  header_row?: number
  add_row_button?: boolean
  max_rows?: number
  columns?: Record<string, ColumnDef>
}

interface ConclusionFieldDef {
  name: string
  label: string
  type?: string
  cell_after_table?: number
  max_length?: number
  required?: boolean
  hint?: string
  enum?: OverallOption[]
}

interface CompositeConclusion {
  mode?: 'composite' | string
  audit_explanation_field?: ConclusionFieldDef
  overall_conclusion_field?: ConclusionFieldDef
  remarks_field?: ConclusionFieldDef
}

type TableRow = Record<string, any> & { _row_id?: string }

interface TableData extends DFormData {
  context?: Record<string, any>
  rows?: TableRow[]
  conclusion?: {
    audit_explanation?: string
    overall_conclusion?: string
    remarks?: string
  }
}

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: DFormSchema
  htmlData: DFormData
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  'field-change': [payload: FieldChangePayload]
  'jump-to-reference': [refCode: string]
  'save': [data: DFormData]
}>()


// ─── Refs（按 setup const 顺序铁律放最前） ────────────────────────────────────

const contextData = ref<Record<string, any>>({})
const tableRows = ref<TableRow[]>([])
const conclusionData = ref<{
  audit_explanation: string
  overall_conclusion: string
  remarks: string
}>({
  audit_explanation: '',
  overall_conclusion: '',
  remarks: '',
})

let saveTimer: ReturnType<typeof setTimeout> | null = null

// ─── Static maps ─────────────────────────────────────────────────────────────

const conclusionIcons: Record<string, any> = {
  CircleCheck,
  CircleCheckFilled,
  WarningFilled,
  CircleCloseFilled,
}

// ─── Computed ────────────────────────────────────────────────────────────────

const fixedCells = computed(() => (props.schema as any)?.fixed_cells ?? {})

const entityName = computed(() => fixedCells.value?.A3 || '')
const periodEnd = computed(() => fixedCells.value?.A4 || '')
const indexNo = computed(
  () => fixedCells.value?.P3 || fixedCells.value?.O3 || fixedCells.value?.J3 || ''
)
const hasHeaderInfo = computed(
  () => !!(entityName.value || periodEnd.value || indexNo.value)
)

const contextFields = computed<ContextField[]>(() => {
  const arr = (props.schema as any)?.fields
  return Array.isArray(arr) ? arr as ContextField[] : []
})

const dynamicTable = computed<DynamicTableSchema | null>(() => {
  const dt = (props.schema as any)?.dynamic_table
  return dt && typeof dt === 'object' ? dt : null
})

const tableColumns = computed<ColumnDef[]>(() => {
  const cols = dynamicTable.value?.columns ?? {}
  return Object.entries(cols).map(([_cell, def]) => def as ColumnDef)
})

const maxRows = computed(() => dynamicTable.value?.max_rows ?? 100)

const reachedMaxRows = computed(() => tableRows.value.length >= maxRows.value)

const tableTitle = computed(() => props.sheetName || '动态明细表')

const dictionaries = computed<Record<string, DictDef>>(
  () => (props.schema as any)?.dictionaries ?? {}
)

const conclusionBlock = computed<CompositeConclusion | null>(() => {
  const c = (props.schema as any)?.conclusion
  return c && typeof c === 'object' ? c : null
})

const hasComposite = computed(
  () =>
    conclusionBlock.value?.mode === 'composite' &&
    !!(
      conclusionBlock.value?.audit_explanation_field ||
      conclusionBlock.value?.overall_conclusion_field ||
      conclusionBlock.value?.remarks_field
    )
)

const explanationField = computed(
  () => conclusionBlock.value?.audit_explanation_field || null
)
const overallField = computed(
  () => conclusionBlock.value?.overall_conclusion_field || null
)
const remarksField = computed(
  () => conclusionBlock.value?.remarks_field || null
)

const overallOptions = computed<OverallOption[]>(() => {
  const opts = overallField.value?.enum
  if (!Array.isArray(opts)) return []
  return opts as OverallOption[]
})


// ─── Helpers ─────────────────────────────────────────────────────────────────

function genRowId(): string {
  return `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function buildEmptyRow(): TableRow {
  const row: TableRow = { _row_id: genRowId() }
  for (const col of tableColumns.value) {
    if (col.type === 'multi_enum') row[col.field] = []
    else if (col.type === 'number') row[col.field] = null
    else if (col.type === 'boolean') row[col.field] = false
    else row[col.field] = ''
  }
  // 自动填充序号（如果列名为 seq）
  const seqCol = tableColumns.value.find(c => c.field === 'seq')
  if (seqCol) {
    row.seq = tableRows.value.length + 1
  }
  return row
}

function resolveDictItems(col: ColumnDef): DictItem[] {
  if (col.render !== 'dictionary_dropdown') return []
  const dictKey = col.dict_source
  if (dictKey && dictionaries.value[dictKey]?.items) {
    return dictionaries.value[dictKey].items
  }
  // Fallback to enum
  if (Array.isArray(col.enum)) {
    return col.enum.map(v => ({ value: v, label: v }))
  }
  return []
}

function splitRefs(value: any): string[] {
  if (!value) return []
  const text = String(value).trim()
  if (!text) return []
  // 多个底稿引用允许用逗号 / 分号 / 空格 / 顿号 分隔
  return text
    .split(/[\s,，、;；]+/)
    .map(s => s.trim())
    .filter(Boolean)
}

// ─── Field change emitters ───────────────────────────────────────────────────

function emitFieldChange(field_name: string, oldValue: any, newValue: any) {
  emit('field-change', {
    field_name,
    old_value: oldValue,
    new_value: newValue,
  })
}

// ─── Context fields ──────────────────────────────────────────────────────────

function onContextFieldChange(name: string) {
  emitFieldChange(`context.${name}`, undefined, contextData.value[name])
  debounceSave()
}

// ─── Table cell handlers ─────────────────────────────────────────────────────

function handleAddRow() {
  if (reachedMaxRows.value) return
  tableRows.value.push(buildEmptyRow())
  debounceSave()
}

function handleRemoveRow(idx: number) {
  tableRows.value.splice(idx, 1)
  // 如有 seq 列，重排序号
  const hasSeq = tableColumns.value.some(c => c.field === 'seq')
  if (hasSeq) {
    tableRows.value.forEach((r, i) => {
      r.seq = i + 1
    })
  }
  debounceSave()
}

function onCellChange(row: TableRow, fieldName: string, idx: number) {
  emitFieldChange(`rows[${idx}].${fieldName}`, undefined, row[fieldName])
  debounceSave()
}

function onIndexChipClick(refCode: string) {
  emit('jump-to-reference', refCode)
}

// ─── Conclusion handlers ─────────────────────────────────────────────────────

function onConclusionFieldChange(name: 'audit_explanation' | 'overall_conclusion' | 'remarks') {
  emitFieldChange(`conclusion.${name}`, undefined, conclusionData.value[name])
  debounceSave()
}


// ─── Init / Sync ─────────────────────────────────────────────────────────────

function initData() {
  const data = (props.htmlData ?? {}) as TableData

  // 上下文字段
  const ctxIn = data.context && typeof data.context === 'object' ? data.context : {}
  const ctxOut: Record<string, any> = {}
  for (const f of contextFields.value) {
    ctxOut[f.name] = (ctxIn as Record<string, any>)[f.name] ?? ''
  }
  contextData.value = ctxOut

  // 表格行
  const rowsIn = Array.isArray(data.rows) ? data.rows : []
  tableRows.value = rowsIn.map((r): TableRow => {
    const cleaned: TableRow = { _row_id: r._row_id || genRowId() }
    for (const col of tableColumns.value) {
      if (Object.prototype.hasOwnProperty.call(r, col.field)) {
        cleaned[col.field] = r[col.field]
      } else if (col.type === 'multi_enum') {
        cleaned[col.field] = []
      } else if (col.type === 'number') {
        cleaned[col.field] = null
      } else if (col.type === 'boolean') {
        cleaned[col.field] = false
      } else {
        cleaned[col.field] = ''
      }
    }
    return cleaned
  })

  // 结论
  const c = data.conclusion && typeof data.conclusion === 'object' ? data.conclusion : {}
  conclusionData.value = {
    audit_explanation: typeof c.audit_explanation === 'string' ? c.audit_explanation : '',
    overall_conclusion: typeof c.overall_conclusion === 'string' ? c.overall_conclusion : '',
    remarks: typeof c.remarks === 'string' ? c.remarks : '',
  }
}

initData()

watch(
  () => props.htmlData,
  () => {
    initData()
  },
  { deep: true }
)

watch(
  () => props.schema,
  () => {
    // schema 变化（结构差异）时重新初始化
    initData()
  },
  { deep: true }
)

// ─── Save payload + debounce ─────────────────────────────────────────────────

function buildSavePayload(): TableData {
  const payload: TableData = {
    ...(props.htmlData || {}),
    context: { ...contextData.value },
    rows: tableRows.value.map(r => {
      const out: TableRow = {}
      if (r._row_id) out._row_id = r._row_id
      for (const col of tableColumns.value) {
        out[col.field] = r[col.field]
      }
      return out
    }),
    conclusion: { ...conclusionData.value },
  }
  return payload
}

function debounceSave() {
  if (props.readonly) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    emit('save', buildSavePayload())
  }, 1500)
}

// ─── Cleanup ─────────────────────────────────────────────────────────────────

onBeforeUnmount(() => {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
})

// ─── wp-locate-foundation Task 3.2: 暴露 scrollToRow 定位接口 ───
function scrollToRow(index: number) {
  const container = document.querySelector('.gt-d-form-table')
  if (!container) return
  const rows = container.querySelectorAll('.el-table__body .el-table__row')
  if (index >= 0 && index < rows.length) {
    rows[index].scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

defineExpose({ scrollToRow })
</script>


<style scoped>
.gt-d-form-table {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
}

/* ── Header ── */
.gt-dft__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 14px;
  background: var(--gt-color-bg-soft, #f5f7fa);
  border-radius: 6px;
  font-size: 13px;
}
.gt-dft__header-meta {
  display: flex;
  align-items: center;
  gap: 16px;
}
.gt-dft__entity {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-dft__period {
  color: var(--el-text-color-regular);
}
.gt-dft__index {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dft__index strong {
  color: var(--el-color-primary);
  margin-left: 4px;
}

/* ── Context fields ── */
.gt-dft__context {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 12px 16px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-dft__context-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 12px 16px;
}
.gt-dft__context-item {
  margin-bottom: 0;
}

/* ── Toolbar ── */
.gt-dft__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
}
.gt-dft__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-dft__toolbar-actions {
  display: flex;
  gap: 8px;
}

/* ── Table ── */
.gt-dft__table {
  width: 100%;
}
.gt-dft__cell-chip {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-dft__chip-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.gt-dft__cell-bool {
  display: flex;
  align-items: center;
  gap: 6px;
}
.gt-dft__check-icon {
  color: var(--el-color-success);
  font-size: 16px;
}
.gt-dft__amount-input :deep(.el-input__inner) {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  text-align: right;
}
.gt-dft__date-picker {
  width: 100%;
}
.gt-dft__tag-select :deep(.el-select__selected-item) {
  font-weight: 500;
}

/* ── Dictionary option layout ── */
.gt-dft__dict-option {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: 100%;
}
.gt-dft__dict-info {
  color: var(--el-color-info);
  font-size: 14px;
}

/* ── Field hint ── */
.gt-dft__field-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dft__field-hint .el-icon {
  color: var(--el-color-info);
}

/* ── Conclusion ── */
.gt-dft__conclusion {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-color-primary-light-9);
}
.gt-dft__concl-item {
  margin-bottom: 0;
}
.gt-dft__overall-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.gt-dft__overall-group :deep(.el-radio) {
  height: auto;
  padding: 10px 12px;
  margin-right: 0;
  align-items: flex-start;
  border: 1px solid transparent;
  border-radius: 4px;
  transition: background 0.15s, border-color 0.15s;
}
.gt-dft__overall-group :deep(.el-radio:hover) {
  background: var(--el-color-primary-light-8);
}
.gt-dft__overall-group :deep(.el-radio.is-checked) {
  background: var(--el-color-primary-light-8);
  border-color: var(--el-color-primary-light-5);
}
.gt-dft__overall-option.is-success :deep(.el-radio.is-checked) {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-8);
}
.gt-dft__overall-option.is-warning :deep(.el-radio.is-checked) {
  border-color: var(--el-color-warning);
  background: var(--el-color-warning-light-8);
}
.gt-dft__overall-option.is-danger :deep(.el-radio.is-checked) {
  border-color: var(--el-color-danger);
  background: var(--el-color-danger-light-8);
}
.gt-dft__overall-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
.gt-dft__overall-icon {
  font-size: 16px;
}
.gt-dft__overall-option.is-success .gt-dft__overall-icon {
  color: var(--el-color-success);
}
.gt-dft__overall-option.is-warning .gt-dft__overall-icon {
  color: var(--el-color-warning);
}
.gt-dft__overall-option.is-danger .gt-dft__overall-icon {
  color: var(--el-color-danger);
}
.gt-dft__overall-option.is-info .gt-dft__overall-icon {
  color: var(--el-color-info);
}
</style>
