/**
 * D5 sheet 编码 → render-config sheet_name 默认映射
 */
export interface D5IndexRowDef {
  seq: number
  name: string
  code: string
  group: string
  applicable: boolean
}

export const D5_SHEET_LABEL_MAP: Record<string, string> = {
  D5: '底稿目录',
  'D5-目录': '底稿目录',
  D5A: '应收款项融资审计程序表D5A',
  'D5-1': '应收款项融资审定表D5-1',
  'D5-2': '应收款项融资明细表D5-2',
  'D5-3': '应收款项融资调整分录汇总D5-3',
  'D5-4': '应收款项融资公允价值测算D5-4',
  'D5-附注上市': '附注披露信息（上市公司）',
  'D5-附注国企': '附注披露信息（国企）',
}

export const D5_INDEX_ROWS: D5IndexRowDef[] = [
  { seq: 1, name: '底稿目录', code: 'D5', group: '核心', applicable: true },
  { seq: 2, name: '应收款项融资审计程序表', code: 'D5A', group: '核心', applicable: true },
  { seq: 3, name: '应收款项融资审定表', code: 'D5-1', group: '核心', applicable: true },
  { seq: 4, name: '应收款项融资明细表', code: 'D5-2', group: '核心', applicable: true },
  { seq: 5, name: '应收款项融资调整分录汇总', code: 'D5-3', group: '核心', applicable: true },
  { seq: 6, name: '应收款项融资公允价值测算', code: 'D5-4', group: '核心', applicable: true },
  { seq: 7, name: '附注披露信息（上市公司）', code: 'D5-附注上市', group: '核心', applicable: true },
  { seq: 8, name: '附注披露信息（国企）', code: 'D5-附注国企', group: '核心', applicable: true },
]

/** 程序表索引号 → sheet_label */
export const D5_PROC_INDEX_SHEET_MAP: Record<string, string> = {
  'D5-1': D5_SHEET_LABEL_MAP['D5-1'],
  'D5-2': D5_SHEET_LABEL_MAP['D5-2'],
  'D5-4': D5_SHEET_LABEL_MAP['D5-4'],
}

export function resolveD5SheetLabel(
  code: string,
  availableSheets?: Array<{ sheet_name?: string }>,
): string {
  if (availableSheets?.length) {
    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`)
    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name
    if (code === 'D5-附注上市' || code === '附注上市') {
      const d = availableSheets.find(s => s.sheet_name?.includes('附注') && s.sheet_name?.includes('上市'))
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === 'D5-附注国企' || code === '附注国企') {
      const d = availableSheets.find(s => s.sheet_name?.includes('附注') && (s.sheet_name?.includes('国企') || s.sheet_name?.includes('国有')))
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === 'D5' || code === 'D5-目录') {
      const d = availableSheets.find(s => s.sheet_name?.includes('目录'))
      if (d?.sheet_name) return d.sheet_name
    }
  }
  return D5_SHEET_LABEL_MAP[code] ?? code
}
