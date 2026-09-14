<template>
  <div class="h0-lower">
    <!-- ══════════ 一、函证情况（品种 × 8 指标矩阵） ══════════ -->
    <section class="h0-lower__block">
      <div class="h0-lower__head">
        <h4 class="h0-lower__title">
          {{ BLOCKS.matrix.title }}
          <span class="h0-lower__anchor">源模板 {{ BLOCKS.matrix.anchor }}</span>
        </h4>
        <div class="h0-lower__head-actions">
          <el-button
            size="small"
            :disabled="readonly"
            :loading="refreshing"
            @click="emit('refresh-book-amounts')"
          >
            🔄 刷新账面金额
          </el-button>
          <el-button size="small" :disabled="readonly" @click="handleAddCategory">
            ＋ 增加品种
          </el-button>
          <el-button size="small" text @click="showSource = !showSource">
            {{ showSource ? '收起溯源' : '取数溯源' }}
          </el-button>
        </div>
      </div>

      <!-- 覆盖率红线提示 -->
      <div v-if="coverageAlerts.length" class="h0-lower__alert-bar">
        <el-tag
          v-for="a in coverageAlerts"
          :key="a.categoryKey"
          :type="a.level === 'error' ? 'danger' : 'warning'"
          size="small"
          effect="light"
        >
          {{ a.categoryLabel }} 回函+替代确认占账面 {{ pct(a.ratio) }}
        </el-tag>
        <el-text size="small" type="info">覆盖率偏低，请评价函证程序的充分性并考虑扩大替代程序范围</el-text>
      </div>

      <el-table
        :data="matrixRows"
        border
        size="small"
        class="h0-lower__matrix"
        :empty-text="EMPTY_MATRIX_TEXT"
      >
        <el-table-column prop="metric" label="项目" min-width="230" fixed>
          <template #default="{ row }">
            <span :class="{ 'h0-lower__formula': !row.editable }">{{ row.metric }}</span>
            <el-tooltip v-if="!row.editable" placement="top" :content="metricHint(row)">
              <span class="h0-lower__q">?</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column
          v-for="cat in categories"
          :key="cat.key"
          min-width="150"
          align="right"
        >
          <template #header>
            <div class="h0-lower__cat-head">
              <span>{{ cat.label }}</span>
              <span v-if="!readonly" class="h0-lower__cat-ops">
                <span class="h0-lower__cat-op" title="改名" @click="handleRenameCategory(cat)">✎</span>
                <span class="h0-lower__cat-op" title="删除" @click="handleRemoveCategory(cat)">✕</span>
              </span>
            </div>
          </template>
          <template #default="{ row }">
            <!-- 账面金额行：可编辑（手工优先，清空回落自动取数） -->
            <WpAmountInput
              v-if="row.editable && !readonly"
              :model-value="row.cells[cat.key]?.value ?? null"
              :placeholder="bookPlaceholder(row.cells[cat.key])"
              size="small"
              @update:model-value="(v: number | null) => handleBookAmountChange(cat.key, v)"
            />
            <template v-else>
              <span v-if="row.cells[cat.key]?.value === null" class="h0-lower__dash">
                <el-tooltip v-if="row.cells[cat.key]?.sourceHint" placement="top" :content="row.cells[cat.key]!.sourceHint!">
                  <span>-</span>
                </el-tooltip>
                <span v-else>-</span>
              </span>
              <el-tooltip
                v-else
                placement="top"
                :content="row.cells[cat.key]?.sourceHint || ''"
                :disabled="!row.cells[cat.key]?.sourceHint"
              >
                <span :class="cellClass(row.cells[cat.key])">
                  {{ row.kind === 'ratio' ? pct(row.cells[cat.key]!.value!) : fmt(row.cells[cat.key]!.value!) }}
                </span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <!-- 取数溯源面板 -->
      <div v-if="showSource" class="h0-lower__source">
        <div v-if="bookConflicts.length" class="h0-lower__conflict">
          <el-alert
            v-for="(c, i) in bookConflicts"
            :key="i"
            type="warning"
            :closable="false"
            :title="c"
            show-icon
          />
        </div>
        <el-table :data="sourceRows" border size="small">
          <el-table-column prop="category" label="品种" width="130" />
          <el-table-column prop="sourceWp" label="来源底稿" width="90" />
          <el-table-column prop="rowCode" label="报表行" width="90" />
          <el-table-column prop="formula" label="口径" min-width="240" />
          <el-table-column prop="codes" label="解析出的科目码" min-width="160" />
          <el-table-column label="定位来源" width="140">
            <template #default="{ row }">
              <el-tag :type="row.tagType" size="small" effect="plain">{{ row.resolvedLabel }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
        <el-text size="small" type="info" class="h0-lower__source-note">
          账面金额按品种走语义科目定位（客户科目表优先按名匹配 → 标准科目表 → 报表行公式 → 兜底码），
          再从 tb_balance 叶子聚合（原值 − 备抵）。「本项目无此科目」与「余额为 0」是两种状态。
        </el-text>
      </div>
    </section>

    <!-- ══════════ 二、样本选择 ══════════ -->
    <section class="h0-lower__block">
      <h4 class="h0-lower__title">
        {{ BLOCKS.sample_selection.title }}
        <span class="h0-lower__anchor">源模板 {{ BLOCKS.sample_selection.anchor }}</span>
      </h4>
      <div class="h0-lower__sample-grid">
        <div v-for="f in SAMPLE_FIELDS" :key="f.key" class="h0-lower__sample-item">
          <label>{{ f.label }}</label>
          <el-input
            v-model="sampleValues[f.key]"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="readonly"
            :placeholder="f.placeholder"
            @change="saveSample(f.key)"
          />
        </div>
      </div>
    </section>

    <!-- ══════════ 三、审计说明 ══════════ -->
    <el-card class="h0-lower__card" shadow="never">
      <template #header>
        <div class="h0-lower__head">
          <h4 class="h0-lower__title">
            {{ BLOCKS.audit_note.title }}
            <span class="h0-lower__anchor">源模板 {{ BLOCKS.audit_note.anchor }}</span>
          </h4>
          <el-tooltip placement="top" :content="AUDIT_NOTE_TYPO_HINT">
            <el-tag type="info" size="small" effect="plain">源模板编号笔误已修正</el-tag>
          </el-tooltip>
        </div>
      </template>

      <div v-for="s in AUDIT_NOTE_SECTIONS" :key="s.key" class="h0-lower__note">
        <div class="h0-lower__head">
          <div class="h0-lower__note-title">{{ s.title }}</div>
          <div class="h0-lower__head-actions">
            <el-button
              size="small"
              :disabled="readonly"
              :loading="aiLoadingKey === s.key"
              @click="emit('ai-generate', s.aiSection, s.key)"
            >
              🤖 AI 辅助
            </el-button>
            <el-button size="small" :disabled="readonly" @click="emit('review', s.key)">
              💬 复核
            </el-button>
          </div>
        </div>
        <div v-if="s.hint" class="h0-lower__hint">{{ s.hint }}</div>
        <el-input
          v-model="noteValues[s.key]"
          type="textarea"
          :autosize="{ minRows: 3 }"
          :disabled="readonly"
          :placeholder="notePlaceholder(s.title)"
          @change="saveNote(s.key)"
        />
      </div>
    </el-card>

    <!-- ══════════ 四、审计结论 ══════════ -->
    <el-card class="h0-lower__card" shadow="never">
      <template #header>
        <div class="h0-lower__head">
          <h4 class="h0-lower__title">
            {{ BLOCKS.conclusion.title }}
            <span class="h0-lower__anchor">源模板 {{ BLOCKS.conclusion.anchor }}</span>
          </h4>
          <div class="h0-lower__head-actions">
            <el-button
              size="small"
              :disabled="readonly"
              :loading="aiLoadingKey === 'conclusion'"
              @click="emit('ai-generate', 'summary-conclusion', 'conclusion')"
            >
              🤖 AI 辅助
            </el-button>
            <el-button size="small" :disabled="readonly" @click="emit('review', 'conclusion')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>

      <div class="h0-lower__hint h0-lower__hint--ref">
        <div class="h0-lower__ref-title">参考结论（源模板）</div>
        <div
          v-for="r in REFERENCE_CONCLUSIONS"
          :key="r.code"
          class="h0-lower__ref-item"
        >
          <el-button
            size="small"
            text
            type="primary"
            :disabled="readonly"
            @click="applyReference(r.text)"
          >
            {{ r.code }}
          </el-button>
          <span>{{ r.text }}</span>
        </div>
      </div>

      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="readonly"
        placeholder="请填写审计结论（可点击左侧 A/B/C 一键套用源模板参考结论后再修改）"
        @change="saveConclusion"
      />
    </el-card>

    <!-- ══════════ 编制说明（折叠，底部） ══════════ -->
    <details class="h0-lower__guidance">
      <summary>编制说明与函证注意事项（源模板）</summary>
      <div
        v-for="g in GUIDANCE_TEXTS"
        :key="g.key"
        class="h0-lower__hint h0-lower__hint--amber"
      >
        <p v-for="(line, i) in g.text.split('\n')" :key="i">{{ line }}</p>
        <span class="h0-lower__anchor">源模板 {{ g.anchor }}</span>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H0SummaryLowerZone.vue — H0-1 函证结果汇总表下区四块专属组件
 *
 * 源模板：`函证结果汇总表H0-1` R28~R37 + R42~R69
 * 范式对齐 `E0SummaryLowerZone.vue`，但 H0 的矩阵是**动态品种列**且账面金额可自动取数。
 *
 * spec: h0-confirmation-source-fidelity-and-linkage R2.1 / R3.1 / R3.7 / R3.9
 */
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import WpAmountInput from '../shared/WpAmountInput.vue'
import type { ConfirmationRow } from './confirmationTypes'
import {
  H0_LOWER_ZONE_BLOCKS as BLOCKS,
  H0_SAMPLE_SELECTION_FIELDS as SAMPLE_FIELDS,
  H0_AUDIT_NOTE_SECTIONS as AUDIT_NOTE_SECTIONS,
  H0_REFERENCE_CONCLUSIONS as REFERENCE_CONCLUSIONS,
  H0_CONCLUSION_KEY,
  getH0TextsForBlock,
  h0AuditNoteItemId,
  h0SampleItemId,
} from './h0SummaryLowerZone'
import {
  buildH0SummaryMatrix,
  createDefaultH0Categories,
  detectH0CoverageAlerts,
  h0MatrixOverrideItemId,
  maxH0CategorySeq,
  nextH0CategoryKey,
  parseH0Categories,
  parseH0Seq,
  toH0MatrixTableRows,
  H0_MATRIX_CATEGORIES_KEY,
  H0_MATRIX_SEQ_KEY,
  type H0MatrixCategory,
  type H0MatrixCell,
  type H0MatrixTableRow,
} from './h0SummaryMatrix'

const props = defineProps<{
  /** H0-1 上区明细行（矩阵按品种 SUMIF 的数据源） */
  rows: readonly ConfirmationRow[]
  readonly: boolean
  /** 已持久化的 checklist responses（itemId → value） */
  responses?: Record<string, string>
  /** 后端注入的按品种账面金额（键不存在=未取数；值为 null=本项目无此科目） */
  bookAmounts?: Record<string, number | null>
  /** 后端注入的取数溯源 */
  bookSourceCodes?: Record<string, Record<string, unknown>>
  /** report_config 与科目表冲突告警 */
  bookConflicts?: string[]
  /** 品种可选值（`confirmation_account_type` 枚举，矩阵品种须 ⊆ 它） */
  categoryOptions?: readonly string[]
  refreshing?: boolean
  aiLoadingKey?: string | null
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: string): void
  (e: 'ai-generate', aiSection: string, key: string): void
  (e: 'review', key: string): void
  (e: 'refresh-book-amounts'): void
}>()

// 🔴 金额格式单一真源 = displayPrefs.fmtAmount（**store 成员，不是模块级导出**）。
// 必须在 setup 顶层取 store：写进函数体会静默失效。
const displayPrefs = useDisplayPrefsStore()

const EMPTY_MATRIX_TEXT = '请先在上方明细表录入函证行（矩阵按「账户/交易」列分品种聚合）'
const AUDIT_NOTE_TYPO_HINT =
  '源模板本块编号原文为「二、审计说明」，与上一块「二、样本选择」撞号，属源模板笔误，界面按「三」显示'

const showSource = ref(false)

// ─── 品种列（动态，持久化） ─────────────────────────────────────────────────

const categories = ref<H0MatrixCategory[]>(createDefaultH0Categories())
/** 品种列 key 单调计数器（持久化，保证删列后再增列不复用旧 key） */
const categorySeq = ref(0)

// ─── 录入值 ─────────────────────────────────────────────────────────────────

const sampleValues = ref<Record<string, string>>({})
const noteValues = ref<Record<string, string>>({})
const conclusion = ref('')
const manualOverrides = ref<Record<string, number>>({})

/**
 * 从 responses 恢复（props 变化时重新 hydrate）。
 * 🔴 用本地镜像 + immediate watch：宿主 map 异步加载，onMounted 一次性读会读到空。
 */
watch(
  () => props.responses,
  (r) => {
    const src = r ?? {}
    categories.value = parseH0Categories(safeJson(src[H0_MATRIX_CATEGORIES_KEY]))
    categorySeq.value = Math.max(
      parseH0Seq(src[H0_MATRIX_SEQ_KEY]),
      maxH0CategorySeq(categories.value),
    )
    for (const f of SAMPLE_FIELDS) {
      sampleValues.value[f.key] = src[h0SampleItemId(f.key)] ?? ''
    }
    for (const s of AUDIT_NOTE_SECTIONS) {
      noteValues.value[s.key] = src[h0AuditNoteItemId(s.key)] ?? ''
    }
    conclusion.value = src[H0_CONCLUSION_KEY] ?? ''

    const ov: Record<string, number> = {}
    for (const cat of categories.value) {
      const id = h0MatrixOverrideItemId(cat.key, 0)
      const n = Number(src[id])
      if (src[id] !== undefined && src[id] !== '' && Number.isFinite(n)) ov[id] = n
    }
    manualOverrides.value = ov
  },
  { immediate: true, deep: false },
)

function safeJson(raw: unknown): unknown {
  if (typeof raw !== 'string' || !raw.trim()) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

// ─── 矩阵 ───────────────────────────────────────────────────────────────────

const matrix = computed<H0MatrixCell[][]>(() =>
  buildH0SummaryMatrix({
    rows: props.rows,
    categories: categories.value,
    bookAmounts: props.bookAmounts,
    manualOverrides: manualOverrides.value,
  }),
)

const matrixRows = computed<H0MatrixTableRow[]>(() => toH0MatrixTableRows(matrix.value))
const coverageAlerts = computed(() => detectH0CoverageAlerts(matrix.value))
const bookConflicts = computed(() => props.bookConflicts ?? [])

const sourceRows = computed(() =>
  categories.value.map((cat) => {
    const s = props.bookSourceCodes?.[cat.label] as Record<string, any> | undefined
    const resolved = String(s?.resolved_from ?? 'none')
    return {
      category: cat.label,
      sourceWp: s?.source_wp_code ?? '—',
      rowCode: s?.row_code ?? '—',
      formula: s?.formula_hint ?? '—',
      codes: Array.isArray(s?.gross) && s.gross.length ? s.gross.join(' / ') : '—',
      resolvedLabel: resolvedLabel(resolved, s),
      tagType: resolvedTagType(resolved),
    }
  }),
)

function resolvedLabel(v: string, s?: Record<string, any>): string {
  switch (v) {
    case 'account_chart_client':
      return '客户科目表(按名)'
    case 'account_chart_standard':
      return '标准科目表(按名)'
    case 'report_config':
      return '报表行公式'
    case 'fallback':
      return '兜底科目码'
    default:
      return s?.absent_reason ? String(s.absent_reason) : '本项目无此科目'
  }
}

function resolvedTagType(v: string): 'success' | 'warning' | 'info' | '' {
  if (v === 'account_chart_client' || v === 'account_chart_standard') return 'success'
  if (v === 'report_config') return ''
  if (v === 'fallback') return 'warning'
  return 'info'
}

function metricHint(row: H0MatrixTableRow): string {
  const first = Object.values(row.cells)[0]
  return first?.sourceHint || '按源模板公式自上区明细聚合'
}

function cellClass(cell?: H0MatrixCell): string {
  if (!cell) return ''
  if (cell.origin === 'manual') return 'h0-lower__val h0-lower__val--manual'
  if (cell.origin === 'auto') return 'h0-lower__val h0-lower__val--auto'
  return 'h0-lower__val'
}

function bookPlaceholder(cell?: H0MatrixCell): string {
  if (!cell) return '请填写'
  if (cell.origin === 'absent') return '本项目无此科目'
  if (cell.origin === 'empty') return '未取数，可手填'
  return '自动取数（可覆盖）'
}

function fmt(v: number): string {
  return displayPrefs.fmtAmount(v)
}

function pct(v: number): string {
  return `${(v * 100).toFixed(2)}%`
}

function notePlaceholder(title: string): string {
  return `请填写${title.replace(/^\d+、/, '')}的内容`
}

// ─── 品种列增删改名 ─────────────────────────────────────────────────────────

function persistCategories() {
  emit('save', H0_MATRIX_CATEGORIES_KEY, JSON.stringify(categories.value))
}

async function handleAddCategory() {
  const options = props.categoryOptions ?? []
  const used = new Set(categories.value.map((c) => c.label))
  const avail = options.filter((o) => !used.has(o))
  if (!avail.length) {
    ElMessage.warning('可选品种已全部加入矩阵')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt(
      `可选品种：${avail.join('、')}`,
      '增加品种',
      { inputValue: avail[0], confirmButtonText: '确定', cancelButtonText: '取消' },
    )
    const label = String(value || '').trim()
    if (!label) return
    if (used.has(label)) {
      ElMessage.error('该品种已在矩阵中')
      return
    }
    if (options.length && !options.includes(label)) {
      ElMessage.error('品种名须取自「账户/交易」枚举，否则按品种聚合会取不到数据')
      return
    }
    const key = nextH0CategoryKey(categories.value, categorySeq.value)
    categories.value = [...categories.value, { key, label }]
    categorySeq.value = maxH0CategorySeq(categories.value)
    emit('save', H0_MATRIX_SEQ_KEY, String(categorySeq.value))
    persistCategories()
  } catch {
    /* 用户取消 */
  }
}

async function handleRenameCategory(cat: H0MatrixCategory) {
  const options = props.categoryOptions ?? []
  try {
    const { value } = await ElMessageBox.prompt('品种名（须取自「账户/交易」枚举）', '重命名品种', {
      inputValue: cat.label,
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    const label = String(value || '').trim()
    if (!label || label === cat.label) return
    if (categories.value.some((c) => c.key !== cat.key && c.label === label)) {
      ElMessage.error('该品种已在矩阵中')
      return
    }
    if (options.length && !options.includes(label)) {
      ElMessage.error('品种名须取自「账户/交易」枚举，否则按品种聚合会取不到数据')
      return
    }
    categories.value = categories.value.map((c) => (c.key === cat.key ? { ...c, label } : c))
    persistCategories()
  } catch {
    /* 用户取消 */
  }
}

async function handleRemoveCategory(cat: H0MatrixCategory) {
  if (categories.value.length <= 1) {
    ElMessage.warning('至少保留一个品种列')
    return
  }
  try {
    await ElMessageBox.confirm(
      `删除品种「${cat.label}」列？该列的账面金额手工覆盖值会一并清除。`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  categories.value = categories.value.filter((c) => c.key !== cat.key)
  const id = h0MatrixOverrideItemId(cat.key, 0)
  if (id in manualOverrides.value) {
    const next = { ...manualOverrides.value }
    delete next[id]
    manualOverrides.value = next
    emit('save', id, '')
  }
  persistCategories()
}

// ─── 录入落库 ───────────────────────────────────────────────────────────────

function handleBookAmountChange(categoryKey: string, v: number | null) {
  const id = h0MatrixOverrideItemId(categoryKey, 0)
  const next = { ...manualOverrides.value }
  if (v === null || v === undefined || !Number.isFinite(v)) {
    delete next[id]
    manualOverrides.value = next
    emit('save', id, '') // 空值 = 撤销覆盖，回落自动取数
    return
  }
  next[id] = v
  manualOverrides.value = next
  emit('save', id, String(v))
}

function saveSample(key: string) {
  emit('save', h0SampleItemId(key), sampleValues.value[key] ?? '')
}

function saveNote(key: string) {
  emit('save', h0AuditNoteItemId(key), noteValues.value[key] ?? '')
}

function saveConclusion() {
  emit('save', H0_CONCLUSION_KEY, conclusion.value)
}

function applyReference(text: string) {
  conclusion.value = conclusion.value.trim() ? `${conclusion.value.trim()}\n${text}` : text
  saveConclusion()
}

// ─── 只读方法论上下文 ───────────────────────────────────────────────────────

const GUIDANCE_TEXTS = computed(() => getH0TextsForBlock('guidance'))

/** 供外部（宿主 AI 回填）写入审计说明/结论 */
defineExpose({
  applyAiText(key: string, text: string) {
    if (key === 'conclusion') {
      conclusion.value = text
      saveConclusion()
      return
    }
    noteValues.value[key] = text
    saveNote(key)
  },
})
</script>

<style scoped>
.h0-lower {
  margin-top: 20px;
  border-top: 1px solid var(--el-border-color-light);
  padding-top: 14px;
  font-size: 13px;
}
.h0-lower__block {
  margin-bottom: 18px;
}
.h0-lower__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.h0-lower__head-actions {
  margin-left: auto;
  display: flex;
  gap: 6px;
}
.h0-lower__title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--el-text-color-primary);
}
.h0-lower__anchor {
  margin-left: 8px;
  font-size: 11px;
  font-weight: 400;
  color: var(--el-text-color-placeholder);
}
.h0-lower__alert-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
  padding: 6px 10px;
  background: var(--el-color-warning-light-9);
  border-left: 3px solid var(--el-color-warning);
  border-radius: 2px;
}
.h0-lower__matrix :deep(.el-table__cell) {
  font-variant-numeric: tabular-nums;
}
.h0-lower__formula {
  border-bottom: 1px dashed var(--el-color-info);
  cursor: help;
}
.h0-lower__q {
  display: inline-block;
  margin-left: 4px;
  width: 13px;
  height: 13px;
  line-height: 13px;
  text-align: center;
  font-size: 10px;
  border-radius: 50%;
  background: var(--el-color-info-light-7);
  color: var(--el-color-info);
  cursor: help;
}
.h0-lower__cat-head {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}
.h0-lower__cat-ops {
  display: inline-flex;
  gap: 3px;
}
.h0-lower__cat-op {
  cursor: pointer;
  color: var(--el-text-color-placeholder);
  font-size: 11px;
}
.h0-lower__cat-op:hover {
  color: var(--el-color-primary);
}
.h0-lower__val {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.h0-lower__val--auto {
  color: var(--el-color-primary);
}
.h0-lower__val--manual {
  color: var(--el-color-warning-dark-2);
  font-weight: 500;
}
.h0-lower__dash {
  color: var(--el-text-color-placeholder);
  cursor: help;
}
.h0-lower__source {
  margin-top: 10px;
}
.h0-lower__conflict {
  margin-bottom: 8px;
}
.h0-lower__source-note {
  display: block;
  margin-top: 6px;
  line-height: 1.6;
}
.h0-lower__sample-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 10px 14px;
}
.h0-lower__sample-item label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-regular);
  margin-bottom: 3px;
}
.h0-lower__card {
  margin-bottom: 18px;
}
.h0-lower__card :deep(.el-card__header) {
  padding: 10px 14px;
}
.h0-lower__note {
  margin-bottom: 14px;
}
.h0-lower__note-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.h0-lower__hint {
  border-left: 3px solid var(--el-color-warning-light-3);
  background: var(--el-color-warning-light-9);
  padding: 6px 10px;
  margin: 4px 0 6px;
  font-size: 12px;
  line-height: 1.65;
  color: var(--el-text-color-regular);
}
.h0-lower__hint--amber {
  border-left-color: #e6a23c;
  background: #fdf6ec;
}
.h0-lower__hint--ref {
  border-left-color: var(--el-color-primary-light-3);
  background: var(--el-color-primary-light-9);
}
.h0-lower__hint p {
  margin: 0;
}
.h0-lower__ref-title {
  font-weight: 500;
  margin-bottom: 3px;
}
.h0-lower__ref-item {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  line-height: 1.7;
}
.h0-lower__guidance {
  margin-top: 12px;
  font-size: 12px;
}
.h0-lower__guidance summary {
  cursor: pointer;
  color: var(--el-text-color-secondary);
  padding: 4px 0;
}
</style>
