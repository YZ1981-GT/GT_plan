<template>
  <div class="aud-screen">
    <header class="aud-header">
      <h1 class="aud-header__title">审定报表</h1>
      <span class="aud-header__note">按试算表审定数生成；调整分录批准后需重新生成{{ canManualEdit ? '；金额可手工修改' : '' }}</span>
    </header>

    <nav class="aud-tabs">
      <button
        v-for="item in TABS"
        :key="item.key"
        type="button"
        class="aud-tab"
        :class="{ 'aud-tab--active': tab === item.key }"
        @click="tab = item.key"
      >{{ item.label }}</button>
    </nav>

    <section ref="panelRef" class="aud-panel">
      <p v-if="!year" class="sheet-empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
      <template v-else>
        <div class="citar-notice" :class="{ 'citar-notice--plain': generated }">
          <span v-if="prerequisite">{{ prerequisite.message }}</span>
          <span v-else-if="!generated && !loading">审定报表尚未生成，下表只显示行次。</span>
          <span v-else>报表数据取自最近一次生成；试算表或调整分录有变化时请重新生成。</span>
          <button v-if="prerequisite?.segment" class="citar-btn" type="button" @click="goSegment(prerequisite.segment)">
            去{{ prerequisite.label }}
          </button>
          <button
            class="citar-btn citar-btn--primary"
            type="button"
            :disabled="generating || saving || edits.dirty.value"
            :title="edits.dirty.value ? '有未保存的金额修改，请先保存或放弃' : undefined"
            @click="generate"
          >
            {{ generating ? '生成中…' : generated ? '重新生成' : '生成报表' }}
          </button>
        </div>

        <div v-if="generated && !canManualEdit" class="citar-toolbar">
          <span class="citar-toolbar__hint">{{ MANUAL_EDIT_DENIED_TIP }}</span>
        </div>
        <div v-else-if="generated" class="citar-toolbar">
          <button class="citar-btn" type="button" :disabled="!edits.dirty.value || saving" @click="edits.clear">放弃修改</button>
          <button class="citar-btn citar-btn--primary" type="button" :disabled="!edits.dirty.value || saving" @click="saveManual">
            {{ saving ? '保存中…' : '保存修改' }}
          </button>
          <span v-if="edits.dirty.value" class="citar-toolbar__count">有 {{ edits.count.value }} 处未保存的修改</span>
          <span class="citar-toolbar__hint">点金额可修改；改过的金额重新生成后保留（合计按改后的数重算），点开可「恢复」</span>
        </div>

        <CitarReportTable
          :kind="tab"
          :rows="rows"
          :year="year"
          :entity-name="entityName"
          :loading="loading"
          :error="error"
          :editable="generated && !saving && canManualEdit"
          :draft-of="(code, col) => edits.draftOf(cellKey(code, col))"
          :is-restored="(code, col) => edits.isRestored(cellKey(code, col))"
          src-prefix=""
          :located="locatedRow"
          @edit="(code, col, v) => edits.edit(cellKey(code, col), v)"
          @restore="(code, col) => edits.restore(cellKey(code, col), Boolean(rowOf(code)?.manual_amounts?.[col]))"
        />
      </template>
    </section>

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
 * 审定报表（CITAR 审定资产负债表 / 利润表版式）。
 * 读：GET /api/reports/{pid}/{year}/{type}（读已生成的 financial_report；未生成时返回金额为空的模板行次）
 * 生成：POST /api/reports/generate（平台既有前置条件：已导入账套、已映射、已重算试算表）
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getReport } from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'
import { cellSources as P_src } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import CitarReportTable, { type CitarAmountColumn, type CitarReportRow } from '../components/CitarReportTable.vue'
import CitarSourceCard from '../components/CitarSourceCard.vue'
import type { CellSourceLink, CellSourceResponse } from '../cellSource'
import { saveReportManualValues, type ManualReportItem } from '../citarReportManual'
import { useCitarAmountDrafts } from '../useCitarAmountDrafts'
import { useCitarProject } from '../useCitarProject'
import { useCitarReportGenerate } from '../useCitarReportGenerate'
import { useCitarSourceCard } from '../useCitarSourceCard'
import { MANUAL_EDIT_DENIED_TIP, useManualEditPermission } from '@/composables/useManualEditPermission'

defineOptions({ name: 'CitarAuditedReports' })

type TabKey = 'balance_sheet' | 'income_statement'
const TABS: { key: TabKey; label: string }[] = [
  { key: 'balance_sheet', label: '资产负债表' },
  { key: 'income_statement', label: '利润表' },
]
const isTab = (v: unknown): v is TabKey => TABS.some(t => t.key === v)

const route = useRoute()
const { projectId, year, yearLoading, entityName, goSegment } = useCitarProject()
const { generating, prerequisite, generate: runGenerate } = useCitarReportGenerate(projectId, year)
const { canManualEdit } = useManualEditPermission()

// 从数据来源链接跳来：?tab=报表 &locate=行次（spec citar-cell-source-hover R2）
const tab = ref<TabKey>(isTab(route.query.tab) ? route.query.tab : 'balance_sheet')
const pendingLocate = ref<string | null>(typeof route.query.locate === 'string' ? route.query.locate : null)
const locatedRow = ref<string | null>(null)
const panelRef = ref<HTMLElement | null>(null)
const rows = ref<CitarReportRow[]>([])
const loading = ref(false)
const error = ref('')
/** 金额手工修改（spec citar-table-manual-edit R6） */
const edits = useCitarAmountDrafts()
const saving = ref(false)

/** 未生成时后端返回模板行次、金额全空 */
const generated = computed(() =>
  rows.value.some(r => r.current_period_amount !== null || r.prior_period_amount !== null),
)

async function load() {
  if (!year.value) return
  loading.value = true
  error.value = ''
  try {
    rows.value = (await getReport(projectId.value, year.value, tab.value)) as CitarReportRow[]
  } catch (e: any) {
    rows.value = []
    error.value = e?.response?.status === 404 ? '报表格式未配置，无法显示' : e?.message || '读取审定报表失败'
  } finally {
    loading.value = false
  }
  await locateRow()
}

// ── 悬浮数据来源（spec citar-cell-source-hover R5） ──
const sources = useCitarSourceCard({
  container: panelRef,
  async load() {
    const res = (await api.get(P_src.report(projectId.value, tab.value), {
      params: { year: year.value, mode: 'audited' }, _silent: true,
    } as any)) as CellSourceResponse
    return res?.cells ?? {}
  },
  label(key) {
    const [code, col] = key.split(':')
    const r = rowOf(code)
    const colText = col === 'current' ? (tab.value === 'balance_sheet' ? '期末数' : '本期金额') : (tab.value === 'balance_sheet' ? '期初数' : '上期金额')
    return `${code} ${r?.row_name?.trim() ?? ''} · ${colText}`
  },
  locate(l: CellSourceLink) {
    if (l.page !== 'reports' || !l.code) return false
    pendingLocate.value = l.code
    if (l.report_type && isTab(l.report_type) && l.report_type !== tab.value) tab.value = l.report_type
    else void locateRow()
    return true
  },
  dirty: () => edits.dirty.value,
})
watch(rows, () => sources.invalidate())

async function locateRow() {
  const code = pendingLocate.value
  if (!code || !rows.value.length) return
  pendingLocate.value = null
  if (!rowOf(code)) {
    ElMessage.info(`本表没有行次 ${code}`)
    return
  }
  locatedRow.value = code
  await nextTick()
  panelRef.value?.querySelector<HTMLElement>(`[data-locate="${code.replace(/["\\]/g, '\\$&')}"]`)
    ?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
}

async function generate() {
  if (await runGenerate()) await load()
}

function rowOf(code: string) {
  return rows.value.find(r => r.row_code === code)
}

/** 草稿键带报表类型：切页签不串 */
function cellKey(code: string, col: CitarAmountColumn) {
  return `${tab.value}|${code}|${col}`
}

async function saveManual() {
  if (!year.value) return
  const items: ManualReportItem[] = []
  for (const [key, value] of Object.entries(edits.drafts.value)) {
    const [reportType, rowCode, column] = key.split('|')
    items.push({ report_type: reportType, row_code: rowCode, column: column as CitarAmountColumn, value })
  }
  for (const key of edits.restored.value) {
    const [reportType, rowCode, column] = key.split('|')
    items.push({ report_type: reportType, row_code: rowCode, column: column as CitarAmountColumn, restore: true })
  }
  saving.value = true
  try {
    await saveReportManualValues(projectId.value, year.value, items)
    edits.clear()
    ElMessage.success('已保存，报表已按修改后的金额重算')
    await load()
  } catch (e) {
    handleApiError(e, '保存报表修改')
  } finally {
    saving.value = false
  }
}

watch([projectId, year], () => edits.clear())
watch([projectId, year, tab], load, { immediate: true })
</script>

<style scoped src="../styles/audited.css"></style>
<style scoped src="../styles/citar-data.css"></style>

<style scoped>
.citar-notice--plain {
  border-color: #e4d8f3;
  background: var(--citar-c-fbf9fe);
  color: var(--citar-c-5c5c68);
}
</style>
