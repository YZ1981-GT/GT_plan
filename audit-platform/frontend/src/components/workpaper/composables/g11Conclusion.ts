/**
 * G11 审计结论 A/B/C 口径 + 跨表汇总（对齐 G4 / G10）
 */
export type G11ConclusionOption = '' | 'A' | 'B' | 'C'

export interface G11SheetConclusionItem {
  code: string
  name: string
  option: G11ConclusionOption
  text: string
  filled: boolean
}

function inferG11ConclusionOption(text: string): G11ConclusionOption {
  const t = (text || '').trim()
  if (/^A[、,.，]/.test(t) || t.startsWith('A、') || t.startsWith('A.')) return 'A'
  if (/^B[、,.，]/.test(t) || t.startsWith('B、') || t.startsWith('B.')) return 'B'
  if (/^C[、,.，]/.test(t) || t.startsWith('C、') || t.startsWith('C.')) return 'C'
  return ''
}

const G11_CONCLUSION_SOURCES: Array<{
  code: string
  name: string
  textKeys: Array<{ key: string; field: 'remark' | 'conclusion' }>
}> = [
  {
    code: 'G11-1',
    name: '审定表',
    textKeys: [{ key: 'G11-adj-conclusion', field: 'conclusion' }],
  },
  {
    code: 'G11-2',
    name: '明细分析',
    textKeys: [{ key: 'G11-detail-audit-conclusion', field: 'conclusion' }],
  },
  {
    code: 'G11-3',
    name: '调整分录',
    textKeys: [{ key: 'G11-adjustment-audit-conclusion', field: 'conclusion' }],
  },
  {
    code: 'G11-4',
    name: '收益率分析',
    textKeys: [{ key: 'G11-return-rate-conclusion', field: 'conclusion' }],
  },
  {
    code: 'G11-5',
    name: '凭证检查',
    // 正式 A/B/C 结论优先；抽查结论文本次之（均写 conclusion，旧 remark 可读兜底）
    textKeys: [
      { key: 'G11-voucher-audit-conclusion', field: 'conclusion' },
      { key: 'G11-voucher-conclusion', field: 'conclusion' },
    ],
  },
]

/** 优先读指定字段，空则回退另一字段（兼容历史 remark/conclusion 混存） */
function readResponseText(
  m: Map<string, any>,
  key: string,
  field: 'remark' | 'conclusion',
): string {
  const row = m.get(key)
  if (!row) return ''
  const preferred = String(row[field] ?? '').trim()
  if (preferred) return preferred
  const other = field === 'conclusion' ? 'remark' : 'conclusion'
  return String(row[other] ?? '').trim()
}

export function collectG11SheetConclusions(m: Map<string, any>): G11SheetConclusionItem[] {
  return G11_CONCLUSION_SOURCES.map((src) => {
    let text = ''
    for (const tk of src.textKeys) {
      text = readResponseText(m, tk.key, tk.field)
      if (text) break
    }
    const option = inferG11ConclusionOption(text)
    return {
      code: src.code,
      name: src.name,
      option,
      text,
      filled: !!(text || option),
    }
  })
}

export function summarizeG11Conclusions(
  items: G11SheetConclusionItem[],
): { worst: G11ConclusionOption | 'empty'; filled: number; total: number } {
  const filled = items.filter((i) => i.filled).length
  if (items.some((i) => i.option === 'C')) return { worst: 'C', filled, total: items.length }
  if (items.some((i) => i.option === 'B')) return { worst: 'B', filled, total: items.length }
  if (filled === 0) return { worst: 'empty', filled, total: items.length }
  if (items.filter((i) => i.filled).every((i) => i.option === 'A')) {
    return { worst: 'A', filled, total: items.length }
  }
  return { worst: 'empty', filled, total: items.length }
}

export interface G11AProcedureMark {
  key: string
  label: string
}

export function collectG11AProcedureMarks(m: Map<string, any>): G11AProcedureMark[] {
  const marks: G11AProcedureMark[] = []
  const voucher = m.get('G11A-voucher-complete')
  if (voucher?.conclusion === 'completed' || voucher?.remark) {
    marks.push({ key: 'voucher', label: '凭证检查 seq3' })
  }
  return marks
}
