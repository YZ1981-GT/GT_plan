import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/services/consolidationApi'
import type {
  ComponentAuditor, Instruction, InstructionResult,
  ConsolTrialRow, InternalTrade, GoodwillRow,
  ForexRow, MinorityInterestRow, ConsistencyCheckResult,
  ConsolReportData, YoYAnalysis,
  ConsolScopeNote, SubsidiaryNote, GoodwillNote,
  MinorityInterestNote, InternalTradeNote, InternalArApNote,
  ForexTranslationNote,
} from '@/services/consolidationApi'

export const useConsolidationStore = defineStore('consolidation', () => {
  // ─── State ──────────────────────────────────────────────────────────────────
  const auditors = ref<ComponentAuditor[]>([])
  const instructions = ref<Instruction[]>([])
  const results = ref<InstructionResult[]>([])
  const consolTrial = ref<ConsolTrialRow[]>([])
  const internalTrades = ref<InternalTrade[]>([])
  const goodwillRows = ref<GoodwillRow[]>([])
  const forexRows = ref<ForexRow[]>([])
  const miRows = ref<MinorityInterestRow[]>([])
  const dashboard = ref<any>(null)
  const consistencyResult = ref<ConsistencyCheckResult | null>(null)
  const loading = ref(false)
  const activeTab = ref('trial')

  // 合并报表状态
  const currentReportType = ref<string>('balance_sheet')
  const currentPeriod = ref<string>('')
  const consolReport = ref<ConsolReportData | null>(null)
  const yoyAnalysis = ref<YoYAnalysis[]>([])

  // 合并附注状态
  const consolScopeNotes = ref<ConsolScopeNote[]>([])
  const subsidiaryNotes = ref<SubsidiaryNote[]>([])
  const goodwillNotes = ref<GoodwillNote[]>([])
  const minorityInterestNotes = ref<MinorityInterestNote[]>([])
  const internalTradeNotes = ref<{ trades: InternalTradeNote[]; arap: InternalArApNote[] }>({ trades: [], arap: [] })
  const forexNotes = ref<ForexTranslationNote[]>([])
  const otherMatters = ref('')

  // ─── Computed ────────────────────────────────────────────────────────────────
  const auditorsByStatus = computed(() => ({
    pending: auditors.value.filter(a => a.status === 'pending'),
    in_progress: auditors.value.filter(a => a.status === 'in_progress'),
    completed: auditors.value.filter(a => a.status === 'completed'),
  }))

  const instructionsByStatus = computed(() => ({
    pending: instructions.value.filter(i => i.status === 'pending'),
    issued: instructions.value.filter(i => i.status === 'issued'),
    responded: instructions.value.filter(i => i.status === 'responded'),
  }))

  // ─── Actions ─────────────────────────────────────────────────────────────────

  async function fetchAuditors(projectId: string) {
    loading.value = true
    try { auditors.value = await api.getComponentAuditors(projectId) }
    finally { loading.value = false }
  }

  async function fetchInstructions(projectId: string) {
    loading.value = true
    try { instructions.value = await api.getInstructions(projectId) }
    finally { loading.value = false }
  }

  async function fetchResults(projectId: string) {
    loading.value = true
    try { results.value = await api.getResults(projectId) }
    finally { loading.value = false }
  }

  async function fetchDashboard(projectId: string) {
    loading.value = true
    try { dashboard.value = await api.getComponentDashboard(projectId) }
    finally { loading.value = false }
  }

  async function fetchConsolTrial(projectId: string, year: number) {
    loading.value = true
    try { consolTrial.value = await api.getConsolTrialBalance(projectId, year) }
    finally { loading.value = false }
  }

  async function fetchInternalTrades(projectId: string, year?: number) {
    loading.value = true
    try { internalTrades.value = await api.getInternalTrades(projectId, year ?? new Date().getFullYear()) }
    finally { loading.value = false }
  }

  async function fetchGoodwillRows(projectId: string, year?: number) {
    loading.value = true
    try { goodwillRows.value = await api.getGoodwillRows(projectId, year ?? new Date().getFullYear()) }
    finally { loading.value = false }
  }

  async function fetchForexRows(projectId: string, year?: number) {
    loading.value = true
    try { forexRows.value = await api.getForexRows(projectId, year ?? new Date().getFullYear()) }
    finally { loading.value = false }
  }

  async function fetchMinorityInterestRows(projectId: string, year?: number) {
    loading.value = true
    try { miRows.value = await api.getMinorityInterestRows(projectId, year ?? new Date().getFullYear()) }
    finally { loading.value = false }
  }

  async function checkConsistency(projectId: string, year: number) {
    consistencyResult.value = await api.checkConsolTrialConsistency(projectId, year)
  }

  // ─── 合并报表 Actions ────────────────────────────────────────────────────────
  async function fetchConsolReport(projectId: string, reportType: string, period: string) {
    loading.value = true
    try {
      currentReportType.value = reportType
      currentPeriod.value = period
      consolReport.value = await api.getConsolReport(projectId, reportType as any, period)
      yoyAnalysis.value = await api.getYoYAnalysis(projectId, reportType as any, period)
    } finally {
      loading.value = false
    }
  }

  async function saveConsolReportData(projectId: string, reportType: string, period: string) {
    if (!consolReport.value) return
    consolReport.value = await api.saveConsolReport(projectId, reportType as any, period, consolReport.value)
  }

  // ─── 合并附注 Actions ────────────────────────────────────────────────────────
  async function fetchConsolNotes(projectId: string, period: string) {
    loading.value = true
    try {
      const [scope, subs, gw, mi, tradeNotes, fx] = await Promise.all([
        api.getConsolScopeNotes(projectId, period),
        api.getSubsidiaryNotes(projectId, period),
        api.getGoodwillNotes(projectId, period),
        api.getMinorityInterestNotes(projectId, period),
        api.getInternalTradeNotes(projectId, period),
        api.getForexTranslationNotes(projectId, period),
      ])
      consolScopeNotes.value = scope
      subsidiaryNotes.value = subs as any
      goodwillNotes.value = gw
      minorityInterestNotes.value = mi
      internalTradeNotes.value = tradeNotes
      forexNotes.value = fx as any
    } finally {
      loading.value = false
    }
  }

  async function saveOtherMatters(projectId: string, period: string) {
    await api.saveConsolNotes(projectId, period, { other_matters: otherMatters.value } as any)
  }

  function reset() {
    auditors.value = []
    instructions.value = []
    results.value = []
    consolTrial.value = []
    internalTrades.value = []
    goodwillRows.value = []
    forexRows.value = []
    miRows.value = []
    dashboard.value = null
    consistencyResult.value = null
    activeTab.value = 'trial'
    currentReportType.value = 'balance_sheet'
    currentPeriod.value = ''
    consolReport.value = null
    yoyAnalysis.value = []
    consolScopeNotes.value = []
    subsidiaryNotes.value = []
    goodwillNotes.value = []
    minorityInterestNotes.value = []
    internalTradeNotes.value = { trades: [], arap: [] }
    forexNotes.value = []
    otherMatters.value = ''
  }

  return {
    auditors, instructions, results, consolTrial,
    internalTrades, goodwillRows, forexRows, miRows,
    dashboard, consistencyResult, loading, activeTab,
    auditorsByStatus, instructionsByStatus,
    fetchAuditors, fetchInstructions, fetchResults, fetchDashboard,
    fetchConsolTrial, fetchInternalTrades,
    fetchGoodwillRows, fetchForexRows, fetchMinorityInterestRows,
    checkConsistency,
    // 合并报表
    currentReportType, currentPeriod, consolReport, yoyAnalysis,
    fetchConsolReport, saveConsolReportData,
    // 合并附注
    consolScopeNotes, subsidiaryNotes, goodwillNotes,
    minorityInterestNotes, internalTradeNotes, forexNotes, otherMatters,
    fetchConsolNotes, saveOtherMatters,
    reset,
  }
})
