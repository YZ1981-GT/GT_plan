/**
 * Unit tests for useG2Detail composable
 * Validates: 纸质滚动核对 + 账龄枚举
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useG2Detail } from '../useG2Detail'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...actual as any,
    onBeforeUnmount: vi.fn(),
  }
})

vi.mock('@/composables/useAgingConfig', async () => {
  const actual = await vi.importActual<any>('@/composables/useAgingConfig')
  return {
    ...actual,
    useAgingConfig: () => ({
      segments: ref(actual.PRESET_SEGMENTS.THREE_YEAR),
      preset: ref('THREE_YEAR'),
      bands: ref([]),
      loading: ref(false),
      refresh: vi.fn(),
    }),
  }
})

function createOptions(storedRows: any[] = []) {
  const allResponses = ref(new Map<string, any>())
  if (storedRows.length > 0) {
    allResponses.value.set('G2-2-detail-rows', {
      item_id: 'G2-2-detail-rows',
      conclusion: null,
      remark: JSON.stringify(storedRows),
    })
  }
  return {
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    allResponses,
    isReadonly: ref(false),
  }
}

function createStoredRow(overrides: Partial<any> = {}) {
  return {
    id: `test-${Math.random().toString(36).slice(2, 6)}`,
    seq: 1,
    investTarget: '某债券',
    investType: '债权投资',
    openingUnadjusted: 10000,
    openingAdjustment: 0,
    debit: 5000,
    credit: 2000,
    closingAdjustment: 0,
    interestDueDate: '2025-12-31',
    accrualPeriod: '2025H1',
    collectionStatus: '',
    faceValue: 1000000,
    couponRate: 5,
    accrualStart: '2025-01-01',
    accrualEnd: '2025-07-01',
    receivedInterest: 0,
    eclStage: 'Stage1' as const,
    remark: '',
    indexRef: '',
    ...overrides,
  }
}

describe('useG2Detail', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('roll-forward formulas', () => {
    it('期初审定 = 期初余额 + 期初调整', () => {
      const row = createStoredRow({ openingUnadjusted: 1000, openingAdjustment: 50 })
      const { dataRows } = useG2Detail(createOptions([row]))
      expect(dataRows.value[0].openingAudited).toBe(1050)
    })

    it('期末余额 = 期初审定 + 借方 − 贷方', () => {
      const row = createStoredRow({
        openingUnadjusted: 10000,
        openingAdjustment: 0,
        debit: 5000,
        credit: 2000,
      })
      const { dataRows } = useG2Detail(createOptions([row]))
      expect(dataRows.value[0].closingUnadjusted).toBe(13000)
    })

    it('期末审定 = 期末余额 + 账项调整', () => {
      const row = createStoredRow({
        openingUnadjusted: 10000,
        debit: 5000,
        credit: 2000,
        closingAdjustment: -100,
      })
      const { dataRows } = useG2Detail(createOptions([row]))
      expect(dataRows.value[0].closingAudited).toBe(12900)
    })

    it('旧版 bookValue 迁移为期初余额', () => {
      const row = {
        id: 'legacy-1',
        seq: 1,
        investTarget: '旧债',
        investType: '债权投资',
        bookValue: 8888,
        faceValue: 0,
        couponRate: 0,
        accrualStart: '',
        accrualEnd: '',
        receivedInterest: 0,
        eclStage: 'Stage1',
        remark: '',
        indexRef: '',
      }
      const { dataRows } = useG2Detail(createOptions([row]))
      expect(dataRows.value[0].openingUnadjusted).toBe(8888)
      expect(dataRows.value[0].openingAudited).toBe(8888)
      expect(dataRows.value[0].closingAudited).toBe(8888)
    })
  })

  describe('interest check formulas', () => {
    it('计息天数与应计利息', () => {
      const row = createStoredRow({
        faceValue: 1000000,
        couponRate: 5,
        accrualStart: '2025-01-01',
        accrualEnd: '2025-04-01',
      })
      const { dataRows } = useG2Detail(createOptions([row]))
      expect(dataRows.value[0].accruedDays).toBe(90)
      const expected = (1000000 * 5 / 100 * 90) / 365
      expect(dataRows.value[0].accruedInterest).toBeCloseTo(expected, 5)
    })
  })

  describe('aging enum', () => {
    it('默认 3 年段 bands', () => {
      const { bands, agingPreset } = useG2Detail(createOptions())
      expect(agingPreset.value).toBe('THREE_YEAR')
      expect(bands.value).toHaveLength(PRESET_SEGMENTS.THREE_YEAR.length)
    })

    it('切换 5 年段并 remap', async () => {
      const row = createStoredRow({
        openingUnadjusted: 1000,
        agingPrior: { within1: 1000, y1to2: 0, y2to3: 0, over3: 0 },
        agingAudited: { within1: 500, y1to2: 0, y2to3: 0, over3: 0 },
      })
      const opts = createOptions([row])
      const detail = useG2Detail(opts)
      detail.setAgingPreset('FIVE_YEAR')
      await nextTick()
      expect(detail.agingPreset.value).toBe('FIVE_YEAR')
      expect(detail.bands.value).toHaveLength(6)
      expect(detail.dataRows.value[0].agingPrior.within1).toBe(1000)
      expect(detail.dataRows.value[0].agingPrior.y3to4).toBe(0)
    })

    it('自定义账龄至少 2 段，并可切换段名', async () => {
      const opts = createOptions([createStoredRow({ openingUnadjusted: 1000 })])
      const detail = useG2Detail(opts)
      expect(detail.setAgingPreset('CUSTOM', ['仅一段'])).toBe(false)
      expect(detail.setAgingPreset('CUSTOM', ['0-6个月', '6-12个月', '1年以上'])).toBe(true)
      await nextTick()
      expect(detail.agingPreset.value).toBe('CUSTOM')
      expect(detail.bands.value).toHaveLength(3)
      expect(detail.bands.value.map((b) => b.label)).toEqual(['0-6个月', '6-12个月', '1年以上'])
      expect(detail.customSegments.value[0].key).toBe('custom-0')
    })

    it('快捷分配将期末审定整笔填入指定段', () => {
      const row = createStoredRow({
        openingUnadjusted: 10000,
        debit: 5000,
        credit: 2000,
        closingAdjustment: 0,
      })
      const opts = createOptions([row])
      const detail = useG2Detail(opts)
      const id = detail.dataRows.value[0].id
      const audited = detail.dataRows.value[0].closingAudited
      detail.allocateAging(id, 'audited', 'within1')
      expect(detail.dataRows.value[0].agingAudited.within1).toBeCloseTo(audited, 5)
      expect(detail.isAgingBalanced(detail.dataRows.value[0], 'audited')).toBe(true)
    })
  })
})
