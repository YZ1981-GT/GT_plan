/**
 * useG2OverdueCheck — G2-6 长期未收回款项检查表
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useG2OverdueCheck } from '../useG2OverdueCheck'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return { ...actual as any, onBeforeUnmount: vi.fn() }
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

function setup(seed?: string) {
  const map = new Map<string, any>()
  if (seed) {
    map.set('G2-6-overdue-rows', { item_id: 'G2-6-overdue-rows', conclusion: null, remark: seed })
  }
  const allResponses = ref(map)
  const overdue = useG2OverdueCheck({
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    allResponses,
    isReadonly: ref(false),
  })
  return { overdue, allResponses }
}

describe('useG2OverdueCheck — 模板滚动态', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('期末余额 = 期初 + 借方 − 贷方', () => {
    const rows = JSON.stringify([
      {
        id: 'r1',
        seq: 1,
        debtorName: '甲公司',
        openingBalance: 1000,
        periodDebit: 200,
        periodCredit: 50,
        aging: '1-2年',
        businessDesc: '',
        unrecoveredReason: '',
        isUncollectible: '',
        actionPlan: '',
        auditedBalance: 1150,
        postPeriodCollection: 0,
        remark: '',
      },
    ])
    const { overdue } = setup(rows)
    expect(overdue.dataRows.value[0].closingBalance).toBe(1150)
  })

  it('合计行汇总金额列', () => {
    const rows = JSON.stringify([
      {
        id: 'r1', seq: 1, debtorName: 'A',
        openingBalance: 100, periodDebit: 10, periodCredit: 0,
        aging: '1年以内', auditedBalance: 110, postPeriodCollection: 20,
        businessDesc: '', unrecoveredReason: '', isUncollectible: '', actionPlan: '', remark: '',
      },
      {
        id: 'r2', seq: 2, debtorName: 'B',
        openingBalance: 200, periodDebit: 0, periodCredit: 50,
        aging: '1-2年', auditedBalance: 150, postPeriodCollection: 0,
        businessDesc: '', unrecoveredReason: '', isUncollectible: '是', actionPlan: '', remark: '',
      },
    ])
    const { overdue } = setup(rows)
    expect(overdue.summary.value.openingBalance).toBe(300)
    expect(overdue.summary.value.closingBalance).toBe(260)
    expect(overdue.summary.value.auditedBalance).toBe(260)
    expect(overdue.summary.value.longTermCount).toBe(1)
    expect(overdue.summary.value.uncollectibleCount).toBe(1)
    const sub = overdue.displayRows.value.find((r) => r.id === '__subtotal__')!
    expect(sub.closingBalance).toBe(260)
  })

  it('账龄枚举 3/5/自定义', async () => {
    const { overdue } = setup()
    expect(overdue.agingOptions.value).toHaveLength(PRESET_SEGMENTS.THREE_YEAR.length)
    overdue.setAgingPreset('FIVE_YEAR')
    await nextTick()
    expect(overdue.agingPreset.value).toBe('FIVE_YEAR')
    expect(overdue.agingOptions.value).toHaveLength(6)
    expect(overdue.setAgingPreset('CUSTOM', ['短', '中', '长'])).toBe(true)
    await nextTick()
    expect(overdue.agingPreset.value).toBe('CUSTOM')
    expect(overdue.agingOptions.value).toEqual(['短', '中', '长'])
  })

  it('同步审定余额=期末', () => {
    const rows = JSON.stringify([
      {
        id: 'r1', seq: 1, debtorName: 'A',
        openingBalance: 80, periodDebit: 20, periodCredit: 5,
        aging: '', auditedBalance: 0, postPeriodCollection: 0,
        businessDesc: '', unrecoveredReason: '', isUncollectible: '', actionPlan: '', remark: '',
      },
    ])
    const { overdue } = setup(rows)
    overdue.syncAuditedFromClosing('r1')
    expect(overdue.dataRows.value[0].auditedBalance).toBe(95)
  })

  it('兼容旧版逾期检查行', () => {
    const legacy = JSON.stringify([
      {
        id: 'old',
        seq: 1,
        investTarget: '旧标的',
        receivableAmount: 500,
        overdueReason: '逾期未收',
        recoverability: 'irrecoverable',
        auditSuggestion: '全额计提',
        remark: '',
      },
    ])
    const { overdue } = setup(legacy)
    const row = overdue.dataRows.value[0]
    expect(row.debtorName).toBe('旧标的')
    expect(row.openingBalance).toBe(500)
    expect(row.closingBalance).toBe(500)
    expect(row.isUncollectible).toBe('是')
    expect(row.unrecoveredReason).toBe('逾期未收')
  })

  it('从 G2-2 导入超1年挂账并按债务人合并', () => {
    const detail = JSON.stringify([
      {
        id: 'd1',
        investTarget: '甲公司',
        agingAudited: { within1: 10, y1to2: 200 },
        agingPrior: { y1to2: 180 },
        remark: '长期挂账',
      },
      {
        id: 'd2',
        investTarget: '乙公司',
        agingAudited: { within1: 100 },
        agingPrior: {},
      },
    ])
    const existing = JSON.stringify([
      {
        id: 'r1', seq: 1, debtorName: '甲公司',
        openingBalance: 1, periodDebit: 0, periodCredit: 0,
        aging: '1-2年', auditedBalance: 1, postPeriodCollection: 0,
        businessDesc: '', unrecoveredReason: '手工原因', isUncollectible: '', actionPlan: '', remark: '',
      },
    ])
    const map = new Map<string, any>()
    map.set('G2-6-overdue-rows', { item_id: 'G2-6-overdue-rows', conclusion: null, remark: existing })
    map.set('G2-2-detail-rows', { item_id: 'G2-2-detail-rows', conclusion: null, remark: detail })
    const allResponses = ref(map)
    const overdue = useG2OverdueCheck({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      isReadonly: ref(false),
    })
    const r = overdue.importFromDetail()
    expect(r.updated).toBe(1)
    expect(r.imported).toBe(0)
    const row = overdue.dataRows.value.find((x) => x.debtorName === '甲公司')!
    expect(row.auditedBalance).toBe(200)
    expect(row.unrecoveredReason).toBe('手工原因')
    expect(row.overdueDays).toBeGreaterThan(90)
    expect(overdue.getStageSuggestion(row)).toBe('Stage2')
  })
})
