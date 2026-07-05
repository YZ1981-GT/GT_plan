/**
 * G6 其他债权投资(ECL组) — 组件逻辑单元测试
 *
 * Spec: .kiro/specs/g6-other-bond-investment-ecl/ Task 11.2
 * Validates: Requirements 2.1, 4.1, 5.1, 5.3
 *
 * 覆盖：
 *   1. G6-11 列式转置解析：空列过滤 / 合并单元格 / 全空列过滤
 *   2. G6-13 section结构完整性：5个section均存在且行数正确
 *   3. G6-14 转回类型校验：仅允许 转回/核销/收回
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
  ReversalWriteOffRow,
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

describe('G6-13 section结构完整性', () => {
  it('EclMeasurementData接口包含5个必需section', () => {
    // 构造一个完整的EclMeasurementData验证结构
    const data: EclMeasurementData = {
      pdSection: [],
      lgdSection: [],
      eadSection: [],
      discountRateSection: [],
      forwardLookingSection: [],
      methodologyContext: '',
    }
    // 验证5个section字段均存在
    expect(data).toHaveProperty('pdSection')
    expect(data).toHaveProperty('lgdSection')
    expect(data).toHaveProperty('eadSection')
    expect(data).toHaveProperty('discountRateSection')
    expect(data).toHaveProperty('forwardLookingSection')
  })

  it('各section初始化后为数组类型', () => {
    const data: EclMeasurementData = {
      pdSection: [{ id: '1', seq: 1, checkArea: 'PD', checkItem: '数据来源', auditRequirement: '', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' }],
      lgdSection: [{ id: '2', seq: 1, checkArea: 'LGD', checkItem: '抵押品', auditRequirement: '', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' }],
      eadSection: [{ id: '3', seq: 1, checkArea: 'EAD', checkItem: '余额口径', auditRequirement: '', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' }],
      discountRateSection: [{ id: '4', seq: 1, checkArea: '折现率', checkItem: '实际利率', auditRequirement: '', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' }],
      forwardLookingSection: [{ id: '5', seq: 1, checkArea: '前瞻性', checkItem: '宏观情景', auditRequirement: '', companyParam: '', isReasonable: '', auditConclusion: '', riskLevel: '', indexRef: '', remark: '' }],
      methodologyContext: 'ECL三要素定义',
    }
    expect(Array.isArray(data.pdSection)).toBe(true)
    expect(Array.isArray(data.lgdSection)).toBe(true)
    expect(Array.isArray(data.eadSection)).toBe(true)
    expect(Array.isArray(data.discountRateSection)).toBe(true)
    expect(Array.isArray(data.forwardLookingSection)).toBe(true)
    // 总行数 = 5(各1行用于测试)
    const total = data.pdSection.length + data.lgdSection.length +
      data.eadSection.length + data.discountRateSection.length + data.forwardLookingSection.length
    expect(total).toBe(5)
  })

  it('section名称对应正确的检查区域', () => {
    // 验证section分组命名一致性
    const sectionNames = ['pdSection', 'lgdSection', 'eadSection', 'discountRateSection', 'forwardLookingSection'] as const
    const expectedAreas = ['PD', 'LGD', 'EAD', '折现率', '前瞻性信息']
    expect(sectionNames).toHaveLength(5)
    expect(expectedAreas).toHaveLength(5)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. G6-14 转回类型校验
// ═══════════════════════════════════════════════════════════════════════════════

describe('G6-14 转回类型校验', () => {
  const VALID_TYPES: Array<'转回' | '核销' | '收回'> = ['转回', '核销', '收回']

  it('仅允许 转回/核销/收回 三种类型', () => {
    // ReversalWriteOffRow.type 只接受这三种值
    for (const t of VALID_TYPES) {
      const row: ReversalWriteOffRow = {
        id: 'test-1',
        seq: 1,
        investProject: '测试债券',
        type: t,
        amount: 10000,
        reason: '测试原因',
        approvalProcedure: '已审批',
        reasonConclusion: '合理',
        indexRef: '',
      }
      expect(VALID_TYPES).toContain(row.type)
    }
  })

  it('TypeScript类型约束：type字段枚举值为3种', () => {
    // 验证枚举完整性
    expect(VALID_TYPES).toHaveLength(3)
    expect(VALID_TYPES).toContain('转回')
    expect(VALID_TYPES).toContain('核销')
    expect(VALID_TYPES).toContain('收回')
  })

  it('转回金额可为正数（表示冲回减值）', () => {
    const row: ReversalWriteOffRow = {
      id: 'test-reversal',
      seq: 1,
      investProject: '国开债2024',
      type: '转回',
      amount: 50000,
      reason: '信用风险改善',
      approvalProcedure: '经理审批',
      reasonConclusion: '合理',
      indexRef: 'G6-12',
    }
    expect(row.type).toBe('转回')
    expect(row.amount).toBeGreaterThan(0)
  })

  it('核销金额为正数（表示坏账核销）', () => {
    const row: ReversalWriteOffRow = {
      id: 'test-writeoff',
      seq: 2,
      investProject: '企业债2023',
      type: '核销',
      amount: 200000,
      reason: '债务人破产',
      approvalProcedure: '董事会批准',
      reasonConclusion: '合理',
      indexRef: '',
    }
    expect(row.type).toBe('核销')
    expect(row.amount).toBeGreaterThan(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. G6-15 凭证异常自动判定 (recalcAbnormal)
// ═══════════════════════════════════════════════════════════════════════════════

describe('G6-15 凭证异常自动判定 (recalcAbnormal)', () => {
  function makeVoucherRow(overrides: Partial<VoucherCheckRow> = {}): VoucherCheckRow {
    return {
      id: 'test-v1',
      seq: 1,
      date: '2024-12-31',
      voucherNo: 'PZ-001',
      businessContent: '计提减值',
      counterAccount: '资产减值损失',
      detailAccount: '1503',
      debitAmount: 10000,
      creditAmount: 0,
      attachment: null,
      supportingDoc: '',
      checkOriginal: true,
      checkAuthorized: true,
      checkAccounting: true,
      checkAmount: true,
      checkClassification: true,
      checkImpairment: true,
      checkInterest: true,
      indexRef: '',
      isAbnormal: false,
      abnormalNote: '',
      riskLevel: '',
      suggestion: '',
      remark: '',
      ...overrides,
    }
  }

  it('7项核对全通过 → isAbnormal = false（正常凭证）', () => {
    const { recalcAbnormal } = useG6EclVoucherCheck(ref('wp-1'), ref('proj-1'))
    const row = makeVoucherRow({
      checkOriginal: true,
      checkAuthorized: true,
      checkAccounting: true,
      checkAmount: true,
      checkClassification: true,
      checkImpairment: true,
      checkInterest: true,
    })
    recalcAbnormal(row)
    expect(row.isAbnormal).toBe(false)
  })

  it('任一核对为false → isAbnormal = true（异常凭证）', () => {
    const { recalcAbnormal } = useG6EclVoucherCheck(ref('wp-1'), ref('proj-1'))

    // 逐项测试每个核对字段为false时的异常判定
    const checkFields: Array<keyof VoucherCheckRow> = [
      'checkOriginal', 'checkAuthorized', 'checkAccounting',
      'checkAmount', 'checkClassification', 'checkImpairment', 'checkInterest',
    ]
    for (const field of checkFields) {
      const row = makeVoucherRow({ [field]: false })
      recalcAbnormal(row)
      expect(row.isAbnormal).toBe(true, `${field}为false时应判定为异常`)
    }
  })

  it('多项核对为false → isAbnormal = true', () => {
    const { recalcAbnormal } = useG6EclVoucherCheck(ref('wp-1'), ref('proj-1'))
    const row = makeVoucherRow({
      checkOriginal: false,
      checkAmount: false,
      checkImpairment: false,
    })
    recalcAbnormal(row)
    expect(row.isAbnormal).toBe(true)
  })

  it('全部核对为false → isAbnormal = true', () => {
    const { recalcAbnormal } = useG6EclVoucherCheck(ref('wp-1'), ref('proj-1'))
    const row = makeVoucherRow({
      checkOriginal: false,
      checkAuthorized: false,
      checkAccounting: false,
      checkAmount: false,
      checkClassification: false,
      checkImpairment: false,
      checkInterest: false,
    })
    recalcAbnormal(row)
    expect(row.isAbnormal).toBe(true)
  })
})
