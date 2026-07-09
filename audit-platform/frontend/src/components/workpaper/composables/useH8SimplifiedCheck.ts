/**
 * useH8SimplifiedCheck — H8-13 简化处理检查表 composable（99行18列12公式）
 *
 * CAS21第32条：短期租赁(≤12月) / 低价值资产租赁(≤4万) 可选择简化处理
 * 简化处理：不确认使用权资产和租赁负债，直接计入当期费用
 *
 * 18列含：合同号/资产/出租方/租赁期/年租金/资产全新价值/
 *   是否短期(≤12月)/是否低价值(≤4万)/简化处理类型/费用确认/核查结论
 *
 * 自动判断：
 * - 租赁期≤12月 → 短期租赁
 * - 资产全新价值≤40000 → 低价值
 * - 都不满足 → 红色高亮"不符合简化条件"
 *
 * 底部统计：简化处理笔数/总年租金/应转为使用权资产笔数
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.4
 * Requirements: 8.1-8.4
 */
import { ref, computed, watch, type Ref } from 'vue'
import { isShortTermLease, isLowValueLease } from './useH8CAS21Engine'
import { calcSubtotal } from './useH8FormulaEngine'

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
  /** 租赁期（月） */
  leaseTermMonths: number
  /** 年租金 */
  annualRental: number
  /** 资产全新价值 */
  newAssetValue: number
  /** 是否短期租赁（自动判断：≤12月） */
  isShortTerm: boolean
  /** 是否低价值（自动判断：≤4万） */
  isLowValue: boolean
  /** 简化处理类型（自动推导） */
  simplifiedType: H8SimplifiedType
  /** 费用确认金额 */
  expenseAmount: number
  /** 核查结论 */
  conclusion: string
  /** 备注 */
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H8-13-rows'

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

  function _normalizeRow(raw: any): H8SimplifiedCheckRow {
    const leaseMonths = Number(raw.leaseTermMonths) || 0
    const assetValue = Number(raw.newAssetValue) || 0
    const shortTerm = isShortTermLease(leaseMonths)
    const lowValue = isLowValueLease(assetValue)

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      contractNo: raw.contractNo ?? '',
      assetName: raw.assetName ?? '',
      lessor: raw.lessor ?? '',
      leaseTermMonths: leaseMonths,
      annualRental: Number(raw.annualRental) || 0,
      newAssetValue: assetValue,
      isShortTerm: shortTerm,
      isLowValue: lowValue,
      simplifiedType: _deriveSimplifiedType(shortTerm, lowValue),
      expenseAmount: Number(raw.expenseAmount) || 0,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
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

    const textFields = ['contractNo', 'assetName', 'lessor', 'conclusion', 'remark']
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    const numVal = Number(value) || 0
    switch (field) {
      case 'leaseTermMonths': row.leaseTermMonths = numVal; break
      case 'annualRental': row.annualRental = numVal; break
      case 'newAssetValue': row.newAssetValue = numVal; break
      case 'expenseAmount': row.expenseAmount = numVal; _persist(); return
      default: return
    }

    // 重新判断短期/低价值
    row.isShortTerm = isShortTermLease(row.leaseTermMonths)
    row.isLowValue = isLowValueLease(row.newAssetValue)
    row.simplifiedType = _deriveSimplifiedType(row.isShortTerm, row.isLowValue)

    _persist()
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value.map(r => ({
      rowId: r.rowId, contractNo: r.contractNo, assetName: r.assetName,
      lessor: r.lessor, leaseTermMonths: r.leaseTermMonths,
      annualRental: r.annualRental, newAssetValue: r.newAssetValue,
      expenseAmount: r.expenseAmount, conclusion: r.conclusion, remark: r.remark,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    simplifiedCount, mustRecognizeCount, totalAnnualRental, totalAllRental,
    addRow, deleteRow, updateCell, save, load,
  }
}

export default useH8SimplifiedCheck
