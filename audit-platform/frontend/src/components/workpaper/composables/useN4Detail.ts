/**
 * useN4Detail — N4-2 明细表逻辑（11列18公式，按税种逐项管理）
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/
 * Task: 3.3
 * Requirements: 3.1-3.6
 *
 * 职责：
 * - 动态行管理（新增/删除/重排序），每行代表一笔税种明细
 * - 每行: { seq, taxType, taxBasis, taxRate, periodAmount, priorAmount, yoyChange, n2Accrual, diff, conclusion }
 * - 税额 = 计税依据 × 税率（使用MultiTaxEngine）
 * - 同比变动 = (本期-上期)/上期
 * - N2计提差异 = 本期税额 - N2计提额（差异标红）
 * - 合计行联动审定表（存储 "N4-2-subtotal" 供CrossSheet交叉验证）
 * - 导入/导出集成钩子
 * - 统计摘要（税种数/总金额/平均同比）
 *
 * 科目：6403 税金及附加（损益类/借方科目）
 * Item IDs: "N4-2-detail-rows", "N4-2-subtotal"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcYoyChange,
  calcSubtotal,
} from './useN4FormulaEngine'
import { calcSurtax, calcStampTax, calcLandUseTax } from './useN4MultiTaxEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表行存储结构 */
export interface N4DetailRow {
  rowKey: string
  /** 序号 */
  seq: number
  /** 税种 */
  taxType: string
  /** 计税依据（金额/面积/数量等） */
  taxBasis: number
  /** 适用税率（小数形式） */
  taxRate: number
  /** 本期税额（公式：计税依据×税率） */
  periodAmount: number
  /** 上期税额 */
  priorAmount: number
  /** 同比变动率（公式：(本期-上期)/上期） */
  yoyChange: number | null
  /** N2计提额（来自N2应交税费） */
  n2Accrual: number
  /** 差异（公式：本期税额-N2计提额，非零=异常） */
  diff: number
  /** 审计结论（正常/差异已查明/需进一步核查） */
  conclusion: string
  /** 备注 */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
}

export interface N4DetailSubtotal {
  periodAmount: number
  priorAmount: number
  n2Accrual: number
  diff: number
}

/** 统计摘要 */
export interface N4DetailSummary {
  /** 税种数 */
  taxCount: number
  /** 总金额 */
  totalAmount: number
  /** 平均同比变动 */
  avgYoyChange: number | null
}

export interface UseN4DetailParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'N4-2-detail-rows'
const ITEM_PREFIX = 'N4-2'

/** 税种选项 */
export const TAX_TYPE_OPTIONS = [
  '消费税',
  '城市维护建设税',
  '教育费附加',
  '地方教育附加',
  '房产税',
  '城镇土地使用税',
  '车船税',
  '印花税',
  '资源税',
  '其他',
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

export function useN4Detail(params: UseN4DetailParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<N4DetailRow[]>([])
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const raw = _getJson(ROWS_KEY)
    if (Array.isArray(raw) && raw.length > 0) {
      rows.value = raw.map((r, idx) => _normalizeRow(r, idx))
    } else {
      rows.value = []
    }
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any, idx: number): N4DetailRow {
    const taxBasis = parseNum(raw.taxBasis)
    const taxRate = parseNum(raw.taxRate)
    const periodAmount = taxBasis * taxRate
    const priorAmount = parseNum(raw.priorAmount)
    const yoyChange = calcYoyChange(periodAmount, priorAmount)
    const n2Accrual = parseNum(raw.n2Accrual)
    const diff = periodAmount - n2Accrual

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seq: idx + 1,
      taxType: raw.taxType ?? '',
      taxBasis,
      taxRate,
      periodAmount,
      priorAmount,
      yoyChange,
      n2Accrual,
      diff,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
    }
  }

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedRows: ComputedRef<N4DetailRow[]> = computed(() => {
    return rows.value.map((row, idx) => {
      const periodAmount = row.taxBasis * row.taxRate
      const yoyChange = calcYoyChange(periodAmount, row.priorAmount)
      const diff = periodAmount - row.n2Accrual
      return { ...row, seq: idx + 1, periodAmount, yoyChange, diff }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const subtotal: ComputedRef<N4DetailSubtotal> = computed(() => {
    const detail = computedRows.value
    const periodAmount = calcSubtotal(detail.map(r => r.periodAmount))
    const priorAmount = calcSubtotal(detail.map(r => r.priorAmount))
    const n2Accrual = calcSubtotal(detail.map(r => r.n2Accrual))
    const diff = periodAmount - n2Accrual
    return { periodAmount, priorAmount, n2Accrual, diff }
  })

  // ─── Computed: 统计摘要 ────────────────────────────────────────────────────

  const summary: ComputedRef<N4DetailSummary> = computed(() => {
    const detail = computedRows.value
    const taxCount = detail.length
    const totalAmount = subtotal.value.periodAmount

    // 平均同比变动（排除null/除零行）
    const validYoys = detail
      .map(r => r.yoyChange)
      .filter((v): v is number => v !== null)
    const avgYoyChange = validYoys.length > 0
      ? validYoys.reduce((sum, v) => sum + v, 0) / validYoys.length
      : null

    return { taxCount, totalAmount, avgYoyChange }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: any): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    ;(row as any)[field] = value
    _recalcRow(row)
    isChanged.value = true
    _persist()
  }

  function _recalcRow(row: N4DetailRow): void {
    row.periodAmount = row.taxBasis * row.taxRate
    row.yoyChange = calcYoyChange(row.periodAmount, row.priorAmount)
    row.diff = row.periodAmount - row.n2Accrual
  }

  // ─── 动态行操作 ────────────────────────────────────────────────────────────

  function addRow(taxType: string): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seq: rows.value.length + 1,
      taxType,
      taxBasis: 0,
      taxRate: 0,
      periodAmount: 0,
      priorAmount: 0,
      yoyChange: null,
      n2Accrual: 0,
      diff: 0,
      conclusion: '',
      remark: '',
      isEditable: true,
    })
    isChanged.value = true
    _persist()
  }

  function removeRow(rowKey: string): void {
    if (isReadonly?.value) return
    const idx = rows.value.findIndex(r => r.rowKey === rowKey)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      isChanged.value = true
      _persist()
    }
  }

  function reorderRow(fromIdx: number, toIdx: number): void {
    if (isReadonly?.value) return
    if (fromIdx < 0 || toIdx < 0 || fromIdx >= rows.value.length || toIdx >= rows.value.length) return
    const [moved] = rows.value.splice(fromIdx, 1)
    rows.value.splice(toIdx, 0, moved)
    isChanged.value = true
    _persist()
  }

  // ─── 批量导入（导入导出支持） ─────────────────────────────────────────────

  function importRows(data: Array<Partial<N4DetailRow>>): void {
    if (isReadonly?.value) return
    const imported = data.map((r, idx) => _normalizeRow(r, rows.value.length + idx))
    rows.value.push(...imported)
    isChanged.value = true
    _persist()
  }

  function exportRows(): N4DetailRow[] {
    return computedRows.value
  }

  // ─── N2计提额批量更新（来自EventBus 'tax-accrual:updated'）───────────────

  function updateN2Accruals(accruals: Array<{ taxType: string; amount: number }>): void {
    for (const { taxType, amount } of accruals) {
      const matchRows = rows.value.filter(r => r.taxType === taxType)
      for (const row of matchRows) {
        row.n2Accrual = parseNum(amount)
        _recalcRow(row)
      }
    }
    if (accruals.length > 0) {
      isChanged.value = true
      _persist()
    }
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
    // 同步审定合计供CrossSheet使用（N4-1↔N4-2交叉验证）
    onSave(`${ITEM_PREFIX}-subtotal`, subtotal.value.periodAmount)
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    subtotal,
    summary,
    isChanged,
    updateCell,
    addRow,
    removeRow,
    reorderRow,
    importRows,
    exportRows,
    updateN2Accruals,
    initFromResponses,
  }
}

export default useN4Detail
