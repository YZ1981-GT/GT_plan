<template>
  <div class="l0-lower">
    <!-- ═══ 一、函证情况（2 品种 × 8 指标） ═══════════════════════════════ -->
    <section class="l0-lower__section">
      <div class="l0-lower__title">
        <span>{{ titleOf('matrix') }}</span>
        <el-tooltip
          v-if="titleTypoOf('matrix')"
          :content="titleTypoOf('matrix')"
          placement="top"
        >
          <el-tag size="small" type="warning" effect="plain">源模板笔误</el-tag>
        </el-tooltip>
        <el-button
          v-if="!readonly"
          size="small"
          :loading="refreshing"
          style="margin-left:auto"
          @click="emit('refresh-book-amounts')"
        >
          刷新账面金额
        </el-button>
      </div>

      <!-- 取数诊断：🔴 必须渲染，不能只收集（F0 教训） -->
      <el-alert
        v-if="diagErrors.length"
        type="warning"
        :closable="false"
        show-icon
        class="l0-lower__alert"
      >
        <template #title>账面金额取数提示</template>
        <ul class="l0-lower__diag">
          <li v-for="(e, i) in diagErrors" :key="`err-${i}`">{{ e }}</li>
        </ul>
      </el-alert>
      <el-alert
        v-if="diagConflicts.length"
        type="error"
        :closable="false"
        show-icon
        class="l0-lower__alert"
      >
        <template #title>报表规则与本项目科目表不一致（以科目表为准，请复核）</template>
        <ul class="l0-lower__diag">
          <li v-for="(c, i) in diagConflicts" :key="`cf-${i}`">{{ c }}</li>
        </ul>
      </el-alert>
      <el-alert
        v-if="diagParentIssues.length"
        type="error"
        :closable="false"
        show-icon
        class="l0-lower__alert"
      >
        <template #title>叶子科目合计与父科目余额勾稽不成立</template>
        <ul class="l0-lower__diag">
          <li v-for="(p, i) in diagParentIssues" :key="`pc-${i}`">{{ p }}</li>
        </ul>
      </el-alert>

      <el-table :data="matrixTableData" border size="small" style="width:100%">
        <el-table-column prop="label" :label="LABEL_HEADER" min-width="240" />
        <el-table-column
          v-for="cat in CATEGORY_NAMES"
          :key="cat"
          :label="cat"
          align="right"
          min-width="170"
        >
          <template #header>
            <el-tooltip :content="bookHintOf(cat)" placement="top">
              <span class="l0-lower__cat-head">{{ cat }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <!-- 账面金额行：可手工覆盖 -->
            <WpAmountInput
              v-if="row.metric === 'book_amount' && !readonly"
              :model-value="editableBookValue(cat)"
              :placeholder="bookStateTextOf(cat) || '请输入'"
              size="small"
              @update:model-value="(v: number | null) => onBookAmountInput(cat, v)"
            />
            <span v-else-if="row.metric === 'book_amount'" class="l0-lower__amount">
              {{ bookDisplayOf(cat) }}
            </span>
            <span v-else class="l0-lower__amount">{{ cellText(cat, row.metric) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="l0-lower__hint">
        本区按上区明细表「账户/交易」列分品种聚合（源模板 SUMIF 口径）；
        账面金额自动取数后仍可手工覆盖，覆盖值优先。
      </div>
      <div v-if="!rows.length" class="l0-lower__empty">{{ EMPTY_MATRIX_TEXT }}</div>
    </section>

    <!-- ═══ 二、样本选择（6 项） ═════════════════════════════════════════ -->
    <section class="l0-lower__section">
      <div class="l0-lower__title"><span>{{ titleOf('sample') }}</span></div>
      <el-form label-position="top" size="small">
        <el-form-item v-for="d in SAMPLE_DEFS" :key="d.field">
          <template #label>
            <span class="l0-lower__field-label">
              {{ d.label }}
              <el-tooltip :content="`源模板 ${d.source_ref}`" placement="top">
                <span class="l0-lower__anchor">{{ d.source_ref }}</span>
              </el-tooltip>
            </span>
          </template>
          <el-input
            :model-value="textValues[d.field] ?? ''"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :placeholder="d.placeholder"
            :disabled="readonly"
            @input="(v: string) => onTextInput(d.field, v)"
          />
          <div v-if="d.hint" class="l0-lower__src-hint">{{ d.hint }}</div>
        </el-form-item>
      </el-form>
    </section>

    <!-- ═══ 三、审计说明（5 段，序号笔误已更正） ════════════════════════ -->
    <section class="l0-lower__section">
      <div class="l0-lower__title">
        <span>{{ titleOf('auditNote') }}</span>
        <el-tooltip :content="titleTypoOf('auditNote')" placement="top">
          <el-tag size="small" type="warning" effect="plain">源模板序号笔误</el-tag>
        </el-tooltip>
      </div>
      <el-form label-position="top" size="small">
        <el-form-item v-for="d in AUDIT_NOTE_DEFS" :key="d.field">
          <template #label>
            <span class="l0-lower__field-label">
              {{ d.label }}
              <el-tooltip :content="`源模板 ${d.source_ref}`" placement="top">
                <span class="l0-lower__anchor">{{ d.source_ref }}</span>
              </el-tooltip>
              <el-button
                v-if="!readonly"
                size="small"
                :loading="aiLoadingKey === d.field"
                @click="emit('ai-generate', 'l0-lower-audit-note', d.field)"
              >
                🤖 AI 辅助
              </el-button>
              <GtReviewTrigger :section-id="d.field" label="💬 复核" />
            </span>
          </template>
          <el-input
            :model-value="textValues[d.field] ?? ''"
            type="textarea"
            :autosize="{ minRows: 3 }"
            :placeholder="d.placeholder"
            :disabled="readonly"
            @input="(v: string) => onTextInput(d.field, v)"
          />
          <div v-if="d.hint" class="l0-lower__src-hint">{{ d.hint }}</div>
        </el-form-item>
      </el-form>
    </section>

    <!-- ═══ 四、审计结论 ════════════════════════════════════════════════ -->
    <section class="l0-lower__section">
      <div class="l0-lower__title">
        <span>{{ titleOf('conclusion') }}</span>
        <el-button
          v-if="!readonly"
          size="small"
          :loading="aiLoadingKey === CONCLUSION_FIELD"
          style="margin-left:auto"
          @click="emit('ai-generate', 'l0-lower-conclusion', CONCLUSION_FIELD)"
        >
          🤖 AI 辅助
        </el-button>
        <GtReviewTrigger :section-id="CONCLUSION_FIELD" label="💬 复核" />
      </div>

      <el-input
        :model-value="textValues[CONCLUSION_FIELD] ?? ''"
        type="textarea"
        :autosize="{ minRows: 4 }"
        placeholder="结合上表比例与不符事项，撰写本次函证程序的审计结论"
        :disabled="readonly"
        @input="(v: string) => onTextInput(CONCLUSION_FIELD, v)"
      />

      <!-- 参考结论（只读，源 A65:B68） -->
      <el-card shadow="never" class="l0-lower__ref">
        <template #header>
          <span class="l0-lower__ref-title">{{ REF_TITLE }}</span>
        </template>
        <div v-for="c in REF_CONCLUSIONS" :key="c.code" class="l0-lower__ref-row">
          <el-tag size="small" effect="plain">{{ c.code }}</el-tag>
          <span class="l0-lower__ref-text">{{ c.text }}</span>
          <el-button v-if="!readonly" link size="small" @click="applyRefConclusion(c.text)">
            套用
          </el-button>
        </div>
        <div class="l0-lower__ref-evidence">{{ EVIDENCE_NOTE }}</div>
      </el-card>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * L0SummaryLowerZone.vue — L0-1 下区四块（函证情况 / 样本选择 / 审计说明 / 审计结论）
 *
 * spec: l0-confirmation-source-alignment，Task 12（Requirements 3.1 / 3.4~3.7 / 3.9 / 3.10）
 *
 * 🔴 三条平台铁律在本组件的落法：
 * 1. `fmtAmount` 是 **store 成员**不是模块级导出 → setup 顶层
 *    `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`（写进函数体会静默失效，
 *    模块级 `import { fmtAmount }` 会让整页崩成「does not provide an export named」）。
 * 2. 可编辑金额只能用 `WpAmountInput`（EP 2.13.6 的 `el-input-number` 无 `formatter` prop，
 *    那个 prop 根本不存在 → 千分符从未生效）。
 * 3. 下区录入**直接 emit `save`**，由宿主调
 *    `PUT /api/workpapers/{id}/checklist-responses` —— **不得**走 sheet 级
 *    `emit('save', 载荷)` 通道，那会把整个 sheet 的 `html_data` 覆盖成
 *    `{itemId, value}`，一次点击就把上区函证行全丢并让该 sheet 退化成「旧格式只读」。
 *
 * 🔴 `responses` 必须由宿主从 **`/checklist-responses`（已持久化）** 拉取，
 * 不得来自 `responses_snapshot`（含 prefill 种子，会把种子当成审计师录入）。
 */
import { computed, inject, ref, watch } from 'vue'

import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

import type { ConfirmationRow } from '../confirmationTypes'
import {
  L0_MATRIX_CATEGORIES,
  L0_MATRIX_CATEGORY_NAMES,
  L0_MATRIX_LABEL_HEADER,
  buildL0SummaryMatrix,
  pickL0MatrixCell,
  type L0MatrixCell,
  type L0MetricKey,
} from './l0SummaryMatrix'
import {
  bookAmountOverrideItemId,
  buildL0BookAmountViews,
  buildL0MatrixDiagnostics,
  type L0BookAmountView,
} from './l0MatrixDataSources'
import {
  L0_ATTACHED_EVIDENCE_NOTE,
  L0_AUDIT_NOTE_DEFS,
  L0_CONCLUSION_FIELD,
  L0_REFERENCE_CONCLUSIONS,
  L0_REFERENCE_CONCLUSION_TITLE,
  L0_SAMPLE_SELECTION_DEFS,
  L0_SECTION_TITLE_BY_ID,
} from './l0SummaryLowerZone'

const props = defineProps<{
  /** L0-1 上区明细行（矩阵按品种 SUMIF 的数据源） */
  rows: readonly ConfirmationRow[]
  readonly: boolean
  /**
   * 已**持久化**的 checklist responses（itemId → value）。
   * 🔴 必须来自 `/checklist-responses`，不得来自 `responses_snapshot`。
   */
  responses?: Record<string, string>
  /**
   * 该 sheet 的 `html_data`（内含后端注入的 `project_context.l0_book_amounts`）。
   * 🔴 原样传入，**不要**在调用侧写 `?? {}` —— 那会让「未取数」与「本项目无此科目」不可区分。
   */
  htmlData?: unknown
  refreshing?: boolean
  aiLoadingKey?: string | null
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: string): void
  (e: 'ai-generate', aiSection: string, key: string): void
  (e: 'refresh-book-amounts'): void
}>()

// 🔴 金额格式单一真源 = displayPrefs.fmtAmount（**store 成员**）。必须在 setup 顶层取。
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// ─── 常量（模板引用） ───────────────────────────────────────────────────────

const LABEL_HEADER = L0_MATRIX_LABEL_HEADER
const CATEGORY_NAMES = L0_MATRIX_CATEGORY_NAMES
const SAMPLE_DEFS = L0_SAMPLE_SELECTION_DEFS
const AUDIT_NOTE_DEFS = L0_AUDIT_NOTE_DEFS
const CONCLUSION_FIELD = L0_CONCLUSION_FIELD
const REF_CONCLUSIONS = L0_REFERENCE_CONCLUSIONS
const REF_TITLE = L0_REFERENCE_CONCLUSION_TITLE
const EVIDENCE_NOTE = L0_ATTACHED_EVIDENCE_NOTE
const EMPTY_MATRIX_TEXT = '请先在上方明细表录入函证行（矩阵按「账户/交易」列分品种聚合）'

// ─── 状态（🔴 全部 ref 必须声明在下方 watch 之前 —— TDZ） ───────────────────

const textValues = ref<Record<string, string>>({})
const manualOverrides = ref<Record<string, number>>({})

watch(
  () => props.responses,
  (r) => {
    const src = r ?? {}
    const texts: Record<string, string> = {}
    const overrides: Record<string, number> = {}
    for (const [k, v] of Object.entries(src)) {
      if (k.startsWith('L0-1-lower')) {
        texts[k] = String(v ?? '')
      } else if (k.startsWith('L0-1-matrix')) {
        const n = Number(v)
        if (Number.isFinite(n)) overrides[k] = n
      }
    }
    textValues.value = texts
    manualOverrides.value = overrides
  },
  { immediate: true, deep: true },
)

// ─── 段标题（含笔误更正） ───────────────────────────────────────────────────

function titleOf(id: string): string {
  return L0_SECTION_TITLE_BY_ID[id]?.display ?? ''
}
function titleTypoOf(id: string): string {
  return L0_SECTION_TITLE_BY_ID[id]?.typoNote ?? ''
}

// ─── 矩阵 ───────────────────────────────────────────────────────────────────

const bookViews = computed<L0BookAmountView[]>(() => buildL0BookAmountViews(props.htmlData))
const bookViewByCat = computed(() =>
  Object.fromEntries(bookViews.value.map((v) => [v.category, v])),
)

const bookAmountsForMatrix = computed<Record<string, number | null> | undefined>(() => {
  const views = bookViews.value
  if (views.every((v) => v.state === 'not_fetched')) return undefined
  const out: Record<string, number | null> = {}
  for (const v of views) {
    if (v.state === 'not_fetched') continue
    out[v.category] = v.state === 'absent' ? null : v.value
  }
  return out
})

const matrix = computed<L0MatrixCell[][]>(() =>
  buildL0SummaryMatrix({
    rows: props.rows ?? [],
    bookAmounts: bookAmountsForMatrix.value,
    manualOverrides: manualOverrides.value,
  }),
)

/** 表格行（按指标一行，品种作列） */
const matrixTableData = computed(() =>
  (matrix.value[0] ?? []).map((cell) => ({ metric: cell.metric, label: cell.label })),
)

function cellText(category: string, metric: L0MetricKey): string {
  const cell = pickL0MatrixCell(matrix.value, category, metric)
  if (!cell || cell.value === null) return '-'
  if (cell.kind === 'ratio') return `${(cell.value * 100).toFixed(2)}%`
  return displayPrefs.fmtAmount(cell.value)
}

function bookDisplayOf(category: string): string {
  const cell = pickL0MatrixCell(matrix.value, category, 'book_amount')
  if (!cell || cell.value === null) return bookStateTextOf(category) || '-'
  return displayPrefs.fmtAmount(cell.value)
}

/** 三态文案（未取数 / 本项目无此科目 / 有值时空串） */
function bookStateTextOf(category: string): string {
  return bookViewByCat.value[category]?.text ?? ''
}

function bookHintOf(category: string): string {
  const def = L0_MATRIX_CATEGORIES.find((c) => c.name === category)
  const src = bookViewByCat.value[category]?.source
  const parts = [def?.book.hint ?? '']
  if (src?.resolved_from) parts.push(`定位来源：${resolvedFromLabel(src.resolved_from)}`)
  if (src?.gross?.length) parts.push(`取数科目：${src.gross.join(' / ')}`)
  for (const n of src?.notes ?? []) parts.push(n)
  return parts.filter(Boolean).join('\n')
}

/** `resolved_from` 中文标签（UI 全中文化） */
function resolvedFromLabel(v: string): string {
  switch (v) {
    case 'account_chart_client': return '客户科目表（按科目名定位）'
    case 'account_chart_standard': return '标准科目表（按科目名定位）'
    case 'report_config': return '报表规则映射'
    case 'fallback': return '兜底科目码'
    case 'none': return '本项目无此科目'
    default: return v
  }
}

function editableBookValue(category: string): number | null {
  const cell = pickL0MatrixCell(matrix.value, category, 'book_amount')
  return cell?.value ?? null
}

function onBookAmountInput(category: string, v: number | null) {
  const itemId = bookAmountOverrideItemId(category)
  emit('save', itemId, v === null || v === undefined ? '' : String(v))
}

// ─── 诊断（必须渲染） ───────────────────────────────────────────────────────

const diagnostics = computed(() => buildL0MatrixDiagnostics(props.htmlData))
const diagErrors = computed(() => diagnostics.value.errors)
const diagConflicts = computed(() => diagnostics.value.conflicts)
const diagParentIssues = computed(() => diagnostics.value.parentCheckIssues)

// ─── 文本 ───────────────────────────────────────────────────────────────────

function onTextInput(field: string, v: string) {
  textValues.value = { ...textValues.value, [field]: v }
  emit('save', field, v)
}

function applyRefConclusion(text: string) {
  onTextInput(CONCLUSION_FIELD, text)
}

/**
 * 供宿主回填 AI 生成文本（与 G0/H0 下区同款契约）。
 *
 * 🔴 `key` 是 `L0_AUDIT_NOTE_DEFS[].field` 或 `L0_CONCLUSION_FIELD`（= 持久化 itemId），
 *    不是 aiSection —— 宿主 `handleL0LowerAi(aiSection, key)` 的第二参就是它。
 * 走 `onTextInput` 而非直写 ref：AI 文本必须与手工录入同路径落库（否则显示有值但没保存）。
 */
function applyAiText(key: string, text: string) {
  onTextInput(key, text)
}

defineExpose({ applyAiText })

const rows = computed(() => props.rows ?? [])
const readonly = computed(() => !!props.readonly)
const refreshing = computed(() => !!props.refreshing)
const aiLoadingKey = computed(() => props.aiLoadingKey ?? null)
</script>

<style scoped>
.l0-lower { font-size: 13px; }
.l0-lower__section { margin-top: 16px; }
.l0-lower__title {
  display: flex; align-items: center; gap: 8px;
  font-weight: 600; margin-bottom: 8px;
}
.l0-lower__alert { margin-bottom: 8px; }
.l0-lower__diag { margin: 0; padding-left: 18px; }
.l0-lower__amount { font-variant-numeric: tabular-nums; white-space: nowrap; }
.l0-lower__cat-head { border-bottom: 1px dashed #909399; cursor: help; }
.l0-lower__hint { color: #909399; margin-top: 6px; }
.l0-lower__empty { color: #E6A23C; margin-top: 6px; }
.l0-lower__field-label { display: flex; align-items: center; gap: 8px; }
.l0-lower__anchor { color: #C0C4CC; font-weight: 400; }
.l0-lower__src-hint {
  margin-top: 4px; padding: 6px 8px;
  border-left: 3px solid #E6A23C; background: #FDF6EC; color: #7A5C22;
}
.l0-lower__ref { margin-top: 12px; }
.l0-lower__ref-title { font-weight: 600; }
.l0-lower__ref-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.l0-lower__ref-text { flex: 1; }
.l0-lower__ref-evidence { color: #909399; margin-top: 8px; }
</style>
