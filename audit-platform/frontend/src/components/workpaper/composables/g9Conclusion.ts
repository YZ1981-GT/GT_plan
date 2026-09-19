/**
 * G9 审计结论 A/B/C 口径模板 + 跨表汇总（对齐 G8）
 */
export const G9_CONCLUSION_OPTIONS = [
  { value: 'A', label: 'A — 充分恰当 / 未见异常' },
  { value: 'B', label: 'B — 除已调整事项外未见异常' },
  { value: 'C', label: 'C — 重大未调整或范围受限，不可确认' },
] as const

export type G9ConclusionOption = '' | 'A' | 'B' | 'C'

export const G9_CONCLUSION_TEMPLATES: Record<'A' | 'B' | 'C', string> = {
  A: 'A、经复核程序执行充分、依据恰当，未见异常，相关认定可确认。',
  B: 'B、除上述已调整（或已说明）事项外，其余未见异常。',
  C: 'C、由于存在重大未调整事项或审计范围受限，不可确认。',
}

/** 从结论文本推断 A/B/C（兼容纯文本历史数据） */
export function inferG9ConclusionOption(text: string): G9ConclusionOption {
  const t = (text || '').trim()
  if (/^A[、,.，]/.test(t) || t.startsWith('A、') || t.startsWith('A.')) return 'A'
  if (/^B[、,.，]/.test(t) || t.startsWith('B、') || t.startsWith('B.')) return 'B'
  if (/^C[、,.，]/.test(t) || t.startsWith('C、') || t.startsWith('C.')) return 'C'
  return ''
}

export function applyG9ConclusionTemplate(
  option: string,
  existingText: string,
): string {
  const key = option as 'A' | 'B' | 'C'
  const template = G9_CONCLUSION_TEMPLATES[key]
  if (!template) return existingText
  if (!existingText?.trim()) return template
  if (existingText.trim() === template) return existingText
  return template
}

export interface G9SheetConclusionItem {
  code: string
  name: string
  option: G9ConclusionOption
  text: string
  filled: boolean
}

/** 各子表结论文本/选项键（优先 option 键，否则从文本推断） */
const G9_CONCLUSION_SOURCES: Array<{
  code: string
  name: string
  textKeys: Array<{ key: string; field: 'remark' | 'conclusion' }>
  optionKey?: string
}> = [
  {
    code: 'G9-1',
    name: '审定表',
    textKeys: [
      { key: 'G9-adj-conclusion', field: 'conclusion' },
      { key: 'G9-adjudication-audit-conclusion', field: 'conclusion' },
    ],
  },
  {
    code: 'G9-2',
    name: '明细表',
    textKeys: [{ key: 'G9-detail-audit-conclusion', field: 'conclusion' }],
  },
  {
    code: 'G9-3',
    name: '调整分录',
    textKeys: [{ key: 'G9-adjustment-audit-conclusion', field: 'conclusion' }],
  },
  {
    code: 'G9-4',
    name: '公允测试',
    textKeys: [{ key: 'G9-fv-conclusion', field: 'conclusion' }],
  },
  {
    code: 'G9-5',
    name: 'L3调节',
    textKeys: [{ key: 'G9-l3-conclusion', field: 'conclusion' }],
  },
  {
    code: 'G9-6',
    name: '凭证检查',
    textKeys: [
      { key: 'G9-voucher-conclusion', field: 'conclusion' },
      { key: 'G9-voucher-audit-conclusion', field: 'conclusion' },
    ],
  },
]

function readResponseText(
  m: Map<string, any>,
  key: string,
  field: 'remark' | 'conclusion',
): string {
  const row = m.get(key)
  if (!row) return ''
  // 优先目标字段，兼容历史写在另一字段的数据
  const primary = String(row[field] ?? '').trim()
  if (primary) return primary
  const fallback = field === 'conclusion' ? row.remark : row.conclusion
  return String(fallback ?? '').trim()
}

/** 汇总各子表 A/B/C 结论，供底稿目录看板使用 */
export function collectG9SheetConclusions(m: Map<string, any>): G9SheetConclusionItem[] {
  return G9_CONCLUSION_SOURCES.map((src) => {
    let text = ''
    for (const tk of src.textKeys) {
      text = readResponseText(m, tk.key, tk.field)
      if (text) break
    }
    let option: G9ConclusionOption = ''
    if (src.optionKey) {
      const opt = String(m.get(src.optionKey)?.conclusion ?? '').trim()
      if (opt === 'A' || opt === 'B' || opt === 'C') option = opt
    }
    if (!option) option = inferG9ConclusionOption(text)
    return {
      code: src.code,
      name: src.name,
      option,
      text,
      filled: !!(text || option),
    }
  })
}

/** C > B > 未填 > 全 A */
export function summarizeG9Conclusions(
  items: G9SheetConclusionItem[],
): { worst: G9ConclusionOption | 'empty'; filled: number; total: number } {
  const filled = items.filter((i) => i.filled).length
  if (items.some((i) => i.option === 'C')) return { worst: 'C', filled, total: items.length }
  if (items.some((i) => i.option === 'B')) return { worst: 'B', filled, total: items.length }
  if (filled === 0) return { worst: 'empty', filled, total: items.length }
  if (items.filter((i) => i.filled).every((i) => i.option === 'A')) {
    return { worst: 'A', filled, total: items.length }
  }
  return { worst: 'empty', filled, total: items.length }
}
