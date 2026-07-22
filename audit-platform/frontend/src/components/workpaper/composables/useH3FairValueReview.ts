/**
 * useH3FairValueReview — H3-8 公允价值复核 composable
 *
 * 主表对齐致同模板：账面数(面积/单价/期末余额) vs 复核(参考单价/来源/公允价值/差异)
 * + 评估师信息/方法假设/收益法交叉验证/假设挑战（补充区域）
 *
 * Spec: .kiro/specs/h3-investment-property/
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcSubtotal } from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AppraiserInfo {
  firm: string
  qualification: string
  independence: string
}

/** 主复核表行 — 对齐 Excel H3-8 列 ①~⑨ */
export interface FairValueReviewRow {
  rowId: string
  category: string
  assetName: string
  openingFairValue: number
  area: number
  bookUnitPrice: number
  endingBalance: number
  refUnitPrice: number
  refPriceSource: string
  auditorFairValue: number
  difference: number
  diffReason: string
  methodConsistent: string
  indexRef: string
  remark: string
  // 收益法交叉验证（补充）
  discountRate: number
  rentAssumption: number
  capRate: number
  growthRate: number
  independentCalc: number
  indVsBookDiff: number
  withinRange: boolean
  conclusion: string
  // 向后兼容 H3-11 取数字段
  appraisalValue: number
  bookValue: number
  marketRef: number
}

export interface AssumptionChallengeRow {
  rowId: string
  assumption: string
  appraiserValue: string
  auditorJudgment: string
  difference: string
  reasonableness: string
}

export interface FairValueSubtotal {
  openingFairValue: number
  area: number
  endingBalance: number
  auditorFairValue: number
  difference: number
}

const ITEM_APPRAISER = 'H3-8-appraiser'
const ITEM_METHOD = 'H3-8-method'
const ITEM_CALC_ROWS = 'H3-8-calc-rows'
const ITEM_CHALLENGE = 'H3-8-challenge-rows'
const ITEM_H32_ROWS = 'H3-2-fair-rows'
const ITEM_H31_FAIR_ROWS = 'H3-1-fair-rows'
const ITEM_H14_ROWS = 'H3-14-contract-rows'
const ITEM_H14_ROWS_LEGACY = 'H3-14-rental-rows'

const DEFAULT_GROWTH = 0.02
const RANGE_TOLERANCE = 0.1

export function calcBookUnitPrice(endingBalance: number, area: number): number {
  return area > 0 ? endingBalance / area : 0
}

export function calcAuditorFairValue(area: number, refUnitPrice: number): number {
  return area * refUnitPrice
}

export function calcFairValueDifference(endingBalance: number, auditorFairValue: number): number {
  return endingBalance - auditorFairValue
}

export function calcIncomeApproachValue(
  monthlyRent: number,
  capRate: number,
  growthRate = DEFAULT_GROWTH,
): number {
  if (capRate <= growthRate || monthlyRent <= 0) return 0
  return (monthlyRent * 12) / (capRate - growthRate)
}

export function isWithinAcceptableRange(
  independentCalc: number,
  benchmark: number,
  tolerance = RANGE_TOLERANCE,
): boolean {
  if (!benchmark) return independentCalc === 0
  return Math.abs(independentCalc - benchmark) <= Math.abs(benchmark) * tolerance
}

/** 由月租金反推隐含资本化率：cap = 年租金/物业价值 + 增长率 */
export function calcImpliedCapRate(
  monthlyRent: number,
  propertyValue: number,
  growthRate = DEFAULT_GROWTH,
): number {
  if (monthlyRent <= 0 || propertyValue <= 0) return 0
  return (monthlyRent * 12) / propertyValue + growthRate
}

function _fmtAmt(n: number): string {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 根据复核结果生成审计说明草稿（纯函数，便于单测） */
export function buildFairValueAuditNoteDraft(input: {
  rows: FairValueReviewRow[]
  appraiser?: AppraiserInfo
  methodText?: string
  h31?: H38ReconcileResult
  h32?: H38ReconcileResult
  highDiffRows?: FairValueReviewRow[]
  outOfRangeRows?: FairValueReviewRow[]
}): string {
  const lines: string[] = []
  const rows = input.rows ?? []
  const ending = rows.reduce((s, r) => s + (r.endingBalance || 0), 0)
  const auditorFv = rows.reduce((s, r) => s + (r.auditorFairValue || 0), 0)
  const diff = ending - auditorFv

  lines.push('【公允价值复核程序执行情况】')
  lines.push(`1. 本期共复核投资性房地产 ${rows.length} 项，账面期末余额合计 ${_fmtAmt(ending)}，按参考单价×面积测算公允价值合计 ${_fmtAmt(auditorFv)}，差异合计 ${_fmtAmt(diff)}。`)

  const withSource = rows.filter((r) => r.refPriceSource)
  if (withSource.length) {
    const sources = [...new Set(withSource.map((r) => r.refPriceSource).filter(Boolean))]
    lines.push(`2. 参考单价来源主要包括：${sources.slice(0, 5).join('；')}${sources.length > 5 ? '等' : ''}。`)
  } else {
    lines.push('2. 参考单价来源尚待补充，请注明成交案例、评估报告或市场指数索引。')
  }

  const high = input.highDiffRows ?? rows.filter((r) => {
    if (!r.endingBalance) return Math.abs(r.difference) > 0
    return Math.abs(r.difference / r.endingBalance) > 0.2
  })
  if (high.length) {
    lines.push(`3. 差异率超过 20% 的物业共 ${high.length} 项：`)
    for (const r of high.slice(0, 8)) {
      const rate = r.endingBalance ? ((r.difference / r.endingBalance) * 100).toFixed(1) : '-'
      lines.push(`   - ${r.assetName || '未命名'}：账面 ${_fmtAmt(r.endingBalance)}，复核 ${_fmtAmt(r.auditorFairValue)}，差异 ${_fmtAmt(r.difference)}（${rate}%）${r.diffReason ? `；原因：${r.diffReason}` : '；原因待说明'}`)
    }
  } else {
    lines.push('3. 各物业账面期末与复核公允价值差异率均未超过 20%，未见重大异常。')
  }

  const out = input.outOfRangeRows ?? []
  if (out.length) {
    lines.push(`4. 收益法交叉验证超出 ±10% 合理区间的物业 ${out.length} 项，已执行/拟执行假设挑战。`)
  }

  const ai = input.appraiser
  if (ai?.firm || ai?.independence) {
    lines.push(`5. 评估机构：${ai.firm || '（待填）'}；资质：${ai.qualification || '（待填）'}；独立性：${ai.independence || '（待填）'}。`)
  }
  if (input.methodText?.trim()) {
    lines.push(`6. 评估方法与关键假设：${input.methodText.trim().slice(0, 200)}${input.methodText.length > 200 ? '…' : ''}`)
  }

  if (input.h31) {
    lines.push(`7. 与 H3-1 审定表勾稽：${input.h31.note}`)
  }
  if (input.h32) {
    lines.push(`8. 与 H3-2 明细表勾稽：${input.h32.note}`)
  }

  return lines.join('\n')
}

/** 根据异常情况推荐审计结论草稿 */
export function buildFairValueConclusionDraft(input: {
  highDiffCount: number
  outOfRangeCount: number
  h31Matched: boolean
  hasData: boolean
}): string {
  if (!input.hasData) {
    return 'C、公允价值复核尚未完成，审计范围受限，本期不可确认。'
  }
  if (!input.h31Matched || input.highDiffCount > 0 || input.outOfRangeCount > 0) {
    return 'B、除下列事项外未见异常：\n1. （请列示差异率超阈值或勾稽差异事项及拟调整）\n2. （如有）假设挑战后仍存疑事项。'
  }
  return 'A、经复核，投资性房地产公允价值计量恰当，参考单价来源可靠，与 H3-1/H3-2 勾稽一致，未见异常。'
}

export interface H38ReconcileResult {
  source: string
  sourceTotal: number
  h38Total: number
  diff: number
  matched: boolean
  note: string
}

function _matchAssetName(a: string, b: string): boolean {
  const x = a.trim()
  const y = b.trim()
  if (!x || !y) return false
  return x === y || x.includes(y) || y.includes(x)
}

function _sumH31FairAudited(raw: any): number {
  const rows = Array.isArray(raw) ? raw : []
  return rows.reduce((sum: number, r: any) => {
    const audited = Number(r.audited)
    if (audited) return sum + audited
    const end = Number(r.endFair)
    if (end) return sum + end
    return sum
  }, 0)
}

function _sumH32FairEnd(raw: any): number {
  const rows = Array.isArray(raw) ? raw : []
  return rows.reduce((sum: number, r: any) => sum + (Number(r.fairValueEnd) || 0), 0)
}

export function useH3FairValueReview(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params

  const appraiserInfo = ref<AppraiserInfo>({ firm: '', qualification: '', independence: '' })
  const methodText = ref<string>('')
  const calcRows = ref<FairValueReviewRow[]>([])
  const challengeRows = ref<AssumptionChallengeRow[]>([])

  function loadData(): void {
    const ai = getValue(ITEM_APPRAISER)
    if (ai && typeof ai === 'object') appraiserInfo.value = { ...appraiserInfo.value, ...ai }
    const mt = getValue(ITEM_METHOD)
    methodText.value = typeof mt === 'string' ? mt : (mt?.text ?? '')
    const rawCalc = getValue(ITEM_CALC_ROWS)
    calcRows.value = Array.isArray(rawCalc) ? rawCalc.map(_normCalc) : []
    const rawChallenge = getValue(ITEM_CHALLENGE)
    challengeRows.value = Array.isArray(rawChallenge) ? rawChallenge.map(_normChallenge) : []
  }

  function _normCalc(raw: any): FairValueReviewRow {
    const ending = Number(raw.endingBalance ?? raw.appraisalValue ?? raw.bookValue) || 0
    const area = Number(raw.area) || 0
    const refPrice = Number(raw.refUnitPrice ?? raw.marketRef) || 0
    const bookUnit = calcBookUnitPrice(ending, area)
    const auditorFv = calcAuditorFairValue(area, refPrice)
    const diff = calcFairValueDifference(ending, auditorFv)
    const rent = Number(raw.rentAssumption ?? raw.rentalAssumption) || 0
    const cap = Number(raw.capRate) || 0
    const growth = Number(raw.growthRate) || DEFAULT_GROWTH
    const indCalc = calcIncomeApproachValue(rent, cap, growth)
    const benchmark = auditorFv > 0 ? auditorFv : ending
    return {
      rowId: raw.rowId ?? `fv-${Math.random().toString(36).slice(2, 8)}`,
      category: raw.category ?? raw.assetType ?? '',
      assetName: raw.assetName ?? '',
      openingFairValue: Number(raw.openingFairValue ?? raw.fairValueBegin) || 0,
      area,
      bookUnitPrice: bookUnit,
      endingBalance: ending,
      refUnitPrice: refPrice,
      refPriceSource: raw.refPriceSource ?? raw.refSource ?? '',
      auditorFairValue: auditorFv,
      difference: diff,
      diffReason: raw.diffReason ?? raw.differenceReason ?? '',
      methodConsistent: raw.methodConsistent ?? raw.consistentWithPrior ?? '',
      indexRef: raw.indexRef ?? raw.index ?? '',
      remark: raw.remark ?? '',
      discountRate: Number(raw.discountRate) || 0,
      rentAssumption: rent,
      capRate: cap,
      growthRate: growth,
      independentCalc: indCalc,
      indVsBookDiff: indCalc - ending,
      withinRange: isWithinAcceptableRange(indCalc, benchmark),
      conclusion: raw.conclusion ?? '',
      appraisalValue: ending,
      bookValue: ending,
      marketRef: refPrice,
    }
  }

  function _normChallenge(raw: any): AssumptionChallengeRow {
    return {
      rowId: raw.rowId ?? `ch-${Math.random().toString(36).slice(2, 8)}`,
      assumption: raw.assumption ?? '',
      appraiserValue: raw.appraiserValue ?? '',
      auditorJudgment: raw.auditorJudgment ?? '',
      difference: raw.difference ?? raw.diff ?? '',
      reasonableness: raw.reasonableness ?? raw.reasonability ?? '',
    }
  }

  const subtotalRow = computed<FairValueSubtotal>(() => ({
    openingFairValue: calcSubtotal(calcRows.value.map((r) => r.openingFairValue)),
    area: calcSubtotal(calcRows.value.map((r) => r.area)),
    endingBalance: calcSubtotal(calcRows.value.map((r) => r.endingBalance)),
    auditorFairValue: calcSubtotal(calcRows.value.map((r) => r.auditorFairValue)),
    difference: calcSubtotal(calcRows.value.map((r) => r.difference)),
  }))

  const highDiffRows = computed(() =>
    calcRows.value.filter((r) => {
      if (!r.endingBalance) return Math.abs(r.difference) > 0
      return Math.abs(r.difference / r.endingBalance) > 0.2
    }),
  )

  const outOfRangeRows = computed(() => calcRows.value.filter((r) => !r.withinRange && r.independentCalc > 0))
  const fairValueChangeTotal = computed(() => calcSubtotal(calcRows.value.map((r) => r.difference)))

  const h31Reconcile = computed<H38ReconcileResult>(() => {
    const h31Total = _sumH31FairAudited(getValue(ITEM_H31_FAIR_ROWS))
    const h38Total = subtotalRow.value.endingBalance
    const diff = h38Total - h31Total
    const matched = Math.abs(diff) < 0.01
    return {
      source: 'H3-1 审定表',
      sourceTotal: h31Total,
      h38Total,
      diff,
      matched,
      note: matched
        ? 'H3-8 期末余额合计与 H3-1 审定数一致。'
        : `H3-8 期末余额合计 ${h38Total.toLocaleString('zh-CN')} 与 H3-1 审定数 ${h31Total.toLocaleString('zh-CN')} 差异 ${diff.toLocaleString('zh-CN')}，请核对明细或调整分录。`,
    }
  })

  const h32Reconcile = computed<H38ReconcileResult>(() => {
    const h32Total = _sumH32FairEnd(getValue(ITEM_H32_ROWS))
    const h38Total = subtotalRow.value.endingBalance
    const diff = h38Total - h32Total
    const matched = Math.abs(diff) < 0.01
    return {
      source: 'H3-2 明细表',
      sourceTotal: h32Total,
      h38Total,
      diff,
      matched,
      note: matched
        ? 'H3-8 期末余额合计与 H3-2 公允期末合计一致。'
        : `H3-8 与 H3-2 期末公允差异 ${diff.toLocaleString('zh-CN')}，请检查是否遗漏物业或明细未更新。`,
    }
  })

  function updateAppraiserInfo(_info?: any): void {
    setValue(ITEM_APPRAISER, appraiserInfo.value)
  }

  function updateMethod(text: string): void {
    methodText.value = text ?? ''
    setValue(ITEM_METHOD, methodText.value)
  }

  function addCalcRow(seed?: Partial<FairValueReviewRow>): void {
    calcRows.value.push(_normCalc({ rowId: `fv-${Date.now()}`, ...seed }))
    setValue(ITEM_CALC_ROWS, calcRows.value)
  }

  function removeCalcRow(index: number): void {
    calcRows.value.splice(index, 1)
    setValue(ITEM_CALC_ROWS, calcRows.value)
  }

  function updateCalcRow(index: number, _row?: any): void {
    const row = calcRows.value[index]
    if (!row) return
    Object.assign(row, _normCalc({ ...row }))
    setValue(ITEM_CALC_ROWS, calcRows.value)
  }

  /** 从 H3-2 公允明细带入主表行（按资产名称去重合并） */
  function importFromH32(): { ok: boolean; message: string; count: number } {
    const raw = getValue(ITEM_H32_ROWS)
    const h32Rows = Array.isArray(raw) ? raw : []
    if (!h32Rows.length) {
      return { ok: false, message: 'H3-2 公允明细无数据，请先编制明细表', count: 0 }
    }
    let count = 0
    for (const src of h32Rows) {
      const name = String(src.assetName ?? '').trim()
      if (!name) continue
      const existing = calcRows.value.find((r) => r.assetName === name)
      const seed = {
        category: src.assetType ?? '',
        assetName: name,
        openingFairValue: Number(src.fairValueBegin) || 0,
        area: Number(src.area) || 0,
        endingBalance: Number(src.fairValueEnd) || 0,
        remark: src.remark ?? '',
      }
      if (existing) {
        Object.assign(existing, _normCalc({ ...existing, ...seed }))
      } else {
        calcRows.value.push(_normCalc({ rowId: `fv-${Date.now()}-${count}`, ...seed }))
      }
      count++
    }
    setValue(ITEM_CALC_ROWS, calcRows.value)
    return { ok: true, message: `已从 H3-2 带入 ${count} 项物业`, count }
  }

  /** 从 H3-14 租金合同带入月租金、面积，并反推隐含资本化率 */
  function importRentalFromH14(): { ok: boolean; message: string; count: number } {
    let raw = getValue(ITEM_H14_ROWS)
    if (!Array.isArray(raw) || !raw.length) raw = getValue(ITEM_H14_ROWS_LEGACY)
    const h14Rows = Array.isArray(raw) ? raw : []
    if (!h14Rows.length) {
      return { ok: false, message: 'H3-14 无租金合同数据，请先编制租金收入测算表', count: 0 }
    }
    let count = 0
    for (const src of h14Rows) {
      const name = String(src.assetName ?? '').trim()
      const monthly = Number(src.monthlyRent) || 0
      if (!name || monthly <= 0) continue
      let row = calcRows.value.find((r) => _matchAssetName(r.assetName, name))
      if (!row) {
        row = _normCalc({ rowId: `fv-${Date.now()}-${count}`, assetName: name })
        calcRows.value.push(row)
      }
      row.rentAssumption = monthly
      if (!row.area && Number(src.area) > 0) row.area = Number(src.area)
      const benchmark = row.endingBalance > 0 ? row.endingBalance : row.auditorFairValue
      if (benchmark > 0) {
        row.capRate = calcImpliedCapRate(monthly, benchmark, row.growthRate || DEFAULT_GROWTH)
      }
      if (src.contractIndex && !row.indexRef) row.indexRef = String(src.contractIndex)
      if (!row.refPriceSource && src.contractIndex) {
        row.refPriceSource = `H3-14 合同 ${src.contractIndex}`
      }
      Object.assign(row, _normCalc({ ...row }))
      count++
    }
    setValue(ITEM_CALC_ROWS, calcRows.value)
    return { ok: true, message: `已从 H3-14 带入 ${count} 项租金并推算资本化率`, count }
  }

  /** OCR 结果写入参考单价（总额÷面积）或来源说明 */
  function applyRefPriceOcr(index: number, ocr: { amount?: number; counterparty?: string; date?: string }): void {
    const row = calcRows.value[index]
    if (!row) return
    const amount = Number(ocr.amount) || 0
    if (amount > 0) {
      if (row.area > 0 && amount > row.area) {
        row.refUnitPrice = amount / row.area
      } else if (amount < 1_000_000) {
        row.refUnitPrice = amount
      } else if (row.area > 0) {
        row.refUnitPrice = amount / row.area
      }
    }
    const parts = [ocr.counterparty, ocr.date].filter(Boolean)
    if (parts.length) {
      row.refPriceSource = `OCR: ${parts.join(' / ')}`
    } else if (!row.refPriceSource) {
      row.refPriceSource = 'OCR识别'
    }
    Object.assign(row, _normCalc({ ...row }))
    setValue(ITEM_CALC_ROWS, calcRows.value)
  }

  function addChallengeRow(): void {
    challengeRows.value.push(_normChallenge({}))
    setValue(ITEM_CHALLENGE, challengeRows.value)
  }

  function updateChallengeRow(index: number, _row?: any): void {
    if (!challengeRows.value[index]) return
    setValue(ITEM_CHALLENGE, challengeRows.value)
  }

  function draftAuditNote(): string {
    return buildFairValueAuditNoteDraft({
      rows: calcRows.value,
      appraiser: appraiserInfo.value,
      methodText: methodText.value,
      h31: h31Reconcile.value,
      h32: h32Reconcile.value,
      highDiffRows: highDiffRows.value,
      outOfRangeRows: outOfRangeRows.value,
    })
  }

  function draftAuditConclusion(): string {
    return buildFairValueConclusionDraft({
      highDiffCount: highDiffRows.value.length,
      outOfRangeCount: outOfRangeRows.value.length,
      h31Matched: h31Reconcile.value.matched || h31Reconcile.value.sourceTotal === 0,
      hasData: calcRows.value.length > 0 && subtotalRow.value.endingBalance > 0,
    })
  }

  watch(allResponses, () => loadData(), { immediate: true })

  return {
    appraiserInfo,
    methodText,
    calcRows,
    challengeRows,
    reviewCalcRows: calcRows,
    subtotalRow,
    highDiffRows,
    outOfRangeRows,
    fairValueChangeTotal,
    h31Reconcile,
    h32Reconcile,
    updateAppraiserInfo,
    updateMethod,
    addCalcRow,
    removeCalcRow,
    updateCalcRow,
    importFromH32,
    importRentalFromH14,
    applyRefPriceOcr,
    addChallengeRow,
    updateChallengeRow,
    draftAuditNote,
    draftAuditConclusion,
    loadData,
  }
}

export default useH3FairValueReview
