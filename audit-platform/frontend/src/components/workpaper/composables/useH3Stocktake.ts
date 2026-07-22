/**
 * useH3Stocktake — H3-9 盘点检查 composable
 *
 * 致同五段式 + 双向抽盘 + 三数量勾稽 + IR 专用列 + H3-2 跨表联动
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import {
  collectStocktakeImpairmentConcerns,
  ITEM_H310_STOCKTAKE_CONCERNS,
} from './h3ImpairmentCrossSheet'
import {
  applyQtySideEffects,
  calcDirectionCoverage,
  calcStocktakeStats,
  createEmptyCheckMeta,
  createEmptyCheckRow,
  draftCheckSheetConclusion,
  draftCheckSheetNote,
  mapH32RowsToCheckRows,
  normalizeCheckMeta,
  normalizeCheckRow,
  sumH32BookAmount,
  type H3StocktakeCheckMeta,
  type H3StocktakeCheckRow,
  type StocktakeDirection,
} from './h3StocktakeCheckModel'

const ROWS_KEY = 'H3-9-stocktake-rows'
const META_KEY = 'H3-9-stocktake-meta'
const NOTE_KEY = 'H3-9-audit-note'
const CONCLUSION_KEY = 'H3-9-audit-conclusion'
const H32_COST_KEY = 'H3-2-cost-rows'
const H32_FAIR_KEY = 'H3-2-fair-rows'

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

export function useH3Stocktake(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  measurementModel: Ref<'cost' | 'fair_value'>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, measurementModel, getValue, setValue, saveImmediate } = params

  const rows = ref<H3StocktakeCheckRow[]>([])
  const meta = ref<H3StocktakeCheckMeta>(createEmptyCheckMeta())
  const auditNote = ref('')
  const auditConclusion = ref('')

  function loadAll(): void {
    const rawRows = getValue(ROWS_KEY)
    rows.value = _parseRows(rawRows).map((r, i) => normalizeCheckRow(r, i))
    meta.value = normalizeCheckMeta(getValue(META_KEY))
    const n = allResponses.value.get(NOTE_KEY)
    auditNote.value = n?.remark ?? ''
    const c = allResponses.value.get(CONCLUSION_KEY)
    auditConclusion.value = c?.remark ?? ''
  }

  function _persistRows(): void { setValue(ROWS_KEY, rows.value) }
  function _persistMeta(): void { setValue(META_KEY, meta.value) }

  function updateMeta<K extends keyof H3StocktakeCheckMeta>(key: K, value: H3StocktakeCheckMeta[K]): void {
    meta.value = { ...meta.value, [key]: value }
    _persistMeta()
  }

  function addRow(direction: StocktakeDirection = 'bookToFloor', assetName = ''): void {
    const dirRows = rows.value.filter((r) =>
      direction === 'floorToBook' ? r.direction === 'floorToBook' : r.direction !== 'floorToBook',
    )
    rows.value.push(createEmptyCheckRow(direction, dirRows.length + 1, assetName))
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

  function updateRow(rowId: string, patch: Partial<H3StocktakeCheckRow>): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    Object.assign(row, patch)
    applyQtySideEffects(row)
    _persistRows()
  }

  function saveAuditNote(val: string): void {
    auditNote.value = val
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    void saveImmediate(NOTE_KEY, val)
  }

  function saveAuditConclusion(val: string): void {
    auditConclusion.value = val
    allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
    void saveImmediate(CONCLUSION_KEY, val)
  }

  function _getH32Rows(): any[] {
    const key = measurementModel.value === 'fair_value' ? H32_FAIR_KEY : H32_COST_KEY
    return _parseRows(getValue(key))
  }

  function importFromH32(opts?: {
    overwrite?: boolean
    direction?: StocktakeDirection
    maxRows?: number
  }): { added: number; message: string } {
    const detail = _getH32Rows()
    if (!detail.length) {
      return { added: 0, message: 'H3-2 明细暂无资产，请先编制明细表' }
    }
    const direction = opts?.direction ?? 'bookToFloor'
    const incoming = mapH32RowsToCheckRows(detail, {
      measurementModel: measurementModel.value,
      direction,
      maxRows: opts?.maxRows ?? 50,
    })
    if (opts?.overwrite) {
      // 仅覆盖同方向行
      const keep = rows.value.filter((r) =>
        direction === 'floorToBook' ? r.direction !== 'floorToBook' : r.direction === 'floorToBook',
      )
      rows.value = [...keep, ...incoming]
      _renumber()
      _persistRows()
      return { added: incoming.length, message: `已从 H3-2 覆盖带入 ${incoming.length} 项（${direction === 'floorToBook' ? '实物→账面' : '账面→实物'}）` }
    }
    const existing = new Set(
      rows.value
        .filter((r) => (direction === 'floorToBook' ? r.direction === 'floorToBook' : r.direction !== 'floorToBook'))
        .map((r) => r.assetName.trim().toLowerCase()),
    )
    let added = 0
    for (const row of incoming) {
      const key = row.assetName.trim().toLowerCase()
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
        ? `已从 H3-2 新增 ${added} 项（${direction === 'floorToBook' ? '实物→账面' : '账面→实物'}，大额优先）`
        : 'H3-2 资产均已存在于本方向表，未新增',
    }
  }

  function syncTotalBookCost(): { ok: boolean; amount: number; message: string } {
    const detail = _getH32Rows()
    const amount = sumH32BookAmount(detail, measurementModel.value)
    if (amount <= 0) {
      return { ok: false, amount: 0, message: 'H3-2 明细暂无可用金额' }
    }
    updateMeta('totalBookCost', amount)
    if (!meta.value.testPopulation) {
      const label = measurementModel.value === 'fair_value' ? '公允价值' : '原值'
      updateMeta(
        'testPopulation',
        `期末投资性房地产共 ${detail.length} 项，${label}合计 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元`,
      )
    }
    return { ok: true, amount, message: `已同步期末合计 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元` }
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

  const rentedCount = computed(() => stats.value.rentedCount)
  const vacantCount = computed(() => stats.value.vacantCount)
  const vacantRate = computed(() => stats.value.vacantRate)

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

  /** 空置/闲置/毁损/盘亏 → 线索计数（供跳转 H3-10） */
  function concernCount(): number {
    return rows.value.filter((r) =>
      r.leaseStatus === '空置'
      || r.qualityStatus === '闲置'
      || r.qualityStatus === '毁损'
      || r.result === '盘亏',
    ).length
  }

  /** 空置/闲置/毁损/盘亏 → 推送 H3-10 减值关注 */
  function pushImpairmentConcernsToH10(): { concernCount: number; message: string } {
    const concerns = collectStocktakeImpairmentConcerns(rows.value)
    if (!concerns.length) {
      return { concernCount: 0, message: '未发现需推送的减值关注（空置/闲置/毁损/盘亏）' }
    }
    setValue(ITEM_H310_STOCKTAKE_CONCERNS, {
      updatedAt: new Date().toISOString(),
      items: concerns,
    })
    return {
      concernCount: concerns.length,
      message: `已推送 ${concerns.length} 项减值关注至 H3-10`,
    }
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
    rentedCount,
    vacantCount,
    vacantRate,
    addRow,
    removeRow,
    updateRow,
    updateMeta,
    saveAuditNote,
    saveAuditConclusion,
    importFromH32,
    syncTotalBookCost,
    draftNote,
    draftConclusion,
    concernCount,
    pushImpairmentConcernsToH10,
    loadAll,
  }
}

export default useH3Stocktake
