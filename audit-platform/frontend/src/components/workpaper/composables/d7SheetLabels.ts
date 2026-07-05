/**
 * D7 sheet 编码 → render-config sheet_name 默认映射
 */
export interface D7IndexRowDef {
  seq: number
  name: string
  code: string
  group: string
  applicable: boolean
}

export const D7_SHEET_LABEL_MAP: Record<string, string> = {
  D7: '底稿目录',
  'D7-目录': '底稿目录',
  D7A: '合同负债审计程序表D7A',
  'D7-1': '合同负债审定表D7-1',
  'D7-2': '合同负债明细表D7-2',
  'D7-3': '合同负债调整分录汇总D7-3',
  'D7-4': '合同负债分析表D7-4',
  'D7-5': '账龄1年以上合同负债检查D7-5',
  'D7-6': '关联方合同负债检查D7-6',
  'D7-7': '合同负债凭证检查D7-7',
  'D7-附注上市': '合同负债附注披露信息（上市公司）',
  'D7-附注国企': '合同负债附注披露信息（国企）',
}

export const D7_INDEX_ROWS: D7IndexRowDef[] = [
  { seq: 1, name: '底稿目录', code: 'D7', group: '核心', applicable: true },
  { seq: 2, name: '合同负债审计程序表', code: 'D7A', group: '核心', applicable: true },
  { seq: 3, name: '合同负债审定表', code: 'D7-1', group: '核心', applicable: true },
  { seq: 4, name: '合同负债明细表', code: 'D7-2', group: '核心', applicable: true },
  { seq: 5, name: '调整分录汇总', code: 'D7-3', group: '核心', applicable: true },
  { seq: 6, name: '合同负债分析表', code: 'D7-4', group: '分析', applicable: true },
  { seq: 7, name: '账龄1年以上检查', code: 'D7-5', group: '检查', applicable: true },
  { seq: 8, name: '关联方检查', code: 'D7-6', group: '检查', applicable: true },
  { seq: 9, name: '凭证检查', code: 'D7-7', group: '检查', applicable: true },
  { seq: 10, name: '附注披露（上市公司）', code: 'D7-附注上市', group: '核心', applicable: true },
  { seq: 11, name: '附注披露（国企）', code: 'D7-附注国企', group: '核心', applicable: true },
]

export const D7_PROC_INDEX_SHEET_MAP: Record<string, string> = {
  'D7-1': D7_SHEET_LABEL_MAP['D7-1'],
  'D7-2': D7_SHEET_LABEL_MAP['D7-2'],
  'D7-7': D7_SHEET_LABEL_MAP['D7-7'],
}

export function resolveD7SheetLabel(
  code: string,
  availableSheets?: Array<{ sheet_name?: string }>,
): string {
  if (availableSheets?.length) {
    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`)
    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name
    if (code === 'D7-附注上市' || code === '附注上市') {
      const d = availableSheets.find(s => s.sheet_name?.includes('附注') && s.sheet_name?.includes('上市'))
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === 'D7-附注国企' || code === '附注国企') {
      const d = availableSheets.find(s => s.sheet_name?.includes('附注') && (s.sheet_name?.includes('国企') || s.sheet_name?.includes('国有')))
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === 'D7' || code === 'D7-目录') {
      const d = availableSheets.find(s => s.sheet_name?.includes('目录'))
      if (d?.sheet_name) return d.sheet_name
    }
  }
  return D7_SHEET_LABEL_MAP[code] ?? code
}
