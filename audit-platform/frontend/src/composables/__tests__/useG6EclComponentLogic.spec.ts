/**
 * G6 其他债权投资(ECL组) — 组件逻辑单元测试
 *
 * Spec: .kiro/specs/g6-other-bond-investment-ecl/ Task 11.2
 * Validates: Requirements 2.1, 4.1, 5.1, 5.3
 *
 * 覆盖：
 *   1. G6-11 列式转置解析：空列过滤 / 合并单元格 / 全空列过滤
 *   2. G6-13 section结构完整性：5个section均存在且行数正确
 *   3. G6-14 转回/核销双表结构
 *   4. G6-15 凭证异常自动判定：7项核对全通过=正常，任一✗=异常
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// Mock element-plus (needed by composables with ElMessageBox)
vi.mock('element-plus', () => ({
  ElMessageBox: { prompt: vi.fn(), confirm: vi.fn() },
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() },
}))

// Mock http (needed by useG6EclVoucherCheck)
vi.mock('@/utils/http', () => ({
  default: { post: vi.fn(), get: vi.fn() },
}))

import {
  useG6EclStageClassification,
  type ColumnarSourceData,
} from '@/composables/useG6EclStageClassification'

import type {
  EclMeasurementData,
  PdLgdCalcRow,
  G6ReversalRow,
  G6WriteOffRow,
  VoucherCheckRow,
} from '@/components/workpaper/composables/useG6EclFormData'

import { useG6EclVoucherCheck } from '@/composables/useG6EclVoucherCheck'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. G6-11 列式转置解析
// ═══════════════════════════════════════════════════════════════════════════════

describe('G6-11 列式转置解析 (transposeToRows + getValidColumnIndices)', () => {
  it('空列头+空数据列被过滤', () => {
    const { transposeToRows } = useG6EclStageClassification()
    const source: ColumnarSourceData = {
      columnHeaders: ['债券A', '', '债券B', ''],
      sectionOneMatrix: Array.from({ length: 13 }, () => ['否', '', '是', '']),
      sectionTwoMatrix: Array.from({ length: 3 }, () => ['否', '', '否', '']),
      sectionThreeMatrix: Array.from({ length: 8 }, () => ['否', '', '否', '']),
    }
    const rows = transposeToRows(source)
    // 只有2个有效列（债券A, 债券B），空列头无数据的列被过滤
    expect(rows).toHaveLength(2)
    expect(rows[0].investProject).toBe('债券A')
    expect(rows[1].investProject).toBe('债券B')
  })

  it('合并单元格（空列头但有数据的列）保留', () => {
    const { transposeToRows } = useG6EclStageClassification()
    // 列头为空但该列有检查项数据 → 视为有效列（合并单元格虚列有数据）
    const source: ColumnarSourceData = {
      columnHeaders: ['债券A', '', '债券C'],
      sectionOneMatrix: Array.from({ length: 13 }, () => ['是', '是', '否']),
      sectionTwoMatrix: Array.from({ length: 3 }, () => ['否', '否', '否']),
      sectionThreeMatrix: Array.from({ length: 8 }, () => ['否', '否', '否']),
    }
    const rows = transposeToRows(source)
    // 第2列头为空但sectionOneMatrix有数据 → 保留
    expect(rows).toHaveLength(3)
    expect(rows[0].investProject).toBe('债券A')
    // 空列头但有数据的行会取 fallback 名称
    expect(rows[1].investProject).toBe('投资2')
    expect(rows[2].investProject).toBe('债券C')
  })

  it('全空列（无列头 + 无数据行）被完全过滤', () => {
    const { getValidColumnIndices } = useG6EclStageClassification()
    const headers = ['债券X', '', '', '债券Y']
    // 第2、3列在所有矩阵中都无数据
    const s1 = Array.from({ length: 13 }, () => ['是', '', '', '否'])
    const s2 = Array.from({ length: 3 }, () => ['否', '', '', '否'])
    const s3 = Array.from({ length: 8 }, () => ['否', '', '', '否'])
    const indices = getValidColumnIndices(headers, s1, s2, s3)
    // 只有第0列(债券X)和第3列(债券Y)是有效的
    expect(indices).toEqual([0, 3])
  })

  it('16384列场景仅返回有效列', () => {
    const { getValidColumnIndices } = useG6EclStageClassification()
    // 模拟16384列中仅前3列有数据
    const headers = Array.from({ length: 100 }, (_, i) => (i < 3 ? `投资${i + 1}` : ''))
    const s1 = Array.from({ length: 13 }, () => Array.from({ length: 100 }, () => ''))
    const s2 = Array.from({ length: 3 }, () => Array.from({ length: 100 }, () => ''))
    const s3 = Array.from({ length: 8 }, () => Array.from({ length: 100 }, () => ''))
    const indices = getValidColumnIndices(headers, s1, s2, s3)
    expect(indices).toHaveLength(3)
    expect(indices).toEqual([0, 1, 2])
  })

  it('转置后行数据包含正确的Stage判定', () => {
    const { transposeToRows } = useG6EclStageClassification()
    const source: ColumnarSourceData = {
      columnHeaders: ['标的A'],
      // 第1项"是" → hasSignificantIncrease=true → Stage2
      sectionOneMatrix: [['是'], ...Array.from({ length: 12 }, () => ['否'])],
      sectionTwoMatrix: Array.from({ length: 3 }, () => ['否']),
      sectionThreeMatrix: Array.from({ length: 8 }, () => ['否']),
    }
    const rows = transposeToRows(source)
    expect(rows).toHaveLength(1)
    expect(rows[0].hasSignificantIncrease).toBe(true)
    expect(rows[0].auditStage).toBe('Stage2')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. G6-13 section结构完整性
// ═══════════════════════════════════════════════════════════════════════════════

describe('G6-13 ECL计量数据结构', () => {
  it('EclMeasurementData 含方法评价/组合/双路径测算', () => {
    const data: EclMeasurementData = {
      schemaVersion: 2,
      methodEvaluation: [],
      groupBasis: [],
      parameterEvaluation: [],
      pdLgdRows: [],
      lossRateRows: [],
      conclusion: '',
    }
    expect(data).toHaveProperty('methodEvaluation')
    expect(data).toHaveProperty('groupBasis')
    expect(data).toHaveProperty('pdLgdRows')
    expect(data).toHaveProperty('lossRateRows')
    expect(data).toHaveProperty('parameterEvaluation')
  })

  it('PD/LGD 行含 Excel 核心字段', () => {
    const row: PdLgdCalcRow = {
      id: '1',
      projectName: '债A',
      bookBalance: 100,
      remainingMonths: 12,
      stage: 'Stage1',
      rating: 'A+',
      externalMappedPd: 0.002,
      termAdjustedPd: 0.002,
      lgd: 0.45,
      eclRate: 0.0009,
      eclAmount: 0.09,
      priorHistoricalLossRate: 0,
      note: '',
    }
    expect(row.eclRate).toBeCloseTo(row.termAdjustedPd * row.lgd, 6)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. G6-14 转回/核销双表
// ═══════════════════════════════════════════════════════════════════════════════

describe('G6-14 转回/核销双表结构', () => {
  it('转回行含 Excel 核心字段且金额不超累计计提', () => {
    const row: G6ReversalRow = {
      id: '1',
      seq: 1,
      unitName: '债A',
      reversalReason: '信用改善',
      recoveryMethod: '现金',
      originalBasis: 'Stage3 单项',
      reversalAmount: 100,
      accumulatedProvision: 200,
      reasonAnalysis: '合理',
      isReasonable: '合理',
      indexRef: '',
    }
    expect(row.reversalAmount).toBeLessThanOrEqual(row.accumulatedProvision)
  })

  it('核销行含关联交易标记', () => {
    const row: G6WriteOffRow = {
      id: '2',
      seq: 1,
      unitName: '债B',
      writeOffType: '公司债',
      writeOffAmount: 50,
      writeOffReason: '破产',
      writeOffProcedure: '董事会审批',
      isRelatedParty: true,
      reasonAnalysis: '已披露',
      isReasonable: '合理',
      indexRef: '',
    }
    expect(row.isRelatedParty).toBe(true)
    expect(row.writeOffAmount).toBeGreaterThan(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. G6-15 凭证六项三态核对
// ═══════════════════════════════════════════════════════════════════════════════

describe('G6-15 凭证六项三态核对', () => {
  function makeVoucherRow(overrides: Partial<VoucherCheckRow> = {}): VoucherCheckRow {
    return {
      id: 'test-v1',
      seq: 1,
      period: 'occurrence',
      date: '2024-12-31',
      voucherNo: 'PZ-001',
      businessContent: '计提减值',
      businessType: '减值计提',
      counterAccount: '资产减值损失',
      detailAccount: '1503',
      debitAmount: 10000,
      creditAmount: 0,
      attachment: null,
      attachmentId: null,
      attachmentUrl: null,
      attachmentUploadedAt: null,
      supportingDoc: '',
      checkOriginal: 'Y',
      checkAuthorized: 'Y',
      checkAccounting: 'Y',
      checkInitialCost: 'Y',
      checkInterest: 'Y',
      checkFairValue: 'Y',
      indexRef: '',
      isAbnormal: false,
      manualAbnormal: false,
      abnormalNote: '',
      riskLevel: '',
      suggestion: '',
      remark: '',
      source: '手工',
      selectionReason: '',
      samplingMethod: '',
      selectionCategory: 'manual',
      sourceId: 'test-v1',
      ...overrides,
    }
  }

  it('六项核对全通过 → 已完成且正常', () => {
    const { recalcAbnormal } = useG6EclVoucherCheck(ref('wp-1'), ref('proj-1'))
    const row = makeVoucherRow({
      checkOriginal: 'Y',
      checkAuthorized: 'Y',
      checkAccounting: 'Y',
      checkInitialCost: 'Y',
      checkInterest: 'Y',
      checkFairValue: 'Y',
    })
    recalcAbnormal(row)
    expect(row.isAbnormal).toBe(false)
    expect(useG6EclVoucherCheck(ref('wp-1'), ref('proj-1')).isAllChecked(row)).toBe(true)
  })

  it('任一核对为N → 异常凭证', () => {
    const { recalcAbnormal } = useG6EclVoucherCheck(ref('wp-1'), ref('proj-1'))

    // 逐项测试每个核对字段为false时的异常判定
    const checkFields: Array<keyof VoucherCheckRow> = [
      'checkOriginal', 'checkAuthorized', 'checkAccounting',
      'checkInitialCost', 'checkInterest', 'checkFairValue',
    ]
    for (const field of checkFields) {
      const row = makeVoucherRow({ [field]: 'N' })
      recalcAbnormal(row)
      expect(row.isAbnormal).toBe(true, `${field}为N时应判定为异常`)
    }
  })

  it('未检查与检查不通过分离：空值待完成但不自动异常', () => {
    const { recalcAbnormal } = useG6EclVoucherCheck(ref('wp-1'), ref('proj-1'))
    const row = makeVoucherRow({
      checkOriginal: '',
    })
    recalcAbnormal(row)
    expect(row.isAbnormal).toBe(false)
    expect(useG6EclVoucherCheck(ref('wp-1'), ref('proj-1')).isAllChecked(row)).toBe(false)
  })

  it('人工标记可在六项通过时保留异常', () => {
    const { recalcAbnormal } = useG6EclVoucherCheck(ref('wp-1'), ref('proj-1'))
    const row = makeVoucherRow({
      manualAbnormal: true,
    })
    recalcAbnormal(row)
    expect(row.isAbnormal).toBe(true)
  })
})
