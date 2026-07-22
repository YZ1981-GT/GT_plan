/**
 * H4 附注披露（上市公司）数据模型
 *
 * 对齐致同 Excel「附注披露信息（上市公司）」列结构（列不可改）：
 *   交叉索引：【在建工程与工程物资的合计数披露详见J2-1】
 *   （2）工程物资
 *     专用材料 / 专用设备 / 工器具
 *     （小计 — 三项原值合计）
 *     工程物资减值准备（抵减，括号列示）
 *     合计 = 小计 − 减值
 *   列：项目 | 期末余额 | 上年年末余额
 */

export const H4_LISTED_ITEM = {
  materials: 'H4-listed-materials',
  noteText: 'H4-disclosure-listed-text',
} as const

export function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export type H4ListedMaterialKey = 'specialMaterial' | 'specialEquipment' | 'tools' | 'impairment'

export interface H4ListedMaterialRow {
  key: H4ListedMaterialKey
  label: string
  endBalance: number
  priorBalance: number
  /** 减值行为抵减 */
  isDeduction?: boolean
}

export function createDefaultH4ListedMaterials(): H4ListedMaterialRow[] {
  return [
    { key: 'specialMaterial', label: '专用材料', endBalance: 0, priorBalance: 0 },
    { key: 'specialEquipment', label: '专用设备', endBalance: 0, priorBalance: 0 },
    { key: 'tools', label: '工器具', endBalance: 0, priorBalance: 0 },
    { key: 'impairment', label: '工程物资减值准备', endBalance: 0, priorBalance: 0, isDeduction: true },
  ]
}

/** 三项原值小计（不含减值） */
export function h4ListedMaterialsGross(rows: H4ListedMaterialRow[]): { endBalance: number; priorBalance: number } {
  const gross = rows.filter((r) => !r.isDeduction)
  return {
    endBalance: gross.reduce((s, r) => s + num(r.endBalance), 0),
    priorBalance: gross.reduce((s, r) => s + num(r.priorBalance), 0),
  }
}

/** 净值合计 = 小计 − 减值 */
export function h4ListedMaterialsNet(rows: H4ListedMaterialRow[]): { endBalance: number; priorBalance: number } {
  const g = h4ListedMaterialsGross(rows)
  const imp = rows.find((r) => r.isDeduction)
  return {
    endBalance: g.endBalance - num(imp?.endBalance),
    priorBalance: g.priorBalance - num(imp?.priorBalance),
  }
}

/** 明细分类名 → 披露固定行 */
export function mapCategoryToH4ListedKey(category: string): Exclude<H4ListedMaterialKey, 'impairment'> | null {
  const s = String(category || '').trim()
  if (!s) return null
  if (/专用材料|材料/.test(s) && !/设备|器具|工具/.test(s)) return 'specialMaterial'
  if (/专用设备|设备/.test(s)) return 'specialEquipment'
  if (/工器具|工具|器具/.test(s)) return 'tools'
  if (/其他/.test(s)) return 'specialMaterial'
  return null
}

export interface H4DetailCategorySource {
  category?: string
  beginAmount?: number
  endAmount?: number
  auditedEnd?: number
  impairEnd?: number
  auditedImpairEnd?: number
  beginImpair?: number
}

/**
 * 从 H4-2 明细按分类汇总到上市披露固定行。
 * 期末优先审定期末；上年年末取期初；减值单独汇总。
 */
export function seedH4ListedMaterialsFromDetail(
  detailRows: H4DetailCategorySource[],
  opts?: { impairmentEnd?: number; impairmentPrior?: number },
): H4ListedMaterialRow[] {
  const rows = createDefaultH4ListedMaterials()
  const byKey = new Map(rows.map((r) => [r.key, r]))
  let impairEnd = 0
  let impairPrior = 0

  for (const d of detailRows || []) {
    const key = mapCategoryToH4ListedKey(String(d.category || ''))
    const end = num(d.auditedEnd) || num(d.endAmount)
    const prior = num(d.beginAmount)
    impairEnd += num(d.auditedImpairEnd) || num(d.impairEnd)
    impairPrior += num(d.beginImpair)
    if (!key) continue
    const target = byKey.get(key)!
    target.endBalance = Math.round((target.endBalance + end) * 100) / 100
    target.priorBalance = Math.round((target.priorBalance + prior) * 100) / 100
  }

  const imp = byKey.get('impairment')!
  imp.endBalance = opts?.impairmentEnd != null && opts.impairmentEnd !== 0
    ? num(opts.impairmentEnd)
    : Math.round(impairEnd * 100) / 100
  imp.priorBalance = opts?.impairmentPrior != null
    ? num(opts.impairmentPrior)
    : Math.round(impairPrior * 100) / 100

  return rows
}

/** 展示行：数据行 + 小计 + 合计 */
export interface H4ListedMaterialDisplayRow {
  key: string
  label: string
  endBalance: number
  priorBalance: number
  editable: boolean
  isDeduction?: boolean
}

export function buildH4ListedMaterialsDisplay(rows: H4ListedMaterialRow[]): H4ListedMaterialDisplayRow[] {
  const gross = h4ListedMaterialsGross(rows)
  const net = h4ListedMaterialsNet(rows)
  const data = rows.filter((r) => !r.isDeduction)
  const imp = rows.find((r) => r.isDeduction)
  return [
    ...data.map((r) => ({
      key: r.key,
      label: r.label,
      endBalance: r.endBalance,
      priorBalance: r.priorBalance,
      editable: true,
    })),
    {
      key: '__gross__',
      label: '',
      endBalance: gross.endBalance,
      priorBalance: gross.priorBalance,
      editable: false,
    },
    {
      key: 'impairment',
      label: imp?.label || '工程物资减值准备',
      endBalance: num(imp?.endBalance),
      priorBalance: num(imp?.priorBalance),
      editable: true,
      isDeduction: true,
    },
    {
      key: '__total__',
      label: '合  计',
      endBalance: net.endBalance,
      priorBalance: net.priorBalance,
      editable: false,
    },
  ]
}
