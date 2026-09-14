<template>
  <div class="g0-lower">
    <!-- ══════════ 一、函证情况（品种 × 8 指标矩阵） ══════════ -->
    <section class="g0-lower__block">
      <div class="g0-lower__head">
        <h4 class="g0-lower__title">
          {{ matrixBlock.title }}
          <span class="g0-lower__anchor">源模板 {{ matrixBlock.anchor }}</span>
        </h4>
        <div class="g0-lower__head-actions">
          <el-switch
            v-model="showAllCategories"
            size="small"
            active-text="显示全部品种"
            inline-prompt
            :title="SHOW_ALL_HINT"
          />
          <el-button size="small" :disabled="readonly" @click="handleAddCustomCategory">
            ＋ 新增品种
          </el-button>
          <el-button
            size="small"
            :disabled="readonly"
            :loading="refreshing"
            @click="emit('refresh-book-amounts')"
          >
            🔄 刷新账面金额
          </el-button>
        </div>
      </div>

      <!--
        🔴 取数错误必须有渲染出口：`loadG0MatrixSources` 全程 `_silent`（不弹窗打断录入），
        只收集不显示会让「整条取数链路失效」与「本项目确实没这科目」不可区分
        —— F0 那轮正是它掩盖了 http/apiProxy 形态错用。
      -->
      <el-alert
        v-if="bookErrors.length"
        type="warning"
        show-icon
        :closable="false"
        class="g0-lower__errors"
      >
        <template #title>账面金额取数未完成（{{ bookErrors.length }} 项）</template>
        <div v-for="(e, i) in bookErrors" :key="i" class="g0-lower__error-line">{{ e }}</div>
      </el-alert>

      <el-table
        :data="matrixTableRows"
        border
        size="small"
        class="g0-lower__matrix"
        :empty-text="EMPTY_MATRIX_TEXT"
      >
        <el-table-column prop="label" label="项目" min-width="250" fixed>
          <template #default="{ row }">
            <span :class="{ 'g0-lower__formula': !row.editable }">{{ row.label }}</span>
            <el-tooltip v-if="row.metricHint" placement="top" :content="row.metricHint">
              <span class="g0-lower__q">?</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column
          v-for="cat in visibleCategories"
          :key="cat"
          :label="cat"
          align="right"
          min-width="150"
        >
          <template #header>
            <div class="g0-lower__cat-head">
              <el-tooltip placement="top" :content="categoryTooltip(cat)">
                <span>{{ cat }}</span>
              </el-tooltip>
              <span
                v-if="!readonly && isCustomCategory(cat)"
                class="g0-lower__cat-op"
                title="删除自定义品种"
                @click="handleRemoveCustomCategory(cat)"
              >✕</span>
            </div>
          </template>
          <template #default="{ row }">
            <!-- 账面金额行：可手工录入（手工优先，清空回落自动取数） -->
            <WpAmountInput
              v-if="row.editable && !readonly"
              :model-value="cellOf(row, cat)?.value ?? null"
              :placeholder="bookPlaceholder(cat)"
              size="small"
              @update:model-value="(v: number | null) => handleBookAmountChange(cat, v)"
            />
            <template v-else>
              <el-tooltip
                placement="top"
                :content="cellOf(row, cat)?.sourceHint || ''"
                :disabled="!cellOf(row, cat)?.sourceHint"
              >
                <span :class="cellClass(row, cat)">{{ renderCell(row, cat) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <div class="g0-lower__matrix-note">
        <el-text size="small" type="info">
          发函金额 / 回函确认金额 / 替代测试确认金额均按源模板 SUMIF 公式自上区明细聚合（依次取
          「账面期末余额」「可确认金额」「替代后可确认金额」三列）；账面金额取自相邻 G 循环审定表
          （可手工覆盖）。「-」表示数据缺失，绝不用 0 冒充。
        </el-text>
        <div v-if="bookSourceSummary" class="g0-lower__matrix-note-line">
          <el-text size="small" type="success">{{ bookSourceSummary }}</el-text>
        </div>
        <div v-if="!showAllCategories && hiddenCategories.length" class="g0-lower__matrix-note-line">
          <el-text size="small" type="info">
            已隐藏无内容的品种（{{ hiddenCategories.join('、') }}）—— 打开「显示全部品种」即可为其录入账面金额。
          </el-text>
        </div>
      </div>
    </section>

    <!-- ══════════ 三、审计说明（5 项） ══════════ -->
    <el-card class="g0-lower__card" shadow="never">
      <template #header>
        <h4 class="g0-lower__title">
          {{ auditNoteBlock.title }}
          <span class="g0-lower__anchor">源模板 {{ auditNoteBlock.anchor }}</span>
        </h4>
      </template>

      <div v-for="d in AUDIT_NOTE_DEFS" :key="d.key" class="g0-lower__note">
        <div class="g0-lower__head">
          <div class="g0-lower__note-title">
            {{ d.title }}
            <!--
              源模板此项标题的交叉引用写「（G0-6）」实为笔误（回函可靠性验证表是 G0-7）。
              R10.3：标题**逐字保留原文** + 加标注，不静默修正。
            -->
            <el-tooltip v-if="defectNoteOf(d.key)" placement="top" :content="defectNoteOf(d.key)">
              <span class="g0-lower__typo">源模板笔误</span>
            </el-tooltip>
          </div>
          <div class="g0-lower__head-actions">
            <el-button
              size="small"
              :disabled="readonly"
              :loading="aiLoadingKey === d.key"
              @click="emit('ai-generate', d.aiSection, d.key)"
            >
              🤖 AI 辅助
            </el-button>
            <GtReviewTrigger :section-id="d.reviewSectionId" label="💬 复核" />
          </div>
        </div>
        <!-- 只读提示语（琥珀色方法论上下文）—— 与小标题是两个角色，不拼接 -->
        <div v-if="d.hint" class="g0-lower__hint">{{ d.hint }}</div>
        <el-input
          v-model="noteValues[d.key]"
          type="textarea"
          :autosize="{ minRows: 4 }"
          :disabled="readonly"
          :placeholder="notePlaceholder(d.title)"
          @change="saveNote(d.key)"
        />
      </div>
    </el-card>

    <!-- ══════════ 四、审计结论 ══════════ -->
    <el-card class="g0-lower__card" shadow="never">
      <template #header>
        <div class="g0-lower__head">
          <h4 class="g0-lower__title">
            {{ conclusionBlock.title }}
            <span class="g0-lower__anchor">源模板 {{ conclusionBlock.anchor }}</span>
          </h4>
          <div class="g0-lower__head-actions">
            <el-dropdown :disabled="readonly" trigger="click" @command="applyRefConclusion">
              <el-button size="small" :disabled="readonly">
                套用参考结论
                <span class="g0-lower__caret">▾</span>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="r in REF_CONCLUSIONS"
                    :key="r.code"
                    :command="r.code"
                  >
                    <b>{{ r.code }}、</b>{{ r.text }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button
              size="small"
              :disabled="readonly"
              :loading="aiLoadingKey === CONCLUSION_KEY_LOCAL"
              @click="emit('ai-generate', CONCLUSION_AI_SECTION, CONCLUSION_KEY_LOCAL)"
            >
              🤖 AI 辅助
            </el-button>
            <GtReviewTrigger :section-id="CONCLUSION_REVIEW_SECTION_ID" label="💬 复核" />
          </div>
        </div>
      </template>

      <div class="g0-lower__hint g0-lower__hint--ref">
        <div class="g0-lower__ref-title">{{ REF_CONCLUSION_HEADING.text }}（源模板 {{ REF_CONCLUSION_HEADING.anchor }}）</div>
        <div v-for="r in REF_CONCLUSIONS" :key="r.code" class="g0-lower__ref-item">
          <el-tag size="small" effect="plain" class="g0-lower__ref-tag" @click="applyRefConclusion(r.code)">
            {{ r.code }}
          </el-tag>
          <span>{{ r.text }}</span>
        </div>
      </div>

      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="readonly"
        placeholder="请填写审计结论（可点击上方 A/B/C 一键套用源模板参考结论后再修改）"
        @change="saveConclusion"
      />
    </el-card>

    <!-- ══════════ 源模板已知缺陷（只读折叠，Task 20 / R10.2~10.3） ══════════ -->
    <details class="g0-lower__guidance">
      <summary>
        源模板已知缺陷（{{ SOURCE_DEFECTS.length }} 项）—— 平台按意图实现，逐条可追溯
      </summary>
      <div v-for="d in SOURCE_DEFECTS" :key="d.id" class="g0-lower__hint g0-lower__hint--amber">
        <p class="g0-lower__guidance-line">
          <b>{{ DEFECT_HANDLING_LABEL[d.handling] }}</b>
          <span class="g0-lower__anchor">源模板 {{ d.anchor }}</span>
        </p>
        <p class="g0-lower__guidance-line">源模板事实：{{ d.defect }}</p>
        <p class="g0-lower__guidance-line">正确意图：{{ d.intent }}（判据：{{ d.intentEvidence }}）</p>
        <p class="g0-lower__guidance-line">平台处置：{{ d.uiNote }}</p>
      </div>
    </details>

    <!-- ══════════ 编制说明（只读折叠） ══════════ -->
    <details class="g0-lower__guidance">
      <summary>编制说明（准则 1312 第十条选样要求 · 函证注意事项 8 条 · 参考结论 · 后附审计证据）</summary>
      <div
        v-for="note in PREPARATION_NOTES"
        :key="note.key"
        class="g0-lower__hint g0-lower__hint--amber"
      >
        <p v-for="(line, i) in note.lines" :key="i" class="g0-lower__guidance-line">{{ line.text }}</p>
        <span class="g0-lower__anchor">源模板 {{ note.lines[0].anchor }}{{ note.lines.length > 1 ? `~${note.lines[note.lines.length - 1].anchor}` : '' }}</span>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G0SummaryLowerZone.vue — G0-1 函证结果汇总表下区专属组件
 *
 * spec: g0-confirmation-source-alignment，Task 8/9（Requirement 3.1~3.5 / 3.7~3.11）
 *
 * 渲染四部分：**一、函证情况（矩阵）· 三、审计说明 · 四、审计结论 · 编制说明**
 *
 * 🔴🔴 本组件**绝不渲染「二、样本选择」** —— 那由 `confirmation/ConfirmationSampling.vue`
 * （Task 13，`isG0` → 6 项）承担。`GtConfirmationSummary.vue` 已有一处
 * `<ConfirmationSampling :data="data.sampling.value">`，其持久化就是 `G0-1-sampling`
 * （`SamplingConfig` JSON）；这里再渲染一份就是「同一 item_id 两套口径同写」的双真源。
 * 守卫按源码断言本文件不含 6 个 sampling 字段任一的 `v-model`。
 *
 * 🔴 收敛锚点（裁决门 D = D-2）：本组件属
 * `CONVERGENCE_TARGET = 'confirmation-summary-lower-zone-convergence'` 副本族
 * （E0/H0/G0 各一份）。收敛 spec 靠 grep 该字面量定位全量清单，勿删勿改名。
 *
 * 🔴 三条踩坑预防（本文件逐条落实）：
 * 1. `fmtAmount` 是 **store 成员**不是模块级导出 → setup 顶层
 *    `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`（写进函数体会静默失效）。
 * 2. 可编辑金额只能用 `WpAmountInput`（EP 2.13.6 的 `el-input-number` 无 `formatter` prop）；
 *    比例/数量行不套用。
 * 3. `watch(...)` 的依赖在 setup 期求值 → 全部被引用的 ref **必须先声明**（TDZ 会让整组件挂不上）。
 *
 * 🔴 账面金额三级优先级：`用户手工编辑值` > `语义定位值（相邻 Gx 的 tb_amount）` > `prefill 种子`。
 * `responses` 必须由宿主从 **`/checklist-responses`（已持久化）** 拉取，
 * **不得**取自 `html_data.responses_snapshot` —— 后者含 Tier A 公式预设的 transient 种子，
 * 一旦被 `parseG0ManualOverrides` 当成手工覆盖，`TB('1504')` 等 5 个恒空品种就会把
 * 「本项目无此科目」压成假 0（`Number(null) === 0` 同族坑）。
 */
import { computed, inject, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import WpAmountInput from '../shared/WpAmountInput.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import type { ConfirmationRow } from '../confirmation/confirmationTypes'
import {
  buildG0SummaryMatrix,
  G0_CATEGORY_NAMES,
  G0_CUSTOM_CATEGORY_HINT,
  G0_MATRIX_CATEGORIES,
  G0_MATRIX_METRICS,
  visibleG0Categories,
  type G0MatrixCell,
  type G0MetricKey,
} from './g0SummaryMatrix'
import {
  g0MatrixOverrideItemId,
  parseG0ManualOverrides,
  type G0SourceDiagnostics,
} from './g0MatrixDataSources'
import {
  getG0LowerBlock,
  g0AuditNoteItemId,
  G0_AUDIT_NOTE_DEFS as AUDIT_NOTE_DEFS,
  G0_CONCLUSION_AI_SECTION as CONCLUSION_AI_SECTION,
  G0_CONCLUSION_KEY,
  G0_CONCLUSION_REVIEW_SECTION_ID as CONCLUSION_REVIEW_SECTION_ID,
  G0_PREPARATION_NOTES as PREPARATION_NOTES,
  G0_REF_CONCLUSION_HEADING as REF_CONCLUSION_HEADING,
  G0_REF_CONCLUSIONS as REF_CONCLUSIONS,
} from './g0SummaryLowerZone'
import {
  G0_SOURCE_DEFECTS as SOURCE_DEFECTS,
  g0DefectUiNote,
  type G0DefectHandling,
} from './g0SourceDefects'

const props = defineProps<{
  /** G0-1 上区明细行（矩阵按品种 SUMIF 的数据源） */
  rows: readonly ConfirmationRow[]
  readonly: boolean
  /**
   * 已**持久化**的 checklist responses（itemId → value）。
   * 🔴 必须来自 `/checklist-responses`，不得来自 `responses_snapshot`（含 prefill 种子）。
   */
  responses?: Record<string, string>
  /** 相邻 G 循环 render-config 的 `project_context.tb_amount`（缺该品种 = 键不存在 ≠ 0） */
  bookAmounts?: Record<string, number>
  /** 取数诊断（错误必须渲染，不能只收集） */
  diagnostics?: G0SourceDiagnostics
  refreshing?: boolean
  aiLoadingKey?: string | null
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: string): void
  (e: 'ai-generate', aiSection: string, key: string): void
  (e: 'refresh-book-amounts'): void
}>()

// 🔴 金额格式单一真源 = displayPrefs.fmtAmount（**store 成员，不是模块级导出**）。
//    必须在 setup 顶层取：写进函数体会静默失效。
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// ─── 常量 ───────────────────────────────────────────────────────────────────

const EMPTY_MATRIX_TEXT = '请先在上方明细表录入函证行（矩阵按「账户/交易」列分品种聚合）'
const SHOW_ALL_HINT =
  '默认只显示「有内容」的品种（上区有该品种行 / 取到账面金额 / 有手工值）。打开本开关可显示全部候选品种，以便为尚无数据的品种录入账面金额。'
const CONCLUSION_KEY_LOCAL = 'conclusion'

const matrixBlock = getG0LowerBlock('matrix')
const auditNoteBlock = getG0LowerBlock('audit_note')
const conclusionBlock = getG0LowerBlock('conclusion')

/** 源缺陷处置方式的中文标签（UI 全中文化铁律） */
const DEFECT_HANDLING_LABEL: Readonly<Record<G0DefectHandling, string>> = {
  'implement-intent': '按意图实现（平台不复现该缺陷）',
  'display-as-is': '原文保留 + 加标注',
  'index-label-correction': '定位用 tab 名 / 展示用目录索引号',
}

/**
 * 审计说明某项的源缺陷标注（目前只有第 3 项 `reliability` 的 S24 交叉引用笔误）。
 * 🔴 按 `G0_AUDIT_NOTE_DEFS[].key` 映射而非写死序号 —— 序号变了标注不会跟着串位。
 */
const AUDIT_NOTE_DEFECT_ID: Readonly<Record<string, string>> = { reliability: 'xref-reliability' }

function defectNoteOf(noteKey: string): string {
  const id = AUDIT_NOTE_DEFECT_ID[noteKey]
  return id ? g0DefectUiNote(id) : ''
}

/** 自定义品种持久化键（源 `H20` 的 `……` 可扩位；R3.2.5） */
const CUSTOM_CATEGORIES_KEY = 'G0-1-lower-custom-categories'

// ─── 状态（🔴 全部 ref 必须声明在下方 watch 之前 —— TDZ） ────────────────────

const showAllCategories = ref(false)
const customCategories = ref<string[]>([])
const noteValues = ref<Record<string, string>>({})
const conclusion = ref('')
const manualOverrides = ref<Record<string, number>>({})

watch(
  () => props.responses,
  (r) => {
    const src = r ?? {}
    customCategories.value = parseCustomCategories(src[CUSTOM_CATEGORIES_KEY])
    for (const d of AUDIT_NOTE_DEFS) {
      noteValues.value[d.key] = src[g0AuditNoteItemId(d.seq)] ?? ''
    }
    conclusion.value = src[G0_CONCLUSION_KEY] ?? ''
    // 手工覆盖只从已持久化 responses 解析（见文件头「三级优先级」说明）
    manualOverrides.value = parseG0ManualOverrides(src, allCategoryNames())
  },
  { immediate: true, deep: false },
)

function parseCustomCategories(raw: unknown): string[] {
  if (typeof raw !== 'string' || !raw.trim()) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((x) => String(x).trim()).filter((x) => x && !G0_CATEGORY_NAMES.includes(x))
  } catch {
    return []
  }
}

/** 候选全集 + 自定义品种（非响应式读法，供 watch 内使用） */
function allCategoryNames(): string[] {
  return [...G0_CATEGORY_NAMES, ...customCategories.value]
}

// ─── 矩阵 ───────────────────────────────────────────────────────────────────

const allCategories = computed<string[]>(() => [...G0_CATEGORY_NAMES, ...customCategories.value])

const visibleCategories = computed<string[]>(() =>
  visibleG0Categories({
    rows: props.rows,
    bookAmounts: props.bookAmounts,
    manualOverrides: manualOverrides.value,
    categories: allCategories.value,
    showAll: showAllCategories.value,
  }),
)

const hiddenCategories = computed<string[]>(() => {
  const visible = new Set(visibleCategories.value)
  return allCategories.value.filter((c) => !visible.has(c))
})

/** 矩阵按**可见品种**计算（隐藏是渲染层概念，不清除已录入值 — R3.2.6） */
const matrix = computed<G0MatrixCell[][]>(() =>
  buildG0SummaryMatrix({
    rows: props.rows,
    bookAmounts: props.bookAmounts,
    manualOverrides: manualOverrides.value,
    categories: visibleCategories.value,
  }),
)

interface MatrixTableRow {
  label: string
  metric: G0MetricKey
  kind: 'amount' | 'ratio'
  editable: boolean
  metricHint?: string
  cells: Record<string, G0MatrixCell>
}

const matrixTableRows = computed<MatrixTableRow[]>(() =>
  G0_MATRIX_METRICS.map((def, metricIdx) => {
    const cells: Record<string, G0MatrixCell> = {}
    visibleCategories.value.forEach((cat, catIdx) => {
      const cell = matrix.value[catIdx]?.[metricIdx]
      if (cell) cells[cat] = cell
    })
    return {
      label: def.label,
      metric: def.key,
      kind: def.kind,
      editable: def.editable,
      metricHint: metricHint(def.key, cells),
      cells,
    }
  }),
)

function metricHint(metric: G0MetricKey, cells: Record<string, G0MatrixCell>): string | undefined {
  if (metric === 'book_amount') return undefined
  const first = Object.values(cells)[0]
  return first?.sourceHint || '按源模板公式自上区明细聚合'
}

function cellOf(row: MatrixTableRow, category: string): G0MatrixCell | undefined {
  return row.cells[category]
}

function renderCell(row: MatrixTableRow, category: string): string {
  const cell = row.cells[category]
  if (!cell || cell.value === null || cell.value === undefined) return '-'
  if (row.kind === 'ratio') return `${(cell.value * 100).toFixed(2)}%`
  return displayPrefs.fmtAmount(cell.value)
}

function cellClass(row: MatrixTableRow, category: string): string {
  const cell = row.cells[category]
  if (!cell || cell.value === null) return 'g0-lower__dash'
  if (cell.isManual) return 'g0-lower__val g0-lower__val--manual'
  if (row.metric === 'book_amount') return 'g0-lower__val g0-lower__val--auto'
  return 'g0-lower__val'
}

/** 品种列表头 tooltip：溯源（报表行 + 科目码只在 hint 里出现） */
function categoryTooltip(category: string): string {
  const def = G0_MATRIX_CATEGORIES.find((c) => c.name === category)
  if (def) return `账面金额来源：${def.book.hint}`
  return G0_CUSTOM_CATEGORY_HINT
}

function isCustomCategory(category: string): boolean {
  return !G0_CATEGORY_NAMES.includes(category)
}

/**
 * 账面金额输入框 placeholder。
 *
 * 🔴 三态必须分开（Requirement 4.3）：**「本项目无此科目」是业务事实**（后端
 * `resolved_from='none'`），**「未取数」是待补编制**（相邻审定表还没编 / 取数失败）。
 * 改造前两者共用「本项目无此科目」一句话 —— 会让审计师把「G7 审定表没编」误读成
 * 「公司没有长期股权投资」。
 */
function bookPlaceholder(category: string): string {
  if (props.bookAmounts && category in props.bookAmounts) return '自动取数（可覆盖）'
  if (props.diagnostics?.bookAbsent?.includes(category)) return '本项目无此科目，可手填'
  if (props.diagnostics?.bookMissing.includes(category)) return '未取数（审定表未编制？），可手填'
  return '未取数，可手填'
}

/** 账面金额取数状态摘要 */
const bookSourceSummary = computed(() => {
  const d = props.diagnostics
  if (!d) return ''
  const absent = new Set(d.bookAbsent ?? [])
  const pending = d.bookMissing.filter((c) => !absent.has(c))
  const parts: string[] = []
  if (d.bookResolved.length) parts.push(`已取数：${d.bookResolved.join('、')}`)
  if (absent.size) parts.push(`本项目无此科目：${[...absent].join('、')}`)
  if (pending.length) parts.push(`待手工填写：${pending.join('、')}`)
  return parts.join('　|　')
})

const bookErrors = computed<string[]>(() => props.diagnostics?.errors ?? [])

// ─── 账面金额手工覆盖 ───────────────────────────────────────────────────────

function handleBookAmountChange(category: string, v: number | null) {
  const itemId = g0MatrixOverrideItemId(category, 'book_amount')
  const key = `${category}::book_amount`
  const next = { ...manualOverrides.value }
  if (v === null || v === undefined || !Number.isFinite(v)) {
    delete next[key]
    manualOverrides.value = next
    emit('save', itemId, '') // 空值 = 撤销覆盖，回落自动取数
    return
  }
  next[key] = v
  manualOverrides.value = next
  emit('save', itemId, String(v))
}

// ─── 自定义品种（源 H20 的 `……` 可扩位） ────────────────────────────────────

function persistCustomCategories() {
  emit('save', CUSTOM_CATEGORIES_KEY, JSON.stringify(customCategories.value))
}

async function handleAddCustomCategory() {
  try {
    const { value } = await ElMessageBox.prompt(G0_CUSTOM_CATEGORY_HINT, '新增品种', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '请输入品种名称（须与上区「账户/交易」取值一致）',
    })
    const name = String(value || '').trim()
    if (!name) return
    if (allCategories.value.includes(name)) {
      ElMessage.error('该品种已在矩阵中')
      return
    }
    customCategories.value = [...customCategories.value, name]
    persistCustomCategories()
  } catch {
    /* 用户取消 */
  }
}

async function handleRemoveCustomCategory(category: string) {
  try {
    await ElMessageBox.confirm(
      `删除自定义品种「${category}」？该列的账面金额手工覆盖值会一并清除。`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  customCategories.value = customCategories.value.filter((c) => c !== category)
  const key = `${category}::book_amount`
  if (key in manualOverrides.value) {
    const next = { ...manualOverrides.value }
    delete next[key]
    manualOverrides.value = next
    emit('save', g0MatrixOverrideItemId(category, 'book_amount'), '')
  }
  persistCustomCategories()
}

// ─── 审计说明 / 结论落库 ────────────────────────────────────────────────────

function notePlaceholder(title: string): string {
  return `请填写「${title.replace(/^\d+、/, '')}」的内容`
}

function saveNote(key: string) {
  const def = AUDIT_NOTE_DEFS.find((d) => d.key === key)
  if (!def) return
  emit('save', g0AuditNoteItemId(def.seq), noteValues.value[key] ?? '')
}

function saveConclusion() {
  emit('save', G0_CONCLUSION_KEY, conclusion.value)
}

/** 参考结论一键套用（已有内容时先确认，避免覆盖审计师已写内容） */
async function applyRefConclusion(code: string | number | object) {
  const ref0 = REF_CONCLUSIONS.find((r) => r.code === code)
  if (!ref0) return
  const current = conclusion.value.trim()
  if (!current) {
    conclusion.value = ref0.text
    saveConclusion()
    return
  }
  let mode: 'replace' | 'append' = 'replace'
  try {
    await ElMessageBox.confirm(
      `审计结论已有内容。「覆盖」用参考结论 ${ref0.code} 替换现有内容；「追加」在末尾另起一行插入。`,
      '套用参考结论',
      {
        confirmButtonText: '覆盖',
        cancelButtonText: '追加',
        distinguishCancelAndClose: true,
        type: 'warning',
      },
    )
  } catch (e: unknown) {
    if (e === 'close' || String(e) === 'close') return // 右上角关闭 = 取消
    mode = 'append'
  }
  conclusion.value = mode === 'replace' ? ref0.text : `${current}\n${ref0.text}`
  saveConclusion()
}

// ─── 供宿主 AI 回填 ─────────────────────────────────────────────────────────

defineExpose({
  applyAiText(key: string, text: string) {
    if (key === CONCLUSION_KEY_LOCAL) {
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
.g0-lower {
  margin-top: 20px;
  border-top: 1px solid var(--el-border-color-light);
  padding-top: 14px;
  font-size: 13px;
}
.g0-lower__block {
  margin-bottom: 18px;
}
.g0-lower__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.g0-lower__head-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
}
.g0-lower__title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--el-text-color-primary);
}
.g0-lower__anchor {
  margin-left: 8px;
  font-size: 11px;
  font-weight: 400;
  color: var(--el-text-color-placeholder);
}
.g0-lower__errors {
  margin-bottom: 8px;
}
.g0-lower__error-line {
  font-size: 12px;
  line-height: 1.6;
}
.g0-lower__matrix :deep(.el-table__cell) {
  font-variant-numeric: tabular-nums;
}
.g0-lower__formula {
  border-bottom: 1px dashed var(--el-color-info);
  cursor: help;
}
.g0-lower__q {
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
.g0-lower__cat-head {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}
.g0-lower__cat-op {
  cursor: pointer;
  color: var(--el-text-color-placeholder);
  font-size: 11px;
}
.g0-lower__cat-op:hover {
  color: var(--el-color-danger);
}
.g0-lower__val {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.g0-lower__val--auto {
  color: var(--el-color-primary);
}
.g0-lower__val--manual {
  color: var(--el-color-warning-dark-2);
  font-weight: 500;
}
.g0-lower__dash {
  color: var(--el-text-color-placeholder);
  cursor: help;
}
.g0-lower__matrix-note {
  margin-top: 6px;
  line-height: 1.6;
}
.g0-lower__matrix-note-line {
  margin-top: 4px;
}
.g0-lower__card {
  margin-bottom: 18px;
}
.g0-lower__card :deep(.el-card__header) {
  padding: 10px 14px;
}
.g0-lower__note {
  margin-bottom: 14px;
}
.g0-lower__note-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}
.g0-lower__typo {
  margin-left: 6px;
  padding: 0 5px;
  font-size: 11px;
  font-weight: 400;
  border-radius: 2px;
  border: 1px dashed #e6a23c;
  background: #fdf6ec;
  color: #b88230;
  cursor: help;
}
.g0-lower__hint {
  border-left: 3px solid var(--el-color-warning-light-3);
  background: var(--el-color-warning-light-9);
  padding: 6px 10px;
  margin: 4px 0 6px;
  font-size: 12px;
  line-height: 1.65;
  color: var(--el-text-color-regular);
}
.g0-lower__hint--amber {
  border-left-color: #e6a23c;
  background: #fdf6ec;
}
.g0-lower__hint--ref {
  border-left-color: var(--el-color-primary-light-3);
  background: var(--el-color-primary-light-9);
}
.g0-lower__ref-title {
  font-weight: 500;
  margin-bottom: 3px;
}
.g0-lower__ref-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  line-height: 1.9;
}
.g0-lower__ref-tag {
  cursor: pointer;
}
.g0-lower__caret {
  margin-left: 2px;
}
.g0-lower__guidance {
  margin-top: 12px;
  font-size: 12px;
}
.g0-lower__guidance summary {
  cursor: pointer;
  color: var(--el-text-color-secondary);
  padding: 4px 0;
}
.g0-lower__guidance-line {
  margin: 0;
  white-space: pre-wrap;
}
</style>
