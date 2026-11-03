<template>
  <div>
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
              <td class="is-numeric">{{ fmtMoney(r.unadjusted) }}</td>
              <td class="is-numeric" :class="{ 'ra-adjusted': r.adjustment }">{{ fmtMoney(r.adjustment) }}</td>
              <td class="is-numeric">{{ fmtMoney(r.audited) }}</td>
              <td class="is-numeric">{{ fmtMoney(r.prior) }}</td>
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
  </div>
</template>

<script setup lang="ts">
/**
 * 报表分析 · 六张报表之一：审定 / 未审 / 对比三态（spec citar-report-analysis R2）。
 * 审定读已生成的 financial_report；未审按试算表未审数读时计算；对比在前端按 row_code 合并。
 */
import { computed, ref, toRef, watch } from 'vue'
import CitarReportTable from './CitarReportTable.vue'
import CitarEquityMatrix from './CitarEquityMatrix.vue'
import { fmtMoney } from '../useCitarProject'
import { useCitarReportGenerate } from '../useCitarReportGenerate'
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

async function load() {
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
      rows.value = audited
      compareRows.value = mergeCompare(audited, unadjusted)
    } else {
      rows.value = await fetchStatement(props.projectId, props.year, props.kind, mode.value === 'unadjusted')
    }
  } catch (e: any) {
    error.value = e?.response?.status === 404
      ? '本项目的报表口径没有这张表（如上市版单体报表无资产减值准备表）'
      : errorText(e, '读取报表失败')
  } finally {
    loading.value = false
  }
}

async function onGenerate() {
  if (await generate()) await load()
}

watch(() => props.kind, k => { if (k === 'equity_statement' && mode.value === 'compare') mode.value = 'audited' })
watch([() => props.kind, () => props.year, () => props.projectId, mode], load, { immediate: true })

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
