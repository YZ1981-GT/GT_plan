/**
 * G8-5 指定适当性检查 — 矩阵逻辑与 G8-2 同步契约测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  buildDesignationConclusionDraft,
  designationBasisLabel,
  emptyDesignationRow,
  hasFvtociBasis,
  hasTradingCharacteristic,
  isDesignationRowComplete,
  useG8DesignationCheck,
} from '../useG8DesignationCheck'
import type { ChecklistResponse } from '../useF1FormData'

const apiPost = vi.fn()

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    post: (...args: unknown[]) => apiPost(...args),
  },
}))

beforeEach(() => {
  apiPost.mockReset()
})

describe('buildDesignationConclusionDraft', () => {
  it('全部适当 → A 口径', () => {
    const text = buildDesignationConclusionDraft({
      listed: 3,
      appropriate: 3,
      tradingRisk: 0,
      incomplete: 0,
    })
    expect(text.startsWith('A、')).toBe(true)
    expect(text).toContain('3 项')
  })

  it('存在交易性 → B 口径', () => {
    const text = buildDesignationConclusionDraft({
      listed: 2,
      appropriate: 1,
      tradingRisk: 1,
      incomplete: 0,
      tradingNames: ['甲公司'],
    })
    expect(text.startsWith('B、')).toBe(true)
    expect(text).toContain('甲公司')
  })

  it('未完成勾选 → C 口径', () => {
    const text = buildDesignationConclusionDraft({
      listed: 2,
      appropriate: 0,
      tradingRisk: 0,
      incomplete: 2,
    })
    expect(text.startsWith('C、')).toBe(true)
  })
})

describe('G8-5 designation matrix logic', () => {
  it('交易性任一情形即不宜指定 FVOCI', () => {
    const row = emptyDesignationRow('1', 1)
    row.investeeName = '甲公司'
    row.tradingNearTermSale = 'no'
    row.tradingPortfolioShortTerm = 'no'
    row.tradingDerivative = 'no'
    row.equityInstrument = 'yes'
    row.designatedFvtoci = 'yes'
    row.fvReliable = 'yes'
    expect(hasFvtociBasis(row)).toBe(true)
    row.tradingNearTermSale = 'yes'
    expect(hasTradingCharacteristic(row)).toBe(true)
    expect(hasFvtociBasis(row)).toBe(false)
    expect(designationBasisLabel(row)).toContain('不宜指定')
  })

  it('非交易性且三项权益条件满足则适当', () => {
    const row = emptyDesignationRow('2', 2)
    row.investeeName = '乙公司'
    row.tradingNearTermSale = 'no'
    row.tradingPortfolioShortTerm = 'no'
    row.tradingDerivative = 'no'
    row.equityInstrument = 'yes'
    row.designatedFvtoci = 'yes'
    row.fvReliable = 'yes'
    expect(hasFvtociBasis(row)).toBe(true)
    expect(designationBasisLabel(row)).toContain('适当')
  })

  it('矩阵行完成度校验', () => {
    const row = emptyDesignationRow('3', 3)
    row.investeeName = '丙公司'
    expect(isDesignationRowComplete(row)).toBe(false)
    row.tradingNearTermSale = 'no'
    row.tradingPortfolioShortTerm = 'no'
    row.tradingDerivative = 'no'
    row.equityInstrument = 'yes'
    row.designatedFvtoci = 'yes'
    row.fvReliable = 'yes'
    expect(isDesignationRowComplete(row)).toBe(true)
  })
})

describe('syncFromDetail', () => {
  it('从 G8-2 明细同步被投资单位与账面价值', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G8-detail-rows', {
        item_id: 'G8-detail-rows',
        remark: JSON.stringify([
          {
            rowId: 'd1',
            investeeName: '战略投资A',
            closingAdjusted: 500000,
            designationReason: '长期持有',
            fairValueLevel: 'Level2',
          },
        ]),
        conclusion: null,
      } as ChecklistResponse],
    ]))

    const dc = useG8DesignationCheck({
      wpId: ref('wp-1'),
      allResponses,
      debouncedSave: (id, data) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: data.conclusion ?? null,
          remark: data.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })

    const n = dc.syncFromDetail()
    expect(n).toBe(1)
    expect(dc.rows.value[0].investeeName).toBe('战略投资A')
    expect(dc.rows.value[0].closingBookValue).toBe(500000)
    expect(dc.rows.value[0].designationReason).toBe('长期持有')
    expect(dc.rows.value[0].equityInstrument).toBe('yes')
    expect(dc.rows.value[0].indexRef).toBe('G8-2')
  })

  it('旧版问卷数据迁移为空矩阵行', () => {
    const legacy = [{
      rowId: 'old',
      seq: 1,
      sectionNo: '(一)',
      sectionTitle: '测试',
      checkItem: '测试项',
      auditRequirement: 'req',
      evidenceOrReply: '',
      compliance: '',
      auditConclusion: '',
      indexRef: '',
    }]
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G8-designation-rows', {
        item_id: 'G8-designation-rows',
        remark: JSON.stringify(legacy),
        conclusion: null,
      } as ChecklistResponse],
    ]))

    const dc = useG8DesignationCheck({
      wpId: ref('wp-1'),
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })

    expect(dc.rows.value[0].investeeName).toBe('')
    expect(dc.rows.value[0].checkItem).toBeUndefined()
  })
})

describe('applyFromFairValue', () => {
  it('按被投资单位名称从 G8-4 带入 FV 可靠计量', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G8-designation-rows', {
        item_id: 'G8-designation-rows',
        remark: JSON.stringify([
          {
            ...emptyDesignationRow('r1', 1),
            investeeName: '战略投资A',
            closingBookValue: 100,
            indexRef: 'G8-2',
          },
        ]),
        conclusion: null,
      } as ChecklistResponse],
      ['G8-fv-test-rows', {
        item_id: 'G8-fv-test-rows',
        remark: JSON.stringify([
          {
            investeeName: '战略投资A',
            fairValueLevel: 'Level2',
            closingAuditedFV: 100,
            valuationDocIndex: 'G8-4-1',
          },
        ]),
        conclusion: null,
      } as ChecklistResponse],
    ]))

    const dc = useG8DesignationCheck({
      wpId: ref('wp-1'),
      allResponses,
      debouncedSave: (id, data) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: data.conclusion ?? null,
          remark: data.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })

    const n = dc.applyFromFairValue()
    expect(n).toBe(1)
    expect(dc.rows.value[0].fvReliable).toBe('yes')
    expect(dc.rows.value[0].indexRef).toContain('G8-4')
  })
})

describe('fillDefaultChecks + detailReconcile', () => {
  it('一键默认勾选仅填空白且不覆盖已有', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G8-designation-rows', {
        item_id: 'G8-designation-rows',
        remark: JSON.stringify([
          {
            ...emptyDesignationRow('r1', 1),
            investeeName: '甲',
            closingBookValue: 10,
            tradingNearTermSale: 'yes',
          },
        ]),
        conclusion: null,
      } as ChecklistResponse],
    ]))

    const dc = useG8DesignationCheck({
      wpId: ref('wp-1'),
      allResponses,
      debouncedSave: (id, data) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: data.conclusion ?? null,
          remark: data.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })

    expect(dc.fillDefaultChecks()).toBe(1)
    expect(dc.rows.value[0].tradingNearTermSale).toBe('yes')
    expect(dc.rows.value[0].tradingPortfolioShortTerm).toBe('no')
    expect(dc.rows.value[0].equityInstrument).toBe('yes')
    expect(dc.rows.value[0].designatedFvtoci).toBe('yes')
    expect(dc.rows.value[0].fvReliable).toBe('')
  })

  it('与 G8-2 名称与合计勾稽', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G8-designation-rows', {
        item_id: 'G8-designation-rows',
        remark: JSON.stringify([
          { ...emptyDesignationRow('r1', 1), investeeName: '甲', closingBookValue: 100 },
          { ...emptyDesignationRow('r2', 2), investeeName: '丙', closingBookValue: 50 },
        ]),
        conclusion: null,
      } as ChecklistResponse],
      ['G8-detail-rows', {
        item_id: 'G8-detail-rows',
        remark: JSON.stringify([
          { rowId: 'd1', investeeName: '甲', closingAdjusted: 100 },
          { rowId: 'd2', investeeName: '乙', closingAdjusted: 80 },
        ]),
        conclusion: null,
      } as ChecklistResponse],
    ]))

    const dc = useG8DesignationCheck({
      wpId: ref('wp-1'),
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })

    const r = dc.detailReconcile.value
    expect(r.hasDetail).toBe(true)
    expect(r.missingInDesignation).toContain('乙')
    expect(r.missingInDetail).toContain('丙')
    expect(r.bookDiff).toBe(-30)
  })
})

describe('applyConclusionDraft + levelReconcile', () => {
  it('结论草稿写入 A 口径且不覆盖已有结论', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G8-designation-rows', {
        item_id: 'G8-designation-rows',
        remark: JSON.stringify([
          {
            ...emptyDesignationRow('r1', 1),
            investeeName: '甲',
            closingBookValue: 10,
            tradingNearTermSale: 'no',
            tradingPortfolioShortTerm: 'no',
            tradingDerivative: 'no',
            equityInstrument: 'yes',
            designatedFvtoci: 'yes',
            fvReliable: 'yes',
          },
        ]),
        conclusion: null,
      } as ChecklistResponse],
    ]))

    const dc = useG8DesignationCheck({
      wpId: ref('wp-1'),
      allResponses,
      debouncedSave: (id, data) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: data.conclusion ?? null,
          remark: data.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })

    const draft = dc.applyConclusionDraft()
    expect(draft.startsWith('A、')).toBe(true)
    expect(dc.overallConclusion.value.startsWith('A、')).toBe(true)
    expect(dc.applyConclusionDraft(false)).toBe('')
  })

  it('Level3 勾稽：本表有 G8-4 无 也会触发 hasLevelMismatch', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G8-designation-rows', {
        item_id: 'G8-designation-rows',
        remark: JSON.stringify([
          {
            ...emptyDesignationRow('r1', 1),
            investeeName: '甲',
            closingBookValue: 10,
            fvReliable: 'yes',
            fairValueLevel: '',
          },
        ]),
        conclusion: null,
      } as ChecklistResponse],
      ['G8-fv-test-rows', {
        item_id: 'G8-fv-test-rows',
        remark: JSON.stringify([
          { investeeName: '乙', fairValueLevel: 'Level2' },
        ]),
        conclusion: null,
      } as ChecklistResponse],
    ]))

    const dc = useG8DesignationCheck({
      wpId: ref('wp-1'),
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })

    expect(dc.levelReconcile.value.missingInFv).toContain('甲')
    expect(dc.levelReconcile.value.missingInDesignation).toContain('乙')
    expect(dc.hasLevelMismatch.value).toBe(true)
  })

  it('refreshLinkage 清除 fvStale', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G8-designation-rows', {
        item_id: 'G8-designation-rows',
        remark: JSON.stringify([
          { ...emptyDesignationRow('r1', 1), investeeName: '甲', closingBookValue: 1 },
        ]),
        conclusion: null,
      } as ChecklistResponse],
      ['G8-detail-rows', {
        item_id: 'G8-detail-rows',
        remark: JSON.stringify([
          { rowId: 'd1', investeeName: '甲', closingAdjusted: 1, fairValueLevel: 'Level2' },
        ]),
        conclusion: null,
      } as ChecklistResponse],
      ['G8-fv-test-rows', {
        item_id: 'G8-fv-test-rows',
        remark: JSON.stringify([
          { investeeName: '甲', fairValueLevel: 'Level2', closingAuditedFV: 1 },
        ]),
        conclusion: null,
      } as ChecklistResponse],
    ]))
    const dc = useG8DesignationCheck({
      wpId: ref('wp-1'),
      allResponses,
      debouncedSave: (id, data) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: data.conclusion ?? null,
          remark: data.remark ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })
    dc.fvStale.value = true
    dc.refreshLinkage()
    expect(dc.fvStale.value).toBe(false)
  })
})

describe('validateDesignationRemote', () => {
  it('网络失败返回 ok=false', async () => {
    apiPost.mockRejectedValue(new Error('network'))
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const dc = useG8DesignationCheck({
      wpId: ref('wp-1'),
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })
    const res = await dc.validateDesignationRemote()
    expect(res.ok).toBe(false)
    expect(res.errors[0]?.field).toBe('network')
  })

  it('服务端返回错误时 ok=false', async () => {
    apiPost.mockResolvedValue({
      data: { ok: false, errors: [{ field: 'tradingNearTermSale', message: '未勾选：近期出售或回购' }] },
    })
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G8-designation-rows', {
        item_id: 'G8-designation-rows',
        remark: JSON.stringify([
          { ...emptyDesignationRow('r1', 1), investeeName: '甲', closingBookValue: 1 },
        ]),
        conclusion: null,
      } as ChecklistResponse],
    ]))
    const dc = useG8DesignationCheck({
      wpId: ref('wp-1'),
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })
    const res = await dc.validateDesignationRemote()
    expect(res.ok).toBe(false)
    expect(res.errors[0]?.message).toContain('未勾选')
  })
})
