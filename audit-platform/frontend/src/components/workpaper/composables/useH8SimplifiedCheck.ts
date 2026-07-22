/**
 * useH8SimplifiedCheck — H8-13 简化处理检查表 composable
 *
 * CAS21第32条：短期租赁(≤12月) / 低价值资产租赁(≤4万) 可选择简化处理
 * 简化处理：不确认使用权资产和租赁负债，直接计入当期费用
 *
 * 双轨逻辑：
 * 1) 资格判断：租赁期≤12月 / 全新价值≤40000 → 简化类型
 * 2) 费用重算：本期应计租金 = 月租金 × 本期应计月数；差异 = 应计 − 账面
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.4
 * Requirements: 8.1-8.4
 */
import { ref, computed, watch, type Ref } from 'vue'
import { isShortTermLease, isLowValueLease } from './useH8CAS21Engine'
import { calcSubtotal } from './useH8FormulaEngine'
import {
  listLeaseTermsFromH85Raw,
  upsertH85ShortTermIntoH813Rows,
  isShortTermLeaseCandidate,
  type H85TermOption,
  type H8LeaseTermRecord,
  resolveEffectiveLeaseTermMonths,
} from './useH8LeaseTerm'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 简化处理类型 */
export type H8SimplifiedType = '短期租赁' | '低价值' | '短期+低价值' | '不符合' | ''

/** H8-13 简化处理检查行 */
export interface H8SimplifiedCheckRow {
  rowId: string
  /** 合同号 */
  contractNo: string
  /** 承租资产 */
  assetName: string
  /** 出租方 */
  lessor: string
  /** 资产类别 */
  assetCategory: string
  /** 租赁期（月） */
  leaseTermMonths: number
  /** 年租金（兼容旧字段；优先用月租金×12 或费用重算） */
  annualRental: number
  /** 资产全新价值 */
  newAssetValue: number
  /** 是否短期租赁（自动判断：≤12月） */
  isShortTerm: boolean
  /** 是否低价值（自动判断：≤4万） */
  isLowValue: boolean
  /** 简化处理类型（自动推导） */
  simplifiedType: H8SimplifiedType
  /** 月租金 */
  monthlyRent: number
  /** 本期应计月数 */
  accrualMonths: number
  /** 本期应计租金（自动：月租金×应计月数） */
  expectedExpense: number
  /** 账面本期租金 */
  bookExpense: number
  /** 差异（自动：应计−账面） */
  difference: number
  /** 与相关科目是否勾稽一致 */
  reconciled: string
  /** 费用科目 */
  expenseAccount: string
  /** 费用确认金额（兼容旧字段；默认同 expectedExpense） */
  expenseAmount: number
  /** 核查结论 */
  conclusion: string
  /** 备注 */
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H8-13-rows'
const H85_RECORDS_KEY = 'H8-5-records'

export interface H813SyncFromH85Result {
  ok: boolean
  reason?: string
  updated: number
  added: number
  mismatchedBefore: number
  details: Array<{ contractNo: string; months: number; action: 'updated' | 'added' }>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _calcExpected(monthlyRent: number, accrualMonths: number): number {
  if (!monthlyRent && !accrualMonths) return 0
  return Math.round(monthlyRent * accrualMonths * 100) / 100
}

function _deriveAnnualRental(monthlyRent: number, annualRental: number): number {
  if (monthlyRent > 0) return Math.round(monthlyRent * 12 * 100) / 100
  return annualRental
}

function _autoConclusion(simplifiedType: H8SimplifiedType, current: string): string {
  if (simplifiedType === '不符合') return '不符合，应确认ROU'
  if (simplifiedType && (!current || current === '待核实' || current === '不符合，应确认ROU')) {
    return '符合简化条件'
  }
  return current || '待核实'
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8SimplifiedCheck(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H8SimplifiedCheckRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  /** 推导简化处理类型 */
  function _deriveSimplifiedType(shortTerm: boolean, lowValue: boolean): H8SimplifiedType {
    if (shortTerm && lowValue) return '短期+低价值'
    if (shortTerm) return '短期租赁'
    if (lowValue) return '低价值'
    return '不符合'
  }

  function _recalcRow(row: H8SimplifiedCheckRow): void {
    row.isShortTerm = isShortTermLease(row.leaseTermMonths)
    row.isLowValue = isLowValueLease(row.newAssetValue)
    row.simplifiedType = _deriveSimplifiedType(row.isShortTerm, row.isLowValue)
    row.expectedExpense = _calcExpected(row.monthlyRent, row.accrualMonths)
    row.difference = Math.round((row.expectedExpense - row.bookExpense) * 100) / 100
    // 兼容旧「费用确认」：若未单独维护则同步应计租金
    if (!row.expenseAmount || row.expenseAmount === 0) {
      row.expenseAmount = row.expectedExpense
    }
    row.annualRental = _deriveAnnualRental(row.monthlyRent, row.annualRental)
    row.conclusion = _autoConclusion(row.simplifiedType, row.conclusion)
  }

  function _normalizeRow(raw: any): H8SimplifiedCheckRow {
    const leaseMonths = Number(raw.leaseTermMonths ?? raw.termMonths) || 0
    const assetValue = Number(raw.newAssetValue) || 0
    const monthlyRent = Number(raw.monthlyRent) || 0
    const accrualMonths = Number(raw.accrualMonths) || 0
    const bookExpense = Number(raw.bookExpense ?? raw.expenseAmount) || 0
    const annualRental = Number(raw.annualRental ?? raw.annualRent) || 0
    // 旧数据仅有年租金时，回推月租金便于重算
    const derivedMonthly = monthlyRent > 0
      ? monthlyRent
      : (annualRental > 0 ? Math.round((annualRental / 12) * 100) / 100 : 0)
    const derivedAccrual = accrualMonths > 0 ? accrualMonths : (derivedMonthly > 0 ? Math.min(leaseMonths || 12, 12) : 0)

    const row: H8SimplifiedCheckRow = {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      contractNo: raw.contractNo ?? '',
      assetName: raw.assetName ?? '',
      lessor: raw.lessor ?? '',
      assetCategory: raw.assetCategory ?? '',
      leaseTermMonths: leaseMonths,
      annualRental,
      newAssetValue: assetValue,
      isShortTerm: false,
      isLowValue: false,
      simplifiedType: '',
      monthlyRent: derivedMonthly,
      accrualMonths: derivedAccrual,
      expectedExpense: 0,
      bookExpense,
      difference: 0,
      reconciled: raw.reconciled ?? '',
      expenseAccount: raw.expenseAccount ?? '',
      expenseAmount: Number(raw.expenseAmount) || 0,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
    _recalcRow(row)
    return row
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      rows.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed: 底部统计 ────────────────────────────────────────────────────

  /** 简化处理笔数（短期或低价值） */
  const simplifiedCount = computed(() =>
    rows.value.filter(r => r.simplifiedType !== '不符合' && r.simplifiedType !== '').length,
  )

  /** 应转为使用权资产笔数（不符合简化条件） */
  const mustRecognizeCount = computed(() =>
    rows.value.filter(r => r.simplifiedType === '不符合').length,
  )

  /** 总年租金（简化处理部分） */
  const totalAnnualRental = computed(() =>
    calcSubtotal(
      rows.value
        .filter(r => r.simplifiedType !== '不符合' && r.simplifiedType !== '')
        .map(r => r.annualRental),
    ),
  )

  /** 全部年租金 */
  const totalAllRental = computed(() =>
    calcSubtotal(rows.value.map(r => r.annualRental)),
  )

  /** 本期应计租金合计 */
  const totalExpectedExpense = computed(() =>
    calcSubtotal(rows.value.map(r => r.expectedExpense)),
  )

  /** 账面本期租金合计 */
  const totalBookExpense = computed(() =>
    calcSubtotal(rows.value.map(r => r.bookExpense)),
  )

  /** 差异合计 */
  const totalDifference = computed(() =>
    Math.round((totalExpectedExpense.value - totalBookExpense.value) * 100) / 100,
  )

  const h85TermOptions = computed(() => listLeaseTermsFromH85Raw(_getJson(H85_RECORDS_KEY)))

  /** H8-5 短期候选（≤12月；购买选择权排除需读原始记录） */
  const h85ShortTermCandidates = computed(() => {
    const raw = _getJson(H85_RECORDS_KEY)
    if (!Array.isArray(raw)) return [] as H85TermOption[]
    return raw
      .filter((r: any) => isShortTermLeaseCandidate({
        nonCancellableMonths: Number(r.nonCancellableMonths ?? r.nonCancellableTerm) || 0,
        renewalMonths: Number(r.renewalMonths ?? r.renewalOptionTerm) || 0,
        renewalReasonablyCertain: r.renewalReasonablyCertain ?? r.isRenewalReasonablyCertain ?? '',
        terminationOptionMonths: Number(r.terminationOptionMonths ?? r.terminationOptionTerm) || 0,
        lesseeReasonablyCertainNotTerminate: r.lesseeReasonablyCertainNotTerminate ?? '',
        bothCanTerminateNoPenalty: r.bothCanTerminateNoPenalty ?? '',
        determinedLeaseTermMonths: Number(r.determinedLeaseTermMonths ?? r.finalLeaseTerm) || 0,
        redeterminedLeaseTermMonths: Number(r.redeterminedLeaseTermMonths) || 0,
        purchaseReasonablyCertain: r.purchaseReasonablyCertain ?? '',
      } as H8LeaseTermRecord))
      .map((r: any) => ({
        recordId: String(r.recordId ?? ''),
        contractNo: String(r.contractNo ?? ''),
        months: resolveEffectiveLeaseTermMonths({
          nonCancellableMonths: Number(r.nonCancellableMonths ?? r.nonCancellableTerm) || 0,
          renewalMonths: Number(r.renewalMonths ?? r.renewalOptionTerm) || 0,
          renewalReasonablyCertain: r.renewalReasonablyCertain ?? r.isRenewalReasonablyCertain ?? '',
          terminationOptionMonths: Number(r.terminationOptionMonths ?? r.terminationOptionTerm) || 0,
          lesseeReasonablyCertainNotTerminate: r.lesseeReasonablyCertainNotTerminate ?? '',
          bothCanTerminateNoPenalty: r.bothCanTerminateNoPenalty ?? '',
          determinedLeaseTermMonths: Number(r.determinedLeaseTermMonths ?? r.finalLeaseTerm) || 0,
          redeterminedLeaseTermMonths: Number(r.redeterminedLeaseTermMonths) || 0,
        } as H8LeaseTermRecord),
        conclusion: String(r.conclusion ?? ''),
        commencementDate: String(r.commencementDate ?? ''),
      }))
      .filter((o: H85TermOption) => o.contractNo)
  })

  /** 本表租期与 H8-5 不一致（同合同号） */
  const h85LeaseTermMismatches = computed(() => {
    const byCn = new Map(h85TermOptions.value.map(o => [o.contractNo, o]))
    const out: Array<{ rowId: string; contractNo: string; h813Months: number; h85Months: number }> = []
    for (const row of rows.value) {
      const cn = row.contractNo.trim()
      if (!cn) continue
      const term = byCn.get(cn)
      if (!term || term.months <= 0) continue
      if (row.leaseTermMonths !== term.months) {
        out.push({
          rowId: row.rowId,
          contractNo: cn,
          h813Months: row.leaseTermMonths,
          h85Months: term.months,
        })
      }
    }
    return out
  })

  /**
   * H8-5 有短期候选但本表缺失的合同
   */
  const h85ShortTermMissing = computed(() => {
    const existing = new Set(rows.value.map(r => r.contractNo.trim()).filter(Boolean))
    return h85ShortTermCandidates.value.filter(c => !existing.has(c.contractNo))
  })

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(contractNo: string): void {
    if (!contractNo?.trim()) return
    rows.value.push(_normalizeRow({ contractNo: contractNo.trim() }))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const textFields = [
      'contractNo', 'assetName', 'lessor', 'assetCategory',
      'conclusion', 'remark', 'reconciled', 'expenseAccount',
    ]
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    const numVal = Number(value) || 0
    switch (field) {
      case 'leaseTermMonths': row.leaseTermMonths = numVal; break
      case 'annualRental':
        row.annualRental = numVal
        if (!row.monthlyRent && numVal > 0) {
          row.monthlyRent = Math.round((numVal / 12) * 100) / 100
        }
        break
      case 'newAssetValue': row.newAssetValue = numVal; break
      case 'monthlyRent': row.monthlyRent = numVal; break
      case 'accrualMonths': row.accrualMonths = numVal; break
      case 'bookExpense': row.bookExpense = numVal; break
      case 'expenseAmount':
        row.expenseAmount = numVal
        row.bookExpense = numVal
        break
      default: return
    }

    _recalcRow(row)
    _persist()
  }

  /**
   * 从 H8-5 同步：更新已有行租期 + 可选新增短期候选行，并重算资格判断。
   */
  function syncFromH85(opts?: { addMissing?: boolean; onlyShortTerm?: boolean }): H813SyncFromH85Result {
    const addMissing = opts?.addMissing !== false
    const onlyShortTerm = opts?.onlyShortTerm !== false
    const candidates = onlyShortTerm
      ? h85ShortTermCandidates.value
      : h85TermOptions.value.filter(o => o.months > 0)

    if (!candidates.length) {
      return {
        ok: false,
        reason: onlyShortTerm
          ? 'H8-5 无短期租赁候选（≤12月且无购买选择权）'
          : 'H8-5 尚无有效租赁期',
        updated: 0,
        added: 0,
        mismatchedBefore: h85LeaseTermMismatches.value.length,
        details: [],
      }
    }

    const mismatchedBefore = h85LeaseTermMismatches.value.length
    // 仅短期候选走 upsert（含新增）；全量模式只更新已有行租期，避免把长期合同误建进简化表
    if (onlyShortTerm) {
      const applied = upsertH85ShortTermIntoH813Rows(
        rows.value.map(r => ({ ...r })),
        candidates,
        { addMissing },
      )
      if (applied.updated + applied.added === 0) {
        return {
          ok: true,
          reason: '已与 H8-5 短期候选一致',
          updated: 0,
          added: 0,
          mismatchedBefore,
          details: [],
        }
      }
      rows.value = applied.rows.map(_normalizeRow)
      _persist()
      return {
        ok: true,
        updated: applied.updated,
        added: applied.added,
        mismatchedBefore,
        details: applied.details,
      }
    }

    // 全量：只更新已有行
    let updated = 0
    const details: H813SyncFromH85Result['details'] = []
    const byCn = new Map(candidates.map(c => [c.contractNo, c]))
    for (const row of rows.value) {
      const term = byCn.get(row.contractNo.trim())
      if (!term || term.months <= 0) continue
      if (row.leaseTermMonths === term.months) continue
      row.leaseTermMonths = term.months
      const tag = '已与H8-5同步租赁期'
      if (!row.remark.includes(tag)) {
        row.remark = row.remark ? `${row.remark}；${tag}` : tag
      }
      _recalcRow(row)
      updated++
      details.push({ contractNo: row.contractNo, months: term.months, action: 'updated' })
    }
    if (updated > 0) _persist()
    return {
      ok: updated > 0,
      reason: updated === 0 ? '已有行租期与 H8-5 一致' : undefined,
      updated,
      added: 0,
      mismatchedBefore,
      details,
    }
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value.map(r => ({
      rowId: r.rowId,
      contractNo: r.contractNo,
      assetName: r.assetName,
      lessor: r.lessor,
      assetCategory: r.assetCategory,
      leaseTermMonths: r.leaseTermMonths,
      termMonths: r.leaseTermMonths, // 兼容后端 validate_simplified_processing
      annualRental: r.annualRental,
      annualRent: r.annualRental,
      newAssetValue: r.newAssetValue,
      monthlyRent: r.monthlyRent,
      accrualMonths: r.accrualMonths,
      expectedExpense: r.expectedExpense,
      bookExpense: r.bookExpense,
      difference: r.difference,
      reconciled: r.reconciled,
      expenseAccount: r.expenseAccount,
      expenseAmount: r.expenseAmount || r.expectedExpense,
      conclusion: r.conclusion,
      remark: r.remark,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    simplifiedCount, mustRecognizeCount, totalAnnualRental, totalAllRental,
    totalExpectedExpense, totalBookExpense, totalDifference,
    h85TermOptions, h85ShortTermCandidates, h85LeaseTermMismatches, h85ShortTermMissing,
    addRow, deleteRow, updateCell, syncFromH85, save, load,
  }
}

export default useH8SimplifiedCheck
