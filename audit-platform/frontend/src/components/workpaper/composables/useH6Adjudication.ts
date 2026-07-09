/**
 * useH6Adjudication — H6-1 审定表 composable（过渡科目1606，59公式）
 *
 * 审定表结构（清理过程）：
 * 清理收入 | 清理支出(账面价值/清理费用/税费) | 清理净损益 | 期初余额 | 本期发生 | 期末余额
 *
 * 列：项目 | 期初余额 | 本期借方 | 本期贷方 | 期末余额 | 未审数 | AJE | RJE | 审定数
 *
 * 功能：
 * - calcAuditedAmount for each row（=未审+AJE+RJE）
 * - Transit account check: 期末审定数≠0→red warning
 * - H10 cross-check: 净损益 vs H10差额
 * - TB writeback on audited change（科目1606）
 * - Saves to allResponses with prefix "H6-1-"
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/
 * Task: 3.4
 * Requirements: 2.1-2.9
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcDisposalGainLoss,
  calcSubtotal,
  isTransitBalanceZero,
} from './useH6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H6-1 审定表行 */
export interface H6AdjudicationRow {
  rowId: string
  /** 项目名称 */
  name: string
  /** 行分类：income=清理收入 / expense=清理支出 / gainLoss=清理净损益 / balance=余额行 */
  category: 'income' | 'expense' | 'gainLoss' | 'balance'
  /** 支出子分类：bookValue=账面价值 / fee=清理费用 / tax=税费 */
  subCategory?: 'bookValue' | 'fee' | 'tax'
  /** 期初余额 */
  beginBalance: number
  /** 本期借方 */
  debitAmount: number
  /** 本期贷方 */
  creditAmount: number
  /** 期末余额（公式：=期初+借方-贷方，资产类借方1606） */
  endBalance: number
  /** 未审数 */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE重分类 */
  rje: number
  /** 审定数（公式：=未审+AJE+RJE） */
  audited: number
  /** 是否小计/合计行 */
  isSubtotal?: boolean
}

/** 过渡科目期末校验结果 */
export interface TransitCheckResult {
  /** 期末余额是否为零 */
  isZero: boolean
  /** 当前期末审定数 */
  balance: number
  /** 警告文本（非零时） */
  warning: string
}

/** H10交叉验证结果 */
export interface H10CrossCheck {
  /** H6清理净损益 */
  h6GainLoss: number
  /** H10资产处置损益（外部传入） */
  h10Amount: number
  /** 差额 */
  diff: number
  /** 是否匹配 */
  isMatch: boolean
  /** 警告文本（不匹配时） */
  warning: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H6-1-rows'
const NOTE_KEY = 'H6-1-audit-note'
const CONCLUSION_KEY = 'H6-1-audit-conclusion'
const GAIN_LOSS_KEY = 'H6-1-disposal-gain-loss'
const END_BALANCE_KEY = 'H6-1-end-balance-audited'
const AJE_TOTAL_KEY = 'H6-1-aje-total'
const RJE_TOTAL_KEY = 'H6-1-rje-total'

// ─── Default rows ────────────────────────────────────────────────────────────

const DEFAULT_ROWS: Partial<H6AdjudicationRow>[] = [
  { name: '清理收入', category: 'income' },
  { name: '清理支出—账面价值', category: 'expense', subCategory: 'bookValue' },
  { name: '清理支出—清理费用', category: 'expense', subCategory: 'fee' },
  { name: '清理支出—税费', category: 'expense', subCategory: 'tax' },
  { name: '清理净损益', category: 'gainLoss', isSubtotal: true },
  { name: '期初余额', category: 'balance' },
  { name: '本期发生', category: 'balance' },
  { name: '期末余额', category: 'balance' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH6Adjudication(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  tbData?: Ref<{ unadjusted1606: number; audited1606: number }>
  h10Amount?: Ref<number>
  onSave?: (itemId: string, value: any) => void
  onWritebackTB?: (auditedAmount: number) => Promise<void>
}) {
  const { allResponses, onSave, onWritebackTB, tbData, h10Amount } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H6AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  /** 规范化行（从 JSON 加载后重算公式列） */
  function _normalizeRow(raw: any): H6AdjudicationRow {
    const begin = Number(raw.beginBalance) || 0
    const debit = Number(raw.debitAmount) || 0
    const credit = Number(raw.creditAmount) || 0
    const unadj = Number(raw.unadjusted) || 0
    const aje = Number(raw.aje) || 0
    const rje = Number(raw.rje) || 0

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name: raw.name ?? '',
      category: raw.category ?? 'balance',
      subCategory: raw.subCategory,
      beginBalance: begin,
      debitAmount: debit,
      creditAmount: credit,
      endBalance: calcAssetEndBalance(begin, debit, credit),
      unadjusted: unadj,
      aje,
      rje,
      audited: calcAuditedAmount(unadj, aje, rje),
      isSubtotal: raw.isSubtotal ?? false,
    }
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      // 使用默认行结构
      rows.value = DEFAULT_ROWS.map(r => _normalizeRow(r))
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed: 分类行 ──────────────────────────────────────────────────────

  const incomeRows = computed(() => rows.value.filter(r => r.category === 'income'))
  const expenseRows = computed(() => rows.value.filter(r => r.category === 'expense'))
  const balanceRows = computed(() => rows.value.filter(r => r.category === 'balance'))

  // ─── Computed: 清理支出小计 ────────────────────────────────────────────────

  const expenseSubtotal = computed(() => ({
    unadjusted: calcSubtotal(expenseRows.value.map(r => r.unadjusted)),
    aje: calcSubtotal(expenseRows.value.map(r => r.aje)),
    rje: calcSubtotal(expenseRows.value.map(r => r.rje)),
    audited: calcSubtotal(expenseRows.value.map(r => r.audited)),
    beginBalance: calcSubtotal(expenseRows.value.map(r => r.beginBalance)),
    debitAmount: calcSubtotal(expenseRows.value.map(r => r.debitAmount)),
    creditAmount: calcSubtotal(expenseRows.value.map(r => r.creditAmount)),
    endBalance: calcSubtotal(expenseRows.value.map(r => r.endBalance)),
  }))

  // ─── Computed: 清理净损益 = 清理收入 - 清理支出 ────────────────────────────

  const disposalGainLoss: ComputedRef<number> = computed(() => {
    const incomeAudited = calcSubtotal(incomeRows.value.map(r => r.audited))
    const expenseAudited = expenseSubtotal.value.audited
    return incomeAudited - expenseAudited
  })

  // ─── Computed: 期末余额审定数（过渡科目核心指标） ──────────────────────────

  const endBalanceAudited: ComputedRef<number> = computed(() => {
    const endRow = rows.value.find(r => r.category === 'balance' && r.name.includes('期末'))
    return endRow?.audited ?? 0
  })

  // ─── Computed: 过渡科目校验（期末审定数≠0→红色警告） ────────────────────────

  const transitCheck: ComputedRef<TransitCheckResult> = computed(() => {
    const balance = endBalanceAudited.value
    const isZero = isTransitBalanceZero(balance)
    return {
      isZero,
      balance,
      warning: isZero
        ? ''
        : `⚠ 过渡科目期末余额应为0，当前余额：${balance}元，请检查是否有未完成清理项目`,
    }
  })

  // ─── Computed: H10交叉验证 ─────────────────────────────────────────────────

  const h10CrossCheck: ComputedRef<H10CrossCheck> = computed(() => {
    const h6GL = disposalGainLoss.value
    const h10Val = h10Amount?.value ?? 0
    const diff = h6GL - h10Val
    const isMatch = Math.abs(diff) < 0.01
    return {
      h6GainLoss: h6GL,
      h10Amount: h10Val,
      diff,
      isMatch,
      warning: isMatch ? '' : `净损益≠H10资产处置损益，差额：${diff > 0 ? '+' : ''}${diff}`,
    }
  })

  // ─── Computed: AJE/RJE总额（供H6-3双向同步） ──────────────────────────────

  const ajeTotalNet: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.filter(r => !r.isSubtotal).map(r => r.aje)),
  )

  const rjeTotalNet: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.filter(r => !r.isSubtotal).map(r => r.rje)),
  )

  // ─── Computed: TB取数 ──────────────────────────────────────────────────────

  const tbUnadjusted = computed(() => tbData?.value?.unadjusted1606 ?? 0)
  const tbAudited = computed(() => tbData?.value?.audited1606 ?? 0)
  const tbDiff = computed(() => endBalanceAudited.value - tbAudited.value)
  const isTbMatch = computed(() => Math.abs(tbDiff.value) < 0.01)

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row || row.isSubtotal) return

    const numVal = Number(value) || 0

    switch (field) {
      case 'name': row.name = String(value ?? ''); break
      case 'beginBalance': row.beginBalance = numVal; break
      case 'debitAmount': row.debitAmount = numVal; break
      case 'creditAmount': row.creditAmount = numVal; break
      case 'unadjusted': row.unadjusted = numVal; break
      case 'aje': row.aje = numVal; break
      case 'rje': row.rje = numVal; break
      default: return
    }

    // 重算公式列
    row.endBalance = calcAssetEndBalance(row.beginBalance, row.debitAmount, row.creditAmount)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)

    _persist()
  }

  function addRow(name: string, category: H6AdjudicationRow['category'] = 'expense'): void {
    if (!name?.trim()) return
    rows.value.push(_normalizeRow({ name: name.trim(), category }))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    const row = rows.value[idx]
    if (row.isSubtotal) return
    rows.value.splice(idx, 1)
    _persist()
  }

  /** 接收H6-3调整分录同步AJE/RJE金额到行 */
  function syncAjeRjeFromAdjustment(ajeNet: number, rjeNet: number): void {
    // 将净额按比例分配到收入/支出行，或直接写入期末余额行
    const endRow = rows.value.find(r => r.category === 'balance' && r.name.includes('期末'))
    if (endRow) {
      endRow.aje = ajeNet
      endRow.rje = rjeNet
      endRow.audited = calcAuditedAmount(endRow.unadjusted, endRow.aje, endRow.rje)
      _persist()
    }
  }

  /** 审定数回写TB + EventBus */
  async function publishAdjudicated(): Promise<void> {
    if (onWritebackTB) {
      await onWritebackTB(endBalanceAudited.value)
    }
  }

  function saveNote(note: string): void {
    auditNote.value = note
    onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    onSave?.(CONCLUSION_KEY, conclusion)
  }

  // ─── Save ──────────────────────────────────────────────────────────────────

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId,
      name: r.name,
      category: r.category,
      subCategory: r.subCategory,
      beginBalance: r.beginBalance,
      debitAmount: r.debitAmount,
      creditAmount: r.creditAmount,
      unadjusted: r.unadjusted,
      aje: r.aje,
      rje: r.rje,
      isSubtotal: r.isSubtotal,
    }))
    onSave(ROWS_KEY, toPersist)

    // 同步写入跨sheet汇总值
    onSave(GAIN_LOSS_KEY, disposalGainLoss.value)
    onSave(END_BALANCE_KEY, endBalanceAudited.value)
    onSave(AJE_TOTAL_KEY, ajeTotalNet.value)
    onSave(RJE_TOTAL_KEY, rjeTotalNet.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    auditNote,
    auditConclusion,
    // Computed — 分类行
    incomeRows,
    expenseRows,
    balanceRows,
    expenseSubtotal,
    // Computed — 核心指标
    disposalGainLoss,
    endBalanceAudited,
    // Computed — 过渡科目校验
    transitCheck,
    // Computed — H10交叉验证
    h10CrossCheck,
    // Computed — AJE/RJE
    ajeTotalNet,
    rjeTotalNet,
    // Computed — TB
    tbUnadjusted,
    tbAudited,
    tbDiff,
    isTbMatch,
    // Actions
    updateCell,
    addRow,
    deleteRow,
    syncAjeRjeFromAdjustment,
    save,
    load,
    publishAdjudicated,
    saveNote,
    saveConclusion,
  }
}

export default useH6Adjudication
