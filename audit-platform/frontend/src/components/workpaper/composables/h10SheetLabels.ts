import type { GCycleIndexRowDef } from './g12SheetLabels'
import { SOURCE_WP_OPTIONS } from './h10Constants'

export const H10_SHEET_LABEL_MAP: Record<string, string> = {
  H10: '底稿目录',
  'H10-目录': '底稿目录',
  H10A: '资产处置损益实质性程序表H10A',
  'H10-1': '审定表H10-1',
  'H10-2': '明细表H10-2',
  'H10-3': '调整分录汇总H10-3',
  'H10-4': '检查表H10-4',
  附注上市: '附注披露信息（上市公司）',
  附注国企: '附注披露信息（国有企业）',
}

export const H10_INDEX_ROWS: GCycleIndexRowDef[] = [
  { seq: 1, name: '底稿目录', code: 'H10-目录', group: '核心', applicable: true },
  { seq: 2, name: 'H10A 实质性程序表', code: 'H10A', group: '核心', applicable: true },
  { seq: 3, name: 'H10-1 审定表', code: 'H10-1', group: '核心', applicable: true },
  { seq: 4, name: 'H10-2 明细表', code: 'H10-2', group: '核心', applicable: true },
  { seq: 5, name: 'H10-3 调整分录', code: 'H10-3', group: '核心', applicable: true },
  { seq: 6, name: 'H10-4 检查表', code: 'H10-4', group: '检查', applicable: true },
  { seq: 7, name: '附注披露（上市公司）', code: '附注上市', group: '附注', applicable: true },
  { seq: 8, name: '附注披露（国有企业）', code: '附注国企', group: '附注', applicable: true },
]

export function extractH10SheetCode(sheetName: string): string {
  if (/底稿目录/.test(sheetName)) return '底稿目录'
  if (/附注披露/.test(sheetName)) {
    return sheetName.includes('国企') || sheetName.includes('国有') ? '附注国企' : '附注上市'
  }
  const m = sheetName.match(/(H10A|H10-\d+)/)
  return m ? m[1] : ''
}

export function resolveH10SheetLabel(
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
    if (code === 'H10-目录' || code === 'H10') {
      const dir = availableSheets.find(s => s.sheet_name?.includes('底稿目录'))
      if (dir?.sheet_name) return dir.sheet_name
    }
    const codeRe = new RegExp(`${code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`)
    const hit = availableSheets.find(s => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name
  }
  return H10_SHEET_LABEL_MAP[code] ?? code
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

export function isH10SheetComplete(code: string, m: Map<string, any>): boolean {
  switch (code) {
    case 'H10-目录':
    case '底稿目录':
      return true
    case 'H10A':
      return [...m.keys()].some(k => k.startsWith('H10-proc-') || k.startsWith('H10A-'))
    case 'H10-1':
      return m.has('H10-adj-rows') || m.has('H10-adj-tb')
    case 'H10-2':
      return hasJsonRows(m, 'H10-detail-rows')
    case 'H10-3':
      return hasJsonRows(m, 'H10-adjustment-rows')
    case 'H10-4':
      return hasJsonRows(m, 'H10-check-rows')
    case '附注上市':
      return m.has('H10-disclosure-listed')
    case '附注国企':
      return m.has('H10-disclosure-soe')
    default:
      return false
  }
}

export interface H10SourceTraceRow {
  wpCode: string
  label: string
  status: 'done' | 'pending' | 'empty'
}

function parseDetailRows(raw: string | null | undefined): any[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 底稿目录 — H1~H8 + H6 来源追溯链状态 */
export function getH10SourceTraceStatus(m: Map<string, any>): H10SourceTraceRow[] {
  const detailRows = parseDetailRows(m.get('H10-detail-rows')?.remark)
  const linked = new Set(detailRows.map((r) => String(r.sourceWp ?? '')).filter(Boolean))
  const h6Linked = linked.has('H6') || detailRows.some((r) => String(r.linkageId ?? '').startsWith('h6-'))

  const rows: H10SourceTraceRow[] = SOURCE_WP_OPTIONS.map((o) => {
    const count = detailRows.filter((r) => r.sourceWp === o.value).length
    let status: H10SourceTraceRow['status'] = 'empty'
    if (count > 0) status = 'done'
    else if (o.value !== 'OTHER') status = 'pending'
    return { wpCode: o.value, label: o.label, status }
  })

  rows.push({
    wpCode: 'H6',
    label: 'H6 固定资产清理',
    status: h6Linked ? 'done' : 'pending',
  })

  return rows
}
