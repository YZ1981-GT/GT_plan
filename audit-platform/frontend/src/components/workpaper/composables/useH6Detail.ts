/**
 * useH6Detail — H6-2 明细表 composable
 *
 * 对齐致同模板编制逻辑（数字化适配）：
 * - 逐项跟踪清理全过程（原值/折旧/减值 → 净值 → 收入费用 → 净损益 → 结转）
 * - 余额变动（对齐 xlsx）：期初/本期增减/期末 × 未审·期初调整·账项增减 → 审定
 * - 挂账关注：转入清理超 1 年须说明进展
 * - 与 H6-1 审定表交叉验证；H1-8 / H10 索引联动
 *
 * Saves to "H6-2-rows"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcNetBookValue,
  calcDisposalGainLoss,
  calcSubtotal,
  isClearingOverOneYear,
  defaultH6PeriodEnd,
  calcH62EndUnadjusted,
  calcH62BeginAudited,
  calcH62EndAdjustment,
  calcH62EndAudited,
} from './useH6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 清理原因（对齐致同 md：出售/报废/毁损/对外投资/非货币性资产交换/债务重组） */
export const H6_DISPOSAL_REASON_OPTIONS = [
  '出售',
  '报废',
  '毁损',
  '对外投资',
  '非货币性资产交换',
  '债务重组',
  '其他',
] as const

export type H6DisposalReason = (typeof H6_DISPOSAL_REASON_OPTIONS)[number] | ''

/** H6-2 明细表行 */
export interface H6DetailRow {
  rowId: string

  // ═══ 区块1: 基础信息 ═══
  seq: number
  assetName: string
  originalCost: number
  accumulatedDepreciation: number
  /** 减值准备（转入清理时一并转销） */
  impairmentProvision: number
  /** 净值 = 原值 - 累计折旧 - 减值准备 */
  netBookValue: number
  disposalReason: string
  startDate: string

  // ═══ 区块2: 清理信息 ═══
  disposalIncome: number
  disposalExpenses: number
  taxAmount: number
  /** 净损益 = 处置收入 - 净值 - 清理费用 - 税费 */
  gainLoss: number
  transferAccount: string
  completionDate: string
  status: '清理中' | '已完成' | '已结转'
  refH1Code: string
  refH10Code: string

  // ═══ 区块3: 余额变动（对齐 Excel H6-2 B–L） ═══
  /** 未审·期初 */
  beginUnadjusted: number
  /** 未审·本期增加 */
  periodIncrease: number
  /** 未审·本期减少 */
  periodDecrease: number
  /** 未审·期末（公式 = 期初+增加−减少） */
  endUnadjusted: number
  /** 期初调整 */
  beginAdjustment: number
  /** 账项调整·本期增加 */
  ajeIncrease: number
  /** 账项调整·本期减少 */
  ajeDecrease: number
  /** 审定·期初（= 期初未审 + 期初调整） */
  beginAudited: number
  /** 审定·本期增加（= 未审增加 + 账项增加） */
  increaseAudited: number
  /** 审定·本期减少（= 未审减少 + 账项减少） */
  decreaseAudited: number
  /** 审定·期末（= 审定期初 + 审定增加 − 审定减少） */
  endAudited: number
  /** 供 H6-1 期末账项列：期初调整+账项增加−账项减少 */
  endAdjustment: number

  // ═══ 区块4: 挂账关注（对齐 xlsx 定性列） ═══
  /** 转入清理起始时间已超过1年的进展说明 */
  overOneYearProgress: string
  remarks: string
}

/** 明细表Tab类型 */
export type H6DetailTab = 'basic' | 'balance' | 'disposal' | 'aging'

/** 状态选项 */
export const H6_DETAIL_STATUS_OPTIONS = ['清理中', '已完成', '已结转'] as const

/** 行级警告类型 */
export type H6DetailWarningKind =
  | 'over_one_year_no_progress'
  | 'transferred_missing_account'
  | 'uncleared'

export interface H6DetailRowWarning {
  kind: H6DetailWarningKind
  message: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H6-2-rows'
const SUBTOTAL_GAIN_LOSS_KEY = 'H6-2-subtotal-gain-loss'
const SUBTOTAL_END_KEY = 'H6-2-subtotal-net-book-value'
const SUBTOTAL_BEGIN_UNADJ_KEY = 'H6-2-subtotal-begin-unadjusted'
const SUBTOTAL_END_UNADJ_KEY = 'H6-2-subtotal-end-unadjusted'
const SUBTOTAL_BEGIN_AUDITED_KEY = 'H6-2-subtotal-begin-audited'
const SUBTOTAL_END_AUDITED_KEY = 'H6-2-subtotal-end-audited'

// ─── Pure helpers（可单测） ───────────────────────────────────────────────────

/** 行级审计警告：净损益≠0 在已结转后属正常，不应告警 */
export function getDetailRowWarnings(
  row: Pick<
    H6DetailRow,
    'status' | 'startDate' | 'overOneYearProgress' | 'transferAccount'
  >,
  asOfDate: string,
): H6DetailRowWarning[] {
  const out: H6DetailRowWarning[] = []
  const overYear = isClearingOverOneYear(row.startDate, asOfDate)
  const uncleared = row.status !== '已结转'

  if (overYear && uncleared && !row.overOneYearProgress?.trim()) {
    out.push({
      kind: 'over_one_year_no_progress',
      message: '转入清理已超1年且未结转，请填写进展情况',
    })
  }
  if (row.status === '已结转' && !row.transferAccount?.trim()) {
    out.push({
      kind: 'transferred_missing_account',
      message: '已结转但未填写结转科目',
    })
  }
  if (uncleared) {
    out.push({
      kind: 'uncleared',
      message: '清理尚未结转（过渡科目仍有余额风险）',
    })
  }
  return out
}

/** 重算余额变动公式列（对齐 Excel E/I/J/K/L 及 H6-1!F） */
export function applyH62BalanceFormulas(row: Pick<
  H6DetailRow,
  | 'beginUnadjusted'
  | 'periodIncrease'
  | 'periodDecrease'
  | 'beginAdjustment'
  | 'ajeIncrease'
  | 'ajeDecrease'
>): Pick<
  H6DetailRow,
  | 'endUnadjusted'
  | 'beginAudited'
  | 'increaseAudited'
  | 'decreaseAudited'
  | 'endAudited'
  | 'endAdjustment'
> {
  const endUnadjusted = calcH62EndUnadjusted(
    row.beginUnadjusted,
    row.periodIncrease,
    row.periodDecrease,
  )
  const beginAudited = calcH62BeginAudited(row.beginUnadjusted, row.beginAdjustment)
  const increaseAudited = row.periodIncrease + row.ajeIncrease
  const decreaseAudited = row.periodDecrease + row.ajeDecrease
  const endAudited = calcH62EndAudited(beginAudited, increaseAudited, decreaseAudited)
  const endAdjustment = calcH62EndAdjustment(
    row.beginAdjustment,
    row.ajeIncrease,
    row.ajeDecrease,
  )
  return { endUnadjusted, beginAudited, increaseAudited, decreaseAudited, endAudited, endAdjustment }
}

/**
 * 旧存档无余额列时，按净值/状态推导初始余额变动（不覆盖已有手工数）。
 * - 清理中/已完成：期初0、增加=净值、期末=净值
 * - 已结转：期初0、增加=净值、减少=净值、期末0
 */
export function seedBalanceFromNetBook(
  netBookValue: number,
  status: string,
  existing?: Partial<H6DetailRow>,
): Pick<
  H6DetailRow,
  | 'beginUnadjusted'
  | 'periodIncrease'
  | 'periodDecrease'
  | 'beginAdjustment'
  | 'ajeIncrease'
  | 'ajeDecrease'
> {
  const hasAny =
    existing
    && (
      existing.beginUnadjusted != null
      || existing.periodIncrease != null
      || existing.periodDecrease != null
      || existing.endUnadjusted != null
      || existing.beginAdjustment != null
      || existing.ajeIncrease != null
      || existing.ajeDecrease != null
    )

  if (hasAny) {
    return {
      beginUnadjusted: Number(existing!.beginUnadjusted) || 0,
      periodIncrease: Number(existing!.periodIncrease) || 0,
      periodDecrease: Number(existing!.periodDecrease) || 0,
      beginAdjustment: Number(existing!.beginAdjustment) || 0,
      ajeIncrease: Number(existing!.ajeIncrease) || 0,
      ajeDecrease: Number(existing!.ajeDecrease) || 0,
    }
  }

  const nbv = Number(netBookValue) || 0
  const transferred = status === '已结转'
  return {
    beginUnadjusted: 0,
    periodIncrease: nbv,
    periodDecrease: transferred ? nbv : 0,
    beginAdjustment: 0,
    ajeIncrease: 0,
    ajeDecrease: 0,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH6Detail(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  /** 报表截止日 YYYY-MM-DD，用于超1年判定 */
  periodEndDate?: Ref<string | undefined>
}) {
  const { allResponses, onSave, periodEndDate } = params

  const rows = ref<H6DetailRow[]>([])
  const activeTab = ref<H6DetailTab>('basic')

  const asOfDate = computed(() => {
    const ext = periodEndDate?.value?.trim()
    return ext || defaultH6PeriodEnd()
  })

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  /** 规范化行（加载后重算公式列） */
  function _normalizeRow(raw: any, idx: number): H6DetailRow {
    const cost = Number(raw.originalCost) || 0
    const dep = Number(raw.accumulatedDepreciation ?? raw.accDepreciation ?? raw.accDep) || 0
    const impair = Number(raw.impairmentProvision ?? raw.impairment) || 0
    const income = Number(raw.disposalIncome) || 0
    const expenses = Number(raw.disposalExpenses) || 0
    const tax = Number(raw.taxAmount ?? raw.tax) || 0
    const status = H6_DETAIL_STATUS_OPTIONS.includes(raw.status) ? raw.status : '清理中'

    const netBookValue = calcNetBookValue(cost, dep, impair)
    const gainLoss = calcDisposalGainLoss(income, netBookValue, expenses, tax)
    const bal = seedBalanceFromNetBook(netBookValue, status, raw)
    const formulas = applyH62BalanceFormulas(bal)

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      seq: raw.seq ?? idx + 1,
      assetName: raw.assetName ?? '',
      originalCost: cost,
      accumulatedDepreciation: dep,
      impairmentProvision: impair,
      netBookValue,
      disposalReason: raw.disposalReason ?? '',
      startDate: raw.startDate ?? '',
      disposalIncome: income,
      disposalExpenses: expenses,
      taxAmount: tax,
      gainLoss,
      transferAccount: raw.transferAccount ?? '',
      completionDate: raw.completionDate ?? '',
      status,
      refH1Code: raw.refH1Code ?? raw.h1Reference ?? '',
      refH10Code: raw.refH10Code ?? raw.h10Reference ?? '',
      ...bal,
      ...formulas,
      overOneYearProgress: raw.overOneYearProgress ?? '',
      remarks: raw.remarks ?? '',
    }
  }

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map((r, i) => _normalizeRow(r, i))
    } else {
      rows.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  const subtotalRow = computed(() => ({
    originalCost: calcSubtotal(rows.value.map(r => r.originalCost)),
    accumulatedDepreciation: calcSubtotal(rows.value.map(r => r.accumulatedDepreciation)),
    impairmentProvision: calcSubtotal(rows.value.map(r => r.impairmentProvision)),
    netBookValue: calcSubtotal(rows.value.map(r => r.netBookValue)),
    disposalIncome: calcSubtotal(rows.value.map(r => r.disposalIncome)),
    disposalExpenses: calcSubtotal(rows.value.map(r => r.disposalExpenses)),
    taxAmount: calcSubtotal(rows.value.map(r => r.taxAmount)),
    gainLoss: calcSubtotal(rows.value.map(r => r.gainLoss)),
    beginUnadjusted: calcSubtotal(rows.value.map(r => r.beginUnadjusted)),
    periodIncrease: calcSubtotal(rows.value.map(r => r.periodIncrease)),
    periodDecrease: calcSubtotal(rows.value.map(r => r.periodDecrease)),
    endUnadjusted: calcSubtotal(rows.value.map(r => r.endUnadjusted)),
    beginAdjustment: calcSubtotal(rows.value.map(r => r.beginAdjustment)),
    ajeIncrease: calcSubtotal(rows.value.map(r => r.ajeIncrease)),
    ajeDecrease: calcSubtotal(rows.value.map(r => r.ajeDecrease)),
    beginAudited: calcSubtotal(rows.value.map(r => r.beginAudited)),
    endAudited: calcSubtotal(rows.value.map(r => r.endAudited)),
    endAdjustment: calcSubtotal(rows.value.map(r => r.endAdjustment)),
  }))

  const gainLossTotal: ComputedRef<number> = computed(() => subtotalRow.value.gainLoss)

  const statusSummary = computed(() => ({
    clearing: rows.value.filter(r => r.status === '清理中').length,
    completed: rows.value.filter(r => r.status === '已完成').length,
    transferred: rows.value.filter(r => r.status === '已结转').length,
    total: rows.value.length,
    uncleared: rows.value.filter(r => r.status !== '已结转').length,
    overOneYear: rows.value.filter(r => isClearingOverOneYear(r.startDate, asOfDate.value)).length,
    overOneYearUncleared: rows.value.filter(
      r => isClearingOverOneYear(r.startDate, asOfDate.value) && r.status !== '已结转',
    ).length,
  }))

  const hasCriticalWarning = computed(() =>
    rows.value.some(r => {
      const ws = getDetailRowWarnings(r, asOfDate.value)
      return ws.some(w => w.kind === 'over_one_year_no_progress' || w.kind === 'transferred_missing_account')
    }),
  )

  function rowWarnings(row: H6DetailRow): H6DetailRowWarning[] {
    return getDetailRowWarnings(row, asOfDate.value)
  }

  function isRowOverOneYear(row: H6DetailRow): boolean {
    return isClearingOverOneYear(row.startDate, asOfDate.value)
  }

  function _recalcDisposal(row: H6DetailRow): void {
    row.netBookValue = calcNetBookValue(
      row.originalCost,
      row.accumulatedDepreciation,
      row.impairmentProvision,
    )
    row.gainLoss = calcDisposalGainLoss(
      row.disposalIncome,
      row.netBookValue,
      row.disposalExpenses,
      row.taxAmount,
    )
  }

  function _recalcBalance(row: H6DetailRow): void {
    const f = applyH62BalanceFormulas(row)
    Object.assign(row, f)
  }

  function addRow(assetName: string): void {
    if (!assetName?.trim()) return
    const seq = rows.value.length + 1
    rows.value.push(_normalizeRow({ assetName: assetName.trim(), seq }, seq - 1))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const textFields = [
      'assetName', 'disposalReason', 'startDate', 'transferAccount',
      'completionDate', 'refH1Code', 'refH10Code', 'overOneYearProgress', 'remarks',
    ]
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    if (field === 'status') {
      const prev = row.status
      row.status = H6_DETAIL_STATUS_OPTIONS.includes(value as any) ? value : '清理中'
      // 刚结转：若减少仍为0，自动按当前期末未审结转减少
      if (prev !== '已结转' && row.status === '已结转' && row.periodDecrease === 0 && row.endUnadjusted !== 0) {
        row.periodDecrease = row.beginUnadjusted + row.periodIncrease
        _recalcBalance(row)
      }
      _persist()
      return
    }

    const numVal = Number(value) || 0
    const disposalFields = [
      'originalCost', 'accumulatedDepreciation', 'impairmentProvision',
      'disposalIncome', 'disposalExpenses', 'taxAmount',
    ]
    const balanceFields = [
      'beginUnadjusted', 'periodIncrease', 'periodDecrease',
      'beginAdjustment', 'ajeIncrease', 'ajeDecrease',
    ]

    if (disposalFields.includes(field)) {
      ;(row as any)[field] = numVal
      _recalcDisposal(row)
      _persist()
      return
    }

    if (balanceFields.includes(field)) {
      ;(row as any)[field] = numVal
      _recalcBalance(row)
      _persist()
      return
    }
  }

  function setActiveTab(tab: H6DetailTab): void {
    activeTab.value = tab
  }

  /** 从H1处置事件自动创建清理项目行 */
  function createFromH1Disposal(payload: {
    assetName: string
    originalCost: number
    accDep: number
    impairment?: number
    refH1Code: string
    disposalReason?: string
    startDate?: string
  }): void {
    const seq = rows.value.length + 1
    const nbv = calcNetBookValue(
      payload.originalCost,
      payload.accDep,
      payload.impairment ?? 0,
    )
    rows.value.push(_normalizeRow({
      assetName: payload.assetName,
      originalCost: payload.originalCost,
      accumulatedDepreciation: payload.accDep,
      impairmentProvision: payload.impairment ?? 0,
      disposalReason: payload.disposalReason ?? '',
      startDate: payload.startDate ?? '',
      refH1Code: payload.refH1Code,
      seq,
      // 转入清理：本期增加=净值
      beginUnadjusted: 0,
      periodIncrease: nbv,
      periodDecrease: 0,
      beginAdjustment: 0,
      ajeIncrease: 0,
      ajeDecrease: 0,
    }, seq - 1))
    _persist()
  }

  /**
   * 按净值同步余额「本期增加/期末」：未手工改过余额列时一键对齐。
   * 已结转行：增加=净值、减少=净值、期末=0。
   */
  function syncBalanceFromNetBook(): { applied: number } {
    let applied = 0
    for (const row of rows.value) {
      const nbv = row.netBookValue
      const transferred = row.status === '已结转'
      row.beginUnadjusted = row.beginUnadjusted || 0
      row.periodIncrease = nbv
      row.periodDecrease = transferred ? (row.beginUnadjusted + nbv) : 0
      // 若期初已有余额，未结转期末=期初+增加−减少
      if (!transferred && row.beginUnadjusted !== 0) {
        row.periodIncrease = Math.max(0, nbv - row.beginUnadjusted)
        row.periodDecrease = Math.max(0, row.beginUnadjusted - nbv)
      }
      _recalcBalance(row)
      applied++
    }
    if (applied) _persist()
    return { applied }
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId,
      seq: r.seq,
      assetName: r.assetName,
      originalCost: r.originalCost,
      accumulatedDepreciation: r.accumulatedDepreciation,
      // 兼容旧导入键（导出以规范名为准）
      accDepreciation: r.accumulatedDepreciation,
      impairmentProvision: r.impairmentProvision,
      netBookValue: r.netBookValue,
      disposalReason: r.disposalReason,
      startDate: r.startDate,
      disposalIncome: r.disposalIncome,
      disposalExpenses: r.disposalExpenses,
      taxAmount: r.taxAmount,
      tax: r.taxAmount,
      gainLoss: r.gainLoss,
      netGainLoss: r.gainLoss,
      transferAccount: r.transferAccount,
      completionDate: r.completionDate,
      status: r.status,
      refH1Code: r.refH1Code,
      h1Reference: r.refH1Code,
      refH10Code: r.refH10Code,
      h10Reference: r.refH10Code,
      beginUnadjusted: r.beginUnadjusted,
      periodIncrease: r.periodIncrease,
      periodDecrease: r.periodDecrease,
      endUnadjusted: r.endUnadjusted,
      beginAdjustment: r.beginAdjustment,
      ajeIncrease: r.ajeIncrease,
      ajeDecrease: r.ajeDecrease,
      beginAudited: r.beginAudited,
      endAudited: r.endAudited,
      endAdjustment: r.endAdjustment,
      overOneYearProgress: r.overOneYearProgress,
      remarks: r.remarks,
    }))
    onSave(ROWS_KEY, toPersist)
    onSave(SUBTOTAL_GAIN_LOSS_KEY, gainLossTotal.value)
    onSave(SUBTOTAL_END_KEY, subtotalRow.value.netBookValue)
    onSave(SUBTOTAL_BEGIN_UNADJ_KEY, subtotalRow.value.beginUnadjusted)
    onSave(SUBTOTAL_END_UNADJ_KEY, subtotalRow.value.endUnadjusted)
    onSave(SUBTOTAL_BEGIN_AUDITED_KEY, subtotalRow.value.beginAudited)
    onSave(SUBTOTAL_END_AUDITED_KEY, subtotalRow.value.endAudited)
  }

  return {
    rows,
    activeTab,
    asOfDate,
    subtotalRow,
    gainLossTotal,
    statusSummary,
    hasCriticalWarning,
    rowWarnings,
    isRowOverOneYear,
    addRow,
    deleteRow,
    updateCell,
    setActiveTab,
    createFromH1Disposal,
    syncBalanceFromNetBook,
    save,
    load,
  }
}

export default useH6Detail
