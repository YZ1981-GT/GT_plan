/**
 * 附注模块 → 底稿「披露表」跳转：从 note 元数据/章节号推断 G7 披露 sheet。
 * 不改附注表结构；仅导航。
 */

export const G7_DISCLOSURE_SHEET_LISTED = '附注披露信息（上市公司）'
export const G7_DISCLOSURE_SHEET_SOE = '附注披露信息（国企）'

export interface NoteDisclosureJumpTarget {
  /** 底稿 sheet 名（传给 ?sheet=） */
  sheet: string
  /** 已知同步 wp_id（可空，空则走 ACNR 解析 G7） */
  wpId: string | null
  /** listed | soe */
  variant: 'listed' | 'soe'
  /** 推断依据说明 */
  reason: string
}

function asRecord(raw: unknown): Record<string, unknown> | null {
  return raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : null
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

  if (syncedSheet.includes('附注披露信息（上市公司）') || syncedSheet.includes('附注披露(上市)')) {
    return {
      sheet: G7_DISCLOSURE_SHEET_LISTED,
      wpId,
      variant: 'listed',
      reason: '同步来源 sheet',
    }
  }
  if (syncedSheet.includes('附注披露信息（国企）') || syncedSheet.includes('附注披露(国企)')) {
    return {
      sheet: G7_DISCLOSURE_SHEET_SOE,
      wpId,
      variant: 'soe',
      reason: '同步来源 sheet',
    }
  }

  if (section === '五、18' || section.startsWith('五、18') || std.startsWith('listed')) {
    if (isG7EquityNoteSection(section) || std.startsWith('listed') || syncedSheet) {
      return {
        sheet: G7_DISCLOSURE_SHEET_LISTED,
        wpId,
        variant: 'listed',
        reason: section ? `章节 ${section}` : 'listed 准则',
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
      }
    }
  }

  // 同步过但 sheet 名不标准：仍允许用 wpId 打开，sheet 空则由调用方只开底稿
  if (wpId && isG7EquityNoteSection(section)) {
    const variant = std.startsWith('listed') ? 'listed' : 'soe'
    return {
      sheet: variant === 'listed' ? G7_DISCLOSURE_SHEET_LISTED : G7_DISCLOSURE_SHEET_SOE,
      wpId,
      variant,
      reason: '章节推断 + 同步底稿',
    }
  }

  return null
}
