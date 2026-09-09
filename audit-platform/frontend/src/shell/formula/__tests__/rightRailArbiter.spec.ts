/**
 * G-RAIL + formula Task 11 guards.
 */

import { describe, expect, it, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import {
  GC0_CONTRACT_VERSION,
  type CanonicalWorkpaperLocation,
} from '@/shared/contracts/gc0'
import { assertRailIdentity } from '@/shared/contracts/gc0/workpaper-route-baseline'
import {
  GRAIL_CONTRACT_ID,
  GRAIL_CONTRACT_VERSION,
  GRAIL_CONSUMERS,
  buildGrailEvidencePayload,
  createGuidanceRailAdapter,
  guidanceSourceOwnsShellPlacement,
  toGuidanceRailContractSnapshot,
} from '@/shell/guidance'
import {
  RightRailArbiter,
  createAiAssistShellRail,
  createGuidanceShellRail,
  createReviewShellRail,
  resetRightRailArbiter,
  SHELL_RAIL_ORDER,
} from '@/shell/formula/rightRailArbiter'
import {
  DEFAULT_SHELL_LAYOUT_TOKENS,
  shellLayoutCssVars,
} from '@/shell/formula/shellLayoutTokens'
import type { WorkpaperCapabilitySnapshot } from '@/shell/formula/workpaperCapabilitySnapshot'

function makeLocation(overrides: Partial<CanonicalWorkpaperLocation> = {}): CanonicalWorkpaperLocation {
  return {
    contractVersion: GC0_CONTRACT_VERSION,
    organizationId: 'org-1',
    projectId: 'proj-1',
    fiscalYear: 2025,
    wpId: 'wp-1',
    wpCode: 'E1-1',
    entryId: 'e-1',
    host: 'html',
    anchor: { kind: 'sheet', sheetUid: 's-1', sheetCode: 'E1-1' },
    display: { sheetName: '货币资金', sectionLabel: null },
    ownerEpoch: 1,
    contextRevision: 1,
    ...overrides,
  }
}

function allowAll(): WorkpaperCapabilitySnapshot {
  const yes = { allowed: true, reasonCode: null, owner: null, nextAction: null, zhMessage: null }
  return {
    snapshotVersion: '1.0',
    subjectDigest: 'd',
    ownerEpoch: 1,
    expiresAt: '2099-01-01T00:00:00Z',
    formulaView: yes,
    formulaEditUser: yes,
    formulaHistory: yes,
    aiReviewPage: yes,
    aiReviewBatch: yes,
    aiAssistChat: yes,
    humanReviewRead: yes,
    humanReviewWrite: yes,
    guidanceRead: yes,
  }
}

function deny(key: keyof WorkpaperCapabilitySnapshot): WorkpaperCapabilitySnapshot {
  const snap = allowAll()
  const decision = {
    allowed: false,
    reasonCode: 'role_denied',
    owner: 'matrix',
    nextAction: '联系负责人',
    zhMessage: '当前角色无权',
  }
  ;(snap as any)[key] = decision
  return snap
}

describe('G-RAIL GuidanceRailAdapter producer', () => {
  it('publishes G-RAIL identity + consumers for formula F11', () => {
    const payload = buildGrailEvidencePayload()
    expect(payload.subject).toEqual({ kind: 'contract', contractId: GRAIL_CONTRACT_ID })
    expect((payload.contractVersions as Record<string, string>)[GRAIL_CONTRACT_ID]).toBe(
      GRAIL_CONTRACT_VERSION,
    )
    expect(payload.consumers).toEqual([...GRAIL_CONSUMERS])
    expect(payload.nonCapabilities).toEqual(
      expect.arrayContaining(['dom_placement', 'fixed_top_right_zindex']),
    )
  })

  it('returns null for incomplete location / unknown major', () => {
    expect(
      createGuidanceRailAdapter({
        location: null,
        visible: true,
        disabledReason: null,
        capabilityAllowed: true,
        controller: {
          isOpen: false,
          hasDraft: false,
          guidanceVersion: null,
          open: () => undefined,
          close: () => undefined,
        },
      }),
    ).toBeNull()

    const bad = makeLocation({ contractVersion: '9.0' as typeof GC0_CONTRACT_VERSION })
    expect(
      createGuidanceRailAdapter({
        location: bad,
        visible: true,
        disabledReason: null,
        capabilityAllowed: true,
        controller: {
          isOpen: false,
          hasDraft: false,
          guidanceVersion: null,
          open: () => undefined,
          close: () => undefined,
        },
      }),
    ).toBeNull()
  })

  it('preserves draft on close({preserveDraft:true}) and discards otherwise', async () => {
    let discarded = false
    let closed = false
    const adapter = createGuidanceRailAdapter({
      location: makeLocation(),
      visible: true,
      disabledReason: null,
      capabilityAllowed: true,
      controller: {
        isOpen: true,
        hasDraft: true,
        guidanceVersion: 'g-1',
        open: () => undefined,
        close: () => {
          closed = true
        },
        discardDraft: () => {
          discarded = true
        },
      },
    })
    expect(adapter).not.toBeNull()
    const wire = toGuidanceRailContractSnapshot(adapter!)
    expect(assertRailIdentity(wire)).not.toBeNull()

    await adapter!.close({ preserveDraft: true })
    expect(closed).toBe(true)
    expect(discarded).toBe(false)

    closed = false
    await adapter!.close({ preserveDraft: false })
    expect(discarded).toBe(true)
  })

  it('guidance adapter + panel source do not own shell placement CSS', () => {
    const adapterSrc = readFileSync(
      join(__dirname, '../../guidance/guidanceRailAdapter.ts'),
      'utf8',
    )
    expect(guidanceSourceOwnsShellPlacement(adapterSrc)).toBe(false)
    const panelSrc = readFileSync(
      join(__dirname, '../../../components/workpaper/WpGuidancePanel.vue'),
      'utf8',
    )
    expect(guidanceSourceOwnsShellPlacement(panelSrc)).toBe(false)
  })
})

describe('Task 11: RightRailArbiter + WorkpaperCapabilityShell ownership', () => {
  beforeEach(() => {
    resetRightRailArbiter()
  })

  it('orders review → guidance → ai-assist and allows only one open', async () => {
    const arbiter = new RightRailArbiter()
    arbiter.setEpochs({ ownerEpoch: 1, capabilityEpoch: 1 })
    const snap = allowAll()
    const opens: string[] = []
    const closes: string[] = []

    arbiter.register(createReviewShellRail({
      ownerEpoch: 1,
      capabilityEpoch: 1,
      snapshot: snap,
      hasDraft: false,
      open: () => {
        opens.push('review')
      },
      close: () => {
        closes.push('review')
      },
    }))
    const guidance = createGuidanceShellRail({
      ownerEpoch: 1,
      capabilityEpoch: 1,
      snapshot: snap,
      location: makeLocation(),
      controller: {
        isOpen: false,
        hasDraft: true,
        guidanceVersion: 'g-1',
        open: () => {
          opens.push('guidance')
        },
        close: () => {
          closes.push('guidance')
        },
      },
    })
    expect(guidance).not.toBeNull()
    arbiter.register(guidance!)
    arbiter.register(createAiAssistShellRail({
      ownerEpoch: 1,
      capabilityEpoch: 1,
      snapshot: snap,
      openDsh: () => {
        opens.push('ai-assist')
      },
      closeDsh: () => {
        closes.push('ai-assist')
      },
    }))

    expect(arbiter.mountableTriggers().map((r) => r.id)).toEqual([
      'review',
      'guidance',
      'ai-assist',
    ])
    expect(SHELL_RAIL_ORDER.review).toBe(10)
    expect(SHELL_RAIL_ORDER.guidance).toBe(20)
    expect(SHELL_RAIL_ORDER['ai-assist']).toBe(30)

    await arbiter.requestOpen('guidance')
    expect(arbiter.getOpenState()).toEqual({ status: 'open', id: 'guidance' })
    await arbiter.requestOpen('review')
    expect(closes).toContain('guidance')
    expect(arbiter.getOpenState()).toEqual({ status: 'open', id: 'review' })
    expect(opens.filter((x) => x === 'review')).toHaveLength(1)
  })

  it('visible=false / denied / epoch-stale never occupy trigger slots', () => {
    const arbiter = new RightRailArbiter()
    arbiter.setEpochs({ ownerEpoch: 1, capabilityEpoch: 1 })
    const denied = deny('guidanceRead')
    const guidance = createGuidanceShellRail({
      ownerEpoch: 1,
      capabilityEpoch: 1,
      snapshot: denied,
      location: makeLocation(),
      controller: {
        isOpen: false,
        hasDraft: false,
        guidanceVersion: null,
        open: () => undefined,
        close: () => undefined,
      },
    })
    expect(guidance).not.toBeNull()
    arbiter.register(guidance!)
    arbiter.register(createReviewShellRail({
      ownerEpoch: 1,
      capabilityEpoch: 99, // stale capability epoch
      snapshot: allowAll(),
      hasDraft: false,
      open: () => undefined,
      close: () => undefined,
    }))

    const slots = arbiter.listTriggerSlots()
    expect(slots.find((s) => s.id === 'guidance')?.occupiesSlot).toBe(false)
    expect(slots.find((s) => s.id === 'review')?.occupiesSlot).toBe(false)
    expect(arbiter.mountableTriggers()).toHaveLength(0)
  })

  it('shell layout tokens own inset/z-index; shell vue owns placement CSS', () => {
    const vars = shellLayoutCssVars(DEFAULT_SHELL_LAYOUT_TOKENS, true)
    expect(vars['--wp-shell-rail-z']).toBe('120')
    expect(vars['--wp-shell-content-inset-right']).toBe('380px')

    const shellSrc = readFileSync(
      join(__dirname, '../WorkpaperCapabilityShell.vue'),
      'utf8',
    )
    expect(shellSrc).toContain('--wp-shell-rail-z')
    expect(shellSrc).toContain('data-testid="workpaper-capability-shell"')
    expect(shellSrc).toMatch(/review.*guidance.*ai-assist|data-rail-id/)
  })
})
