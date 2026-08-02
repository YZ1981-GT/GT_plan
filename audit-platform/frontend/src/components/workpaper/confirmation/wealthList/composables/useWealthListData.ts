/**
 * useWealthListData — E0-6 理财产品发函记录表 数据核心 composable
 *
 * 职责：
 * - 从 htmlData 初始化（仅接受 `_format: 'wealth-list-v1'`，其余格式拒绝防误载）
 * - CRUD（addRow / deleteRows / updateField / importRows）
 * - 看板指标（含**汇总键缺失**与**已到期**两个源模板可判定的审计红线）
 * - 行质量状态（红/橙/正常）
 * - buildPayload
 *
 * 纯逻辑全部导出为独立函数，便于单测（不依赖 Vue 实例）。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type {
  WealthProductRow,
  WealthListMetrics,
  WealthListAuditNote,
  WealthListConclusion,
  WealthListPayload,
} from '../wealthListTypes'

function generateRowId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

/** 数值归一：非有限值一律当 0（防 NaN 进合计） */
export function toNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * E0-1 汇总键是否完整。
 * 源公式 `SUMIFS(E0-6!$H:$H, E0-6!$A:$A, E0-1!$B, E0-6!$D:$D, E0-1!$E)`
 * 需要 索引号(A) 与 产品名称(D) 同时非空，缺任一则该行金额汇总不到 E0-1。
 */
export function hasSummaryKey(row: WealthProductRow): boolean {
  return !!String(row.confirm_index ?? '').trim() && !!String(row.product_name ?? '').trim()
}

/**
 * 是否已到期（到期日 ≤ 报表截止日）。
 * 两端任一为空 → false（不猜测）。日期用 `YYYY-MM-DD` 字符串比较即可。
 */
export function isMatured(row: WealthProductRow): boolean {
  const maturity = String(row.maturity_date ?? '').trim()
  const cutoff = String(row.cutoff_date ?? '').trim()
  if (!maturity || !cutoff) return false
  return maturity <= cutoff
}

/** 是否受限（源 K 列 = 是） */
export function isRestricted(row: WealthProductRow): boolean {
  return row.restricted === '是'
}

/**
 * 行质量状态：
 * - 汇总键缺失 → danger（E0-1 拿不到金额，最严重且最隐蔽）
 * - 已到期 → warning（期末仍列示需核实）
 * - 金额为空/0 → warning（发函金额将为 0）
 * - 其余 → ok
 */
export function rowQualityStatus(row: WealthProductRow): 'ok' | 'warning' | 'danger' {
  const hasAnyContent =
    !!String(row.product_name ?? '').trim()
    || !!String(row.bank_and_recipient ?? '').trim()
    || toNum(row.net_value) !== 0
  // 完全空白的新行不打警示（用户刚点新增）
  if (!hasAnyContent) return 'ok'
  if (!hasSummaryKey(row)) return 'danger'
  if (isMatured(row)) return 'warning'
  if (toNum(row.net_value) === 0) return 'warning'
  return 'ok'
}

/** 看板指标（纯函数，便于单测与 PBT） */
export function buildWealthListMetrics(rows: WealthProductRow[]): WealthListMetrics {
  const list = rows ?? []
  let netTotal = 0
  let unitsTotal = 0
  let restrictedCount = 0
  let restrictedAmount = 0
  let maturedCount = 0
  let closedCount = 0
  let openCount = 0
  let missingKeyCount = 0
  let zeroAmountCount = 0

  for (const r of list) {
    const amt = toNum(r.net_value)
    netTotal += amt
    unitsTotal += toNum(r.units_held)
    if (isRestricted(r)) {
      restrictedCount += 1
      restrictedAmount += amt
    }
    if (isMatured(r)) maturedCount += 1
    if (r.product_type === '封闭式') closedCount += 1
    if (r.product_type === '开放式') openCount += 1
    if (!hasSummaryKey(r)) missingKeyCount += 1
    if (amt === 0) zeroAmountCount += 1
  }

  const round2 = (n: number) => Math.round(n * 100) / 100
  return {
    total_count: list.length,
    net_value_total: round2(netTotal),
    units_total: Math.round(unitsTotal * 10000) / 10000,
    restricted_count: restrictedCount,
    restricted_amount: round2(restrictedAmount),
    matured_count: maturedCount,
    closed_count: closedCount,
    open_count: openCount,
    missing_key_count: missingKeyCount,
    zero_amount_count: zeroAmountCount,
  }
}

export interface UseWealthListDataProps {
  htmlData: () => any
  readonly: boolean
  /** 项目报表截止日（新增行时预填，来自 render 的 project_context） */
  defaultCutoffDate?: () => string | undefined
}

export interface UseWealthListDataReturn {
  rows: Ref<WealthProductRow[]>
  auditNote: Ref<WealthListAuditNote>
  conclusion: Ref<WealthListConclusion>
  isDirty: Ref<boolean>
  addRow: () => WealthProductRow
  deleteRows: (ids: string[]) => void
  updateField: (rowId: string, field: string, value: any) => void
  importRows: (newRows: Partial<WealthProductRow>[]) => number
  metrics: ComputedRef<WealthListMetrics>
  getRowQualityStatus: (row: WealthProductRow) => 'ok' | 'warning' | 'danger'
  buildPayload: () => WealthListPayload
}

export function useWealthListData(props: UseWealthListDataProps): UseWealthListDataReturn {
  const rows = ref<WealthProductRow[]>([])
  const auditNote = ref<WealthListAuditNote>({})
  const conclusion = ref<WealthListConclusion>({})
  const isDirty = ref(false)

  function ensureRowId(row: WealthProductRow): WealthProductRow {
    return row._row_id ? row : { ...row, _row_id: generateRowId() }
  }

  function initFromHtmlData(data: any) {
    if (!data || data._format !== 'wealth-list-v1') {
      rows.value = []
      auditNote.value = {}
      conclusion.value = {}
      return
    }
    rows.value = Array.isArray(data.rows) ? data.rows.map(ensureRowId) : []
    auditNote.value = data.audit_note ?? {}
    conclusion.value = data.conclusion ?? {}
    isDirty.value = false
  }

  initFromHtmlData(props.htmlData())

  watch(
    () => props.htmlData(),
    (newData) => { initFromHtmlData(newData) },
    { deep: true },
  )

  function nextSeq(): number {
    return rows.value.reduce((max, r) => Math.max(max, r.seq ?? 0), 0) + 1
  }

  function addRow(): WealthProductRow {
    const newRow: WealthProductRow = {
      _row_id: generateRowId(),
      seq: nextSeq(),
      cutoff_date: props.defaultCutoffDate?.() || undefined,
      currency: '人民币',
      restricted: '否',
      units_held: null,
      net_value: null,
      _source: 'manual',
    }
    rows.value.push(newRow)
    isDirty.value = true
    return newRow
  }

  function deleteRows(ids: string[]) {
    if (!ids?.length) return
    const idSet = new Set(ids)
    rows.value = rows.value.filter((r) => !idSet.has(r._row_id!))
    isDirty.value = true
  }

  function updateField(rowId: string, field: string, value: any) {
    const row = rows.value.find((r) => r._row_id === rowId)
    if (!row) return
    ;(row as any)[field] = value
    isDirty.value = true
  }

  /** 导入：按「索引号 + 产品名称」二元键去重（对齐源模板汇总键） */
  function importRows(newRows: Partial<WealthProductRow>[]): number {
    const keyOf = (r: Partial<WealthProductRow>) =>
      `${String(r.confirm_index ?? '').trim()}||${String(r.product_name ?? '').trim()}`
    const existing = new Set(rows.value.filter(hasSummaryKey).map(keyOf))
    const accepted: WealthProductRow[] = []
    for (const r of newRows ?? []) {
      // 只有键完整的行才参与去重判定；键不全的行照常导入（后续由红色告警提示补全）
      if (hasSummaryKey(r as WealthProductRow) && existing.has(keyOf(r))) continue
      if (hasSummaryKey(r as WealthProductRow)) existing.add(keyOf(r))
      accepted.push({
        ...r,
        _row_id: generateRowId(),
        _source: r._source || 'import',
      } as WealthProductRow)
    }
    const base = rows.value.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    accepted.forEach((r, i) => { r.seq = base + i + 1 })
    rows.value.push(...accepted)
    if (accepted.length) isDirty.value = true
    return accepted.length
  }

  const metrics = computed<WealthListMetrics>(() => buildWealthListMetrics(rows.value))

  function buildPayload(): WealthListPayload {
    return {
      _format: 'wealth-list-v1',
      rows: rows.value.map((r) => ({ ...r })),
      audit_note: auditNote.value,
      conclusion: conclusion.value,
    }
  }

  return {
    rows,
    auditNote,
    conclusion,
    isDirty,
    addRow,
    deleteRows,
    updateField,
    importRows,
    metrics,
    getRowQualityStatus: rowQualityStatus,
    buildPayload,
  }
}
