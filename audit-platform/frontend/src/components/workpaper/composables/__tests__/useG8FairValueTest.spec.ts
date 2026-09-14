/**
 * useG8FairValueTest — G8-4 公允价值测试单元测试
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  enrichG8FairValueRow,
  validateG8Level3,
  validateG8FairValueRow,
  hasG8FairValueDifference,
  G8_FV_DIFF_THRESHOLD,
  useG8FairValueTest,
  type G8FairValueRow,
} from '../useG8FairValueTest'
import {
  calcFairValueAmount,
  calcFairValueDiff,
  calcFairValueQtyImpact,
  calcFairValuePriceImpact,
} from '../useG8FormulaEngine'
import {
  calcG8FvDiffWarning,
  extractDesignationLevel,
  pushG8FvToDetail,
  pushG8FvToDesignation,
  reconcileG8FvWithDesignation,
  selectG8FvDiffTargets,
  buildG8FvProcedureSummary,
} from '../g8CrossHelpers'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: {
    prompt: vi.fn(),
    confirm: vi.fn().mockResolvedValue(true),
  },
}))

function baseRow(patch: Partial<G8FairValueRow> = {}): G8FairValueRow {
  return {
    rowId: 'r1',
    seq: 1,
    investeeName: '测试公司',
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
    valuationDocIndex: '',
    diffReason: '',
    ...patch,
  }
}

describe('G8-4 公式引擎', () => {
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

  it('enrichG8FairValueRow 自动重算公式列', () => {
    const row = enrichG8FairValueRow(baseRow())
    expect(row.closingUnadjustedFV).toBe(1000)
    expect(row.closingAuditedFV).toBe(1200)
    expect(row.fairValueDiff).toBe(200)
    expect(row.qtyImpact).toBe(0)
    expect(row.priceImpact).toBe(200)
  })
})

describe('G8-4 层次校验', () => {
  it('Level3 缺少必填项', () => {
    const row = baseRow({ fairValueLevel: 'Level3' })
    expect(validateG8Level3(row)).toEqual([
      '估值技术',
      '不可观察输入值描述',
      '不可观察输入值',
      '估值文件索引号',
    ])
  })

  it('Level3 填写完整通过', () => {
    const row = baseRow({
      fairValueLevel: 'Level3',
      valuationTechnique: '收益法',
      unobservableInputDesc: '折现率',
      unobservableInputValue: '10%',
      valuationDocIndex: 'G8-4-1',
    })
    expect(validateG8Level3(row)).toEqual([])
  })

  it('Level2 缺少来源机构', () => {
    const row = baseRow({ fairValueLevel: 'Level2', valuationSource: '' })
    expect(validateG8FairValueRow(row)).toContain('公允价值来源机构')
  })

  it('方法变更须说明', () => {
    const row = baseRow({ methodConsistentWithPrior: 'no', inputSourceAndAdjustment: '' })
    expect(validateG8FairValueRow(row)).toContain('方法变更说明（输入值来源及调整）')
  })
})

describe('G8-4 差异标识', () => {
  it('超过阈值判定为有差异', () => {
    const row = enrichG8FairValueRow(baseRow())
    expect(hasG8FairValueDifference(row)).toBe(true)
    expect(G8_FV_DIFF_THRESHOLD).toBe(0.01)
  })

  it('无差异', () => {
    const row = enrichG8FairValueRow(baseRow({
      closingAuditedQty: 100,
      closingAuditedPrice: 10,
    }))
    expect(hasG8FairValueDifference(row)).toBe(false)
  })
})

describe('G8 跨表勾稽辅助', () => {
  it('extractDesignationLevel 解析层次标注', () => {
    expect(extractDesignationLevel({ fairValueLevel: 'Level3' })).toBe('Level3')
    expect(extractDesignationLevel({ other: 'G8-4层次：Level2' })).toBe('Level2')
    expect(extractDesignationLevel({ other: 'G8-4层次: L1' })).toBe('Level1')
  })

  it('reconcileG8FvWithDesignation 检出层次不一致', () => {
    const r = reconcileG8FvWithDesignation(
      [{ investeeName: '甲公司', fairValueLevel: 'Level3' }],
      [{ investeeName: '甲公司', fairValueLevel: 'Level2', fvReliable: 'yes' }],
    )
    expect(r.mismatches).toHaveLength(1)
    expect(r.mismatches[0].issue).toContain('Level3')
  })

  it('calcG8FvDiffWarning 分级', () => {
    expect(calcG8FvDiffWarning(0, 1000)).toBe('none')
    expect(calcG8FvDiffWarning(60, 1000)).toBe('soft')
    expect(calcG8FvDiffWarning(250, 1000)).toBe('hard')
    expect(calcG8FvDiffWarning(80, 1000, { hardAbs: 50 })).toBe('hard')
  })

  it('selectG8FvDiffTargets 按 B15 筛选', () => {
    const { targets, skipped } = selectG8FvDiffTargets({
      rows: [
        { investeeName: '超B15', fairValueDiff: 200, closingAuditedFV: 1200, closingUnadjustedFV: 1000 },
        { investeeName: '未超', fairValueDiff: 30, closingAuditedFV: 1030, closingUnadjustedFV: 1000 },
      ],
      performanceMateriality: 100,
      onlyMaterial: true,
    })
    expect(targets).toHaveLength(1)
    expect(targets[0].investeeName).toBe('超B15')
    expect(skipped).toHaveLength(1)
  })

  it('buildG8FvProcedureSummary 含关键统计', () => {
    const s = buildG8FvProcedureSummary({
      rowCount: 3,
      diffCount: 1,
      level3Count: 1,
      auditedTotal: 5000,
      validationErrors: 0,
    })
    expect(s).toContain('3 项')
    expect(s).toContain('Level3 1')
  })

  it('pushG8FvToDetail 回写层次与审定FV', () => {
    const map = new Map<string, ChecklistResponse>([
      ['G8-detail-rows', {
        item_id: 'G8-detail-rows',
        remark: JSON.stringify([{ rowId: 'd1', investeeName: '测试公司', fairValueLevel: 'Level1' }]),
        conclusion: null,
      } as ChecklistResponse],
    ])
    const saves: Array<{ id: string; remark?: string | null }> = []
    const n = pushG8FvToDetail(
      map,
      (id, d) => {
        saves.push({ id, remark: d.remark })
        map.set(id, { item_id: id, remark: d.remark ?? null, conclusion: null } as ChecklistResponse)
      },
      [enrichG8FairValueRow(baseRow({ fairValueLevel: 'Level3', closingAuditedQty: 10, closingAuditedPrice: 5 }))],
    )
    expect(n).toBe(1)
    const saved = JSON.parse(saves[0].remark!)
    expect(saved[0].fairValueLevel).toBe('Level3')
    expect(saved[0].fairValueTotal).toBe(50)
  })

  it('pushG8FvToDesignation 同步层次到 G8-5', () => {
    const map = new Map<string, ChecklistResponse>([
      ['G8-designation-rows', {
        item_id: 'G8-designation-rows',
        remark: JSON.stringify([{ rowId: 'r1', investeeName: '测试公司', fairValueLevel: '', fvReliable: '' }]),
        conclusion: null,
      } as ChecklistResponse],
    ])
    const saves: Array<{ id: string; remark?: string | null }> = []
    const n = pushG8FvToDesignation(
      map,
      (id, d) => {
        saves.push({ id, remark: d.remark })
        map.set(id, { item_id: id, remark: d.remark ?? null, conclusion: null } as ChecklistResponse)
      },
      [{ investeeName: '测试公司', fairValueLevel: 'Level2' }],
    )
    expect(n).toBe(1)
    const saved = JSON.parse(saves[0].remark!)
    expect(saved[0].fairValueLevel).toBe('Level2')
    expect(saved[0].fvReliable).toBe('yes')
    expect(saved[0].indexRef).toContain('G8-4')
  })
})

describe('useG8FairValueTest 联动', () => {
  it('pushToDetail / levelReconcile 可用', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G8-fv-test-rows', {
        item_id: 'G8-fv-test-rows',
        remark: JSON.stringify([baseRow({ fairValueLevel: 'Level3' })]),
        conclusion: null,
      } as ChecklistResponse],
      ['G8-detail-rows', {
        item_id: 'G8-detail-rows',
        remark: JSON.stringify([{ rowId: 'd1', investeeName: '测试公司' }]),
        conclusion: null,
      } as ChecklistResponse],
      ['G8-designation-rows', {
        item_id: 'G8-designation-rows',
        remark: JSON.stringify([{ investeeName: '测试公司', fairValueLevel: 'Level2' }]),
        conclusion: null,
      } as ChecklistResponse],
    ]))
    const fv = useG8FairValueTest({
      wpId: ref('wp'),
      allResponses,
      debouncedSave: (id, d) => {
        allResponses.value.set(id, {
          item_id: id,
          remark: d.remark ?? allResponses.value.get(id)?.remark ?? null,
          conclusion: d.conclusion ?? null,
        } as ChecklistResponse)
      },
      isReadonly: ref(false),
    })
    expect(fv.hasLevelMismatch.value).toBe(true)
    // 回写 G8-2 明细 + G8-5 指定表各 1
    expect(fv.pushToDetail()).toBe(2)
    // 差异 200 / 未审 1000 = 20% → hard
    expect(fv.diffWarningLevel.value).toBe('hard')
    expect(fv.diffRatioPct.value).toBe(20)
  })
})
