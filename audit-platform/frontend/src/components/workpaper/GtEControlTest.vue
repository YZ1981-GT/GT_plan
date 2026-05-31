<!--
  GtEControlTest.vue — E 类控制测试 shell 组件
  3 种 test_type 路由（summary / single / evaluation_step）+ 结论 + 提示折叠
  子组件：EControlSummaryTable / EControlSingleForm / EControlEvalStepper / EControlAiPanel
-->

<template>
  <div class="gt-e-control-test">
    <!-- ─── 顶部：固定头部 + 索引号（只读展示） ─── -->
    <header v-if="hasHeaderInfo" class="gt-e__header">
      <div class="gt-e__header-meta">
        <span class="gt-e__entity">{{ entityName || '—' }}</span>
        <span class="gt-e__period">{{ periodEnd || '—' }}</span>
      </div>
      <div v-if="indexNo" class="gt-e__index">
        索引号：<strong>{{ indexNo }}</strong>
      </div>
    </header>

    <!-- ───────── summary 子模式：动态表 + per_row 缺陷 ───────── -->
    <EControlSummaryTable
      v-if="testType === 'summary'"
      :schema="schema"
      :rows="summaryRows"
      :readonly="readonly"
      @field-change="onSummaryFieldChange"
      @add-row="handleAddSummaryRow"
      @remove-row="handleRemoveSummaryRow"
      @open-attachment="openAttachment"
    />

    <!-- ───────── evaluation_step 子模式：6 步骤 stepper ───────── -->
    <EControlEvalStepper
      v-else-if="testType === 'evaluation_step'"
      :schema="schema"
      :data="evalData"
      :active-step-no="activeStepNo"
      :current-step="currentStep"
      :is-terminal-step="isTerminalStep"
      :readonly="readonly"
      @field-change="onEvalFieldChange"
      @step-advance="advanceStep"
      @go-to-step="goToStep"
      @open-attachment="openAttachment"
    />

    <!-- ───────── single 子模式：7 segments 顺序渲染（默认 fallback） ───────── -->
    <EControlSingleForm
      v-else
      :schema="schema"
      :data="singleData"
      :readonly="readonly"
      @field-change="onSingleFieldChange"
      @ai-suggest="onAiSuggestField"
      @open-attachment="openAttachment"
    />

    <!-- ───────── AI 建议面板（3 子模式复用，单一实例） ───────── -->
    <EControlAiPanel
      ref="aiPanelRef"
      :wp-id="wpId"
      :sheet-name="sheetName"
      :test-type="testType"
      @adopt="handleAiAdopt"
      @modify="handleAiModify"
    />

    <!-- ───────── 结论区（single + evaluation_step 共用） ───────── -->
    <section
      v-if="hasConclusion"
      class="gt-e__conclusion"
    >
      <h3 class="gt-e__title">最终结论</h3>
      <el-radio-group
        v-model="conclusionValue"
        :disabled="readonly"
        class="gt-e__conclusion-group"
        @change="onConclusionChange"
      >
        <el-radio
          v-for="opt in conclusionOptions"
          :key="opt.value"
          :value="opt.value"
          :class="['gt-e__conclusion-option', `is-${opt.class || 'info'}`]"
        >
          <div class="gt-e__conclusion-label">
            <span class="gt-e__conclusion-name">{{ opt.label }}</span>
            <span
              v-if="opt.description"
              class="gt-e__conclusion-desc"
            >{{ opt.description }}</span>
          </div>
        </el-radio>
      </el-radio-group>
    </section>

    <!-- ───────── 提示区（折叠展开） ───────── -->
    <section v-if="hints.length" class="gt-e__hints">
      <el-collapse v-model="activeHintIds">
        <el-collapse-item
          v-for="hint in hints"
          :key="hint.id"
          :name="hint.id"
          :title="hint.label"
        >
          <!-- reference_table 类型 -->
          <el-table
            v-if="hint.type === 'reference_table'"
            :data="hintTableRows(hint)"
            border
            size="small"
          >
            <el-table-column
              v-for="(col, idx) in (hint.columns || [])"
              :key="col"
              :label="col"
              :prop="`c${idx}`"
            />
          </el-table>

          <!-- items 列表 -->
          <ol v-else-if="hint.items && hint.items.length" class="gt-e__hint-items">
            <li
              v-for="item in hint.items"
              :key="item.no"
            >{{ item.content }}</li>
          </ol>

          <!-- 单段长文本 -->
          <pre v-else-if="hint.content" class="gt-e__hint-content">{{ hint.content }}</pre>
        </el-collapse-item>
      </el-collapse>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import EControlAiPanel from './econtrol/EControlAiPanel.vue'
import EControlSummaryTable from './econtrol/EControlSummaryTable.vue'
import EControlSingleForm from './econtrol/EControlSingleForm.vue'
import EControlEvalStepper from './econtrol/EControlEvalStepper.vue'
import type {
  NextLogic,
  StepDef,
  HintBlock,
  DynamicTableColumnDef,
  EControlTestSchema,
  SummaryRow,
  EControlTestData,
  SuggestionPayload,
} from './GtEControlTest.types'
import { safeEvaluate, hintTableRows } from './econtrol/econtrolHelpers'
import { useEControlConclusion } from './econtrol/composables/useEControlConclusion'
import { useEControlPersist } from './econtrol/composables/useEControlPersist'

export type { EControlTestSchema, EControlTestData, SuggestionPayload }

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  wpId: string
  sheetName: string
  schema: EControlTestSchema
  htmlData: EControlTestData
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  'step-advance': [step: number]
  'conclusion-change': [conclusion: string]
  'trigger-procedure-trimming-suggestion': [payload: SuggestionPayload]
  'save': [data: EControlTestData]
  'open-attachment': [payload: { wpId: string; sheetName: string; rowRef: string }]
}>()

// ─── Refs（按 setup const 顺序铁律放最前） ────────────────────────────────────
const summaryRows = ref<SummaryRow[]>([])
const singleData = ref<Record<string, any>>({})
const evalData = ref<Record<string, any>>({})
const activeStepNo = ref<number>(1)
const conclusionValue = ref<string>('')
const activeHintIds = ref<string[]>([])

// ─── Computed ────────────────────────────────────────────────────────────────
const testType = computed(() => props.schema?.test_type ?? 'single')
const steps = computed<StepDef[]>(() => {
  const arr = props.schema?.steps ?? []
  return [...arr].sort((a, b) => (a.step ?? 0) - (b.step ?? 0))
})
const hints = computed<HintBlock[]>(() => props.schema?.hints ?? [])

// ─── AI 面板 ─────────────────────────────────────────────────────────────────
const aiPanelRef = ref<InstanceType<typeof EControlAiPanel> | null>(null)
const assistedFieldsList = computed(() => aiPanelRef.value?.assistedFieldsList ?? [])

// ─── 数据持久化 composable ───────────────────────────────────────────────────
const { initData, debounceSave } = useEControlPersist({
  props: { get schema() { return props.schema }, get htmlData() { return props.htmlData }, get readonly() { return props.readonly } },
  testType, steps, hints, summaryRows, singleData, evalData,
  activeStepNo, conclusionValue, activeHintIds, assistedFieldsList,
  emit: (e, data) => emit('save', data),
})

function onAiSuggestField(fieldName: string) {
  const ctx = testType.value === 'evaluation_step' ? evalData.value : singleData.value
  const existingContent = ctx[fieldName] || ''
  aiPanelRef.value?.triggerSuggestion(fieldName, existingContent)
}

function handleAiAdopt(fieldName: string, text: string) {
  if (testType.value === 'evaluation_step') {
    evalData.value[fieldName] = text
  } else {
    singleData.value[fieldName] = text
  }
  debounceSave()
}

function handleAiModify(fieldName: string, text: string) {
  handleAiAdopt(fieldName, text)
}

// ─── 结论 composable ─────────────────────────────────────────────────────────
const { conclusionBlock, conclusionOptions, deriveSuggestion, deriveConfidence, onConclusionChange } = useEControlConclusion({
  props: { wpId: props.wpId, sheetName: props.sheetName },
  testType,
  conclusionValue,
  schema: computed(() => props.schema),
  evalData,
  singleData,
  emit,
  debounceSave,
})

const hasConclusion = computed(() => testType.value !== 'summary' && conclusionOptions.value.length > 0)

const summaryColumns = computed<DynamicTableColumnDef[]>(() => {
  const cols = props.schema?.dynamic_table?.columns ?? {}
  return Object.entries(cols).map(([_, def]) => ({ ...(def as DynamicTableColumnDef), width: (def as DynamicTableColumnDef).type === 'textarea' ? 200 : 120 }))
})

const fixedCells = computed(() => props.schema?.fixed_cells ?? {})
const entityName = computed(() => fixedCells.value.A3 || '')
const periodEnd = computed(() => fixedCells.value.A4 || '')
const indexNo = computed(() => fixedCells.value.O3 || fixedCells.value.J3 || fixedCells.value.I3 || '')
const hasHeaderInfo = computed(() => !!(entityName.value || periodEnd.value || indexNo.value))

const currentStep = computed<StepDef | null>(() => steps.value.find(s => s.step === activeStepNo.value) ?? null)
const activeStepIdx = computed(() => { const idx = steps.value.findIndex(s => s.step === activeStepNo.value); return idx >= 0 ? idx : 0 })
const isTerminalStep = computed(() => !!currentStep.value?.is_terminal)

function evaluateNextLogic(step: StepDef, ctx: Record<string, any>): NextLogic | null {
  if (!step.next_logic || step.next_logic.length === 0) return null
  for (const rule of step.next_logic) {
    if (!rule.when || rule.when === 'true') return rule
    if (safeEvaluate(rule.when, ctx)) return rule
  }
  return null
}

function advanceStep() {
  if (!currentStep.value) return
  const next = evaluateNextLogic(currentStep.value, evalData.value)
  if (next?.conclusion_hint && !conclusionValue.value) conclusionValue.value = next.conclusion_hint
  const targetStepNo = next?.goto ?? (activeStepNo.value + 1)
  const targetStep = steps.value.find(s => s.step === targetStepNo)
  if (targetStep) {
    activeStepNo.value = targetStepNo
    emit('step-advance', targetStepNo)
    debounceSave()
  }
}

function goToStep(idx: number) {
  const target = steps.value[idx]
  if (target) {
    activeStepNo.value = target.step
    emit('step-advance', target.step)
  }
}

function openAttachment(stepOrRowId: string) {
  emit('open-attachment', {
    wpId: props.wpId,
    sheetName: props.sheetName,
    rowRef: `${props.sheetName}:${stepOrRowId}`,
  })
}

function buildEmptySummaryRow(): SummaryRow {
  const row: SummaryRow = { id: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` }
  for (const col of summaryColumns.value) { row[col.field] = col.type === 'multi_enum' ? [] : (col.type === 'number' ? 0 : '') }
  return row
}
function handleAddSummaryRow() { summaryRows.value.push(buildEmptySummaryRow()); debounceSave() }
function handleRemoveSummaryRow(idx: number) { summaryRows.value.splice(idx, 1); debounceSave() }
function onSummaryFieldChange(_row: SummaryRow, _field: string, _idx: number) { debounceSave() }
function onSingleFieldChange(_name: string) { debounceSave() }

function onEvalFieldChange(name: string) {
  // 当步骤六的 final_conclusion 字段变化时，同步到 conclusionValue
  if (currentStep.value?.is_terminal && (name === 'final_conclusion' || name === currentStep.value.fields.find(f => f.required && f.type === 'enum')?.name)) {
    conclusionValue.value = String(evalData.value[name] ?? '')
    onConclusionChange(conclusionValue.value)
  }
  debounceSave()
}

initData()

watch(() => props.htmlData, () => { initData() }, { deep: true })
watch(() => props.schema, () => { activeStepNo.value = steps.value[0]?.step ?? 1 }, { deep: true })

// ─── wp-locate-foundation Task 3.2: 暴露 scrollToRow 定位接口 ───
function scrollToRow(index: number) {
  const container = document.querySelector('.gt-e-control-test')
  if (!container) return
  const rows = container.querySelectorAll('.el-table__body .el-table__row')
  if (index >= 0 && index < rows.length) {
    rows[index].scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

defineExpose({ scrollToRow })
</script>

<style scoped>
.gt-e-control-test { padding: 16px; display: flex; flex-direction: column; gap: 24px; }
.gt-e__header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; padding: 12px 16px; background: var(--gt-color-bg-soft, #f5f7fa); border-radius: 6px; font-size: 13px; }
.gt-e__header-meta { display: flex; align-items: center; gap: 16px; }
.gt-e__entity { font-weight: 600; color: var(--el-text-color-primary); }
.gt-e__period { color: var(--el-text-color-regular); }
.gt-e__index { color: var(--el-text-color-secondary); font-size: 12px; }
.gt-e__index strong { color: var(--el-color-primary); margin-left: 4px; }
.gt-e__title { margin: 0; font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); }
.gt-e__attach-btn { font-size: 14px; }
.gt-e__conclusion { display: flex; flex-direction: column; gap: 12px; padding: 16px; border: 1px solid var(--el-border-color-light); border-radius: 6px; background: var(--el-color-primary-light-9); }
.gt-e__conclusion-group { display: flex; flex-direction: column; gap: 8px; }
.gt-e__conclusion-group :deep(.el-radio) { height: auto; padding: 10px 12px; margin-right: 0; align-items: flex-start; border: 1px solid transparent; border-radius: 4px; transition: background 0.15s, border-color 0.15s; }
.gt-e__conclusion-group :deep(.el-radio:hover) { background: var(--el-color-primary-light-8); }
.gt-e__conclusion-group :deep(.el-radio.is-checked) { background: var(--el-color-primary-light-8); border-color: var(--el-color-primary-light-5); }
.gt-e__conclusion-option.is-success :deep(.el-radio.is-checked), .gt-e__conclusion-option.is-success { --conclusion-accent: var(--el-color-success); }
.gt-e__conclusion-option.is-warning { --conclusion-accent: var(--el-color-warning); }
.gt-e__conclusion-option.is-danger { --conclusion-accent: var(--el-color-danger); }
.gt-e__conclusion-option.is-info { --conclusion-accent: var(--el-color-info); }
.gt-e__conclusion-label { display: flex; flex-direction: column; gap: 2px; }
.gt-e__conclusion-name { font-size: 14px; font-weight: 600; color: var(--el-text-color-primary); }
.gt-e__conclusion-desc { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.5; }
.gt-e__hints { margin-top: 8px; }
.gt-e__hint-items { margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.8; color: var(--el-text-color-regular); }
.gt-e__hint-items li { margin-bottom: 4px; }
.gt-e__hint-content { margin: 0; font-family: inherit; font-size: 13px; line-height: 1.7; color: var(--el-text-color-regular); white-space: pre-wrap; word-break: break-word; }
</style>
