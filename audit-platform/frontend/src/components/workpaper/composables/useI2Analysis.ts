/**
 * useI2Analysis — I2-5 实质性分析
 * 对齐 Excel：构成分析 / 同行指标 / 人均同期 / 人均同行 / 结构化说明
 * 兼容 Spec Req4：开发支出项目波动分析（旧 I2-5-rows 数组）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import http from '@/utils/http'
import {
  calcAssetEndBalance,
  calcChangeRate,
  calcVarianceFromExpected,
  calcSubtotal,
} from './useI2FormulaEngine'
import {
  type I2AnalysisBundle,
  type I2CompositionRow,
  type I2CompositionMeta,
  type I2PeerIndicatorRow,
  type I2PerCapitaYoY,
  type I2PerCapitaPeerRow,
  type I2AnalysisStructuredNotes,
  normalizeBundle,
  createDefaultBundle,
  syncDerivedFromComposition,
  recomputeAllComposition,
  recomputePerCapitaYoY,
  emptyCompositionRow,
  emptyPeerIndicator,
  emptyPerCapitaPeer,
  compositionTotals,
  summarizeAnalysisAnomalies,
  buildAnalysisConclusionDraft,
  seedCompositionFromI6Detail,
  I2_ANALYSIS_GROWTH_THRESHOLD,
  I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD,
} from './i2AnalysisModel'

/** 旧版项目波动行（Spec Req4） */
export interface AnalysisRow {
  projectName: string
  beginAmount: number
  increaseAmount: number
  decreaseAmount: number
  endAmount: number
  priorEndAmount: number
  changeRate: number | null
  expectedValue: number
  variance: number
  exceedThreshold: boolean
  analysisConclusion: string
  anomalyReason: string
  auditResponse: string
  remark: string
}

const BUNDLE_KEY = 'I2-5-analysis-bundle'
const ROWS_KEY = 'I2-5-rows'
const DEFAULT_MATERIALITY = 0

function _createEmptyProjectRow(projectName: string): AnalysisRow {
  return {
    projectName,
    beginAmount: 0,
    increaseAmount: 0,
    decreaseAmount: 0,
    endAmount: 0,
    priorEndAmount: 0,
    changeRate: null,
    expectedValue: 0,
    variance: 0,
    exceedThreshold: false,
    analysisConclusion: '',
    anomalyReason: '',
    auditResponse: '',
    remark: '',
  }
}

function _recalcProjectRow(row: AnalysisRow, materiality: number): void {
  row.endAmount = calcAssetEndBalance(row.beginAmount, row.increaseAmount, row.decreaseAmount)
  row.changeRate = calcChangeRate(row.endAmount, row.priorEndAmount)
  row.variance = calcVarianceFromExpected(row.endAmount, row.expectedValue)
  row.exceedThreshold = materiality > 0 && Math.abs(row.variance) > materiality
}

export function useI2Analysis(params: {
  allResponses: Ref<Map<string, any>>
  saveResponses: (sheetCode: string, data: Record<string, any>) => Promise<void>
  materialityLevel?: Ref<number>
}) {
  const { allResponses, saveResponses, materialityLevel } = params

  const bundle = ref<I2AnalysisBundle>(createDefaultBundle())
  const rows = ref<AnalysisRow[]>([])

  function _getJson(key: string): any {
    const item = allResponses.value.get(key)
    if (!item) return null
    const raw = item.remark ?? item.conclusion ?? item
    if (raw == null) return null
    if (typeof raw === 'object') return raw
    try { return JSON.parse(raw as string) } catch { return null }
  }

  function _getMateriality(): number {
    return materialityLevel?.value ?? DEFAULT_MATERIALITY
  }

  function _load(): void {
    const bundled = _getJson(BUNDLE_KEY)
    const legacy = _getJson(ROWS_KEY)
    if (bundled && typeof bundled === 'object' && !Array.isArray(bundled)) {
      bundle.value = normalizeBundle(bundled)
      if (Array.isArray(bundled.projectFluctuationRows)) {
        rows.value = _normalizeProjectRows(bundled.projectFluctuationRows)
      } else if (Array.isArray(legacy)) {
        rows.value = _normalizeProjectRows(legacy)
      } else {
        rows.value = []
      }
    } else if (Array.isArray(legacy)) {
      bundle.value = normalizeBundle(legacy)
      rows.value = _normalizeProjectRows(legacy)
    } else {
      bundle.value = createDefaultBundle()
      rows.value = []
    }
  }

  function _normalizeProjectRows(data: any[]): AnalysisRow[] {
    const mat = _getMateriality()
    return data.map((raw) => {
      const row = _createEmptyProjectRow(String(raw.projectName ?? ''))
      row.beginAmount = Number(raw.beginAmount) || 0
      row.increaseAmount = Number(raw.increaseAmount) || 0
      row.decreaseAmount = Number(raw.decreaseAmount) || 0
      row.priorEndAmount = Number(raw.priorEndAmount) || 0
      row.expectedValue = Number(raw.expectedValue) || 0
      row.analysisConclusion = String(raw.analysisConclusion ?? '')
      row.anomalyReason = String(raw.anomalyReason ?? '')
      row.auditResponse = String(raw.auditResponse ?? '')
      row.remark = String(raw.remark ?? '')
      _recalcProjectRow(row, mat)
      return row
    })
  }

  watch(allResponses, () => _load(), { immediate: true })
  if (materialityLevel) {
    watch(materialityLevel, () => {
      const mat = _getMateriality()
      for (const row of rows.value) _recalcProjectRow(row, mat)
    })
  }

  // ─── Bundle mutations ──────────────────────────────────────────────────────

  function refreshDerived(): void {
    bundle.value = syncDerivedFromComposition(bundle.value)
  }

  function updateCompositionMeta(field: keyof I2CompositionMeta, value: number): void {
    bundle.value.compositionMeta[field] = Number(value) || 0
    refreshDerived()
  }

  /** 更新可配置阈值（growthThreshold / revRatioDeltaThreshold），并重算构成异常判定 */
  function updateThreshold(field: 'growthThreshold' | 'revRatioDeltaThreshold', value: number): void {
    const n = Number(value)
    const fallback = field === 'growthThreshold'
      ? I2_ANALYSIS_GROWTH_THRESHOLD
      : I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD
    bundle.value.compositionMeta[field] = Number.isFinite(n) && n > 0 ? n : fallback
    refreshDerived()
  }

  /**
   * 从 TB 取主营业务收入（科目前缀 6001），带入构成分析表本期/上期主营业务收入。
   */
  async function fetchRevenueFromTb(projectId: string): Promise<{ ok: boolean; message: string }> {
    if (!projectId) return { ok: false, message: '缺少项目ID，无法从 TB 取数' }
    try {
      const res = await http.get(`/projects/${projectId}/trial-balance`, {
        params: { account_prefix: '6001' },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
      let current = 0
      let prior = 0
      let hit = false
      for (const item of list) {
        const code = String(item.standard_account_code ?? item.account_code ?? '')
        if (!code.startsWith('6001')) continue
        hit = true
        current += Number(item.audited_amount ?? item.unadjusted_amount ?? item.current_amount ?? 0) || 0
        prior += Number(
          item.prior_amount ?? item.prior_audited_amount ?? item.prior_period_amount ?? item.last_year_amount ?? 0,
        ) || 0
      }
      if (!hit) return { ok: false, message: '未从 TB 取得 6001 主营业务收入数据，请检查试算平衡表' }
      // 主营业务收入为贷方性质，TB 未审/审定数通常已为正数余额；此处取绝对值防止符号方向差异
      current = Math.abs(current)
      prior = Math.abs(prior)
      bundle.value.compositionMeta.revenueCurrent = current
      if (prior > 0) bundle.value.compositionMeta.revenuePrior = prior
      refreshDerived()
      return {
        ok: true,
        message: prior > 0
          ? `已从 TB 带入主营业务收入：本期 ${current.toFixed(2)}，上期 ${prior.toFixed(2)}`
          : `已从 TB 带入主营业务收入：本期 ${current.toFixed(2)}（未取得上期数，请手工补充）`,
      }
    } catch {
      return { ok: false, message: 'TB 取数失败，请检查网络或稍后重试' }
    }
  }

  function updateCompositionField(index: number, field: keyof I2CompositionRow, value: any): void {
    const row = bundle.value.compositionRows[index]
    if (!row) return
    ;(row as any)[field] = value
    bundle.value.compositionRows = recomputeAllComposition(
      bundle.value.compositionRows,
      bundle.value.compositionMeta,
    )
    refreshDerived()
  }

  function addCompositionRow(itemName = ''): void {
    bundle.value.compositionRows.push(emptyCompositionRow({ itemName }))
    refreshDerived()
  }

  function removeCompositionRow(index: number): void {
    if (index < 0 || index >= bundle.value.compositionRows.length) return
    bundle.value.compositionRows.splice(index, 1)
    refreshDerived()
  }

  function updatePeerIndicator(index: number, field: keyof I2PeerIndicatorRow, value: any): void {
    const row = bundle.value.peerIndicators[index]
    if (!row) return
    if (field === 'peerA' || field === 'peerB' || field === 'peerC' || field === 'current') {
      let n = value == null || value === '' ? null : Number(value)
      if (n != null && Number.isFinite(n) && Math.abs(n) > 1) n = n / 100 // 兼容录入 8 表示 8%
      ;(row as any)[field] = n
      return
    }
    ;(row as any)[field] = value
  }

  function addPeerIndicator(): void {
    bundle.value.peerIndicators.push(emptyPeerIndicator({ indicator: '' }))
  }

  function updatePerCapitaYoY(field: keyof I2PerCapitaYoY, value: any): void {
    ;(bundle.value.perCapitaYoY as any)[field] = value
    bundle.value.perCapitaYoY = recomputePerCapitaYoY(bundle.value.perCapitaYoY)
    refreshDerived()
  }

  function updatePerCapitaPeer(index: number, field: keyof I2PerCapitaPeerRow, value: any): void {
    const row = bundle.value.perCapitaPeers[index]
    if (!row) return
    ;(row as any)[field] = value
  }

  function addPerCapitaPeer(name = '可比公司'): void {
    bundle.value.perCapitaPeers.push(emptyPerCapitaPeer({ companyName: name, isSelf: false }))
  }

  function updateStructuredNote(key: keyof I2AnalysisStructuredNotes, value: string): void {
    bundle.value.structuredNotes[key] = value
  }

  function seedFromI6(): { ok: boolean; message: string } {
    const detail = _getJson('I6-2-detail-rows')
    const list = Array.isArray(detail) ? detail : []
    if (!list.length) return { ok: false, message: '未找到 I6-2 明细数据，请先在研发费用底稿完成明细表' }
    bundle.value.compositionRows = seedCompositionFromI6Detail(list)
    refreshDerived()
    return { ok: true, message: `已从 I6-2 带入 ${bundle.value.compositionRows.length} 个构成项目` }
  }

  // ─── Legacy project fluctuation ────────────────────────────────────────────

  const totalRow: ComputedRef<AnalysisRow> = computed(() => {
    const r = rows.value
    const beginAmount = calcSubtotal(r.map((row) => row.beginAmount))
    const increaseAmount = calcSubtotal(r.map((row) => row.increaseAmount))
    const decreaseAmount = calcSubtotal(r.map((row) => row.decreaseAmount))
    const endAmount = calcAssetEndBalance(beginAmount, increaseAmount, decreaseAmount)
    const priorEndAmount = calcSubtotal(r.map((row) => row.priorEndAmount))
    const changeRate = calcChangeRate(endAmount, priorEndAmount)
    const expectedValue = calcSubtotal(r.map((row) => row.expectedValue))
    const variance = calcVarianceFromExpected(endAmount, expectedValue)
    const matLevel = _getMateriality()
    return {
      projectName: '合计',
      beginAmount,
      increaseAmount,
      decreaseAmount,
      endAmount,
      priorEndAmount,
      changeRate,
      expectedValue,
      variance,
      exceedThreshold: matLevel > 0 && Math.abs(variance) > matLevel,
      analysisConclusion: '',
      anomalyReason: '',
      auditResponse: '',
      remark: '',
    }
  })

  const anomalyRows = computed(() => {
    const out: { rowIndex: number; variance: number }[] = []
    rows.value.forEach((row, i) => {
      if (row.exceedThreshold) out.push({ rowIndex: i, variance: row.variance })
    })
    return out
  })

  const hasAnomalies = computed(() => anomalyRows.value.length > 0)

  function addRow(projectName: string): void {
    if (!projectName?.trim()) return
    rows.value.push(_createEmptyProjectRow(projectName.trim()))
  }

  function removeRow(index: number): void {
    if (index < 0 || index >= rows.value.length) return
    rows.value.splice(index, 1)
  }

  function updateField(rowIndex: number, field: string, value: any): void {
    if (rowIndex < 0 || rowIndex >= rows.value.length) return
    const row = rows.value[rowIndex]
    const textFields = ['projectName', 'analysisConclusion', 'anomalyReason', 'auditResponse', 'remark']
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      return
    }
    const numFields = ['beginAmount', 'increaseAmount', 'decreaseAmount', 'priorEndAmount', 'expectedValue']
    if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
      _recalcProjectRow(row, _getMateriality())
    }
  }

  const compositionSummary = computed(() =>
    compositionTotals(bundle.value.compositionRows, bundle.value.compositionMeta),
  )
  const anomalySummary = computed(() => summarizeAnalysisAnomalies(bundle.value))

  async function save(): Promise<void> {
    const projectPersist = rows.value.map((row) => ({
      projectName: row.projectName,
      beginAmount: row.beginAmount,
      increaseAmount: row.increaseAmount,
      decreaseAmount: row.decreaseAmount,
      priorEndAmount: row.priorEndAmount,
      expectedValue: row.expectedValue,
      analysisConclusion: row.analysisConclusion,
      anomalyReason: row.anomalyReason,
      auditResponse: row.auditResponse,
      remark: row.remark,
    }))

    const toSave: I2AnalysisBundle = {
      ...bundle.value,
      projectFluctuationRows: projectPersist,
    }

    await saveResponses('I2-5', {
      [BUNDLE_KEY]: JSON.stringify(toSave),
      [ROWS_KEY]: JSON.stringify(projectPersist),
    })
  }

  return {
    bundle,
    compositionSummary,
    anomalySummary,
    refreshDerived,
    updateCompositionMeta,
    updateThreshold,
    fetchRevenueFromTb,
    updateCompositionField,
    addCompositionRow,
    removeCompositionRow,
    updatePeerIndicator,
    addPeerIndicator,
    updatePerCapitaYoY,
    updatePerCapitaPeer,
    addPerCapitaPeer,
    updateStructuredNote,
    seedFromI6,
    buildConclusionDraft: () => buildAnalysisConclusionDraft(bundle.value),
    // legacy
    rows,
    totalRow,
    anomalyRows,
    hasAnomalies,
    addRow,
    removeRow,
    updateField,
    save,
  }
}

export default useI2Analysis
