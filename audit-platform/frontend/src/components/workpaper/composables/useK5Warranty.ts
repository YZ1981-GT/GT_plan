/**
 * useK5Warranty — K5-4 产品质量保修检查表逻辑
 *
 * Spec: .kiro/specs/k5-provisions/
 * Task: 3.4
 * Requirements: 6.1-6.4
 *
 * 职责：
 * - 管理产品质量保修检查行（产品/销售收入/历史保修率/预计保修支出/期初/计提/使用/期末/结论）
 * - 公式：预计保修支出=销售收入×历史保修率
 * - 与K5-1产品质量保证行交叉验证
 * - AI辅助生成结论
 * - Save with prefix "K5-4-"
 *
 * 科目：2701 预计负债-产品质量保证（**贷方/负债类**）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcWarrantyProvision } from './useK5BestEstimateEngine'
import { calcLiabilityEndBalance, calcSubtotal } from './useK5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K5WarrantyRow {
  rowId: string
  seqNo: number
  productName: string         // 产品名称（计提基数科目/产品类别）
  revenue: number             // 计提基数（销售收入）
  warrantyRate: number        // 计提比例（历史保修率，小数，如0.02=2%）
  estimatedExpense: number    // 应计提金额（公式：计提基数×计提比例）
  bookProvision: number       // 账面已计提金额
  variance: number            // 差异金额（公式：应计提 − 账面已计提）
  varianceReason: string      // 差异原因
  beginBalance: number        // 期初余额
  periodProvision: number     // 本期计提
  periodUsed: number          // 本期使用（转销）
  endBalance: number          // 期末余额（公式：期初+计提-使用）
  conclusion: string          // 结论
  remark: string
}

/** （二）历史质量保修情况：本期 + 前2年 实际发生额/收入 → 计算3年平均保修率 */
export interface K5WarrantyHistoryRow {
  rowId: string
  productName: string
  currentActual: number   // 本期实际发生金额
  currentRevenue: number  // 本期收入金额
  year1Actual: number     // 前1年实际发生金额
  year1Revenue: number    // 前1年收入金额
  year2Actual: number     // 前2年实际发生金额
  year2Revenue: number    // 前2年收入金额
  avgRate: number         // 3年平均保修率（∑实际/∑收入）
}

/** （四）预计保修发生时间：期末数分1年内/1年以上 */
export interface K5WarrantyTimingRow {
  rowId: string
  productName: string
  endBalance: number      // 期末数
  within1Year: number     // 1年以内
  over1Year: number       // 1年以上
}

export interface K5WarrantySubtotals {
  revenue: number
  estimatedExpense: number
  beginBalance: number
  periodProvision: number
  periodUsed: number
  endBalance: number
  count: number
}

export interface K5WarrantyCrossCheck {
  /** K5-4 期末合计 */
  warrantyTotal: number
  /** K5-1 产品质保行审定数（从allResponses读取） */
  adjudicationWarranty: number
  /** 差异 */
  diff: number
  /** 是否一致 */
  isMatch: boolean
}

export interface UseK5WarrantyParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K5-4-rows'
const ITEM_ID_POLICY = 'K5-4-policy'
const ITEM_ID_HISTORY = 'K5-4-history-rows'
const ITEM_ID_TIMING = 'K5-4-timing-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK5Warranty(params: UseK5WarrantyParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const warrantyRows = ref<K5WarrantyRow[]>([])
  const policyText = ref('')                              // （一）产品质量保修政策
  const historyRows = ref<K5WarrantyHistoryRow[]>([])     // （二）历史质量保修情况
  const timingRows = ref<K5WarrantyTimingRow[]>([])       // （四）预计保修发生时间

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { warrantyRows.value = [] } else {
      try {
        const parsed = JSON.parse(raw)
        warrantyRows.value = Array.isArray(parsed) && parsed.length > 0 ? parsed.map(_normalizeRow) : []
      } catch { warrantyRows.value = [] }
    }
    // （一）政策
    const pItem = allResponses.value.get(ITEM_ID_POLICY)
    policyText.value = (pItem?.remark ?? pItem?.conclusion ?? (typeof pItem === 'string' ? pItem : '')) || ''
    // （二）历史保修率对照
    const hItem = allResponses.value.get(ITEM_ID_HISTORY)
    const hRaw = hItem?.remark ?? hItem?.conclusion ?? null
    if (hRaw) {
      try {
        const parsed = JSON.parse(hRaw)
        historyRows.value = Array.isArray(parsed) ? parsed.map(_normalizeHistoryRow) : []
      } catch { historyRows.value = [] }
    } else { historyRows.value = [] }
    // （四）预计发生时间
    const tItem = allResponses.value.get(ITEM_ID_TIMING)
    const tRaw = tItem?.remark ?? tItem?.conclusion ?? null
    if (tRaw) {
      try {
        const parsed = JSON.parse(tRaw)
        timingRows.value = Array.isArray(parsed) ? parsed.map(_normalizeTimingRow) : []
      } catch { timingRows.value = [] }
    } else { timingRows.value = [] }
  }

  function _normalizeHistoryRow(raw: any): K5WarrantyHistoryRow {
    const row: K5WarrantyHistoryRow = {
      rowId: raw.rowId ?? `hrow-${Math.random().toString(36).slice(2, 10)}`,
      productName: raw.productName ?? '',
      currentActual: Number(raw.currentActual) || 0,
      currentRevenue: Number(raw.currentRevenue) || 0,
      year1Actual: Number(raw.year1Actual) || 0,
      year1Revenue: Number(raw.year1Revenue) || 0,
      year2Actual: Number(raw.year2Actual) || 0,
      year2Revenue: Number(raw.year2Revenue) || 0,
      avgRate: 0,
    }
    _recalcHistoryRow(row)
    return row
  }

  function _normalizeTimingRow(raw: any): K5WarrantyTimingRow {
    return {
      rowId: raw.rowId ?? `trow-${Math.random().toString(36).slice(2, 10)}`,
      productName: raw.productName ?? '',
      endBalance: Number(raw.endBalance) || 0,
      within1Year: Number(raw.within1Year) || 0,
      over1Year: Number(raw.over1Year) || 0,
    }
  }

  function _recalcHistoryRow(row: K5WarrantyHistoryRow): void {
    const totalActual = row.currentActual + row.year1Actual + row.year2Actual
    const totalRevenue = row.currentRevenue + row.year1Revenue + row.year2Revenue
    row.avgRate = totalRevenue > 0 ? totalActual / totalRevenue : 0
  }

  function _normalizeRow(raw: any, idx?: number): K5WarrantyRow {
    const row: K5WarrantyRow = {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      productName: raw.productName ?? '',
      revenue: Number(raw.revenue) || 0,
      warrantyRate: Number(raw.warrantyRate) || 0,
      estimatedExpense: 0,
      bookProvision: Number(raw.bookProvision) || 0,
      variance: 0,
      varianceReason: raw.varianceReason ?? '',
      beginBalance: Number(raw.beginBalance) || 0,
      periodProvision: Number(raw.periodProvision) || 0,
      periodUsed: Number(raw.periodUsed) || 0,
      endBalance: 0,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
    _recalcRow(row)
    return row
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K5WarrantyRow): void {
    // 应计提金额=计提基数×计提比例
    row.estimatedExpense = calcWarrantyProvision(row.revenue, row.warrantyRate)
    // 差异金额=应计提 − 账面已计提
    row.variance = row.estimatedExpense - (row.bookProvision || 0)
    // 负债类期末=期初+计提-使用
    row.endBalance = calcLiabilityEndBalance(row.beginBalance, row.periodProvision, row.periodUsed)
  }

  function recalcAll(): void {
    for (const row of warrantyRows.value) _recalcRow(row)
  }

  // ─── Subtotals ─────────────────────────────────────────────────────────────

  const subtotals: ComputedRef<K5WarrantySubtotals> = computed(() => {
    const r = warrantyRows.value
    return {
      revenue: calcSubtotal(r.map(x => x.revenue)),
      estimatedExpense: calcSubtotal(r.map(x => x.estimatedExpense)),
      beginBalance: calcSubtotal(r.map(x => x.beginBalance)),
      periodProvision: calcSubtotal(r.map(x => x.periodProvision)),
      periodUsed: calcSubtotal(r.map(x => x.periodUsed)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      count: r.length,
    }
  })

  // ─── 与K5-1交叉验证 (Req 6.3) ─────────────────────────────────────────────

  const crossCheck: ComputedRef<K5WarrantyCrossCheck> = computed(() => {
    const warrantyTotal = subtotals.value.endBalance
    // 从 allResponses 获取K5-1产品质保行审定数
    const adjItem = allResponses.value.get('K5-1-r0-audited') ?? allResponses.value.get('K5-1-warranty-audited')
    const adjVal = Number(adjItem?.remark ?? adjItem?.conclusion ?? 0) || 0
    const diff = warrantyTotal - adjVal
    return {
      warrantyTotal,
      adjudicationWarranty: adjVal,
      diff,
      isMatch: Math.abs(diff) < 0.01,
    }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = warrantyRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── Dynamic Row Add ───────────────────────────────────────────────────────

  async function addRow(productName?: string): Promise<void> {
    let name = productName
    if (!name) {
      try {
        const { value } = await ElMessageBox.prompt(
          '请输入产品名称',
          '新增产品质量保修行',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：XX型号产品',
            inputValidator: (val) => (!val?.trim() ? '产品名称不能为空' : true),
          },
        )
        name = value?.trim()
      } catch {
        return
      }
    }
    if (!name) return

    const newRow: K5WarrantyRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: warrantyRows.value.length + 1,
      productName: name,
      revenue: 0,
      warrantyRate: 0,
      estimatedExpense: 0,
      bookProvision: 0,
      variance: 0,
      varianceReason: '',
      beginBalance: 0,
      periodProvision: 0,
      periodUsed: 0,
      endBalance: 0,
      conclusion: '',
      remark: '',
    }
    warrantyRows.value.push(newRow)
    _persist()
  }

  // ─── （二）历史保修率对照行操作 ────────────────────────────────────────────

  function updateHistoryCell(rowId: string, field: string, value: any): void {
    const row = historyRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcHistoryRow(row)
    _persist()
  }

  function addHistoryRow(productName = ''): void {
    historyRows.value.push({
      rowId: `hrow-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      productName, currentActual: 0, currentRevenue: 0,
      year1Actual: 0, year1Revenue: 0, year2Actual: 0, year2Revenue: 0, avgRate: 0,
    })
    _persist()
  }

  function removeHistoryRow(idx: number): void {
    if (idx < 0 || idx >= historyRows.value.length) return
    historyRows.value.splice(idx, 1)
    _persist()
  }

  // ─── （四）预计发生时间行操作 ──────────────────────────────────────────────

  function updateTimingCell(rowId: string, field: string, value: any): void {
    const row = timingRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persist()
  }

  function addTimingRow(productName = ''): void {
    timingRows.value.push({
      rowId: `trow-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      productName, endBalance: 0, within1Year: 0, over1Year: 0,
    })
    _persist()
  }

  function removeTimingRow(idx: number): void {
    if (idx < 0 || idx >= timingRows.value.length) return
    timingRows.value.splice(idx, 1)
    _persist()
  }

  // ─── （一）政策 ────────────────────────────────────────────────────────────

  function updatePolicy(text: string): void {
    policyText.value = text
    _persist()
  }

  // ─── 历史/时间 合计 ───────────────────────────────────────────────────────

  const historySubtotals = computed(() => {
    const r = historyRows.value
    const totalActual = calcSubtotal(r.map(x => x.currentActual + x.year1Actual + x.year2Actual))
    const totalRevenue = calcSubtotal(r.map(x => x.currentRevenue + x.year1Revenue + x.year2Revenue))
    return {
      currentActual: calcSubtotal(r.map(x => x.currentActual)),
      currentRevenue: calcSubtotal(r.map(x => x.currentRevenue)),
      year1Actual: calcSubtotal(r.map(x => x.year1Actual)),
      year1Revenue: calcSubtotal(r.map(x => x.year1Revenue)),
      year2Actual: calcSubtotal(r.map(x => x.year2Actual)),
      year2Revenue: calcSubtotal(r.map(x => x.year2Revenue)),
      avgRate: totalRevenue > 0 ? totalActual / totalRevenue : 0,
    }
  })

  const timingSubtotals = computed(() => {
    const r = timingRows.value
    return {
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      within1Year: calcSubtotal(r.map(x => x.within1Year)),
      over1Year: calcSubtotal(r.map(x => x.over1Year)),
    }
  })

  // ─── Remove Row ────────────────────────────────────────────────────────────

  function removeRow(idx: number): void {
    if (idx < 0 || idx >= warrantyRows.value.length) return
    warrantyRows.value.splice(idx, 1)
    warrantyRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  // ─── Import ────────────────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    warrantyRows.value = data.map((raw, i) => _normalizeRow(raw, i))
    _persist()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    saveResponse('4-rows', { remark: JSON.stringify(warrantyRows.value) })
    saveResponse('4-warranty-total', { remark: String(subtotals.value.endBalance) })
    saveResponse('4-policy', { remark: policyText.value })
    saveResponse('4-history-rows', { remark: JSON.stringify(historyRows.value) })
    saveResponse('4-timing-rows', { remark: JSON.stringify(timingRows.value) })
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    warrantyRows,
    subtotals,
    crossCheck,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    // （一）政策
    policyText,
    updatePolicy,
    // （二）历史保修率对照
    historyRows,
    historySubtotals,
    updateHistoryCell,
    addHistoryRow,
    removeHistoryRow,
    // （四）预计发生时间
    timingRows,
    timingSubtotals,
    updateTimingCell,
    addTimingRow,
    removeTimingRow,
  }
}
