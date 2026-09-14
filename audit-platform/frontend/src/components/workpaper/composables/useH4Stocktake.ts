/**
 * useH4Stocktake — H4-6 盘点检查表 composable
 *
 * 致同五段式 + 双向抽盘 + 三数量勾稽 + H4-2 跨表联动 + H4-7 减值关注推送
 * 兼容旧版「账面 vs 盘点」两数量行结构
 */
import { ref, computed, watch, inject, type Ref, type ComputedRef } from 'vue'
import {
  applyQtySideEffects,
  calcDirectionCoverage,
  calcStocktakeStats,
  collectStocktakeImpairmentConcerns,
  createEmptyCheckMeta,
  createEmptyCheckRow,
  draftCheckSheetConclusion,
  draftCheckSheetNote,
  ITEM_H47_STOCKTAKE_CONCERNS,
  mapH42RowsToCheckRows,
  normalizeCheckMeta,
  normalizeCheckRow,
  sumH42EndAmount,
  type H4StocktakeCheckMeta,
  type H4StocktakeCheckRow,
  type StocktakeDirection,
} from './h4StocktakeCheckModel'
import { H46_AJE_MARKER, pushDraftPairsToH43 } from './h4AdjustmentDraftPush'

const ROWS_KEY = 'H4-6-rows'
const META_KEY = 'H4-6-stocktake-meta'
const NOTE_KEY = 'H4-6-note'
const CONCLUSION_KEY = 'H4-6-conclusion'
const H42_ROWS_KEY = 'H4-2-rows'

function _parseRows(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  return []
}

function _getJson(map: Map<string, any>, itemId: string): any {
  const item = map.get(itemId)
  if (!item) return null
  const raw = item.remark ?? item.conclusion
  if (!raw) return null
  if (typeof raw !== 'string') return raw
  try { return JSON.parse(raw) } catch { return raw }
}

export function useH4Stocktake(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', () => {})

  const rows = ref<H4StocktakeCheckRow[]>([])
  const meta = ref<H4StocktakeCheckMeta>(createEmptyCheckMeta())
  const auditNote = ref('')
  const auditConclusion = ref('')

  function _persist(itemId: string, value: any): void {
    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    allResponses.value.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
    if (onSave) onSave(itemId, value)
    else saveResponse(itemId, value)
  }

  function loadAll(): void {
    const data = _getJson(allResponses.value, ROWS_KEY)
    rows.value = _parseRows(data).map((r, i) => {
      const row = normalizeCheckRow(r, i)
      applyQtySideEffects(row)
      return row
    })
    meta.value = normalizeCheckMeta(_getJson(allResponses.value, META_KEY))
    const n = allResponses.value.get(NOTE_KEY)
    if (n?.remark != null) auditNote.value = String(n.remark)
    const c = allResponses.value.get(CONCLUSION_KEY)
    if (c?.remark != null) auditConclusion.value = String(c.remark)
  }

  function _persistRows(): void {
    _persist(ROWS_KEY, rows.value.map((r) => ({
      rowId: r.rowId,
      seq: r.seq,
      direction: r.direction,
      name: r.name,
      assetNo: r.assetNo,
      spec: r.spec,
      unit: r.unit,
      location: r.location,
      unitPrice: r.unitPrice,
      bookQty: r.bookQty,
      bookAmount: r.bookAmount,
      // 旧字段兼容写出，便于导入导出旧模板仍可读
      bookAmt: r.bookAmount,
      clientCountQty: r.clientCountQty,
      sampleQty: r.sampleQty,
      countQty: r.sampleQty,
      countAmt: r.unitPrice && r.sampleQty ? r.unitPrice * r.sampleQty : undefined,
      qualityStatus: r.qualityStatus,
      result: r.result,
      diffReason: r.diffReason,
      diffAmount: r.diffAmount,
      remark: r.remark,
      countDate: r.countDate,
    })))
  }

  function _persistMeta(): void {
    _persist(META_KEY, meta.value)
  }

  function updateMeta<K extends keyof H4StocktakeCheckMeta>(
    key: K,
    value: H4StocktakeCheckMeta[K],
  ): void {
    meta.value = { ...meta.value, [key]: value }
    _persistMeta()
  }

  function _renumber(): void {
    let b = 0
    let f = 0
    for (const r of rows.value) {
      if (r.direction === 'floorToBook') {
        f++
        r.seq = f
      } else {
        b++
        r.seq = b
      }
    }
  }

  function addRow(direction: StocktakeDirection = 'bookToFloor', name = ''): void {
    const dirRows = rows.value.filter((r) =>
      direction === 'floorToBook' ? r.direction === 'floorToBook' : r.direction !== 'floorToBook',
    )
    rows.value.push(createEmptyCheckRow(direction, dirRows.length + 1, name))
    _renumber()
    _persistRows()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value.splice(idx, 1)
    _renumber()
    _persistRows()
  }

  /** @deprecated 兼容旧 API */
  function deleteRow(rowId: string): void {
    removeRow(rowId)
  }

  function updateRow(rowId: string, patch: Partial<H4StocktakeCheckRow>): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    Object.assign(row, patch)
    applyQtySideEffects(row)
    _persistRows()
  }

  /** @deprecated 兼容旧 API：按字段更新 */
  function updateCell(rowId: string, field: string, value: any): void {
    const map: Record<string, string> = {
      bookAmt: 'bookAmount',
      countQty: 'sampleQty',
      countAmt: 'diffAmount',
    }
    const key = (map[field] ?? field) as keyof H4StocktakeCheckRow
    updateRow(rowId, { [key]: value } as Partial<H4StocktakeCheckRow>)
  }

  function saveAuditNote(val?: string): void {
    if (val != null) auditNote.value = val
    _persist(NOTE_KEY, auditNote.value)
  }

  function saveAuditConclusion(val?: string): void {
    if (val != null) auditConclusion.value = val
    _persist(CONCLUSION_KEY, auditConclusion.value)
  }

  function _getH42Rows(): any[] {
    return _parseRows(_getJson(allResponses.value, H42_ROWS_KEY))
  }

  function importFromH42(opts?: {
    overwrite?: boolean
    direction?: StocktakeDirection
    maxRows?: number
  }): { added: number; message: string } {
    const detail = _getH42Rows()
    if (!detail.length) {
      return { added: 0, message: 'H4-2 明细暂无物资，请先编制明细表' }
    }
    const direction = opts?.direction ?? 'bookToFloor'
    const incoming = mapH42RowsToCheckRows(detail, {
      direction,
      maxRows: opts?.maxRows ?? 50,
    })
    if (opts?.overwrite) {
      const keep = rows.value.filter((r) =>
        direction === 'floorToBook' ? r.direction !== 'floorToBook' : r.direction === 'floorToBook',
      )
      rows.value = [...keep, ...incoming]
      _renumber()
      _persistRows()
      return {
        added: incoming.length,
        message: `已从 H4-2 覆盖带入 ${incoming.length} 项（${direction === 'floorToBook' ? '实物→账面' : '账面→实物'}）`,
      }
    }
    const existing = new Set(
      rows.value
        .filter((r) =>
          direction === 'floorToBook' ? r.direction === 'floorToBook' : r.direction !== 'floorToBook',
        )
        .map((r) => r.name.trim().toLowerCase()),
    )
    let added = 0
    for (const row of incoming) {
      const key = row.name.trim().toLowerCase()
      if (!key || existing.has(key)) continue
      rows.value.push(row)
      existing.add(key)
      added++
    }
    _renumber()
    _persistRows()
    return {
      added,
      message: added
        ? `已从 H4-2 新增 ${added} 项（${direction === 'floorToBook' ? '实物→账面' : '账面→实物'}，大额优先）`
        : 'H4-2 物资均已存在于本方向表，未新增',
    }
  }

  function syncTotalBookCost(): { ok: boolean; amount: number; message: string } {
    const detail = _getH42Rows()
    const amount = sumH42EndAmount(detail)
    if (amount <= 0) {
      return { ok: false, amount: 0, message: 'H4-2 明细暂无可用期末余额' }
    }
    updateMeta('totalBookCost', amount)
    if (!meta.value.testPopulation) {
      updateMeta(
        'testPopulation',
        `期末工程物资共 ${detail.length} 项，余额合计 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元`,
      )
    }
    return {
      ok: true,
      amount,
      message: `已同步期末余额 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元`,
    }
  }

  const bookToFloorRows = computed(() =>
    rows.value.filter((r) => r.direction !== 'floorToBook'),
  )
  const floorToBookRows = computed(() =>
    rows.value.filter((r) => r.direction === 'floorToBook'),
  )
  const bookToFloorCoverage = computed(() =>
    calcDirectionCoverage(bookToFloorRows.value as any, meta.value.totalBookCost),
  )
  const floorToBookCoverage = computed(() =>
    calcDirectionCoverage(floorToBookRows.value as any, meta.value.totalBookCost),
  )
  const stats = computed(() => calcStocktakeStats(rows.value))

  /** 兼容旧 UI：差异行数 / 总笔数 */
  const diffRowCount: ComputedRef<number> = computed(() => stats.value.varianceCount)
  const totalCount: ComputedRef<number> = computed(() => stats.value.total)

  function draftNote(): void {
    saveAuditNote(draftCheckSheetNote({
      stats: stats.value,
      meta: meta.value,
      bookToFloorCoverage: bookToFloorCoverage.value,
      floorToBookCoverage: floorToBookCoverage.value,
    }))
  }

  function draftConclusion(): void {
    saveAuditConclusion(draftCheckSheetConclusion({
      stats: stats.value,
      bookToFloorCoverage: bookToFloorCoverage.value,
      floorToBookCoverage: floorToBookCoverage.value,
      meta: meta.value,
    }))
  }

  function concernCount(): number {
    return stats.value.concernCount
  }

  function pushImpairmentConcernsToH47(): { concernCount: number; message: string } {
    const concerns = collectStocktakeImpairmentConcerns(rows.value)
    if (!concerns.length) {
      return { concernCount: 0, message: '未发现需推送的减值关注（闲置/积压/毁损/盘亏）' }
    }
    _persist(ITEM_H47_STOCKTAKE_CONCERNS, {
      updatedAt: new Date().toISOString(),
      items: concerns,
    })
    return {
      concernCount: concerns.length,
      message: `已推送 ${concerns.length} 项减值关注至 H4-7`,
    }
  }

  /**
   * 盘盈/盘亏差异 → H4-3：
   * 盘亏：借营业外支出 / 贷工程物资；盘盈：借工程物资 / 贷营业外收入
   */
  function pushAjeDraftToH43(): { ok: boolean; added: number; amount: number; message: string } {
    const targets = rows.value.filter(
      (r) => r.result === '盘盈' || r.result === '盘亏',
    )
    if (!targets.length) {
      return { ok: false, added: 0, amount: 0, message: '无盘盈/盘亏行可推送' }
    }
    const pairs = targets.map((r) => {
      const amt = Math.abs(r.diffAmount) > 0.01
        ? Math.abs(r.diffAmount)
        : Math.abs(r.bookAmount)
      const name = (r.name || '工程物资').trim()
      if (r.result === '盘亏') {
        return {
          description: `盘点盘亏拟调整-${name}`,
          amount: amt,
          debitCode: '5301',
          debitName: '营业外支出',
          creditCode: '1605',
          creditName: '工程物资',
          reportItemDebit: '营业外支出',
          reportItemCredit: '工程物资',
          indexRef: 'H4-6',
          marker: H46_AJE_MARKER,
        }
      }
      return {
        description: `盘点盘盈拟调整-${name}`,
        amount: amt,
        debitCode: '1605',
        debitName: '工程物资',
        creditCode: '6301',
        creditName: '营业外收入',
        reportItemDebit: '工程物资',
        reportItemCredit: '营业外收入',
        indexRef: 'H4-6',
        marker: H46_AJE_MARKER,
      }
    }).filter((p) => p.amount >= 0.005)
    return pushDraftPairsToH43({
      allResponses: allResponses.value,
      marker: H46_AJE_MARKER,
      pairs,
      onSave: (itemId, value) => _persist(itemId, value),
    })
  }

  function save(): void {
    _persistRows()
    _persistMeta()
  }

  watch(allResponses, () => loadAll(), { immediate: true })

  return {
    rows,
    meta,
    auditNote,
    auditConclusion,
    stats,
    bookToFloorRows,
    floorToBookRows,
    bookToFloorCoverage,
    floorToBookCoverage,
    diffRowCount,
    totalCount,
    addRow,
    removeRow,
    deleteRow,
    updateRow,
    updateCell,
    updateMeta,
    saveAuditNote,
    saveAuditConclusion,
    importFromH42,
    syncTotalBookCost,
    draftNote,
    draftConclusion,
    concernCount,
    pushImpairmentConcernsToH47,
    pushAjeDraftToH43,
    save,
    load: loadAll,
    loadAll,
  }
}

/** @deprecated 旧接口类型别名 */
export type H4StocktakeRow = H4StocktakeCheckRow

export default useH4Stocktake
