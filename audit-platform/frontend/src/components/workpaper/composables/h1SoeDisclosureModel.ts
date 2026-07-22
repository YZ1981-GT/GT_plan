/**
 * H1 附注披露（国有企业）数据模型
 *
 * 对齐源模板「附注披露信息（国有企业）」78 行 + note_template_soe「八、22」：
 *  A 汇总：固定资产 / 固定资产清理 / 合计（期末/期初账面价值）
 *  B (1) 固定资产情况：原值→累计折旧→净值→减值→账面价值 五层增减变动
 *  C ② 暂时闲置（原值/累计折旧/减值/账面价值/备注）
 *  D ③ 未办妥产权证书（账面价值/原因）
 *  E (2) 固定资产清理 + 超1年进展说明
 */
import { calcNetValue, calcSubtotal } from './useH1FormulaEngine'

// ─── Persistence keys ────────────────────────────────────────────────────────
// 新键 H1-soe-*；旧键 H1-disc-soe-* 仅 hydrate 回退读取。

export const H1_SOE_KEYS = {
  summary: 'H1-soe-summary',
  movement: 'H1-soe-movement',
  idle: 'H1-soe-idle-rows',
  title: 'H1-soe-title-rows',
  clearing: 'H1-soe-clearing-rows',
  clearingNote: 'H1-soe-clearing-note',
  fullyDep: 'H1-soe-fully-dep-rows',
} as const

export const H1_SOE_KEYS_LEGACY: { [K in keyof typeof H1_SOE_KEYS]: string } = {
  summary: 'H1-disc-soe-summary',
  movement: 'H1-disc-soe-movement',
  idle: 'H1-disc-soe-idle-rows',
  title: 'H1-disc-soe-title-rows',
  clearing: 'H1-disc-soe-clearing-rows',
  clearingNote: 'H1-disc-soe-clearing-note',
  fullyDep: 'H1-disc-soe-fully-dep-rows',
}

/** 优先新键，回退旧 H1-disc-soe-* */
export function readSoeRemark(
  get: (itemId: string) => { remark?: string | null } | undefined,
  key: keyof typeof H1_SOE_KEYS,
): string | null {
  const primary = get(H1_SOE_KEYS[key])?.remark
  if (primary != null && String(primary).length > 0) return primary
  const legacy = get(H1_SOE_KEYS_LEGACY[key])?.remark
  return legacy != null && String(legacy).length > 0 ? legacy : null
}

// ─── Categories（国企附注固定分类，含土地/酒店业家具）────────────────────────

export interface H1SoeCategoryDef {
  key: string
  /** 表内显示标签（土地带「其中：」） */
  label: string
  /** 匹配 H1-2/H1-1 分类用短名 */
  shortLabel: string
}

export const H1_SOE_CATEGORIES: readonly H1SoeCategoryDef[] = [
  { key: 'land', label: '其中：土地资产', shortLabel: '土地资产' },
  { key: 'building', label: '房屋、建筑物', shortLabel: '房屋、建筑物' },
  { key: 'machinery', label: '机器设备', shortLabel: '机器设备' },
  { key: 'transport', label: '运输工具', shortLabel: '运输工具' },
  { key: 'electronic', label: '电子设备', shortLabel: '电子设备' },
  { key: 'office', label: '办公设备', shortLabel: '办公设备' },
  { key: 'hotel', label: '酒店业家具', shortLabel: '酒店业家具' },
  { key: 'other', label: '其他', shortLabel: '其他' },
] as const

export type H1SoeLayer = 'cost' | 'dep' | 'net' | 'impair' | 'carrying'

export const H1_SOE_LAYER_META: Record<H1SoeLayer, { title: string; movementNa: boolean }> = {
  cost: { title: '一、账面原值合计', movementNa: false },
  dep: { title: '二、累计折旧合计', movementNa: false },
  net: { title: '三、固定资产账面净值合计', movementNa: true },
  impair: { title: '四、固定资产减值准备合计', movementNa: false },
  carrying: { title: '五、固定资产账面价值合计', movementNa: true },
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H1SoeMoveAmounts {
  begin: number
  increase: number
  decrease: number
  end: number
}

export interface H1SoeCategoryMove extends H1SoeMoveAmounts {
  key: string
}

export interface H1SoeLayerBlock {
  layer: H1SoeLayer
  categories: H1SoeCategoryMove[]
}

export interface H1SoeSummaryState {
  /** 固定资产清理期末/期初（手工或跨底稿带入） */
  clearingEnd: number
  clearingBegin: number
}

export interface H1SoeIdleRow {
  rowId: string
  name: string
  originalCost: number
  accumDep: number
  impairment: number
  carrying: number
  remark: string
  source?: string
}

export interface H1SoeTitleRow {
  rowId: string
  name: string
  carrying: number
  reason: string
  source?: string
}

export interface H1SoeClearingRow {
  rowId: string
  name: string
  endCarrying: number
  beginCarrying: number
  reason: string
}

/** ⑥已提足折旧仍继续使用的固定资产（按类别账面原值） */
export interface H1SoeFullyDepRow {
  rowId: string
  name: string
  cost: number
  remark: string
}

export interface H1SoeDisclosureState {
  summary: H1SoeSummaryState
  layers: H1SoeLayerBlock[]
  idleRows: H1SoeIdleRow[]
  titleRows: H1SoeTitleRow[]
  clearingRows: H1SoeClearingRow[]
  clearingNote: string
}

/** 扁平展示行（表格渲染用） */
export interface H1SoeFlatMoveRow {
  rowKey: string
  layer: H1SoeLayer
  kind: 'total' | 'detail'
  categoryKey: string
  label: string
  indent: boolean
  begin: number
  increase: number
  decrease: number
  end: number
  /** 本期增减列显示「—」 */
  movementNa: boolean
  /** 土地折旧等不适用 */
  allNa?: boolean
  editable: boolean
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

export function n(v: unknown): number {
  const x = typeof v === 'number' ? v : parseFloat(String(v ?? ''))
  return Number.isFinite(x) ? x : 0
}

export function emptyMove(): H1SoeMoveAmounts {
  return { begin: 0, increase: 0, decrease: 0, end: 0 }
}

export function newRowId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
}

/** 将 H1-2 / H1-1 分类名映射到国企附注固定分类 */
export function mapToSoeCategoryKey(raw: string | null | undefined): string {
  const s = String(raw || '').trim()
  if (!s) return 'other'
  if (/土地/.test(s)) return 'land'
  if (/房屋|建筑/.test(s)) return 'building'
  if (/机器|机械/.test(s)) return 'machinery'
  if (/运输|车辆/.test(s)) return 'transport'
  if (/电子/.test(s)) return 'electronic'
  if (/办公/.test(s)) return 'office'
  if (/酒店|家具/.test(s)) return 'hotel'
  if (/其他设备/.test(s)) return 'other'
  if (s === '其他') return 'other'
  return 'other'
}

function defaultCategories(): H1SoeCategoryMove[] {
  return H1_SOE_CATEGORIES.map((c) => ({ key: c.key, ...emptyMove() }))
}

export function createEmptyLayers(): H1SoeLayerBlock[] {
  return (Object.keys(H1_SOE_LAYER_META) as H1SoeLayer[]).map((layer) => ({
    layer,
    categories: defaultCategories(),
  }))
}

export function createH1SoeDisclosureState(): H1SoeDisclosureState {
  return {
    summary: { clearingEnd: 0, clearingBegin: 0 },
    layers: createEmptyLayers(),
    idleRows: [],
    titleRows: [],
    clearingRows: [],
    clearingNote: '',
  }
}

function layerMap(layers: H1SoeLayerBlock[]): Record<H1SoeLayer, H1SoeLayerBlock> {
  const m = {} as Record<H1SoeLayer, H1SoeLayerBlock>
  for (const b of layers) m[b.layer] = b
  return m
}

function findCat(block: H1SoeLayerBlock, key: string): H1SoeCategoryMove {
  let c = block.categories.find((x) => x.key === key)
  if (!c) {
    c = { key, ...emptyMove() }
    block.categories.push(c)
  }
  return c
}

/** 合计 = Σ 分类；净值/账面价值由公式推导；期末 = 期初+增-减（净值/账面价值层仅用期初/期末） */
export function recomputeSoeLayers(layers: H1SoeLayerBlock[]): H1SoeLayerBlock[] {
  const map = layerMap(layers)
  const cost = map.cost
  const dep = map.dep
  const impair = map.impair
  const net = map.net
  const carrying = map.carrying

  for (const def of H1_SOE_CATEGORIES) {
    const k = def.key
    const c = findCat(cost, k)
    const d = findCat(dep, k)
    const i = findCat(impair, k)
    // 土地一般不提折旧：保留用户数，不强制清零
    c.end = c.begin + c.increase - c.decrease
    d.end = d.begin + d.increase - d.decrease
    i.end = i.begin + i.increase - i.decrease

    const nv = findCat(net, k)
    nv.begin = calcNetValue(c.begin, d.begin, 0)
    nv.end = calcNetValue(c.end, d.end, 0)
    nv.increase = 0
    nv.decrease = 0

    const cv = findCat(carrying, k)
    cv.begin = calcNetValue(c.begin, d.begin, i.begin)
    cv.end = calcNetValue(c.end, d.end, i.end)
    cv.increase = 0
    cv.decrease = 0
  }

  return layers
}

export function layerTotal(block: H1SoeLayerBlock): H1SoeMoveAmounts {
  return {
    begin: calcSubtotal(block.categories.map((c) => c.begin)),
    increase: calcSubtotal(block.categories.map((c) => c.increase)),
    decrease: calcSubtotal(block.categories.map((c) => c.decrease)),
    end: calcSubtotal(block.categories.map((c) => c.end)),
  }
}

/** 展平为表格行（合计行 + 分类行） */
export function flattenSoeMovement(layers: H1SoeLayerBlock[]): H1SoeFlatMoveRow[] {
  const rows: H1SoeFlatMoveRow[] = []
  for (const block of layers) {
    const meta = H1_SOE_LAYER_META[block.layer]
    const tot = layerTotal(block)
    rows.push({
      rowKey: `${block.layer}-total`,
      layer: block.layer,
      kind: 'total',
      categoryKey: '',
      label: meta.title,
      indent: false,
      begin: tot.begin,
      increase: tot.increase,
      decrease: tot.decrease,
      end: tot.end,
      movementNa: meta.movementNa,
      editable: false,
    })
    for (const def of H1_SOE_CATEGORIES) {
      const c = block.categories.find((x) => x.key === def.key) ?? { key: def.key, ...emptyMove() }
      const landDepNa = block.layer === 'dep' && def.key === 'land'
      rows.push({
        rowKey: `${block.layer}-${def.key}`,
        layer: block.layer,
        kind: 'detail',
        categoryKey: def.key,
        label: def.label,
        indent: true,
        begin: c.begin,
        increase: c.increase,
        decrease: c.decrease,
        end: c.end,
        movementNa: meta.movementNa,
        allNa: landDepNa,
        editable: !meta.movementNa && block.layer !== 'net' && block.layer !== 'carrying',
      })
    }
  }
  return rows
}

export interface H1SoeSummaryDisplayRow {
  key: string
  label: string
  endCarrying: number
  beginCarrying: number
  isTotal?: boolean
  clearingEditable?: boolean
}

export function buildSummaryRows(
  layers: H1SoeLayerBlock[],
  summary: H1SoeSummaryState,
): H1SoeSummaryDisplayRow[] {
  const carrying = layers.find((l) => l.layer === 'carrying')
  const fa = carrying ? layerTotal(carrying) : emptyMove()
  const clearingEnd = n(summary.clearingEnd)
  const clearingBegin = n(summary.clearingBegin)
  return [
    { key: 'fa', label: '固定资产', endCarrying: fa.end, beginCarrying: fa.begin },
    {
      key: 'clearing',
      label: '固定资产清理',
      endCarrying: clearingEnd,
      beginCarrying: clearingBegin,
      clearingEditable: true,
    },
    {
      key: 'total',
      label: '合  计',
      endCarrying: fa.end + clearingEnd,
      beginCarrying: fa.begin + clearingBegin,
      isTotal: true,
    },
  ]
}

export function idleSubtotal(rows: H1SoeIdleRow[]): H1SoeIdleRow {
  return {
    rowId: 'idle-total',
    name: '合  计',
    originalCost: calcSubtotal(rows.map((r) => r.originalCost)),
    accumDep: calcSubtotal(rows.map((r) => r.accumDep)),
    impairment: calcSubtotal(rows.map((r) => r.impairment)),
    carrying: calcSubtotal(rows.map((r) => r.carrying)),
    remark: '',
  }
}

export function titleSubtotal(rows: H1SoeTitleRow[]): number {
  return calcSubtotal(rows.map((r) => r.carrying))
}

export function clearingSubtotal(rows: H1SoeClearingRow[]): { end: number; begin: number } {
  return {
    end: calcSubtotal(rows.map((r) => r.endCarrying)),
    begin: calcSubtotal(rows.map((r) => r.beginCarrying)),
  }
}

// ─── Seed from H1-2 / H1-4 / H1-16 ───────────────────────────────────────────

function pickAud(row: Record<string, unknown>, audKey: string, legacyKey: string): number {
  const a = n(row[audKey])
  if (a !== 0) return a
  return n(row[legacyKey])
}

/** 从 H1-2 明细按分类聚合原值/折旧/减值（优先审定字段） */
export function seedMovementFromDetailRows(detailRows: Record<string, unknown>[]): H1SoeLayerBlock[] {
  const layers = createEmptyLayers()
  const map = layerMap(layers)
  const buckets: Record<string, { cost: H1SoeMoveAmounts; dep: H1SoeMoveAmounts; impair: H1SoeMoveAmounts }> = {}
  for (const def of H1_SOE_CATEGORIES) {
    buckets[def.key] = { cost: emptyMove(), dep: emptyMove(), impair: emptyMove() }
  }

  for (const row of detailRows) {
    const key = mapToSoeCategoryKey(String(row.category ?? ''))
    const b = buckets[key] ?? buckets.other
    b.cost.begin += pickAud(row, 'costBeginAud', 'originalCostBegin')
    b.cost.increase += pickAud(row, 'costIncAud', 'originalCostIncrease')
    b.cost.decrease += pickAud(row, 'costDecAud', 'originalCostDecrease')
    b.dep.begin += pickAud(row, 'depBeginAud', 'accDepBegin')
    b.dep.increase += pickAud(row, 'depIncAud', 'accDepProvision')
    b.dep.decrease += pickAud(row, 'depDecAud', 'accDepReversal')
    b.impair.begin += pickAud(row, 'impairBeginAud', 'impairmentBegin')
    b.impair.increase += pickAud(row, 'impairIncAud', 'impairmentProvision')
    b.impair.decrease += pickAud(row, 'impairDecAud', 'impairmentReversal')
  }

  for (const def of H1_SOE_CATEGORIES) {
    const b = buckets[def.key]
    Object.assign(findCat(map.cost, def.key), b.cost)
    Object.assign(findCat(map.dep, def.key), b.dep)
    Object.assign(findCat(map.impair, def.key), b.impair)
  }
  return recomputeSoeLayers(layers)
}

export function mapIdleRowsToSoe(idleRows: Record<string, unknown>[]): H1SoeIdleRow[] {
  return idleRows.map((r, i) => {
    const originalCost = n(r.originalCost)
    const accumDep = n(r.accDep)
    const impairment = n(r.impairmentProvision ?? r.impairmentAmount)
    const carrying = n(r.netValue) || calcNetValue(originalCost, accumDep, impairment)
    return {
      rowId: String(r.rowId || newRowId('idle')),
      name: String(r.name || r.category || `闲置资产-${i + 1}`),
      originalCost,
      accumDep,
      impairment,
      carrying,
      remark: [r.idleReason, r.condition, r.remark].filter(Boolean).map(String).join('；'),
      source: 'H1-4',
    }
  })
}

export function mapUncertifiedBuildingsToSoe(buildingRows: Record<string, unknown>[]): H1SoeTitleRow[] {
  return buildingRows
    .filter((r) => {
      const conclusion = String(r.checkConclusion || r.conclusion || '')
      const noCert = !String(r.titleCertNo || '').trim()
      const fromCip = String(r.fromCip || '').toUpperCase() === 'Y'
      // 明确未取得权证，或在建转固且无证号
      return conclusion === '未取得权证' || (fromCip && noCert)
    })
    .map((r, i) => ({
      rowId: String(r.rowId || newRowId('title')),
      name: [r.assetCode, r.name, r.address].filter(Boolean).map(String).join(' ') || `未办证资产-${i + 1}`,
      carrying: n(r.netValue) || calcNetValue(n(r.bookValue), n(r.accumDep), n(r.impairment)),
      reason: String(r.cipNote || r.diffReason || r.remark || '未办妥产权证书'),
      source: 'H1-16',
    }))
}

export function emptyIdleRow(): H1SoeIdleRow {
  return { rowId: newRowId('idle'), name: '', originalCost: 0, accumDep: 0, impairment: 0, carrying: 0, remark: '' }
}

export function emptyTitleRow(): H1SoeTitleRow {
  return { rowId: newRowId('title'), name: '', carrying: 0, reason: '' }
}

export function emptyClearingRow(): H1SoeClearingRow {
  return { rowId: newRowId('clr'), name: '', endCarrying: 0, beginCarrying: 0, reason: '' }
}

export function emptyFullyDepRow(): H1SoeFullyDepRow {
  return { rowId: newRowId('fdep'), name: '', cost: 0, remark: '' }
}

export function fullyDepSubtotal(rows: H1SoeFullyDepRow[]): number {
  return calcSubtotal(rows.map((r) => n(r.cost)))
}

/**
 * 从 H1-2 明细识别「已提足折旧仍在使用」候选，映射到国企固定分类标签，按类别汇总账面原值。
 * 净值 ≤ 原值 × 残值率(默认5%) 且 累计折旧>0 视为提足；结果为候选需审计师确认。
 */
export function deriveSoeFullyDepreciated(
  detailRows: Record<string, unknown>[],
  opts?: { residualRate?: number },
): H1SoeFullyDepRow[] {
  const residualRate = opts?.residualRate ?? 0.05
  const labelByKey = new Map(H1_SOE_CATEGORIES.map((c) => [c.key, c.shortLabel]))
  const byKey = new Map<string, number>()
  for (const r of detailRows) {
    const cost = n(r.costEndAud) || n(r.originalCostEnd)
    if (cost <= 0) continue
    const accDep = n(r.depEndAud) || n(r.accDepEnd)
    if (accDep <= 0) continue
    const impair = n(r.impairEndAud) || n(r.impairmentEnd)
    const net = r.netValue != null ? n(r.netValue) : cost - accDep - impair
    if (net > cost * residualRate + 0.005) continue
    const key = mapToSoeCategoryKey(String(r.category ?? ''))
    byKey.set(key, (byKey.get(key) || 0) + cost)
  }
  return [...byKey.entries()].map(([key, cost], i) => ({
    rowId: `fdep-${i}-${key}`,
    name: labelByKey.get(key) || '其他',
    cost,
    remark: '已提足折旧仍继续使用',
  }))
}

export function hydrateFullyDepRows(saved: unknown): H1SoeFullyDepRow[] {
  if (!Array.isArray(saved)) return []
  return saved.map((raw: any, i) => ({
    rowId: String(raw?.rowId || newRowId('fdep')),
    name: String(raw?.name || `行${i + 1}`),
    cost: n(raw?.cost ?? raw?.amount),
    remark: String(raw?.remark || ''),
  }))
}

/** 闲置行自动重算账面价值 */
export function recomputeIdleCarrying(row: H1SoeIdleRow): void {
  row.carrying = calcNetValue(row.originalCost, row.accumDep, row.impairment)
}

// ─── Load / merge persisted JSON ─────────────────────────────────────────────

export function parseJsonArray<T>(raw: string | null | undefined): T[] {
  if (!raw) return []
  try {
    const p = JSON.parse(raw)
    return Array.isArray(p) ? (p as T[]) : []
  } catch {
    return []
  }
}

export function hydrateLayers(saved: unknown): H1SoeLayerBlock[] {
  const base = createEmptyLayers()
  if (!Array.isArray(saved) || saved.length === 0) return base
  const map = layerMap(base)
  for (const block of saved as H1SoeLayerBlock[]) {
    if (!block?.layer || !map[block.layer]) continue
    for (const c of block.categories || []) {
      if (!c?.key) continue
      Object.assign(findCat(map[block.layer], c.key), {
        begin: n(c.begin),
        increase: n(c.increase),
        decrease: n(c.decrease),
        end: n(c.end),
      })
    }
  }
  return recomputeSoeLayers(base)
}

export function hydrateSummary(saved: unknown): H1SoeSummaryState {
  if (!saved || typeof saved !== 'object') return { clearingEnd: 0, clearingBegin: 0 }
  const o = saved as Record<string, unknown>
  return { clearingEnd: n(o.clearingEnd), clearingBegin: n(o.clearingBegin) }
}

/** 兼容旧版动态行 { name, amount, description } */
export function hydrateIdleRows(saved: unknown): H1SoeIdleRow[] {
  if (!Array.isArray(saved)) return []
  return saved.map((raw: any, i) => {
    if (raw && ('originalCost' in raw || 'accumDep' in raw)) {
      const row: H1SoeIdleRow = {
        rowId: String(raw.rowId || newRowId('idle')),
        name: String(raw.name || ''),
        originalCost: n(raw.originalCost),
        accumDep: n(raw.accumDep),
        impairment: n(raw.impairment),
        carrying: n(raw.carrying),
        remark: String(raw.remark || raw.description || ''),
        source: raw.source,
      }
      if (!row.carrying) recomputeIdleCarrying(row)
      return row
    }
    // legacy
    return {
      rowId: String(raw?.rowId || newRowId('idle')),
      name: String(raw?.name || `行${i + 1}`),
      originalCost: 0,
      accumDep: 0,
      impairment: 0,
      carrying: n(raw?.amount),
      remark: String(raw?.description || raw?.remark || ''),
    }
  })
}

export function hydrateTitleRows(saved: unknown): H1SoeTitleRow[] {
  if (!Array.isArray(saved)) return []
  return saved.map((raw: any, i) => ({
    rowId: String(raw.rowId || newRowId('title')),
    name: String(raw.name || `行${i + 1}`),
    carrying: n(raw.carrying ?? raw.amount),
    reason: String(raw.reason || raw.description || ''),
    source: raw.source,
  }))
}

export function hydrateClearingRows(saved: unknown): H1SoeClearingRow[] {
  if (!Array.isArray(saved)) return []
  return saved.map((raw: any) => ({
    rowId: String(raw.rowId || newRowId('clr')),
    name: String(raw.name || ''),
    endCarrying: n(raw.endCarrying ?? raw.amount),
    beginCarrying: n(raw.beginCarrying),
    reason: String(raw.reason || raw.description || ''),
  }))
}

export function layersHaveAnyAmount(layers: H1SoeLayerBlock[]): boolean {
  for (const b of layers) {
    for (const c of b.categories) {
      if (c.begin || c.increase || c.decrease || c.end) return true
    }
  }
  return false
}

export const CLEARING_NOTE_PLACEHOLDER =
  '说明转入固定资产清理起始时间已超过1年的固定资产清理进展情况。'
