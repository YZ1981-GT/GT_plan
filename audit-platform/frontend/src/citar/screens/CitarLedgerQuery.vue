<template>
  <div class="unaudited-screen">
    <header class="unaudited-header">
      <h1 class="unaudited-header__title">账务查询</h1>
      <span class="unaudited-header__note">未审数据：导入的科目余额表、序时账，以及按试算表未审数计算的报表</span>
    </header>

    <nav class="unaudited-tabs">
      <template v-for="(item, index) in TABS" :key="item.key">
        <!-- 账套与报表之间一道分隔，两类表性质不同 -->
        <span v-if="index > 0 && TABS[index - 1].group !== item.group" class="unaudited-tabs__divider" />
        <button
          type="button"
          class="unaudited-tab"
          :class="{ 'unaudited-tab--active': tab === item.key }"
          @click="setTab(item.key)"
        >{{ item.label }}</button>
      </template>
    </nav>

    <section class="unaudited-panel">
      <p v-if="!year" class="sheet-empty">{{ yearLoading ? '正在读取项目信息…' : '项目未设置审核年度，请先在项目信息里填写' }}</p>
      <template v-else>
        <CitarBalanceTab
          v-if="tab === 'balance'"
          :project-id="projectId"
          :year="year"
          :entity-name="entityName"
          @open-account="openAccount"
        />
        <CitarJournalTab
          v-else-if="tab === 'journal'"
          :project-id="projectId"
          :year="year"
          :entity-name="entityName"
          :account-code="journalCode"
          @update:account-code="setJournalCode"
        />
        <CitarReportTable
          v-else
          :kind="tab === 'balance-sheet' ? 'balance_sheet' : 'income_statement'"
          :rows="reportRows"
          :year="year"
          :entity-name="entityName"
          :loading="reportLoading"
          :error="reportError"
        />
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * 账务查询（CITAR「未审账套、报表」版式，接平台真实数据）。
 * 报表两张：GET /api/reports/{pid}/{year}/{type}?unadjusted=true —— 按试算表未审数读时计算，不落库。
 */
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getReport } from '@/services/auditPlatformApi'
import CitarBalanceTab from '../components/CitarBalanceTab.vue'
import CitarJournalTab from '../components/CitarJournalTab.vue'
import CitarReportTable, { type CitarReportRow } from '../components/CitarReportTable.vue'
import { useCitarProject } from '../useCitarProject'

defineOptions({ name: 'CitarLedgerQuery' })

type TabKey = 'balance' | 'journal' | 'balance-sheet' | 'income-statement'

const TABS: { key: TabKey; label: string; group: 'ledger' | 'report' }[] = [
  { key: 'balance', label: '科目余额表', group: 'ledger' },
  { key: 'journal', label: '序时账', group: 'ledger' },
  { key: 'balance-sheet', label: '资产负债表', group: 'report' },
  { key: 'income-statement', label: '利润表', group: 'report' },
]

const route = useRoute()
const router = useRouter()
const { projectId, year, yearLoading, entityName } = useCitarProject()

/** 当前标签记在 ?tab=，刷新与返回不丢 */
const tab = ref<TabKey>(TABS.some(t => t.key === route.query.tab) ? (route.query.tab as TabKey) : 'balance')
const journalCode = ref(typeof route.query.account === 'string' ? route.query.account : '')

function setTab(key: TabKey) {
  tab.value = key
  router.replace({ query: { ...route.query, tab: key } })
}

function setJournalCode(code: string) {
  journalCode.value = code
  const { account: _drop, ...rest } = route.query
  router.replace({ query: code ? { ...rest, account: code } : rest })
}

function openAccount(code: string) {
  journalCode.value = code
  tab.value = 'journal'
  router.replace({ query: { ...route.query, tab: 'journal', account: code } })
}

const reportRows = ref<CitarReportRow[]>([])
const reportLoading = ref(false)
const reportError = ref('')

async function loadReport() {
  if (!year.value || (tab.value !== 'balance-sheet' && tab.value !== 'income-statement')) return
  const type = tab.value === 'balance-sheet' ? 'balance_sheet' : 'income_statement'
  reportLoading.value = true
  reportError.value = ''
  reportRows.value = []
  try {
    reportRows.value = (await getReport(projectId.value, year.value, type, true)) as CitarReportRow[]
  } catch (e: any) {
    reportError.value = e?.response?.data?.detail || e?.message || '读取未审报表失败'
  } finally {
    reportLoading.value = false
  }
}

watch([tab, year, projectId], loadReport, { immediate: true })
</script>

<style scoped src="../styles/unaudited.css"></style>
