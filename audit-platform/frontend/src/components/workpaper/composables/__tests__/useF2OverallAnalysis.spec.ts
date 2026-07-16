/**
 * useF2OverallAnalysis — F2-18 pack v2
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { ref, computed } from 'vue'
import { useF2OverallAnalysis } from '../useF2OverallAnalysis'
import type { ChecklistResponse } from '../useF2FormData'

function mockCrossSheet(closingByKey: Record<string, number> = {}) {
  return {
    categorySummaries: computed(() =>
      Object.entries(closingByKey).map(([rowKey, closingAmt]) => ({
        rowKey,
        label: rowKey,
        sheetCode: '',
        accountCode: '',
        openingAmt: closingAmt * 0.8,
        increaseAmt: 0,
        decreaseAmt: 0,
        closingAmt,
      })),
    ),
    detailGrandTotal: computed(() =>
      Object.values(closingByKey).reduce((a, b) => a + b, 0),
    ),
    detailOpeningTotal: computed(() =>
      Object.values(closingByKey).reduce((a, b) => a + b * 0.8, 0),
    ),
  } as any
}

describe('useF2OverallAnalysis F2-18 rebuild', () => {
  beforeEach(() => {
    window.addEventListener('f2:save-items', () => {})
  })
  afterEach(() => {
    window.removeEventListener('f2:save-items', () => {})
  })

  it('defaults to 13 composition categories', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const oa = useF2OverallAnalysis({
      allResponses: map,
      crossSheet: mockCrossSheet(),
      isReadonly: ref(false),
    })
    expect(oa.compositionRows.value).toHaveLength(13)
    expect(oa.indicatorRows.value).toHaveLength(5)
    expect(oa.productRows.value.length).toBeGreaterThanOrEqual(1)
  })

  it('computes structure share and indicator turnover', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const oa = useF2OverallAnalysis({
      allResponses: map,
      crossSheet: mockCrossSheet({ 'raw-materials': 60, 'finished-goods': 40 }),
      isReadonly: ref(false),
    })
    oa.syncCompositionFromDetail()
    const raw = oa.compositionRows.value.find((r) => r.key === 'raw-materials')!
    const fg = oa.compositionRows.value.find((r) => r.key === 'finished-goods')!
    expect(raw.amt0).toBe(60)
    expect(fg.amt0).toBe(40)
    expect(Math.round(raw.share0)).toBe(60)
    expect(Math.round(fg.share0)).toBe(40)

    oa.updateInput('cogs0', 200)
    oa.updateInput('invAvg0', 50)
    const turnover = oa.indicatorRows.value.find((r) => r.key === 'turnover')!
    expect(turnover.v0).toBe(4)
    expect(turnover.unit).toBe('次')
    const days = oa.indicatorRows.value.find((r) => r.key === 'days')!
    expect(Math.round(days.v0)).toBe(91)
  })

  it('persists version 2 pack', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const oa = useF2OverallAnalysis({
      allResponses: map,
      crossSheet: mockCrossSheet(),
      isReadonly: ref(false),
    })
    oa.updateComposition('raw-materials', 'amt0', 100)
    oa.updateNotes('notesA', 'note', '构成未见重大异常')
    oa.analysisConclusion.value = 'A、未见异常。'

    const stored = map.value.get('F2-18-pack')?.remark
    expect(stored).toBeTruthy()
    const parsed = JSON.parse(stored!)
    expect(parsed.version).toBe(2)
    expect(parsed.notesA.note).toContain('构成')
    expect(parsed.auditConclusion).toContain('未见异常')
  })

  it('computes industry deviation', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const oa = useF2OverallAnalysis({
      allResponses: map,
      crossSheet: mockCrossSheet(),
      isReadonly: ref(false),
    })
    oa.updateInput('cogs0', 100)
    oa.updateInput('invAvg0', 50) // turnover = 2
    oa.updateIndustryPeer('avg', 'turnover', 4)
    const row = oa.industryRows.value.find((r) => r.key === 'turnover')!
    expect(row.client).toBe(2)
    expect(row.deviation).toBe(-50)
  })
})
