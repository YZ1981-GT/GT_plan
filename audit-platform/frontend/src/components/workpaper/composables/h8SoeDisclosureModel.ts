/**
 * H8 附注披露（国企）数据模型
 *
 * 对齐源模板「附注披露信息（国企）」+ note_template_soe「八、26」：
 *  一、账面原值合计（土地 / 房屋建筑物 / 机器运输办公 / 其他）
 *  二、累计折旧合计
 *  三、使用权资产账面净值合计（增减列 N/A）
 *  四、减值准备合计
 *  五、使用权资产账面价值合计（增减列 N/A）
 */
export const H8_SOE_KEYS = {
  layers: 'H8-soe-layers',
  noteImpairment: 'H8-soe-note-impairment',
  auditNote: 'H8-soe-audit-note',
  auditConclusion: 'H8-soe-audit-conclusion',
} as const

export interface H8SoeCategoryDef {
  key: string
  label: string
  shortLabel: string
}

/** 国企固定分类（对齐源模板「其中」行） */
export const H8_SOE_CATEGORIES: readonly H8SoeCategoryDef[] = [
  { key: 'land', label: '其中：土地', shortLabel: '土地' },
  { key: 'building', label: '房屋、建筑物', shortLabel: '房屋、建筑物' },
  { key: 'equipment', label: '机器、运输、办公设备', shortLabel: '机器、运输、办公设备' },
  { key: 'other', label: '其他', shortLabel: '其他' },
] as const

export type H8SoeLayer = 'cost' | 'dep' | 'net' | 'impair' | 'carrying'

export const H8_SOE_LAYER_META: Record<H8SoeLayer, { title: string; movementNa: boolean }> = {
  cost: { title: '一、账面原值合计', movementNa: false },
  dep: { title: '二、累计折旧合计', movementNa: false },
  net: { title: '三、使用权资产账面净值合计', movementNa: true },
  impair: { title: '四、减值准备合计', movementNa: false },
  carrying: { title: '五、使用权资产账面价值合计', movementNa: true },
}

export interface H8SoeMoveAmounts {
  begin: number
  increase: number
  decrease: number
  end: number
}

export interface H8SoeCategoryMove extends H8SoeMoveAmounts {
  key: string
}

export interface H8SoeLayerBlock {
  layer: H8SoeLayer
  categories: H8SoeCategoryMove[]
}

function emptyMove(key: string): H8SoeCategoryMove {
  return { key, begin: 0, increase: 0, decrease: 0, end: 0 }
}

export function createDefaultSoeLayers(): H8SoeLayerBlock[] {
  const cats = () => H8_SOE_CATEGORIES.map((c) => emptyMove(c.key))
  return (Object.keys(H8_SOE_LAYER_META) as H8SoeLayer[]).map((layer) => ({
    layer,
    categories: cats(),
  }))
}

export function num(v: unknown): number {
  const x = typeof v === 'number' ? v : parseFloat(String(v ?? '').replace(/,/g, ''))
  return Number.isFinite(x) ? x : 0
}

/** 期末 = 期初 + 增 - 减（净值/账面价值层由公式覆盖） */
export function resolveCategoryEnd(m: H8SoeMoveAmounts, movementNa: boolean): number {
  if (movementNa) return num(m.end)
  return num(m.begin) + num(m.increase) - num(m.decrease)
}

export function layerTotal(block: H8SoeLayerBlock): H8SoeMoveAmounts {
  const meta = H8_SOE_LAYER_META[block.layer]
  const begin = block.categories.reduce((s, c) => s + num(c.begin), 0)
  const increase = meta.movementNa ? 0 : block.categories.reduce((s, c) => s + num(c.increase), 0)
  const decrease = meta.movementNa ? 0 : block.categories.reduce((s, c) => s + num(c.decrease), 0)
  const end = block.categories.reduce((s, c) => s + resolveCategoryEnd(c, meta.movementNa), 0)
  return { begin, increase, decrease, end }
}

/** 净值层 = 原值 − 折旧；账面价值 = 净值 − 减值（同步各类别） */
export function recomputeDerivedLayers(layers: H8SoeLayerBlock[]): H8SoeLayerBlock[] {
  const byLayer = new Map(layers.map((l) => [l.layer, l]))
  const cost = byLayer.get('cost')
  const dep = byLayer.get('dep')
  const impair = byLayer.get('impair')
  if (!cost || !dep) return layers

  const netCats: H8SoeCategoryMove[] = H8_SOE_CATEGORIES.map((c) => {
    const cc = cost.categories.find((x) => x.key === c.key) || emptyMove(c.key)
    const dc = dep.categories.find((x) => x.key === c.key) || emptyMove(c.key)
    const beginNet = num(cc.begin) - num(dc.begin)
    const endNet = resolveCategoryEnd(cc, false) - resolveCategoryEnd(dc, false)
    return { key: c.key, begin: beginNet, increase: 0, decrease: 0, end: endNet }
  })

  const netBlock: H8SoeLayerBlock = { layer: 'net', categories: netCats }

  const impairCats = impair?.categories || H8_SOE_CATEGORIES.map((c) => emptyMove(c.key))
  const carryingCats: H8SoeCategoryMove[] = H8_SOE_CATEGORIES.map((c) => {
    const n = netCats.find((x) => x.key === c.key) || emptyMove(c.key)
    const im = impairCats.find((x) => x.key === c.key) || emptyMove(c.key)
    const begin = num(n.begin) - num(im.begin)
    const end = num(n.end) - resolveCategoryEnd(im, false)
    return { key: c.key, begin, increase: 0, decrease: 0, end }
  })

  return layers.map((l) => {
    if (l.layer === 'net') return netBlock
    if (l.layer === 'carrying') return { layer: 'carrying', categories: carryingCats }
    if (l.layer === 'cost' || l.layer === 'dep' || l.layer === 'impair') {
      return {
        ...l,
        categories: l.categories.map((c) => ({
          ...c,
          end: resolveCategoryEnd(c, false),
        })),
      }
    }
    return l
  })
}

export function flattenSoeMovement(layers: H8SoeLayerBlock[]): Array<{
  layer: H8SoeLayer
  kind: 'total' | 'detail'
  label: string
  begin: number
  increase: number
  decrease: number
  end: number
  allNa: boolean
}> {
  const out: Array<{
    layer: H8SoeLayer
    kind: 'total' | 'detail'
    label: string
    begin: number
    increase: number
    decrease: number
    end: number
    allNa: boolean
  }> = []
  for (const block of layers) {
    const meta = H8_SOE_LAYER_META[block.layer]
    const tot = layerTotal(block)
    out.push({
      layer: block.layer,
      kind: 'total',
      label: meta.title,
      begin: tot.begin,
      increase: tot.increase,
      decrease: tot.decrease,
      end: tot.end,
      allNa: false,
    })
    for (const cat of H8_SOE_CATEGORIES) {
      const m = block.categories.find((c) => c.key === cat.key) || emptyMove(cat.key)
      out.push({
        layer: block.layer,
        kind: 'detail',
        label: cat.label,
        begin: num(m.begin),
        increase: num(m.increase),
        decrease: num(m.decrease),
        end: resolveCategoryEnd(m, meta.movementNa),
        allNa: meta.movementNa,
      })
    }
  }
  return out
}

export function mapToSoeCategoryKey(name: string): string {
  const s = String(name || '')
  if (/土地|土地使用权/.test(s)) return 'land'
  if (/房屋|建筑|办公楼|厂房/.test(s)) return 'building'
  if (/机器|运输|车辆|办公|设备/.test(s)) return 'equipment'
  return 'other'
}

export interface H8SoeSyncSnapshot {
  layers: H8SoeLayerBlock[]
  noteImpairment: string
}

export const H8_SOE_GUIDANCE = {
  impairment:
    '【长期资产本期进行减值测试的，应披露可收回金额的具体确定方法、关键参数及与以前年度差异原因。即使未计提减值，执行减值测试的也要披露。估计可收回金额时通常不应使用重置成本法。】',
} as const
