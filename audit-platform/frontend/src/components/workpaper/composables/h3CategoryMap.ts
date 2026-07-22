/**
 * H3 资产类别归一化 — 统一 H3-1 / H3-2 / H3-3 分类键
 */
export const H3_ASSET_CATEGORIES = ['房屋及建筑物', '土地使用权', '其他'] as const
export type H3AssetCategory = (typeof H3_ASSET_CATEGORIES)[number]

/** 是否已是标准三类文案（不含模糊推断） */
export function isStandardH3Category(raw: string | null | undefined): boolean {
  const s = String(raw || '').trim()
  return (H3_ASSET_CATEGORIES as readonly string[]).includes(s)
}

/** 将任意分类文本归一到 H3-1 标准三类 */
export function normalizeH3Category(raw: string | null | undefined): H3AssetCategory {
  const s = String(raw || '').trim()
  if (!s) return '其他'
  if (/房屋|建筑|楼|厂房|写字楼|公寓/.test(s)) return '房屋及建筑物'
  if (/土地|使用权|地块/.test(s)) return '土地使用权'
  if (s === '房屋及建筑物' || s === '土地使用权' || s === '其他') return s
  return '其他'
}

/** 从调整分录文本推断分类（category 优先，其次 description/summary/accountName） */
export function inferH3CategoryFromAdjustment(row: {
  category?: string
  description?: string
  summary?: string
  accountName?: string
}): H3AssetCategory {
  if (row.category) return normalizeH3Category(row.category)
  const blob = `${row.description || ''} ${row.summary || ''} ${row.accountName || ''}`
  return normalizeH3Category(blob)
}

export function emptyCategoryAmountMap(): Record<H3AssetCategory, number> {
  return {
    '房屋及建筑物': 0,
    '土地使用权': 0,
    '其他': 0,
  }
}
