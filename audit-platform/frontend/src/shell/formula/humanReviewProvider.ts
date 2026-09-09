/**
 * HumanReviewProvider + canonical thread keys (formula-toolbar Task 10).
 *
 * Canonical key: projectId / wpId / (sheetUid | whole-workbook) / anchorId
 * Legacy: `${wpId}:${sectionId}` — migrate via dry-run then idempotent apply.
 */

import {
  assertCapabilityAllowed,
  type WorkpaperCapabilitySnapshot,
  type CapabilityKey,
} from './workpaperCapabilitySnapshot'

export const HUMAN_REVIEW_KEY_VERSION = '1.0' as const

export type HumanReviewAction = 'create' | 'reply' | 'resolve' | 'reopen' | 'read'

const ACTION_CAPABILITY: Record<HumanReviewAction, CapabilityKey> = {
  read: 'humanReviewRead',
  create: 'humanReviewWrite',
  reply: 'humanReviewWrite',
  resolve: 'humanReviewWrite',
  reopen: 'humanReviewWrite',
}

export interface CanonicalReviewThreadKey {
  keyVersion: typeof HUMAN_REVIEW_KEY_VERSION
  projectId: string
  wpId: string
  /** sheetUid or the literal 'whole-workbook' */
  sheetScope: string
  anchorId: string
  /** Wire form: project/wp/sheetScope/anchorId */
  wire: string
}

export function buildCanonicalReviewThreadKey(input: {
  projectId: string
  wpId: string
  sheetUid?: string | null
  wholeWorkbook?: boolean
  anchorId: string
}): CanonicalReviewThreadKey {
  if (!input.projectId.trim() || !input.wpId.trim() || !input.anchorId.trim()) {
    throw new Error('projectId, wpId, and anchorId are required for canonical review key')
  }
  // Honest degradation: no fabricated cell when sheet/anchor coarse.
  const sheetScope = input.wholeWorkbook
    ? 'whole-workbook'
    : input.sheetUid?.trim() || 'page'
  const wire = `${input.projectId}/${input.wpId}/${sheetScope}/${input.anchorId}`
  return {
    keyVersion: HUMAN_REVIEW_KEY_VERSION,
    projectId: input.projectId,
    wpId: input.wpId,
    sheetScope,
    anchorId: input.anchorId,
    wire,
  }
}

/** Legacy key used by useReviewDialog / review_dialog.py */
export function buildLegacyReviewThreadKey(wpId: string, sectionId: string): string {
  return `${wpId}:${sectionId}`
}

export function parseLegacyReviewThreadKey(
  legacy: string,
): { wpId: string; sectionId: string } | null {
  const i = legacy.indexOf(':')
  if (i <= 0 || i === legacy.length - 1) return null
  return { wpId: legacy.slice(0, i), sectionId: legacy.slice(i + 1) }
}

export interface ReviewKeyMigrationRow {
  legacyKey: string
  canonicalWire: string | null
  status: 'mapped' | 'collision' | 'orphan' | 'unmapped'
  detail: string
}

export interface ReviewKeyMigrationReport {
  dryRun: boolean
  scanned: number
  mapped: number
  collisions: number
  orphans: number
  rows: ReviewKeyMigrationRow[]
  rollbackEvidence: Array<{ legacyKey: string; previousCanonical: string | null }>
}

/**
 * Deterministic dry-run: map legacy wpId:sectionId → canonical using projectId + section as anchor.
 * Collisions (two legacies → same canonical) are reported, never auto-merged.
 */
export function dryRunReviewKeyMigration(input: {
  projectId: string
  legacyKeys: string[]
  /** Optional pre-existing canonical wires already in store */
  existingCanonical?: string[]
}): ReviewKeyMigrationReport {
  const rows: ReviewKeyMigrationRow[] = []
  const targetCount = new Map<string, string[]>()
  const existing = new Set(input.existingCanonical ?? [])

  for (const legacy of input.legacyKeys) {
    const parsed = parseLegacyReviewThreadKey(legacy)
    if (!parsed) {
      rows.push({
        legacyKey: legacy,
        canonicalWire: null,
        status: 'orphan',
        detail: 'unparseable legacy key',
      })
      continue
    }
    const canonical = buildCanonicalReviewThreadKey({
      projectId: input.projectId,
      wpId: parsed.wpId,
      sheetUid: null,
      anchorId: parsed.sectionId,
    })
    const list = targetCount.get(canonical.wire) ?? []
    list.push(legacy)
    targetCount.set(canonical.wire, list)
    rows.push({
      legacyKey: legacy,
      canonicalWire: canonical.wire,
      status: 'mapped',
      detail: existing.has(canonical.wire) ? 'target already exists (idempotent)' : 'ok',
    })
  }

  for (const [wire, legacies] of targetCount) {
    if (legacies.length > 1) {
      for (const row of rows) {
        if (row.canonicalWire === wire) {
          row.status = 'collision'
          row.detail = `collision among ${legacies.join(', ')}`
        }
      }
    }
  }

  return {
    dryRun: true,
    scanned: input.legacyKeys.length,
    mapped: rows.filter((r) => r.status === 'mapped').length,
    collisions: rows.filter((r) => r.status === 'collision').length,
    orphans: rows.filter((r) => r.status === 'orphan').length,
    rows,
    rollbackEvidence: rows
      .filter((r) => r.canonicalWire)
      .map((r) => ({ legacyKey: r.legacyKey, previousCanonical: null })),
  }
}

/**
 * Idempotent apply: skip collisions/orphans; mapped rows become applied.
 */
export function applyReviewKeyMigration(
  report: ReviewKeyMigrationReport,
): ReviewKeyMigrationReport {
  if (!report.dryRun) return report
  return {
    ...report,
    dryRun: false,
    rows: report.rows.map((r) =>
      r.status === 'mapped'
        ? { ...r, detail: r.detail.includes('idempotent') ? r.detail : 'applied' }
        : r,
    ),
  }
}

export interface HumanReviewProvider {
  assertAction(
    action: HumanReviewAction,
    capability: WorkpaperCapabilitySnapshot | null | undefined,
    ownerEpoch: number,
  ): { allowed: true } | { allowed: false; reasonCode: string; zhMessage: string }
  buildKey: typeof buildCanonicalReviewThreadKey
}

export function createHumanReviewProvider(): HumanReviewProvider {
  return {
    buildKey: buildCanonicalReviewThreadKey,
    assertAction(action, capability, ownerEpoch) {
      const key = ACTION_CAPABILITY[action]
      const verdict = assertCapabilityAllowed(capability, key, ownerEpoch)
      if (verdict.status === 'allowed') return { allowed: true }
      return {
        allowed: false,
        reasonCode: verdict.reasonCode,
        zhMessage: verdict.zhMessage,
      }
    },
  }
}
