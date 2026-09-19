/**
 * useH4StocktakePlan — H4-6A 监盘计划 / H4-6B 监盘小结
 */
import { ref, computed, watch, inject, type Ref } from 'vue'
import {
  H4_PLAN_KEY,
  H4_SUMMARY_KEY,
  createEmptyPlanForm,
  createEmptySummaryForm,
  draftPlanConclusion,
  draftSummaryFromCheck,
  normalizePlanForm,
  normalizeSummaryForm,
  planGateBlockers,
  suggestedCoverage,
  type H4StocktakePlanForm,
  type H4StocktakeSummaryForm,
  type H4StocktakeLocationRow,
} from './h4StocktakePlanModel'
import { calcStocktakeStats, normalizeCheckMeta, normalizeCheckRow } from './h4StocktakeCheckModel'
import { calcDirectionCoverage } from './h1StocktakeCheckModel'

const CHECK_ROWS_KEY = 'H4-6-rows'
const CHECK_META_KEY = 'H4-6-stocktake-meta'
const CHECK_NOTE_KEY = 'H4-6-note'
const CHECK_CONCLUSION_KEY = 'H4-6-conclusion'

function _parse(map: Map<string, any>, itemId: string): any {
  const item = map.get(itemId)
  if (!item) return null
  const raw = item.remark ?? item.conclusion
  if (raw == null || raw === '') return null
  if (typeof raw !== 'string') return raw
  try { return JSON.parse(raw) } catch { return raw }
}

export function useH4StocktakePlan(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
}) {
  const { allResponses } = params
  const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', () => {})

  const plan = ref<H4StocktakePlanForm>(createEmptyPlanForm())
  const summary = ref<H4StocktakeSummaryForm>(createEmptySummaryForm())

  function _persist(itemId: string, value: any): void {
    const strVal = JSON.stringify(value)
    allResponses.value.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
    saveResponse(itemId, value)
  }

  function load(): void {
    plan.value = normalizePlanForm(_parse(allResponses.value, H4_PLAN_KEY))
    summary.value = normalizeSummaryForm(_parse(allResponses.value, H4_SUMMARY_KEY))
  }

  function persistPlan(): void {
    _persist(H4_PLAN_KEY, plan.value)
  }

  function persistSummary(): void {
    _persist(H4_SUMMARY_KEY, summary.value)
  }

  function updatePlan<K extends keyof H4StocktakePlanForm>(key: K, value: H4StocktakePlanForm[K]): void {
    plan.value = { ...plan.value, [key]: value }
    persistPlan()
  }

  function updateSummary<K extends keyof H4StocktakeSummaryForm>(
    key: K,
    value: H4StocktakeSummaryForm[K],
  ): void {
    summary.value = { ...summary.value, [key]: value }
    persistSummary()
  }

  function addLocation(): void {
    const row: H4StocktakeLocationRow = {
      rowId: `loc-${Date.now().toString(36)}`,
      location: '',
      materialTypes: '',
      estimatedAmount: 0,
      remark: '',
    }
    plan.value = { ...plan.value, locations: [...plan.value.locations, row] }
    persistPlan()
  }

  function removeLocation(rowId: string): void {
    plan.value = {
      ...plan.value,
      locations: plan.value.locations.filter((r) => r.rowId !== rowId),
    }
    persistPlan()
  }

  function updateLocation(rowId: string, patch: Partial<H4StocktakeLocationRow>): void {
    plan.value = {
      ...plan.value,
      locations: plan.value.locations.map((r) => (r.rowId === rowId ? { ...r, ...patch } : r)),
    }
    persistPlan()
  }

  const blockers = computed(() => planGateBlockers(plan.value))
  const planReady = computed(() => blockers.value.length === 0)
  const riskCoverageHint = computed(() => suggestedCoverage(plan.value.existenceRiskLevel))

  function applyRiskCoverage(): void {
    updatePlan('plannedCoveragePct', suggestedCoverage(plan.value.existenceRiskLevel))
  }

  function draftPlanConclusionText(): void {
    updatePlan('planConclusion', draftPlanConclusion(plan.value))
  }

  /** 将计划关键字段写入 H4-6 meta（仅填空） */
  function pushPlanToCheckMeta(): { ok: boolean; message: string } {
    const meta = normalizeCheckMeta(_parse(allResponses.value, CHECK_META_KEY))
    let changed = 0
    if (!meta.countTime && plan.value.stocktakeDate) {
      meta.countTime = plan.value.stocktakeDate
      changed++
    }
    if (!meta.auditors && plan.value.participants) {
      meta.auditors = plan.value.participants
      changed++
    }
    if (!meta.location && plan.value.locations[0]?.location) {
      meta.location = plan.value.locations[0].location
      changed++
    }
    if (!meta.samplingMethod && plan.value.method) {
      meta.samplingMethod = plan.value.method.includes('全面') ? '全面盘点' : '随机选样'
      changed++
    }
    if (!meta.testPopulation && plan.value.scope) {
      meta.testPopulation = plan.value.scope
      changed++
    }
    if (!meta.samplingProcess && plan.value.sampleSizeNote) {
      meta.samplingProcess = plan.value.sampleSizeNote
      changed++
    }
    if (changed === 0) {
      return { ok: false, message: 'H4-6 过程字段已有内容，未覆盖写入' }
    }
    _persist(CHECK_META_KEY, meta)
    return { ok: true, message: `已将计划 ${changed} 项字段回填至 H4-6 过程/样本段` }
  }

  function syncSummaryFromCheck(): { ok: boolean; message: string } {
    const rawRows = _parse(allResponses.value, CHECK_ROWS_KEY)
    const rows = Array.isArray(rawRows) ? rawRows.map((r, i) => normalizeCheckRow(r, i)) : []
    const meta = normalizeCheckMeta(_parse(allResponses.value, CHECK_META_KEY))
    const stats = calcStocktakeStats(rows)
    const cov = calcDirectionCoverage(rows as any, meta.totalBookCost)
    const noteItem = allResponses.value.get(CHECK_NOTE_KEY)
    const concItem = allResponses.value.get(CHECK_CONCLUSION_KEY)
    summary.value = draftSummaryFromCheck({
      location: meta.location,
      countTime: meta.countTime,
      clientStaff: meta.clientStaff,
      auditors: meta.auditors,
      total: stats.total,
      matchCount: stats.matchCount,
      surplusCount: stats.surplusCount,
      deficitCount: stats.deficitCount,
      varianceCount: stats.varianceCount,
      concernCount: stats.concernCount,
      matchRate: stats.matchRate,
      coveragePct: cov.ratioPct,
      auditNote: String(noteItem?.remark ?? ''),
      auditConclusion: String(concItem?.remark ?? ''),
    })
    persistSummary()
    return {
      ok: true,
      message: rows.length
        ? `已从 H4-6 回填小结（${rows.length} 项抽盘）`
        : '已初始化小结框架（H4-6 尚无抽盘行）',
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  return {
    plan,
    summary,
    blockers,
    planReady,
    riskCoverageHint,
    updatePlan,
    updateSummary,
    addLocation,
    removeLocation,
    updateLocation,
    applyRiskCoverage,
    draftPlanConclusionText,
    pushPlanToCheckMeta,
    syncSummaryFromCheck,
    persistPlan,
    persistSummary,
    load,
  }
}

export default useH4StocktakePlan
