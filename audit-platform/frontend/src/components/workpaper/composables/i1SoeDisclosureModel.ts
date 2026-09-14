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
  /**
   * 自定义类别的中文名（默认 12 类不带，label 取自 `I1_SOE_CATEGORIES`）。
   * 🔴 源模板四层末各一个 `……` 可扩位（原价/累计摊销/减值/账面价值），
   * 审计师增行时把名字存在这里，随 layers 数据一起持久化 —— 类别集因此
   * 从数据派生而非写死常量，稳定 key 不复用已删序号（Task 13 / Property 21·23）。
   */
  label?: string
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

  // 类别集从数据派生（默认 12 类 + 自定义），使自定义类别在账面价值层也联动
  const effectiveCats = resolveI1SoeCategories(layers)
  const carryingCats: I1SoeCategoryMove[] = effectiveCats.map((c) => {
    const cc = cost.categories.find((x) => x.key === c.key) || emptyMove(c.key)
    const ac = amort.categories.find((x) => x.key === c.key) || emptyMove(c.key)
    const ic = impair?.categories.find((x) => x.key === c.key) || emptyMove(c.key)
    const begin = num(cc.begin) - num(ac.begin) - num(ic.begin)
    const end = resolveCategoryEnd(cc, false) - resolveCategoryEnd(ac, false) - resolveCategoryEnd(ic, false)
    const label = _SOE_DEFAULT_LABEL.get(c.key) ? undefined : c.label
    return { key: c.key, label, begin, increase: 0, decrease: 0, end }
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
    for (const cat of resolveI1SoeCategories(layers)) {
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

// ── 动态可扩类别（Task 13 / R7.1 国企四层末 `……` 可扩位）───────────────────
//
// 🔴 源模板国企披露 sheet 每层（原价/累计摊销/减值/账面价值）末尾各有一个 `……`
// 可扩位。国企版类别是「跨四层共享」的（同一类别在四层都出现），故自定义类别
// 通过 `I1SoeCategoryMove.label` 随数据携带（default 12 类的 label 仍取自
// `I1_SOE_CATEGORIES` 常量，自定义类别的 label 存在数据里）。
//
// key 用单调计数器 `soe_custom_${seq}`，**不复用已删序号**（撞键会让旧数据串台，
// H7 已踩）；seq = max(现有全部 custom seq, 0) + 1。

const _SOE_DEFAULT_KEYS = new Set(I1_SOE_CATEGORIES.map((c) => c.key))
const _SOE_CUSTOM_KEY_RE = /^soe_custom_(\d+)$/

/** default 类别 key → label（自定义类别不在此表，label 随数据） */
const _SOE_DEFAULT_LABEL = new Map(I1_SOE_CATEGORIES.map((c) => [c.key, c.label]))

/**
 * 从 layers 数据派生「有效类别序列」= 默认 12 类 + 数据里出现的自定义类别（按 seq 升序）。
 *
 * 自定义类别的 label 取自任一层该 key 的 move.label（首个非空）。渲染 / flatten /
 * recompute 全部改用本函数，不再直接遍历 `I1_SOE_CATEGORIES`，这样自定义类别一处新增
 * 即在四层同时出现。
 */
export function resolveI1SoeCategories(
  layers: I1SoeLayerBlock[],
): Array<{ key: string; label: string; removable: boolean }> {
  const out = I1_SOE_CATEGORIES.map((c) => ({ key: c.key, label: c.label, removable: c.key !== 'other' }))
  const seen = new Set(_SOE_DEFAULT_KEYS)
  const customs: Array<{ key: string; label: string; seq: number }> = []
  for (const block of layers) {
    for (const m of block.categories) {
      if (seen.has(m.key)) continue
      const mm = _SOE_CUSTOM_KEY_RE.exec(m.key)
      if (!mm) continue
      seen.add(m.key)
      customs.push({ key: m.key, label: String(m.label || m.key), seq: Number(mm[1]) })
    }
  }
  customs.sort((a, b) => a.seq - b.seq)
  for (const c of customs) out.push({ key: c.key, label: c.label, removable: true })
  return out
}

/** 数据里现存自定义类别的最大 seq（0 = 无自定义类别）。 */
export function maxI1SoeCustomSeq(layers: I1SoeLayerBlock[]): number {
  let maxSeq = 0
  for (const block of layers) {
    for (const m of block.categories) {
      const mm = _SOE_CUSTOM_KEY_RE.exec(m.key)
      if (mm) maxSeq = Math.max(maxSeq, Number(mm[1]))
    }
  }
  return maxSeq
}

/**
 * 下一个自定义类别 key（单调计数器，**不复用已删序号**）。
 *
 * 🔴 只看「数据里现存最大 seq」会在删掉最大号后回退、下一个 key 复用已删序号
 * （撞键 → 旧持久化数据串台，H7 已踩）。故传入 `seqFloor` = 持久化的单调计数器，
 * key = `max(现存最大, seqFloor) + 1`。调用方（composable）负责持久化该计数器。
 */
export function nextI1SoeCustomKey(layers: I1SoeLayerBlock[], seqFloor = 0): string {
  const next = Math.max(maxI1SoeCustomSeq(layers), seqFloor) + 1
  return `soe_custom_${next}`
}

/**
 * 在四层同时新增一个自定义类别（撞名拒绝 → 返回 null）。
 *
 * @param label 用户输入的类别名（已 trim；空或与现有 label 撞名则拒绝）
 * @param seqFloor 持久化单调计数器，防复用已删序号（见 `nextI1SoeCustomKey`）
 * @returns `{ layers, key, seq }` 或 null；调用方据 `seq` 回写持久化计数器
 */
export function addI1SoeCategory(
  layers: I1SoeLayerBlock[],
  label: string,
  seqFloor = 0,
): { layers: I1SoeLayerBlock[]; key: string; seq: number } | null {
  const trimmed = (label || '').trim()
  if (!trimmed) return null
  // 撞名检测：默认类别 label + 已有自定义类别 label
  const existingLabels = new Set<string>(resolveI1SoeCategories(layers).map((c) => c.label))
  if (existingLabels.has(trimmed)) return null
  const key = nextI1SoeCustomKey(layers, seqFloor)
  const seq = Number(_SOE_CUSTOM_KEY_RE.exec(key)![1])
  const next = layers.map((block) => ({
    ...block,
    categories: [...block.categories, { key, label: trimmed, begin: 0, increase: 0, decrease: 0, end: 0 }],
  }))
  return { layers: next, key, seq }
}

/** 从四层同时删除一个自定义类别（默认类别不可删 → 返回 null）。 */
export function removeI1SoeCategory(
  layers: I1SoeLayerBlock[],
  key: string,
): I1SoeLayerBlock[] | null {
  if (_SOE_DEFAULT_KEYS.has(key) || !_SOE_CUSTOM_KEY_RE.test(key)) return null
  return layers.map((block) => ({
    ...block,
    categories: block.categories.filter((c) => c.key !== key),
  }))
}

/** 某 key 的展示 label（默认类别取常量，自定义取数据里的 label）。 */
export function i1SoeCategoryLabel(key: string, layers: I1SoeLayerBlock[]): string {
  const def = _SOE_DEFAULT_LABEL.get(key)
  if (def) return def
  for (const block of layers) {
    const m = block.categories.find((c) => c.key === key)
    if (m && m.label) return String(m.label)
  }
  return key
}
