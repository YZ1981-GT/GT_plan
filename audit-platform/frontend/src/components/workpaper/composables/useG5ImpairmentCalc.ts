/**
 * useG5ImpairmentCalc — G5-10 长期应收款坏账准备测算表（ECL公式链 + Stage分组 + 2区段Tab）
 *
 * Spec: .kiro/specs/g5-long-term-receivable/ Task 11.2
 * Requirements: 13.1~13.12
 *
 * 职责：
 * - ECL公式链自动计算（③④⑥⑦⑧⑨ 引用 useG5FormulaEngine 纯函数）
 * - Stage分组逻辑 + GroupSubtotal 小计汇总
 * - 行CRUD（addRow/removeRow） + 数据响应式绑定
 * - Tab切换行同步（activeTab + activeRowIndex）
 *
 * 公式链：
 * ③ impairmentProvision = ① bookBalance × ② creditLossRate
 * ④ bookValue = ① - ③
 * ⑥ impairmentAdjustment = ⑤×②A + ①×(②A-②)
 * ⑦ adjBookBalance = ① + ⑤
 * ⑧ adjImpairment = ③ + ⑥
 * ⑨ adjBookValue = ⑦ - ⑧
 * 本年计提 = ⑧ - 上年 + 转回（或 max(0, ⑧-上年)）
 *
 * 与G4-10差异：字段名"投资项目"→"债务人"，引用G5FormulaEngine
 */
import { ref, computed, watch } from 'vue'
import {
  calcImpairmentProvision,
  calcImpairmentAdjustment,
  calcAdjustedBalance,
  calcAdjustedImpairment,
  calcAdjustedBookValue,
  parseNum,
} from '@/composables/useG5FormulaEngine'
import { ElMessageBox } from 'element-plus'

// ─── 行数据接口 ─────────────────────────────────────────────────────────────

export interface G5ImpairmentCalcRow {
  id: string
  seq: number
  debtor: string                   // G5用"债务人"
  stageGroup: 'Stage1' | 'Stage2' | 'Stage3'
  bookBalance: number              // ① 账面余额
  pvFutureCashFlow: number         // 现金流量现值（辅助参考）
  creditLossRate: number           // ② 信用损失率
  impairmentProvision: number      // ③ 坏账准备 = ①×②
  bookValue: number                // ④ 账面价值 = ①-③
  balanceAdjustment: number        // ⑤ 余额调整
  adjustedCreditLossRate: number   // ②A 调整后信用损失率
  impairmentAdjustment: number     // ⑥ 坏账调整 = ⑤×②A+①×(②A-②)
  adjBookBalance: number           // ⑦ 审定账面余额 = ①+⑤
  adjImpairment: number            // ⑧ 审定坏账准备 = ③+⑥
  adjBookValue: number             // ⑨ 审定账面价值 = ⑦-⑧
  priorImpairment: number          // 上年坏账准备
  currentProvision: number         // 本年计提 = max(0, ⑧-上年)
  currentReversal: number          // 本年转回 = max(0, 上年-⑧)
  differenceNote: string           // 差异说明
}

// ─── GroupSubtotal 小计接口 ──────────────────────────────────────────────────

export interface GroupSubtotal {
  bookBalance: number           // Σ①
  impairmentProvision: number   // Σ③
  bookValue: number             // Σ④
  balanceAdjustment: number     // Σ⑤
  impairmentAdjustment: number  // Σ⑥
  adjBookBalance: number        // Σ⑦
  adjImpairment: number         // Σ⑧
  adjBookValue: number          // Σ⑨
}

export interface StageGroup {
  rows: G5ImpairmentCalcRow[]
  subtotal: GroupSubtotal
}

export interface G5ImpairmentCalcGrouped {
  stage1: StageGroup
  stage2: StageGroup
  stage3: StageGroup
  grandTotal: GroupSubtotal
}

// ─── 小计计算辅助 ────────────────────────────────────────────────────────────

function calcSumCol(values: number[]): number {
  return values.reduce((s, v) => s + parseNum(v), 0)
}

function calcSubtotal(rows: G5ImpairmentCalcRow[]): GroupSubtotal {
  return {
    bookBalance: calcSumCol(rows.map(r => r.bookBalance)),
    impairmentProvision: calcSumCol(rows.map(r => r.impairmentProvision)),
    bookValue: calcSumCol(rows.map(r => r.bookValue)),
    balanceAdjustment: calcSumCol(rows.map(r => r.balanceAdjustment)),
    impairmentAdjustment: calcSumCol(rows.map(r => r.impairmentAdjustment)),
    adjBookBalance: calcSumCol(rows.map(r => r.adjBookBalance)),
    adjImpairment: calcSumCol(rows.map(r => r.adjImpairment)),
    adjBookValue: calcSumCol(rows.map(r => r.adjBookValue)),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG5ImpairmentCalc() {
  const rows = ref<G5ImpairmentCalcRow[]>([])
  const activeTab = ref<'tab1' | 'tab2'>('tab1')
  const activeRowIndex = ref(0)

  // ─── 公式链自动计算 ────────────────────────────────────────────────────────

  /**
   * recalcRow — 重算所有公式列 ③④⑥⑦⑧⑨ + currentProvision/currentReversal
   *
   * 公式链：
   * ③ impairmentProvision = ① bookBalance × ② creditLossRate
   * ④ bookValue = ① - ③
   * ⑥ impairmentAdjustment = ⑤×②A + ①×(②A-②)
   * ⑦ adjBookBalance = ① + ⑤
   * ⑧ adjImpairment = ③ + ⑥
   * ⑨ adjBookValue = ⑦ - ⑧
   * currentProvision = max(0, ⑧ - priorImpairment)
   * currentReversal = max(0, priorImpairment - ⑧)
   */
  function recalcRow(row: G5ImpairmentCalcRow): void {
    // ③ 坏账准备 = ① × ②
    row.impairmentProvision = Math.round(calcImpairmentProvision(row.bookBalance, row.creditLossRate) * 100) / 100

    // ④ 账面价值 = ① - ③
    row.bookValue = Math.round((parseNum(row.bookBalance) - parseNum(row.impairmentProvision)) * 100) / 100

    // ⑥ 坏账调整 = ⑤×②A + ①×(②A-②)
    row.impairmentAdjustment = Math.round(calcImpairmentAdjustment(
      row.balanceAdjustment,
      row.adjustedCreditLossRate,
      row.bookBalance,
      row.creditLossRate,
    ) * 100) / 100

    // ⑦ 审定账面余额 = ① + ⑤
    row.adjBookBalance = Math.round(calcAdjustedBalance(row.bookBalance, row.balanceAdjustment) * 100) / 100

    // ⑧ 审定坏账准备 = ③ + ⑥
    row.adjImpairment = Math.round(calcAdjustedImpairment(row.impairmentProvision, row.impairmentAdjustment) * 100) / 100

    // ⑨ 审定账面价值 = ⑦ - ⑧
    row.adjBookValue = Math.round(calcAdjustedBookValue(row.adjBookBalance, row.adjImpairment) * 100) / 100

    // 本年计提 = max(0, ⑧ - 上年坏账准备)
    const diff = parseNum(row.adjImpairment) - parseNum(row.priorImpairment)
    row.currentProvision = Math.round(Math.max(0, diff) * 100) / 100

    // 本年转回 = max(0, 上年坏账准备 - ⑧)
    row.currentReversal = Math.round(Math.max(0, -diff) * 100) / 100
  }

  // ─── Stage分组 + 小计汇总 ─────────────────────────────────────────────────

  const groupedRows = computed<G5ImpairmentCalcGrouped>(() => {
    const s1Rows = rows.value.filter(r => r.stageGroup === 'Stage1')
    const s2Rows = rows.value.filter(r => r.stageGroup === 'Stage2')
    const s3Rows = rows.value.filter(r => r.stageGroup === 'Stage3')

    return {
      stage1: { rows: s1Rows, subtotal: calcSubtotal(s1Rows) },
      stage2: { rows: s2Rows, subtotal: calcSubtotal(s2Rows) },
      stage3: { rows: s3Rows, subtotal: calcSubtotal(s3Rows) },
      grandTotal: calcSubtotal(rows.value),
    }
  })

  const grandTotal = computed<GroupSubtotal>(() => groupedRows.value.grandTotal)

  // ─── watch输入字段变化自动重算 ────────────────────────────────────────────

  watch(
    rows,
    (newRows) => {
      for (const row of newRows) {
        recalcRow(row)
      }
    },
    { deep: true },
  )

  // ─── 行CRUD ───────────────────────────────────────────────────────────────

  async function addRow(defaultStage: 'Stage1' | 'Stage2' | 'Stage3' = 'Stage1'): Promise<void> {
    const { value } = await ElMessageBox.prompt('请输入债务人名称', '新增行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValidator: (v) => (v?.trim() ? true : '债务人名称不能为空'),
    })
    if (!value?.trim()) return

    const newRow: G5ImpairmentCalcRow = {
      id: crypto.randomUUID(),
      seq: rows.value.length + 1,
      debtor: value.trim(),
      stageGroup: defaultStage,
      bookBalance: 0,
      pvFutureCashFlow: 0,
      creditLossRate: 0,
      impairmentProvision: 0,
      bookValue: 0,
      balanceAdjustment: 0,
      adjustedCreditLossRate: 0,
      impairmentAdjustment: 0,
      adjBookBalance: 0,
      adjImpairment: 0,
      adjBookValue: 0,
      priorImpairment: 0,
      currentProvision: 0,
      currentReversal: 0,
      differenceNote: '',
    }
    recalcRow(newRow)
    rows.value.push(newRow)
  }

  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  // ─── 数据加载 ─────────────────────────────────────────────────────────────

  function loadRows(data: G5ImpairmentCalcRow[]): void {
    rows.value = data.map((r, i) => {
      const row: G5ImpairmentCalcRow = {
        ...r,
        id: r.id || crypto.randomUUID(),
        seq: i + 1,
      }
      recalcRow(row)
      return row
    })
  }

  // ─── 导出序列化 ──────────────────────────────────────────────────────────

  function toJSON(): G5ImpairmentCalcRow[] {
    return rows.value.map(r => ({ ...r }))
  }

  return {
    // State
    rows,
    activeTab,
    activeRowIndex,
    // Computed
    groupedRows,
    grandTotal,
    // Methods
    recalcRow,
    addRow,
    removeRow,
    loadRows,
    toJSON,
  }
}

export default useG5ImpairmentCalc
