<template>
  <div class="aud-screen">
    <header class="aud-header">
      <h1 class="aud-header__title">单体财务报表</h1>
      <span class="aud-header__note">数据源与「试算平衡表」相同（标准科目审定数）；格式按申报表 A000000 第 107 项会计准则代码自动选择</span>
    </header>

    <nav v-if="visibleStatements.length" class="aud-tabs">
      <button
        v-for="(s, i) in visibleStatements"
        :key="s.key"
        type="button"
        class="aud-tab"
        :class="{ 'aud-tab--active': tab === i }"
        @click="tab = i"
      >{{ s.title }}</button>
    </nav>

    <section class="aud-panel">
      <p v-if="!year" class="sheet-empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
      <template v-else>
        <div class="citar-toolbar">
          <span v-if="data?.format_label" class="citar-tag citar-tag--type">
            {{ data.format_label }}格式{{ data.standard_code ? `（代码 ${data.standard_code}）` : '' }}
          </span>
          <button class="citar-btn" type="button" :disabled="loading" @click="load">刷新</button>
          <button class="citar-btn citar-btn--primary" type="button" :disabled="!data?.statements.length || exporting" @click="exportXlsx">
            {{ exporting ? '导出中…' : '导出 Excel' }}
          </button>
          <span class="citar-toolbar__hint">调整分录批准、试算表重算后点「刷新」</span>
        </div>

        <details v-if="otherNotices.length || failedChecks.length || error" class="citar-errors">
          <summary>其他问题（{{ otherNotices.length + failedChecks.length + (error ? 1 : 0) }}）</summary>
          <div v-for="n in otherNotices" :key="n" class="citar-notice">
            <span>{{ n }}</span>
            <button v-if="n.includes('审定报表')" class="citar-btn" type="button" @click="goSegment('reports')">去审定报表</button>
          </div>
          <div v-for="c in failedChecks" :key="c.label" class="citar-notice">
            {{ c.label }}：{{ fmtMoney(numberOf(c.difference)) }}（不平，请核对科目映射与调整分录）
          </div>
          <p v-if="error" class="citar-notice citar-notice--error">{{ error }}</p>
        </details>

        <p v-if="loading && !data" class="sheet-empty">正在生成财务报表…</p>
        <template v-else-if="current">
          <div class="sheet-caption">
            <p v-if="current.attachment" class="fs-attachment">{{ current.attachment }}</p>
            <h2 class="sheet-caption__title">{{ current.title }}</h2>
            <p class="sheet-caption__period">{{ periodText }}</p>
            <div class="sheet-caption__meta"><span>编制单位：{{ data?.entity_name }}</span><span>单位：人民币元</span></div>
          </div>
          <div class="sheet-scroll">
            <table class="sheet-table">
              <thead>
                <tr><th>项　　目</th><th v-for="c in current.columns" :key="c" class="fs-amount">{{ c }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="r in current.rows" :key="r.r" :class="rowClass(r)" :title="r.note || undefined">
                  <td :style="{ paddingLeft: `${10 + r.indent * 14}px` }">
                    {{ r.label }}<span v-if="r.note" class="fs-note">（{{ r.note }}）</span>
                  </td>
                  <td class="is-numeric">{{ amount(r, 'current') }}</td>
                  <td class="is-numeric">{{ amount(r, 'prior') }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 单体财务报表（CITAR 鉴证报告 · 单体财务报表）。
 * 企业会计制度格式由后端按税审专用行次配置从标准科目审定数计算；企业会计准则格式复用平台审定报表。
 * 金额：取不到（null）留空，0 显示「-」。
 */
import { computed, ref, watch } from 'vue'
import { handleApiError } from '@/utils/errorHandler'
import {
  downloadTaxAssurance, fetchFinancialStatements, numberOf,
  type FinancialStatementsData, type FsRow,
} from '../taxAssuranceApi'
import { fmtMoney, useCitarProject } from '../useCitarProject'

defineOptions({ name: 'CitarFinancialStatements' })

const { projectId, year, yearLoading, goSegment } = useCitarProject()
const data = ref<FinancialStatementsData | null>(null)
const loading = ref(false)
const exporting = ref(false)
const error = ref('')
const tab = ref(0)

const HIDDEN_STATEMENT_KEYS = new Set([
  'cash_flow_statement',
  'cash_flow_supplement',
])
const HIDDEN_NOTICE_MARKERS = ['税审底稿', '1-12', '现金流量表底稿']

const visibleStatements = computed(() =>
  (data.value?.statements ?? []).filter(s => !HIDDEN_STATEMENT_KEYS.has(s.key)),
)
const current = computed(() => visibleStatements.value[tab.value] ?? null)
const otherNotices = computed(() =>
  (data.value?.notices ?? []).filter(n => !HIDDEN_NOTICE_MARKERS.some(marker => n.includes(marker))),
)
const failedChecks = computed(() => (data.value?.checks ?? []).filter(c => !c.ok))
const periodText = computed(() => {
  if (!year.value || !current.value) return ''
  return current.value.columns[0]?.startsWith('期末') ? `${year.value}年12月31日` : `${year.value}年度`
})

let seq = 0
async function load() {
  if (!year.value) return
  const mine = ++seq
  loading.value = true
  error.value = ''
  try {
    const res = await fetchFinancialStatements(projectId.value, year.value)
    if (mine !== seq) return
    data.value = res
    if (tab.value >= visibleStatements.value.length) tab.value = 0
  } catch (e: any) {
    if (mine === seq) error.value = e?.response?.data?.detail || e?.message || '生成财务报表失败'
  } finally {
    if (mine === seq) loading.value = false
  }
}

async function exportXlsx() {
  if (!year.value) return
  exporting.value = true
  try {
    await downloadTaxAssurance('financialStatementsExport', projectId.value, year.value, `${year.value}年度财务报表.xlsx`)
  } catch (e) {
    handleApiError(e, '导出财务报表')
  } finally {
    exporting.value = false
  }
}

function amount(r: FsRow, key: 'current' | 'prior') {
  if (r.heading) return ''
  return fmtMoney(numberOf(r[key]))
}

function rowClass(r: FsRow) {
  if (r.heading) return 'level-group'
  if (r.total) return /总计\s*$/.test(r.label) ? 'level-total' : 'level-subtotal'
  return ''
}

watch([projectId, year], load, { immediate: true })
</script>

<style scoped src="../styles/audited.css"></style>
<style scoped src="../styles/unaudited.css"></style>
<style scoped src="../styles/citar-data.css"></style>

<style scoped>
.citar-errors {
  margin: 0 0 12px;
  border: 1px solid #eadff3;
  border-radius: var(--gt-radius-sm);
  background: var(--citar-c-fbf9fe);
}

.citar-errors summary {
  padding: 8px 12px;
  color: var(--citar-c-4c1273);
  font-size: var(--citar-fs-13);
  font-weight: 600;
  cursor: pointer;
  user-select: none;
}

.citar-errors[open] summary {
  border-bottom: 1px solid #eadff3;
}

.citar-errors .citar-notice {
  margin: 8px 12px;
}

.citar-errors .citar-notice:last-child {
  margin-bottom: 12px;
}

.citar-notice--error {
  color: var(--citar-c-e5484d);
}

.fs-attachment {
  margin: 0;
  text-align: left;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-6b6b76);
}

.fs-amount {
  width: 200px;
}

.fs-note {
  margin-left: 6px;
  font-size: var(--citar-fs-12);
  color: var(--citar-c-a0a0aa);
}
</style>
