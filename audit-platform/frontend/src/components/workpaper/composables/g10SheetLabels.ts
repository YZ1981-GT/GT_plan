import type { GCycleIndexRowDef } from './g12SheetLabels'
import { collectG10AProcedureMarks } from './g10FvCrossHelpers'

export const G10_SHEET_LABEL_MAP: Record<string, string> = {
  G10: '底稿目录',
  'G10-目录': '底稿目录',
  G10A: '交易性金融负债实质性程序表G10A',
  'G10-1': '审定表G10-1',
  'G10-2': '明细表G10-2',
  'G10-3': '调整分录汇总G10-3',
  'G10-4': '分类的适当性检查表G10-4',
  'G10-5': '公允价值测试表G10-5',
  'G10-6': '第三层次公允价值计量的调节表G10-6',
  'G10-7': '凭证检查表G10-7',
  'G10-8': '衍生金融工具核查表G10-8',
  附注上市: '附注披露信息（上市公司）',
  附注国企: '附注披露信息（国企）',
}

export const G10_INDEX_ROWS: GCycleIndexRowDef[] = [
  { seq: 1, name: '底稿目录', code: 'G10-目录', group: '核心', applicable: true },
  { seq: 2, name: 'G10A 实质性程序表', code: 'G10A', group: '核心', applicable: true },
  { seq: 3, name: 'G10-1 审定表', code: 'G10-1', group: '核心', applicable: true },
  { seq: 4, name: 'G10-2 明细表', code: 'G10-2', group: '核心', applicable: true },
  { seq: 5, name: 'G10-3 调整分录', code: 'G10-3', group: '核心', applicable: true },
  { seq: 6, name: 'G10-4 分类适当性检查', code: 'G10-4', group: '检查', applicable: true },
  { seq: 7, name: 'G10-5 公允价值测试', code: 'G10-5', group: '分析', applicable: true },
  { seq: 8, name: 'G10-6 L3调节表', code: 'G10-6', group: '分析', applicable: true },
  { seq: 9, name: 'G10-7 凭证检查', code: 'G10-7', group: '检查', applicable: true },
  { seq: 10, name: 'G10-8 衍生工具核查', code: 'G10-8', group: '检查', applicable: true },
  { seq: 11, name: '附注披露（上市公司）', code: '附注上市', group: '附注', applicable: true },
  { seq: 12, name: '附注披露（国企）', code: '附注国企', group: '附注', applicable: true },
]

export function resolveG10SheetLabel(
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
    if (code === 'G10-目录' || code === 'G10') {
      const dir = availableSheets.find(s => s.sheet_name?.includes('底稿目录'))
      if (dir?.sheet_name) return dir.sheet_name
    }
    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`)
    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name
  }
  return G10_SHEET_LABEL_MAP[code] ?? code
}

function hasJsonRows(m: Map<string, any>, key: string): boolean {
  const item = m.get(key)
  const raw = item?.remark ?? item?.conclusion
  if (!raw) return false
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) && parsed.length > 0
  } catch {
    return false
  }
}

export function isG10SheetComplete(code: string, m: Map<string, any>): boolean {
  switch (code) {
    case 'G10-目录':
      return true
    case 'G10A':
      return collectG10AProcedureMarks(m).length > 0
        || [...m.keys()].some(k => k.startsWith('G10A-'))
    case 'G10-1':
      return m.has('G10-adj-rows') || m.has('G10-adj-tb')
    case 'G10-2':
      return hasJsonRows(m, 'G10-detail-rows')
    case 'G10-3':
      return hasJsonRows(m, 'G10-aje-rows')
    case 'G10-4':
      return hasJsonRows(m, 'G10-classification-rows')
        || !!m.get('G10-classification-conclusion')?.conclusion
    case 'G10-5':
      return hasJsonRows(m, 'G10-fv-test-rows')
    case 'G10-6':
      return hasJsonRows(m, 'G10-l3-rows')
    case 'G10-7':
      return hasJsonRows(m, 'G10-voucher-rows')
    case 'G10-8':
      return hasJsonRows(m, 'G10-derivative-rows')
        || !!m.get('G10-derivative-conclusion')?.conclusion
    case '附注上市':
      return m.has('G10-disclosure-listed')
    case '附注国企':
      return m.has('G10-disclosure-soe')
    default:
      return false
  }
}

/** 解析 G10 sheet 显示名并跳转（依赖 inject jumpToSection） */
export function jumpToG10Sheet(
  code: string,
  jumpFn: ((sheetLabel: string) => void) | null | undefined,
  availableSheets?: Array<{ sheet_name?: string }>,
): boolean {
  if (!jumpFn) return false
  const label = resolveG10SheetLabel(code, availableSheets) || G10_SHEET_LABEL_MAP[code] || code
  jumpFn(label)
  return true
}
