/**
 * Domain-owned formula dialogs — OUT OF SCOPE for workpaper-route uniqueness.
 * Requirement 1.4: TB / report / note dialogs are recorded as exclusion evidence
 * and MUST NOT inflate duplicate / outlet numerators.
 */

export interface DomainOwnedExclusion {
  /** Path relative to audit-platform/frontend/src */
  relativePath: string
  ownerSpec: string
  reason: string
}

export const DOMAIN_OWNED_FORMULA_EXCLUSIONS: readonly DomainOwnedExclusion[] = [
  {
    relativePath: 'views/TrialBalance.vue',
    ownerSpec: 'trial-balance',
    reason: 'TB domain formula UX — not workpaper-route shell',
  },
  {
    relativePath: 'views/ReportView.vue',
    ownerSpec: 'report',
    reason: 'Report domain formula UX — not workpaper-route shell',
  },
  {
    relativePath: 'views/DisclosureEditor.vue',
    ownerSpec: 'disclosure-notes',
    reason: 'Note/disclosure domain formula UX — not workpaper-route shell',
  },
  {
    relativePath: 'views/ReportConfigEditor.vue',
    ownerSpec: 'report-config',
    reason: 'Report-config domain — not workpaper-route shell',
  },
  {
    relativePath: 'views/ReportConfigBaselineTab.vue',
    ownerSpec: 'report-config',
    reason: 'Report-config domain — not workpaper-route shell',
  },
  {
    relativePath: 'views/AuditReportEditor.vue',
    ownerSpec: 'audit-report',
    reason: 'Audit-report domain — not workpaper-route shell',
  },
] as const

export function isDomainOwnedRelativePath(relativePath: string): boolean {
  const normalized = relativePath.replace(/\\/g, '/')
  return DOMAIN_OWNED_FORMULA_EXCLUSIONS.some(
    (e) => e.relativePath === normalized || normalized.endsWith(e.relativePath),
  )
}
