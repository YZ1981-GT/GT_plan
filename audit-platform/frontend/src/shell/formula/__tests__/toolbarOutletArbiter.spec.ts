/**
 * Formula-toolbar Task 5 — toolbar outlet arbiter + named slots.
 */

import { describe, expect, it, beforeEach } from 'vitest'

import {
  COMPATIBILITY_OUTLET_SLOT,
  PRIMARY_OUTLET_SLOT,
} from '@/shell/formula/outletSlots'
import {
  ToolbarOutletArbiter,
  resetToolbarOutletArbiter,
} from '@/shell/formula/toolbarOutletArbiter'
import {
  inspectGtWpToolbarOutlets,
  loadGtWpToolbarSource,
} from '@/shell/formula/hostInventoryScanners'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

function el(attrs: Record<string, string> = {}): HTMLElement {
  const node = document.createElement('span')
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v)
  return node
}

describe('Task 5: named outlets + placement arbiter', () => {
  beforeEach(() => {
    resetToolbarOutletArbiter()
  })

  it('GtWpToolbar exposes real page-capabilities-compatibility slot (not CSS-as-slot)', () => {
    const toolbar = inspectGtWpToolbarOutlets(loadGtWpToolbarSource())
    expect(toolbar.hasPageCapabilitiesCompatibilitySlot).toBe(true)
    expect(toolbar.hasRightCssClass).toBe(true)
    expect(loadGtWpToolbarSource()).toContain('data-toolbar-outlet="page-capabilities-compatibility"')
  })

  it('primary host source uses named slot page-capabilities-primary', () => {
    const src = readFileSync(
      join(__dirname, '../WorkpaperPrimaryCapabilitiesHost.vue'),
      'utf8',
    )
    expect(src).toMatch(/slot name=["']page-capabilities-primary["']/)
    expect(src).toContain(`data-toolbar-outlet="${PRIMARY_OUTLET_SLOT}"`)
  })

  it('ThreeColumnLayout mounts primary host after AI and before 金额单位', () => {
    const src = readFileSync(
      join(__dirname, '../../../layouts/ThreeColumnLayout.vue'),
      'utf8',
    )
    const ai = src.indexOf('<!-- AI 助手快捷入口 -->')
    const primary = src.indexOf('<WorkpaperPrimaryCapabilitiesHost')
    const amount = src.indexOf('<!-- 金额单位快捷（保证 AI')
    expect(ai).toBeGreaterThan(0)
    expect(primary).toBeGreaterThan(ai)
    expect(amount).toBeGreaterThan(primary)
  })

  it('primary wins; compatibility waits until primary unavailable', () => {
    const arbiter = new ToolbarOutletArbiter()
    arbiter.beginCycle(1)
    const primaryEl = el({ 'data-toolbar-outlet': PRIMARY_OUTLET_SLOT })
    const compatEl = el({ 'data-toolbar-outlet': COMPATIBILITY_OUTLET_SLOT })

    expect(
      arbiter.register({
        hostInstanceId: 'p1',
        ownerEpoch: 1,
        kind: 'primary',
        outletElement: primaryEl,
        namedSlot: PRIMARY_OUTLET_SLOT,
      }).ok,
    ).toBe(true)
    expect(
      arbiter.register({
        hostInstanceId: 'c1',
        ownerEpoch: 1,
        kind: 'compatibility',
        outletElement: compatEl,
        namedSlot: COMPATIBILITY_OUTLET_SLOT,
      }).ok,
    ).toBe(true)

    let placement = arbiter.settle()
    expect(placement.status).toBe('registered')
    if (placement.status === 'registered') {
      expect(placement.selected.kind).toBe('primary')
    }

    // Without primary: compat must not steal while primary still considered available
    const arb2 = new ToolbarOutletArbiter()
    arb2.beginCycle(2)
    arb2.register({
      hostInstanceId: 'c2',
      ownerEpoch: 2,
      kind: 'compatibility',
      outletElement: compatEl,
      namedSlot: COMPATIBILITY_OUTLET_SLOT,
    })
    placement = arb2.settle()
    expect(placement.status).toBe('pending')

    arb2.markPrimaryUnavailable(2, true)
    placement = arb2.settle()
    expect(placement.status).toBe('registered')
    if (placement.status === 'registered') {
      expect(placement.selected.kind).toBe('compatibility')
    }
  })

  it('rejects duplicate kind, cross-epoch, and CSS-class-only outlet', () => {
    const arbiter = new ToolbarOutletArbiter()
    arbiter.beginCycle(3)
    const a = el({ 'data-toolbar-outlet': PRIMARY_OUTLET_SLOT })
    const b = el({ 'data-toolbar-outlet': PRIMARY_OUTLET_SLOT })
    expect(
      arbiter.register({
        hostInstanceId: 'h1',
        ownerEpoch: 3,
        kind: 'primary',
        outletElement: a,
        namedSlot: PRIMARY_OUTLET_SLOT,
      }).ok,
    ).toBe(true)
    const dup = arbiter.register({
      hostInstanceId: 'h2',
      ownerEpoch: 3,
      kind: 'primary',
      outletElement: b,
      namedSlot: PRIMARY_OUTLET_SLOT,
    })
    expect(dup.ok).toBe(false)
    if (!dup.ok) expect(dup.reasonCode).toBe('duplicate_kind_collision')

    const cross = arbiter.register({
      hostInstanceId: 'h3',
      ownerEpoch: 99,
      kind: 'compatibility',
      outletElement: el({ 'data-toolbar-outlet': COMPATIBILITY_OUTLET_SLOT }),
      namedSlot: COMPATIBILITY_OUTLET_SLOT,
    })
    expect(cross.ok).toBe(false)

    const cssOnly = document.createElement('div')
    cssOnly.className = 'gt-wp-toolbar__right'
    const css = arbiter.register({
      hostInstanceId: 'h4',
      ownerEpoch: 3,
      kind: 'compatibility',
      outletElement: cssOnly,
      namedSlot: COMPATIBILITY_OUTLET_SLOT,
    })
    expect(css.ok).toBe(false)
    if (!css.ok) expect(css.reasonCode).toBe('css_class_not_outlet')
  })
})
