/**
 * H2 附注适用准则（applicable_standards）解析与显示控制
 * 对齐 D5 useD5Disclosure / h2NoteSectionMap.isH2DisclosureApplicable
 */
import { computed, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import {
  isH2DisclosureApplicable,
  type H2DisclosureVariant,
  H2_DISCLOSURE_SHEET_NAME,
} from './h2NoteSectionMap'

export const H2_APPLICABLE_STANDARDS_KEY = 'H2-applicable-standards'

export function parseApplicableStandardsFromMap(
  map: Map<string, any> | null | undefined,
): string[] {
  if (!map) return []
  const keys = [H2_APPLICABLE_STANDARDS_KEY, 'applicable_standards', 'D5-applicable-standards']
  for (const key of keys) {
    const raw = map.get(key)?.remark
    if (raw == null) continue
    const str = String(raw).trim()
    if (!str) continue
    try {
      const parsed = JSON.parse(str)
      if (Array.isArray(parsed)) return parsed.map(String)
    } catch { /* comma-separated */ }
    return str.split(/[,，;；]/).map(s => s.trim()).filter(Boolean)
  }
  return []
}

/** 仅一方适用时返回该版；双方或均未识别时返回 null（目录两版均适用） */
export function resolveH2DisclosureVariantFromStandards(
  standards: readonly string[],
): H2DisclosureVariant | null {
  const list = standards.map(s => String(s).trim()).filter(Boolean)
  if (list.length === 0) return null
  const hasListed = isH2DisclosureApplicable('listed', list)
  const hasSoe = isH2DisclosureApplicable('soe', list)
  if (hasListed && !hasSoe) return 'listed'
  if (hasSoe && !hasListed) return 'soe'
  return null
}

export function resolveH2DisclosureVariantFromResponses(
  map: Map<string, any>,
): H2DisclosureVariant | null {
  const manual = String(map.get('H2-disclosure-variant')?.remark ?? '').trim().toLowerCase()
  const standards = parseApplicableStandardsFromMap(map)
  if (manual === 'listed' || manual === 'soe') {
    const v = manual as H2DisclosureVariant
    if (standards.length === 0) return v
    if (isH2DisclosureApplicable(v, standards)) return v
  }
  return resolveH2DisclosureVariantFromStandards(standards)
}

export function useH2ApplicableStandards(options: {
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  htmlData?: Ref<any>
  onPersist?: (key: string, value: unknown) => void
}) {
  const applicableStandards = computed<string[]>(() => {
    const fromMap = parseApplicableStandardsFromMap(options.allResponses.value)
    if (fromMap.length > 0) return fromMap
    const hd = options.htmlData?.value
    const fromHtml =
      hd?.project_context?.applicable_standards
      ?? hd?.projectContext?.applicable_standards
      ?? hd?.applicable_standards
    if (Array.isArray(fromHtml) && fromHtml.length > 0) return fromHtml.map(String)
    return []
  })

  const showListed = computed(() =>
    isH2DisclosureApplicable('listed', applicableStandards.value),
  )

  const showSoe = computed(() =>
    isH2DisclosureApplicable('soe', applicableStandards.value),
  )

  const activeDisclosureVariant = computed<H2DisclosureVariant>(() => {
    const resolved = resolveH2DisclosureVariantFromResponses(options.allResponses.value)
    if (resolved) return resolved
    return showListed.value ? 'listed' : 'soe'
  })

  async function loadFromProject(): Promise<void> {
    if (!options.projectId.value) return
    if (parseApplicableStandardsFromMap(options.allResponses.value).length > 0) return
    try {
      const res = await api.get(`/api/projects/${options.projectId.value}`, { _silent: true } as any)
      const data = res?.data ?? res
      const standards = data?.applicable_standards
      if (Array.isArray(standards) && standards.length > 0) {
        options.onPersist?.(H2_APPLICABLE_STANDARDS_KEY, standards)
      }
    } catch { /* silent */ }
  }

  function isSheetApplicable(sheetCode: '附注上市' | '附注国企'): boolean {
    return sheetCode === '附注上市' ? showListed.value : showSoe.value
  }

  function redirectSheetName(sheetCode: string): string | null {
    if (sheetCode === '附注上市' && !showListed.value && showSoe.value) {
      return H2_DISCLOSURE_SHEET_NAME.soe
    }
    if (sheetCode === '附注国企' && !showSoe.value && showListed.value) {
      return H2_DISCLOSURE_SHEET_NAME.listed
    }
    return null
  }

  return {
    applicableStandards,
    showListed,
    showSoe,
    activeDisclosureVariant,
    loadFromProject,
    isSheetApplicable,
    redirectSheetName,
  }
}
