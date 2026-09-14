/**
 * useG3OverdueCheck — G3-5 长期未收回款项检查表
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import {
  useG3OverdueCheck,
  migrateLegacyOverdueRow,
  getOverdueRiskClass,
} from '../useG3OverdueCheck'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'
import { computeG3AgingSummary } from '../g3AdjudicationItems'

vi.mock('element-plus', () => ({
  ElMessageBox: {
    prompt: vi.fn(),
  },
}))

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
    map.set('G3-5-overdue-rows', {
      item_id: 'G3-5-overdue-rows',
      conclusion: seed,
      remark: null,
    })
  }
  const allResponses = ref(map)
  const saved: Array<{ id: string; data: any }> = []
  const overdue = useG3OverdueCheck({
    allResponses,
    debouncedSave: (id, data) => {
      saved.push({ id, data })
      const prev = map.get(id) || { item_id: id }
      map.set(id, { ...prev, ...data })
    },
    isReadonly: ref(false),
    projectId: ref('proj-1'),
    asOf: ref(new Date('2020-12-31')),
  })
  return { overdue, allResponses, saved }
}

describe('useG3OverdueCheck', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2020-12-31'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('期末余额 = 期初 + 借方 − 贷方', () => {
    const rows = JSON.stringify([
      {
        id: 'r1',
        seq: 1,
        investeeName: '甲公司',
        openingBalance: 1000,
        periodDebit: 200,
        periodCredit: 50,
        aging: '1-2年',
        agreedPaymentDate: '2019-01-01',
        auditedBalance: 1150,
      },
    ])
    const { overdue } = setup(rows)
    expect(overdue.dataRows.value[0].closingBalance).toBe(1150)
    expect(overdue.dataRows.value[0].receivableAmount).toBe(1150)
  })

  it('逾期天数按约定付款日计算', () => {
    const rows = JSON.stringify([
      {
        id: 'r1',
        seq: 1,
        investeeName: '甲',
        openingBalance: 400,
        periodDebit: 0,
        periodCredit: 0,
        agreedPaymentDate: '2019-06-01',
        auditedBalance: 400,
      },
    ])
    const { overdue } = setup(rows)
    expect(overdue.dataRows.value[0].overdueDays).toBeGreaterThanOrEqual(365)
  })

  it('合计行汇总金额列', () => {
    const rows = JSON.stringify([
      {
        id: 'r1',
        seq: 1,
        investeeName: 'A',
        openingBalance: 100,
        periodDebit: 10,
        periodCredit: 0,
        aging: '1年以内',
        auditedBalance: 110,
        postPeriodCollection: 20,
        agreedPaymentDate: '2020-11-01',
      },
      {
        id: 'r2',
        seq: 2,
        investeeName: 'B',
        openingBalance: 200,
        periodDebit: 0,
        periodCredit: 50,
        aging: '1-2年',
        auditedBalance: 150,
        isUncollectible: '是',
        agreedPaymentDate: '2019-01-01',
      },
    ])
    const { overdue } = setup(rows)
    expect(overdue.summary.value.openingBalance).toBe(300)
    expect(overdue.summary.value.closingBalance).toBe(260)
    expect(overdue.summary.value.auditedBalance).toBe(260)
    expect(overdue.summary.value.uncollectibleCount).toBe(1)
    const sub = overdue.displayRows.value.find((r) => r.id === '__subtotal__')!
    expect(sub.closingBalance).toBe(260)
  })

  it('旧版字段迁移到滚动态', () => {
    const legacy = migrateLegacyOverdueRow(
      {
        id: 'old',
        investeeName: '丙',
        receivableAmount: 500,
        overdueReason: '资金紧张',
        recoverability: 'irrecoverable',
        auditSuggestion: '建议计提减值',
        investeeOperatingStatus: '亏损',
        agreedPaymentDate: '2018-01-01',
      },
      1,
    )
    expect(legacy.openingBalance).toBe(500)
    expect(legacy.auditedBalance).toBe(500)
    expect(legacy.unrecoveredReason).toBe('资金紧张')
    expect(legacy.isUncollectible).toBe('是')
    expect(legacy.actionPlan).toBe('建议计提减值')
    expect(legacy.businessDesc).toContain('亏损')
  })

  it('账龄枚举 3/5/自定义', async () => {
    const { overdue } = setup()
    expect(overdue.agingOptions.value).toHaveLength(PRESET_SEGMENTS.THREE_YEAR.length)
    overdue.setAgingPreset('FIVE_YEAR')
    await nextTick()
    expect(overdue.agingPreset.value).toBe('FIVE_YEAR')
    expect(overdue.agingOptions.value).toHaveLength(PRESET_SEGMENTS.FIVE_YEAR.length)
  })

  it('高亮：无法收回红色 / 逾期>90橙色', () => {
    const red = getOverdueRiskClass({
      id: '1',
      overdueDays: 10,
      isUncollectible: '是',
      aging: '',
    } as any)
    expect(red).toBe('overdue-danger')
    const orange = getOverdueRiskClass({
      id: '2',
      overdueDays: 120,
      isUncollectible: '',
      aging: '1-2年',
    } as any)
    expect(orange).toBe('overdue-warning')
  })

  it('从 G3-2 导入逾期明细', () => {
    const { overdue, allResponses } = setup()
    allResponses.value.set('G3-2-detail-rows', {
      item_id: 'G3-2-detail-rows',
      conclusion: JSON.stringify([
        {
          investeeName: '丁公司',
          dividendReceivable: 1000,
          receivedAmount: 200,
          netReceivable: 800,
          overdueDays: 400,
          isOverdue: '是',
          declarationDate: '2019-03-01',
          recordDate: '2019-04-01',
          dividendPlan: '现金分红',
        },
        {
          investeeName: '已收清',
          netReceivable: 0,
          overdueDays: 500,
          isOverdue: '是',
        },
      ]),
      remark: null,
    })
    const r = overdue.importFromDetail()
    expect(r.imported).toBe(1)
    expect(overdue.dataRows.value.some((x) => x.investeeName === '丁公司')).toBe(true)
    const row = overdue.dataRows.value.find((x) => x.investeeName === '丁公司')!
    expect(row.closingBalance).toBe(800)
    expect(row.agreedPaymentDate).toBe('2019-04-01')
  })

  it('G3-1 账龄汇总可读滚动态期末金额', () => {
    const overdue = JSON.stringify([
      {
        investeeName: '甲',
        openingBalance: 400,
        periodDebit: 0,
        periodCredit: 0,
        agreedPaymentDate: '2019-06-01',
      },
      {
        investeeName: '乙',
        openingBalance: 100,
        periodDebit: 0,
        periodCredit: 0,
        agreedPaymentDate: '2020-11-01',
      },
    ])
    const summary = computeG3AgingSummary(1000, overdue, new Date('2020-12-31'))
    expect(summary.over1YearAmount).toBe(400)
    expect(summary.within1YearAmount).toBe(600)
  })
})
