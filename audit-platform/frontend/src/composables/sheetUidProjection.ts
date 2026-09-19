/**
 * G-ID sheet uid projection — mirrors backend guidance_render_identity.project_sheet_uid.
 * Display names never invent uid.
 */

export function projectSheetUid(input: {
  parentWpCode: string
  sheetCode: string | null | undefined
  sheetName: string | null | undefined
  wholeWorkbook: boolean
  explicitUid?: string | null
  codeReason?: string | null
}): { sheetUid: string | null; nullReason: string | null } {
  const explicit = input.explicitUid?.trim() || null
  if (explicit) return { sheetUid: explicit, nullReason: null }
  if (input.wholeWorkbook) return { sheetUid: null, nullReason: 'whole_workbook' }
  const code = input.sheetCode?.trim() || null
  if (code && input.parentWpCode.trim()) {
    return { sheetUid: `uid:${input.parentWpCode.trim()}:${code}`, nullReason: null }
  }
  if (input.codeReason === 'no_canonical_code') {
    return { sheetUid: null, nullReason: 'no_canonical_code' }
  }
  if (input.sheetName) {
    return { sheetUid: null, nullReason: 'display_name_not_identity' }
  }
  return { sheetUid: null, nullReason: 'sheet_uid_unavailable' }
}

export function buildHtmlSubjectKey(input: {
  sheetUid: string | null
  sheetCode: string | null
  sheetName: string
  host: string
  wholeWorkbook: boolean
}): string {
  if (input.wholeWorkbook) return `${input.host}|whole-workbook`
  if (input.sheetUid) return `${input.host}|sheet:${input.sheetUid}`
  return `${input.host}|unresolved:${input.sheetCode || ''}:${input.sheetName || ''}`
}
