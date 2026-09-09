import { describe, it, expect } from 'vitest'
import {
  decideRoute,
  isCapabilityEligible,
  DEFAULT_BUNDLE_BUDGET,
  type RouteMeasurement,
} from '../bundleBudget'

const eligibleCap = {
  archiveLimits: true,
  emailIsolation: true,
  dxf: true,
  disposable: true,
  license: true,
}

describe('decideRoute capability-before-budget', () => {
  it('entryParserBytes 预算真源为 0', () => {
    expect(DEFAULT_BUNDLE_BUDGET.entryParserBytes).toBe(0)
  })

  it('A 资格失败时即使体积更小也不得入选', () => {
    const measurements: RouteMeasurement[] = [
      {
        route: 'A',
        capability: { ...eligibleCap, archiveLimits: false },
        entryGzip: 1000,
        entryGzipDelta: 100,
        chunks: { archive: 10, email: 10, drawing: 10 },
        moduleIdsPresent: ['a'],
      },
      {
        route: 'B',
        capability: eligibleCap,
        entryGzip: 50000,
        entryGzipDelta: 2000,
        chunks: { archive: 80_000, email: 200_000, drawing: 100_000 },
        moduleIdsPresent: ['b'],
      },
    ]
    const d = decideRoute(measurements)
    expect(isCapabilityEligible(measurements[0].capability)).toBe(false)
    expect(d.selected).toBe('B')
    expect(d.eligibleRoutes).toEqual(['B'])
    expect(d.drawingInScope).toBe(true)
  })

  it('A eligible 但首屏超门 → B', () => {
    const measurements: RouteMeasurement[] = [
      {
        route: 'A',
        capability: eligibleCap,
        entryGzip: 90000,
        entryGzipDelta: 20_000,
        chunks: { archive: 10, email: 10, drawing: 10 },
        moduleIdsPresent: ['a'],
      },
      {
        route: 'B',
        capability: eligibleCap,
        entryGzip: 40000,
        entryGzipDelta: 1000,
        chunks: { archive: 80_000, email: 200_000, drawing: 100_000 },
        moduleIdsPresent: ['b'],
      },
    ]
    const d = decideRoute(measurements)
    expect(d.selected).toBe('B')
    expect(d.reason).toBe('A_entry_over_budget_fallback_B')
  })

  it('drawing 超门 → drawing_drop 且 drawingInScope=false', () => {
    const measurements: RouteMeasurement[] = [
      {
        route: 'B',
        capability: eligibleCap,
        entryGzip: 1000,
        entryGzipDelta: 100,
        chunks: {
          archive: 10_000,
          email: 10_000,
          drawing: DEFAULT_BUNDLE_BUDGET.drawingChunk + 1,
        },
        moduleIdsPresent: ['b'],
      },
    ]
    const d = decideRoute(measurements)
    expect(d.kind).toBe('drawing_drop')
    expect(d.selected).toBe('B')
    expect(d.drawingInScope).toBe(false)
  })

  it('无合资格路线 → ineligible', () => {
    const d = decideRoute([
      {
        route: 'A',
        capability: { ...eligibleCap, license: false },
        entryGzip: 1,
        entryGzipDelta: 0,
        chunks: { archive: 1, email: 1, drawing: 1 },
        moduleIdsPresent: [],
      },
    ])
    expect(d.kind).toBe('ineligible')
    expect(d.selected).toBeNull()
  })

  it('按需 chunk 合计超门 → subset_required（各 chunk 分别核算总量）', () => {
    // drawing 单项在门内，但 archive+email+drawing 合计超 onDemandTotal ⇒ 必须缩子集
    const measurements: RouteMeasurement[] = [
      {
        route: 'B',
        capability: eligibleCap,
        entryGzip: 1000,
        entryGzipDelta: 100,
        chunks: {
          // drawing 单项在门内；archive+email+drawing 合计明显超 onDemandTotal ⇒ subset
          archive: DEFAULT_BUNDLE_BUDGET.onDemandTotal,
          email: DEFAULT_BUNDLE_BUDGET.emailChunk,
          drawing: DEFAULT_BUNDLE_BUDGET.drawingChunk,
        },
        moduleIdsPresent: ['b'],
      },
    ]
    const d = decideRoute(measurements)
    expect(d.kind).toBe('subset_required')
    expect(d.reason).toBe('on_demand_total_over_budget')
  })

  it('entryGzipDelta 首屏增量门为 8 KiB 单一真源', () => {
    expect(DEFAULT_BUNDLE_BUDGET.entryGzipDelta).toBe(8 * 1024)
  })
})
