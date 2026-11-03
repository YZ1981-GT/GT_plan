<template>
  <div>
    <div class="citar-toolbar">
      <div class="ra-seg" role="group" aria-label="报表">
        <button
          v-for="t in REPORTS"
          :key="t.key"
          type="button"
          class="ra-seg__btn"
          :class="{ 'ra-seg__btn--active': report === t.key }"
          @click="report = t.key"
        >{{ t.label }}</button>
      </div>
      <div class="ra-seg" role="group" aria-label="数据口径">
        <button
          v-for="m in MODES"
          :key="m.key"
          type="button"
          class="ra-seg__btn"
          :class="{ 'ra-seg__btn--active': mode === m.key }"
          @click="mode = m.key"
        >{{ m.label }}</button>
      </div>
      <label class="citar-check"><input v-model="significantOnly" type="checkbox" /> 只看显著变动（≥10%）</label>
      <span class="citar-toolbar__count">{{ shown.length }} 行</span>
    </div>

    <p v-if="loading" class="sheet-empty">正在读取…</p>
    <p v-else-if="error" class="sheet-empty">{{ error }}</p>
    <template v-else>
      <div v-if="!hasPrior && rows.length" class="citar-notice">
        {{ report === 'bs' ? '资产负债表没有期初数' : '利润表没有上期数（没有上年项目或上年报表）' }}，算不出变动。
      </div>
      <p v-if="!rows.length" class="sheet-empty">{{ mode === 'audited' ? '审定报表尚未生成。' : '未审报表没有数据。' }}</p>
      <table v-else-if="shown.length" class="sheet-table">
        <thead>
          <tr>
            <th>项　目</th><th>{{ labels[0] }}</th><th>{{ labels[1] }}</th>
            <th>变动额</th><th>变动率</th><th class="ra-col-status">显著</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in shown" :key="r.row_code" :class="{ 'level-subtotal': r.is_total_row }">
            <td :style="{ paddingLeft: `${10 + (r.indent_level || 0) * 12}px` }">{{ r.row_name }}</td>
            <td class="is-numeric">{{ fmtMoney(r.current) }}</td>
            <td class="is-numeric">{{ fmtMoney(r.prior) }}</td>
            <td class="is-numeric">{{ fmtMoney(r.change) }}</td>
            <td class="is-numeric" :class="{ 'ra-alert': r.significant }">
              {{ r.change_rate == null ? '' : `${Number(r.change_rate).toFixed(2)}%` }}
            </td>
            <td class="citar-center">{{ r.significant ? '是' : '' }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="sheet-empty">没有{{ significantOnly ? '显著变动的' : '有数的' }}行。</p>
    </template>
  </div>
</template>

<script setup lang="ts">
/** 变动分析：GET /api/workpapers/{pid}/{year}/bs-trend | pl-trend（本期对上期，≥10% 显著）。 */
import { computed, ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { reports as P_rpt } from '@/services/apiPaths'
import { fmtMoney } from '../useCitarProject'
import { errorText, silent, toNumber } from '../useCitarReportAnalysis'

interface TrendRow {
  row_code: string
  row_name: string
  indent_level: number
  is_total_row: boolean
  current: number | string | null
  prior: number | string | null
  change: number | string | null
  change_rate: number | string | null
  significant: boolean
}

const props = defineProps<{ projectId: string; year: number }>()

const REPORTS = [
  { key: 'bs', label: '资产负债表' },
  { key: 'pl', label: '利润表' },
] as const
const MODES = [
  { key: 'audited', label: '审定' },
  { key: 'unadjusted', label: '未审' },
] as const

const report = ref<'bs' | 'pl'>('bs')
const mode = ref<'audited' | 'unadjusted'>('audited')
const significantOnly = ref(false)
const rows = ref<TrendRow[]>([])
const loading = ref(false)
const error = ref('')

const labels = computed(() => (report.value === 'bs' ? ['期末数', '期初数'] : ['本期金额', '上期金额']))
const hasPrior = computed(() => rows.value.some(r => r.prior !== null))
const shown = computed(() =>
  rows.value.filter(r => {
    if (significantOnly.value) return r.significant
    return Boolean(toNumber(r.current)) || Boolean(toNumber(r.prior))
  }),
)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const path = report.value === 'bs'
      ? P_rpt.analysis.bsTrend(props.projectId, props.year)
      : P_rpt.analysis.plTrend(props.projectId, props.year)
    const data = await api.get(path, { params: { mode: mode.value }, ...silent })
    rows.value = Array.isArray(data) ? (data as TrendRow[]) : []
  } catch (e: any) {
    rows.value = []
    error.value = errorText(e, '读取变动分析失败')
  } finally {
    loading.value = false
  }
}

watch([() => props.projectId, () => props.year, report, mode], load, { immediate: true })
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>
<style scoped src="../styles/report-analysis.css"></style>
