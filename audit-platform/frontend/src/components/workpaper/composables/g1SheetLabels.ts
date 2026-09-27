/** G1 交易性金融资产 — sheetName ↔ 内部分发编码 / OnlyOffice sheet 名 */

/**
 * 编码 → 默认 Excel sheet_name（无 availableSheets 时兜底）。
 *
 * 🔴 18 条值必须**逐字**等于权威模板 `backend/wp_templates/G/G1 交易性金融资产.xlsx`
 * 的 `wb.sheetnames`，**含空格**。判据：
 * `backend/tests/workpaper_sync/test_g_foundation_p4_p8_p17_p18_red_baselines.py`
 * 的 `TestGfP4Bp5G1SheetLabels`（spec `g-cycle-sync-foundation-and-first-canary` BP-5）。
 *
 * 原注释写「编码紧贴表名、**无空格**」—— 这条描述本身就是 BP-5 的成因：`G1A` 的真实 tab
 * 名尾部**有一个空格**，按「无空格」写出来的值在模板里找不到。已按源模板事实改正。
 * 本表 5 条错名（G1A / G1-8 / G1-10 / G1-12 / 附注国企）于 2026-09-27 修正，
 * 逐条依据见 slice BP-5 正文与 `evidence/task5-bp5-g1-sheet-labels.md`。
 */
export const G1_SHEET_LABEL_MAP: Record<string, string> = {
  底稿目录: '底稿目录',
  // 🔴 尾部空格是源模板事实，不得 trim（模板 tab 逐字为 '…实质性程序表G1A '）
  G1A: '交易性金融资产实质性程序表G1A ',
  'G1-1': '审定表G1-1',
  'G1-2': '明细表G1-2',
  'G1-3': '调整分录汇总G1-3',
  'G1-4': '结存表G1-4',
  'G1-5': '收益测算表G1-5',
  'G1-6': '公允价值测试表G1-6',
  'G1-7': '第三层次公允价值计量的调节表G1-7',
  'G1-8': '业务模式分析G1-8',
  'G1-9': '分类的适当性检查表G1-9',
  'G1-10': '合同现金流量特征分析G1-10',
  'G1-11': '有价证券监盘表G1-11',
  'G1-12': '有价证券盘点倒轧表G1-12',
  'G1-13': '检查表G1-13',
  'G1-14': '衍生金融工具核查表G1-14',
  附注上市: '附注披露信息（上市公司）',
  附注国企: '附注披露信息（国企）',
}

/** sheetName → 内部分发编码 */
export function extractG1SheetCode(sheetName: string): string {
  if (/底稿目录/.test(sheetName)) return '底稿目录'
  if (/G1-note-listed|附注披露.*上市|附注.*上市/.test(sheetName)) return '附注上市'
  if (/G1-note-soe|附注披露.*国企|附注.*国企/.test(sheetName)) return '附注国企'
  if (/附注/.test(sheetName)) return sheetName.includes('国企') ? '附注国企' : '附注上市'
  if (/调整分录/.test(sheetName)) return 'G1-3'
  const m = sheetName.match(/(G1A|G1-\d+)/i)
  if (!m) return ''
  return m[1].toUpperCase().replace(/^G1A$/i, 'G1A')
}

/**
 * 编码 → 真实 Excel sheet_name（OnlyOffice / 导入导出）。
 * 优先从 availableSheets 按末尾编码匹配（对齐 D4 resolveD4SheetLabel）。
 */
export function resolveG1SheetLabel(
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

  if (fallbackSheetName && extractG1SheetCode(fallbackSheetName) === code) {
    return fallbackSheetName
  }

  return G1_SHEET_LABEL_MAP[code] ?? fallbackSheetName ?? code
}
