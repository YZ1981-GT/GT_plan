<template>
  <div ref="rootRef">
    <div class="citar-toolbar">
      <div class="ra-seg" role="group" aria-label="数据口径">
        <button
          v-for="m in MODES"
          :key="m.key"
          type="button"
          class="ra-seg__btn"
          :class="{ 'ra-seg__btn--active': mode === m.key }"
          :disabled="m.key === 'compare' && kind === 'equity_statement'"
          :title="m.key === 'compare' && kind === 'equity_statement' ? '权益变动表是矩阵，请分别切换「审定」「未审」查看' : ''"
          @click="mode = m.key"
        >{{ m.label }}</button>
      </div>
      <span class="citar-toolbar__hint">{{ MODE_HINTS[mode] }}</span>
    </div>

    <div v-if="needsGenerate" class="citar-notice">
      <span v-if="prerequisite">{{ prerequisite.message }}</span>
      <span v-else>审定报表尚未生成，下表只显示行次。</span>
      <button v-if="prerequisite?.segment" class="citar-btn" type="button" @click="emit('go', prerequisite.segment)">
        去{{ prerequisite.label }}
      </button>
      <button class="citar-btn citar-btn--primary" type="button" :disabled="generating" @click="onGenerate">
        {{ generating ? '生成中…' : '生成报表' }}
      </button>
    </div>

    <p v-if="loading" class="sheet-empty">正在读取报表…</p>
    <p v-else-if="error" class="sheet-empty">{{ error }}</p>

    <!-- 资产负债表 / 利润表：与「审定报表」页同一版式 -->
    <CitarReportTable
      v-else-if="mode !== 'compare' && bsOrIs"
      :kind="bsOrIs"
      :rows="rows"
      :year="year"
      :entity-name="entityName"
      src-prefix=""
    />

    <template v-else>
      <div class="sheet-caption">
        <h2 class="sheet-caption__title">{{ STATEMENT_TITLES[kind] }}</h2>
        <p class="sheet-caption__period">{{ periodText }}</p>
        <div class="sheet-caption__meta"><span>编制单位：{{ entityName }}</span><span>单位：人民币元</span></div>
      </div>

      <CitarEquityMatrix v-if="kind === 'equity_statement'" :rows="rows" />

      <div v-else-if="mode === 'compare'" class="sheet-scroll">
        <table class="sheet-table">
          <thead>
            <tr>
              <th>项　目</th><th>未审数</th><th>调整影响</th><th>审定数</th>
              <th>{{ periodLabels(kind)[1] }}</th><th>变动额</th><th>变动率</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in compareRows" :key="r.row_code" :class="rowClass(r)">
              <td :style="indentStyle(r)">{{ r.row_name }}</td>
              <td class="is-numeric" :data-src="srcOf(`u|${r.row_code}:current`)">{{ fmtMoney(r.unadjusted) }}</td>
              <td class="is-numeric" :class="{ 'ra-adjusted': r.adjustment }" :data-src="srcOf(`adj|${r.row_code}`)">{{ fmtMoney(r.adjustment) }}</td>
              <td class="is-numeric" :data-src="srcOf(`a|${r.row_code}:current`)">{{ fmtMoney(r.audited) }}</td>
              <td class="is-numeric" :data-src="srcOf(`a|${r.row_code}:prior`)">{{ fmtMoney(r.prior) }}</td>
              <td class="is-numeric">{{ fmtMoney(r.change) }}</td>
              <td class="is-numeric" :class="{ 'ra-alert': r.change_rate !== null && Math.abs(r.change_rate) >= 20 }">
                {{ r.change_rate === null ? '' : `${r.change_rate.toFixed(1)}%` }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <table v-else class="sheet-table">
        <thead><tr><th>项　目</th><th>{{ periodLabels(kind)[0] }}</th><th>{{ periodLabels(kind)[1] }}</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.row_code" :class="rowClass(r)">
            <td :style="indentStyle(r)">{{ r.row_name }}</td>
            <td class="is-numeric">{{ fmtMoney(r.current_period_amount) }}</td>
            <td class="is-numeric">{{ fmtMoney(r.prior_period_amount) }}</td>
          </tr>
        </tbody>
      </table>

      <p v-if="kind === 'impairment_provision'" class="ra-footnote">
        本期计提、转回、转销等增减明细平台暂无取数来源，此表只列年初与期末账面余额。
      </p>
      <p v-if="kind === 'cash_flow_statement' && allZero" class="ra-footnote">
        现金流量表各行为 0：现金流量表由现金流量表工作底稿分配后生成，尚未编制时这里没有数。
      </p>
    </template>

    <CitarSourceCard
      :state="sources.card.value"
      :label="sources.cardLabel.value"
      @open="sources.open"
      @enter="sources.onCardEnter"
      @leave="sources.onCardLeave"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * 报表分析 · 六张报表之一：审定 / 未审 / 对比三态（spec citar-report-analysis R2）。
 * 审定读已生成的 financial_report；未审按试算表未审数读时计算；对比在前端按 row_code 合并。
 */
import { computed, ref, toRef, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { cellSources as P_src } from '@/services/apiPaths'
import CitarReportTable from './CitarReportTable.vue'
import CitarEquityMatrix from './CitarEquityMatrix.vue'
import CitarSourceCard from './CitarSourceCard.vue'
import { localSource, type CellSource, type CellSourceResponse } from '../cellSource'
import { fmtMoney } from '../useCitarProject'
import { useCitarReportGenerate } from '../useCitarReportGenerate'
import { useCitarSourceCard } from '../useCitarSourceCard'
import {
  STATEMENT_TITLES,
  errorText,
  fetchStatement,
  isGenerated,
  mergeCompare,
  periodLabels,
  toNumber,
  type CompareRow,
  type ReportRow,
  type StatementKind,
  type StatementMode,
} from '../useCitarReportAnalysis'

const props = defineProps<{
  kind: StatementKind
  projectId: string
  year: number
  entityName: string
}>()
const emit = defineEmits<{ (e: 'go', segment: string): void }>()

const MODES: { key: StatementMode; label: string }[] = [
  { key: 'audited', label: '审定' },
  { key: 'unadjusted', label: '未审' },
  { key: 'compare', label: '对比' },
]
const MODE_HINTS: Record<StatementMode, string> = {
  audited: '审定数：取最近一次生成的报表；调整分录变化后需重新生成',
  unadjusted: '未审数：按试算表未审数实时计算',
  compare: '对比：未审 → 调整影响 → 审定，并与上期比较',
}

const mode = ref<StatementMode>('audited')
const rows = ref<ReportRow[]>([])
const compareRows = ref<CompareRow[]>([])
const loading = ref(false)
const error = ref('')

const { generating, prerequisite, generate } = useCitarReportGenerate(
  toRef(props, 'projectId'),
  computed(() => props.year),
)

const needsGenerate = computed(() =>
  !loading.value && !error.value && mode.value !== 'unadjusted' && rows.value.length > 0 && !isGenerated(rows.value),
)
/** 资产负债表 / 利润表用「审定报表」页同一组件（左右分栏版式） */
const bsOrIs = computed(() =>
  props.kind === 'balance_sheet' || props.kind === 'income_statement' ? props.kind : null,
)
const allZero = computed(() => rows.value.length > 0 && rows.value.every(r => !toNumber(r.current_period_amount)))
const periodText = computed(() =>
  props.kind === 'balance_sheet' || props.kind === 'impairment_provision'
    ? `${props.year}年12月31日`
    : `${props.year}年度`,
)

/**
 * 每次读取取一个序号，只有最新一次的结果 / 错误写回页面。
 * 「审定」未回就切「对比」时，新请求与旧请求同 URL 同参数，GET 去重会取消旧的那个；
 * 旧的 catch 晚于新请求发出才执行，不按序号丢弃就会把「读取报表失败」盖在已成功的对比表上。
 */
let loadSeq = 0

async function load() {
  const seq = ++loadSeq
  loading.value = true
  error.value = ''
  rows.value = []
  compareRows.value = []
  try {
    if (mode.value === 'compare') {
      const [audited, unadjusted] = await Promise.all([
        fetchStatement(props.projectId, props.year, props.kind, false),
        fetchStatement(props.projectId, props.year, props.kind, true),
      ])
      if (seq !== loadSeq) return
      rows.value = audited
      compareRows.value = mergeCompare(audited, unadjusted)
    } else {
      const data = await fetchStatement(props.projectId, props.year, props.kind, mode.value === 'unadjusted')
      if (seq !== loadSeq) return
      rows.value = data
    }
  } catch (e: any) {
    if (seq !== loadSeq) return
    error.value = e?.response?.status === 404
      ? '本项目的报表口径没有这张表（如上市版单体报表无资产减值准备表）'
      : errorText(e, '读取报表失败')
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

async function onGenerate() {
  if (await generate()) await load()
}

watch(() => props.kind, k => { if (k === 'equity_statement' && mode.value === 'compare') mode.value = 'audited' })
watch([() => props.kind, () => props.year, () => props.projectId, mode], load, { immediate: true })

// ── 悬浮数据来源（spec citar-cell-source-hover R5.3；本轮只接资产负债表、利润表） ──
const rootRef = ref<HTMLElement | null>(null)
/** 对比模式的键带口径前缀（u| 未审、a| 审定、adj| 调整影响）；其余模式无前缀 */
function srcOf(key: string): string | undefined {
  return bsOrIs.value ? key : undefined
}

async function fetchSources(m: 'audited' | 'unadjusted'): Promise<Record<string, CellSource>> {
  const res = (await api.get(P_src.report(props.projectId, props.kind), {
    params: { year: props.year, mode: m }, _silent: true,
  } as any)) as CellSourceResponse
  return res?.cells ?? {}
}

function adjustmentSource(code: string): CellSource | null {
  const r = compareRows.value.find(x => x.row_code === code)
  if (!r) return null
  return localSource('derived', '调整影响 = 审定数 − 未审数（两张报表同一行相减；含审定报表的手工修改）', r.adjustment === null ? null : String(r.adjustment), {
    items: [
      { label: '审定数', detail: null, amount: r.audited === null ? null : String(r.audited), sign: '1', link: null },
      { label: '未审数', detail: null, amount: r.unadjusted === null ? null : String(r.unadjusted), sign: '-1', link: null },
    ],
    linear: r.adjustment !== null,
    total: r.adjustment === null ? null : String(r.adjustment),
    notes: ['审定数、未审数格子各自悬停可看构成；调整分录明细见试算平衡表调整列'],
  })
}

const sources = useCitarSourceCard({
  container: rootRef,
  async load() {
    if (mode.value !== 'compare') return fetchSources(mode.value)
    const [a, u] = await Promise.all([fetchSources('audited'), fetchSources('unadjusted')])
    const out: Record<string, CellSource> = {}
    for (const [k, v] of Object.entries(a)) out[`a|${k}`] = v
    for (const [k, v] of Object.entries(u)) out[`u|${k}`] = v
    for (const r of compareRows.value) {
      const s = adjustmentSource(r.row_code)
      if (s) out[`adj|${r.row_code}`] = s
    }
    return out
  },
  label(key) {
    const [prefix, rest] = key.includes('|') ? key.split('|') : ['', key]
    const [code, col] = rest.split(':')
    const r = rows.value.find(x => x.row_code === code)
    const colText = prefix === 'adj' ? '调整影响' : `${prefix === 'u' || mode.value === 'unadjusted' ? '未审' : '审定'}${col === 'prior' ? '上期' : '本期'}`
    return `${code} ${(r?.row_name ?? '').trim()} · ${colText}`
  },
})
watch([rows, compareRows, mode], () => sources.invalidate())

function rowClass(r: ReportRow) {
  if (r.is_total_row) return /总计\s*$/.test(r.row_name || '') ? 'level-total' : 'level-subtotal'
  if (!r.indent_level) return 'level-group'
  return ''
}

function indentStyle(r: ReportRow) {
  if (r.is_total_row) return undefined
  return { paddingLeft: `${10 + (r.indent_level || 0) * 12}px` }
}
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>
<style scoped src="../styles/report-analysis.css"></style>
