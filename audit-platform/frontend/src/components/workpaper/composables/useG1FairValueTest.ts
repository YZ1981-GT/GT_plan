/**
 * useG1FairValueTest — G1-6 公允价值测试表
 *
 * 对齐 Excel《交易性金融资产公允价值测试表》编制逻辑：
 * 目标 → 程序闸门 → 账面 vs 测试/审定 → 按 Level1/2/3 取证 → 回写 G1-2 → 说明/结论
 *
 * 联动：从 G1-2 带入；测试结果推送明细层级与单位公允；附注可汇总层次。
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  parseNum,
  calcFairValue,
  calcLevel1Diff,
  calcSubtotal,
} from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { TradingDetailRow } from './useG1Detail'
import {
  matchSecurityKey,
  findBySecurityKeys,
  loadDetailPartials,
  dispatchG1DetailUpdated,
  pushItemsToG1Adjustment,
} from './g1CrossHelpers'

export type FvLevel = 1 | 2 | 3

export const G1_VALUATION_METHOD_OPTIONS = [
  '市场报价',
  '市场法',
  '收益法',
  '成本法',
  '现金流折现',
  '期权定价',
  '其他',
] as const

export interface G1FairValueRow {
  id: string
  seq: number
  securityName: string
  securityCode: string
  /** 期末账面 — 数量 */
  quantity: number
  /** 期末账面 — 单位公允（辅助） */
  bookUnitFv: number
  /** 期末账面 — 公允价值 */
  bookValue: number
  fvLevel: FvLevel
  valuationMethod: string
  methodConsistentWithPrior: 'yes' | 'no' | ''
  quoteDate: string
  quoteSource: string
  quoteValue: number
  marketValue: number
  level1Diff: number
  /** Level2：可观察输入来源及调整 */
  observableDesc: string
  level2Result: number
  level2Diff: number
  /** Level3 */
  valuationTechnique: string
  unobservableInput: string
  unobservableInputValue: string
  assumption: string
  sensitivityAnalysis: string
  level3Result: number
  level3Diff: number
  /** 当前层级测试/审定公允价值 */
  testedValue: number
  /** 差异 = 测试值 − 账面 */
  activeDiff: number
  valuationDocIndex: string
  conclusion: string
  remark: string
}

export interface G1FvGates {
  levelPolicyReviewed: boolean
  quoteSourceVerified: boolean
  level3AssumptionsNoted: boolean
}

const DATA_KEY = 'G1-6-rows'
const GATES_KEY = 'G1-6-gates'
const DETAIL_KEY = 'G1-2-rows'
const CONCLUSION_KEY = 'G1-6-conclusion'
const DIFF_THRESHOLD = 0.01

export const DEFAULT_G1_FV_GATES: G1FvGates = {
  levelPolicyReviewed: false,
  quoteSourceVerified: false,
  level3AssumptionsNoted: false,
}

function genId(): string {
  return `g1fv-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function matchKey(name: string, code = ''): string {
  return `${(name || '').trim().toLowerCase()}|${(code || '').trim().toLowerCase()}`
}

function emptyRow(id: string, seq = 1): G1FairValueRow {
  return {
    id,
    seq,
    securityName: '',
    securityCode: '',
    quantity: 0,
    bookUnitFv: 0,
    bookValue: 0,
    fvLevel: 1,
    valuationMethod: '市场报价',
    methodConsistentWithPrior: 'yes',
    quoteDate: '',
    quoteSource: '',
    quoteValue: 0,
    marketValue: 0,
    level1Diff: 0,
    observableDesc: '',
    level2Result: 0,
    level2Diff: 0,
    valuationTechnique: '',
    unobservableInput: '',
    unobservableInputValue: '',
    assumption: '',
    sensitivityAnalysis: '',
    level3Result: 0,
    level3Diff: 0,
    testedValue: 0,
    activeDiff: 0,
    valuationDocIndex: '',
    conclusion: '',
    remark: '',
  }
}

export function enrichFvRow(r: G1FairValueRow): G1FairValueRow {
  const qty = parseNum(r.quantity)
  const bookUnit = parseNum(r.bookUnitFv)
  const quote = parseNum(r.quoteValue)
  let book = parseNum(r.bookValue)
  if (bookUnit !== 0 && qty !== 0 && book === 0) {
    book = calcFairValue(qty, bookUnit)
  }
  const marketValue = calcFairValue(qty, quote)
  const level1Diff = calcLevel1Diff(qty, quote, book)
  const level2Result = parseNum(r.level2Result)
  const level3Result = parseNum(r.level3Result)
  const level2Diff = level2Result - book
  const level3Diff = level3Result - book
  const level = (r.fvLevel === 2 || r.fvLevel === 3 ? r.fvLevel : 1) as FvLevel
  const testedValue = level === 1 ? marketValue : level === 2 ? level2Result : level3Result
  const activeDiff = testedValue - book
  return {
    ...r,
    quantity: qty,
    bookUnitFv: bookUnit,
    bookValue: book,
    fvLevel: level,
    quoteValue: quote,
    marketValue,
    level1Diff,
    level2Result,
    level2Diff,
    level3Result,
    level3Diff,
    testedValue,
    activeDiff,
  }
}

/** 旧行 / 导入行迁移 */
export function migrateFvRaw(raw: Record<string, unknown>, seq: number): G1FairValueRow {
  const id = String(raw.id || raw.rowId || genId())
  const qty = parseNum(raw.quantity ?? raw.bookQty)
  const bookUnit = parseNum(raw.bookUnitFv ?? raw.unitFairValue)
  const book = parseNum(raw.bookValue ?? raw.bookFv)
  let fvLevel: FvLevel = 1
  const lv = raw.fvLevel ?? raw.fairValueLevel
  if (lv === 2 || lv === '2' || lv === 'Level2' || lv === 'Level 2') fvLevel = 2
  else if (lv === 3 || lv === '3' || lv === 'Level3' || lv === 'Level 3') fvLevel = 3

  const consistent = String(raw.methodConsistentWithPrior ?? 'yes')
  const methodConsistentWithPrior: G1FairValueRow['methodConsistentWithPrior'] =
    consistent === 'no' || consistent === '否' ? 'no' : consistent === '' ? '' : 'yes'

  return enrichFvRow({
    ...emptyRow(id, seq),
    securityName: String(raw.securityName ?? ''),
    securityCode: String(raw.securityCode ?? ''),
    quantity: qty,
    bookUnitFv: bookUnit,
    bookValue: book,
    fvLevel,
    valuationMethod: String(raw.valuationMethod || (fvLevel === 1 ? '市场报价' : '')),
    methodConsistentWithPrior,
    quoteDate: String(raw.quoteDate ?? ''),
    quoteSource: String(raw.quoteSource ?? raw.valuationSource ?? ''),
    quoteValue: parseNum(raw.quoteValue ?? raw.auditedUnitFv),
    observableDesc: String(raw.observableDesc ?? raw.inputSourceAndAdjustment ?? ''),
    level2Result: parseNum(raw.level2Result ?? raw.auditedFv),
    valuationTechnique: String(raw.valuationTechnique ?? ''),
    unobservableInput: String(raw.unobservableInput ?? raw.unobservableInputDesc ?? ''),
    unobservableInputValue: String(raw.unobservableInputValue ?? ''),
    assumption: String(raw.assumption ?? ''),
    sensitivityAnalysis: String(raw.sensitivityAnalysis ?? ''),
    level3Result: parseNum(raw.level3Result ?? raw.auditedFv),
    valuationDocIndex: String(raw.valuationDocIndex ?? raw.indexRef ?? ''),
    conclusion: String(raw.conclusion ?? ''),
    remark: String(raw.remark ?? ''),
  })
}

export function validateG1Level3(row: G1FairValueRow): string[] {
  if (row.fvLevel !== 3) return []
  const missing: string[] = []
  if (!row.valuationTechnique?.trim() && !row.assumption?.trim()) missing.push('估值技术/假设')
  if (!row.unobservableInput?.trim()) missing.push('不可观察输入值')
  return missing
}

/** Level 互斥启用列（编制提示 / 测试） */
export function getEnabledValuationColumns(level: FvLevel) {
  const level1Cols = ['quoteDate', 'quoteSource', 'quoteValue', 'marketValue', 'level1Diff']
  const level2Cols = ['observableDesc', 'valuationMethod', 'level2Result', 'level2Diff']
  const level3Cols = [
    'valuationTechnique',
    'unobservableInput',
    'unobservableInputValue',
    'assumption',
    'level3Result',
    'level3Diff',
  ]
  return {
    level1Enabled: level === 1,
    level2Enabled: level === 2,
    level3Enabled: level === 3,
    enabledCols: level === 1 ? level1Cols : level === 2 ? level2Cols : level3Cols,
  }
}

function loadRowsPayload(map: Map<string, ChecklistResponse>): string | undefined {
  const item = map.get(DATA_KEY)
  return item?.conclusion || item?.remark || undefined
}

function loadRows(map: Map<string, ChecklistResponse>): G1FairValueRow[] {
  const raw = loadRowsPayload(map)
  if (!raw) return [enrichFvRow(emptyRow(genId(), 1))]
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || !parsed.length) return [enrichFvRow(emptyRow(genId(), 1))]
    return parsed.map((r: Record<string, unknown>, i: number) => migrateFvRaw(r, i + 1))
  } catch {
    return [enrichFvRow(emptyRow(genId(), 1))]
  }
}

function loadGates(map: Map<string, ChecklistResponse>): G1FvGates {
  const raw = map.get(GATES_KEY)?.conclusion
  if (!raw) return { ...DEFAULT_G1_FV_GATES }
  try {
    return { ...DEFAULT_G1_FV_GATES, ...(JSON.parse(raw) as Partial<G1FvGates>) }
  } catch {
    return { ...DEFAULT_G1_FV_GATES }
  }
}

function loadDetailRows(map: Map<string, ChecklistResponse>): Partial<TradingDetailRow>[] {
  return loadDetailPartials(map)
}

function levelFromDetail(src: string | number | undefined): FvLevel {
  const n = Number(src)
  if (n === 2) return 2
  if (n === 3) return 3
  return 1
}

export function useG1FairValueTest(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1FairValueRow[]>(loadRows(opts.allResponses.value))
  const gates = ref<G1FvGates>(loadGates(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')
  const activeTab = ref<'basic' | 'valuation'>('basic')

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
    gates.value = loadGates(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
  }

  watch(
    () => loadRowsPayload(opts.allResponses.value),
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  const stats = computed(() => {
    const level1 = rows.value.filter((r) => r.fvLevel === 1).length
    const level2 = rows.value.filter((r) => r.fvLevel === 2).length
    const level3 = rows.value.filter((r) => r.fvLevel === 3).length
    const overThreshold = rows.value.filter((r) => Math.abs(r.activeDiff) > DIFF_THRESHOLD).length
    const bookTotal = calcSubtotal(rows.value.map((r) => parseNum(r.bookValue)))
    const testedTotal = calcSubtotal(rows.value.map((r) => parseNum(r.testedValue)))
    const diffTotal = testedTotal - bookTotal
    return { level1, level2, level3, overThreshold, bookTotal, testedTotal, diffTotal }
  })

  const level3Violations = computed(() =>
    rows.value.flatMap((r) => {
      const missing = validateG1Level3(r)
      return missing.length
        ? [{ id: r.id, securityName: r.securityName || `第${r.seq}行`, missing }]
        : []
    }),
  )

  const gatesReady = computed(() => {
    const hasL3 = rows.value.some((r) => r.fvLevel === 3)
    return (
      gates.value.levelPolicyReviewed &&
      gates.value.quoteSourceVerified &&
      (!hasL3 || gates.value.level3AssumptionsNoted)
    )
  })

  const balanceOk = computed(() => Math.abs(stats.value.diffTotal) < DIFF_THRESHOLD)

  function persist() {
    if (opts.isReadonly.value) return
    const payload = JSON.stringify(rows.value)
    // conclusion 为主存储；remark 兼容附注误读
    opts.debouncedSave(DATA_KEY, { conclusion: payload, remark: payload })
  }

  function persistGates() {
    if (opts.isReadonly.value) return
    opts.debouncedSave(GATES_KEY, { conclusion: JSON.stringify(gates.value) })
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateGates(patch: Partial<G1FvGates>) {
    if (opts.isReadonly.value) return
    gates.value = { ...gates.value, ...patch }
    persistGates()
  }

  function updateRow(id: string, patch: Partial<G1FairValueRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.id !== id) return r
      const merged = enrichFvRow({ ...r, ...patch })
      const errs = validateG1Level3(merged)
      if (errs.length) ElMessage.warning(`Level3 建议补全：${errs.join('、')}`)
      return merged
    })
    persist()
  }

  function updateCell(id: string, field: keyof G1FairValueRow, value: unknown) {
    updateRow(id, { [field]: value } as Partial<G1FairValueRow>)
  }

  function addRow() {
    if (opts.isReadonly.value) return
    const seq = rows.value.length + 1
    rows.value = [...rows.value, enrichFvRow(emptyRow(genId(), seq))]
    persist()
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
  }

  /** 从 G1-2 带入名称/代码/数量/账面公允/层级 */
  function syncFromDetail(): number {
    if (opts.isReadonly.value) return 0
    const details = loadDetailRows(opts.allResponses.value)
    if (!details.length) return 0

    const existing = new Map(
      rows.value.map((r) => [matchKey(r.securityName, r.securityCode), r]),
    )
    const next: G1FairValueRow[] = []
    for (const d of details) {
      const name = (d.securityName || '').trim()
      if (!name && !d.securityCode) continue
      const key = matchKey(name, d.securityCode || '')
      const prev = existing.get(key)
      const qty = parseNum(d.closingQuantity)
      const unit = parseNum(d.unitFairValue)
      const book =
        parseNum(d.closingFairValue) ||
        (unit ? calcFairValue(qty, unit) : 0) ||
        parseNum(d.auditedClosingFvTotal)
      const level = prev?.fvLevel || levelFromDetail(d.fairValueSource)
      next.push(
        enrichFvRow({
          ...(prev || emptyRow(genId(), next.length + 1)),
          securityName: name || prev?.securityName || '',
          securityCode: d.securityCode || prev?.securityCode || '',
          quantity: qty || prev?.quantity || 0,
          bookUnitFv: unit || prev?.bookUnitFv || 0,
          bookValue: book || prev?.bookValue || 0,
          fvLevel: level,
          quoteDate: prev?.quoteDate || d.quoteDate || '',
          quoteValue: prev?.quoteValue || (level === 1 ? unit : 0),
          valuationDocIndex: prev?.valuationDocIndex || d.indexRef || '',
          valuationMethod:
            prev?.valuationMethod || (level === 1 ? '市场报价' : prev?.valuationMethod || ''),
        }),
      )
      existing.delete(key)
    }
    for (const leftover of existing.values()) {
      if (leftover.securityName || leftover.bookValue) next.push(leftover)
    }
    if (!next.length) return 0
    rows.value = next.map((r, i) => ({ ...r, seq: i + 1 }))
    persist()
    return next.length
  }

  /**
   * 将测试结果回写 G1-2：公允层级 + 单位公允（L1 用报价；L2/L3 用 测试值/数量）
   */
  function pushToDetail(): number {
    if (opts.isReadonly.value) return 0
    const raw = opts.allResponses.value.get(DETAIL_KEY)?.conclusion
    if (!raw) return 0
    let details: Partial<TradingDetailRow>[]
    try {
      details = JSON.parse(raw)
      if (!Array.isArray(details)) return 0
    } catch {
      return 0
    }

    const byKey = new Map(
      rows.value.map((r) => [matchKey(r.securityName, r.securityCode), r]),
    )
    let n = 0
    const next = details.map((d) => {
      const hit =
        byKey.get(matchKey(d.securityName || '', d.securityCode || '')) ||
        byKey.get(matchKey(d.securityName || ''))
      if (!hit) return d
      n += 1
      const qty = parseNum(hit.quantity) || parseNum(d.closingQuantity)
      let unit = parseNum(hit.quoteValue)
      if (hit.fvLevel !== 1 && qty > 0) {
        unit = parseNum(hit.testedValue) / qty
      } else if (hit.fvLevel === 1) {
        unit = parseNum(hit.quoteValue)
      }
      return {
        ...d,
        fairValueSource: String(hit.fvLevel) as '1' | '2' | '3',
        unitFairValue: unit || parseNum(d.unitFairValue),
        quoteDate: hit.quoteDate || d.quoteDate || '',
      }
    })
    if (n) {
      opts.debouncedSave(DETAIL_KEY, { conclusion: JSON.stringify(next) })
      dispatchG1DetailUpdated('G1-6')
    }
    return n
  }

  /** 超阈值差异推送 G1-3 */
  function pushDiffToAdjustment(): number {
    if (opts.isReadonly.value) return 0
    const targets = rows.value.filter((r) => Math.abs(r.activeDiff) > DIFF_THRESHOLD)
    if (!targets.length) return 0
    return pushItemsToG1Adjustment(
      opts.allResponses.value,
      opts.debouncedSave,
      targets.map((r) => ({
        description: `G1-6 公允测试差异：${r.securityName || '未命名'}`,
        amount: r.activeDiff,
        indexRef: 'G1-6',
        remark: `Level ${r.fvLevel} 测试 ${r.testedValue} − 账面 ${r.bookValue}`,
      })),
      'G1-6',
    )
  }

  /** Level3 行合并写入 G1-7 */
  function pushLevel3ToG1_7(): number {
    if (opts.isReadonly.value) return 0
    const l3 = rows.value.filter((r) => r.fvLevel === 3 && (r.securityName || r.testedValue))
    if (!l3.length) return 0

    let existing: Array<Record<string, unknown>> = []
    const raw = opts.allResponses.value.get('G1-7-rows')?.conclusion
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) existing = parsed
      } catch {
        existing = []
      }
    }

    const byName = new Map(
      existing.map((r) => [String(r.itemName || '').trim().toLowerCase(), r]),
    )
    let n = 0
    for (const r of l3) {
      const name = (r.securityName || '').trim()
      const key = name.toLowerCase()
      const prev = byName.get(key)
      const patch = {
        ...(prev || {
          id: `l3-${Date.now()}-${n}`,
          seq: existing.length + n + 1,
          itemName: name,
          assetClass: 'equity',
          openingBalance: 0,
          transferIn: 0,
          transferOut: 0,
          gainPl: 0,
          investmentIncome: 0,
          purchase: 0,
          issue: 0,
          sale: 0,
          settlement: 0,
          closingBalance: 0,
          unrealizedHeld: 0,
          reportedClosing: 0,
          variance: 0,
          remark: '',
        }),
        itemName: name || String(prev?.itemName || ''),
        reportedClosing: parseNum(r.level3Result) || parseNum(r.bookValue),
        remark: r.assumption
          ? `自 G1-6：${r.assumption}`
          : String(prev?.remark || '自 G1-6 Level3 带入'),
      }
      if (prev) Object.assign(prev, patch)
      else {
        existing.push(patch)
        byName.set(key, patch)
      }
      n += 1
    }
    opts.debouncedSave('G1-7-rows', { conclusion: JSON.stringify(existing) })
    try {
      window.dispatchEvent(new CustomEvent('g1:level3-updated', { detail: { source: 'G1-6', count: n } }))
    } catch {
      /* ignore */
    }
    return n
  }

  function validateLevel3(): boolean {
    const v = level3Violations.value
    if (v.length) {
      ElMessage.warning(`Level3 行缺少：${v.map((x) => x.securityName).join('、')}`)
      return false
    }
    ElMessage.success('Level3 必填项校验通过')
    return true
  }

  return {
    rows,
    gates,
    gatesReady,
    auditConclusion,
    activeTab,
    stats,
    balanceOk,
    level3Violations,
    loadAll,
    updateGates,
    updateRow,
    updateCell,
    addRow,
    removeRow,
    syncFromDetail,
    pushToDetail,
    pushDiffToAdjustment,
    pushLevel3ToG1_7,
    validateLevel3,
    valuationMethodOptions: G1_VALUATION_METHOD_OPTIONS,
    validateG1Level3,
    getEnabledValuationColumns,
  }
}

export default useG1FairValueTest
