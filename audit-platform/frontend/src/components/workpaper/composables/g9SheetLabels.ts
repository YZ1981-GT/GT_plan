import type { GCycleIndexRowDef } from './g12SheetLabels'

export interface G9AProcedureMark {
  key: string
  label: string
}

export function collectG9AProcedureMarks(m: Map<string, any>): G9AProcedureMark[] {
  const marks: G9AProcedureMark[] = []
  const voucher = m.get('G9A-voucher-complete')
  if (voucher?.conclusion === 'completed' || voucher?.remark) {
    marks.push({ key: 'voucher', label: '凭证/程序回填' })
  }
  const fv = m.get('G9A-fv-complete')
  if (fv?.conclusion === 'completed' || fv?.remark) {
    marks.push({ key: 'fv', label: '公允/L3 程序回填' })
  }
  return marks
}

export const G9_SHEET_LABEL_MAP: Record<string, string> = {
  G9: '底稿目录',
  'G9-目录': '底稿目录',
  G9A: '其他非流动金融资产实质性程序表G9A',
  'G9-1': '审定表G9-1',
  'G9-2': '明细表G9-2',
  'G9-3': '调整分录汇总G9-3',
  'G9-4': '公允价值测试表G9-4',
  'G9-5': '第三层次公允价值计量的调节表G9-5',
  'G9-6': '凭证检查表G9-6',
  附注上市: '附注披露信息（上市公司）',
  附注国企: '附注披露信息（国企）',
}

export const G9_INDEX_ROWS: GCycleIndexRowDef[] = [
  { seq: 1, name: '底稿目录', code: 'G9-目录', group: '核心', applicable: true },
  { seq: 2, name: 'G9A 实质性程序表', code: 'G9A', group: '核心', applicable: true },
  { seq: 3, name: 'G9-1 审定表', code: 'G9-1', group: '核心', applicable: true },
  { seq: 4, name: 'G9-2 明细表', code: 'G9-2', group: '核心', applicable: true },
  { seq: 5, name: 'G9-3 调整分录', code: 'G9-3', group: '核心', applicable: true },
  { seq: 6, name: 'G9-4 公允价值测试', code: 'G9-4', group: '分析', applicable: true },
  { seq: 7, name: 'G9-5 L3调节表', code: 'G9-5', group: '分析', applicable: true },
  { seq: 8, name: 'G9-6 凭证检查', code: 'G9-6', group: '检查', applicable: true },
  { seq: 9, name: '附注披露（上市公司）— 监管主体选填其一', code: '附注上市', group: '附注', applicable: true },
  { seq: 10, name: '附注披露（国企）— 监管主体选填其一', code: '附注国企', group: '附注', applicable: true },
]

export function resolveG9SheetLabel(
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
    if (code === 'G9-目录' || code === 'G9') {
      const dir = availableSheets.find(s => s.sheet_name?.includes('底稿目录'))
      if (dir?.sheet_name) return dir.sheet_name
    }
    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`)
    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name
  }
  return G9_SHEET_LABEL_MAP[code] ?? code
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

export function isG9SheetComplete(code: string, m: Map<string, any>): boolean {
  switch (code) {
    case 'G9-目录':
      return true
    case 'G9A':
      return collectG9AProcedureMarks(m).length > 0
        || [...m.keys()].some(k => k.startsWith('G9A-'))
    case 'G9-1':
      return m.has('G9-adj-rows') || m.has('G9-adj-tb') || m.has('G9-1-adjudicated-amount')
    case 'G9-2':
      return hasJsonRows(m, 'G9-detail-rows')
    case 'G9-3':
      return hasJsonRows(m, 'G9-adjustment-rows')
    case 'G9-4':
      return hasJsonRows(m, 'G9-fv-test-rows')
    case 'G9-5':
      return hasJsonRows(m, 'G9-l3-rows')
    case 'G9-6':
      return hasJsonRows(m, 'G9-voucher-rows')
    case '附注上市':
      return m.has('G9-disclosure-listed')
    case '附注国企':
      return m.has('G9-disclosure-soe')
    default:
      return false
  }
}

export function extractG9SheetCode(sheetName: string): string {
  if (/底稿目录/.test(sheetName)) return '底稿目录'
  if (/附注披露/.test(sheetName)) return sheetName.includes('国企') ? '附注国企' : '附注上市'
  const m = sheetName.match(/(G9A|G9-\d+)/)
  return m ? m[1] : ''
}

/** 解析 G9 sheet 显示名并跳转（依赖 inject jumpToSection） */
export function jumpToG9Sheet(
  code: string,
  jumpFn: ((sheetLabel: string) => void) | null | undefined,
  availableSheets?: Array<{ sheet_name?: string }>,
): boolean {
  if (!jumpFn) return false
  const label = resolveG9SheetLabel(code, availableSheets) || G9_SHEET_LABEL_MAP[code] || code
  jumpFn(label)
  return true
}
