/**
 * D6 sheet 编码 → render-config sheet_name 默认映射
 */
export interface D6IndexRowDef {
  seq: number
  name: string
  code: string
  group: string
  applicable: boolean
}

export const D6_SHEET_LABEL_MAP: Record<string, string> = {
  D6: '底稿目录',
  'D6-目录': '底稿目录',
  D6A: '实质性程序表D6A',
  'D6-1': '合同资产审定表D6-1',
  'D6-2': '合同资产明细表D6-2',
  'D6-3': '合同资产减值准备明细表D6-3',
  'D6-4': '调整分录汇总表D6-4',
  'D6-5': '关联关系及交易检查D6-5',
  'D6-6': '合同资产检查表D6-6',
  'D6-7': '合同资产减值准备会计政策检查D6-7',
  'D6-8': '合同资产减值准备测算D6-8',
  'D6-9': '减值准备转回核销检查D6-9',
  'D6-附注上市': '合同资产附注披露信息（上市公司）',
  'D6-附注国企': '合同资产附注披露信息（国企）',
}

export const D6_INDEX_ROWS: D6IndexRowDef[] = [
  { seq: 1, name: '底稿目录', code: 'D6', group: '核心', applicable: true },
  { seq: 2, name: '实质性程序表', code: 'D6A', group: '核心', applicable: true },
  { seq: 3, name: '合同资产审定表', code: 'D6-1', group: '核心', applicable: true },
  { seq: 4, name: '合同资产明细表', code: 'D6-2', group: '核心', applicable: true },
  { seq: 5, name: '减值准备明细表', code: 'D6-3', group: '核心', applicable: true },
  { seq: 6, name: '调整分录汇总', code: 'D6-4', group: '核心', applicable: true },
  { seq: 7, name: '关联关系及交易检查', code: 'D6-5', group: '检查', applicable: true },
  { seq: 8, name: '合同资产检查表', code: 'D6-6', group: '检查', applicable: true },
  { seq: 9, name: '减值政策检查', code: 'D6-7', group: '检查', applicable: true },
  { seq: 10, name: '减值准备测算', code: 'D6-8', group: '检查', applicable: true },
  { seq: 11, name: '转回核销检查', code: 'D6-9', group: '检查', applicable: true },
  { seq: 12, name: '附注披露（上市公司）', code: 'D6-附注上市', group: '核心', applicable: true },
  { seq: 13, name: '附注披露（国企）', code: 'D6-附注国企', group: '核心', applicable: true },
]

export const D6_PROC_INDEX_SHEET_MAP: Record<string, string> = {
  'D6-1': D6_SHEET_LABEL_MAP['D6-1'],
  'D6-2': D6_SHEET_LABEL_MAP['D6-2'],
  'D6-8': D6_SHEET_LABEL_MAP['D6-8'],
}

export function resolveD6SheetLabel(
  code: string,
  availableSheets?: Array<{ sheet_name?: string }>,
): string {
  if (availableSheets?.length) {
    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`)
    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name
    if (code === 'D6-附注上市' || code === '附注上市') {
      const d = availableSheets.find(s => s.sheet_name?.includes('附注') && s.sheet_name?.includes('上市'))
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === 'D6-附注国企' || code === '附注国企') {
      const d = availableSheets.find(s => s.sheet_name?.includes('附注') && (s.sheet_name?.includes('国企') || s.sheet_name?.includes('国有')))
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === 'D6' || code === 'D6-目录') {
      const d = availableSheets.find(s => s.sheet_name?.includes('目录'))
      if (d?.sheet_name) return d.sheet_name
    }
  }
  return D6_SHEET_LABEL_MAP[code] ?? code
}
