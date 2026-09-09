/**
 * Formula-toolbar Task 10 — HumanReviewProvider + key migration.
 */

import { describe, expect, it } from 'vitest'

import type { WorkpaperCapabilitySnapshot, CapabilityDecision } from '@/shell/formula'
import {
  applyReviewKeyMigration,
  buildCanonicalReviewThreadKey,
  buildLegacyReviewThreadKey,
  createHumanReviewProvider,
  dryRunReviewKeyMigration,
  parseLegacyReviewThreadKey,
} from '@/shell/formula/humanReviewProvider'

function decision(allowed: boolean): CapabilityDecision {
  return {
    allowed,
    reasonCode: allowed ? null : 'role_denied',
    owner: 'workpaper-capability-matrix',
    nextAction: null,
    zhMessage: allowed ? null : '当前角色无权执行此操作。',
  }
}

function capability(write: boolean): WorkpaperCapabilitySnapshot {
  return {
    snapshotVersion: '1.0',
    subjectDigest: 'd'.repeat(64),
    ownerEpoch: 1,
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
    formulaView: decision(true),
    formulaEditUser: decision(true),
    formulaHistory: decision(true),
    aiReviewPage: decision(true),
    aiReviewBatch: decision(true),
    aiAssistChat: decision(true),
    humanReviewRead: decision(true),
    humanReviewWrite: decision(write),
    guidanceRead: decision(true),
  }
}

describe('Task 10: HumanReviewProvider + canonical keys', () => {
  it('builds canonical key project/wp/sheetScope/anchorId', () => {
    const key = buildCanonicalReviewThreadKey({
      projectId: 'p1',
      wpId: 'wp1',
      sheetUid: 's1',
      anchorId: 'sec-a',
    })
    expect(key.wire).toBe('p1/wp1/s1/sec-a')

    const whole = buildCanonicalReviewThreadKey({
      projectId: 'p1',
      wpId: 'wp1',
      wholeWorkbook: true,
      anchorId: 'page',
    })
    expect(whole.sheetScope).toBe('whole-workbook')

    const degraded = buildCanonicalReviewThreadKey({
      projectId: 'p1',
      wpId: 'wp1',
      anchorId: 'sec-b',
    })
    expect(degraded.sheetScope).toBe('page')
  })

  it('parses legacy wpId:sectionId and dry-run detects collisions', () => {
    expect(buildLegacyReviewThreadKey('wp1', 'sec1')).toBe('wp1:sec1')
    expect(parseLegacyReviewThreadKey('wp1:sec1')).toEqual({ wpId: 'wp1', sectionId: 'sec1' })

    const report = dryRunReviewKeyMigration({
      projectId: 'p1',
      legacyKeys: ['wp1:sec1', 'wp1:sec1', 'bad', 'wp2:sec2'],
    })
    // two identical legacies map to same wire → collision
    expect(report.collisions).toBeGreaterThan(0)
    expect(report.orphans).toBe(1)
    expect(report.dryRun).toBe(true)

    const applied = applyReviewKeyMigration(report)
    expect(applied.dryRun).toBe(false)
    expect(applied.rollbackEvidence.length).toBeGreaterThan(0)
  })

  it('gates create/reply/resolve/reopen/read by capability', () => {
    const provider = createHumanReviewProvider()
    expect(provider.assertAction('read', capability(false), 1).allowed).toBe(true)
    expect(provider.assertAction('create', capability(false), 1).allowed).toBe(false)
    expect(provider.assertAction('reply', capability(true), 1).allowed).toBe(true)
  })
})
