/**
 * useG10FairValueTest — G10-5 公允价值测试单元测试
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  validateG10Level3Row,
  useG10FairValueTest,
  type G10FairValueRow,
} from '../useG10FairValueTest'
import {
  calcG10FairValueDiff,
  calcG10FvDiffWarning,
  G10_FV_DIFF_THRESHOLD,
  hasG10FairValueDifference,
  selectG10FvDiffTargets,
} from '../g10FvCrossHelpers'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: {
    prompt: vi.fn(),
    confirm: vi.fn().mockResolvedValue(true),
  },
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

function baseRow(patch: Partial<G10FairValueRow> = {}): G10FairValueRow {
  return {
    rowId: 'r1',
    seq: 1,
    liabilityName: '衍生负债A',
    initialDate: '2024-01-01',
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
    sensitivityAnalysis: '',
    valuationDocIndex: '',
    ...patch,
  }
}

describe('G10-5 校验与差异', () => {
  it('Level3 必填估值技术与不可观察输入值', () => {
    const row = baseRow({ fairValueLevel: 'Level3' })
    expect(validateG10Level3Row(row)).toEqual(
      expect.arrayContaining(['估值技术', '不可观察输入值描述']),
    )
  })

  it('calcG10FairValueDiff 与 hasG10FairValueDifference', () => {
    expect(calcG10FairValueDiff(1200, 1000)).toBe(200)
    expect(hasG10FairValueDifference({
      ...baseRow(),
      closingUnadjustedFV: 1000,
      closingAuditedFV: 1200,
      fairValueDiff: 200,
    })).toBe(true)
    expect(G10_FV_DIFF_THRESHOLD).toBe(0.01)
  })

  it('calcG10FvDiffWarning 负债差异分级', () => {
    expect(calcG10FvDiffWarning(0, 1000)).toBe('none')
    expect(calcG10FvDiffWarning(60, 1000)).toBe('soft')
    expect(calcG10FvDiffWarning(250, 1000)).toBe('hard')
  })

  it('selectG10FvDiffTargets 按 B15 筛选', () => {
    const { targets, skipped } = selectG10FvDiffTargets({
      rows: [
        { liabilityName: '超B15', fairValueDiff: 200, closingAuditedFV: 1200, closingUnadjustedFV: 1000 },
        { liabilityName: '未超', fairValueDiff: 30, closingAuditedFV: 1030, closingUnadjustedFV: 1000 },
      ],
      performanceMateriality: 100,
      onlyMaterial: true,
    })
    expect(targets.map((t) => t.liabilityName)).toEqual(['超B15'])
    expect(skipped).toHaveLength(1)
  })
})

describe('useG10FairValueTest 持久化', () => {
  it('加载并计算行差异', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G10-fv-test-rows', {
        item_id: 'G10-fv-test-rows',
        conclusion: null,
        remark: JSON.stringify([baseRow()]),
      } as ChecklistResponse],
    ]))
    const fv = useG10FairValueTest({
      wpId: ref('wp1'),
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    expect(fv.rows.value).toHaveLength(1)
    expect(fv.rows.value[0].fairValueDiff).toBe(200)
    expect(fv.diffCount.value).toBe(1)
    expect(fv.level3Count.value).toBe(0)
  })

  it('Level3 行计入 level3Count 与校验告警', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>([
      ['G10-fv-test-rows', {
        item_id: 'G10-fv-test-rows',
        conclusion: null,
        remark: JSON.stringify([baseRow({ fairValueLevel: 'Level3' })]),
      } as ChecklistResponse],
    ]))
    const fv = useG10FairValueTest({
      allResponses,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    expect(fv.level3Count.value).toBe(1)
    expect(fv.level3Violations.value).toHaveLength(1)
  })
})
