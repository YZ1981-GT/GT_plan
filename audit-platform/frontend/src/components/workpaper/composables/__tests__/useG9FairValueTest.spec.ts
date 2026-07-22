/**
 * useG9FairValueTest — G9-4 公允价值测试单元测试
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  enrichG9FairValueRow,
  validateG9Level3,
  validateG9FairValueRow,
  hasG9FairValueDifference,
  G9_FV_DIFF_THRESHOLD,
  useG9FairValueTest,
  type G9FairValueRow,
} from '../useG9FairValueTest'
import {
  calcFairValueAmount,
  calcFairValueDiff,
  calcFairValueQtyImpact,
  calcFairValuePriceImpact,
} from '../useG9FormulaEngine'
import {
  calcG9FvDiffWarning,
  pushG9FvToDetail,
  selectG9FvDiffTargets,
  buildG9FvProcedureSummary,
  pushG9FvDiffToAdjustment,
} from '../g9FvCrossHelpers'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: {
    prompt: vi.fn(),
    confirm: vi.fn().mockResolvedValue(true),
  },
}))

function baseRow(patch: Partial<G9FairValueRow> = {}): G9FairValueRow {
  return {
    rowId: 'r1',
    seq: 1,
    assetName: '理财产品A',
    initialInvestDate: '2024-01-01',
    closingUnadjustedQty: 100,
    closingUnadjustedPrice: 10,
    closingUnadjustedFV: 0,
    closingAuditedQty: 100,
    closingAuditedPrice: 12,
    closingAuditedFV: 0,
    fairValueLevel: 'Level2',
    valuationMethod: '市场法',
    methodConsistentWithPrior: 'yes',
    valuationSource: '评估机构A',
    inputSourceAndAdjustment: '',
    valuationTechnique: '',
    unobservableInputDesc: '',
    unobservableInputValue: '',
    nonLiquidityDiscount: 0,
    valuationDocIndex: '',
    diffReason: '',
    ...patch,
  }
}

describe('G9-4 公式引擎', () => {
  it('calcFairValueAmount = 数量 × 单价', () => {
    expect(calcFairValueAmount(10, 100.5)).toBe(1005)
    expect(calcFairValueAmount(0, 100)).toBe(0)
  })

  it('差异分解：数量影响 + 价格影响 = 总差异', () => {
    const unadjQty = 100
    const unadjPrice = 10
    const auditedQty = 120
    const auditedPrice = 11
    const unadjFv = calcFairValueAmount(unadjQty, unadjPrice)
    const auditedFv = calcFairValueAmount(auditedQty, auditedPrice)
    const diff = calcFairValueDiff(auditedFv, unadjFv)
    const qtyImpact = calcFairValueQtyImpact(auditedQty, unadjQty, unadjPrice)
    const priceImpact = calcFairValuePriceImpact(auditedQty, auditedPrice, unadjPrice)
    expect(qtyImpact + priceImpact).toBeCloseTo(diff, 2)
  })
})

describe('enrichG9FairValueRow', () => {
  it('自动计算 FV 与差异', () => {
    const row = enrichG9FairValueRow(baseRow())
    expect(row.closingUnadjustedFV).toBe(1000)
    expect(row.closingAuditedFV).toBe(1200)
    expect(row.fairValueDiff).toBe(200)
  })

  it('无数量单价时保留手工 FV', () => {
    const row = enrichG9FairValueRow(baseRow({
      closingUnadjustedQty: 0,
      closingUnadjustedPrice: 0,
      closingUnadjustedFV: 880,
      closingAuditedQty: 0,
      closingAuditedPrice: 0,
      closingAuditedFV: 900,
    }))
    expect(row.closingUnadjustedFV).toBe(880)
    expect(row.closingAuditedFV).toBe(900)
    expect(row.fairValueDiff).toBe(20)
  })
})

describe('校验', () => {
  it('Level3 必填估值技术与输入值', () => {
    const row = baseRow({ fairValueLevel: 'Level3' })
    expect(validateG9Level3(row)).toEqual(
      expect.arrayContaining(['估值技术', '不可观察输入值描述', '不可观察输入值', '估值文件索引']),
    )
  })

  it('Level2 缺来源机构报错', () => {
    const row = baseRow({ fairValueLevel: 'Level2', valuationSource: '' })
    expect(validateG9FairValueRow(row)).toContain('公允价值来源机构')
  })

  it('hasG9FairValueDifference', () => {
    expect(hasG9FairValueDifference(enrichG9FairValueRow(baseRow()))).toBe(true)
    expect(hasG9FairValueDifference(enrichG9FairValueRow(baseRow({
      closingAuditedPrice: 10,
    })))).toBe(false)
  })
})

describe('跨表联动', () => {
  it('calcG9FvDiffWarning', () => {
    expect(calcG9FvDiffWarning(0, 1000)).toBe('none')
    expect(calcG9FvDiffWarning(60, 1000)).toBe('soft')
    expect(calcG9FvDiffWarning(250, 1000)).toBe('hard')
    expect(calcG9FvDiffWarning(50, 1000, { hardAbs: 40 })).toBe('hard')
  })

  it('selectG9FvDiffTargets 按 B15 筛选', () => {
    const { targets, skipped } = selectG9FvDiffTargets({
      rows: [
        { assetName: '超B15', fairValueDiff: 200, closingAuditedFV: 1200, closingUnadjustedFV: 1000 },
        { assetName: '未超', fairValueDiff: 30, closingAuditedFV: 1030, closingUnadjustedFV: 1000 },
      ],
      performanceMateriality: 100,
      onlyMaterial: true,
    })
    expect(targets.map((t) => t.assetName)).toEqual(['超B15'])
    expect(skipped).toHaveLength(1)
  })

  it('pushG9FvToDetail 按资产名回写层次', () => {
    const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const map = new Map<string, ChecklistResponse>([
      ['G9-detail-rows', {
        item_id: 'G9-detail-rows',
        conclusion: null,
        remark: JSON.stringify([{ rowId: 'd1', assetName: '理财产品A', fairValueLevel: 'Level1' }]),
      } as ChecklistResponse],
    ])
    const n = pushG9FvToDetail(
      map,
      (id, d) => { saves.push({ id, data: d }) },
      [enrichG9FairValueRow(baseRow({ fairValueLevel: 'Level3' }))],
    )
    expect(n).toBe(1)
    const saved = JSON.parse(String(saves[0].data.remark))
    expect(saved[0].fairValueLevel).toBe('Level3')
  })

  it('pushG9FvDiffToAdjustment 写入借贷分录', () => {
    const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const map = new Map<string, ChecklistResponse>()
    const n = pushG9FvDiffToAdjustment(
      map,
      (id, d) => {
        saves.push({ id, data: d })
        map.set(id, { item_id: id, conclusion: null, remark: d.remark ?? null } as ChecklistResponse)
      },
      [{ summary: '测试差异', amount: 200 }],
    )
    expect(n).toBe(1)
    const adj = JSON.parse(String(saves.find((s) => s.id === 'G9-adjustment-rows')?.data.remark))
    expect(adj).toHaveLength(2)
    expect(adj[0].accountCode).toBe('1519')
    expect(adj[0].debitAmount).toBe(200)
    expect(adj[1].accountCode).toBe('6101')
    expect(adj[1].creditAmount).toBe(200)
  })

  it('buildG9FvProcedureSummary', () => {
    const s = buildG9FvProcedureSummary({
      rowCount: 3,
      diffCount: 1,
      level3Count: 2,
      auditedTotal: 1000,
      validationErrors: 0,
    })
    expect(s).toContain('3 项')
    expect(s).toContain('Level3 2')
  })
})

describe('useG9FairValueTest 持久化', () => {
  it('加载并计算行', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G9-fv-test-rows', {
        item_id: 'G9-fv-test-rows',
        conclusion: null,
        remark: JSON.stringify([baseRow()]),
      } as ChecklistResponse],
    ]))
    const fv = useG9FairValueTest({
      wpId: ref('wp1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    expect(fv.rows.value).toHaveLength(1)
    expect(fv.rows.value[0].fairValueDiff).toBe(200)
    expect(fv.diffCount.value).toBe(1)
    expect(G9_FV_DIFF_THRESHOLD).toBe(0.01)
  })
})
