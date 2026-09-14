/**
 * useK9Detail — K9-2 明细表逻辑（55行×25列→3区段Tab管理）
 *
 * Spec: .kiro/specs/k9-admin-expenses/
 * Task: 3.4
 * Requirements: 3.1-3.4
 *
 * 职责：
 * - 55行明细费用科目管理（从tb_ledger明细科目取发生额）
 * - 25列拆3区段Tab：基础(序号/明细科目/本期发生/上期发生) | 分析(同比/占收入比/波动说明) | 检查(凭证抽查/核查结论/备注)
 * - 动态行增删（新增费用明细科目）
 * - 合计行联动审定表K9-1
 * - tb_ledger 明细科目取数（发生额明细）
 * - computed: 月度汇总、分类合计
 *
 * Item IDs: "K9-2-row-{idx}-{field}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcSubtotal,
  calcIncomeStatementOccurrence,
} from './useK9FormulaEngine'
import { calcYoYChange, calcRatioToRevenue } from './useK9AnalysisEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表行存储结构 */
export interface K9DetailRow {
  rowKey: string
  /** 明细科目编码 */
  accountCode: string
  /** 明细科目名称 */
  accountName: string
  /** 月度金额 1-12月 */
  months: number[]
  /** 本期未审合计（公式：SUM(months)） */
  unadjTotal: number
  /** AJE调整 */
  aje: number
  /** RJE重分类 */
  rje: number
  /** 审定数（公式：未审+AJE+RJE） */
  audited: number
  /** 上期发生额 */
  priorAmount: number
  /** 同比变动率（公式列） */
  yoyChangeRate: number | null
  /** 占营业收入比（公式列） */
  ratioToRevenue: number | null
  /** 波动说明 */
  fluctuationNote: string
  /** 凭证抽查结论 */
  voucherCheckResult: string
  /** 核查结论 */
  inspectionConclusion: string
  /** 备注 */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
}

/** 区段Tab标识 */
export type K9DetailTabKey = 'basic' | 'analysis' | 'inspection'

export interface K9DetailSubtotal {
  months: number[]
  unadjTotal: number
  aje: number
  rje: number
  audited: number
  priorAmount: number
}

export interface UseK9DetailParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  /** 营业收入（来自外部输入或CrossSheet） */
  revenue?: Ref<number>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'K9-2-detail-rows'
const ITEM_PREFIX = 'K9-2'

/** 3区段Tab配置 */
export const DETAIL_TABS: Array<{ key: K9DetailTabKey; label: string }> = [
  { key: 'basic', label: '基础信息' },
  { key: 'analysis', label: '分析' },
  { key: 'inspection', label: '检查' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK9Detail(params: UseK9DetailParams) {
  const { allResponses, projectId, wpId, revenue, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K9DetailRow[]>([])
  const activeTab = ref<K9DetailTabKey>('basic')
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const raw = _getJson(ROWS_KEY)
    if (Array.isArray(raw) && raw.length > 0) {
      rows.value = raw.map(_normalizeRow)
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

  function _normalizeRow(raw: any): K9DetailRow {
    const months = Array.isArray(raw.months)
      ? raw.months.map((v: any) => parseNum(v))
      : new Array(12).fill(0)
    const unadjTotal = calcSubtotal(months)
    const aje = parseNum(raw.aje)
    const rje = parseNum(raw.rje)
    const audited = calcAuditedAmount(unadjTotal, aje, rje)
    const priorAmount = parseNum(raw.priorAmount)
    const rev = revenue?.value ?? 0
    const yoyChangeRate = calcYoYChange(audited, priorAmount)
    const ratioToRevenue = calcRatioToRevenue(audited, rev)

    return {
      rowKey: raw.rowKey ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      accountCode: raw.accountCode ?? '',
      accountName: raw.accountName ?? '',
      months, unadjTotal, aje, rje, audited, priorAmount,
      yoyChangeRate, ratioToRevenue,
      fluctuationNote: raw.fluctuationNote ?? '',
      voucherCheckResult: raw.voucherCheckResult ?? '',
      inspectionConclusion: raw.inspectionConclusion ?? '',
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
    }
  }

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedRows: ComputedRef<K9DetailRow[]> = computed(() => {
    const rev = revenue?.value ?? 0
    return rows.value.map((row) => {
      const unadjTotal = calcSubtotal(row.months)
      const audited = calcAuditedAmount(unadjTotal, row.aje, row.rje)
      const yoyChangeRate = calcYoYChange(audited, row.priorAmount)
      const ratioToRevenue = calcRatioToRevenue(audited, rev)
      return { ...row, unadjTotal, audited, yoyChangeRate, ratioToRevenue }
    })
  })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const subtotal: ComputedRef<K9DetailSubtotal> = computed(() => {
    const detail = computedRows.value
    const months = Array.from({ length: 12 }, (_, i) =>
      calcSubtotal(detail.map(r => r.months[i] ?? 0)),
    )
    const unadjTotal = calcSubtotal(months)
    const aje = calcSubtotal(detail.map(r => r.aje))
    const rje = calcSubtotal(detail.map(r => r.rje))
    const audited = calcAuditedAmount(unadjTotal, aje, rje)
    const priorAmount = calcSubtotal(detail.map(r => r.priorAmount))
    return { months, unadjTotal, aje, rje, audited, priorAmount }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: any): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row || !row.isEditable) return

    if (field.startsWith('month-')) {
      const monthIdx = parseInt(field.replace('month-', ''), 10)
      if (monthIdx >= 0 && monthIdx < 12) {
        row.months[monthIdx] = parseNum(value)
      }
    } else {
      ;(row as any)[field] = value
    }
    _recalcRow(row)
    isChanged.value = true
    _persist()
  }

  function _recalcRow(row: K9DetailRow): void {
    row.unadjTotal = calcSubtotal(row.months)
    row.audited = calcAuditedAmount(row.unadjTotal, row.aje, row.rje)
    const rev = revenue?.value ?? 0
    row.yoyChangeRate = calcYoYChange(row.audited, row.priorAmount)
    row.ratioToRevenue = calcRatioToRevenue(row.audited, rev)
  }

  // ─── 动态行操作 ────────────────────────────────────────────────────────────

  function addRow(accountName: string, accountCode: string = ''): void {
    if (isReadonly?.value) return
    rows.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      accountCode, accountName,
      months: new Array(12).fill(0),
      unadjTotal: 0, aje: 0, rje: 0, audited: 0,
      priorAmount: 0, yoyChangeRate: null, ratioToRevenue: null,
      fluctuationNote: '', voucherCheckResult: '', inspectionConclusion: '',
      remark: '', isEditable: true,
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

  /**
   * 从 I1-9 摊销分配回填「无形资产摊销」行未审发生额（写入 12 月以保持 SUM(months)）。
   */
  function applyI1AmortAmount(amount: number, keywords: string[] = ['无形资产摊销']): {
    ok: boolean
    message: string
  } {
    if (isReadonly?.value) return { ok: false, message: '只读' }
    const hit = rows.value.find((r) =>
      keywords.some((k) => String(r.accountName || '').includes(k)),
    )
    if (!hit) {
      return { ok: false, message: '未找到「无形资产摊销」明细行，请先新增该科目' }
    }
    const months = new Array(12).fill(0)
    months[11] = amount
    hit.months = months
    _recalcRow(hit)
    isChanged.value = true
    _persist()
    return { ok: true, message: `已回填「${hit.accountName}」= ${amount.toFixed(2)}` }
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
    // 同步审定合计供CrossSheet使用
    onSave('K9-2-detail-audited-total', subtotal.value.audited)
  }

  // ─── Tab切换 ──────────────────────────────────────────────────────────────

  function setActiveTab(tab: K9DetailTabKey): void {
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
    addRow,
    removeRow,
    applyI1AmortAmount,
    setActiveTab,
    computeAll,
    initFromResponses,
  }
}

export default useK9Detail
