/**
 * useK12Detail — K12-2 明细表逻辑（27行×26列→3区段Tab管理，31+公式）
 *
 * Spec: .kiro/specs/k12-non-operating-income/
 * Task: 3.4
 * Requirements: 2~6 全部
 *
 * 职责：
 * - 27行动态明细行管理（按收入来源逐项）
 * - 26列拆3区段Tab：
 *   基础(序号/收入来源/收入类型/对方单位/金额/发生日期)
 *   | 分析(占比/同比/说明)
 *   | 检查(依据文件/凭证号/是否偶发/结论/备注)
 * - Month columns B~M (12月贷方发生) + N(sum) + O(AJE) + P(RJE) + Q(audited)
 * - 使用 calcAuditedAmount / calcProportion / calcYoYChange / calcSubtotal
 * - 动态行增删 + 导入/导出支持
 * - 合计行联动审定表（存储 "K12-2-subtotal" 供CrossSheet使用）
 *
 * 科目：6301营业外收入（**损益类/贷方科目**）
 * Item IDs: "K12-2-row-{idx}-{field}", "K12-2-subtotal"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcProportion,
  calcYoYChange,
  calcSubtotal,
} from './useK12FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表行存储结构 */
export interface K12DetailRow {
  rowKey: string
  /** 序号 */
  seq: number
  // ─── 基础区段 ───
  /** 收入来源 */
  incomeSource: string
  /** 收入类型（政府补助/债务重组利得/资产盘盈/罚款收入/捐赠利得/无法支付款项转入/其他） */
  incomeType: string
  /** 对方单位 */
  counterparty: string
  /** 金额（本期发生额） */
  amount: number
  /** 发生日期 */
  occurDate: string
  // ─── 月份列 B~M（12个月贷方发生） ───
  monthAmounts: number[]
  /** N列：12个月合计（公式：SUM(B~M)） */
  monthTotal: number
  /** O列：AJE调整 */
  aje: number
  /** P列：RJE重分类 */
  rje: number
  /** Q列：审定数（公式：monthTotal + AJE + RJE） */
  audited: number
  // ─── 分析区段 ───
  /** 占比（公式：本行审定/合计审定） */
  proportion: number | null
  /** 同比变动率 */
  yoyChange: number | null
  /** 上期金额（用于同比计算） */
  priorAmount: number
  /** 分析说明 */
  analysisNote: string
  // ─── 检查区段 ───
  /** 依据文件 */
  supportingDoc: string
  /** 凭证号 */
  voucherRef: string
  /** 是否偶发 */
  isNonRecurring: boolean
  /** 结论 */
  conclusion: string
  /** 备注 */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
}

/** 区段Tab标识 */
export type K12DetailTabKey = 'basic' | 'analysis' | 'check'

export interface K12DetailSubtotal {
  amount: number
  monthTotal: number
  aje: number
  rje: number
  audited: number
  priorAmount: number
}

export interface UseK12DetailParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'K12-2-detail-rows'
const ITEM_PREFIX = 'K12-2'

/** 3区段Tab配置 */
export const DETAIL_TABS: Array<{ key: K12DetailTabKey; label: string }> = [
  { key: 'basic', label: '基础信息' },
  { key: 'analysis', label: '分析' },
  { key: 'check', label: '检查' },
]

/** 收入类型选项 */
export const INCOME_TYPE_OPTIONS = [
  '政府补助',
  '债务重组利得',
  '资产盘盈利得',
  '罚款收入',
  '捐赠利得',
  '无法支付款项转入',
  '其他',
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK12Detail(params: UseK12DetailParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K12DetailRow[]>([])
  const activeTab = ref<K12DetailTabKey>('basic')
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

  function _normalizeRow(raw: any, idx: number): K12DetailRow {
    const monthAmounts = Array.isArray(raw.monthAmounts) && raw.monthAmounts.length === 12
      ? raw.monthAmounts.map(parseNum)
      : Array(12).fill(0)
    const monthTotal = calcSubtotal(monthAmounts)
    const aje = parseNum(raw.aje)
    const rje = parseNum(raw.rje)
    const audited = calcAuditedAmount(monthTotal, aje, rje)
    const priorAmount = parseNum(raw.priorAmount)
    const yoyChange = calcYoYChange(audited, priorAmount)

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seq: idx + 1,
      incomeSource: raw.incomeSource ?? '',
      incomeType: raw.incomeType ?? '',
      counterparty: raw.counterparty ?? '',
      amount: parseNum(raw.amount),
      occurDate: raw.occurDate ?? '',
      monthAmounts,
      monthTotal,
      aje,
      rje,
      audited,
      proportion: null, // 需要合计后重算
      yoyChange,
      priorAmount,
      analysisNote: raw.analysisNote ?? '',
      supportingDoc: raw.supportingDoc ?? '',
      voucherRef: raw.voucherRef ?? '',
      isNonRecurring: raw.isNonRecurring ?? false,
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
    }
  }

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedRows: ComputedRef<K12DetailRow[]> = computed(() => {
    // 先计算合计审定数用于占比
    const allAudited = rows.value.map((row) => {
      const mt = calcSubtotal(row.monthAmounts)
      return calcAuditedAmount(mt, row.aje, row.rje)
    })
    const totalAudited = calcSubtotal(allAudited)

    return rows.value.map((row, idx) => {
      const monthTotal = calcSubtotal(row.monthAmounts)
      const audited = calcAuditedAmount(monthTotal, row.aje, row.rje)
      const proportion = calcProportion(audited, totalAudited)
      const yoyChange = calcYoYChange(audited, row.priorAmount)
      return {
        ...row,
        seq: idx + 1,
        monthTotal,
        audited,
        proportion,
        yoyChange,
      }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const subtotal: ComputedRef<K12DetailSubtotal> = computed(() => {
    const detail = computedRows.value
    const amount = calcSubtotal(detail.map(r => r.amount))
    const monthTotal = calcSubtotal(detail.map(r => r.monthTotal))
    const aje = calcSubtotal(detail.map(r => r.aje))
    const rje = calcSubtotal(detail.map(r => r.rje))
    const audited = calcAuditedAmount(monthTotal, aje, rje)
    const priorAmount = calcSubtotal(detail.map(r => r.priorAmount))
    return { amount, monthTotal, aje, rje, audited, priorAmount }
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

  /** 更新月份列 */
  function updateMonthAmount(rowKey: string, monthIndex: number, value: number): void {
    if (isReadonly?.value) return
    if (monthIndex < 0 || monthIndex >= 12) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return
    row.monthAmounts[monthIndex] = parseNum(value)
    _recalcRow(row)
    isChanged.value = true
    _persist()
  }

  function _recalcRow(row: K12DetailRow): void {
    row.monthTotal = calcSubtotal(row.monthAmounts)
    row.audited = calcAuditedAmount(row.monthTotal, row.aje, row.rje)
    row.yoyChange = calcYoYChange(row.audited, row.priorAmount)
    // proportion在computed中重算（需合计值）
  }

  // ─── 动态行操作 ────────────────────────────────────────────────────────────

  function addRow(incomeSource: string, incomeType: string = ''): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seq: rows.value.length + 1,
      incomeSource,
      incomeType,
      counterparty: '',
      amount: 0,
      occurDate: '',
      monthAmounts: Array(12).fill(0),
      monthTotal: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      proportion: null,
      yoyChange: null,
      priorAmount: 0,
      analysisNote: '',
      supportingDoc: '',
      voucherRef: '',
      isNonRecurring: false,
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

  // ─── 批量导入（导入导出支持） ─────────────────────────────────────────────

  function importRows(data: Array<Partial<K12DetailRow>>): void {
    if (isReadonly?.value) return
    const imported = data.map((r, idx) => _normalizeRow(r, rows.value.length + idx))
    rows.value.push(...imported)
    isChanged.value = true
    _persist()
  }

  function exportRows(): K12DetailRow[] {
    return computedRows.value
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
    // 同步审定合计供CrossSheet使用（K12-1↔K12-2交叉验证）
    onSave('K12-2-subtotal', subtotal.value.audited)
  }

  // ─── Tab切换 ──────────────────────────────────────────────────────────────

  function setActiveTab(tab: K12DetailTabKey): void {
    activeTab.value = tab
  }

  function computeAll(): void {
    for (const row of rows.value) _recalcRow(row)
    _persist()
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows: computedRows,
    subtotal,
    activeTab,
    isChanged,
    updateCell,
    updateMonthAmount,
    addRow,
    removeRow,
    importRows,
    exportRows,
    setActiveTab,
    computeAll,
    initFromResponses,
  }
}

export default useK12Detail
