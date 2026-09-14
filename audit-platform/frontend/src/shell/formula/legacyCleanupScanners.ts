/**
 * Task 12 legacy cleanup scanners — fixed rails, nodeKey-only consumers,
 * audit warning-then-commit, bare AI mounts.
 */

export interface LegacyCleanupFinding {
  code: string
  detail: string
  pathHint: string
}

export function scanFixedReviewRailSource(source: string, pathHint: string): LegacyCleanupFinding[] {
  const findings: LegacyCleanupFinding[] = []
  const stripped = source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/.*$/gm, '')
    .replace(/<!--[\s\S]*?-->/g, '')
  if (/position\s*:\s*fixed/i.test(stripped) && /gt-wp-review-rail/i.test(stripped)) {
    findings.push({
      code: 'fixed_review_rail',
      detail: 'GtWpReviewRail must not own fixed top/right/z-index; shell owns placement',
      pathHint,
    })
  }
  return findings
}

/** nodeKey may remain as migration metadata; identity consumers are forbidden. */
export function scanNodeKeyIdentityConsumer(source: string, pathHint: string): LegacyCleanupFinding[] {
  const findings: LegacyCleanupFinding[] = []
  if (/nodeKeyAsIdentity\s*:/.test(source) && /reduceLocationFact|assertGidSheetIdentity/.test(source)) {
    // Guards that reject identity are OK — look for assignment-as-identity without reject.
  }
  if (
    /sheetUid\s*[:=]\s*.*nodeKey/i.test(source)
    || /ownerKey\s*[:=]\s*.*nodeKey/i.test(source)
  ) {
    findings.push({
      code: 'nodekey_as_identity',
      detail: 'nodeKey used as location identity',
      pathHint,
    })
  }
  return findings
}

export function scanAuditWarningThenCommit(source: string, pathHint: string): LegacyCleanupFinding[] {
  const findings: LegacyCleanupFinding[] = []
  // Require explicit anti-pattern markers — not identifier lists like audit_warning_then_commit.
  if (
    /warn-then-commit/i.test(source)
    || (/except\s+AuditCommitError\s*:/.test(source) && /pass\s*(#.*warn)?/i.test(source))
  ) {
    findings.push({
      code: 'audit_warning_then_commit',
      detail: 'audit failure must block commit',
      pathHint,
    })
  }
  return findings
}

export function scanBareAiMount(source: string, pathHint: string): LegacyCleanupFinding[] {
  const findings: LegacyCleanupFinding[] = []
  if (/openAiAssist\s*\(/.test(source) || /ai-assist-fab/i.test(source)) {
    findings.push({
      code: 'bare_ai_mount',
      detail: 'AI assist must use DSH carrier only',
      pathHint,
    })
  }
  return findings
}

export function scanHardcodedCapabilityAvailability(source: string, pathHint: string): LegacyCleanupFinding[] {
  const findings: LegacyCleanupFinding[] = []
  // Explicit always-allow without snapshot gate in shell consumers.
  if (/capabilityAlwaysTrue|HARDCODED_CAPABILITY_ALLOW\s*=\s*true/.test(source)) {
    findings.push({
      code: 'hardcoded_capability',
      detail: 'capability must come from WorkpaperCapabilitySnapshot',
      pathHint,
    })
  }
  return findings
}
