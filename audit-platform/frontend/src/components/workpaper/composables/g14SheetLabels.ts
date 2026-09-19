/** G14 sheet 编码 → render-config sheet_name 映射 */
import type { GCycleIndexRowDef } from './g12SheetLabels'

export interface G14AProcedureMark {
  key: string
  label: string
}

export function collectG14AProcedureMarks(m: Map<string, any>): G14AProcedureMark[] {
  const marks: G14AProcedureMark[] = []
  const voucher = m.get('G14A-voucher-complete')
  if (voucher?.conclusion === 'completed' || voucher?.remark) {
    marks.push({ key: 'voucher', label: '凭证/程序回填' })
  }
  return marks
}

export const G14_SHEET_LABEL_MAP: Record<string, string> = {
  G14: '底稿目录',
  'G14-目录': '底稿目录',
  G14A: '信用减值损失审计程序表G14A',
  'G14-1': '审定表G14-1',
  'G14-2': '明细表G14-2',
  'G14-3': '调整分录汇总G14-3',
  附注上市: '附注披露信息（上市公司）',
  附注国企: '附注披露信息（国企）',
}

export const G14_INDEX_ROWS: GCycleIndexRowDef[] = [
  { seq: 1, name: '底稿目录', code: 'G14-目录', group: '核心', applicable: true },
  { seq: 2, name: 'G14A 审计程序表', code: 'G14A', group: '核心', applicable: true },
  { seq: 3, name: 'G14-1 审定表', code: 'G14-1', group: '核心', applicable: true },
  { seq: 4, name: 'G14-2 明细表', code: 'G14-2', group: '核心', applicable: true },
  { seq: 5, name: 'G14-3 调整分录', code: 'G14-3', group: '核心', applicable: true },
  { seq: 6, name: '附注披露（上市公司）', code: '附注上市', group: '核心', applicable: true },
  { seq: 7, name: '附注披露（国企）', code: '附注国企', group: '核心', applicable: true },
]

export function resolveG14SheetLabel(
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
    if (code === 'G14-目录' || code === 'G14') {
      const dir = availableSheets.find(s => s.sheet_name?.includes('底稿目录'))
      if (dir?.sheet_name) return dir.sheet_name
    }
    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`)
    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name
  }
  return G14_SHEET_LABEL_MAP[code] ?? code
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

export function isG14SheetComplete(code: string, m: Map<string, any>): boolean {
  switch (code) {
    case 'G14-目录':
      return true
    case 'G14A':
      return collectG14AProcedureMarks(m).length > 0
        || [...m.keys()].some(k => k.startsWith('G14A-'))
    case 'G14-1':
      return m.has('G14-adj-prior') || m.has('G14-adj-tb') || m.has('G14-1-adjudicated-amount')
    case 'G14-2':
      return hasJsonRows(m, 'G14-detail-rows')
    case 'G14-3':
      return hasJsonRows(m, 'G14-aje-rows')
    case '附注上市':
      return m.has('G14-disclosure-listed')
    case '附注国企':
      return m.has('G14-disclosure-soe')
    default:
      return false
  }
}
