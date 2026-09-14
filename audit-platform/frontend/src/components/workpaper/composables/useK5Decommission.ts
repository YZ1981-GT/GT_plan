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

/** （一）弃置费用完整性检查行 */
export interface K5CompletenessRow {
  rowId: string
  internalDesc: string       // 描述相关内部资料、外部评估报告等
  thirdPartyDesc: string     // 描述与第三方机构或监管机构的函件
  faIncreaseCheck: string    // 检查固定资产本期增加，是否迹象表明计提不足
  onSiteObservation: string  // 实地观察固定资产，是否迹象表明计提不足
  indexNo: string            // 相关支持性资料索引
}

/** （二）关键假设评估行 */
export interface K5AssumptionRow {
  rowId: string
  assumption: string          // 关键假设
  consistentWithData: string  // 是否与历史/行业数据一致（是/否）
  affectedByPostEvent: string // 期后事项是否会影响关键假设（是/否）
  isReasonable: string        // 关键假设是否合理（是/否）
  indexNo: string             // 相关支持性资料索引
}

/** 借/贷方发生额分析行 */
export interface K5AmountAnalysisRow {
  rowId: string
  offsetAccount: string  // 对应科目
  amount: number         // 对应金额
  remark: string         // 备注
}

export interface UseK5DecommissionParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: (field: string, value: any) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K5-5-rows'
const ITEM_ID_COMPLETENESS = 'K5-5-completeness-rows'
const ITEM_ID_ASSUMPTION = 'K5-5-assumption-rows'
const ITEM_ID_DEBIT = 'K5-5-debit-analysis'
const ITEM_ID_CREDIT = 'K5-5-credit-analysis'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK5Decommission(params: UseK5DecommissionParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const decommissionRows = ref<K5DecommissionRow[]>([])
  const completenessRows = ref<K5CompletenessRow[]>([])    // （一）完整性检查
  const assumptionRows = ref<K5AssumptionRow[]>([])         // （二）关键假设评估
  const debitRows = ref<K5AmountAnalysisRow[]>([])          // 借方发生额分析
  const creditRows = ref<K5AmountAnalysisRow[]>([])         // 贷方发生额分析

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { decommissionRows.value = [] } else {
      try {
        const parsed = JSON.parse(raw)
        decommissionRows.value = Array.isArray(parsed) && parsed.length > 0 ? parsed.map(_normalizeRow) : []
      } catch { decommissionRows.value = [] }
    }
    completenessRows.value = _loadArray(ITEM_ID_COMPLETENESS, _normalizeCompletenessRow)
    assumptionRows.value = _loadArray(ITEM_ID_ASSUMPTION, _normalizeAssumptionRow)
    debitRows.value = _loadArray(ITEM_ID_DEBIT, _normalizeAmountRow)
    creditRows.value = _loadArray(ITEM_ID_CREDIT, _normalizeAmountRow)
  }

  function _loadArray<T>(itemId: string, mapper: (raw: any) => T): T[] {
    const item = allResponses.value.get(itemId)
    const raw = item?.remark ?? item?.conclusion ?? null
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed.map(mapper) : []
    } catch { return [] }
  }

  function _normalizeCompletenessRow(raw: any): K5CompletenessRow {
    return {
      rowId: raw.rowId ?? `crow-${Math.random().toString(36).slice(2, 10)}`,
      internalDesc: raw.internalDesc ?? '',
      thirdPartyDesc: raw.thirdPartyDesc ?? '',
      faIncreaseCheck: raw.faIncreaseCheck ?? '',
      onSiteObservation: raw.onSiteObservation ?? '',
      indexNo: raw.indexNo ?? '',
    }
  }

  function _normalizeAssumptionRow(raw: any): K5AssumptionRow {
    return {
      rowId: raw.rowId ?? `arow-${Math.random().toString(36).slice(2, 10)}`,
      assumption: raw.assumption ?? '',
      consistentWithData: raw.consistentWithData ?? '',
      affectedByPostEvent: raw.affectedByPostEvent ?? '',
      isReasonable: raw.isReasonable ?? '',
      indexNo: raw.indexNo ?? '',
    }
  }

  function _normalizeAmountRow(raw: any): K5AmountAnalysisRow {
    return {
      rowId: raw.rowId ?? `mrow-${Math.random().toString(36).slice(2, 10)}`,
      offsetAccount: raw.offsetAccount ?? '',
      amount: Number(raw.amount) || 0,
      remark: raw.remark ?? '',
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
    saveResponse('5-completeness-rows', { remark: JSON.stringify(completenessRows.value) })
    saveResponse('5-assumption-rows', { remark: JSON.stringify(assumptionRows.value) })
    saveResponse('5-debit-analysis', { remark: JSON.stringify(debitRows.value) })
    saveResponse('5-credit-analysis', { remark: JSON.stringify(creditRows.value) })
  }

  // ─── （一）完整性检查 CRUD ─────────────────────────────────────────────────
  function addCompletenessRow(): void {
    completenessRows.value.push(_normalizeCompletenessRow({}))
    _persist()
  }
  function updateCompletenessCell(rowId: string, field: string, value: any): void {
    const row = completenessRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persist()
  }
  function removeCompletenessRow(idx: number): void {
    if (idx < 0 || idx >= completenessRows.value.length) return
    completenessRows.value.splice(idx, 1)
    _persist()
  }

  // ─── （二）关键假设评估 CRUD ───────────────────────────────────────────────
  function addAssumptionRow(): void {
    assumptionRows.value.push(_normalizeAssumptionRow({}))
    _persist()
  }
  function updateAssumptionCell(rowId: string, field: string, value: any): void {
    const row = assumptionRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persist()
  }
  function removeAssumptionRow(idx: number): void {
    if (idx < 0 || idx >= assumptionRows.value.length) return
    assumptionRows.value.splice(idx, 1)
    _persist()
  }

  // ─── 借/贷方发生额分析 CRUD ────────────────────────────────────────────────
  function addAmountRow(side: 'debit' | 'credit'): void {
    const arr = side === 'debit' ? debitRows : creditRows
    arr.value.push(_normalizeAmountRow({}))
    _persist()
  }
  function updateAmountCell(side: 'debit' | 'credit', rowId: string, field: string, value: any): void {
    const arr = side === 'debit' ? debitRows : creditRows
    const row = arr.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persist()
  }
  function removeAmountRow(side: 'debit' | 'credit', idx: number): void {
    const arr = side === 'debit' ? debitRows : creditRows
    if (idx < 0 || idx >= arr.value.length) return
    arr.value.splice(idx, 1)
    _persist()
  }

  const debitTotal = computed(() => calcSubtotal(debitRows.value.map(r => r.amount)))
  const creditTotal = computed(() => calcSubtotal(creditRows.value.map(r => r.amount)))

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
    // （一）完整性检查
    completenessRows,
    addCompletenessRow,
    updateCompletenessCell,
    removeCompletenessRow,
    // （二）关键假设评估
    assumptionRows,
    addAssumptionRow,
    updateAssumptionCell,
    removeAssumptionRow,
    // 借/贷方发生额分析
    debitRows,
    creditRows,
    debitTotal,
    creditTotal,
    addAmountRow,
    updateAmountCell,
    removeAmountRow,
  }
}
