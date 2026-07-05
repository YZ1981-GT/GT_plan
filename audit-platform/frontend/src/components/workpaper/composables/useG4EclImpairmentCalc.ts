/**
 * useG4EclImpairmentCalc — G4-10 减值准备测算表（ECL公式链 + Stage分组 + 2区段Tab）
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/
 * Task: 6.2
 *
 * 职责：
 * - 公式链自动计算（③④⑥⑦⑧⑨ 调用 useG4EclFormulaEngine 纯函数）
 * - Stage分组逻辑 + GroupSubtotal 小计汇总
 * - 行CRUD（addRow/removeRow） + 数据响应式绑定
 * - Tab切换行同步（activeTab + activeRowIndex）
 *
 * Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9
 */
import { ref, computed, watch } from 'vue'
import {
  calcImpairmentProvision,
  calcBookValue,
  calcImpairmentAdjustment,
  calcAdjustedBalance,
  calcAdjustedImpairment,
  calcAdjustedBookValue,
  calcSumColumn,
  parseNum,
} from '@/composables/useG4EclFormulaEngine'
import { ElMessageBox } from 'element-plus'
import type { ImpairmentCalcRow } from './useG4EclFormData'

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
  rows: ImpairmentCalcRow[]
  subtotal: GroupSubtotal
}

export interface ImpairmentCalcGrouped {
  stage1: StageGroup
  stage2: StageGroup
  stage3: StageGroup
  grandTotal: GroupSubtotal
}

// ─── 小计计算辅助 ────────────────────────────────────────────────────────────

function calcSubtotal(rows: ImpairmentCalcRow[]): GroupSubtotal {
  return {
    bookBalance: calcSumColumn(rows.map(r => r.bookBalance)),
    impairmentProvision: calcSumColumn(rows.map(r => r.impairmentProvision)),
    bookValue: calcSumColumn(rows.map(r => r.bookValue)),
    balanceAdjustment: calcSumColumn(rows.map(r => r.balanceAdjustment)),
    impairmentAdjustment: calcSumColumn(rows.map(r => r.impairmentAdjustment)),
    adjBookBalance: calcSumColumn(rows.map(r => r.adjBookBalance)),
    adjImpairment: calcSumColumn(rows.map(r => r.adjImpairment)),
    adjBookValue: calcSumColumn(rows.map(r => r.adjBookValue)),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG4EclImpairmentCalc() {
  const rows = ref<ImpairmentCalcRow[]>([])
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
  function recalcRow(row: ImpairmentCalcRow): void {
    // ③ 减值准备 = ① × ②
    row.impairmentProvision = calcImpairmentProvision(row.bookBalance, row.creditLossRate)

    // ④ 账面价值 = ① - ③
    row.bookValue = calcBookValue(row.bookBalance, row.impairmentProvision)

    // ⑥ 减值准备调整 = ⑤×②A + ①×(②A-②)（可负）
    row.impairmentAdjustment = calcImpairmentAdjustment(
      row.balanceAdjustment,
      row.adjustedCreditLossRate,
      row.bookBalance,
      row.creditLossRate,
    )

    // ⑦ 审定账面余额 = ① + ⑤
    row.adjBookBalance = calcAdjustedBalance(row.bookBalance, row.balanceAdjustment)

    // ⑧ 审定减值准备 = ③ + ⑥
    row.adjImpairment = calcAdjustedImpairment(row.impairmentProvision, row.impairmentAdjustment)

    // ⑨ 审定账面价值 = ⑦ - ⑧
    row.adjBookValue = calcAdjustedBookValue(row.adjBookBalance, row.adjImpairment)

    // 本年计提 = max(0, 审定减值⑧ - 上年减值)
    const diff = parseNum(row.adjImpairment) - parseNum(row.priorImpairment)
    row.currentProvision = Math.round(Math.max(0, diff) * 100) / 100

    // 本年转回 = max(0, 上年减值 - 审定减值⑧)
    row.currentReversal = Math.round(Math.max(0, -diff) * 100) / 100
  }

  // ─── Stage分组 + 小计汇总 ─────────────────────────────────────────────────

  const groupedRows = computed<ImpairmentCalcGrouped>(() => {
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
    const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValidator: (v) => (v?.trim() ? true : '投资项目名称不能为空'),
    })
    if (!value?.trim()) return

    const newRow: ImpairmentCalcRow = {
      id: crypto.randomUUID(),
      seq: rows.value.length + 1,
      investProject: value.trim(),
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
    // 重排序号
    rows.value.forEach((r, i) => { r.seq = i + 1 })
  }

  // ─── 数据加载 ─────────────────────────────────────────────────────────────

  function loadRows(data: ImpairmentCalcRow[]): void {
    rows.value = data.map((r, i) => {
      const row: ImpairmentCalcRow = {
        ...r,
        id: r.id || crypto.randomUUID(),
        seq: i + 1,
      }
      recalcRow(row)
      return row
    })
  }

  // ─── 导出序列化 ──────────────────────────────────────────────────────────

  function toJSON(): ImpairmentCalcRow[] {
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

export default useG4EclImpairmentCalc
