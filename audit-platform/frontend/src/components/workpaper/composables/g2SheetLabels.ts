/** G2 应收利息 — sheetName ↔ 内部分发编码 / Excel sheet 名 */

/** 编码 → 默认 Excel sheet_name（无 availableSheets 时兜底） */
export const G2_SHEET_LABEL_MAP: Record<string, string> = {
  底稿目录: '底稿目录',
  G2A: '应收利息实质性程序表G2A',
  'G2-1': '审定表G2-1',
  'G2-2': '明细表G2-2',
  'G2-3': '坏账准备明细表G2-3',
  'G2-4': '调整分录汇总G2-4',
  'G2-5': '利息测算表G2-5',
  'G2-6': '长期未收回检查表G2-6',
  'G2-7': '坏账准备测算表G2-7',
  'G2-8': '凭证检查表G2-8',
  附注上市: '附注披露信息（上市公司）',
  附注国企: '附注披露信息（国有企业）',
}

/** 目录展示短名（对齐 D4TabIndex 静态清单） */
export const G2_DIRECTORY_ROWS: Array<{ seq: number; indexCode: string; name: string }> = [
  { seq: 1, indexCode: 'G2A', name: '应收利息实质性程序表' },
  { seq: 2, indexCode: 'G2-1', name: '应收利息审定表' },
  { seq: 3, indexCode: 'G2-2', name: '应收利息明细表' },
  { seq: 4, indexCode: 'G2-3', name: '坏账准备明细表' },
  { seq: 5, indexCode: 'G2-4', name: '调整分录汇总' },
  { seq: 6, indexCode: 'G2-5', name: '利息测算表' },
  { seq: 7, indexCode: 'G2-6', name: '长期未收回检查表' },
  { seq: 8, indexCode: 'G2-7', name: '坏账准备测算表' },
  { seq: 9, indexCode: 'G2-8', name: '凭证检查表' },
  { seq: 10, indexCode: '附注上市', name: '附注披露（上市公司）' },
  { seq: 11, indexCode: '附注国企', name: '附注披露（国有企业）' },
]

/** sheetName → 内部分发编码 */
export function extractG2SheetCode(sheetName: string): string {
  if (/底稿目录/.test(sheetName)) return '底稿目录'
  if (/G2-note-listed|附注披露.*上市|附注.*上市/.test(sheetName)) return '附注上市'
  if (/G2-note-soe|附注披露.*国企|附注.*国企/.test(sheetName)) return '附注国企'
  if (/附注/.test(sheetName)) return sheetName.includes('国企') ? '附注国企' : '附注上市'
  const m = sheetName.match(/(G2A|G2-\d+)/i)
  if (!m) return ''
  return m[1].toUpperCase().replace(/^G2A$/i, 'G2A')
}

/**
 * 编码 → 真实 Excel sheet_name（OnlyOffice / 跳转）。
 * 优先从 availableSheets 按末尾编码匹配。
 */
export function resolveG2SheetLabel(
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

  if (fallbackSheetName && extractG2SheetCode(fallbackSheetName) === code) {
    return fallbackSheetName
  }

  return G2_SHEET_LABEL_MAP[code] ?? fallbackSheetName ?? code
}

/** 无 render-config sheets 时，用默认映射构造 availableSheets（供目录 / OO 解析） */
export function buildG2FallbackSheets(): Array<{ sheet_name: string; componentType: string }> {
  return Object.entries(G2_SHEET_LABEL_MAP)
    .filter(([code]) => code !== '底稿目录')
    .map(([, sheet_name]) => ({
      sheet_name,
      componentType: 'g2-interest-receivable',
    }))
}
