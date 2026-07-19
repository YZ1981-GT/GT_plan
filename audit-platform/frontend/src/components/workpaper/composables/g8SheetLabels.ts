import type { GCycleIndexRowDef } from './g12SheetLabels'

export const G8_SHEET_LABEL_MAP: Record<string, string> = {
  G8: '底稿目录',
  'G8-目录': '底稿目录',
  G8A: '其他权益工具投资实质性程序表G8A',
  'G8-1': '审定表G8-1',
  'G8-2': '明细表G8-2',
  'G8-3': '调整分录汇总G8-3',
  'G8-4': '公允价值测试表G8-4',
  'G8-5': '指定的适当性检查表G8-5',
  'G8-6': '凭证检查表G8-6',
  附注上市: '附注披露信息（上市公司）',
  附注国企: '附注披露信息（国企）',
}

export const G8_INDEX_ROWS: GCycleIndexRowDef[] = [
  { seq: 1, name: '底稿目录', code: 'G8-目录', group: '核心', applicable: true },
  { seq: 2, name: 'G8A 实质性程序表', code: 'G8A', group: '核心', applicable: true },
  { seq: 3, name: 'G8-1 审定表', code: 'G8-1', group: '核心', applicable: true },
  { seq: 4, name: 'G8-2 明细表', code: 'G8-2', group: '核心', applicable: true },
  { seq: 5, name: 'G8-3 调整分录', code: 'G8-3', group: '核心', applicable: true },
  { seq: 6, name: 'G8-4 公允价值测试', code: 'G8-4', group: '分析', applicable: true },
  { seq: 7, name: 'G8-5 适当性检查', code: 'G8-5', group: '分析', applicable: true },
  { seq: 8, name: 'G8-6 凭证检查', code: 'G8-6', group: '检查', applicable: true },
  { seq: 9, name: '附注披露（上市公司）', code: '附注上市', group: '附注', applicable: true },
  { seq: 10, name: '附注披露（国企）', code: '附注国企', group: '附注', applicable: true },
]

export function resolveG8SheetLabel(
  code: string,
  availableSheets?: Array<{ sheet_name?: string }>,
): string {
  if (availableSheets?.length) {
    if (code === '附注上市') {
      const d = availableSheets.find(s => s.sheet_name?.includes('附注') && s.sheet_name?.includes('上市'))
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === '附注国企') {
      const d = availableSheets.find(s =>
        s.sheet_name?.includes('附注') && (s.sheet_name?.includes('国企') || s.sheet_name?.includes('国有')),
      )
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === 'G8-目录' || code === 'G8') {
      const dir = availableSheets.find(s => s.sheet_name?.includes('底稿目录'))
      if (dir?.sheet_name) return dir.sheet_name
    }
    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`)
    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name
  }
  return G8_SHEET_LABEL_MAP[code] ?? code
}

function hasJsonRows(m: Map<string, any>, key: string): boolean {
  const raw = m.get(key)?.remark
  if (!raw) return false
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) && parsed.length > 0
  } catch {
    return false
  }
}

export function isG8SheetComplete(code: string, m: Map<string, any>): boolean {
  switch (code) {
    case 'G8-目录':
      return true
    case 'G8A':
      return [...m.keys()].some(k => k.startsWith('G8-proc-') || k.startsWith('G8A-'))
    case 'G8-1':
      return m.has('G8-adj-rows') || m.has('G8-adj-tb')
    case 'G8-2':
      return hasJsonRows(m, 'G8-detail-rows')
    case 'G8-3':
      return hasJsonRows(m, 'G8-adjustment-rows')
    case 'G8-4':
      return hasJsonRows(m, 'G8-fv-test-rows')
    case 'G8-5':
      return hasJsonRows(m, 'G8-designation-rows')
    case 'G8-6':
      return hasJsonRows(m, 'G8-voucher-rows')
    case '附注上市':
    case '附注国企':
      return m.has('G8-disclosure-listed') || m.has('G8-disclosure-soe')
    default:
      return false
  }
}

export function extractG8SheetCode(sheetName: string): string {
  if (!sheetName) return ''
  if (/G8-note-listed|附注披露.*上市|附注.*上市/.test(sheetName)) return '附注上市'
  if (/G8-note-soe|附注披露.*国企|附注.*国企/.test(sheetName)) return '附注国企'
  if (/G8-directory|底稿目录/.test(sheetName)) return '底稿目录'
  if (/附注/.test(sheetName)) return sheetName.includes('国企') ? '附注国企' : '附注上市'
  const m = sheetName.match(/(G8A|G8-\d+)/)
  return m ? m[1] : ''
}
