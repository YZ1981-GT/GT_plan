/**
 * F2 披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：backend/data/note_template_variant_matrix.json → cun_huo
 *   listed_* → 五、9
 *   soe_*    → 八、10
 *
 * 一页仅反写一种标准对应的章节，禁止交叉写入。
 */

export type F2DisclosureVariant = 'listed' | 'soe'

export const F2_NOTE_SECTION = {
  listed: '五、9',
  soe: '八、10',
} as const satisfies Record<F2DisclosureVariant, string>

export const F2_DISCLOSURE_SHEET_NAME = {
  listed: 'F2-note-listed',
  soe: 'F2-note-soe',
} as const satisfies Record<F2DisclosureVariant, string>

/** 存货科目 1401–1412（与审定取数口径一致） */
export const F2_INVENTORY_ACCOUNT_CODES: readonly string[] = Array.from(
  { length: 12 },
  (_, i) => String(1401 + i),
)

export function isListedStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return x.includes('listed') || x.includes('上市') || x === 'listed_standalone' || x === 'listed_consolidated'
}

export function isSoeStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return (
    x.includes('soe')
    || x.includes('state_owned')
    || x.includes('国企')
    || x.includes('国有')
    || x === 'cass'
    || x === 'cas'
  )
}

/** 与 useF2DisclosureListed / useF2DisclosureSoe 的 isApplicable 同口径 */
export function isF2DisclosureApplicable(
  variant: F2DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards || []
  if (list.length === 0) return true
  return variant === 'listed'
    ? list.some(isListedStandard)
    : list.some(isSoeStandard)
}

/**
 * 解析 sync payload 的 current_standard。
 * 空准则时按页变体给默认 standalone，避免一页同时写两种标准。
 */
export function resolveF2CurrentStandard(
  variant: F2DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    if (list.some((s) => s === 'listed_consolidated' || (s.includes('listed') && s.includes('consol')))) {
      return 'listed_consolidated'
    }
    return 'listed_standalone'
  }
  if (list.some((s) => s === 'soe_consolidated' || (s.includes('soe') && s.includes('consol')))) {
    return 'soe_consolidated'
  }
  return 'soe_standalone'
}

export interface F2NoteSectionTarget {
  variant: F2DisclosureVariant
  sectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
}

/**
 * 解析当前披露页应对接的附注章节。
 * 不适用时返回 null（调用方应禁用同步）。
 */
export function resolveF2NoteSectionTarget(
  variant: F2DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): F2NoteSectionTarget | null {
  if (!isF2DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = F2_NOTE_SECTION[variant]
  return {
    variant,
    sectionId,
    sheetName: F2_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveF2CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}
