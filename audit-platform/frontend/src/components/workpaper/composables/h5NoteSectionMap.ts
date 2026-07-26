/**
 * h5NoteSectionMap — H5 油气资产披露表↔附注联动映射
 *
 * 权威 note_template_variant_matrix.json · you_qi_zi_chan：
 *   soe_standalone = 八、25（国企独立章节）
 *   listed_standalone = null（上市无独立油气章节）
 *
 * 仅 SOE 变体有同步（listed 不做）。
 */

// ─── 常量 ─────────────────────────────────────────────────────────────────────

/** 权威附注章节号（仅 SOE 有独立章节） */
export const H5_NOTE_SECTION = { soe: '八、25' } as const

/** H5 SOE 版披露 sheet 真实 tab 名 */
export const H5_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

// ─── 类型 ─────────────────────────────────────────────────────────────────────

export interface ColumnDef {
  key: string
  label: string
  is_label?: boolean
}

export interface H5SyncRow {
  label: string
  values: (number | string | null)[]
  is_total?: boolean
}

export interface H5SyncPayloadOptions {
  wpId: string
  projectId: string
  year: number
  /** 汇总表行数据（项目/期末余额/期初余额） */
  summaryRows: H5SyncRow[]
  /** 说明文本（国企特殊披露区段） */
  soeDisclosureText?: string
}

// ─── 列定义（从 H5TabDisclosureSoe el-table-column 逐字提取） ─────────────────

/**
 * 油气资产汇总表列头：
 * - 项目（标签列）
 * - 期末余额
 * - 期初余额
 */
export const H5_SOE_COLUMNS: Record<string, ColumnDef[]> = {
  '油气资产': [
    { key: 'item', label: '项目', is_label: true },
    { key: 'endBalance', label: '期末余额' },
    { key: 'beginBalance', label: '期初余额' },
  ],
}

// ─── 构造同步载荷（纯函数） ───────────────────────────────────────────────────

/**
 * 构造 H5 SOE 版附注同步载荷。
 *
 * @returns 可直接 POST 到 /disclosure-notes/{pid}/{year}/{section}/sync-from-workpaper 的请求体
 */
export function buildH5SyncPayload(opts: H5SyncPayloadOptions): {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  year: number
  sub_table_data: Record<string, any>
  columns: Record<string, ColumnDef[]>
  _note_texts: Array<{ section: string; title: string; text: string }>
} {
  const { wpId, year, summaryRows, soeDisclosureText } = opts

  // 子表数据
  const subTableData: Record<string, any> = {}
  if (summaryRows.length > 0) {
    subTableData['油气资产'] = summaryRows.map((r) => ({
      label: r.label,
      values: r.values,
      is_total: r.is_total || false,
    }))
  }

  // 说明文本
  const noteTexts: Array<{ section: string; title: string; text: string }> = []
  if (soeDisclosureText && soeDisclosureText.trim()) {
    noteTexts.push({
      section: 'soe-supplementary',
      title: '补充披露（国资监管要求）',
      text: soeDisclosureText.trim(),
    })
  }

  return {
    wp_id: wpId,
    sheet_name: H5_DISCLOSURE_SHEET_SOE,
    section_id: H5_NOTE_SECTION.soe,
    current_standard: 'soe_standalone',
    year,
    sub_table_data: subTableData,
    columns: H5_SOE_COLUMNS,
    _note_texts: noteTexts,
  }
}
