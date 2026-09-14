/** G12 sheet 编码 → render-config sheet_name 映射 */
import { collectG12AProcedureMarks } from './g12Conclusion'
import { isG12NetExposureSheetComplete } from './g12NetExposureComplete'

export interface GCycleIndexRowDef {
  seq: number
  name: string
  code: string
  group: string
  applicable: boolean
}

export const G12_SHEET_LABEL_MAP: Record<string, string> = {
  G12: '底稿目录',
  'G12-目录': '底稿目录',
  G12A: '净敞口套期收益审计程序表G12A',
  'G12-1': '审定表G12-1',
  'G12-2': '明细表G12-2',
  'G12-3': '调整分录汇总G12-3',
  'G12-4': '公允价值测试表G12-4',
  'G12-5': '风险净敞口检查表G12-5',
  'G12-6': '凭证检查表G12-6',
  附注上市: '附注披露信息（上市公司）',
  附注国企: '附注披露信息（国企）',
}

export const G12_INDEX_ROWS: GCycleIndexRowDef[] = [
  { seq: 1, name: '底稿目录', code: 'G12-目录', group: '核心', applicable: true },
  { seq: 2, name: 'G12A 审计程序表', code: 'G12A', group: '核心', applicable: true },
  { seq: 3, name: 'G12-1 审定表', code: 'G12-1', group: '核心', applicable: true },
  { seq: 4, name: 'G12-2 净敞口套期收益明细', code: 'G12-2', group: '套期', applicable: true },
  { seq: 5, name: 'G12-3 调整分录汇总', code: 'G12-3', group: '核心', applicable: true },
  { seq: 6, name: 'G12-4 公允价值测试', code: 'G12-4', group: '套期', applicable: true },
  { seq: 7, name: 'G12-5 风险净敞口检查', code: 'G12-5', group: '套期', applicable: true },
  { seq: 8, name: 'G12-6 凭证检查', code: 'G12-6', group: '凭证', applicable: true },
  { seq: 9, name: '附注披露（上市公司）', code: '附注上市', group: '核心', applicable: true },
  { seq: 10, name: '附注披露（国企）', code: '附注国企', group: '核心', applicable: true },
]

function resolveNoteSheet(
  code: string,
  availableSheets?: Array<{ sheet_name?: string }>,
): string | undefined {
  if (!availableSheets?.length) return undefined
  if (code === '附注上市') {
    return availableSheets.find(s => s.sheet_name?.includes('附注') && s.sheet_name?.includes('上市'))?.sheet_name
  }
  if (code === '附注国企') {
    return availableSheets.find(s =>
      s.sheet_name?.includes('附注') && (s.sheet_name?.includes('国企') || s.sheet_name?.includes('国有')),
    )?.sheet_name
  }
  return undefined
}

export function resolveG12SheetLabel(
  code: string,
  availableSheets?: Array<{ sheet_name?: string }>,
): string {
  const noteHit = resolveNoteSheet(code, availableSheets)
  if (noteHit) return noteHit
  if (code === 'G12-目录' || code === 'G12') {
    const dir = availableSheets?.find(s => s.sheet_name?.includes('底稿目录'))
    if (dir?.sheet_name) return dir.sheet_name
    return '底稿目录'
  }
  if (availableSheets?.length) {
    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*$`)
    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name
  }
  return G12_SHEET_LABEL_MAP[code] ?? code
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

export function isG12SheetComplete(code: string, m: Map<string, any>): boolean {
  switch (code) {
    case 'G12-目录':
      return true
    case 'G12A':
      return collectG12AProcedureMarks(m).length > 0
        || [...m.keys()].some(k => k.startsWith('G12A-'))
    case 'G12-1':
      return m.has('G12-adj-prior') || m.has('G12-1-adjudicated-amount')
    case 'G12-2':
      return hasJsonRows(m, 'G12-hedge-detail-rows')
    case 'G12-3':
      return hasJsonRows(m, 'G12-aje-rows')
    case 'G12-4':
      return hasJsonRows(m, 'G12-fv-test-rows')
    case 'G12-5':
      return isG12NetExposureSheetComplete(m)
    case 'G12-6':
      return hasJsonRows(m, 'G12-voucher-rows')
    case '附注上市':
      return m.has('G12-disclosure-listed')
    case '附注国企':
      return m.has('G12-disclosure-soe')
    default:
      return false
  }
}
