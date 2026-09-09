/**
 * Formula-toolbar Task 2 — dynamic host inventory + mounted red baseline.
 *
 * **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 4.1, 13.2**
 */

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it, beforeEach } from 'vitest'

import { REGISTRY_LIST } from '@/components/workpaper/registry'
import {
  DOMAIN_OWNED_FORMULA_EXCLUSIONS,
  GT_WP_TOOLBAR_RIGHT_CSS_CLASS,
  PRIMARY_OUTLET_SLOT,
  COMPATIBILITY_OUTLET_SLOT,
  assertCssClassIsNotOutletCapability,
  buildWorkpaperHostInventory,
  inspectGtWpToolbarOutlets,
  loadGtWpToolbarSource,
  registerHostAdapterTelemetry,
  resetHostAdapterTelemetry,
  scanDuplicateCapabilityFindings,
} from '@/shell/formula'

const EVIDENCE_DIR = join(
  __dirname,
  '../../../../../../.kiro/specs/workpaper-page-formula-toolbar-closure/basis',
)

describe('Task 2: workpaper host inventory', () => {
  beforeEach(() => {
    resetHostAdapterTelemetry()
  })

  it('derives entry count from REGISTRY_LIST (+ custom), not a hardcoded page list', () => {
    const run = buildWorkpaperHostInventory({
      runId: 'test-static',
      now: () => new Date('2026-09-08T12:00:00.000Z'),
      duplicates: [],
    })
    expect(run.entries.length).toBe(REGISTRY_LIST.length)
    expect(run.entries.length).toBeGreaterThan(50)

    const withCustom = buildWorkpaperHostInventory({
      runId: 'test-custom',
      now: () => new Date('2026-09-08T12:00:00.000Z'),
      runtimeCustomEntries: [
        {
          entryId: 'custom:runtime-1',
          componentType: 'custom',
          host: 'onlyoffice',
          reason: 'runtime custom workbook',
        },
      ],
      duplicates: [],
    })
    expect(withCustom.entries.length).toBe(REGISTRY_LIST.length + 1)
    expect(withCustom.entries.some((e) => e.entryId === 'custom:runtime-1')).toBe(true)
  })

  it('each entry carries required inventory fields (Req 1.2)', () => {
    const run = buildWorkpaperHostInventory({
      hostPolicies: [
        { componentType: 'd2-accounts-receivable', hostPolicy: 'html' },
        { componentType: 'word-template', hostPolicy: 'word' },
      ],
      renderConfigComponentTypes: ['d2-accounts-receivable'],
      runId: 'fields',
      now: () => new Date('2026-09-08T12:00:00.000Z'),
      duplicates: [],
    })
    for (const e of run.entries) {
      expect(e.inventoryVersion).toBe('1.0')
      expect(e.entryId).toBeTruthy()
      expect(e.componentType).toBeTruthy()
      expect(e.routeScope).toBe('workpaper')
      expect(['html', 'univer', 'onlyoffice', 'grid', 'word']).toContain(e.host)
      expect(e.primaryOutlet).toMatch(/^(supported|unsupported|pending)$/)
      expect(e.compatibilityOutlet).toMatch(/^(supported|unsupported|pending)$/)
      expect(e.sourceDigest).toMatch(/^[a-f0-9]{64}$/)
      expect(e.evidenceState).toMatch(/^(observed|derived|blocked|excluded)$/)
    }
    const observed = run.entries.find((e) => e.componentType === 'd2-accounts-receivable')
    expect(observed?.evidenceState).toBe('observed')
  })

  it('records domain exclusions without counting them as workpaper duplicates (Req 1.4)', () => {
    const run = buildWorkpaperHostInventory({
      runId: 'excl',
      now: () => new Date('2026-09-08T12:00:00.000Z'),
      duplicates: scanDuplicateCapabilityFindings(),
    })
    expect(run.domainExclusions.length).toBe(DOMAIN_OWNED_FORMULA_EXCLUSIONS.length)
    expect(run.domainExclusions.map((d) => d.relativePath)).toContain('views/TrialBalance.vue')
    for (const d of run.duplicates) {
      expect(DOMAIN_OWNED_FORMULA_EXCLUSIONS.some((e) => e.relativePath === d.relativePath)).toBe(
        false,
      )
    }
  })

  it('empty telemetry ⇒ no supported outlets; CSS class is not capability (Req 1.3 / 4.1)', () => {
    const toolbar = inspectGtWpToolbarOutlets(loadGtWpToolbarSource())
    expect(toolbar.hasRightCssClass).toBe(true)
    // Task 5 added a real named compatibility slot; CSS class alone still is not the outlet.
    expect(
      toolbar.hasPageCapabilitiesCompatibilitySlot,
      'hasPageCapabilitiesCompatibilitySlot',
    ).toBe(true)
    expect(
      toolbar.hasPageCapabilitiesPrimarySlot,
      'hasPageCapabilitiesPrimarySlot',
    ).toBe(false)
    expect(toolbar.namedSlots).toContain(COMPATIBILITY_OUTLET_SLOT)
    expect(toolbar.namedSlots).not.toContain(PRIMARY_OUTLET_SLOT)

    const run = buildWorkpaperHostInventory({
      runId: 'css-not-slot',
      now: () => new Date('2026-09-08T12:00:00.000Z'),
      duplicates: [],
    })
    expect(run.outletBaseline.cssClassNotSlot).toBe(GT_WP_TOOLBAR_RIGHT_CSS_CLASS)
    expect(run.outletBaseline.primaryNamedOutletMounted).toBe(false)
    expect(run.entries.every((e) => e.primaryOutlet !== 'supported')).toBe(true)
    expect(() =>
      assertCssClassIsNotOutletCapability(GT_WP_TOOLBAR_RIGHT_CSS_CLASS, run),
    ).not.toThrow()
  })

  it('only named-outlet telemetry can flip primaryOutlet to supported', () => {
    registerHostAdapterTelemetry({
      hostInstanceId: 'h1',
      componentType: 'd2-accounts-receivable',
      host: 'html',
      primaryOutlet: 'supported',
      compatibilityOutlet: 'unsupported',
      namedOutletMounted: true,
      namedOutletSlot: PRIMARY_OUTLET_SLOT,
      registeredAt: 1,
      source: 'test',
    })
    const run = buildWorkpaperHostInventory({
      runId: 'tele',
      now: () => new Date('2026-09-08T12:00:00.000Z'),
      duplicates: [],
    })
    expect(run.outletBaseline.primaryNamedOutletMounted).toBe(true)
    const d2 = run.entries.find((e) => e.componentType === 'd2-accounts-receivable')
    expect(d2?.primaryOutlet).toBe('supported')
  })

  it('rejects CSS selector as namedOutletSlot (mounted red guard)', () => {
    expect(() =>
      registerHostAdapterTelemetry({
        hostInstanceId: 'bad',
        componentType: null,
        host: 'html',
        primaryOutlet: 'supported',
        compatibilityOutlet: 'unsupported',
        namedOutletMounted: true,
        namedOutletSlot: `.${GT_WP_TOOLBAR_RIGHT_CSS_CLASS}`,
        registeredAt: 1,
        source: 'test',
      }),
    ).toThrow(/CSS class/)
  })

  it('enumerates duplicate AI/review/rail/formula findings with digests', () => {
    const duplicates = scanDuplicateCapabilityFindings()
    expect(duplicates.some((d) => d.kind === 'formula-entry')).toBe(true)
    expect(duplicates.some((d) => d.kind === 'ai-assist' || d.kind === 'ai-review-panel')).toBe(
      true,
    )

    const run = buildWorkpaperHostInventory({
      runId: 'dup-run',
      now: () => new Date('2026-09-08T12:00:00.000Z'),
      duplicates,
    })
    expect(run.digests.entries).toMatch(/^[a-f0-9]{64}$/)
    expect(run.digests.duplicates).toMatch(/^[a-f0-9]{64}$/)
    expect(run.digests.exclusions).toMatch(/^[a-f0-9]{64}$/)
    expect(run.digests.run).toMatch(/^[a-f0-9]{64}$/)

    mkdirSync(EVIDENCE_DIR, { recursive: true })
    const outPath = join(EVIDENCE_DIR, 'T02-host-inventory-run.json')
    writeFileSync(
      outPath,
      JSON.stringify(
        {
          inventoryVersion: run.inventoryVersion,
          generatedAt: run.generatedAt,
          runId: run.runId,
          entryCount: run.entries.length,
          duplicateCount: run.duplicates.length,
          domainExclusionCount: run.domainExclusions.length,
          outletBaseline: run.outletBaseline,
          digests: run.digests,
          sampleDuplicates: run.duplicates.slice(0, 30),
        },
        null,
        2,
      ),
      'utf8',
    )
    const saved = JSON.parse(readFileSync(outPath, 'utf8'))
    expect(saved.digests.run).toBe(run.digests.run)
  })

  it('GtWpToolbar source still documents center slot only — __right is CSS (Req 4.1)', () => {
    const src = loadGtWpToolbarSource()
    expect(src).toContain('gt-wp-toolbar__right')
    expect(src).toMatch(/\$slots\.center|<slot name="center"/)
    expect(src).toMatch(/slot name=["']page-capabilities-compatibility["']/)
    expect(src).not.toMatch(/slot name=["']page-capabilities-primary["']/)
    // Mutation anchor: must not document __right as a Vue slot.
    expect(src).not.toMatch(/GtWpToolbar\.__right|slot name=["']__right["']/)
  })
})
