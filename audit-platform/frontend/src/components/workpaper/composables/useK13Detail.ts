/**
 * useK13Detail — K13-2 明细表逻辑（27行×26列→3区段Tab管理，31+公式）
 *
 * Spec: .kiro/specs/k13-non-operating-expense/
 * Task: 3.4
 * Requirements: 2~6 全部
 *
 * 职责：
 * - 动态明细行管理（按支出去向逐项）
 * - 26列拆3区段Tab：
 *   基础(序号/支出去向/支出类型/对方单位/金额/发生日期/月份列/小计/AJE/RJE/审定)
 *   | 分析(是否偶发/交叉引用/占比/上期金额/上期AJE/上期RJE/上期审定/上期占比/同比变动)
 *   | 检查(covered by useK13Check)
 * - Month columns B~M (12月借方发生) + N(sum) + O(AJE) + P(RJE) + Q(audited)
 * - 使用 calcAuditedAmount / calcProportion / calcYoYChange / calcSubtotal
 * - 动态行增删（ElMessageBox.prompt命名后创建）+ 导入/导出支持
 * - 合计行联动审定表（存储 "K13-2-subtotal" 供CrossSheet使用）
 *
 * 科目：6711营业外支出（**损益类/借方科目**）
 * Item IDs: "K13-2-detail-rows", "K13-2-subtotal"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcProportion,
  calcYoYChange,
  calcSubtotal,
} from './useK13FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表行存储结构 */
export interface K13DetailRow {
  rowKey: string
  /** 序号 */
  seq: number
  // ─── 基础区段 ───
  /** 支出去向/项目名称 */
  project: string
  /** 支出类型 */
  expenseType: string
  /** 对方单位 */
  counterparty: string
  /** 金额（本期发生额） */
  amount: number
  /** 发生日期 */
  occurDate: string
  // ─── 月份列 B~M（12个月借方发生） ───
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
  /** 是否偶发/非经常性 */
  nonRecurring: boolean
  /** 交叉引用 */
  crossRef: string
  /** 占比（公式：本行审定/合计审定） */
  proportion: number | null
  /** 上期金额 */
  priorAmount: number
  /** 上期AJE */
  priorAje: number
  /** 上期RJE */
  priorRje: number
  /** 上期审定数（公式：上期金额+上期AJE+上期RJE） */
  priorAudited: number
  /** 上期占比 */
  priorProportion: number | null
  /** 同比变动率 */
  yoyChange: number | null
  // ─── 检查区段（由useK13Check管理）───
  /** 备注 */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
}

/** 区段Tab标识 */
export type K13DetailTabKey = 'basic' | 'analysis' | 'check'

export interface K13DetailSubtotal {
  amount: number
  monthTotal: number
  aje: number
  rje: number
  audited: number
  priorAmount: number
  priorAudited: number
}

export interface UseK13DetailParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'K13-2-detail-rows'
const ITEM_PREFIX = 'K13-2'

/** 3区段Tab配置 */
export const DETAIL_TABS: Array<{ key: K13DetailTabKey; label: string }> = [
  { key: 'basic', label: '基础信息' },
  { key: 'analysis', label: '分析' },
  { key: 'check', label: '检查' },
]

/** 支出类型选项（营业外支出6大类） */
export const EXPENSE_TYPE_OPTIONS = [
  '非流动资产处置损失',
  '捐赠支出',
  '罚款滞纳金',
  '债务重组损失',
  '资产盘亏损失',
  '其他',
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK13Detail(params: UseK13DetailParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K13DetailRow[]>([])
  const activeTab = ref<K13DetailTabKey>('basic')
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

  function _normalizeRow(raw: any, idx: number): K13DetailRow {
    const monthAmounts = Array.isArray(raw.monthAmounts) && raw.monthAmounts.length === 12
      ? raw.monthAmounts.map(parseNum)
      : Array(12).fill(0)
    const monthTotal = calcSubtotal(monthAmounts)
    const aje = parseNum(raw.aje)
    const rje = parseNum(raw.rje)
    const audited = calcAuditedAmount(monthTotal, aje, rje)
    const priorAmount = parseNum(raw.priorAmount)
    const priorAje = parseNum(raw.priorAje)
    const priorRje = parseNum(raw.priorRje)
    const priorAudited = calcAuditedAmount(priorAmount, priorAje, priorRje)
    const yoyChange = calcYoYChange(audited, priorAudited)

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seq: idx + 1,
      project: raw.project ?? '',
      expenseType: raw.expenseType ?? '',
      counterparty: raw.counterparty ?? '',
      amount: parseNum(raw.amount),
      occurDate: raw.occurDate ?? '',
      monthAmounts,
      monthTotal,
      aje,
      rje,
      audited,
      nonRecurring: raw.nonRecurring ?? false,
      crossRef: raw.crossRef ?? '',
      proportion: null, // 需要合计后重算
      priorAmount,
      priorAje,
      priorRje,
      priorAudited,
      priorProportion: null, // 需要合计后重算
      yoyChange,
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
    }
  }

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedRows: ComputedRef<K13DetailRow[]> = computed(() => {
    // 先计算合计审定数用于占比
    const allAudited = rows.value.map((row) => {
      const mt = calcSubtotal(row.monthAmounts)
      return calcAuditedAmount(mt, row.aje, row.rje)
    })
    const totalAudited = calcSubtotal(allAudited)

    // 上期合计用于上期占比
    const allPriorAudited = rows.value.map((row) => {
      return calcAuditedAmount(row.priorAmount, row.priorAje, row.priorRje)
    })
    const totalPriorAudited = calcSubtotal(allPriorAudited)

    return rows.value.map((row, idx) => {
      const monthTotal = calcSubtotal(row.monthAmounts)
      const audited = calcAuditedAmount(monthTotal, row.aje, row.rje)
      const proportion = calcProportion(audited, totalAudited)
      const priorAudited = calcAuditedAmount(row.priorAmount, row.priorAje, row.priorRje)
      const priorProportion = calcProportion(priorAudited, totalPriorAudited)
      const yoyChange = calcYoYChange(audited, priorAudited)
      return {
        ...row,
        seq: idx + 1,
        monthTotal,
        audited,
        proportion,
        priorAudited,
        priorProportion,
        yoyChange,
      }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const subtotal: ComputedRef<K13DetailSubtotal> = computed(() => {
    const detail = computedRows.value
    const amount = calcSubtotal(detail.map(r => r.amount))
    const monthTotal = calcSubtotal(detail.map(r => r.monthTotal))
    const aje = calcSubtotal(detail.map(r => r.aje))
    const rje = calcSubtotal(detail.map(r => r.rje))
    const audited = calcAuditedAmount(monthTotal, aje, rje)
    const priorAmount = calcSubtotal(detail.map(r => r.priorAmount))
    const priorAudited = calcSubtotal(detail.map(r => r.priorAudited))
    return { amount, monthTotal, aje, rje, audited, priorAmount, priorAudited }
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

  function _recalcRow(row: K13DetailRow): void {
    row.monthTotal = calcSubtotal(row.monthAmounts)
    row.audited = calcAuditedAmount(row.monthTotal, row.aje, row.rje)
    row.priorAudited = calcAuditedAmount(row.priorAmount, row.priorAje, row.priorRje)
    row.yoyChange = calcYoYChange(row.audited, row.priorAudited)
    // proportion在computed中重算（需合计值）
  }

  // ─── 动态行操作（ElMessageBox.prompt命名） ─────────────────────────────────

  function addRow(project: string, expenseType: string = ''): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seq: rows.value.length + 1,
      project,
      expenseType,
      counterparty: '',
      amount: 0,
      occurDate: '',
      monthAmounts: Array(12).fill(0),
      monthTotal: 0,
      aje: 0,
      rje: 0,
      audited: 0,
      nonRecurring: false,
      crossRef: '',
      proportion: null,
      priorAmount: 0,
      priorAje: 0,
      priorRje: 0,
      priorAudited: 0,
      priorProportion: null,
      yoyChange: null,
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

  function importRows(data: Array<Partial<K13DetailRow>>): void {
    if (isReadonly?.value) return
    const imported = data.map((r, idx) => _normalizeRow(r, rows.value.length + idx))
    rows.value.push(...imported)
    isChanged.value = true
    _persist()
  }

  function exportRows(): K13DetailRow[] {
    return computedRows.value
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
    // 同步审定合计供CrossSheet使用（K13-1↔K13-2交叉验证）
    onSave('K13-2-subtotal', subtotal.value.audited)
  }

  // ─── Tab切换 ──────────────────────────────────────────────────────────────

  function setActiveTab(tab: K13DetailTabKey): void {
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

export default useK13Detail
