/**
 * Task 13 directed behavior suite — inventory/location/capability/outlet/dialog/
 * provider/v2/AI/review/rail/a11y + F-SHELL publish gate.
 */

import { describe, expect, it, beforeEach } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'

import { GC0_CONTRACT_VERSION, type CanonicalWorkpaperLocation } from '@/shared/contracts/gc0'
import { assertBaselineEnvelope } from '@/shared/contracts/gc0/workpaper-route-baseline'
import {
  FSHELL_CONTRACT_ID,
  FSHELL_CONTRACT_VERSION,
  FSHELL_CAPABILITIES,
  FSHELL_NON_CAPABILITIES,
  assertFShellConsumerCompatible,
  buildFShellContractSnapshot,
  buildFShellEvidencePayload,
} from '@/shell/formula/fShellContract'
import { GRAIL_CONTRACT_ID } from '@/shell/guidance'
import {
  COMPATIBILITY_OUTLET_SLOT,
  DOMAIN_OWNED_FORMULA_EXCLUSIONS,
  GT_WP_TOOLBAR_RIGHT_CSS_CLASS,
  assertCssClassIsNotOutletCapability,
  buildWorkpaperHostInventory,
} from '@/shell/formula'
import { ToolbarOutletArbiter, resetToolbarOutletArbiter } from '@/shell/formula/toolbarOutletArbiter'
import { assertCapabilityAllowed } from '@/shell/formula/workpaperCapabilitySnapshot'
import {
  createOpenFormulaManagerCommand,
  onLocationChangedWhileOpen,
  markSessionDirty,
} from '@/shell/formula/openFormulaManagerCommand'
import {
  aggregateProviderResults,
  type FormulaDescriptor,
} from '@/shell/formula/formulaProviderRegistry'
import { assertFunctionCategorySplit } from '@/shell/formula/userFormulaV2'
import { assertAiAssistCarrier, assertTaxonomyA11yUnique } from '@/shell/formula/aiActionTaxonomy'
import { buildCanonicalReviewThreadKey } from '@/shell/formula/humanReviewProvider'
import { RightRailArbiter, resetRightRailArbiter } from '@/shell/formula/rightRailArbiter'
import { assertChineseAccessibleName, SHELL_A11Y_NAMES } from '@/shell/formula/shellA11y'
import { assertNotBroadCatchSuccess } from '@/shell/formula/shellStructuredError'

function allowDecision() {
  return {
    allowed: true,
    reasonCode: null,
    owner: null,
    nextAction: null,
    zhMessage: null,
  }
}

function snap(epoch = 1) {
  return {
    snapshotVersion: '1.0',
    subjectDigest: 'd',
    ownerEpoch: epoch,
    expiresAt: '2099-01-01T00:00:00Z',
    formulaView: allowDecision(),
    formulaEditUser: allowDecision(),
    formulaHistory: allowDecision(),
    aiReviewPage: allowDecision(),
    aiReviewBatch: allowDecision(),
    aiAssistChat: allowDecision(),
    humanReviewRead: allowDecision(),
    humanReviewWrite: allowDecision(),
    guidanceRead: allowDecision(),
  }
}

function loc(epoch = 1, rev = 1): CanonicalWorkpaperLocation {
  return {
    contractVersion: GC0_CONTRACT_VERSION,
    organizationId: 'org',
    projectId: 'p1',
    fiscalYear: 2026,
    wpId: 'wp-1',
    wpCode: 'D0',
    entryId: 'e1',
    host: 'html',
    anchor: { kind: 'page' },
    display: { sheetName: null, sectionLabel: null },
    ownerEpoch: epoch,
    contextRevision: rev,
  }
}

function descriptor(formulaId: string, digest: string, providerId: string): FormulaDescriptor {
  return {
    descriptorVersion: '2.0',
    formulaId,
    semanticDigest: digest,
    origin: 'platform',
    ruleKind: 'data_fetch',
    engine: 'platform',
    protection: 'editable',
    location: loc(),
    target: { addrId: null, fieldKey: null, rowKey: null, columnKey: null, a1: null },
    formulaFunction: 'TB',
    ruleCategory: 'auto_calc',
    expression: null,
    ruleSummary: '',
    refs: [],
    currentValue: null,
    valueStatus: 'resolved',
    calculatedAt: null,
    contextFingerprint: 'fp',
    manualOverride: false,
    version: '1',
    owner: 'platform',
    protectionReason: null,
    updatedBy: null,
    updatedAt: null,
    provenance: { providerId, sourceDigest: 'src' },
  }
}

describe('Task 13: directed behavior coverage', () => {
  beforeEach(() => {
    resetToolbarOutletArbiter()
    resetRightRailArbiter()
  })

  it('inventory: CSS class is not an outlet; domain exclusions listed', () => {
    expect(DOMAIN_OWNED_FORMULA_EXCLUSIONS.length).toBeGreaterThan(0)
    const run = buildWorkpaperHostInventory({
      runId: 't13-css-not-slot',
      now: () => new Date('2026-09-08T12:00:00.000Z'),
      duplicates: [],
    })
    expect(run.outletBaseline.cssClassNotSlot).toBe(GT_WP_TOOLBAR_RIGHT_CSS_CLASS)
    expect(() => assertCssClassIsNotOutletCapability(GT_WP_TOOLBAR_RIGHT_CSS_CLASS, run)).not.toThrow()
  })

  it('location + capability: command requires ready G-C0 location + matching epoch', () => {
    const r = createOpenFormulaManagerCommand({
      location: loc(1),
      capability: snap(1),
    })
    expect(r.ok).toBe(true)
    expect(assertCapabilityAllowed(snap(1), 'formulaView', 1).status).toBe('allowed')
    expect(assertCapabilityAllowed(snap(1), 'formulaView', 9).status).toBe('blocked')
  })

  it('location missing/invalid major is rejected at command gate', () => {
    const bad = { ...loc(1), contractVersion: '9.0' as typeof GC0_CONTRACT_VERSION }
    const r = createOpenFormulaManagerCommand({
      location: bad,
      capability: snap(1),
    })
    expect(r.ok).toBe(false)
    if (!r.ok) expect(r.reasonCode).toBe('gc0_location_rejected')
  })

  it('outlet: primary wins; fallback must not steal', () => {
    const arb = new ToolbarOutletArbiter()
    arb.beginCycle(1)
    const el = document.createElement('span')
    el.setAttribute('data-toolbar-outlet', COMPATIBILITY_OUTLET_SLOT)
    arb.register({
      hostInstanceId: 'c',
      ownerEpoch: 1,
      kind: 'compatibility',
      outletElement: el,
      namedSlot: COMPATIBILITY_OUTLET_SLOT,
    })
    expect(arb.settle().status).toBe('pending')
  })

  it('dialog: dirty draft pins; does not follow latest', () => {
    const created = createOpenFormulaManagerCommand({
      location: loc(1, 1),
      capability: snap(1),
    })
    expect(created.ok).toBe(true)
    if (!created.ok) return
    let session = markSessionDirty(created.session)
    session = onLocationChangedWhileOpen(session, loc(1, 2))
    expect(session.pinnedLocation.contextRevision).toBe(1)
    expect(session.openedAtLocation.contextRevision).toBe(2)
  })

  it('provider: collision with different digests is blocked (not take-first)', () => {
    const agg = aggregateProviderResults(loc(), [
      {
        providerId: 'p1',
        verdict: 'ok',
        reason: null,
        descriptors: [descriptor('f1', 'aaa', 'p1')],
      },
      {
        providerId: 'p2',
        verdict: 'ok',
        reason: null,
        descriptors: [descriptor('f1', 'bbb', 'p2')],
      },
    ])
    expect(agg.collisions.length).toBe(1)
    expect(agg.status).toBe('blocked')
  })

  it('v2 API: function/category split; formula_type dual-sense forbidden', () => {
    expect(
      assertFunctionCategorySplit({
        formulaFunction: 'TB',
        ruleCategory: 'auto_calc',
      }).ok,
    ).toBe(true)
    expect(
      assertFunctionCategorySplit({
        formulaFunction: 'TB',
        ruleCategory: 'auto_calc',
        formula_type: 'TB',
      }).ok,
    ).toBe(false)
  })

  it('AI taxonomy: assist is DSH-only; a11y names unique', () => {
    expect(() => assertTaxonomyA11yUnique()).not.toThrow()
    expect(
      assertAiAssistCarrier({
        requestedCarrier: 'dsh-assist',
        usingAiReviewPermission: false,
      }).ok,
    ).toBe(true)
    expect(
      assertAiAssistCarrier({
        requestedCarrier: 'dsh-assist',
        usingAiReviewPermission: true,
      }).ok,
    ).toBe(false)
  })

  it('review: canonical key honest; no forged cell scope', () => {
    const key = buildCanonicalReviewThreadKey({
      projectId: 'p1',
      wpId: 'wp-1',
      anchorId: 'sec-1',
    })
    expect(key.sheetScope).toBe('page')
    expect(key.wire).not.toContain('cell:forged')
  })

  it('rail: invisible never occupies slot', () => {
    const arb = new RightRailArbiter()
    arb.setEpochs({ ownerEpoch: 1, capabilityEpoch: 1 })
    arb.register({
      id: 'guidance',
      order: 20,
      visible: false,
      disabledReason: 'hidden',
      ownerEpoch: 1,
      capabilityEpoch: 1,
      hasDraft: false,
      a11yName: '编制说明',
      open: () => undefined,
      close: () => undefined,
    })
    expect(arb.listTriggerSlots()[0]?.occupiesSlot).toBe(false)
  })

  it('a11y: Chinese names + broad-catch success forbidden', () => {
    expect(assertChineseAccessibleName(SHELL_A11Y_NAMES['rail-trigger'])).toBe(true)
    expect(assertNotBroadCatchSuccess({ caught: true, reportedSuccess: true }).ok).toBe(false)
  })
})

describe('Task 13: F-SHELL publish gate', () => {
  it('publishes F-SHELL identity, dependencies, and consumer list', () => {
    const contract = buildFShellContractSnapshot()
    expect(contract.contractId).toBe(FSHELL_CONTRACT_ID)
    expect(contract.contractVersion).toBe(FSHELL_CONTRACT_VERSION)
    expect(contract.dependsOn['G-C0']).toBe(GC0_CONTRACT_VERSION)
    expect(contract.dependsOn[GRAIL_CONTRACT_ID]).toBeDefined()
    expect(contract.consumers.length).toBe(3)
    expect(FSHELL_CAPABILITIES).toContain('rightRailArbiter')
    expect(FSHELL_NON_CAPABILITIES).toContain('fixed_rail_css')
  })

  it('consumer gate blocks unknown major and forbidden capabilities', () => {
    expect(
      assertFShellConsumerCompatible({
        consumerDeclaredVersion: '1.0',
        requiredCapabilities: ['canonicalLocationState', 'rightRailArbiter'],
      }).ok,
    ).toBe(true)
    expect(
      assertFShellConsumerCompatible({
        consumerDeclaredVersion: '2.0',
        requiredCapabilities: ['canonicalLocationState'],
      }).ok,
    ).toBe(false)
    expect(
      assertFShellConsumerCompatible({
        consumerDeclaredVersion: '1.0',
        requiredCapabilities: ['fixed_rail_css'],
      }).ok,
    ).toBe(false)
  })

  it('evidence payload is C0-shaped and ACCEPT at baseline wiring', () => {
    const payload = buildFShellEvidencePayload({ directedSuiteVerdict: 'PASS' })
    expect(payload.subject).toEqual({ kind: 'contract', contractId: FSHELL_CONTRACT_ID })
    expect(payload.verdict).toBe('PASS')
    const envelope = {
      contractVersion: GC0_CONTRACT_VERSION,
      evidenceId: String(payload.evidenceId),
      runId: String(payload.runId),
      subject: payload.subject as { kind: 'contract'; contractId: string },
      contractVersions: payload.contractVersions as Record<string, string>,
      inventoryDigest: null,
      sourceDigests: {},
      operationIds: {},
      artifacts: [],
      verdict: 'PASS' as const,
      recordedAt: String(payload.recordedAt),
    }
    expect(assertBaselineEnvelope(envelope).verdict).toBe('ACCEPT')
  })

  it('shell modules exist for every published capability touchpoint', () => {
    const root = join(__dirname, '..')
    const required = [
      'canonicalLocationState.ts',
      'workpaperCapabilitySnapshot.ts',
      'toolbarOutletArbiter.ts',
      'openFormulaManagerCommand.ts',
      'formulaProviderRegistry.ts',
      'userFormulaV2.ts',
      'aiActionTaxonomy.ts',
      'humanReviewProvider.ts',
      'rightRailArbiter.ts',
      'shellLayoutTokens.ts',
      'shellA11y.ts',
      'fShellContract.ts',
      'WorkpaperCapabilityShell.vue',
    ]
    for (const file of required) {
      expect(existsSync(join(root, file)), file).toBe(true)
      expect(readFileSync(join(root, file), 'utf8').length).toBeGreaterThan(20)
    }
  })
})
