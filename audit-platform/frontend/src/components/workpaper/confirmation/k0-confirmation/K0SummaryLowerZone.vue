<template>
  <div class="k0-lower">
    <!-- ═══ 一、函证情况（2 品种 × 8 指标） ═══════════════════════════════ -->
    <section class="k0-lower__section">
      <div class="k0-lower__title">
        <span>{{ titleOf('matrix') }}</span>
        <span class="k0-lower__anchor">源模板 {{ anchorOf('matrix') }}</span>
        <el-button
          v-if="!readonly"
          size="small"
          :loading="refreshing"
          style="margin-left:auto"
          @click="emit('refresh-book-amounts')"
        >
          🔄 刷新账面金额
        </el-button>
      </div>

      <!-- 取数诊断：🔴 必须渲染，不能只收集（F0 那轮的教训：被吞掉的错误让
           「链路失效」与「本项目确实没这科目」不可区分，掩盖了一个 P0） -->
      <el-alert
        v-if="diagErrors.length"
        type="warning"
        :closable="false"
        show-icon
        class="k0-lower__alert"
      >
        <template #title>账面金额取数提示</template>
        <ul class="k0-lower__diag">
          <li v-for="(e, i) in diagErrors" :key="`err-${i}`">{{ e }}</li>
        </ul>
      </el-alert>
      <el-alert
        v-if="diagKnownGaps.length"
        type="error"
        :closable="false"
        show-icon
        class="k0-lower__alert"
      >
        <template #title>已登记的取数口径缺口（请与相邻循环审定表核对）</template>
        <ul class="k0-lower__diag">
          <li v-for="(g, i) in diagKnownGaps" :key="`gap-${i}`">{{ g }}</li>
        </ul>
      </el-alert>

      <el-table :data="matrixTableData" border size="small" style="width:100%">
        <el-table-column prop="label" :label="LABEL_HEADER" min-width="260">
          <template #default="{ row }">
            <span>{{ row.label }}</span>
            <span class="k0-lower__anchor">{{ row.anchor }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-for="cat in CATEGORY_NAMES"
          :key="cat"
          align="right"
          min-width="180"
        >
          <template #header>
            <el-tooltip :content="bookHintOf(cat)" placement="top">
              <span class="k0-lower__cat-head">{{ cat }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <!-- 账面金额行：可手工覆盖（源 R29 无公式 = 手填），手工值优先 -->
            <WpAmountInput
              v-if="row.metric === 'book_amount' && !readonly"
              :model-value="editableBookValue(cat)"
              :placeholder="bookStateTextOf(cat) || '请输入'"
              size="small"
              @update:model-value="(v: number | null) => onBookAmountInput(cat, v)"
            />
            <span v-else-if="row.metric === 'book_amount'" class="k0-lower__amount">
              {{ bookDisplayOf(cat) }}
            </span>
            <span v-else class="k0-lower__amount">{{ cellText(cat, row.metric) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="k0-lower__hint">
        本区按上区明细表「账户/交易」列分品种聚合（源模板
        <code>SUMIF(E7:E26, 品种, F|U|Y)</code> 口径，不叠「相符」过滤）；
        账面金额自动取数后仍可手工覆盖，覆盖值优先。
      </div>
      <div v-if="!rows.length" class="k0-lower__empty">{{ EMPTY_MATRIX_TEXT }}</div>
      <div v-else-if="unclassifiedCount > 0" class="k0-lower__empty">
        有 {{ unclassifiedCount }} 行「账户/交易」不在「{{ CATEGORY_NAMES.join(' / ') }}」内，
        <strong>不计入函证情况</strong>（请核对分类键是否与源模板一致）。
      </div>
    </section>

    <!--
      ═══ 二、样本选择 ═══
      🔴 **不在本组件内渲染** —— 由共享 `ConfirmationSampling`（`isK0` → 源模板 6 项）承担，
         持久化目标是 `SamplingData`。两处都渲染 = 同一份 `SamplingData` 有两个录入口（双真源）。
         判据固化在 `k0LowerZoneSpec.K0_LOWER_ZONE_BLOCKS` 的 `renderedHere: false`。
    -->

    <!-- ═══ 三、审计说明（5 项，源 S28/X28/S32/X32/S36） ═════════════════ -->
    <section class="k0-lower__section">
      <div class="k0-lower__title">
        <span>{{ titleOf('audit_note') }}</span>
        <span class="k0-lower__anchor">源模板 {{ anchorOf('audit_note') }}</span>
      </div>
      <el-form label-position="top" size="small">
        <el-form-item v-for="note in AUDIT_NOTES" :key="note.key">
          <template #label>
            <span class="k0-lower__field-label">
              <span>{{ note.label }}</span>
              <el-tooltip
                v-if="typoOf(note)"
                :content="typoOf(note)"
                placement="top"
              >
                <el-tag size="small" type="warning" effect="plain">源模板索引号笔误</el-tag>
              </el-tooltip>
              <el-tag v-if="note.aliasOf" size="small" type="info" effect="plain">
                引用「审计说明」区既有内容
              </el-tag>
              <span class="k0-lower__anchor">{{ note.labelAnchor }}</span>
              <el-button
                v-if="!readonly && !note.aliasOf"
                size="small"
                :loading="aiLoadingKey === itemIdOf(note)"
                @click="emit('ai-generate', note.aiSection, itemIdOf(note))"
              >
                🤖 AI 辅助
              </el-button>
              <GtReviewTrigger :section-id="note.reviewSectionId" label="💬 复核" />
            </span>
          </template>

          <!-- aliasOf 项：只读引用既有共享字段，不重复录入（R3.8） -->
          <div v-if="note.aliasOf" class="k0-lower__alias">
            <div class="k0-lower__alias-text">{{ aliasTextOf(note) || '（下方「审计说明」区尚未填写「替代程序」）' }}</div>
            <div class="k0-lower__alias-tip">
              本项与下方「审计说明」区的「替代程序」为同一内容，请在那里编辑（避免两处录入）。
            </div>
          </div>

          <el-input
            v-else
            :model-value="textValues[itemIdOf(note)] ?? ''"
            type="textarea"
            :autosize="{ minRows: 3 }"
            :placeholder="`请撰写${note.label.replace(/^\d+\./, '')}`"
            :disabled="readonly"
            @input="(v: string) => onTextInput(itemIdOf(note), v)"
          />

          <!-- 只读提示语（源模板独立格；🔴 绝不与标题拼接，否则出错句） -->
          <div v-if="note.inlineHint" class="k0-lower__src-hint">
            {{ note.inlineHint }}
            <span class="k0-lower__anchor">源模板 {{ note.inlineHintAnchor }}</span>
          </div>
        </el-form-item>
      </el-form>
    </section>

    <!-- ═══ 四、审计结论 ════════════════════════════════════════════════ -->
    <section class="k0-lower__section">
      <div class="k0-lower__title">
        <span>{{ titleOf('conclusion') }}</span>
        <span class="k0-lower__anchor">源模板 {{ anchorOf('conclusion') }}</span>
        <el-button
          v-if="!readonly"
          size="small"
          :loading="aiLoadingKey === CONCLUSION_KEY"
          style="margin-left:auto"
          @click="emit('ai-generate', CONCLUSION_AI_SECTION, CONCLUSION_KEY)"
        >
          🤖 AI 辅助
        </el-button>
        <GtReviewTrigger :section-id="CONCLUSION_REVIEW_SECTION_ID" label="💬 复核" />
      </div>

      <el-input
        :model-value="textValues[CONCLUSION_KEY] ?? ''"
        type="textarea"
        :autosize="{ minRows: 4 }"
        placeholder="结合上表三项覆盖率、不符事项与未回函替代程序结果，撰写本次函证程序的审计结论"
        :disabled="readonly"
        @input="(v: string) => onTextInput(CONCLUSION_KEY, v)"
      />

      <!-- 参考结论 A/B/C（源 B64:B66，内容在 B 列；A 列只是 `A、`/`B、`/`C、` 标签） -->
      <el-card shadow="never" class="k0-lower__ref">
        <template #header>
          <span class="k0-lower__ref-title">参考结论（源模板 B64:B66，可一键套用）</span>
        </template>
        <div v-for="c in REF_CONCLUSIONS" :key="c.code" class="k0-lower__ref-row">
          <el-tag size="small" effect="plain">{{ c.code }}</el-tag>
          <span class="k0-lower__ref-text">{{ c.text }}</span>
          <span class="k0-lower__anchor">{{ c.anchor }}</span>
          <el-button v-if="!readonly" link size="small" @click="applyRefConclusion(c.text)">
            套用
          </el-button>
        </div>
      </el-card>
    </section>

    <!-- ═══ 编制说明（只读方法论上下文，折叠置底） ═══════════════════════ -->
    <details class="k0-lower__guidance">
      <summary>编制说明（源模板 A40 / A42~A67，只读）</summary>
      <div v-for="blk in GUIDANCE_BLOCKS" :key="blk.key" class="k0-lower__guidance-block">
        <div class="k0-lower__guidance-heading">{{ blk.heading }}</div>
        <ul class="k0-lower__guidance-list">
          <li v-for="(line, i) in blk.lines" :key="`${blk.key}-${i}`">
            {{ line.text }}
            <span class="k0-lower__anchor">{{ line.anchor }}</span>
          </li>
        </ul>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K0SummaryLowerZone.vue — K0-1 下区（函证情况 / 审计说明 / 审计结论 / 编制说明）
 *
 * spec: k0-confirmation-source-alignment · Task 10
 *   Requirements 3.1 / 3.2 / 3.3 / 3.4 / 3.5 / 3.7 / 3.10 / 3.11 / 3.12
 *   Property 22（金额单一真源）/ Property 23（可编辑金额控件选型）
 *
 * 🔴 **「二、样本选择」不在本组件** —— 由共享 `ConfirmationSampling`（`isK0` → 源模板 6 项）
 * 承担，持久化目标是 `SamplingData`。两处都渲染 = 同一份数据两个录入口（双真源）。
 * 判据固化在 `k0LowerZoneSpec.K0_LOWER_ZONE_BLOCKS` 的 `renderedHere` 字段。
 *
 * 🔴 三条平台铁律在本组件的落法：
 * 1. **`fmtAmount` 是 store 成员不是模块级导出** → setup 顶层
 *    `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`。
 *    写 `import { fmtAmount } from '@/stores/displayPrefs'` 会让整页崩成
 *    「does not provide an export named 'fmtAmount'」（`get_diagnostics` 与 vitest 全绿，
 *    只有浏览器暴露）；`useDisplayPrefsStore()` 写进函数体则静默失效。
 * 2. **可编辑金额只能用 `WpAmountInput`** —— EP 2.13.6 的 `el-input-number` **没有**
 *    `formatter` prop（源码级实证），千分符从未生效。
 * 3. **下区录入直接 `emit('save', itemId, value)`**，由宿主走
 *    `PUT /api/workpapers/{id}/checklist-responses`。**绝不能**走 sheet 级 save 通道 ——
 *    那会把整个 sheet 的 `html_data` 覆盖成 `{itemId, value}`，一次点击就丢掉上区函证行
 *    并让该 sheet 退化成「旧格式只读」（G0 侧已浏览器实测复现）。
 *
 * 🔴 `responses` 必须由宿主从 **`/checklist-responses`（已持久化）** 拉，
 * 不得来自 `responses_snapshot` —— 后者含 Tier A 公式预设的 transient 种子，
 * 被当成手工覆盖会把「本项目无此科目」压成假 0。
 */
import { computed, inject, ref, watch } from 'vue'

import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import WpAmountInput from '../../shared/WpAmountInput.vue'
// 🔴 `GtReviewTrigger.vue` 在 `components/workpaper/` 根，不在 `confirmation/` 下 →
//    必须回退**两级**。写 `'../GtReviewTrigger.vue'` 会让 Vite transform 500
//    （`Failed to resolve import`），而 `get_diagnostics` 与 vitest 全绿 —— 本轮实测踩过。
import GtReviewTrigger from '../../GtReviewTrigger.vue'

import type { ConfirmationRow } from '../confirmationTypes'
import { K0_MATRIX_CATEGORIES } from './k0MatrixSpec'
import {
  K0_MATRIX_CATEGORY_NAMES,
  K0_MATRIX_LABEL_HEADER,
  K0_MATRIX_METRICS,
  buildK0SummaryMatrix,
  countK0UnclassifiedRows,
  pickK0MatrixCell,
  type K0MatrixCell,
  type K0MetricKey,
} from './k0SummaryMatrix'
import {
  bookAmountOverrideItemId,
  buildK0BookAmountViews,
  type K0BookAmountView,
  type K0MatrixDiagnostics,
} from './k0MatrixDataSources'
import {
  K0_AUDIT_NOTES,
  K0_CONCLUSION_AI_SECTION,
  K0_CONCLUSION_KEY,
  K0_CONCLUSION_REVIEW_SECTION_ID,
  K0_GUIDANCE_BLOCKS,
  K0_LOWER_KEY_PREFIX,
  K0_REFERENCE_CONCLUSIONS,
  getK0IndexTypo,
  getK0LowerBlock,
  k0AuditNoteItemId,
  type K0AuditNoteItem,
  type K0LowerBlock,
} from './k0LowerZoneSpec'

const props = defineProps<{
  /** K0-1 上区明细行（矩阵按品种 SUMIF 的数据源） */
  rows: readonly ConfirmationRow[]
  readonly: boolean
  /**
   * 已**持久化**的 checklist responses（itemId → value）。
   * 🔴 必须来自 `/checklist-responses`，不得来自 `responses_snapshot`。
   */
  responses?: Record<string, string>
  /**
   * 账面金额（`k0MatrixDataSources.loadK0MatrixSources` 的结果）。
   * 🔴 三态语义原样传入，**禁 `?? {}` 兜底** —— 那会把「未取数」变成「本项目无此科目」。
   */
  bookAmounts?: Record<string, number | null>
  diagnostics?: K0MatrixDiagnostics | null
  refreshing?: boolean
  aiLoadingKey?: string | null
  /** 下方共享「审计说明」区的既有内容（供 `aliasOf` 项只读引用，不重复录入） */
  notes?: Record<string, string> | null
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: string): void
  (e: 'ai-generate', aiSection: string, itemId: string): void
  (e: 'refresh-book-amounts'): void
}>()

// 🔴 金额格式单一真源 = displayPrefs.fmtAmount（**store 成员**）。必须在 setup 顶层取。
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// ─── 常量（模板引用） ───────────────────────────────────────────────────────

const LABEL_HEADER = K0_MATRIX_LABEL_HEADER
const CATEGORY_NAMES = K0_MATRIX_CATEGORY_NAMES
const AUDIT_NOTES = K0_AUDIT_NOTES
const CONCLUSION_KEY = K0_CONCLUSION_KEY
const CONCLUSION_AI_SECTION = K0_CONCLUSION_AI_SECTION
const CONCLUSION_REVIEW_SECTION_ID = K0_CONCLUSION_REVIEW_SECTION_ID
const REF_CONCLUSIONS = K0_REFERENCE_CONCLUSIONS
const GUIDANCE_BLOCKS = K0_GUIDANCE_BLOCKS
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
      if (k.startsWith(K0_LOWER_KEY_PREFIX)) {
        texts[k] = String(v ?? '')
      } else if (k.startsWith('K0-1-matrix')) {
        const n = Number(v)
        if (Number.isFinite(n)) overrides[k] = n
      }
    }
    textValues.value = texts
    manualOverrides.value = overrides
  },
  { immediate: true, deep: true },
)

// ─── 段标题与锚点 ───────────────────────────────────────────────────────────

function titleOf(key: K0LowerBlock): string {
  return getK0LowerBlock(key).title
}
function anchorOf(key: K0LowerBlock): string {
  return getK0LowerBlock(key).anchor
}

/** 该审计说明项对应的源模板索引号笔误说明（无则空串） */
function typoOf(note: K0AuditNoteItem): string {
  const typo = getK0IndexTypo(`函证结果汇总表K0-1!${note.labelAnchor}`)
  if (!typo) return ''
  return `${typo.note}（源模板原文：${typo.literal} → 实际指向 ${typo.intended}）`
}

function itemIdOf(note: K0AuditNoteItem): string {
  return k0AuditNoteItemId(note.seq)
}

/** `aliasOf` 项的只读文本（读下方共享「审计说明」区的既有字段，不重复录入） */
function aliasTextOf(note: K0AuditNoteItem): string {
  if (!note.aliasOf) return ''
  return String(props.notes?.[note.aliasOf] ?? '')
}

// ─── 矩阵 ───────────────────────────────────────────────────────────────────

const bookViews = computed<K0BookAmountView[]>(() =>
  buildK0BookAmountViews(props.bookAmounts),
)
const bookViewByCat = computed(() =>
  Object.fromEntries(bookViews.value.map((v) => [v.category, v])),
)

const matrix = computed<K0MatrixCell[][]>(() =>
  buildK0SummaryMatrix({
    rows: props.rows ?? [],
    // 🔴 原样传入（含 undefined），不写 `?? {}`
    bookAmounts: props.bookAmounts,
    manualOverrides: manualOverrides.value,
  }),
)

/** 表格行（按指标一行，品种作列） */
const matrixTableData = computed(() =>
  K0_MATRIX_METRICS.map((m) => ({ metric: m.key, label: m.label, anchor: m.anchor })),
)

function cellText(category: string, metric: K0MetricKey): string {
  const cell = pickK0MatrixCell(matrix.value, category, metric)
  if (!cell || cell.value === null) return '-'
  if (cell.kind === 'ratio') return `${(cell.value * 100).toFixed(2)}%`
  return displayPrefs.fmtAmount(cell.value)
}

function bookDisplayOf(category: string): string {
  const cell = pickK0MatrixCell(matrix.value, category, 'book_amount')
  if (!cell || cell.value === null) return bookStateTextOf(category) || '-'
  return displayPrefs.fmtAmount(cell.value)
}

/** 三态文案（未取数 / 本项目无此科目 / 有值时空串） */
function bookStateTextOf(category: string): string {
  return bookViewByCat.value[category]?.text ?? ''
}

/** 溯源 tooltip：报表行 + 来源底稿 + 实际命中的取数口径 + 已登记缺口 */
function bookHintOf(category: string): string {
  const def = K0_MATRIX_CATEGORIES.find((c) => c.category === category)
  const view = bookViewByCat.value[category]
  const parts: string[] = [def?.amountHint ?? '']
  if (view?.resolvedBy) parts.push(`实际取数口径：${view.resolvedBy}`)
  if (view?.state === 'not_fetched') parts.push('尚未取数 —— 可点右上「刷新账面金额」或手工填写')
  if (view?.state === 'absent') parts.push('本项目无此科目或未编制该审定表 —— 请手工填写')
  if (view?.knownGap) parts.push(`⚠ 已登记缺口：${view.knownGap}`)
  return parts.filter(Boolean).join('\n')
}

function editableBookValue(category: string): number | null {
  const cell = pickK0MatrixCell(matrix.value, category, 'book_amount')
  return cell?.value ?? null
}

function onBookAmountInput(category: string, v: number | null) {
  const itemId = bookAmountOverrideItemId(category)
  emit('save', itemId, v === null || v === undefined ? '' : String(v))
}

const unclassifiedCount = computed(() => countK0UnclassifiedRows(props.rows ?? []))

// ─── 诊断（必须渲染） ───────────────────────────────────────────────────────

const diagErrors = computed(() => props.diagnostics?.errors ?? [])
const diagKnownGaps = computed(() => props.diagnostics?.knownGaps ?? [])

// ─── 文本 ───────────────────────────────────────────────────────────────────

function onTextInput(itemId: string, v: string) {
  textValues.value = { ...textValues.value, [itemId]: v }
  emit('save', itemId, v)
}

function applyRefConclusion(text: string) {
  onTextInput(CONCLUSION_KEY, text)
}

/**
 * 供宿主回填 AI 生成文本（与 G0/H0/L0 下区同款契约）。
 *
 * 🔴 `itemId` 是持久化键（`K0-1-lower-audit-note-{seq}` / `K0-1-lower-conclusion`），
 * 不是 aiSection —— 宿主 `handleK0LowerAi(aiSection, itemId)` 的第二参就是它。
 * 走 `onTextInput` 而非直写 ref：AI 文本必须与手工录入同路径落库
 * （否则界面显示有值但没保存）。
 */
function applyAiText(itemId: string, text: string) {
  onTextInput(itemId, text)
}

defineExpose({ applyAiText })

const rows = computed(() => props.rows ?? [])
const readonly = computed(() => !!props.readonly)
const refreshing = computed(() => !!props.refreshing)
const aiLoadingKey = computed(() => props.aiLoadingKey ?? null)
</script>

<style scoped>
.k0-lower { font-size: 13px; }
.k0-lower__section { margin-top: 16px; }
.k0-lower__title {
  display: flex; align-items: center; gap: 8px;
  font-weight: 600; margin-bottom: 8px;
}
.k0-lower__alert { margin-bottom: 8px; }
.k0-lower__diag { margin: 0; padding-left: 18px; }
.k0-lower__amount { font-variant-numeric: tabular-nums; white-space: nowrap; }
.k0-lower__cat-head { border-bottom: 1px dashed #909399; cursor: help; }
.k0-lower__hint { color: #909399; margin-top: 6px; }
.k0-lower__empty { color: #E6A23C; margin-top: 6px; }
.k0-lower__field-label { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.k0-lower__anchor { color: #C0C4CC; font-weight: 400; margin-left: 6px; font-size: 11px; }
.k0-lower__src-hint {
  margin-top: 4px; padding: 6px 8px;
  border-left: 3px solid #E6A23C; background: #FDF6EC; color: #7A5C22;
}
.k0-lower__alias {
  padding: 8px; background: #F4F4F5; border-left: 3px solid #909399;
}
.k0-lower__alias-text { white-space: pre-wrap; }
.k0-lower__alias-tip { color: #909399; margin-top: 4px; font-size: 12px; }
.k0-lower__ref { margin-top: 12px; }
.k0-lower__ref-title { font-weight: 600; }
.k0-lower__ref-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.k0-lower__ref-text { flex: 1; }
.k0-lower__guidance { margin-top: 16px; color: #606266; }
.k0-lower__guidance-block { margin-top: 10px; }
.k0-lower__guidance-heading { font-weight: 600; }
.k0-lower__guidance-list { margin: 4px 0 0; padding-left: 18px; }
</style>
