/**
 * useD2PolicyCheck — 政策检查D2-8核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 12.1
 *
 * 职责：
 * - PolicyParagraph 类型定义（6字段）
 * - paragraphs reactive（6个政策段落）
 * - completedCount / totalCount computed
 * - hasNonCompliant computed（是否存在不合规项）
 * - updateParagraph（conclusion→即时保存，文本→debounce）
 *
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
 */
import { ref, computed, watch, onBeforeUnmount, inject, type ComputedRef } from 'vue'
import { calculateExpectedLossRate } from './useD2FormulaEngine'
import type { UseD2BaseOptions } from './useD2Adjudication'
import { D2_SAVE_ITEMS_KEY, type D2SaveItemsFn } from './d2InjectionKeys'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface PolicyParagraph {
  paragraphId: string
  title: string                // 政策段落标题
  policyDescription: string    // 政策条款描述（只读）
  actualSituation: string      // 被审计单位实际情况（可编辑）
  auditorEvaluation: string    // 审计师评价（可编辑）
  conclusion: 'Y' | 'N' | 'NA' | ''  // 结论
}

/** D2-8 历史损失率矩阵行（9列：3年余额+3年损失+3年损失率） */
export interface PolicyHistoricalRow {
  rowId: string
  agingBand: string
  balanceY1: number
  balanceY2: number
  balanceY3: number
  lossY1: number
  lossY2: number
  lossY3: number
}

/** D2-8 迁徙率矩阵行 */
export interface PolicyMigrationRow {
  rowId: string
  agingBand: string
  year1Rate: number
  year2Rate: number
  year3Rate: number
}

export interface PolicyHistoricalDisplayRow extends PolicyHistoricalRow {
  lossRateY1: number
  lossRateY2: number
  lossRateY3: number
  avgLossRate: number
}

export interface PolicyMigrationDisplayRow extends PolicyMigrationRow {
  avgRate: number
  expectedLossRate: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'D2-policy-paragraphs'
const HISTORICAL_MATRIX_KEY = 'D2-policy-historical-matrix'
const MIGRATION_MATRIX_KEY = 'D2-policy-migration-matrix'
const CONCLUSION_KEY = 'D2-policy-conclusion'
const SUMMARY_KEY = 'D2-policy-summary'

const DEFAULT_AGING_BANDS = [
  '1年以内', '1-2年', '2-3年', '3-4年', '4-5年', '5年以上',
]

/** 默认6个政策检查段落（对齐 D2-8 源模板） */
const DEFAULT_PARAGRAPHS: PolicyParagraph[] = [
  {
    paragraphId: 'ecl-model',
    title: 'ECL模型说明',
    policyDescription: '企业采用预期信用损失（ECL）模型对应收账款计提坏账准备，应说明所采用的简化方法或一般方法，以及模型输入参数（违约概率、违约损失率、违约风险敞口）的确定依据。',
    actualSituation: '',
    auditorEvaluation: '',
    conclusion: '',
  },
  {
    paragraphId: 'credit-risk-increase',
    title: '信用风险显著增加判断标准',
    policyDescription: '企业应建立并披露判断信用风险是否显著增加的标准，通常包括：逾期天数、内部/external信用评级变化、宏观经济指标恶化、债务人财务状况恶化等。',
    actualSituation: '',
    auditorEvaluation: '',
    conclusion: '',
  },
  {
    paragraphId: 'impairment-indicators',
    title: '减值迹象识别',
    policyDescription: '企业应识别并评估表明应收账款已发生信用减值的客观证据，如：债务人发生重大财务困难、破产、重组、长期逾期且无合理还款计划等。',
    actualSituation: '',
    auditorEvaluation: '',
    conclusion: '',
  },
  {
    paragraphId: 'estimate-change',
    title: '会计估计变更',
    policyDescription: '如本期变更坏账准备计提方法、账龄组合划分或预期信用损失率，应说明变更原因、影响金额及是否属于会计估计变更或会计政策变更。',
    actualSituation: '',
    auditorEvaluation: '',
    conclusion: '',
  },
  {
    paragraphId: 'peer-comparison',
    title: '同行业比较',
    policyDescription: '应将本企业应收账款坏账准备计提比例、账龄结构与同行业可比公司进行比较，分析差异合理性，关注显著偏离行业水平的计提政策。',
    actualSituation: '',
    auditorEvaluation: '',
    conclusion: '',
  },
  {
    paragraphId: 'ecl-rate-method',
    title: '预期信用损失率确定方法',
    policyDescription: '企业应说明各账龄段/组合的预期信用损失率确定方法，包括历史损失率法、迁徙率法、前瞻性调整等，并披露前瞻性信息的来源与权重。',
    actualSituation: '',
    auditorEvaluation: '',
    conclusion: '',
  },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseParagraphs(jsonStr: string | null | undefined): PolicyParagraph[] {
  if (!jsonStr) return DEFAULT_PARAGRAPHS.map(p => ({ ...p }))
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return DEFAULT_PARAGRAPHS.map(p => ({ ...p }))
    }
    return parsed.map((raw: any) => ({
      paragraphId: raw.paragraphId || '',
      title: raw.title || '',
      policyDescription: raw.policyDescription || '',
      actualSituation: raw.actualSituation || '',
      auditorEvaluation: raw.auditorEvaluation || '',
      conclusion: (['Y', 'N', 'NA'].includes(raw.conclusion) ? raw.conclusion : '') as PolicyParagraph['conclusion'],
    }))
  } catch {
    return DEFAULT_PARAGRAPHS.map(p => ({ ...p }))
  }
}

function generateRowId(): string {
  return `policy-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function createDefaultHistoricalRows(): PolicyHistoricalRow[] {
  return DEFAULT_AGING_BANDS.map(band => ({
    rowId: generateRowId(),
    agingBand: band,
    balanceY1: 0, balanceY2: 0, balanceY3: 0,
    lossY1: 0, lossY2: 0, lossY3: 0,
  }))
}

function createDefaultMigrationRows(): PolicyMigrationRow[] {
  return DEFAULT_AGING_BANDS.map(band => ({
    rowId: generateRowId(),
    agingBand: band,
    year1Rate: 0, year2Rate: 0, year3Rate: 0,
  }))
}

function parseHistoricalRows(jsonStr: string | null | undefined): PolicyHistoricalRow[] {
  if (!jsonStr) return createDefaultHistoricalRows()
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed) || parsed.length === 0) return createDefaultHistoricalRows()
    return parsed.map((raw: any) => ({
      rowId: raw.rowId || generateRowId(),
      agingBand: raw.agingBand || '',
      balanceY1: Number(raw.balanceY1) || 0,
      balanceY2: Number(raw.balanceY2) || 0,
      balanceY3: Number(raw.balanceY3) || 0,
      lossY1: Number(raw.lossY1) || 0,
      lossY2: Number(raw.lossY2) || 0,
      lossY3: Number(raw.lossY3) || 0,
    }))
  } catch {
    return createDefaultHistoricalRows()
  }
}

function parseMigrationRows(jsonStr: string | null | undefined): PolicyMigrationRow[] {
  if (!jsonStr) return createDefaultMigrationRows()
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed) || parsed.length === 0) return createDefaultMigrationRows()
    return parsed.map((raw: any) => ({
      rowId: raw.rowId || generateRowId(),
      agingBand: raw.agingBand || '',
      year1Rate: Number(raw.year1Rate) || 0,
      year2Rate: Number(raw.year2Rate) || 0,
      year3Rate: Number(raw.year3Rate) || 0,
    }))
  } catch {
    return createDefaultMigrationRows()
  }
}

function calcLossRate(loss: number, balance: number): number {
  return balance === 0 ? 0 : loss / balance
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2PolicyCheck(options: UseD2BaseOptions & { agingBands?: ComputedRef<string[]> }) {
  const { allResponses, isReadonly, agingBands: externalBands } = options

  // ─── 改进3: provide/inject 保存 ──────────────────────────────────────────
  const injectedSave = inject<D2SaveItemsFn | undefined>(D2_SAVE_ITEMS_KEY, undefined)

  // ─── 改进1: 动态账龄段（联动 useAgingConfig） ────────────────────────────
  const agingBands = computed(() => {
    if (externalBands?.value && externalBands.value.length > 0) {
      return externalBands.value
    }
    // 回退：从 D2-1 审定表的账龄模式读取
    const mode = allResponses.value.get('D2-adj-aging-mode')?.remark || '5y'
    if (mode === '3y') return ['一年以内', '一到二年', '二到三年', '三年以上']
    if (mode === 'custom') {
      const json = allResponses.value.get('D2-adj-aging-custom-bands')?.remark
      if (json) {
        try {
          const parsed = JSON.parse(json)
          if (Array.isArray(parsed) && parsed.length > 0) {
            return parsed.map((b: any) => b.label || '未命名')
          }
        } catch { /* fallback */ }
      }
    }
    return DEFAULT_AGING_BANDS
  }) = options

  // ─── State ─────────────────────────────────────────────────────────────

  const paragraphs = ref<PolicyParagraph[]>(DEFAULT_PARAGRAPHS.map(p => ({ ...p })))
  const historicalRows = ref<PolicyHistoricalRow[]>(createDefaultHistoricalRows())
  const migrationRows = ref<PolicyMigrationRow[]>(createDefaultMigrationRows())
  const auditSummary = ref('')
  const auditConclusion = ref('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let matrixDebounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadData(): void {
    const resp = allResponses.value.get(STORAGE_KEY)
    paragraphs.value = parseParagraphs(resp?.remark)
    historicalRows.value = parseHistoricalRows(allResponses.value.get(HISTORICAL_MATRIX_KEY)?.remark)
    migrationRows.value = parseMigrationRows(allResponses.value.get(MIGRATION_MATRIX_KEY)?.remark)
    auditSummary.value = allResponses.value.get(SUMMARY_KEY)?.remark || ''
    auditConclusion.value = allResponses.value.get(CONCLUSION_KEY)?.remark || ''
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => {
      const isInitial = paragraphs.value.every(p => !p.actualSituation && !p.auditorEvaluation && !p.conclusion)
      if (isInitial) loadData()
    },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(HISTORICAL_MATRIX_KEY)?.remark,
    (v) => {
      if (v) historicalRows.value = parseHistoricalRows(v)
    },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(MIGRATION_MATRIX_KEY)?.remark,
    (v) => {
      if (v) migrationRows.value = parseMigrationRows(v)
    },
    { immediate: true },
  )

  // ─── Computed ──────────────────────────────────────────────────────────

  const totalCount: ComputedRef<number> = computed(() => {
    return paragraphs.value.length
  })

  const completedCount: ComputedRef<number> = computed(() => {
    return paragraphs.value.filter(p => p.conclusion !== '').length
  })

  /**
   * 是否存在不合规项（conclusion='N'）
   */
  const hasNonCompliant: ComputedRef<boolean> = computed(() => {
    return paragraphs.value.some(p => p.conclusion === 'N')
  })

  const historicalDisplayRows: ComputedRef<PolicyHistoricalDisplayRow[]> = computed(() =>
    historicalRows.value.map(row => {
      const lossRateY1 = calcLossRate(row.lossY1, row.balanceY1)
      const lossRateY2 = calcLossRate(row.lossY2, row.balanceY2)
      const lossRateY3 = calcLossRate(row.lossY3, row.balanceY3)
      const rates = [lossRateY1, lossRateY2, lossRateY3].filter(r => r > 0)
      const avgLossRate = rates.length ? rates.reduce((a, b) => a + b, 0) / rates.length : 0
      return { ...row, lossRateY1, lossRateY2, lossRateY3, avgLossRate }
    }),
  )

  const migrationDisplayRows: ComputedRef<PolicyMigrationDisplayRow[]> = computed(() =>
    migrationRows.value.map(row => {
      const rates = [row.year1Rate, row.year2Rate, row.year3Rate]
      const avgRate = rates.reduce((a, b) => a + b, 0) / 3
      return { ...row, avgRate, expectedLossRate: calculateExpectedLossRate(rates) }
    }),
  )

  // ─── Update Paragraph ──────────────────────────────────────────────────

  /**
   * 更新段落字段
   * - conclusion → 即时保存（关键判断项）
   * - actualSituation / auditorEvaluation → debounce 2s 保存
   */
  function updateParagraph(id: string, field: string, value: string): void {
    if (isReadonly.value) return
    const paragraph = paragraphs.value.find(p => p.paragraphId === id)
    if (!paragraph) return

    if (field === 'conclusion') {
      paragraph.conclusion = (['Y', 'N', 'NA'].includes(value) ? value : '') as PolicyParagraph['conclusion']
      immediateSave()
    } else if (field === 'actualSituation') {
      paragraph.actualSituation = value
      debounceSave()
    } else if (field === 'auditorEvaluation') {
      paragraph.auditorEvaluation = value
      debounceSave()
    }
  }

  function updateHistoricalCell(rowId: string, field: keyof PolicyHistoricalRow, value: number): void {
    if (isReadonly.value) return
    const row = historicalRows.value.find(r => r.rowId === rowId)
    if (!row || field === 'rowId' || field === 'agingBand') return
    ;(row as any)[field] = value
    debounceMatrixSave()
  }

  function updateMigrationCell(rowId: string, field: keyof PolicyMigrationRow, value: number): void {
    if (isReadonly.value) return
    const row = migrationRows.value.find(r => r.rowId === rowId)
    if (!row || field === 'rowId' || field === 'agingBand') return
    ;(row as any)[field] = value
    debounceMatrixSave()
  }

  function debounceMatrixSave(): void {
    if (matrixDebounceTimer) clearTimeout(matrixDebounceTimer)
    matrixDebounceTimer = setTimeout(() => {
      matrixDebounceTimer = null
      flushMatrixSave()
    }, 2000)
  }

  function flushMatrixSave(): void {
    const histJson = JSON.stringify(historicalRows.value)
    const migJson = JSON.stringify(migrationRows.value)
    allResponses.value.set(HISTORICAL_MATRIX_KEY, {
      item_id: HISTORICAL_MATRIX_KEY, conclusion: null, remark: histJson,
    })
    allResponses.value.set(MIGRATION_MATRIX_KEY, {
      item_id: MIGRATION_MATRIX_KEY, conclusion: null, remark: migJson,
    })
    const items = [
      { item_id: HISTORICAL_MATRIX_KEY, conclusion: null, remark: histJson },
      { item_id: MIGRATION_MATRIX_KEY, conclusion: null, remark: migJson },
    ]
    if (injectedSave) {
      void injectedSave(items)
    } else {
      try {
        window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
      } catch { /* silent */ }
    }
  }

  // ─── Serialization & Save ──────────────────────────────────────────────

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function immediateSave(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    flushSave()
  }

  function flushSave(): void {
    const json = JSON.stringify(paragraphs.value)
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
    dispatchSaveEvent(json)
  }

  function dispatchSaveEvent(json: string): void {
    const items = [{ item_id: STORAGE_KEY, conclusion: null, remark: json }]
    if (injectedSave) {
      void injectedSave(items)
    } else {
      try {
        window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
      } catch { /* silent */ }
    }
  }

  // ─── 改进4: 审计说明/结论 ──────────────────────────────────────────────

  function updateSummary(value: string): void {
    if (isReadonly.value) return
    auditSummary.value = value
    const item = { item_id: SUMMARY_KEY, conclusion: null, remark: value }
    allResponses.value.set(SUMMARY_KEY, item)
    if (injectedSave) void injectedSave([item])
    else {
      try { window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items: [item] } })) } catch { /* */ }
    }
  }

  function updateConclusion(value: string): void {
    if (isReadonly.value) return
    auditConclusion.value = value
    const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: value }
    allResponses.value.set(CONCLUSION_KEY, item)
    if (injectedSave) void injectedSave([item])
    else {
      try { window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items: [item] } })) } catch { /* */ }
    }
  }

  // ─── 改进1: 账龄段变化时重建矩阵行 ────────────────────────────────────────

  watch(agingBands, (newBands) => {
    // 重建历史损失率矩阵（保留已有段数据）
    const existingHist = historicalRows.value
    historicalRows.value = newBands.map(band => {
      const found = existingHist.find(r => r.agingBand === band)
      return found || { rowId: generateRowId(), agingBand: band, balanceY1: 0, balanceY2: 0, balanceY3: 0, lossY1: 0, lossY2: 0, lossY3: 0 }
    })
    // 重建迁徙率矩阵
    const existingMig = migrationRows.value
    migrationRows.value = newBands.map(band => {
      const found = existingMig.find(r => r.agingBand === band)
      return found || { rowId: generateRowId(), agingBand: band, year1Rate: 0, year2Rate: 0, year3Rate: 0 }
    })
  })

  // ─── 改进2: 迁徙率与 D2-10 ECL 交叉引用 ───────────────────────────────────

  /** 迁徙率是否与 D2-10 存在差异（供 UI 展示联动警告） */
  const migrationD10Deviation = computed<string | null>(() => {
    const d10Rows = allResponses.value.get('D2-ecl10-migration-rows')?.remark
    if (!d10Rows) return null
    try {
      const parsed = JSON.parse(d10Rows)
      if (!Array.isArray(parsed) || parsed.length === 0) return null
      // 比较第一段的平均迁徙率
      const d10Avg = parsed[0]?.avgRate ?? parsed[0]?.expectedLossRate
      const d8Avg = migrationDisplayRows.value[0]?.avgRate
      if (d10Avg != null && d8Avg != null && Math.abs(d10Avg - d8Avg) > 0.05) {
        return `D2-8 首段迁徙率(${(d8Avg * 100).toFixed(1)}%)与 D2-10 首段(${(d10Avg * 100).toFixed(1)}%)偏差超过5%，请核实`
      }
    } catch { /* silent */ }
    return null
  })

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
    if (matrixDebounceTimer) {
      clearTimeout(matrixDebounceTimer)
      matrixDebounceTimer = null
      flushMatrixSave()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    paragraphs,
    historicalDisplayRows,
    migrationDisplayRows,
    completedCount,
    totalCount,
    hasNonCompliant,
    updateParagraph,
    updateHistoricalCell,
    updateMigrationCell,
    // 改进1: 动态账龄段
    agingBands,
    // 改进2: 迁徙率交叉引用
    migrationD10Deviation,
    // 改进4: 审计说明/结论
    auditSummary,
    auditConclusion,
    updateSummary,
    updateConclusion,
  }
}

export default useD2PolicyCheck
