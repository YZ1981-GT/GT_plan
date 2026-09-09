/**
 * G-ID consumption for formula-toolbar Task 4.
 *
 * Mirrors backend `guidance_gid.StableSheetIdentity` rules:
 * sheetUid/sheetCode are identity; sheet name / tab index are display-only.
 * Does NOT redeclare G-C0 CanonicalWorkpaperLocation (import from gc0).
 */

export const GID_CONTRACT_ID = 'G-ID' as const
export const GID_CONTRACT_VERSION = '1.0' as const

export interface StableSheetIdentity {
  templateLineageId: string | null
  templateVersionId: string | null
  wpCode: string
  sheetUid: string | null
  sheetCode: string | null
  nullReason: string | null
  catalogKey: string
}

export function buildStableSheetIdentity(input: {
  wpCode: string
  sheetUid?: string | null
  sheetCode?: string | null
  templateLineageId?: string | null
  templateVersionId?: string | null
  nullReason?: string | null
}): StableSheetIdentity {
  const sheetUid = input.sheetUid?.trim() || null
  const sheetCode = input.sheetCode?.trim() || null
  let nullReason = input.nullReason ?? null
  if (!sheetUid && !nullReason) nullReason = 'sheet_uid_unavailable'
  const templateLineageId = input.templateLineageId ?? null
  const templateVersionId = input.templateVersionId ?? null
  const catalogKey = [
    templateLineageId || '',
    templateVersionId || '',
    input.wpCode,
    sheetUid || '',
  ].join('|')
  return {
    templateLineageId,
    templateVersionId,
    wpCode: input.wpCode,
    sheetUid,
    sheetCode,
    nullReason,
    catalogKey,
  }
}

/**
 * Fail-closed identity check for sheet-granularity anchors.
 * Rejects name/index/nodeKey as identity carriers.
 */
export function assertGidSheetIdentity(input: {
  sheetUid?: string | null
  sheetCode?: string | null
  /** Forbidden identity carriers — any present → blocked */
  sheetNameAsIdentity?: string | null
  sheetIndexAsIdentity?: number | null
  nodeKeyAsIdentity?: string | null
}): { ok: true; sheetUid: string; sheetCode: string | null } | { ok: false; reasonCode: string; detail: string } {
  if (input.sheetNameAsIdentity != null && String(input.sheetNameAsIdentity).length > 0) {
    return {
      ok: false,
      reasonCode: 'gid_name_not_identity',
      detail: 'sheet name must not be used as location identity (G-ID)',
    }
  }
  if (input.sheetIndexAsIdentity != null) {
    return {
      ok: false,
      reasonCode: 'gid_index_not_identity',
      detail: 'sheet index must not be used as location identity (G-ID)',
    }
  }
  if (input.nodeKeyAsIdentity != null && String(input.nodeKeyAsIdentity).length > 0) {
    return {
      ok: false,
      reasonCode: 'gid_nodekey_not_identity',
      detail: 'nodeKey is migration metadata only — not location identity',
    }
  }
  const sheetUid = input.sheetUid?.trim() || null
  if (!sheetUid) {
    return {
      ok: false,
      reasonCode: 'sheet_uid_unavailable',
      detail: 'G-ID requires stable sheetUid for sheet/cell/section anchors',
    }
  }
  return {
    ok: true,
    sheetUid,
    sheetCode: input.sheetCode?.trim() || null,
  }
}
