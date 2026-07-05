/** G13 sheet 编码 → render-config sheet_name 映射 */
import type { GCycleIndexRowDef } from './g12SheetLabels'

export const G13_SHEET_LABEL_MAP: Record<string, string> = {
  G13: '底稿目录',
  'G13-目录': '底稿目录',
  G13A: '公允价值变动收益审计程序表G13A',
  'G13-1': '审定表G13-1',
  'G13-2': '明细表G13-2',
  'G13-3': '调整分录汇总G13-3',
  附注上市: '附注披露信息（上市公司）',
  附注国企: '附注披露信息（国企）',
}

export const G13_INDEX_ROWS: GCycleIndexRowDef[] = [
  { seq: 1, name: '底稿目录', code: 'G13-目录', group: '核心', applicable: true },
  { seq: 2, name: 'G13A 审计程序表', code: 'G13A', group: '核心', applicable: true },
  { seq: 3, name: 'G13-1 审定表', code: 'G13-1', group: '核心', applicable: true },
  { seq: 4, name: 'G13-2 明细表', code: 'G13-2', group: '核心', applicable: true },
  { seq: 5, name: 'G13-3 调整分录', code: 'G13-3', group: '核心', applicable: true },
  { seq: 6, name: '附注披露（上市公司）', code: '附注上市', group: '核心', applicable: true },
  { seq: 7, name: '附注披露（国企）', code: '附注国企', group: '核心', applicable: true },
]

export function resolveG13SheetLabel(
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
    if (code === 'G13-目录' || code === 'G13') {
      const dir = availableSheets.find(s => s.sheet_name?.includes('底稿目录'))
      if (dir?.sheet_name) return dir.sheet_name
    }
    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`)
    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name
  }
  return G13_SHEET_LABEL_MAP[code] ?? code
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

export function isG13SheetComplete(code: string, m: Map<string, any>): boolean {
  switch (code) {
    case 'G13-目录':
      return true
    case 'G13A':
      return [...m.keys()].some(k => k.startsWith('G13-proc-') || k.startsWith('G13A-'))
    case 'G13-1':
      return m.has('G13-adj-prior') || m.has('G13-1-adjudicated-amount')
    case 'G13-2':
      return hasJsonRows(m, 'G13-detail-rows')
    case 'G13-3':
      return hasJsonRows(m, 'G13-aje-rows')
    case '附注上市':
      return m.has('G13-disclosure-listed')
    case '附注国企':
      return m.has('G13-disclosure-soe')
    default:
      return false
  }
}
