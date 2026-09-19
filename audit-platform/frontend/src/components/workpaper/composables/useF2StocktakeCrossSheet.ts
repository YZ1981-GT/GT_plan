/**
 * 监盘跨表种子：从 F2-22/F2-23 读取被审计单位与时点，供 F2-24~26 带入。
 */
import type { ChecklistResponse } from './useF2StocktakeFormData'

export interface StocktakeMetaSeed {
  entityName: string
  /** 资产负债表日 / 截止日 YYYY-MM-DD 或原文 */
  bsDate: string
  /** 监盘/盘点日（尽量归一为日期） */
  countDate: string
  source: 'F2-22' | 'F2-23' | ''
}

function parseFieldsRemark(raw: string | undefined | null): Record<string, string> {
  if (!raw) return {}
  try {
    return JSON.parse(raw) as Record<string, string>
  } catch {
    return {}
  }
}

/** 从叙述中尽量抽出首个日期 */
export function extractDateToken(raw: string): string {
  const s = (raw || '').trim()
  if (!s) return ''
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s
  const m = s.match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?/)
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`
  const m2 = s.match(/(\d{4})[./-](\d{1,2})[./-](\d{1,2})/)
  if (m2) return `${m2[1]}-${m2[2].padStart(2, '0')}-${m2[3].padStart(2, '0')}`
  return s
}

export function readStocktakeMetaSeed(
  allResponses: Map<string, ChecklistResponse>,
): StocktakeMetaSeed {
  const from22 = parseFieldsRemark(allResponses.get('F2-22-fields')?.remark)
  const from23 = parseFieldsRemark(allResponses.get('F2-23-fields')?.remark)

  const pick = (key: string): { value: string; source: 'F2-22' | 'F2-23' | '' } => {
    const a = (from22[key] || '').trim()
    if (a) return { value: a, source: 'F2-22' }
    const b = (from23[key] || '').trim()
    if (b) return { value: b, source: 'F2-23' }
    return { value: '', source: '' }
  }

  const entity = pick('entityName')
  const bs = pick('bsDate')
  const count = pick('countDate')

  let source: StocktakeMetaSeed['source'] = ''
  if (entity.source || bs.source || count.source) {
    source = entity.source || bs.source || count.source
  }

  return {
    entityName: entity.value,
    bsDate: extractDateToken(bs.value),
    countDate: extractDateToken(count.value),
    source,
  }
}

/** 仅填空字段；返回实际写入的 key 列表 */
export function applyMetaSeedToFields(
  seed: StocktakeMetaSeed,
  current: Record<string, string>,
  mapping: { entityName?: string; bsDate?: string; countDate?: string },
): Record<string, string> {
  const patch: Record<string, string> = {}
  if (mapping.entityName && seed.entityName && !(current[mapping.entityName] || '').trim()) {
    patch[mapping.entityName] = seed.entityName
  }
  if (mapping.bsDate && seed.bsDate && !(current[mapping.bsDate] || '').trim()) {
    patch[mapping.bsDate] = seed.bsDate
  }
  if (mapping.countDate && seed.countDate && !(current[mapping.countDate] || '').trim()) {
    patch[mapping.countDate] = seed.countDate
  }
  return patch
}

export function parseJsonRows<T extends { id?: string }>(
  allResponses: Map<string, ChecklistResponse>,
  key: string,
): T[] {
  const raw = allResponses.get(key)?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as T[]) : []
  } catch {
    return []
  }
}

/** 供 AI relatedContext 注入的差异行摘要（最多 max 行） */
export function formatVarianceSummary(
  rows: Array<{
    itemName?: string
    qtyDiff?: number
    amtDiff?: number
    variance?: number
    bookQty?: number
    erpQty?: number
    sampleQty?: number
    clientCountQty?: number
    calcBsQty?: number
    varianceReason?: string
    hasVariance?: boolean
  }>,
  opts?: { max?: number; label?: string },
): string {
  const max = opts?.max ?? 12
  const label = opts?.label ?? '差异行'
  const list = rows.filter((r) => r.hasVariance !== false).slice(0, max)
  if (!list.length) return `${label}：无`
  const lines = list.map((r, i) => {
    const name = (r.itemName || `行${i + 1}`).trim() || `行${i + 1}`
    const parts: string[] = [name]
    if (r.qtyDiff != null) parts.push(`数量差=${r.qtyDiff}`)
    else if (r.variance != null) parts.push(`差异=${r.variance}`)
    if (r.amtDiff != null) parts.push(`金额差=${r.amtDiff}`)
    if (r.bookQty != null && r.erpQty != null) parts.push(`账面${r.bookQty}/ERP${r.erpQty}`)
    if (r.bookQty != null && r.sampleQty != null) {
      parts.push(`账面${r.bookQty}/抽盘${r.sampleQty}`)
    }
    if (r.calcBsQty != null && r.bookQty != null) {
      parts.push(`推算${r.calcBsQty}/账面${r.bookQty}`)
    }
    if (r.varianceReason) parts.push(`原因:${r.varianceReason}`)
    return parts.join('，')
  })
  const more = rows.length > max ? `；另有 ${rows.length - max} 行未列示` : ''
  return `${label}（${list.length}）：${lines.join('；')}${more}`
}
