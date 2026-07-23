/**
 * I6 底稿可见性（按 applicableStandards 过滤附注 Tab）
 */
import {
  isI6DisclosureApplicable,
  I6_NOTE_SECTION,
  type I6DisclosureVariant,
} from './i6NoteSectionMap'

export interface I6DisclosureVisibility {
  listed: boolean
  soe: boolean
  /** 至少一个披露版本可见 */
  any: boolean
}

export function resolveI6DisclosureVisibility(
  applicableStandards?: readonly string[] | null,
): I6DisclosureVisibility {
  const listed = isI6DisclosureApplicable('listed', applicableStandards)
  const soe = isI6DisclosureApplicable('soe', applicableStandards)
  return { listed, soe, any: listed || soe }
}

export function isI6DisclosureSheetVisible(
  sheetName: string,
  applicableStandards?: readonly string[] | null,
): boolean {
  const vis = resolveI6DisclosureVisibility(applicableStandards)
  if (/附注.*上市/.test(sheetName)) return vis.listed
  if (/附注.*国/.test(sheetName)) return vis.soe
  return true
}

export function resolveI6DefaultDisclosureSheet(
  applicableStandards?: readonly string[] | null,
): I6DisclosureVariant | null {
  const vis = resolveI6DisclosureVisibility(applicableStandards)
  if (vis.listed) return 'listed'
  if (vis.soe) return 'soe'
  return null
}

export function i6DisclosureSheetLabel(variant: I6DisclosureVariant): string {
  return variant === 'listed'
    ? `附注上市（${I6_NOTE_SECTION.listed}）`
    : `附注国企（${I6_NOTE_SECTION.soe}）`
}
