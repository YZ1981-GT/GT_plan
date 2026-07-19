/**
 * G4 全链路回归：分类回写 / 利息回写 / 异常路由 / 套件状态 / 存储契约 / IE 形状
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  applyG4ClassificationUpdates,
  applyG44InterestToDetailRows,
  deriveG4MeasurementClassification,
} from '../g4CrossHelpers'
import {
  applyEclRateUpdatesToRows,
  collectEclRateUpdates,
} from '../useG4EclImpairmentCalc'
import {
  buildG44InterestVarianceDraft,
  buildG410ImpairmentDrafts,
  persistExceptionDraftsToMainWp,
} from '../g4ExceptionRouting'
import { mergeProvenanceDrafts } from '../useG4MainAdjustment'
import { evaluateG4SuiteStatus } from '../g4SuiteStatus'
import { G4_ITEM_IDS, buildCanonicalPayload, parseCanonicalArray } from '../g4StorageContract'
import {
  flattenInterestGroupsToRows,
  nestFlatInterestRows,
} from '../useG4MainInterestCalc'

const {
  resolveG4MainWorkpaperId,
  fetchCanonicalRowsFromWorkpaper,
  saveCanonicalRowsToWorkpaper,
} = vi.hoisted(() => ({
  resolveG4MainWorkpaperId: vi.fn(),
  fetchCanonicalRowsFromWorkpaper: vi.fn(),
  saveCanonicalRowsToWorkpaper: vi.fn(),
}))

vi.mock('../g4CrossHelpers', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../g4CrossHelpers')>()
  return {
    ...actual,
    resolveG4MainWorkpaperId,
    fetchCanonicalRowsFromWorkpaper,
    saveCanonicalRowsToWorkpaper,
  }
})

describe('G4 full-chain regression', () => {
  beforeEach(() => {
    resolveG4MainWorkpaperId.mockReset()
    fetchCanonicalRowsFromWorkpaper.mockReset()
    saveCanonicalRowsToWorkpaper.mockReset()
  })

  it('G4-5/6 classification writeback prefers stable id and derives AC', () => {
    const rows = [
      {
        id: 'inv-1',
        investProject: '国债A',
        crossSheetInvestmentId: 'inv-1',
        businessModelResult: '',
        sppiResult: '',
        measurementClassification: 'INCOMPLETE',
      },
    ]
    const result = applyG4ClassificationUpdates(rows, [{
      investmentId: 'inv-1',
      investProject: '国债A-别名',
      businessModelResult: 'AC',
      sppiResult: 'PASS',
      classificationSource: 'G4-5/G4-6',
    }])
    expect(result.matched).toEqual(['国债A'])
    expect(result.rows[0].measurementClassification).toBe('AC')
    expect(deriveG4MeasurementClassification('FVOCI', 'PASS')).toBe('FVOCI')
    expect(deriveG4MeasurementClassification('AC', 'FAIL')).toBe('FVTPL')
  })

  it('G4-4 interest writeback uses amortization proxy, not total interest', () => {
    const detail = [{
      id: 'inv-1',
      crossSheetInvestmentId: 'inv-1',
      investProject: '债A',
      periodCostChange: 0,
      periodInterestAdjChange: 0,
      periodAccruedInterestChange: 0,
      periodChangeSubtotal: 0,
      openingInterestAdj: 10,
      closingInterestAdj: 0,
      closingCost: 100,
      closingAccruedInterest: 0,
      closingSubtotal: 0,
      closingAdjustment: 0,
      closingAudited: 0,
      amortizedCost: 0,
      closingImpairment: 0,
      oneYearSubtotal: 0,
      bookValue: 0,
    }]
    const result = applyG44InterestToDetailRows(detail, [{
      id: 'inv-1',
      projectName: '债A',
      periods: [
        { effectiveInterest: 12, cashInflow: 10 },
        { effectiveInterest: 8, cashInflow: 10 },
      ],
    }])
    expect(result.matched).toHaveLength(1)
    expect(result.rows[0].periodInterestAdjChange).toBe(0) // 12-10 + 8-10 = 0
  })

  it('G4-4 nest/flatten round-trips rates percent↔decimal for IE compat key', () => {
    const nested = [{
      id: 'g1',
      projectName: '国债A',
      initial: {
        faceValueTotal: 100,
        initialDate: '2024-01-01',
        maturityDate: '2029-01-01',
        purchasePrice: 98,
        transactionCost: 1,
        initialCarryingAmount: 99,
        couponRate: 0.035,
        effectiveRate: 0.04,
      },
      periods: [{
        id: 'p1',
        cutoffDate: '2025-12-31',
        openingBalance: 99,
        openingImpairment: 0,
        openingAmortizedCost: 99,
        effectiveInterest: 3.96,
        cashInflow: 3.5,
        principalRepaid: 0,
        closingBalance: 99.46,
        days: 365,
        stage: 'Stage1' as const,
      }],
    }]
    const flat = flattenInterestGroupsToRows(nested as any)
    expect(flat[0].couponRate).toBe(3.5)
    expect(flat[0].effectiveRate).toBe(4)
    const restored = nestFlatInterestRows(flat)
    expect(restored).toHaveLength(1)
    expect(restored[0].initial.couponRate).toBeCloseTo(0.035, 6)
    expect(restored[0].initial.effectiveRate).toBeCloseTo(0.04, 6)
    expect(restored[0].periods[0].cutoffDate).toBe('2025-12-31')
  })

  it('G4-11→G4-10 rate transfer is id-first and reports match channels', () => {
    const base = [{
      id: 'r1',
      seq: 1,
      investProject: '债A',
      crossSheetInvestmentId: 'stable-1',
      stageGroup: 'Stage1' as const,
      bookBalance: 100,
      pvFutureCashFlow: 0,
      adjustedPvFutureCashFlow: 0,
      creditLossRate: 0,
      impairmentProvision: 0,
      bookValue: 0,
      balanceAdjustment: 0,
      adjustedCreditLossRate: 0,
      adjRateTouched: false,
      impairmentAdjustment: 0,
      adjBookBalance: 0,
      adjImpairment: 0,
      adjBookValue: 0,
      priorImpairment: 0,
      currentProvision: 0,
      currentReversal: 0,
      differenceNote: '',
    }]
    const updates = collectEclRateUpdates(
      [{ id: 'stable-1', projectName: '债A-别名', eclRate: 0.05, stage: 'Stage1' }],
      null,
      'pdLgd',
    )
    const applied = applyEclRateUpdatesToRows(base, updates)
    expect(applied.count).toBe(1)
    expect(applied.matchReport.byId).toEqual(['债A'])
    expect(applied.rows[0].creditLossRate).toBe(0.05)
  })

  it('exception drafts are provenance-idempotent', () => {
    const drafts = [
      ...buildG44InterestVarianceDraft(100, { description: 'interest' }),
      ...buildG410ImpairmentDrafts([
        {
          id: 'r1',
          investProject: '债A',
          impairmentAdjustment: 50,
          differenceNote: 'ecl gap',
        },
      ]),
    ]
    const once = mergeProvenanceDrafts([], drafts)
    const twice = mergeProvenanceDrafts(once.entries, drafts)
    expect(once.entries.length).toBeGreaterThan(0)
    expect(twice.entries.length).toBe(once.entries.length)
    expect(twice.added + twice.updated).toBe(0)
  })

  it('persistExceptionDraftsToMainWp writes Main only; resolver miss skips save', async () => {
    const drafts = buildG44InterestVarianceDraft(50)
    resolveG4MainWorkpaperId.mockResolvedValueOnce(null)
    expect(await persistExceptionDraftsToMainWp(drafts, { projectId: 'p1' })).toBeNull()
    expect(saveCanonicalRowsToWorkpaper).not.toHaveBeenCalled()

    resolveG4MainWorkpaperId.mockResolvedValueOnce('main-wp')
    fetchCanonicalRowsFromWorkpaper.mockResolvedValueOnce([])
    saveCanonicalRowsToWorkpaper.mockResolvedValueOnce(undefined)
    const result = await persistExceptionDraftsToMainWp(drafts, { projectId: 'p1' })
    expect(result).toMatchObject({ mainWpId: 'main-wp', added: drafts.length })
    expect(saveCanonicalRowsToWorkpaper).toHaveBeenCalledWith(
      'main-wp',
      'p1',
      G4_ITEM_IDS.G4_3_ROWS,
      expect.any(Array),
    )
  })

  it('canonical payload dual-writes conclusion+remark and parses either', () => {
    const payload = buildCanonicalPayload(G4_ITEM_IDS.G4_2_ROWS, [{ id: '1' }])
    expect(payload.conclusion).toBeTruthy()
    expect(payload.remark).toBe(payload.conclusion)
    expect(parseCanonicalArray({ conclusion: payload.conclusion, remark: null } as any)).toHaveLength(1)
    expect(parseCanonicalArray({ conclusion: null, remark: payload.remark } as any)).toHaveLength(1)
  })

  it('suite status evaluates G4A–G4-13 without throwing', () => {
    const status = evaluateG4SuiteStatus(new Map())
    expect(status.length).toBeGreaterThanOrEqual(14)
    expect(status.some(s => s.code === 'G4-1')).toBe(true)
    expect(status.some(s => s.code === 'G4-13')).toBe(true)
  })

  it('G4-12 suite gate prefers aggregate G4-12-rows over split keys', () => {
    const map = new Map([
      [
        G4_ITEM_IDS.G4_12_ROWS,
        buildCanonicalPayload(G4_ITEM_IDS.G4_12_ROWS, {
          reversals: [{ reversalAmount: 10, accumulatedProvision: 20, isReasonable: '合理' }],
          writeOffs: [{ writeOffAmount: 5, isReasonable: '合理', isRelatedParty: false }],
        }),
      ],
      [
        G4_ITEM_IDS.G4_12_REVERSALS,
        buildCanonicalPayload(G4_ITEM_IDS.G4_12_REVERSALS, [
          { reversalAmount: 999, accumulatedProvision: 1, isReasonable: '不合理' },
        ]),
      ],
    ])
    const g12 = evaluateG4SuiteStatus(map).find((s) => s.code === 'G4-12')
    expect(g12?.hasData).toBe(true)
    expect(g12?.gate).toBe(true)
  })
})
