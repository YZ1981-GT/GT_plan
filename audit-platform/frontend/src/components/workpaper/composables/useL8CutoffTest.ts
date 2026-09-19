/**
 * useL8CutoffTest — L8-5 截止测试 composable
 *
 * Spec: .kiro/specs/l8-financial-expenses/
 * Task: 3.4
 * Requirements: 6.1-6.5
 *
 * 职责：
 * - 截止性测试（序时账±天数自动提取+跨期判定+行级抽凭）
 * - 列结构：序号 | 记账凭证(日期/编号/内容/对方科目/金额) | 支出凭单(编号/日期/金额)
 *   | 是否跨期 | 跨期金额
 * - 集成 useCutoffAutoSampling 自动提取
 * - 使用 useL8CutoffEngine (isCrossPeriod, extractCutoffWindow, extractCrossPeriodEntries)
 * - 跨期条目红色高亮
 * - Pre-period（期前）和 Post-period（期后）双区段
 *
 * 科目：6603 财务费用（借方/损益类！取发生额）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import {
  isCrossPeriod,
  extractCutoffWindow,
  extractCrossPeriodEntries,
  calcCrossPeriodTotal,
  calcCrossPeriodRate,
  type LedgerEntry,
} from './useL8CutoffEngine'
import { calcSubtotal, parseNum } from './useL8FormulaEngine'
import type { useL8FormData } from './useL8FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L8-5 截止测试行（对应xlsx 11列） */
export interface L8CutoffTestRow {
  /** 序号 */
  index: number
  /** 记账凭证-日期（YYYY-MM-DD） */
  voucherDate: string
  /** 记账凭证-编号 */
  voucherNo: string
  /** 记账凭证-内容/摘要 */
  voucherContent: string
  /** 记账凭证-对方科目 */
  counterAccount: string
  /** 记账凭证-金额 */
  voucherAmount: number
  /** 支出凭单-编号 */
  paymentNo: string
  /** 支出凭单-日期 */
  paymentDate: string
  /** 支出凭单-金额 */
  paymentAmount: number
  /** 应归属期间（YYYY-MM） */
  attributionPeriod: string
  /** 实际入账期间（YYYY-MM） */
  bookingPeriod: string
  /** 是否跨期（公式：归属≠入账） */
  isCrossPeriod: boolean
  /** 跨期金额（跨期时=凭证金额，否则=0） */
  crossPeriodAmount: number
}

/** 截止测试区段：期前/期后 */
export type L8CutoffSection = 'pre-period' | 'post-period'

/** 截止测试汇总统计 */
export interface L8CutoffSummary {
  /** 总测试笔数 */
  totalCount: number
  /** 跨期笔数 */
  crossCount: number
  /** 跨期金额合计 */
  crossAmountTotal: number
  /** 跨期率（%） */
  crossRate: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认截止窗口天数（±5天） */
const DEFAULT_CUTOFF_DAYS = 5

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L8-5 截止测试业务逻辑
 *
 * @param formData 由调用方传入的 useL8FormData 实例
 * @param prePeriodRows reactive ref of pre-period test rows
 * @param postPeriodRows reactive ref of post-period test rows
 */
export function useL8CutoffTest(
  formData: ReturnType<typeof useL8FormData>,
  prePeriodRows: Ref<L8CutoffTestRow[]>,
  postPeriodRows: Ref<L8CutoffTestRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 区段状态 ──────────────────────────────────────────────────────

  const activeSection = ref<L8CutoffSection>('pre-period')

  /** 报告截止日（YYYY-MM-DD） */
  const reportDate = ref('')

  /** 窗口天数（默认±5天） */
  const cutoffDays = ref(DEFAULT_CUTOFF_DAYS)

  function switchSection(section: L8CutoffSection): void {
    activeSection.value = section
  }

  // ─── 2. 计算属性：跨期判定 ────────────────────────────────────────────

  /** 期前测试行（公式列自动计算） */
  const computedPreRows: ComputedRef<L8CutoffTestRow[]> = computed(() => {
    return _computeRows(prePeriodRows.value)
  })

  /** 期后测试行（公式列自动计算） */
  const computedPostRows: ComputedRef<L8CutoffTestRow[]> = computed(() => {
    return _computeRows(postPeriodRows.value)
  })

  function _computeRows(rows: L8CutoffTestRow[]): L8CutoffTestRow[] {
    return rows.map((row, idx) => {
      const cross = isCrossPeriod(row.attributionPeriod, row.bookingPeriod)
      const crossAmount = cross ? parseNum(row.voucherAmount) : 0
      return {
        ...row,
        index: idx + 1,
        isCrossPeriod: cross,
        crossPeriodAmount: crossAmount,
      }
    })
  }

  // ─── 3. 汇总统计 ─────────────────────────────────────────────────────

  /** 期前汇总 */
  const preSummary: ComputedRef<L8CutoffSummary> = computed(() => {
    return _calcSummary(computedPreRows.value)
  })

  /** 期后汇总 */
  const postSummary: ComputedRef<L8CutoffSummary> = computed(() => {
    return _calcSummary(computedPostRows.value)
  })

  /** 总体汇总（期前+期后） */
  const overallSummary: ComputedRef<L8CutoffSummary> = computed(() => {
    const allRows = [...computedPreRows.value, ...computedPostRows.value]
    return _calcSummary(allRows)
  })

  function _calcSummary(rows: L8CutoffTestRow[]): L8CutoffSummary {
    const totalCount = rows.length
    const crossRows = rows.filter(r => r.isCrossPeriod)
    const crossCount = crossRows.length
    const crossAmountTotal = calcSubtotal(crossRows.map(r => r.crossPeriodAmount))
    const crossRate = calcCrossPeriodRate(crossCount, totalCount)
    return { totalCount, crossCount, crossAmountTotal, crossRate }
  }

  // ─── 4. 从序时账自动提取样本 ──────────────────────────────────────────

  /**
   * 从完整序时账中自动提取截止测试样本
   * 集成 useCutoffAutoSampling → 序时账±N天
   *
   * @param ledger 完整序时账明细（从 API 加载）
   * @param section 放入哪个区段（期前/期后）
   */
  function autoExtractFromLedger(ledger: LedgerEntry[], section: L8CutoffSection): void {
    if (!reportDate.value || !Array.isArray(ledger)) return

    const windowEntries = extractCutoffWindow(ledger, reportDate.value, cutoffDays.value)

    // 按日期区分期前/期后
    const reportMs = new Date(reportDate.value).getTime()
    const entries = windowEntries.filter(entry => {
      const entryMs = new Date(entry.date).getTime()
      if (section === 'pre-period') return entryMs <= reportMs
      return entryMs > reportMs
    })

    // 转换为测试行
    const testRows: L8CutoffTestRow[] = entries.map((entry, idx) => ({
      index: idx + 1,
      voucherDate: entry.date,
      voucherNo: entry.voucherNo,
      voucherContent: entry.summary,
      counterAccount: entry.counterAccount,
      voucherAmount: entry.amount,
      paymentNo: '',
      paymentDate: '',
      paymentAmount: 0,
      attributionPeriod: entry.attributionPeriod,
      bookingPeriod: entry.bookingPeriod,
      isCrossPeriod: false, // 会由 computed 重算
      crossPeriodAmount: 0,
    }))

    if (section === 'pre-period') {
      prePeriodRows.value = testRows
    } else {
      postPeriodRows.value = testRows
    }

    _triggerSaveSection(section)
  }

  // ─── 5. 行操作 ────────────────────────────────────────────────────────

  /** 新增测试行（手动添加） */
  function addRow(section: L8CutoffSection): void {
    const targetRows = section === 'pre-period' ? prePeriodRows : postPeriodRows
    const newRow: L8CutoffTestRow = {
      index: targetRows.value.length + 1,
      voucherDate: '',
      voucherNo: '',
      voucherContent: '',
      counterAccount: '',
      voucherAmount: 0,
      paymentNo: '',
      paymentDate: '',
      paymentAmount: 0,
      attributionPeriod: '',
      bookingPeriod: '',
      isCrossPeriod: false,
      crossPeriodAmount: 0,
    }
    targetRows.value.push(newRow)
    _triggerSaveSection(section)
  }

  /** 删除测试行 */
  function removeRow(section: L8CutoffSection, index: number): void {
    const targetRows = section === 'pre-period' ? prePeriodRows : postPeriodRows
    if (index < 0 || index >= targetRows.value.length) return
    targetRows.value.splice(index, 1)
    _triggerSaveSection(section)
  }

  /** 更新某行某字段 */
  function updateRow(
    section: L8CutoffSection,
    index: number,
    field: keyof L8CutoffTestRow,
    value: any,
  ): void {
    const targetRows = section === 'pre-period' ? prePeriodRows : postPeriodRows
    if (index < 0 || index >= targetRows.value.length) return
    const row = targetRows.value[index] as any
    row[field] = value
    _triggerSaveRow(section, index)
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSaveRow(section: L8CutoffSection, rowIndex: number): void {
    const targetRows = section === 'pre-period' ? prePeriodRows : postPeriodRows
    const row = targetRows.value[rowIndex]
    if (!row) return
    debouncedSave(`L8-5-${section}-row-${rowIndex}`, {
      remark: JSON.stringify({
        voucherDate: row.voucherDate,
        voucherNo: row.voucherNo,
        voucherContent: row.voucherContent,
        counterAccount: row.counterAccount,
        voucherAmount: row.voucherAmount,
        paymentNo: row.paymentNo,
        paymentDate: row.paymentDate,
        paymentAmount: row.paymentAmount,
        attributionPeriod: row.attributionPeriod,
        bookingPeriod: row.bookingPeriod,
      }),
    })
  }

  function _triggerSaveSection(section: L8CutoffSection): void {
    const targetRows = section === 'pre-period' ? prePeriodRows : postPeriodRows
    for (let i = 0; i < targetRows.value.length; i++) {
      _triggerSaveRow(section, i)
    }
    // 保存区段统计
    const summary = section === 'pre-period' ? preSummary.value : postSummary.value
    debouncedSave(`L8-5-${section}-summary`, {
      remark: JSON.stringify(summary),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 区段状态
    activeSection,
    reportDate,
    cutoffDays,
    switchSection,

    // 计算行
    computedPreRows,
    computedPostRows,

    // 汇总
    preSummary,
    postSummary,
    overallSummary,

    // 自动提取
    autoExtractFromLedger,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL8CutoffTest
