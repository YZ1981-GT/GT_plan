/**
 * G12 审计结论 A/B/C 口径 + 跨表汇总（对齐 G4 / G11）
 */
export type G12ConclusionOption = '' | 'A' | 'B' | 'C'

export interface G12SheetConclusionItem {
  code: string
  name: string
  option: G12ConclusionOption
  text: string
  filled: boolean
}

function inferG12ConclusionOption(text: string): G12ConclusionOption {
  const t = (text || '').trim()
  if (/^A[、,.，]/.test(t) || t.startsWith('A、') || t.startsWith('A.')) return 'A'
  if (/^B[、,.，]/.test(t) || t.startsWith('B、') || t.startsWith('B.')) return 'B'
  if (/^C[、,.，]/.test(t) || t.startsWith('C、') || t.startsWith('C.')) return 'C'
  return ''
}

const G12_CONCLUSION_SOURCES: Array<{
  code: string
  name: string
  textKeys: Array<{ key: string; field: 'remark' | 'conclusion' }>
}> = [
  {
    code: 'G12-1',
    name: '审定表',
    textKeys: [{ key: 'G12-adj-conclusion', field: 'conclusion' }],
  },
  {
    code: 'G12-2',
    name: '套期明细',
    textKeys: [{ key: 'G12-hedge-detail-audit-conclusion', field: 'remark' }],
  },
  {
    code: 'G12-3',
    name: '调整分录',
    textKeys: [{ key: 'G12-adjustment-audit-conclusion', field: 'remark' }],
  },
  {
    code: 'G12-4',
    name: '公允测试',
    textKeys: [{ key: 'G12-fv-test-conclusion', field: 'conclusion' }],
  },
  {
    code: 'G12-5',
    name: '净敞口头寸',
    textKeys: [{ key: 'G12-net-exposure-conclusion', field: 'conclusion' }],
  },
  {
    code: 'G12-6',
    name: '凭证检查',
    textKeys: [{ key: 'G12-voucher-conclusion', field: 'conclusion' }],
  },
]

function readResponseText(
  m: Map<string, any>,
  key: string,
  field: 'remark' | 'conclusion',
): string {
  const row = m.get(key)
  if (!row) return ''
  return String(row[field] ?? '').trim()
}

export function collectG12SheetConclusions(m: Map<string, any>): G12SheetConclusionItem[] {
  return G12_CONCLUSION_SOURCES.map((src) => {
    let text = ''
    for (const tk of src.textKeys) {
      text = readResponseText(m, tk.key, tk.field)
      if (text) break
    }
    const option = inferG12ConclusionOption(text)
    return {
      code: src.code,
      name: src.name,
      option,
      text,
      filled: !!(text || option),
    }
  })
}

export function summarizeG12Conclusions(
  items: G12SheetConclusionItem[],
): { worst: G12ConclusionOption | 'empty'; filled: number; total: number } {
  const filled = items.filter((i) => i.filled).length
  if (items.some((i) => i.option === 'C')) return { worst: 'C', filled, total: items.length }
  if (items.some((i) => i.option === 'B')) return { worst: 'B', filled, total: items.length }
  if (filled === 0) return { worst: 'empty', filled, total: items.length }
  if (items.filter((i) => i.filled).every((i) => i.option === 'A')) {
    return { worst: 'A', filled, total: items.length }
  }
  return { worst: 'empty', filled, total: items.length }
}

export interface G12AProcedureMark {
  key: string
  label: string
}

export function collectG12AProcedureMarks(m: Map<string, any>): G12AProcedureMark[] {
  const marks: G12AProcedureMark[] = []
  const voucher = m.get('G12A-voucher-complete')
  if (voucher?.conclusion === 'completed' || voucher?.remark) {
    marks.push({ key: 'voucher', label: '凭证检查 seq10' })
  }
  return marks
}
