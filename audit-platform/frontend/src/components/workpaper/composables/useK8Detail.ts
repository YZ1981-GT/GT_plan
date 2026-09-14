/**
 * useK8Detail — K8-2 明细表逻辑（48行×27列→3区段Tab管理）
 *
 * Spec: .kiro/specs/k8-selling-expenses/
 * Task: 3.4
 * Requirements: 3.1-3.4
 *
 * 职责：
 * - 48行明细费用科目管理（从tb_ledger明细科目取发生额）
 * - 27列拆3区段Tab：基础(序号/明细科目/本期发生/上期发生) | 分析(同比/占收入比/波动说明) | 检查(凭证抽查/核查结论/备注)
 * - Monthly columns (1-12) + subtotal + AJE + RJE + audited
 * - 动态行增删（新增费用明细科目）
 * - 合计行联动审定表K8-1
 * - tb_ledger 明细科目取数
 *
 * Item IDs: "K8-2-row-{idx}-{field}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcSubtotal,
  calcIncomeStatementOccurrence,
} from './useK8FormulaEngine'
import { calcYoYChange, calcRatioToRevenue } from './useK8AnalysisEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 明细表行存储结构 */
export interface K8DetailRow {
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
  /** 与相关科目勾稽（索引号），对齐源模板 K8-2 S 列 */
  crossRefIndex: string
  /** 各项目占比（公式：审定数/审定合计），对齐源模板 R 列 */
  ratioToTotal: number | null
  /** 上期各项目占比（对齐源模板 X 列） */
  priorRatioToTotal: number | null
  /** 各项目占比变动（本期占比−上期占比，对齐源模板 Y 列） */
  ratioChange: number | null
  /** 凭证抽查结论（保留兼容，UI 已不展示） */
  voucherCheckResult: string
  /** 核查结论（保留兼容，UI 已不展示） */
  inspectionConclusion: string
  /** 备注 */
  remark: string
  /** 可编辑标记 */
  isEditable: boolean
}

/** 区段Tab标识（对齐源模板：月度构成 / 审定与占比 / 同比分析） */
export type K8DetailTabKey = 'month' | 'audit' | 'analysis'

export interface K8DetailSubtotal {
  months: number[]
  unadjTotal: number
  aje: number
  rje: number
  audited: number
  priorAmount: number
}

export interface UseK8DetailParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  /** 营业收入（来自外部输入或CrossSheet） */
  revenue?: Ref<number>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'K8-2-detail-rows'
const ITEM_PREFIX = 'K8-2'

/** 3区段Tab配置（对齐源模板 K8-2：月度构成 / 审定与占比 / 同比分析） */
export const DETAIL_TABS: Array<{ key: K8DetailTabKey; label: string }> = [
  { key: 'month', label: '月度构成' },
  { key: 'audit', label: '审定与占比' },
  { key: 'analysis', label: '同比分析' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK8Detail(params: UseK8DetailParams) {
  const { allResponses, projectId, wpId, revenue, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K8DetailRow[]>([])
  const activeTab = ref<K8DetailTabKey>('basic')
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

  function _normalizeRow(raw: any): K8DetailRow {
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
      months,
      unadjTotal,
      aje,
      rje,
      audited,
      priorAmount,
      yoyChangeRate,
      ratioToRevenue,
      fluctuationNote: raw.fluctuationNote ?? '',
      crossRefIndex: raw.crossRefIndex ?? '',
      ratioToTotal: null,
      priorRatioToTotal: null,
      ratioChange: null,
      voucherCheckResult: raw.voucherCheckResult ?? '',
      inspectionConclusion: raw.inspectionConclusion ?? '',
      remark: raw.remark ?? '',
      isEditable: raw.isEditable ?? true,
    }
  }

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedRows: ComputedRef<K8DetailRow[]> = computed(() => {
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

  const subtotal: ComputedRef<K8DetailSubtotal> = computed(() => {
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

  // ─── Computed: 带各项目占比的完整行（对齐源模板 R/X/Y 列）────────────────────
  // ratioToTotal 依赖 subtotal.audited，故单独二次 map，避免与 subtotal 循环依赖
  const rowsWithRatio: ComputedRef<K8DetailRow[]> = computed(() => {
    const totalAudited = subtotal.value.audited
    const totalPrior = subtotal.value.priorAmount
    return computedRows.value.map((row) => {
      const ratioToTotal = totalAudited === 0 ? null : row.audited / totalAudited
      const priorRatioToTotal = totalPrior === 0 ? null : row.priorAmount / totalPrior
      const ratioChange =
        ratioToTotal == null || priorRatioToTotal == null ? null : ratioToTotal - priorRatioToTotal
      return { ...row, ratioToTotal, priorRatioToTotal, ratioChange }
    })
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

  function _recalcRow(row: K8DetailRow): void {
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
      accountCode,
      accountName,
      months: new Array(12).fill(0),
      unadjTotal: 0, aje: 0, rje: 0, audited: 0,
      priorAmount: 0, yoyChangeRate: null, ratioToRevenue: null,
      fluctuationNote: '', crossRefIndex: '',
      ratioToTotal: null, priorRatioToTotal: null, ratioChange: null,
      voucherCheckResult: '', inspectionConclusion: '',
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

  /** 从序时账按月取数结果回填：按明细科目名匹配填月度，无则新增行 */
  function applyMonthlyRows(monthly: Array<{ accountName: string; months: number[] }>): {
    ok: boolean
    message: string
  } {
    if (isReadonly?.value) return { ok: false, message: '只读' }
    if (!Array.isArray(monthly) || monthly.length === 0) return { ok: false, message: '无月度数据' }
    let filled = 0
    let added = 0
    for (const m of monthly) {
      const name = (m.accountName || '').trim()
      if (!name) continue
      const months = new Array(12).fill(0).map((_, i) => parseNum(m.months?.[i] ?? 0))
      const existing = rows.value.find(r => r.accountName === name)
      if (existing) {
        existing.months = months
        _recalcRow(existing)
        filled++
      } else {
        rows.value.push(_normalizeRow({
          rowKey: `row-${name}-${Math.random().toString(36).slice(2, 6)}`,
          accountName: name,
          months,
        }))
        added++
      }
    }
    isChanged.value = true
    _persist()
    return { ok: true, message: `序时账取数：回填 ${filled} 行、新增 ${added} 行月度发生额` }
  }

  /** 从 I1-9 回填无形资产摊销（写入 12 月） */
  function applyI1AmortAmount(amount: number, keywords: string[] = ['无形资产摊销', '折旧及摊销']): {
    ok: boolean
    message: string
  } {
    if (isReadonly?.value) return { ok: false, message: '只读' }
    const hit = rows.value.find((r) =>
      keywords.some((k) => String(r.accountName || '').includes(k)),
    )
    if (!hit) {
      return { ok: false, message: '未找到「无形资产摊销/折旧及摊销」明细行' }
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
    onSave('K8-2-detail-audited-total', subtotal.value.audited)
  }

  // ─── Tab切换 ──────────────────────────────────────────────────────────────

  function setActiveTab(tab: K8DetailTabKey): void {
    activeTab.value = tab
  }

  // ─── 全量重算 ──────────────────────────────────────────────────────────────

  function computeAll(): void {
    for (const row of rows.value) _recalcRow(row)
    _persist()
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows: rowsWithRatio,
    subtotal,
    activeTab,
    isChanged,
    updateCell,
    addRow,
    removeRow,
    applyMonthlyRows,
    applyI1AmortAmount,
    setActiveTab,
    computeAll,
    initFromResponses,
  }
}

export default useK8Detail
