/**
 * I1 附注披露（国有企业）数据模型
 *
 * 对齐源模板「附注披露信息（国有企业）」+ note_template_soe「八、27」：
 *  一、原价合计 / 二、累计摊销合计 / 三、减值准备合计 / 四、账面价值合计
 *  每层：合计行 + 分类明细行；列：期初 / 本期增加 / 本期减少 / 期末
 *  账面价值层增减列 N/A（由原值−摊销−减值推导）
 */
export const I1_SOE_KEYS = {
  layers: 'I1-soe-layers',
  noteIndefinite: 'I1-soe-note-indefinite',
  noteMortgage: 'I1-soe-note-mortgage',
  noteValuation: 'I1-soe-note-valuation',
  noteImpairment: 'I1-soe-note-impairment',
  noteNotReady: 'I1-soe-note-not-ready',
  noteSale: 'I1-soe-note-sale',
  noteTitle: 'I1-soe-note-title',
  auditNote: 'I1-soe-audit-note',
  auditConclusion: 'I1-soe-audit-conclusion',
} as const

export interface I1SoeCategoryDef {
  key: string
  label: string
  shortLabel: string
}

/** 国企固定分类（对齐源模板「其中」+ note_template） */
export const I1_SOE_CATEGORIES: readonly I1SoeCategoryDef[] = [
  { key: 'software', label: '其中：软件', shortLabel: '软件' },
  { key: 'land', label: '土地使用权', shortLabel: '土地使用权' },
  { key: 'housing', label: '房屋使用权', shortLabel: '房屋使用权' },
  { key: 'patent', label: '专利权', shortLabel: '专利权' },
  { key: 'knowhow', label: '非专利技术', shortLabel: '非专利技术' },
  { key: 'trademark', label: '商标权', shortLabel: '商标权' },
  { key: 'copyright', label: '著作权', shortLabel: '著作权' },
  { key: 'franchise', label: '特许权', shortLabel: '特许权' },
  { key: 'mining', label: '采矿权', shortLabel: '采矿权' },
  { key: 'exploration', label: '探矿权', shortLabel: '探矿权' },
  { key: 'data', label: '数据资源', shortLabel: '数据资源' },
  { key: 'other', label: '其他', shortLabel: '其他' },
] as const

export type I1SoeLayer = 'cost' | 'amort' | 'impair' | 'carrying'

export const I1_SOE_LAYER_META: Record<I1SoeLayer, { title: string; movementNa: boolean }> = {
  cost: { title: '一、原价合计', movementNa: false },
  amort: { title: '二、累计摊销合计', movementNa: false },
  impair: { title: '三、无形资产减值准备合计', movementNa: false },
  carrying: { title: '四、账面价值合计', movementNa: true },
}

export interface I1SoeMoveAmounts {
  begin: number
  increase: number
  decrease: number
  end: number
}

export interface I1SoeCategoryMove extends I1SoeMoveAmounts {
  key: string
}

export interface I1SoeLayerBlock {
  layer: I1SoeLayer
  categories: I1SoeCategoryMove[]
}

function emptyMove(key: string): I1SoeCategoryMove {
  return { key, begin: 0, increase: 0, decrease: 0, end: 0 }
}

export function createDefaultI1SoeLayers(): I1SoeLayerBlock[] {
  const cats = () => I1_SOE_CATEGORIES.map((c) => emptyMove(c.key))
  return (Object.keys(I1_SOE_LAYER_META) as I1SoeLayer[]).map((layer) => ({
    layer,
    categories: cats(),
  }))
}

export function num(v: unknown): number {
  const x = typeof v === 'number' ? v : parseFloat(String(v ?? '').replace(/,/g, ''))
  return Number.isFinite(x) ? x : 0
}

export function resolveCategoryEnd(m: I1SoeMoveAmounts, movementNa: boolean): number {
  if (movementNa) return num(m.end)
  return num(m.begin) + num(m.increase) - num(m.decrease)
}

export function layerTotal(block: I1SoeLayerBlock): I1SoeMoveAmounts {
  const meta = I1_SOE_LAYER_META[block.layer]
  const begin = block.categories.reduce((s, c) => s + num(c.begin), 0)
  const increase = meta.movementNa ? 0 : block.categories.reduce((s, c) => s + num(c.increase), 0)
  const decrease = meta.movementNa ? 0 : block.categories.reduce((s, c) => s + num(c.decrease), 0)
  const end = block.categories.reduce((s, c) => s + resolveCategoryEnd(c, meta.movementNa), 0)
  return { begin, increase, decrease, end }
}

/** 账面价值 = 原值 − 摊销 − 减值 */
export function recomputeI1SoeDerivedLayers(layers: I1SoeLayerBlock[]): I1SoeLayerBlock[] {
  const byLayer = new Map(layers.map((l) => [l.layer, l]))
  const cost = byLayer.get('cost')
  const amort = byLayer.get('amort')
  const impair = byLayer.get('impair')
  if (!cost || !amort) return layers

  const carryingCats: I1SoeCategoryMove[] = I1_SOE_CATEGORIES.map((c) => {
    const cc = cost.categories.find((x) => x.key === c.key) || emptyMove(c.key)
    const ac = amort.categories.find((x) => x.key === c.key) || emptyMove(c.key)
    const ic = impair?.categories.find((x) => x.key === c.key) || emptyMove(c.key)
    const begin = num(cc.begin) - num(ac.begin) - num(ic.begin)
    const end = resolveCategoryEnd(cc, false) - resolveCategoryEnd(ac, false) - resolveCategoryEnd(ic, false)
    return { key: c.key, begin, increase: 0, decrease: 0, end }
  })

  return layers.map((l) => {
    if (l.layer === 'carrying') return { layer: 'carrying', categories: carryingCats }
    if (l.layer === 'cost' || l.layer === 'amort' || l.layer === 'impair') {
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

export function flattenI1SoeMovement(layers: I1SoeLayerBlock[]): Array<{
  layer: I1SoeLayer
  kind: 'total' | 'detail'
  label: string
  begin: number
  increase: number
  decrease: number
  end: number
  allNa: boolean
}> {
  const out: Array<{
    layer: I1SoeLayer
    kind: 'total' | 'detail'
    label: string
    begin: number
    increase: number
    decrease: number
    end: number
    allNa: boolean
  }> = []
  for (const block of layers) {
    const meta = I1_SOE_LAYER_META[block.layer]
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
    for (const cat of I1_SOE_CATEGORIES) {
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

export function mapToI1SoeCategoryKey(categoryOrName: string): string {
  const s = String(categoryOrName || '')
  if (/软件|系统/.test(s)) return 'software'
  if (/土地/.test(s)) return 'land'
  if (/房屋|住房/.test(s)) return 'housing'
  if (/专利/.test(s) && !/非专利/.test(s)) return 'patent'
  if (/非专利|专有技术/.test(s)) return 'knowhow'
  if (/商标/.test(s)) return 'trademark'
  if (/著作|版权/.test(s)) return 'copyright'
  if (/特许/.test(s)) return 'franchise'
  if (/采矿/.test(s)) return 'mining'
  if (/探矿/.test(s)) return 'exploration'
  if (/探矿权\/采矿权|矿权/.test(s)) return 'mining'
  if (/数据资源|数据资产/.test(s)) return 'data'
  return 'other'
}

export const I1_SOE_GUIDANCE = {
  indefinite: '1、使用寿命不确定的无形资产判断依据。',
  mortgage: '2、说明用于抵押、担保的土地使用权等情况。',
  valuation: '3、单项金额重大（如超过100万元）且以评估价值入账的，披露评估机构及方法。',
  impairment: '4、减值准备计提或减少的原因。',
  notReady: '5、尚未达到可使用状态的无形资产减值测试结果。',
  sale: '6、明显高于账面价值出售的，说明作价基础、估值模型及敏感性分析。',
  title: '7、未办妥权属证书的土地使用权账面价值、原因及预计办妥时间。',
} as const

export interface I1SoeSyncSnapshot {
  layers: I1SoeLayerBlock[]
  noteIndefinite: string
  noteMortgage: string
  noteValuation: string
  noteImpairment: string
  noteNotReady: string
  noteSale: string
  noteTitle: string
  amortAlloc?: import('./i1DisclosureEnhance').I1AmortAllocSummary
}
