/**
 * i4PolicyIndustryHint — 根据项目上下文 / 明细费用结构推荐年报库行业
 */
export type I4PeerIndustryId = 'retail' | 'manufacturing' | 'property'

export interface IndustryHint {
  id: I4PeerIndustryId
  label: string
  confidence: 'high' | 'medium' | 'low'
  reason: string
}

const INDUSTRY_LABELS: Record<I4PeerIndustryId, string> = {
  retail: '零售/连锁',
  manufacturing: '制造业',
  property: '物业/商业地产',
}

const KEYWORD_MAP: Array<{ id: I4PeerIndustryId; words: string[] }> = [
  { id: 'retail', words: ['零售', '超市', '连锁', '便利店', '百货', '商超', '购物', '电商', '餐饮', '酒店'] },
  { id: 'property', words: ['地产', '房产', '物业', '置业', '置地', '房地产', '商业地产', '万科', '保利', '龙湖'] },
  { id: 'manufacturing', words: ['制造', '机械', '装备', '工业', '水泥', '重工', '汽车', '电子', '化工', '钢铁'] },
]

/** 从文本关键词推断行业 */
export function hintIndustryFromText(text: string): IndustryHint | null {
  const s = String(text || '')
  if (!s.trim()) return null
  for (const { id, words } of KEYWORD_MAP) {
    const hit = words.find((w) => s.includes(w))
    if (hit) {
      return {
        id,
        label: INDUSTRY_LABELS[id],
        confidence: 'high',
        reason: `文本命中「${hit}」`,
      }
    }
  }
  return null
}

/** 从 I4-2 费用类型结构推断（装修/租赁改良占比高→零售/物业） */
export function hintIndustryFromExpenseMix(
  rows: Array<{ expenseType?: string; category?: string; originalAmount?: number }>,
): IndustryHint | null {
  if (!rows?.length) return null
  const totals: Record<string, number> = {}
  let sum = 0
  for (const r of rows) {
    const cat = String(r.expenseType || r.category || '其他').trim() || '其他'
    const amt = Math.abs(Number(r.originalAmount) || 1)
    totals[cat] = (totals[cat] || 0) + amt
    sum += amt
  }
  if (!(sum > 0)) return null
  const deco = (totals['装修费'] || 0) + (totals['租赁改良'] || 0)
  const open = totals['开办费'] || 0
  const decoRatio = deco / sum
  const openRatio = open / sum
  if (decoRatio >= 0.5) {
    return {
      id: 'retail',
      label: INDUSTRY_LABELS.retail,
      confidence: decoRatio >= 0.7 ? 'high' : 'medium',
      reason: `明细装修/租赁改良占比 ${(decoRatio * 100).toFixed(0)}%（亦可选物业）`,
    }
  }
  if (openRatio >= 0.35) {
    return {
      id: 'manufacturing',
      label: INDUSTRY_LABELS.manufacturing,
      confidence: 'medium',
      reason: `明细开办费占比 ${(openRatio * 100).toFixed(0)}%`,
    }
  }
  return {
    id: 'manufacturing',
    label: INDUSTRY_LABELS.manufacturing,
    confidence: 'low',
    reason: '费用结构无显著特征，默认制造业对标',
  }
}

/**
 * 综合推荐：优先项目上下文关键词，其次明细结构
 */
export function recommendPeerIndustry(opts: {
  projectContext?: Record<string, any> | null
  detailRows?: any[]
}): IndustryHint {
  const ctx = opts.projectContext || {}
  const text = [
    ctx.industry,
    ctx.client_industry,
    ctx.client_name,
    ctx.name,
    ctx.project_name,
    ctx.business_category,
  ].filter(Boolean).join(' ')

  const fromText = hintIndustryFromText(text)
  if (fromText) return fromText

  const fromMix = hintIndustryFromExpenseMix(opts.detailRows || [])
  if (fromMix) return fromMix

  return {
    id: 'manufacturing',
    label: INDUSTRY_LABELS.manufacturing,
    confidence: 'low',
    reason: '无可用上下文，默认制造业',
  }
}

export const I4_PEER_INDUSTRY_OPTIONS: Array<{ id: I4PeerIndustryId; label: string }> = [
  { id: 'retail', label: INDUSTRY_LABELS.retail },
  { id: 'manufacturing', label: INDUSTRY_LABELS.manufacturing },
  { id: 'property', label: INDUSTRY_LABELS.property },
]

export default recommendPeerIndustry
