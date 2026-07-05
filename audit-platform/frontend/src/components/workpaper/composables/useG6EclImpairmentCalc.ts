/**
 * useG6EclImpairmentCalc — G6-12 减值准备测算表（ECL公式链 + Stage分组 + 2区段Tab）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-ecl/
 * Task: 6.1
 *
 * 职责：
 * - 公式链自动计算（③④⑥⑦⑧⑨ + currentProvision/currentReversal 调用 useG6EclFormulaEngine 纯函数）
 * - Stage分组逻辑 + GroupSubtotal 小计汇总
 * - 行CRUD（addRow/removeRow） + 数据响应式绑定
 * - Tab切换行同步（activeTab + selectedRowIndex）
 * - 导入导出调用（useG6EclImportExport）
 *
 * G6 vs G4差异：
 * - G6含OCI影响列（Tab1）和OCI调整列（Tab2）
 * - G6按摊余成本口径计提（字段名 amortizedCost vs G4的 bookBalance）
 * - G6增加 fairValue / adjFairValue / ociImpact / ociAdjustment 列
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4
 */
import { ref, computed, watch } from 'vue'
import {
  calcImpairmentProvision,
  calcImpairmentAdjustment,
  calcAdjustedBalance,
  calcAdjustedImpairment,
  calcAdjustedBookValue,
  parseNum,
} from '@/composables/useG6EclFormulaEngine'
import { ElMessageBox } from 'element-plus'
import type { ImpairmentCalcRow } from './useG6EclFormData'

// ─── GroupSubtotal 小计接口 ──────────────────────────────────────────────────

export interface GroupSubtotal {
  amortizedCost: number         // Σ①
  impairmentProvision: number   // Σ③
  bookValue: number             // Σ④
  balanceAdjustment: number     // Σ⑤
  impairmentAdjustment: number  // Σ⑥
  adjBalance: number            // Σ⑦
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

function sumColumn(rows: ImpairmentCalcRow[], key: keyof ImpairmentCalcRow): number {
  const total = rows.reduce((s, r) => s + parseNum(r[key]), 0)
  return Math.round(total * 100) / 100
}

function calcSubtotal(rows: ImpairmentCalcRow[]): GroupSubtotal {
  return {
    amortizedCost: sumColumn(rows, 'amortizedCost'),
    impairmentProvision: sumColumn(rows, 'impairmentProvision'),
    bookValue: sumColumn(rows, 'bookValue'),
    balanceAdjustment: sumColumn(rows, 'balanceAdjustment'),
    impairmentAdjustment: sumColumn(rows, 'impairmentAdjustment'),
    adjBalance: sumColumn(rows, 'adjBalance'),
    adjImpairment: sumColumn(rows, 'adjImpairment'),
    adjBookValue: sumColumn(rows, 'adjBookValue'),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6EclImpairmentCalc() {
  const rows = ref<ImpairmentCalcRow[]>([])
  const activeTab = ref<'tab1' | 'tab2'>('tab1')
  const selectedRowIndex = ref(0)

  // ─── 公式链自动计算 ────────────────────────────────────────────────────────

  /**
   * recalcRow — 重算所有公式列 ③④⑥⑦⑧⑨ + currentProvision/currentReversal
   *
   * 公式链（G6按摊余成本口径）：
   * ③ impairmentProvision = ① amortizedCost × ② creditLossRate
   * ④ bookValue = ① - ③
   * ⑥ impairmentAdjustment = ⑤×②A + ①×(②A-②)（可负=冲回）
   * ⑦ adjBalance = ① + ⑤
   * ⑧ adjImpairment = ③ + ⑥
   * ⑨ adjBookValue = ⑦ - ⑧
   * currentProvision = max(0, ⑧ - priorImpairment)
   * currentReversal = max(0, priorImpairment - ⑧)
   */
  function recalcRow(row: ImpairmentCalcRow): void {
    // ③ 坏账准备 = ① × ②
    row.impairmentProvision = calcImpairmentProvision(row.amortizedCost, row.creditLossRate)

    // ④ 账面价值 = ① - ③
    row.bookValue = Math.round((parseNum(row.amortizedCost) - parseNum(row.impairmentProvision)) * 100) / 100

    // ⑥ 坏账调整 = ⑤×②A + ①×(②A-②)（可负）
    row.impairmentAdjustment = calcImpairmentAdjustment(
      row.balanceAdjustment,
      row.adjustedCreditLossRate,
      row.amortizedCost,
      row.creditLossRate,
    )

    // ⑦ 审定余额 = ① + ⑤
    row.adjBalance = calcAdjustedBalance(row.amortizedCost, row.balanceAdjustment)

    // ⑧ 审定坏账 = ③ + ⑥
    row.adjImpairment = calcAdjustedImpairment(row.impairmentProvision, row.impairmentAdjustment)

    // ⑨ 审定账面价值 = ⑦ - ⑧
    row.adjBookValue = calcAdjustedBookValue(row.adjBalance, row.adjImpairment)

    // 本年计提 = max(0, 审定坏账⑧ - 上年坏账)
    const diff = parseNum(row.adjImpairment) - parseNum(row.priorImpairment)
    row.currentProvision = Math.round(Math.max(0, diff) * 100) / 100

    // 本年转回 = max(0, 上年坏账 - 审定坏账⑧)
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
      amortizedCost: 0,
      fairValue: 0,
      creditLossRate: 0,
      impairmentProvision: 0,
      bookValue: 0,
      balanceAdjustment: 0,
      adjustedCreditLossRate: 0,
      impairmentAdjustment: 0,
      stage: defaultStage,
      ociImpact: 0,
      indexRef: '',
      adjBalance: 0,
      adjImpairment: 0,
      adjBookValue: 0,
      adjFairValue: 0,
      priorImpairment: 0,
      currentProvision: 0,
      currentReversal: 0,
      ociAdjustment: 0,
      differenceNote: '',
    }
    recalcRow(newRow)
    rows.value.push(newRow)
  }

  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
    // 重排序号
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    // 修正selectedRowIndex防止越界
    if (selectedRowIndex.value >= rows.value.length) {
      selectedRowIndex.value = Math.max(0, rows.value.length - 1)
    }
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
    selectedRowIndex,
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

export default useG6EclImpairmentCalc
