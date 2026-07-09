/**
 * useK5Decommission — K5-5 弃置费用检查表逻辑
 *
 * Spec: .kiro/specs/k5-provisions/
 * Task: 3.4
 * Requirements: 7.1-7.4
 *
 * 职责：
 * - 管理弃置费用检查行（资产/预计弃置支出/弃置时间/折现率/现值/期初/增加/利息调整/期末/结论）
 * - 公式：现值=预计弃置支出/(1+折现率)^年数
 * - 公式：本期利息调整=期初现值×折现率
 * - 与K5-1弃置义务行交叉验证
 * - Save with prefix "K5-5-"
 *
 * 科目：2701 预计负债-弃置义务（**贷方/负债类**）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcPresentValue } from './useK5BestEstimateEngine'
import { calcSubtotal } from './useK5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K5DecommissionRow {
  rowId: string
  seqNo: number
  assetName: string            // 资产名称
  futureExpense: number        // 预计弃置支出
  expectedYears: number        // 预计弃置时间（年数）
  discountRate: number         // 折现率（小数，如0.05=5%）
  presentValue: number         // 现值（公式：future/(1+rate)^years）
  beginBalance: number         // 期初余额
  periodIncrease: number       // 本期增加
  interestAdjustment: number   // 利息调整（公式：期初×折现率）
  endBalance: number           // 期末余额（公式：期初+增加+利息调整）
  conclusion: string           // 结论
  remark: string
}

export interface K5DecommissionSubtotals {
  futureExpense: number
  presentValue: number
  beginBalance: number
  periodIncrease: number
  interestAdjustment: number
  endBalance: number
  count: number
}

export interface K5DecommissionCrossCheck {
  /** K5-5 期末合计 */
  decommissionTotal: number
  /** K5-1 弃置义务行审定数 */
  adjudicationDecommission: number
  /** 差异 */
  diff: number
  /** 是否一致 */
  isMatch: boolean
}

export interface UseK5DecommissionParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K5-5-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK5Decommission(params: UseK5DecommissionParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const decommissionRows = ref<K5DecommissionRow[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { decommissionRows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        decommissionRows.value = parsed.map(_normalizeRow)
      } else {
        decommissionRows.value = []
      }
    } catch {
      decommissionRows.value = []
    }
  }

  function _normalizeRow(raw: any, idx?: number): K5DecommissionRow {
    const row: K5DecommissionRow = {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      assetName: raw.assetName ?? '',
      futureExpense: Number(raw.futureExpense) || 0,
      expectedYears: Number(raw.expectedYears) || 0,
      discountRate: Number(raw.discountRate) || 0,
      presentValue: 0,
      beginBalance: Number(raw.beginBalance) || 0,
      periodIncrease: Number(raw.periodIncrease) || 0,
      interestAdjustment: 0,
      endBalance: 0,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
    _recalcRow(row)
    return row
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K5DecommissionRow): void {
    // 现值=预计弃置支出/(1+折现率)^年数
    row.presentValue = calcPresentValue(row.futureExpense, row.discountRate, row.expectedYears)
    // 利息调整=期初现值×折现率（兜底：rate<=0时利息=0）
    row.interestAdjustment = row.discountRate > 0
      ? row.beginBalance * row.discountRate
      : 0
    // 期末=期初+增加+利息调整（弃置费用特殊：利息调整累积增加负债）
    row.endBalance = row.beginBalance + row.periodIncrease + row.interestAdjustment
  }

  function recalcAll(): void {
    for (const row of decommissionRows.value) _recalcRow(row)
  }

  // ─── Subtotals ─────────────────────────────────────────────────────────────

  const subtotals: ComputedRef<K5DecommissionSubtotals> = computed(() => {
    const r = decommissionRows.value
    return {
      futureExpense: calcSubtotal(r.map(x => x.futureExpense)),
      presentValue: calcSubtotal(r.map(x => x.presentValue)),
      beginBalance: calcSubtotal(r.map(x => x.beginBalance)),
      periodIncrease: calcSubtotal(r.map(x => x.periodIncrease)),
      interestAdjustment: calcSubtotal(r.map(x => x.interestAdjustment)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      count: r.length,
    }
  })

  // ─── 与K5-1交叉验证 (Req 7.4) ─────────────────────────────────────────────

  const crossCheck: ComputedRef<K5DecommissionCrossCheck> = computed(() => {
    const decommissionTotal = subtotals.value.endBalance
    // 从 allResponses 获取K5-1弃置义务行审定数（row index=4）
    const adjItem = allResponses.value.get('K5-1-r4-audited') ?? allResponses.value.get('K5-1-decommission-audited')
    const adjVal = Number(adjItem?.remark ?? adjItem?.conclusion ?? 0) || 0
    const diff = decommissionTotal - adjVal
    return {
      decommissionTotal,
      adjudicationDecommission: adjVal,
      diff,
      isMatch: Math.abs(diff) < 0.01,
    }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = decommissionRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── Dynamic Row Add ───────────────────────────────────────────────────────

  async function addRow(assetName?: string): Promise<void> {
    let name = assetName
    if (!name) {
      try {
        const { value } = await ElMessageBox.prompt(
          '请输入资产名称',
          '新增弃置费用检查行',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：XX矿井/XX油气设施',
            inputValidator: (val) => (!val?.trim() ? '资产名称不能为空' : true),
          },
        )
        name = value?.trim()
      } catch {
        return
      }
    }
    if (!name) return

    const newRow: K5DecommissionRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: decommissionRows.value.length + 1,
      assetName: name,
      futureExpense: 0,
      expectedYears: 0,
      discountRate: 0,
      presentValue: 0,
      beginBalance: 0,
      periodIncrease: 0,
      interestAdjustment: 0,
      endBalance: 0,
      conclusion: '',
      remark: '',
    }
    decommissionRows.value.push(newRow)
    _persist()
  }

  // ─── Remove Row ────────────────────────────────────────────────────────────

  function removeRow(idx: number): void {
    if (idx < 0 || idx >= decommissionRows.value.length) return
    decommissionRows.value.splice(idx, 1)
    decommissionRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  // ─── Import ────────────────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    decommissionRows.value = data.map((raw, i) => _normalizeRow(raw, i))
    _persist()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    saveResponse('5-rows', { remark: JSON.stringify(decommissionRows.value) })
    saveResponse('5-decommission-total', { remark: String(subtotals.value.endBalance) })
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    decommissionRows,
    subtotals,
    crossCheck,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
  }
}
