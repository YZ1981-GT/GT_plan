<template>
  <div>
    <div class="citar-toolbar">
      <div class="ra-seg" role="group" aria-label="报表">
        <button
          v-for="t in REPORTS"
          :key="t.key"
          type="button"
          class="ra-seg__btn"
          :class="{ 'ra-seg__btn--active': reportType === t.key }"
          @click="reportType = t.key"
        >{{ t.label }}</button>
      </div>
      <label class="citar-check">
        年度跨度
        <select v-model.number="span" class="ra-select">
          <option :value="3">近 3 年</option>
          <option :value="5">近 5 年</option>
        </select>
      </label>
      <span class="citar-toolbar__hint">取本项目各年度已生成的审定报表；同比 = 与前一年相比</span>
    </div>

    <p v-if="loading" class="sheet-empty">正在读取…</p>
    <p v-else-if="error" class="sheet-empty">{{ error }}</p>
    <template v-else>
      <div v-if="yearsWithData.length < 2" class="citar-notice citar-notice--plain">
        {{ yearsWithData.length ? `只有 ${yearsWithData.join('、')} 年的数据，暂无可对比的年度。` : '所选年度都没有已生成的审定报表。' }}
        上年数据在各报表「对比」视图的「上期」列里。
      </div>
      <div v-if="shown.length" class="sheet-scroll">
        <table class="sheet-table">
          <thead>
            <tr>
              <th>项　目</th>
              <th v-for="y in years" :key="y">{{ y }} 年</th>
              <th v-for="y in years.slice(1)" :key="`yoy-${y}`">{{ y }} 同比</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in shown" :key="r.line_code">
              <td>{{ r.item_name }}</td>
              <td v-for="y in years" :key="y" class="is-numeric">{{ fmtMoney(r.values[String(y)]) }}</td>
              <td
                v-for="y in years.slice(1)"
                :key="`yoy-${y}`"
                class="is-numeric"
                :class="{ 'ra-alert': Math.abs(r.yoy_changes[String(y)] ?? 0) >= 20 }"
              >{{ r.yoy_changes[String(y)] == null ? '' : `${r.yoy_changes[String(y)]!.toFixed(1)}%` }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/** 多年对比：GET /api/projects/{pid}/reports/multi-year（同一报表行次的多年审定数 + 同比）。 */
import { computed, ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { reports as P_rpt } from '@/services/apiPaths'
import { fmtMoney } from '../useCitarProject'
import { errorText, silent } from '../useCitarReportAnalysis'

interface MultiYearRow {
  line_code: string
  item_name: string
  values: Record<string, number | null>
  yoy_changes: Record<string, number | null>
}

const props = defineProps<{ projectId: string; year: number }>()

const REPORTS = [
  { key: 'balance_sheet', label: '资产负债表' },
  { key: 'income_statement', label: '利润表' },
  { key: 'cash_flow_statement', label: '现金流量表' },
] as const

const reportType = ref<(typeof REPORTS)[number]['key']>('balance_sheet')
const span = ref(3)
const rows = ref<MultiYearRow[]>([])
const loading = ref(false)
const error = ref('')

/** 以项目审计年度为终点往前数 */
const years = computed(() => Array.from({ length: span.value }, (_, i) => props.year - span.value + 1 + i))
const yearsWithData = computed(() =>
  years.value.filter(y => rows.value.some(r => r.values[String(y)] != null && r.values[String(y)] !== 0)),
)
const shown = computed(() => rows.value.filter(r => Object.values(r.values).some(v => v != null && v !== 0)))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data: any = await api.get(P_rpt.multiYear(props.projectId, years.value, reportType.value), silent)
    rows.value = Array.isArray(data?.rows) ? data.rows : []
  } catch (e: any) {
    rows.value = []
    error.value = errorText(e, '读取多年数据失败')
  } finally {
    loading.value = false
  }
}

watch([() => props.projectId, () => props.year, reportType, span], load, { immediate: true })
</script>

<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>
<style scoped src="../styles/report-analysis.css"></style>
<style scoped>
.citar-notice--plain {
  border-color: #e4d8f3;
  background: var(--citar-c-fbf9fe);
  color: var(--citar-c-5c5c68);
}
</style>
