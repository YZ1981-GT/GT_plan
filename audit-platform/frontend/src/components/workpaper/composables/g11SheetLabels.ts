import type { GCycleIndexRowDef } from './g12SheetLabels'
import { collectG11AProcedureMarks } from './g11Conclusion'

export const G11_SHEET_LABEL_MAP: Record<string, string> = {
  G11: '底稿目录',
  'G11-目录': '底稿目录',
  G11A: '投资收益实质性程序表G11A',
  'G11-1': '审定表G11-1',
  'G11-2': '明细分析表G11-2',
  'G11-3': '调整分录汇总G11-3',
  'G11-4': '收益率分析表G11-4',
  'G11-5': '凭证检查表G11-5',
  附注上市: '附注披露信息（上市公司）',
  附注国企: '附注披露信息（国企）',
}

export const G11_INDEX_ROWS: GCycleIndexRowDef[] = [
  { seq: 1, name: '底稿目录', code: 'G11-目录', group: '核心', applicable: true },
  { seq: 2, name: 'G11A 实质性程序表', code: 'G11A', group: '核心', applicable: true },
  { seq: 3, name: 'G11-1 审定表', code: 'G11-1', group: '核心', applicable: true },
  { seq: 4, name: 'G11-2 明细分析表', code: 'G11-2', group: '核心', applicable: true },
  { seq: 5, name: 'G11-3 调整分录', code: 'G11-3', group: '核心', applicable: true },
  { seq: 6, name: 'G11-4 收益率分析', code: 'G11-4', group: '分析', applicable: true },
  { seq: 7, name: 'G11-5 凭证检查', code: 'G11-5', group: '检查', applicable: true },
  { seq: 8, name: '附注披露（上市公司）', code: '附注上市', group: '附注', applicable: true },
  { seq: 9, name: '附注披露（国企）', code: '附注国企', group: '附注', applicable: true },
]

export function resolveG11SheetLabel(
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
    if (code === 'G11-目录' || code === 'G11') {
      const dir = availableSheets.find(s => s.sheet_name?.includes('底稿目录'))
      if (dir?.sheet_name) return dir.sheet_name
    }
    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`)
    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name
  }
  return G11_SHEET_LABEL_MAP[code] ?? code
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

export function isG11SheetComplete(code: string, m: Map<string, any>): boolean {
  switch (code) {
    case 'G11-目录':
      return true
    case 'G11A':
      return collectG11AProcedureMarks(m).length > 0
        || [...m.keys()].some(k => k.startsWith('G11A-'))
    case 'G11-1':
      return m.has('G11-adj-rows') || m.has('G11-adj-tb')
    case 'G11-2':
      return hasJsonRows(m, 'G11-detail-rows')
    case 'G11-3':
      return hasJsonRows(m, 'G11-aje-rows')
    case 'G11-4':
      return hasJsonRows(m, 'G11-return-rate-rows') || !!m.get('G11-return-rate-conclusion')?.conclusion
    case 'G11-5':
      return hasJsonRows(m, 'G11-voucher-rows')
        || !!m.get('G11-vc-params')?.remark
        || !!m.get('G11-voucher-conclusion')?.conclusion
    case '附注上市':
      return m.has('G11-disclosure-listed')
    case '附注国企':
      return m.has('G11-disclosure-soe')
    default:
      return false
  }
}
