/**
 * useN2ExportRefund — N2-7 生产企业出口货物免抵退税申报汇总表 (22栏公式引擎)
 *
 * 对齐源模板《免抵退税申报汇总表》：22 个栏次 (line items)，其中 12 行为公式行
 * (auto)，10 行为录入行。不再使用旧的"12个月"结构。
 *
 * 参数区 (params) 驱动公式：
 *   - taxRateParam       征税率 (出口货物增值税税率 13%/9%/6%)
 *   - refundRateParam    退税率 (出口退税率，≤ 征税率)
 *   - exemptMaterialCost 免税购进原材料成本 (保税料件，公式中的"免税原材料")
 *
 * 12 个公式栏 (AUTO) 及其公式：
 *   栏2  = 栏3 + 栏4
 *   栏6  = max(0, 栏1 × (征税率 − 退税率) − 栏5)   [免抵退税出口货物不予免征和抵扣税额]
 *   栏8  = max(0, 栏6)                             [进项转出净额]
 *   栏9  = 栏5 + 栏10                              [不予免征抵扣抵减额合计]
 *   栏10 = 免税原材料 × (征税率 − 退税率)           [不予免征抵扣抵减额]
 *   栏12 = 栏10 + 栏15                             [免抵退税额抵减额合计]
 *   栏13 = 栏2 × 退税率                            [免抵退税额]
 *   栏15 = 免税原材料 × 退税率                      [免抵退税额抵减额]
 *   栏16 = max(0, 栏13 − 栏15)                     [当期免抵退税额]
 *   栏20 = 栏18 − 栏19                             [可退留抵税额]
 *   栏21 = min(栏16, 栏20)                         [当期应退税额]
 *   栏22 = 栏16 − 栏21                             [当期免抵税额]
 *
 * 核心结论：栏21 当期应退税额 (→ N2-7-total) / 栏22 当期免抵税额 /
 *          栏6 不予免征抵扣税额 (→ N2-6 进项转出)。
 *
 * 联动：栏6 (不予免征抵扣) → N2-6 进项转出，EventBus 'export-refund:non-deductible-updated'。
 *
 * 持久化：
 *   - N2-7-ledger      JSON { params, rows }
 *   - N2-7-total       栏21 当期应退税额 (供 N2TabIndex 进度检测)
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useN2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 免抵退税申报汇总表参数区 */
export interface RefundParams {
  /** 征税率 (出口货物增值税税率) */
  taxRateParam: number
  /** 退税率 (出口退税率) */
  refundRateParam: number
  /** 免税购进原材料成本 (保税料件，公式中的"免税原材料") */
  exemptMaterialCost: number
}

/** 免抵退税申报汇总表单行 (栏次) */
export interface RefundLedgerRow {
  /** 栏次 1-22 */
  line: number
  /** 栏次名称 */
  label: string
  /** 是否公式行 (auto=true 不可编辑) */
  auto: boolean
  /** 金额 */
  amount: number
  /** 公式说明 (auto行展示来源) */
  formula?: string
  /** 备注/文号 */
  remark?: string
}

/** 完整台账状态 (持久化格式) */
export interface RefundLedgerState {
  params: RefundParams
  rows: RefundLedgerRow[]
}

// ─── Backward-compat type aliases (旧 12 月结构已移除) ─────────────────────────

/** @deprecated 旧逐月结构已被 22 栏台账取代，保留别名避免下游类型引用报错 */
export type MonthlyExportRow = RefundLedgerRow
/** @deprecated 旧年度汇总结构已移除 */
export type AnnualExportSummary = RefundLedgerState
/** @deprecated Use RefundLedgerRow */
export type N2ExportRefundRow = RefundLedgerRow
/** @deprecated Use RefundLedgerState */
export type N2ExportRefundSummary = RefundLedgerState

// ─── Constants ───────────────────────────────────────────────────────────────

/** 差异阈值 (0.01元内视为一致) */
const DIFF_THRESHOLD = 0.01

/** 台账持久化 item_id */
const LEDGER_ITEM_ID = 'N2-7-ledger'
/** 应退税额合计持久化 item_id (供进度检测) */
const TOTAL_ITEM_ID = 'N2-7-total'
/** 旧持久化 item_id (向后兼容读取) */
const LEGACY_LEDGER_ITEM_IDS = ['N2-7-export-refund'] as const

/** 公式行栏次 (12 行) */
const AUTO_LINES = new Set([2, 6, 8, 9, 10, 12, 13, 15, 16, 20, 21, 22])

/** 核心结论栏次 */
export const LINE_NON_DEDUCTIBLE = 6
export const LINE_REFUND_DUE = 21
export const LINE_EXEMPT_CREDIT = 22

/**
 * 22 栏模板 — 免抵退税申报汇总表。
 * auto:true 为公式行 (12 行)，其余为录入行 (10 行)。
 */
export const REFUND_TEMPLATE: ReadonlyArray<{ line: number; label: string; auto?: boolean; formula?: string }> = [
  { line: 1, label: '当期出口货物销售额（免抵退税办法，FOB）' },
  { line: 2, label: '免抵退出口货物销售额（=③+④）', auto: true, formula: '③ + ④' },
  { line: 3, label: '单证齐全出口销售额' },
  { line: 4, label: '单证不齐出口销售额' },
  { line: 5, label: '免抵退税不予免征和抵扣税额抵减额（明细录入）' },
  { line: 6, label: '免抵退税出口货物不予免征和抵扣税额（=①×(征税率−退税率)−⑤）', auto: true, formula: 'max(0, ① × (征税率 − 退税率) − ⑤)' },
  { line: 7, label: '结转下期继续抵扣的进项税额' },
  { line: 8, label: '当期不予免征和抵扣税额（进项转出净额，=max(0,⑥)）', auto: true, formula: 'max(0, ⑥)' },
  { line: 9, label: '免抵退税不予免征和抵扣税额抵减额合计（=⑤+⑩）', auto: true, formula: '⑤ + ⑩' },
  { line: 10, label: '免抵退税不予免征和抵扣税额抵减额（=免税原材料×(征税率−退税率)）', auto: true, formula: '免税原材料 × (征税率 − 退税率)' },
  { line: 11, label: '上期结转免抵退税额抵减额' },
  { line: 12, label: '免抵退税额抵减额合计（=⑩+⑮）', auto: true, formula: '⑩ + ⑮' },
  { line: 13, label: '免抵退税额（=②×退税率）', auto: true, formula: '② × 退税率' },
  { line: 14, label: '免抵退税额抵减额（明细录入）' },
  { line: 15, label: '免抵退税额抵减额（=免税原材料×退税率）', auto: true, formula: '免税原材料 × 退税率' },
  { line: 16, label: '当期免抵退税额（=max(0,⑬−⑮)）', auto: true, formula: 'max(0, ⑬ − ⑮)' },
  { line: 17, label: '单证收齐补报销售额' },
  { line: 18, label: '当期期末留抵税额（增值税纳税申报表）' },
  { line: 19, label: '上期留抵调整额' },
  { line: 20, label: '可退留抵税额（=⑱−⑲）', auto: true, formula: '⑱ − ⑲' },
  { line: 21, label: '当期应退税额（=min(⑯,⑳)）', auto: true, formula: 'min(⑯, ⑳)' },
  { line: 22, label: '当期免抵税额（=⑯−㉑）', auto: true, formula: '⑯ − ㉑' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function round2(v: number): number {
  return parseFloat((Number.isFinite(v) ? v : 0).toFixed(2))
}

function buildInitialRows(): RefundLedgerRow[] {
  return REFUND_TEMPLATE.map(t => ({
    line: t.line,
    label: t.label,
    auto: !!t.auto,
    formula: t.formula,
    amount: 0,
    remark: '',
  }))
}

function defaultParams(): RefundParams {
  return { taxRateParam: 0.13, refundRateParam: 0.13, exemptMaterialCost: 0 }
}

// ─── Pure recalc engine (exported for testability) ───────────────────────────

/**
 * recalcLedger — 纯函数：根据参数区 + 录入行重算全部 12 个公式行。
 * 不修改入参，返回新数组。计算顺序确保依赖先行。
 */
export function recalcLedger(params: RefundParams, rows: RefundLedgerRow[]): RefundLedgerRow[] {
  const out = rows.map(r => ({ ...r }))
  const val = (line: number): number => out.find(x => x.line === line)?.amount ?? 0
  const setLine = (line: number, v: number): void => {
    const r = out.find(x => x.line === line)
    if (r) r.amount = round2(v)
  }

  const taxRate = parseNum(params.taxRateParam)
  const refundRate = parseNum(params.refundRateParam)
  const rateDiff = taxRate - refundRate
  const material = parseNum(params.exemptMaterialCost)

  // 依赖顺序计算
  setLine(2, val(3) + val(4))
  setLine(6, Math.max(0, val(1) * rateDiff - val(5)))
  setLine(8, Math.max(0, val(6)))
  setLine(10, material * rateDiff)
  setLine(9, val(5) + val(10))
  setLine(13, val(2) * refundRate)
  setLine(15, material * refundRate)
  setLine(12, val(10) + val(15))
  setLine(16, Math.max(0, val(13) - val(15)))
  setLine(20, val(18) - val(19))
  setLine(21, Math.min(val(16), val(20)))
  setLine(22, val(16) - val(21))

  return out
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN2ExportRefundOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (itemId: string, value: { conclusion?: string; remark?: string }) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN2ExportRefund(options: UseN2ExportRefundOptions) {
  const { allResponses, saveField } = options

  // ─── State ───────────────────────────────────────────────────────────────
  const params = ref<RefundParams>(defaultParams())
  const rows = ref<RefundLedgerRow[]>(recalcLedger(defaultParams(), buildInitialRows()))

  // ─── 1. Ledger snapshot ────────────────────────────────────────────────────
  /** 台账行 (recalc 后的完整 22 栏) */
  const ledgerRows: ComputedRef<RefundLedgerRow[]> = computed(() => rows.value)

  /** 台账完整状态 (持久化格式) */
  const ledger: ComputedRef<RefundLedgerState> = computed(() => ({
    params: params.value,
    rows: rows.value,
  }))

  function getLineAmount(line: number): number {
    return rows.value.find(r => r.line === line)?.amount ?? 0
  }

  // ─── 2. Core outputs (核心结论区) ──────────────────────────────────────────
  /** 栏21 当期应退税额 (→ N2-7-total) */
  const totalRefundDue: ComputedRef<number> = computed(() => getLineAmount(LINE_REFUND_DUE))
  /** 栏22 当期免抵税额 */
  const currentExemptCredit: ComputedRef<number> = computed(() => getLineAmount(LINE_EXEMPT_CREDIT))
  /** 栏6 不予免征和抵扣税额 (联动 N2-6 进项转出) */
  const totalNonDeductible: ComputedRef<number> = computed(() => getLineAmount(LINE_NON_DEDUCTIBLE))

  // 兼容旧命名
  const currentRefund = totalRefundDue
  const nonDeductible = totalNonDeductible

  // ─── 3. Recompute + persist ────────────────────────────────────────────────
  function recompute(): void {
    rows.value = recalcLedger(params.value, rows.value)
  }

  async function persist(): Promise<void> {
    await saveField(LEDGER_ITEM_ID, {
      conclusion: JSON.stringify({ params: params.value, rows: rows.value }),
    })
    // 写 N2-7-total (应退税额)，供 N2TabIndex 进度检测
    await saveField(TOTAL_ITEM_ID, {
      conclusion: JSON.stringify(totalRefundDue.value),
    })
  }

  // ─── 4. Load / migrate ─────────────────────────────────────────────────────
  /**
   * 从持久化恢复台账。优先级：N2-7-ledger → 旧 item_id (同格式)。
   */
  function loadLedger(): void {
    const primary = readLedgerState(LEDGER_ITEM_ID)
    if (primary) {
      applyState(primary)
      return
    }
    for (const legacyId of LEGACY_LEDGER_ITEM_IDS) {
      const legacy = readLedgerState(legacyId)
      if (legacy) {
        applyState(legacy)
        return
      }
    }
  }

  function readLedgerState(itemId: string): RefundLedgerState | null {
    const resp = allResponses.value.get(itemId)
    if (!resp?.conclusion) return null
    try {
      const parsed = JSON.parse(resp.conclusion)
      if (parsed && typeof parsed === 'object' && Array.isArray(parsed.rows)) {
        return parsed as RefundLedgerState
      }
    } catch { /* ignore malformed */ }
    return null
  }

  function applyState(state: RefundLedgerState): void {
    const p: RefundParams = {
      taxRateParam: parseNum(state.params?.taxRateParam) || defaultParams().taxRateParam,
      refundRateParam: parseNum(state.params?.refundRateParam) || defaultParams().refundRateParam,
      exemptMaterialCost: parseNum(state.params?.exemptMaterialCost),
    }
    // 以模板为骨架，合并保存的金额/备注 (确保 22 栏完整)
    const savedByLine = new Map<number, RefundLedgerRow>()
    for (const r of state.rows || []) {
      if (r && typeof r.line === 'number') savedByLine.set(r.line, r)
    }
    const merged: RefundLedgerRow[] = REFUND_TEMPLATE.map(t => {
      const saved = savedByLine.get(t.line)
      return {
        line: t.line,
        label: t.label,
        auto: !!t.auto,
        formula: t.formula,
        amount: parseNum(saved?.amount),
        remark: (saved?.remark as string) || '',
      }
    })
    params.value = p
    rows.value = recalcLedger(p, merged)
  }

  // ─── 5. Actions ────────────────────────────────────────────────────────────
  /** 设置参数并重算+保存 */
  async function setParam(key: keyof RefundParams, value: number): Promise<void> {
    params.value = { ...params.value, [key]: parseNum(value) }
    recompute()
    await persist()
  }

  /** 设置录入行金额 (公式行忽略) 并重算+保存 */
  async function setRowAmount(line: number, value: number): Promise<void> {
    if (AUTO_LINES.has(line)) return
    const target = rows.value.find(r => r.line === line)
    if (!target) return
    target.amount = parseNum(value)
    recompute()
    await persist()
  }

  /** 设置行备注 并保存 */
  async function setRowRemark(line: number, remark: string): Promise<void> {
    const target = rows.value.find(r => r.line === line)
    if (!target) return
    target.remark = remark || ''
    await persist()
  }

  /** 验证申报表一致性：比对手工录入的申报值与本表计算值 */
  function verifyDeclaration(
    field: 'refundDue' | 'exemptCredit' | 'nonDeductible',
    declaredValue: number,
  ): { computed: number; declared: number; diff: number; consistent: boolean } {
    const computedVal =
      field === 'refundDue' ? totalRefundDue.value
      : field === 'exemptCredit' ? currentExemptCredit.value
      : totalNonDeductible.value
    const declared = parseNum(declaredValue)
    const diff = round2(computedVal - declared)
    return { computed: computedVal, declared, diff, consistent: Math.abs(diff) <= DIFF_THRESHOLD }
  }

  /** 同步栏6 (不予免征和抵扣税额) 至 N2-6 进项转出 */
  async function syncToN26(): Promise<void> {
    const total = totalNonDeductible.value
    await saveField('N2-6-non-deductible-from-export', { conclusion: JSON.stringify(total) })
    eventBus.emit('export-refund:non-deductible-updated', {
      total,
      wpCode: 'N2',
      timestamp: Date.now(),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────────
  return {
    // State
    params,
    rows,
    ledgerRows,
    ledger,
    // Core outputs
    totalRefundDue,
    currentExemptCredit,
    totalNonDeductible,
    // 兼容别名
    currentRefund,
    nonDeductible,
    // Load / persist
    loadLedger,
    recompute,
    persist,
    // Actions
    setParam,
    setRowAmount,
    setRowRemark,
    verifyDeclaration,
    syncToN26,
  }
}

export default useN2ExportRefund
