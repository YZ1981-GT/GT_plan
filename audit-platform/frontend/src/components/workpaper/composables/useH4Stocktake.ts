/**
 * useH4Stocktake — H4-6 盘点检查表 composable
 *
 * 12列：序号 | 物资名称 | 规格 | 账面数量 | 账面金额 | 盘点数量 | 盘点金额
 *       | 差异数量 | 差异金额 | 存放位置 | 盘点日期 | 备注
 *
 * 功能：
 * - 差异计算: diffQty=countQty-bookQty; diffAmt=countAmt-bookAmt
 * - 差异高亮 flag（差异不为零时标记）
 * - Saves to "H4-6-rows"
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 3.4
 * Requirements: 7.1-7.3
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H4-6 盘点检查行 */
export interface H4StocktakeRow {
  rowId: string
  /** 序号 */
  seq: number
  /** 物资名称 */
  name: string
  /** 规格型号 */
  spec: string
  /** 账面数量 */
  bookQty: number
  /** 账面金额 */
  bookAmt: number
  /** 盘点数量 */
  countQty: number
  /** 盘点金额 */
  countAmt: number
  /** 差异数量（公式：=盘点数量-账面数量） */
  diffQty: number
  /** 差异金额（公式：=盘点金额-账面金额） */
  diffAmt: number
  /** 存放位置 */
  location: string
  /** 盘点日期 */
  countDate: string
  /** 备注 */
  remark: string
  /** 差异高亮标记（差异不为零时true） */
  hasDiff: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H4-6-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4Stocktake(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H4StocktakeRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any, idx: number): H4StocktakeRow {
    const bookQty = Number(raw.bookQty) || 0
    const bookAmt = Number(raw.bookAmt) || 0
    const countQty = Number(raw.countQty) || 0
    const countAmt = Number(raw.countAmt) || 0
    const diffQty = countQty - bookQty
    const diffAmt = countAmt - bookAmt

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      seq: raw.seq ?? idx + 1,
      name: raw.name ?? '',
      spec: raw.spec ?? '',
      bookQty,
      bookAmt,
      countQty,
      countAmt,
      diffQty,
      diffAmt,
      location: raw.location ?? '',
      countDate: raw.countDate ?? '',
      remark: raw.remark ?? '',
      hasDiff: Math.abs(diffQty) > 0 || Math.abs(diffAmt) > 0.01,
    }
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map((r, i) => _normalizeRow(r, i))
    } else {
      rows.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  /** 存在差异的行数 */
  const diffRowCount: ComputedRef<number> = computed(() =>
    rows.value.filter(r => r.hasDiff).length,
  )

  /** 总盘点笔数 */
  const totalCount: ComputedRef<number> = computed(() => rows.value.length)

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(name: string): void {
    if (!name?.trim()) return
    const seq = rows.value.length + 1
    rows.value.push(_normalizeRow({ name: name.trim(), seq }, seq - 1))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    // 文本字段
    if (['name', 'spec', 'location', 'countDate', 'remark'].includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    // 数值字段
    const numVal = Number(value) || 0
    switch (field) {
      case 'bookQty': row.bookQty = numVal; break
      case 'bookAmt': row.bookAmt = numVal; break
      case 'countQty': row.countQty = numVal; break
      case 'countAmt': row.countAmt = numVal; break
      default: return
    }

    // 重算差异
    row.diffQty = row.countQty - row.bookQty
    row.diffAmt = row.countAmt - row.bookAmt
    row.hasDiff = Math.abs(row.diffQty) > 0 || Math.abs(row.diffAmt) > 0.01

    _persist()
  }

  // ─── Save ──────────────────────────────────────────────────────────────────

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId,
      seq: r.seq,
      name: r.name,
      spec: r.spec,
      bookQty: r.bookQty,
      bookAmt: r.bookAmt,
      countQty: r.countQty,
      countAmt: r.countAmt,
      location: r.location,
      countDate: r.countDate,
      remark: r.remark,
    }))
    onSave(ROWS_KEY, toPersist)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    // Computed
    diffRowCount,
    totalCount,
    // Actions
    addRow,
    deleteRow,
    updateCell,
    save,
    load,
  }
}

export default useH4Stocktake
