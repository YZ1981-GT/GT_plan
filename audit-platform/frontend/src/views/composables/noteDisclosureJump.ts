/**
 * 附注模块 → 底稿「披露表」跳转：从 note 元数据/章节号推断 G7/G10/G13/G14 披露 sheet。
 * 不改附注表结构；仅导航。
 */

export const G7_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G7_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const G10_DISCLOSURE_SHEET_LISTED = '附注上市'
export const G10_DISCLOSURE_SHEET_SOE = '附注国企'

export const G13_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G13_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const G14_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G14_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const H1_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const H1_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

export const H8_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const H8_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const H9_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const H9_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export const H10_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const H10_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

export const I1_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const I1_DISCLOSURE_SHEET_SOE = '附注披露信息（国有企业）'

export interface NoteDisclosureJumpTarget {
  /** 底稿 sheet 名（传给 ?sheet=） */
  sheet: string
  /** 已知同步 wp_id（可空，空则走 ACNR 解析） */
  wpId: string | null
  /** listed | soe */
  variant: 'listed' | 'soe'
  /** 推断依据说明 */
  reason: string
  /** 底稿族代码（ACNR 回退解析） */
  wpCode?: 'G7' | 'G10' | 'G13' | 'G14' | 'H1' | 'H8' | 'H9' | 'H10' | 'I1'
}

function asRecord(raw: unknown): Record<string, unknown> | null {
  return raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : null
}

/** 是否像 G13 公允价值变动收益相关附注节 */
export function isG13FairValueNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '三、公允价值变动收益' || s.startsWith('三、公允价值变动')) return true
  if (s === '八、72' || s.startsWith('八、72')) return true
  return false
}

/** 是否像 G14 信用减值损失相关附注节 */
export function isG14CreditImpairmentNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '三、信用减值损失' || s.startsWith('三、信用减值')) return true
  if (s === '八、73' || s.startsWith('八、73')) return true
  return false
}

/** 是否像 G10 交易性金融负债相关附注节 */
export function isG10TradingLiabilityNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、34' || s.startsWith('五、34')) return true
  if (s === '八、34' || s.startsWith('八、34')) return true
  if (s === '五、35' || s.startsWith('五、35')) return true
  if (s === '八、35' || s.startsWith('八、35')) return true
  return false
}

/** 是否像 G7 长期股权投资相关附注节 */
export function isG7EquityNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、18' || s.startsWith('五、18')) return true
  if (s === '八、18' || s.startsWith('八、18')) return true
  if (s === '七' || s.startsWith('七、') || s.startsWith('七 ')) return true
  return false
}

/** 是否像 H1 固定资产相关附注节 */
export function isH1FixedAssetNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、15' || s.startsWith('五、15')) return true
  if (s === '五、22' || s.startsWith('五、22')) return true
  if (s === '八、22' || s.startsWith('八、22')) return true
  if (s === '固定资产' || (s.includes('固定资产') && !s.includes('清理') && !s.includes('在建'))) return true
  return false
}

/** 是否像 H8 使用权资产相关附注节 */
export function isH8RouNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、25' || s.startsWith('五、25')) return true
  if (s === '八、26' || s.startsWith('八、26')) return true
  if (s === '三、使用权资产' || s.startsWith('三、使用权')) return true
  if (s === '四、使用权资产' || s.startsWith('四、使用权')) return true
  if (s === '使用权资产' || (s.includes('使用权资产') && !s.includes('改良'))) return true
  return false
}

/** 是否像 H9 租赁负债相关附注节 */
export function isH9LeaseLiabilityNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、47' || s.startsWith('五、47')) return true
  if (s === '八、52' || s.startsWith('八、52')) return true
  if (s === '租赁负债' || (s.includes('租赁负债') && !s.includes('使用权'))) return true
  return false
}

/** 是否像 H10 资产处置收益相关附注节 */
export function isH10AssetDisposalNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '三、资产处置收益' || s.startsWith('三、资产处置')) return true
  if (s === '八、75' || s.startsWith('八、75')) return true
  if (s === '资产处置收益' || s === '资产处置损益' || (s.includes('资产处置') && !s.includes('清理'))) return true
  return false
}

/** 是否像 I1 无形资产相关附注节 */
export function isI1IntangibleNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、26' || s.startsWith('五、26')) return true
  if (s === '八、27' || s.startsWith('八、27')) return true
  if (s === '三、无形资产' || s.startsWith('三、无形资产')) return true
  if (s === '四、无形资产' || s.startsWith('四、无形资产')) return true
  // 避免误伤「研发支出」等：仅精确/强匹配
  if (s === '无形资产') return true
  return false
}

/**
 * 从当前附注记录推断「跳转至披露表」目标。
 * 优先 last_sync 元数据，其次章节号 / source_template / _current_standard。
 */
export function resolveNoteDisclosureJumpTarget(note: unknown): NoteDisclosureJumpTarget | null {
  const n = asRecord(note)
  if (!n) return null
  const table = asRecord(n.table_data) || {}
  const section = String(n.note_section || '').trim()
  const syncedSheet = String(table._last_sync_sheet || table._last_sync_sheet_name || '').trim()
  const wpId = String(
    n.last_sync_wp_id
    || table._last_sync_wp_id
    || '',
  ).trim() || null
  const std = String(
    table._current_standard
    || n.source_template
    || '',
  ).toLowerCase()

  // G13/G14 须先于 G7：sheet 名相同，靠章节号区分
  if (isG13FairValueNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? G13_DISCLOSURE_SHEET_LISTED : G13_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'G13',
    }
  }

  if (isG14CreditImpairmentNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? G14_DISCLOSURE_SHEET_LISTED : G14_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'G14',
    }
  }

  if (isH1FixedAssetNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? H1_DISCLOSURE_SHEET_LISTED : H1_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'H1',
    }
  }

  // H8 须在通用「附注披露信息」sheet 回退之前（与 G7 sheet 名重叠）
  if (isH8RouNoteSection(section)) {
    const variant = section.startsWith('八') || section.startsWith('四') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? H8_DISCLOSURE_SHEET_LISTED : H8_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'H8',
    }
  }

  // H9 租赁负债（五、47 / 八、52）须在通用 sheet 回退之前
  if (isH9LeaseLiabilityNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? H9_DISCLOSURE_SHEET_LISTED : H9_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'H9',
    }
  }

  // H10 资产处置收益（三、资产处置收益 / 八、75）
  if (isH10AssetDisposalNoteSection(section)) {
    const variant = section.startsWith('八') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? H10_DISCLOSURE_SHEET_LISTED : H10_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'H10',
    }
  }

  // I1 无形资产（五、26 / 八、27）须在通用 sheet 回退之前
  if (isI1IntangibleNoteSection(section)) {
    const variant = section.startsWith('八') || section.startsWith('四') || std.startsWith('soe') ? 'soe' : 'listed'
    return {
      sheet: variant === 'listed' ? I1_DISCLOSURE_SHEET_LISTED : I1_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: `章节 ${section}`,
      wpCode: 'I1',
    }
  }

  if (syncedSheet.includes(G10_DISCLOSURE_SHEET_LISTED)) {
    return {
      sheet: G10_DISCLOSURE_SHEET_LISTED,
      wpId,
      variant: 'listed',
      reason: '同步来源 sheet',
      wpCode: 'G10',
    }
  }
  if (syncedSheet.includes(G10_DISCLOSURE_SHEET_SOE)) {
    return {
      sheet: G10_DISCLOSURE_SHEET_SOE,
      wpId,
      variant: 'soe',
      reason: '同步来源 sheet',
      wpCode: 'G10',
    }
  }

  if (section === '五、34' || section.startsWith('五、34') || section === '五、35' || section.startsWith('五、35')) {
    return {
      sheet: G10_DISCLOSURE_SHEET_LISTED,
      wpId,
      variant: 'listed',
      reason: section ? `章节 ${section}` : 'listed 准则',
      wpCode: 'G10',
    }
  }

  if (section === '八、34' || section.startsWith('八、34') || section === '八、35' || section.startsWith('八、35')) {
    return {
      sheet: G10_DISCLOSURE_SHEET_SOE,
      wpId,
      variant: 'soe',
      reason: section ? `章节 ${section}` : 'soe 准则',
      wpCode: 'G10',
    }
  }

  if (syncedSheet.includes('附注披露信息（上市公司）') || syncedSheet.includes('附注披露(上市)')) {
    return {
      sheet: G7_DISCLOSURE_SHEET_LISTED,
      wpId,
      variant: 'listed',
      reason: '同步来源 sheet',
      wpCode: 'G7',
    }
  }
  if (syncedSheet.includes('附注披露信息（国企）') || syncedSheet.includes('附注披露(国企)')) {
    return {
      sheet: G7_DISCLOSURE_SHEET_SOE,
      wpId,
      variant: 'soe',
      reason: '同步来源 sheet',
      wpCode: 'G7',
    }
  }

  if (section === '五、18' || section.startsWith('五、18') || std.startsWith('listed')) {
    if (isG7EquityNoteSection(section) || std.startsWith('listed') || syncedSheet) {
      return {
        sheet: G7_DISCLOSURE_SHEET_LISTED,
        wpId,
        variant: 'listed',
        reason: section ? `章节 ${section}` : 'listed 准则',
        wpCode: 'G7',
      }
    }
  }

  if (
    section === '八、18'
    || section.startsWith('八、18')
    || section === '七'
    || section.startsWith('七、')
    || section.startsWith('七 ')
    || std.startsWith('soe')
  ) {
    if (isG7EquityNoteSection(section) || std.startsWith('soe')) {
      return {
        sheet: G7_DISCLOSURE_SHEET_SOE,
        wpId,
        variant: 'soe',
        reason: section ? `章节 ${section}` : 'soe 准则',
        wpCode: 'G7',
      }
    }
  }

  if (wpId && isG7EquityNoteSection(section)) {
    const variant = std.startsWith('listed') ? 'listed' : 'soe'
    return {
      sheet: variant === 'listed' ? G7_DISCLOSURE_SHEET_LISTED : G7_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: '章节推断 + 同步底稿',
      wpCode: 'G7',
    }
  }

  return null
}
