<!--
  GtDFormQA.vue — D 类是否问答型子组件（实现版）

  适用范围：~9 sheet（4 判断题 × N 组合 → 业务模式 → 计量分类 → 报表项目）
  样本 schema：D-D2-13.yaml（应收账款业务模式分析）

  核心交互：
  - qa_matrix 渲染为表格：
      行 = N 个问题（q1, q2, ...，包含 question + help_text tooltip）
      列 = N 个组合（动态增删，max_combinations 上限默认 10）
      单元格 = el-radio-group {是 / 否 / 不适用}
      底部 readonly 行 = business_model / measurement_class / report_line（el-tag）
  - auto_derivation 规则引擎：
      支持 q1=='是' / q2!='否' / has_empty
      支持 AND / OR 复合表达式
      首条匹配规则 wins，未匹配 fallback 到 rule_default_pending
      派生 business_model / measurement_class / report_line / confidence
  - notes[] 折叠区（el-collapse default-collapsed）
  - debounced auto-save 1.5s emit 'save' 整体 payload
  - 字段变更 emit 'field-change' { field_name: 'combinations[i].q1_answer', new_value: '是' }

  锚定 spec workpaper-html-renderer Task 8.5
  Validates: Requirements 3.5（D 子模式 3：是否问答型业务模式判定）

  cross-ref:updated 订阅由 `useWpRenderer.ts` 集中处理（Task 13.2），本组件不直接订阅。
-->

<template>
  <div class="gt-d-form-qa">
    <!-- ─── 顶部头部信息 ─── -->
    <header v-if="hasHeaderInfo" class="gt-dfq__header">
      <div class="gt-dfq__header-meta">
        <span v-if="entityName" class="gt-dfq__entity">{{ entityName }}</span>
        <span v-if="periodEnd" class="gt-dfq__period">{{ periodEnd }}</span>
      </div>
      <div v-if="indexNo" class="gt-dfq__index">
        索引号：<strong>{{ indexNo }}</strong>
      </div>
    </header>

    <!-- ─── 上下文字段区 ─── -->
    <section v-if="contextFields.length" class="gt-dfq__context">
      <el-form
        :model="contextData"
        label-position="top"
        :disabled="readonly"
        class="gt-dfq__context-form"
      >
        <el-form-item
          v-for="field in contextFields"
          :key="field.name"
          :label="field.label"
          :required="!!field.required"
          class="gt-dfq__context-item"
        >
          <div v-if="field.type === 'textarea'" class="gt-dfq__input-wrapper">
            <div class="gt-ai-suggest-trigger" v-if="aiEnabled && !readonly && !field.readonly">
              <el-button text size="small" :loading="aiLoading" @click="onAiSuggestContext(field.name)">🤖 AI 建议</el-button>
            </div>
            <el-input
              v-model="contextData[field.name]"
              type="textarea"
              :rows="3"
              :readonly="!!field.readonly"
              :maxlength="field.max_length"
              :show-word-limit="!!field.max_length"
              :placeholder="field.hint || field.label"
              @change="onContextFieldChange(field.name)"
            />
            <!-- AI 建议面板 -->
            <div v-if="showSuggestionPanel && currentSuggestion?.fieldName === ('context.' + field.name)" class="gt-dfq__ai-panel">
              <div class="gt-dfq__ai-panel-header">
                <span class="gt-dfq__ai-panel-title">🤖 AI 建议</span>
                <el-tag size="small" :type="currentSuggestion.confidence >= 0.7 ? 'success' : 'warning'">
                  置信度 {{ Math.round(currentSuggestion.confidence * 100) }}%
                </el-tag>
              </div>
              <pre class="gt-dfq__ai-panel-text">{{ currentSuggestion.text }}</pre>
              <div class="gt-dfq__ai-panel-actions">
                <el-button type="primary" size="small" @click="handleAdoptContext(field.name)">✅ 采纳</el-button>
                <el-button size="small" @click="handleModifyContext(field.name)">✏️ 修改后采纳</el-button>
                <el-button size="small" @click="handleIgnoreQa">❌ 忽略</el-button>
              </div>
            </div>
          </div>
          <el-input
            v-else
            v-model="contextData[field.name]"
            :readonly="!!field.readonly"
            :maxlength="field.max_length"
            :show-word-limit="!!field.max_length"
            :placeholder="field.hint || field.label"
            @change="onContextFieldChange(field.name)"
          />
          <div v-if="field.hint && !field.readonly" class="gt-dfq__field-hint">
            <el-icon><InfoFilled /></el-icon>
            <span>{{ field.hint }}</span>
          </div>
        </el-form-item>
      </el-form>
    </section>

    <!-- ─── 问答矩阵工具栏 ─── -->
    <div class="gt-dfq__toolbar">
      <h3 class="gt-dfq__title">业务模式判定矩阵</h3>
      <div v-if="!readonly" class="gt-dfq__toolbar-actions">
        <el-tooltip
          :content="`已添加 ${combinations.length} / ${maxCombinations} 个组合`"
          placement="top"
        >
          <el-button
            size="small"
            :icon="PlusIcon"
            :disabled="reachedMaxCombinations"
            @click="handleAddCombination"
          >添加组合</el-button>
        </el-tooltip>
        <el-button
          size="small"
          :icon="DeleteIcon"
          :disabled="combinations.length === 0"
          @click="handleRemoveLastCombination"
        >删除末位</el-button>
      </div>
    </div>

    <!-- ─── 问答矩阵（手写 table，避免 el-table 单元格 radio 渲染冲突） ─── -->
    <div class="gt-dfq__matrix-wrap">
      <table class="gt-dfq__matrix" v-if="combinations.length > 0">
        <colgroup>
          <col class="gt-dfq__col-label" />
          <col v-for="(_c, idx) in combinations" :key="`col-${idx}`" class="gt-dfq__col-comb" />
        </colgroup>

        <!-- 表头：组合名称 -->
        <thead>
          <tr>
            <th class="gt-dfq__th-label">问题 / 组合</th>
            <th
              v-for="(comb, idx) in combinations"
              :key="`head-${idx}`"
              class="gt-dfq__th-comb"
            >
              <div class="gt-dfq__comb-head">
                <span class="gt-dfq__comb-no">组合 {{ idx + 1 }}</span>
                <el-input
                  v-model="comb.combination_name"
                  :disabled="readonly"
                  size="small"
                  placeholder="组合名称（如：标准应收）"
                  :maxlength="combinationNameMaxLength"
                  @change="onCombinationNameChange(idx)"
                />
                <el-button
                  v-if="!readonly"
                  link
                  type="danger"
                  size="small"
                  @click="handleRemoveCombination(idx)"
                >删除</el-button>
              </div>
            </th>
          </tr>
        </thead>

        <!-- 4 个问题行 -->
        <tbody>
          <tr v-for="q in questions" :key="q.id" class="gt-dfq__row-question">
            <th class="gt-dfq__th-question">
              <div class="gt-dfq__q-head">
                <span class="gt-dfq__q-seq">{{ q.seq || q.id }}</span>
                <span class="gt-dfq__q-text">{{ q.question }}</span>
                <el-tooltip
                  v-if="q.help_text"
                  placement="right"
                  :show-after="200"
                  popper-class="gt-dfq__help-popper"
                >
                  <template #content>
                    <pre class="gt-dfq__help-text">{{ q.help_text }}</pre>
                  </template>
                  <el-icon class="gt-dfq__q-help"><QuestionFilledIcon /></el-icon>
                </el-tooltip>
              </div>
            </th>
            <td
              v-for="(comb, idx) in combinations"
              :key="`${q.id}-${idx}`"
              class="gt-dfq__td-radio"
            >
              <el-radio-group
                v-model="comb[`${q.id}_answer`]"
                :disabled="readonly"
                size="small"
                class="gt-dfq__radio-group"
                @change="onAnswerChange(idx, q.id)"
              >
                <el-radio v-for="opt in answerOptions" :key="opt" :value="opt">
                  {{ opt }}
                </el-radio>
              </el-radio-group>
            </td>
          </tr>

          <!-- ─── 自动判定行（business_model / measurement_class / report_line） ─── -->
          <tr class="gt-dfq__row-derived gt-dfq__row-derived--first">
            <th class="gt-dfq__th-derived">业务模式判定</th>
            <td
              v-for="(comb, idx) in combinations"
              :key="`bm-${idx}`"
              class="gt-dfq__td-derived"
            >
              <el-tag
                v-if="derivations[idx]?.business_model"
                :type="confidenceTagType(derivations[idx]?.confidence)"
                effect="light"
                size="small"
                class="gt-dfq__derived-tag"
              >{{ derivations[idx].business_model }}</el-tag>
              <span v-else class="gt-dfq__derived-empty">—</span>
            </td>
          </tr>
          <tr class="gt-dfq__row-derived">
            <th class="gt-dfq__th-derived">计量分类</th>
            <td
              v-for="(_comb, idx) in combinations"
              :key="`mc-${idx}`"
              class="gt-dfq__td-derived"
            >
              <el-tag
                v-if="derivations[idx]?.measurement_class && derivations[idx].measurement_class !== '—'"
                :type="confidenceTagType(derivations[idx]?.confidence)"
                effect="plain"
                size="small"
                class="gt-dfq__derived-tag"
              >{{ derivations[idx].measurement_class }}</el-tag>
              <span v-else class="gt-dfq__derived-empty">—</span>
            </td>
          </tr>
          <tr class="gt-dfq__row-derived">
            <th class="gt-dfq__th-derived">报表项目判定</th>
            <td
              v-for="(_comb, idx) in combinations"
              :key="`rl-${idx}`"
              class="gt-dfq__td-derived"
            >
              <el-tag
                v-if="derivations[idx]?.report_line && derivations[idx].report_line !== '—'"
                :type="confidenceTagType(derivations[idx]?.confidence)"
                effect="dark"
                size="small"
                class="gt-dfq__derived-tag"
              >{{ derivations[idx].report_line }}</el-tag>
              <span v-else class="gt-dfq__derived-empty">—</span>
            </td>
          </tr>
          <tr class="gt-dfq__row-derived gt-dfq__row-derived--last">
            <th class="gt-dfq__th-derived">置信度</th>
            <td
              v-for="(_comb, idx) in combinations"
              :key="`cf-${idx}`"
              class="gt-dfq__td-derived"
            >
              <el-tag
                :type="confidenceTagType(derivations[idx]?.confidence)"
                effect="plain"
                size="small"
              >{{ confidenceLabel(derivations[idx]?.confidence) }}</el-tag>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 空态 -->
      <el-empty
        v-else
        :image-size="80"
        description="暂无组合，点击「添加组合」开始填写"
      />
    </div>

    <!-- ─── 注释长段（折叠展开） ─── -->
    <section v-if="notes.length" class="gt-dfq__notes">
      <h3 class="gt-dfq__title">参考说明</h3>
      <el-collapse v-model="activeNoteIds">
        <el-collapse-item
          v-for="note in notes"
          :key="note.id"
          :name="note.id"
          :title="note.label"
        >
          <pre class="gt-dfq__note-content">{{ note.content }}</pre>
        </el-collapse-item>
      </el-collapse>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import {
  InfoFilled,
  QuestionFilled as QuestionFilledIcon,
  Plus as PlusIcon,
  Delete as DeleteIcon,
} from '@element-plus/icons-vue'
import { useWpAiSuggest } from '@/composables/useWpAiSuggest'
import type { DFormSchema, DFormData, FieldChangePayload } from './GtDForm.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

type AnswerValue = '是' | '否' | '不适用' | ''

interface QuestionDef {
  id: string                               // q1, q2, ...
  seq?: string                             // '题 1' 等
  question: string
  help_text?: string
  row?: number
}

interface CombinationColumnDef {
  combination_name?: { max_length?: number; required?: boolean }
  [key: string]: any                       // q1_answer / business_model / etc.
}

interface QaMatrixSchema {
  mode?: string
  questions?: QuestionDef[]
  combinations?: {
    start_col?: string
    end_col?: string
    max_combinations?: number
    column_def?: CombinationColumnDef
  }
}

interface DerivationRule {
  id: string
  when: string
  set: {
    business_model?: string
    measurement_class?: string
    report_line?: string
    confidence?: 'high' | 'medium' | 'low' | 'pending'
  }
}

interface AutoDerivationSchema {
  description?: string
  rules?: DerivationRule[]
}

interface NoteBlock {
  id: string
  label: string
  collapsible?: boolean
  default_collapsed?: boolean
  content?: string
}

interface ContextField {
  name: string
  label: string
  type?: 'text' | 'textarea'
  cell?: string
  max_length?: number
  required?: boolean
  readonly?: boolean
  hint?: string
  default?: string
}

interface CombinationRow {
  combination_name: string
  business_model?: string
  measurement_class?: string
  report_line?: string
  confidence?: 'high' | 'medium' | 'low' | 'pending'
  /** dynamic answer keys: q1_answer / q2_answer / ... */
  [key: string]: any
}

interface DerivationResult {
  rule_id: string
  business_model: string
  measurement_class: string
  report_line: string
  confidence: 'high' | 'medium' | 'low' | 'pending'
}

interface QaFormData extends DFormData {
  context?: Record<string, any>
  combinations?: CombinationRow[]
  active_note_ids?: string[]
}

const ANSWER_OPTIONS: AnswerValue[] = ['是', '否', '不适用']

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
const combinations = ref<CombinationRow[]>([])
const activeNoteIds = ref<string[]>([])

let saveTimer: ReturnType<typeof setTimeout> | null = null

// ─── AI 辅助填写（US-5 Task 7.1/7.3/7.4） ───────────────────────────────────

const {
  aiEnabled,
  aiLoading,
  currentSuggestion,
  showSuggestionPanel,
  assistedFieldsList,
  requestSuggestion,
  adoptSuggestion,
  modifySuggestion,
  ignoreSuggestion,
} = useWpAiSuggest({ wpId: props.wpId, sheetName: props.sheetName })

function onAiSuggestContext(fieldName: string) {
  const existingContent = contextData.value[fieldName] || ''
  requestSuggestion('context.' + fieldName, existingContent)
}

function handleAdoptContext(fieldName: string) {
  const text = adoptSuggestion()
  if (text) {
    contextData.value[fieldName] = text
    debounceSave()
  }
}

function handleModifyContext(fieldName: string) {
  if (currentSuggestion.value) {
    contextData.value[fieldName] = currentSuggestion.value.text
    modifySuggestion(currentSuggestion.value.text)
    debounceSave()
  }
}

function handleIgnoreQa() {
  ignoreSuggestion()
}

// ─── Static ──────────────────────────────────────────────────────────────────

const answerOptions = ANSWER_OPTIONS

// ─── Computed: schema slices ─────────────────────────────────────────────────

const fixedCells = computed(() => (props.schema as any)?.fixed_cells ?? {})

const entityName = computed(() => fixedCells.value?.A3 || '')
const periodEnd = computed(() => fixedCells.value?.A4 || '')
const indexNo = computed(
  () => fixedCells.value?.E3 || fixedCells.value?.O3 || fixedCells.value?.J3 || ''
)
const hasHeaderInfo = computed(
  () => !!(entityName.value || periodEnd.value || indexNo.value)
)

const contextFields = computed<ContextField[]>(() => {
  const arr = (props.schema as any)?.fields
  return Array.isArray(arr) ? (arr as ContextField[]) : []
})

const qaMatrix = computed<QaMatrixSchema>(
  () => (props.schema as any)?.qa_matrix ?? {}
)

const questions = computed<QuestionDef[]>(() => {
  const qs = qaMatrix.value?.questions
  return Array.isArray(qs) ? qs : []
})

const maxCombinations = computed(
  () => qaMatrix.value?.combinations?.max_combinations ?? 10
)

const reachedMaxCombinations = computed(
  () => combinations.value.length >= maxCombinations.value
)

const combinationNameMaxLength = computed(
  () => qaMatrix.value?.combinations?.column_def?.combination_name?.max_length ?? 100
)

const autoDerivation = computed<AutoDerivationSchema>(
  () => (props.schema as any)?.auto_derivation ?? {}
)

const derivationRules = computed<DerivationRule[]>(() => {
  const rules = autoDerivation.value?.rules
  return Array.isArray(rules) ? rules : []
})

const notes = computed<NoteBlock[]>(() => {
  const arr = (props.schema as any)?.notes
  return Array.isArray(arr) ? (arr as NoteBlock[]) : []
})

// ─── Computed: derivations per combination ───────────────────────────────────

const derivations = computed<DerivationResult[]>(() => {
  return combinations.value.map(comb => deriveFromCombination(comb))
})

// ─── Helpers: build rows / context ───────────────────────────────────────────

function buildEmptyCombination(): CombinationRow {
  const row: CombinationRow = {
    combination_name: '',
  }
  for (const q of questions.value) {
    row[`${q.id}_answer`] = ''
  }
  return row
}

function ensureCombinationShape(input: any): CombinationRow {
  const row: CombinationRow = {
    combination_name: typeof input?.combination_name === 'string' ? input.combination_name : '',
  }
  for (const q of questions.value) {
    const key = `${q.id}_answer`
    const v = input?.[key]
    row[key] = ANSWER_OPTIONS.includes(v) ? v : ''
  }
  return row
}

// ─── Auto-derivation engine ──────────────────────────────────────────────────

/**
 * Parse a single comparison: q1=='是' / q2!='否' / q3==是 (no quote)
 * Returns true / false; on parse failure returns null.
 */
function evaluateComparison(expr: string, ctx: Record<string, any>): boolean | null {
  const trimmed = expr.trim()
  if (!trimmed) return null

  // has_empty: any question answer is empty string
  if (trimmed === 'has_empty') {
    return Object.values(ctx).some(v => v === '' || v === null || v === undefined)
  }

  // boolean literals
  if (trimmed === 'true') return true
  if (trimmed === 'false') return false

  // <field> == 'value'  /  <field> != 'value'  (single or double quotes; quotes optional)
  // also accept full-width quotes 「」 from Chinese input but normalize first
  const normalized = trimmed.replace(/[‘’]/g, "'").replace(/[“”]/g, '"')

  let m = normalized.match(/^(\w+)\s*(==|!=|===|!==)\s*['"]?(.+?)['"]?$/)
  if (m) {
    const fieldName = m[1]
    const op = m[2]
    const target = m[3].trim()
    const actual = ctx[fieldName]
    const isEqual = String(actual ?? '') === target
    if (op === '==' || op === '===') return isEqual
    if (op === '!=' || op === '!==') return !isEqual
  }

  return null
}

/**
 * Tokenize and evaluate a `when` expression supporting AND / OR (no NOT, no nesting beyond parens).
 * Examples:
 *   "q1=='是' AND q2=='是' AND q3=='否'"
 *   "q1=='否' OR (q3=='是' AND q4=='否')"
 *   "q2=='否'"
 *   "q1=='不适用' OR q2=='不适用' OR has_empty"
 *
 * Strategy: parse parenthesized groups recursively, then split by OR (top precedence) → AND.
 */
function evaluateWhenExpression(expression: string, ctx: Record<string, any>): boolean {
  if (!expression || typeof expression !== 'string') return false
  const expr = expression.trim()
  if (!expr) return false

  // Strip outer parens if they wrap the whole expression
  const peeled = stripOuterParens(expr)
  if (peeled !== expr) {
    return evaluateWhenExpression(peeled, ctx)
  }

  // Split by OR at top level (lowest precedence)
  const orParts = splitTopLevel(expr, /\s+OR\s+/i)
  if (orParts.length > 1) {
    return orParts.some(part => evaluateWhenExpression(part, ctx))
  }

  // Split by AND
  const andParts = splitTopLevel(expr, /\s+AND\s+/i)
  if (andParts.length > 1) {
    return andParts.every(part => evaluateWhenExpression(part, ctx))
  }

  // Atomic comparison
  const result = evaluateComparison(expr, ctx)
  // Unparseable → false (conservative; rule won't match)
  return result === true
}

/**
 * Split string by `separator` regex but only at depth-0 (outside parentheses).
 */
function splitTopLevel(expr: string, separator: RegExp): string[] {
  const parts: string[] = []
  let depth = 0
  let last = 0
  // Build a global regex tracking sequentially
  const tokens: { start: number; end: number }[] = []
  // Walk character-by-character to find separator matches at depth 0
  // Use a sequential scan with regex.lastIndex
  const pattern = new RegExp(separator.source, separator.flags.includes('g') ? separator.flags : separator.flags + 'g')

  for (let i = 0; i < expr.length; i++) {
    const ch = expr[i]
    if (ch === '(') depth++
    else if (ch === ')') depth = Math.max(0, depth - 1)
  }
  // If parens are unbalanced, fall back to naive split
  if (depth !== 0) {
    return expr.split(separator).map(s => s.trim()).filter(Boolean)
  }

  depth = 0
  pattern.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = pattern.exec(expr)) !== null) {
    // Recompute depth at match position
    let d = 0
    for (let i = 0; i < m.index; i++) {
      if (expr[i] === '(') d++
      else if (expr[i] === ')') d = Math.max(0, d - 1)
    }
    if (d === 0) {
      tokens.push({ start: m.index, end: m.index + m[0].length })
    }
  }

  if (tokens.length === 0) {
    return [expr.trim()]
  }

  for (const t of tokens) {
    parts.push(expr.slice(last, t.start).trim())
    last = t.end
  }
  parts.push(expr.slice(last).trim())
  return parts.filter(Boolean)
}

/**
 * If the expression is wrapped in a single matching outer pair of parens, strip them.
 * Returns the original string if not wrapped.
 */
function stripOuterParens(expr: string): string {
  const s = expr.trim()
  if (s.length < 2 || s[0] !== '(' || s[s.length - 1] !== ')') return s
  let depth = 0
  for (let i = 0; i < s.length; i++) {
    if (s[i] === '(') depth++
    else if (s[i] === ')') {
      depth--
      if (depth === 0 && i < s.length - 1) {
        // Closes before the end → outer parens don't wrap the whole expr
        return s
      }
    }
  }
  if (depth !== 0) return s
  return s.slice(1, -1).trim()
}

function deriveFromCombination(comb: CombinationRow): DerivationResult {
  // Build evaluation context (only answer fields)
  const ctx: Record<string, any> = {}
  for (const q of questions.value) {
    ctx[q.id] = comb[`${q.id}_answer`] ?? ''
  }

  for (const rule of derivationRules.value) {
    if (!rule?.when || !rule?.set) continue
    if (evaluateWhenExpression(rule.when, ctx)) {
      return {
        rule_id: rule.id,
        business_model: rule.set.business_model || '—',
        measurement_class: rule.set.measurement_class || '—',
        report_line: rule.set.report_line || '—',
        confidence: rule.set.confidence || 'medium',
      }
    }
  }

  // Fallback: rule_default_pending (but if no rules at all, return pending)
  const fallback = derivationRules.value.find(r => r.id === 'rule_default_pending')
  if (fallback?.set) {
    return {
      rule_id: fallback.id,
      business_model: fallback.set.business_model || '待判定',
      measurement_class: fallback.set.measurement_class || '—',
      report_line: fallback.set.report_line || '—',
      confidence: fallback.set.confidence || 'pending',
    }
  }
  return {
    rule_id: '',
    business_model: '待判定',
    measurement_class: '—',
    report_line: '—',
    confidence: 'pending',
  }
}

// ─── Tag helpers ─────────────────────────────────────────────────────────────

function confidenceTagType(
  confidence?: 'high' | 'medium' | 'low' | 'pending'
): 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  switch (confidence) {
    case 'high': return 'success'
    case 'medium': return 'primary'
    case 'low': return 'warning'
    case 'pending':
    default: return 'info'
  }
}

function confidenceLabel(
  confidence?: 'high' | 'medium' | 'low' | 'pending'
): string {
  switch (confidence) {
    case 'high': return '高'
    case 'medium': return '中'
    case 'low': return '低'
    case 'pending':
    default: return '待定'
  }
}

// ─── Field change emitters ───────────────────────────────────────────────────

function emitFieldChange(field_name: string, oldValue: any, newValue: any) {
  emit('field-change', {
    field_name,
    old_value: oldValue,
    new_value: newValue,
  })
}

// ─── Context handlers ────────────────────────────────────────────────────────

function onContextFieldChange(name: string) {
  emitFieldChange(`context.${name}`, undefined, contextData.value[name])
  debounceSave()
}

// ─── Combination handlers ───────────────────────────────────────────────────

function handleAddCombination() {
  if (reachedMaxCombinations.value) return
  combinations.value.push(buildEmptyCombination())
  emitFieldChange(
    `combinations.length`,
    combinations.value.length - 1,
    combinations.value.length
  )
  debounceSave()
}

function handleRemoveLastCombination() {
  if (combinations.value.length === 0) return
  combinations.value.pop()
  debounceSave()
}

function handleRemoveCombination(idx: number) {
  if (idx < 0 || idx >= combinations.value.length) return
  combinations.value.splice(idx, 1)
  debounceSave()
}

function onCombinationNameChange(idx: number) {
  emitFieldChange(
    `combinations[${idx}].combination_name`,
    undefined,
    combinations.value[idx]?.combination_name
  )
  debounceSave()
}

function onAnswerChange(idx: number, questionId: string) {
  const fieldName = `${questionId}_answer`
  emitFieldChange(
    `combinations[${idx}].${fieldName}`,
    undefined,
    combinations.value[idx]?.[fieldName]
  )
  debounceSave()
}

// ─── Init / sync ─────────────────────────────────────────────────────────────

function applyContextDefaults() {
  const ctxIn = (props.htmlData as QaFormData)?.context
  const merged: Record<string, any> = {}
  for (const f of contextFields.value) {
    if (ctxIn && Object.prototype.hasOwnProperty.call(ctxIn, f.name)) {
      merged[f.name] = (ctxIn as Record<string, any>)[f.name]
    } else if (typeof f.default === 'string') {
      merged[f.name] = f.default
    } else {
      merged[f.name] = ''
    }
  }
  contextData.value = merged
}

function initData() {
  applyContextDefaults()

  const data = (props.htmlData ?? {}) as QaFormData
  const combosIn = Array.isArray(data.combinations) ? data.combinations : []
  combinations.value = combosIn.map(c => ensureCombinationShape(c))

  // Notes: default collapsed unless schema says otherwise or persisted state says open
  const persisted = Array.isArray(data.active_note_ids) ? data.active_note_ids : null
  if (persisted) {
    activeNoteIds.value = persisted.filter(id => notes.value.some(n => n.id === id))
  } else {
    activeNoteIds.value = notes.value
      .filter(n => n.default_collapsed === false)
      .map(n => n.id)
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
    initData()
  },
  { deep: true }
)

// ─── Save payload + debounce ─────────────────────────────────────────────────

function buildSavePayload(): QaFormData {
  // Snapshot derivations into combinations (for backend persistence + downstream consumption)
  const enriched: CombinationRow[] = combinations.value.map((c, idx) => {
    const d = derivations.value[idx]
    const out: CombinationRow = {
      combination_name: c.combination_name,
    }
    for (const q of questions.value) {
      const key = `${q.id}_answer`
      out[key] = c[key] ?? ''
    }
    if (d) {
      out.business_model = d.business_model
      out.measurement_class = d.measurement_class
      out.report_line = d.report_line
      out.confidence = d.confidence
    }
    return out
  })

  return {
    ...(props.htmlData || {}),
    context: { ...contextData.value },
    combinations: enriched,
    active_note_ids: [...activeNoteIds.value],
    ai_assisted_fields: assistedFieldsList.value.length > 0 ? assistedFieldsList.value : undefined,
  } as QaFormData
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
.gt-d-form-qa {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
}

/* ── Header ── */
.gt-dfq__header {
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
.gt-dfq__header-meta {
  display: flex;
  align-items: center;
  gap: 16px;
}
.gt-dfq__entity {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-dfq__period {
  color: var(--el-text-color-regular);
}
.gt-dfq__index {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dfq__index strong {
  color: var(--el-color-primary);
  margin-left: 4px;
}

/* ── Context fields ── */
.gt-dfq__context {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 12px 16px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-dfq__context-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 12px 16px;
}
.gt-dfq__context-item {
  margin-bottom: 0;
}
.gt-dfq__field-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.gt-dfq__field-hint .el-icon {
  color: var(--el-color-info);
}

/* ── Toolbar ── */
.gt-dfq__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.gt-dfq__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-dfq__toolbar-actions {
  display: flex;
  gap: 8px;
}

/* ── Matrix table ── */
.gt-dfq__matrix-wrap {
  overflow-x: auto;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-dfq__matrix {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
  table-layout: fixed;
}
.gt-dfq__col-label {
  width: 280px;
}
.gt-dfq__col-comb {
  width: 220px;
  min-width: 200px;
}
.gt-dfq__matrix th,
.gt-dfq__matrix td {
  border-bottom: 1px solid var(--el-border-color-lighter);
  border-right: 1px solid var(--el-border-color-lighter);
  padding: 10px 12px;
  vertical-align: middle;
  text-align: left;
}
.gt-dfq__matrix th:last-child,
.gt-dfq__matrix td:last-child {
  border-right: none;
}
.gt-dfq__matrix tr:last-child th,
.gt-dfq__matrix tr:last-child td {
  border-bottom: none;
}
.gt-dfq__th-label {
  background: var(--el-fill-color-light);
  font-weight: 600;
  color: var(--el-text-color-primary);
  position: sticky;
  left: 0;
  z-index: 2;
}
.gt-dfq__th-comb {
  background: var(--el-color-primary-light-9);
  font-weight: 600;
  color: var(--el-color-primary);
}
.gt-dfq__comb-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gt-dfq__comb-no {
  font-size: 12px;
  color: var(--el-color-primary);
  font-weight: 600;
}

/* ── Question rows ── */
.gt-dfq__th-question {
  background: var(--el-fill-color-lighter);
  font-weight: 500;
  color: var(--el-text-color-primary);
  position: sticky;
  left: 0;
  z-index: 1;
}
.gt-dfq__q-head {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}
.gt-dfq__q-seq {
  font-size: 12px;
  color: var(--el-color-primary);
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}
.gt-dfq__q-text {
  flex: 1;
  line-height: 1.5;
}
.gt-dfq__q-help {
  color: var(--el-color-info);
  font-size: 14px;
  cursor: help;
  margin-top: 2px;
  flex-shrink: 0;
}

.gt-dfq__td-radio {
  background: var(--gt-color-bg-white, #fff);
}
.gt-dfq__radio-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-dfq__radio-group :deep(.el-radio) {
  margin-right: 0;
  height: 24px;
}

/* ── Derived rows ── */
.gt-dfq__row-derived--first th,
.gt-dfq__row-derived--first td {
  border-top: 2px solid var(--el-color-primary-light-5);
}
.gt-dfq__th-derived {
  background: var(--el-color-success-light-9);
  font-weight: 600;
  color: var(--el-text-color-primary);
  position: sticky;
  left: 0;
  z-index: 1;
}
.gt-dfq__td-derived {
  background: var(--el-color-success-light-9);
}
.gt-dfq__derived-tag {
  white-space: normal;
  height: auto;
  line-height: 1.4;
  padding: 4px 8px;
  max-width: 100%;
}
.gt-dfq__derived-empty {
  color: var(--el-text-color-disabled);
  font-size: 12px;
}

/* ── Notes ── */
.gt-dfq__notes {
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 12px 16px;
  background: var(--gt-color-bg-white, #fff);
}
.gt-dfq__note-content {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

/* ── Help tooltip ── */
:global(.gt-dfq__help-popper) {
  max-width: 360px;
}
.gt-dfq__help-text {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.6;
}

/* ── AI suggest ── */
.gt-dfq__input-wrapper {
  position: relative;
  width: 100%;
}
.gt-ai-suggest-trigger {
  position: absolute;
  top: 4px;
  right: 8px;
  z-index: 5;
}
.gt-dfq__ai-panel {
  margin-top: 8px;
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: 6px;
  padding: 12px;
  background: var(--el-color-primary-light-9);
}
.gt-dfq__ai-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.gt-dfq__ai-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
}
.gt-dfq__ai-panel-text {
  margin: 0 0 10px;
  padding: 8px 12px;
  background: var(--gt-color-bg-white, #fff);
  border-radius: 4px;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--el-text-color-regular);
  max-height: 200px;
  overflow-y: auto;
}
.gt-dfq__ai-panel-actions {
  display: flex;
  gap: 8px;
}
</style>
