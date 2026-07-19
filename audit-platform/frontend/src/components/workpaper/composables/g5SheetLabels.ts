/** G5 长期应收款 — sheetName ↔ 内部分发编码 / Excel sheet 名 */

/** 编码 → 默认 Excel sheet_name（无 availableSheets 时兜底） */
export const G5_SHEET_LABEL_MAP: Record<string, string> = {
  底稿目录: '底稿目录',
  G5A: '长期应收款实质性程序表G5A',
  'G5-1': '审定表G5-1',
  'G5-2': '余额明细表G5-2',
  'G5-3': '坏账准备明细表G5-3',
  'G5-4': '调整分录汇总G5-4',
  'G5-5': '未实现融资收益测算表（租赁）G5-5',
  'G5-6': '未实现融资收益测算表（分期收款销售）G5-6',
  'G5-7': '保理业务核查表G5-7',
  'G5-8': '会计政策检查表G5-8',
  'G5-9': '三阶段划分检查表G5-9',
  'G5-10': '坏账准备测算表G5-10',
  'G5-11': '坏账准备转回核销检查表G5-11',
  'G5-12': '凭证检查表G5-12',
  附注上市: '附注披露信息（上市公司）',
  附注国企: '附注披露信息（国有企业）',
}

/** 目录展示短名 */
export const G5_DIRECTORY_ROWS: Array<{ seq: number; indexCode: string; name: string }> = [
  { seq: 1, indexCode: 'G5A', name: '长期应收款实质性程序表' },
  { seq: 2, indexCode: 'G5-1', name: '长期应收款审定表' },
  { seq: 3, indexCode: 'G5-2', name: '长期应收款余额明细表' },
  { seq: 4, indexCode: 'G5-3', name: '坏账准备明细表' },
  { seq: 5, indexCode: 'G5-4', name: '调整分录汇总' },
  { seq: 6, indexCode: 'G5-5', name: '融资租赁测算表' },
  { seq: 7, indexCode: 'G5-6', name: '分期销售测算表' },
  { seq: 8, indexCode: 'G5-7', name: '保理核查表' },
  { seq: 9, indexCode: 'G5-8', name: '会计政策检查' },
  { seq: 10, indexCode: 'G5-9', name: '三阶段划分检查表' },
  { seq: 11, indexCode: 'G5-10', name: '坏账准备测算表' },
  { seq: 12, indexCode: 'G5-11', name: '转回核销检查' },
  { seq: 13, indexCode: 'G5-12', name: '凭证检查表' },
  { seq: 14, indexCode: '附注上市', name: '附注披露（上市公司）' },
  { seq: 15, indexCode: '附注国企', name: '附注披露（国有企业）' },
]

/** sheetName → 内部分发编码 */
export function extractG5SheetCode(sheetName: string): string {
  if (/底稿目录/.test(sheetName)) return '底稿目录'
  if (/G5-note-listed|附注披露.*上市|附注.*上市/.test(sheetName)) return '附注上市'
  if (/G5-note-soe|附注披露.*国企|附注.*国企/.test(sheetName)) return '附注国企'
  if (/附注/.test(sheetName)) return sheetName.includes('国企') ? '附注国企' : '附注上市'
  const m = sheetName.match(/(G5A|G5-1[0-2]|G5-[1-9])/i)
  if (!m) return ''
  return m[1].toUpperCase().replace(/^G5A$/i, 'G5A')
}

/**
 * 编码 → 真实 Excel sheet_name（OnlyOffice / 跳转）。
 * 优先从 availableSheets 按末尾编码匹配。
 */
export function resolveG5SheetLabel(
  code: string,
  availableSheets?: Array<{ sheet_name?: string }>,
  fallbackSheetName?: string,
): string {
  if (availableSheets?.length) {
    const escaped = code.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const codeRe = new RegExp(`${escaped}\\s*$`, 'i')
    const hit = availableSheets.find((s) => s.sheet_name && codeRe.test(s.sheet_name))
    if (hit?.sheet_name) return hit.sheet_name

    if (code === '附注上市') {
      const d = availableSheets.find(
        (s) => s.sheet_name?.includes('附注') && s.sheet_name?.includes('上市'),
      )
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === '附注国企') {
      const d = availableSheets.find(
        (s) =>
          s.sheet_name?.includes('附注') &&
          (s.sheet_name?.includes('国企') || s.sheet_name?.includes('国有')),
      )
      if (d?.sheet_name) return d.sheet_name
    }
    if (code === '底稿目录') {
      const d = availableSheets.find((s) => s.sheet_name?.includes('底稿目录'))
      if (d?.sheet_name) return d.sheet_name
    }
  }

  if (fallbackSheetName && extractG5SheetCode(fallbackSheetName) === code) {
    return fallbackSheetName
  }

  return G5_SHEET_LABEL_MAP[code] ?? fallbackSheetName ?? code
}
