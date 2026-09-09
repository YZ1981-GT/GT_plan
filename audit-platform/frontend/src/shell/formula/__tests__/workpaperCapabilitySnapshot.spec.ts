/**
 * Formula-toolbar Task 3 — client capability gate.
 */

import { describe, expect, it } from 'vitest'

import {
  CAPABILITY_KEYS,
  assertCapabilityAllowed,
  denialLeaksSensitiveMetadata,
  type WorkpaperCapabilitySnapshot,
  type CapabilityDecision,
} from '@/shell/formula'

function decision(allowed: boolean, reasonCode: string | null = null): CapabilityDecision {
  return {
    allowed,
    reasonCode,
    owner: 'workpaper-capability-matrix',
    nextAction: allowed ? null : '联系项目负责人',
    zhMessage: allowed ? null : '当前角色无权执行此操作。',
  }
}

function snapshot(partial?: Partial<WorkpaperCapabilitySnapshot>): WorkpaperCapabilitySnapshot {
  const base: WorkpaperCapabilitySnapshot = {
    snapshotVersion: '1.0',
    subjectDigest: 'a'.repeat(64),
    ownerEpoch: 1,
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
    formulaView: decision(true),
    formulaEditUser: decision(true),
    formulaHistory: decision(true),
    aiReviewPage: decision(true),
    aiReviewBatch: decision(false, 'role_denied'),
    aiAssistChat: decision(true),
    humanReviewRead: decision(true),
    humanReviewWrite: decision(false, 'role_denied'),
    guidanceRead: decision(true),
  }
  return { ...base, ...partial }
}

describe('Task 3: WorkpaperCapabilitySnapshot gate', () => {
  it('allows ready in-epoch non-expired decisions', () => {
    const v = assertCapabilityAllowed(snapshot(), 'formulaView', 1)
    expect(v.status).toBe('allowed')
  })

  it('blocks uninitialized / expired / epoch mismatch / denied', () => {
    expect(assertCapabilityAllowed(null, 'formulaView', 1).status).toBe('blocked')
    expect(assertCapabilityAllowed(snapshot(), 'formulaView', 99).status).toBe('blocked')
    expect(
      assertCapabilityAllowed(
        snapshot({ expiresAt: new Date(Date.now() - 1000).toISOString() }),
        'formulaView',
        1,
      ).status,
    ).toBe('blocked')
    const denied = assertCapabilityAllowed(snapshot(), 'aiReviewBatch', 1)
    expect(denied.status).toBe('blocked')
    if (denied.status === 'blocked') {
      expect(denied.zhMessage).toMatch(/无权|拒绝|过期|就绪|切换/)
      expect(denialLeaksSensitiveMetadata(denied.zhMessage)).toBe(false)
    }
  })

  it('covers all capability keys on the snapshot type', () => {
    const s = snapshot()
    for (const key of CAPABILITY_KEYS) {
      expect(s[key]).toBeTruthy()
      expect(typeof s[key].allowed).toBe('boolean')
    }
  })
})
