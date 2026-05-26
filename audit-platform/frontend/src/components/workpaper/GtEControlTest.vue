<!--
  GtEControlTest.vue — E 类控制测试组件

  按 design §3.7 实现：
  - 3 种结构路由（test_type=summary | single | evaluation_step）
  - summary：dynamic_table 15 列 + 提示折叠 + per_row 缺陷派生
  - single：7 segments 顺序渲染 + 单一结论
  - evaluation_step：el-steps 6 步骤 stepper + 4 互斥结论 radio
  - 控制有效结论 → emit 'trigger-procedure-trimming-suggestion'
    → 上层写入 ProcedureTrimming 项目级建议
  - 风险说明长段折叠展开（el-collapse default-collapsed）

  锚定 spec workpaper-html-renderer Task 6.2
  Validates: Requirements 3.6（E 类 322 sheet）

  ─── cross-ref:updated 订阅契约（Task 13.2）──────────────────────────────────
  本组件**不直接订阅** eventBus 'cross-ref:updated' 事件。跨底稿引用变化由
  `useWpRenderer.ts`（GtWpRenderer 父组件持有）统一监听 + 重拉 renderConfig，
  本组件通过 props 接收最新 htmlData 自动更新（单一订阅入口避免内存泄漏）。
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
    <section v-if="testType === 'summary'" class="gt-e__summary">
      <div class="gt-e__toolbar">
        <h3 class="gt-e__title">控制测试汇总表</h3>
        <div v-if="!readonly" class="gt-e__toolbar-actions">
          <el-button size="small" :icon="PlusIcon" @click="handleAddSummaryRow">
            新增控制行
          </el-button>
        </div>
      </div>

      <el-table
        :data="summaryRows"
        border
        size="small"
        class="gt-e__summary-table"
        :row-class-name="summaryRowClass"
        empty-text="暂无控制项，点击「新增控制行」开始"
      >
        <el-table-column
          v-for="col in summaryColumns"
          :key="col.field"
          :label="col.label"
          :min-width="col.width"
          resizable
        >
          <template #default="{ row, $index }">
            <!-- enum 单选下拉 -->
            <el-select
              v-if="col.type === 'enum'"
              v-model="row[col.field]"
              :disabled="readonly"
              size="small"
              clearable
              :placeholder="col.label"
              @change="onSummaryFieldChange(row, col.field, $index)"
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
              @change="onSummaryFieldChange(row, col.field, $index)"
            >
              <el-option
                v-for="opt in col.enum || []"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>

            <!-- number -->
            <el-input-number
              v-else-if="col.type === 'number'"
              v-model="row[col.field]"
              :disabled="readonly"
              :min="col.min ?? 0"
              size="small"
              controls-position="right"
              @change="onSummaryFieldChange(row, col.field, $index)"
            />

            <!-- index_chip 渲染 -->
            <GtIndexChip
              v-else-if="col.render === 'index_chip' && row[col.field]"
              :value="row[col.field]"
              :validate="true"
            />

            <!-- text/textarea -->
            <el-input
              v-else
              v-model="row[col.field]"
              :disabled="readonly"
              size="small"
              :type="col.type === 'textarea' ? 'textarea' : 'text'"
              :rows="col.type === 'textarea' ? 2 : undefined"
              :maxlength="col.max_length"
              :placeholder="col.label"
              @input="onSummaryFieldChange(row, col.field, $index)"
            />
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!readonly" label="操作" width="80" fixed="right">
          <template #default="{ $index }">
            <el-button
              link
              type="danger"
              size="small"
              @click="handleRemoveSummaryRow($index)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- ───────── single 子模式：7 segments 顺序渲染 ───────── -->
    <section v-else-if="testType === 'single'" class="gt-e__single">
      <div
        v-for="seg in segments"
        :key="seg.id"
        class="gt-e__segment"
      >
        <h3 class="gt-e__segment-title">{{ seg.title }}</h3>
        <el-form
          :model="singleData"
          label-position="top"
          :disabled="readonly"
          class="gt-e__segment-form"
        >
          <el-form-item
            v-for="field in visibleSegmentFields(seg)"
            :key="field.name"
            :label="field.label"
            :required="!!field.required"
          >
            <FieldInput
              :field="field"
              :model-value="singleData[field.name]"
              :readonly="readonly"
              @update:model-value="(v: any) => { singleData[field.name] = v; onSingleFieldChange(field.name) }"
            />
            <div v-if="field.hint" class="gt-e__field-hint">
              <el-icon><InfoFilled /></el-icon>
              <span>{{ field.hint }}</span>
            </div>
          </el-form-item>
        </el-form>
      </div>
    </section>

    <!-- ───────── evaluation_step 子模式：6 步骤 stepper ───────── -->
    <section v-else-if="testType === 'evaluation_step'" class="gt-e__eval">
      <!-- el-steps stepper -->
      <el-steps
        :active="activeStepIdx"
        :process-status="stepProcessStatus"
        finish-status="success"
        align-center
        class="gt-e__stepper"
      >
        <el-step
          v-for="step in steps"
          :key="step.step"
          :title="`步骤${stepLabel(step.step)}`"
          :description="stepShortTitle(step)"
        />
      </el-steps>

      <!-- 当前步骤内容 -->
      <div v-if="currentStep" class="gt-e__step-content">
        <header class="gt-e__step-header">
          <h3 class="gt-e__step-title">{{ currentStep.title }}</h3>
          <p
            v-if="currentStep.description"
            class="gt-e__step-desc"
          >{{ currentStep.description }}</p>
        </header>

        <el-form
          :model="evalData"
          label-position="top"
          :disabled="readonly"
        >
          <el-form-item
            v-for="field in visibleStepFields(currentStep)"
            :key="field.name"
            :label="field.label"
            :required="!!field.required"
          >
            <FieldInput
              :field="field"
              :model-value="evalData[field.name]"
              :readonly="readonly"
              @update:model-value="(v: any) => { evalData[field.name] = v; onEvalFieldChange(field.name) }"
            />
            <div v-if="field.hint" class="gt-e__field-hint">
              <el-icon><InfoFilled /></el-icon>
              <span>{{ field.hint }}</span>
            </div>
          </el-form-item>
        </el-form>

        <!-- 步骤导航 -->
        <div class="gt-e__step-nav">
          <el-button
            :disabled="activeStepIdx === 0"
            @click="goToStep(activeStepIdx - 1)"
          >
            上一步
          </el-button>
          <el-button
            v-if="!isTerminalStep"
            type="primary"
            @click="advanceStep"
          >
            下一步
          </el-button>
          <el-tag v-else type="success" size="large">已到达终结步骤</el-tag>
        </div>
      </div>
    </section>

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
import { ref, computed, watch, onBeforeUnmount, defineComponent, h } from 'vue'
import {
  ElInput,
  ElInputNumber,
  ElSelect,
  ElOption,
} from 'element-plus'
import { Plus as PlusIcon, InfoFilled } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

type FieldType =
  | 'text'
  | 'textarea'
  | 'number'
  | 'enum'
  | 'multi_enum'
  | 'attachment_list'

interface FieldDef {
  name: string
  label: string
  type?: FieldType
  required?: boolean
  enum?: string[]
  cell?: string
  min?: number
  max?: number
  max_length?: number
  hint?: string
  conditional?: string
  render?: 'index_chip' | string
}

interface SegmentDef {
  id: string
  title: string
  start_row?: number
  end_row?: number | string
  fields: FieldDef[]
}

interface NextLogic {
  when?: string
  goto?: number
  reason?: string
  conclusion_hint?: string
}

interface StepDef {
  step: number
  id: string
  title: string
  description?: string
  fields: FieldDef[]
  next_logic?: NextLogic[]
  is_terminal?: boolean
}

interface HintItem {
  no: number
  content: string
}

interface HintBlock {
  id: string
  label: string
  collapsible?: boolean
  default_collapsed?: boolean
  type?: 'reference_table' | string
  items?: HintItem[]
  content?: string
  columns?: string[]
  rows?: any[][]
}

interface ConclusionOption {
  value: string
  label: string
  class?: 'success' | 'warning' | 'danger' | 'info'
  icon?: string
  description?: string
}

interface ConclusionBlock {
  mode?: 'single' | 'per_row'
  options?: ConclusionOption[]
  mutual_exclusive?: boolean
  cell?: string
  derived_from?: string
  auto_derive?: { rule: string; editable?: boolean }
}

interface DynamicTableColumnDef {
  field: string
  label: string
  type?: FieldType
  enum?: string[]
  min?: number
  max?: number
  max_length?: number
  pattern?: string
  render?: 'index_chip' | 'select_or_text' | string
  width?: number
}

interface DynamicTableSchema {
  start_row?: number
  end_row?: number | string
  header_row?: number
  columns: Record<string, DynamicTableColumnDef>
}

export interface EControlTestSchema {
  test_type?: 'summary' | 'single' | 'evaluation_step'
  fixed_cells?: Record<string, string>
  fields?: FieldDef[]               // evaluation_step 顶部上下文字段
  segments?: SegmentDef[]           // single 子模式
  steps?: StepDef[]                 // evaluation_step 子模式
  dynamic_table?: DynamicTableSchema  // summary 子模式
  hints?: HintBlock[]
  conclusion?: ConclusionBlock
  [key: string]: any
}

interface SummaryRow {
  id?: string
  conclusion?: string
  [key: string]: any
}

export interface EControlTestData {
  // summary 子模式
  rows?: SummaryRow[]
  // single + evaluation_step 共用
  fields?: Record<string, any>
  // evaluation_step：每步骤独立数据
  steps?: Record<string, Record<string, any>>
  // 终态结论
  conclusion?: string
  // 当前激活步骤
  active_step?: number
  // 折叠状态
  active_hint_ids?: string[]
  [key: string]: any
}

export interface SuggestionPayload {
  wp_id: string
  sheet_name: string
  conclusion: string
  suggestion_type: 'reduce' | 'increase' | 'full' | 'none'
  confidence: 'high' | 'medium' | 'low' | 'required'
  source: string
}

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
}>()

// ─── Refs（按 setup const 顺序铁律放最前） ────────────────────────────────────
const summaryRows = ref<SummaryRow[]>([])
const singleData = ref<Record<string, any>>({})
const evalData = ref<Record<string, any>>({})
const activeStepNo = ref<number>(1)
const conclusionValue = ref<string>('')
const activeHintIds = ref<string[]>([])

let saveTimer: ReturnType<typeof setTimeout> | null = null

// ─── Computed ────────────────────────────────────────────────────────────────

const testType = computed(() => props.schema?.test_type ?? 'single')

const segments = computed<SegmentDef[]>(() => props.schema?.segments ?? [])

const steps = computed<StepDef[]>(() => {
  const arr = props.schema?.steps ?? []
  return [...arr].sort((a, b) => (a.step ?? 0) - (b.step ?? 0))
})

const hints = computed<HintBlock[]>(() => props.schema?.hints ?? [])

const conclusionBlock = computed<ConclusionBlock | null>(() => props.schema?.conclusion ?? null)

const conclusionOptions = computed<ConclusionOption[]>(() => conclusionBlock.value?.options ?? [])

const hasConclusion = computed(() =>
  testType.value !== 'summary' && conclusionOptions.value.length > 0
)

const summaryColumns = computed<DynamicTableColumnDef[]>(() => {
  const cols = props.schema?.dynamic_table?.columns ?? {}
  return Object.entries(cols).map(([_cellLetter, def]) => {
    const colDef = def as DynamicTableColumnDef
    const width = colDef.type === 'textarea' ? 200 : 120
    return {
      ...colDef,
      width,
    }
  })
})

const fixedCells = computed(() => props.schema?.fixed_cells ?? {})

const entityName = computed(() => fixedCells.value.A3 || '')
const periodEnd = computed(() => fixedCells.value.A4 || '')
const indexNo = computed(() =>
  fixedCells.value.O3 || fixedCells.value.J3 || fixedCells.value.I3 || ''
)
const hasHeaderInfo = computed(() =>
  !!(entityName.value || periodEnd.value || indexNo.value)
)

const currentStep = computed<StepDef | null>(() => {
  return steps.value.find(s => s.step === activeStepNo.value) ?? null
})

const activeStepIdx = computed(() => {
  const idx = steps.value.findIndex(s => s.step === activeStepNo.value)
  return idx >= 0 ? idx : 0
})

const isTerminalStep = computed(() => !!currentStep.value?.is_terminal)

const stepProcessStatus = computed<'wait' | 'process' | 'finish' | 'error' | 'success'>(() => {
  if (isTerminalStep.value && conclusionValue.value) return 'success'
  return 'process'
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全 evaluate：仅支持 schema 中 `field == 'value'` / `field in [...]` / `field > N` /
 * `field == 0` 等简单条件。无法解析时返回 true（不隐藏字段，宁可多显示）。
 */
function safeEvaluate(expression: string, ctx: Record<string, any>): boolean {
  if (!expression || typeof expression !== 'string') return true
  const expr = expression.trim()
  if (expr === 'true') return true
  if (expr === 'false') return false

  // field == 'value' / field === "value"
  let m = expr.match(/^(\w+)\s*===?\s*['"](.+?)['"]$/)
  if (m) return ctx[m[1]] === m[2]

  // field != 'value'
  m = expr.match(/^(\w+)\s*!==?\s*['"](.+?)['"]$/)
  if (m) return ctx[m[1]] !== m[2]

  // field == number
  m = expr.match(/^(\w+)\s*===?\s*(\d+(?:\.\d+)?)$/)
  if (m) return Number(ctx[m[1]]) === Number(m[2])

  // field > N / field >= N / field < N / field <= N
  m = expr.match(/^(\w+)\s*(>=|<=|>|<)\s*(\d+(?:\.\d+)?)$/)
  if (m) {
    const v = Number(ctx[m[1]])
    const target = Number(m[3])
    if (Number.isNaN(v)) return false
    switch (m[2]) {
      case '>': return v > target
      case '>=': return v >= target
      case '<': return v < target
      case '<=': return v <= target
    }
  }

  // field in ['a', 'b']
  m = expr.match(/^(\w+)\s+in\s+\[(.+)\]$/)
  if (m) {
    const list = m[2].split(',').map(s => s.trim().replace(/^['"]|['"]$/g, ''))
    return list.includes(String(ctx[m[1]] ?? ''))
  }

  // 默认：无法解析 → 不隐藏（保守）
  return true
}

const stepLabelMap: Record<number, string> = {
  1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六',
  7: '七', 8: '八', 9: '九', 10: '十',
}

function stepLabel(no: number): string {
  return stepLabelMap[no] ?? String(no)
}

function stepShortTitle(step: StepDef): string {
  const title = step.title || ''
  // 移除"步骤一："等前缀，保留主题
  return title.replace(/^步骤[一二三四五六七八九十\d]+[：:]\s*/, '')
}

function visibleSegmentFields(seg: SegmentDef): FieldDef[] {
  return (seg.fields || []).filter(f => {
    if (!f.conditional) return true
    return safeEvaluate(f.conditional, singleData.value)
  })
}

function visibleStepFields(step: StepDef | null): FieldDef[] {
  if (!step) return []
  return (step.fields || []).filter(f => {
    if (!f.conditional) return true
    return safeEvaluate(f.conditional, evalData.value)
  })
}

function renderFieldInput(field: FieldDef): any {
  // Kept for backward compatibility / external use; FieldInput component is preferred
  switch (field.type) {
    case 'enum':
    case 'multi_enum':
      return ElSelect
    case 'number':
      return ElInputNumber
    case 'attachment_list':
      return ElInput
    case 'textarea':
    case 'text':
    default:
      return ElInput
  }
}
void renderFieldInput

/**
 * FieldInput — 内联渲染组件，根据 field.type 选择合适的输入控件
 * 解决 <component :is="ElSelect"> 无法注入子节点 <el-option> 的限制
 */
const FieldInput = defineComponent({
  name: 'FieldInput',
  props: {
    field: { type: Object as () => FieldDef, required: true },
    modelValue: { type: null, default: undefined },
    readonly: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  setup(p, { emit: localEmit }) {
    return () => {
      const f = p.field
      const onUpdate = (v: any) => localEmit('update:modelValue', v)
      const common: Record<string, any> = {
        modelValue: p.modelValue,
        'onUpdate:modelValue': onUpdate,
        disabled: p.readonly,
        size: 'default',
        placeholder: f.label,
      }

      if (f.type === 'enum') {
        return h(
          ElSelect,
          { ...common, clearable: true },
          {
            default: () => (f.enum || []).map(opt =>
              h(ElOption, { key: opt, label: opt, value: opt })
            ),
          }
        )
      }

      if (f.type === 'multi_enum') {
        return h(
          ElSelect,
          {
            ...common,
            multiple: true,
            collapseTags: true,
            collapseTagsTooltip: true,
            modelValue: Array.isArray(p.modelValue) ? p.modelValue : [],
          },
          {
            default: () => (f.enum || []).map(opt =>
              h(ElOption, { key: opt, label: opt, value: opt })
            ),
          }
        )
      }

      if (f.type === 'number') {
        return h(ElInputNumber, {
          ...common,
          min: f.min ?? 0,
          max: f.max,
          controlsPosition: 'right',
        })
      }

      if (f.type === 'textarea') {
        return h(ElInput, {
          ...common,
          type: 'textarea',
          rows: 3,
          maxlength: f.max_length,
          showWordLimit: !!f.max_length,
        })
      }

      if (f.type === 'attachment_list') {
        return h(ElInput, {
          ...common,
          type: 'textarea',
          rows: 2,
          placeholder: '附件列表（暂以文本占位）',
        })
      }

      // text 默认
      return h(ElInput, {
        ...common,
        type: 'text',
        clearable: true,
        maxlength: f.max_length,
        showWordLimit: !!f.max_length,
      })
    }
  },
})

function summaryRowClass(payload: { row: SummaryRow }): string {
  if (payload.row?.deficiency === '重大缺陷') return 'gt-e__summary-row--danger'
  if (payload.row?.deficiency === '控制缺陷') return 'gt-e__summary-row--warning'
  return ''
}

function hintTableRows(hint: HintBlock): Array<Record<string, string | number>> {
  if (!hint.rows) return []
  return hint.rows.map(r => {
    const obj: Record<string, string | number> = {}
    r.forEach((cell, i) => { obj[`c${i}`] = cell })
    return obj
  })
}

// ─── 步骤导航逻辑 ─────────────────────────────────────────────────────────────

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

  // 若 next_logic 提示了 conclusion_hint，自动派生但允许覆盖（参照 schema 注释）
  if (next?.conclusion_hint && !conclusionValue.value) {
    conclusionValue.value = next.conclusion_hint
  }

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

// ─── Summary 子模式：动态行 ──────────────────────────────────────────────────

function buildEmptySummaryRow(): SummaryRow {
  const row: SummaryRow = {
    id: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  }
  for (const col of summaryColumns.value) {
    row[col.field] = col.type === 'multi_enum' ? [] : (col.type === 'number' ? 0 : '')
  }
  return row
}

function handleAddSummaryRow() {
  summaryRows.value.push(buildEmptySummaryRow())
  debounceSave()
}

function handleRemoveSummaryRow(idx: number) {
  summaryRows.value.splice(idx, 1)
  debounceSave()
}

function onSummaryFieldChange(_row: SummaryRow, _field: string, _idx: number) {
  debounceSave()
}

// ─── 字段变更 ────────────────────────────────────────────────────────────────

function onSingleFieldChange(_name: string) {
  debounceSave()
}

function onEvalFieldChange(name: string) {
  // 当步骤六的 final_conclusion 字段变化时，同步到 conclusionValue
  if (currentStep.value?.is_terminal && (name === 'final_conclusion' || name === currentStep.value.fields.find(f => f.required && f.type === 'enum')?.name)) {
    conclusionValue.value = String(evalData.value[name] ?? '')
    onConclusionChange(conclusionValue.value)
  }
  debounceSave()
}

// ─── 结论变更 → emit + ProcedureTrimming 建议 ─────────────────────────────────

function deriveSuggestion(conclusion: string): SuggestionPayload['suggestion_type'] {
  if (conclusion === 'control_effective' || conclusion === 'extended_effective' || conclusion === 'effective') {
    return 'reduce'
  }
  if (conclusion === 'deviation_remains' || conclusion === 'ineffective') {
    return 'increase'
  }
  if (conclusion === 'systemic_deviation') {
    return 'full'
  }
  return 'none'
}

function deriveConfidence(conclusion: string): SuggestionPayload['confidence'] {
  if (conclusion === 'systemic_deviation') return 'required'
  if (conclusion === 'control_effective' || conclusion === 'extended_effective') return 'high'
  if (conclusion === 'deviation_remains') return 'high'
  return 'medium'
}

function onConclusionChange(value: string | number | boolean | undefined) {
  const conclusion = String(value ?? '')
  conclusionValue.value = conclusion
  emit('conclusion-change', conclusion)

  // 控制有效 / 扩大有效 / 仍有偏差 / 系统性偏差 全部触发 ProcedureTrimming 建议
  // （差异由 suggestion_type + confidence 体现）
  const suggestion_type = deriveSuggestion(conclusion)
  if (suggestion_type !== 'none') {
    const payload: SuggestionPayload = {
      wp_id: props.wpId,
      sheet_name: props.sheetName,
      conclusion,
      suggestion_type,
      confidence: deriveConfidence(conclusion),
      source: 'e-control-test',
    }
    emit('trigger-procedure-trimming-suggestion', payload)
  }

  // 同步回 evalData 的 final_conclusion 字段（双向）
  if (testType.value === 'evaluation_step') {
    evalData.value.final_conclusion = conclusion
  } else if (testType.value === 'single') {
    singleData.value.conclusion = conclusion
  }
  debounceSave()
}

// ─── 数据初始化 / 同步 ───────────────────────────────────────────────────────

function initData() {
  const data = props.htmlData ?? {}

  // summary
  summaryRows.value = Array.isArray(data.rows) ? JSON.parse(JSON.stringify(data.rows)) : []

  // single + evaluation_step：fields 块
  const fieldsData: Record<string, any> = data.fields && typeof data.fields === 'object'
    ? { ...data.fields }
    : {}
  singleData.value = { ...fieldsData }

  // evaluation_step：合并 steps[*] 数据 + fields（顶部上下文）到统一表单
  const stepsData = data.steps && typeof data.steps === 'object' ? data.steps : {}
  const merged: Record<string, any> = { ...fieldsData }
  for (const stepKey of Object.keys(stepsData)) {
    const stepFields = stepsData[stepKey]
    if (stepFields && typeof stepFields === 'object') {
      Object.assign(merged, stepFields)
    }
  }
  evalData.value = merged

  // 激活步骤
  activeStepNo.value = typeof data.active_step === 'number'
    ? data.active_step
    : (steps.value[0]?.step ?? 1)

  // 结论
  conclusionValue.value = typeof data.conclusion === 'string' ? data.conclusion : ''

  // 折叠展开：默认全部折叠（default_collapsed: true）
  // 仅展开 active_hint_ids 中明确指定的项；schema 中 default_collapsed=false 的也展开
  const activeIds = new Set<string>(
    Array.isArray(data.active_hint_ids) ? data.active_hint_ids : []
  )
  for (const h of hints.value) {
    if (h.default_collapsed === false) activeIds.add(h.id)
  }
  activeHintIds.value = Array.from(activeIds)
}

initData()

watch(() => props.htmlData, () => {
  initData()
}, { deep: true })

watch(() => props.schema, () => {
  // schema 变化（test_type 切换）时重置激活步骤
  activeStepNo.value = steps.value[0]?.step ?? 1
}, { deep: true })

// ─── debounce save ───────────────────────────────────────────────────────────

function buildSavePayload(): EControlTestData {
  const payload: EControlTestData = {
    active_step: activeStepNo.value,
    active_hint_ids: [...activeHintIds.value],
    conclusion: conclusionValue.value,
  }

  if (testType.value === 'summary') {
    payload.rows = JSON.parse(JSON.stringify(summaryRows.value))
  } else if (testType.value === 'single') {
    payload.fields = JSON.parse(JSON.stringify(singleData.value))
  } else if (testType.value === 'evaluation_step') {
    // 拆分顶部 fields 与 step-specific fields
    const stepsBucket: Record<string, Record<string, any>> = {}
    const topFieldNames = new Set((props.schema.fields ?? []).map(f => f.name))
    const topFields: Record<string, any> = {}
    const allEval = JSON.parse(JSON.stringify(evalData.value))

    for (const step of steps.value) {
      stepsBucket[String(step.step)] = {}
      for (const f of (step.fields || [])) {
        if (f.name in allEval) {
          stepsBucket[String(step.step)][f.name] = allEval[f.name]
        }
      }
    }
    for (const name of Object.keys(allEval)) {
      if (topFieldNames.has(name)) {
        topFields[name] = allEval[name]
      }
    }
    payload.fields = topFields
    payload.steps = stepsBucket
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
</script>

<style scoped>
.gt-e-control-test {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* ── 头部 ── */
.gt-e__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px 16px;
  background: var(--gt-color-bg-soft, #f5f7fa);
  border-radius: 6px;
  font-size: 13px;
}
.gt-e__header-meta {
  display: flex;
  align-items: center;
  gap: 16px;
}
.gt-e__entity {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-e__period {
  color: var(--el-text-color-regular);
}
.gt-e__index {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.gt-e__index strong {
  color: var(--el-color-primary);
  margin-left: 4px;
}

/* ── 通用标题 / 工具栏 ── */
.gt-e__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-e__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.gt-e__toolbar-actions {
  display: flex;
  gap: 8px;
}

/* ── summary 子模式 ── */
.gt-e__summary {
  display: flex;
  flex-direction: column;
}
.gt-e__summary-table :deep(.gt-e__summary-row--warning) {
  background: var(--el-color-warning-light-9);
}
.gt-e__summary-table :deep(.gt-e__summary-row--danger) {
  background: var(--el-color-danger-light-9);
}

/* ── single 子模式 ── */
.gt-e__single {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.gt-e__segment {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 16px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-e__segment-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-color-primary);
  border-left: 3px solid var(--el-color-primary);
  padding-left: 8px;
}
.gt-e__segment-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px 16px;
}

/* ── evaluation_step 子模式 ── */
.gt-e__eval {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.gt-e__stepper {
  padding: 8px 0 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.gt-e__step-content {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 16px 20px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-e__step-header {
  margin-bottom: 16px;
}
.gt-e__step-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
  color: var(--el-color-primary);
}
.gt-e__step-desc {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
  white-space: pre-line;
}
.gt-e__step-nav {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.gt-e__field-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-e__field-hint .el-icon {
  color: var(--el-color-info);
}

/* ── 结论区 ── */
.gt-e__conclusion {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--el-color-primary-light-9);
}
.gt-e__conclusion-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.gt-e__conclusion-group :deep(.el-radio) {
  height: auto;
  padding: 10px 12px;
  margin-right: 0;
  align-items: flex-start;
  border: 1px solid transparent;
  border-radius: 4px;
  transition: background 0.15s, border-color 0.15s;
}
.gt-e__conclusion-group :deep(.el-radio:hover) {
  background: var(--el-color-primary-light-8);
}
.gt-e__conclusion-group :deep(.el-radio.is-checked) {
  background: var(--el-color-primary-light-8);
  border-color: var(--el-color-primary-light-5);
}
.gt-e__conclusion-option.is-success :deep(.el-radio.is-checked),
.gt-e__conclusion-option.is-success {
  --conclusion-accent: var(--el-color-success);
}
.gt-e__conclusion-option.is-warning {
  --conclusion-accent: var(--el-color-warning);
}
.gt-e__conclusion-option.is-danger {
  --conclusion-accent: var(--el-color-danger);
}
.gt-e__conclusion-option.is-info {
  --conclusion-accent: var(--el-color-info);
}
.gt-e__conclusion-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.gt-e__conclusion-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-e__conclusion-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}

/* ── 提示区折叠 ── */
.gt-e__hints {
  margin-top: 8px;
}
.gt-e__hint-items {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--el-text-color-regular);
}
.gt-e__hint-items li {
  margin-bottom: 4px;
}
.gt-e__hint-content {
  margin: 0;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
