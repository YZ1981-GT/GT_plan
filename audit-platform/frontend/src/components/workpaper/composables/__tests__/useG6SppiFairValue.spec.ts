/**
 * useG6SppiFairValue — G6-5 公允价值测试 单元测试
 *
 * 覆盖：分层必填校验、差异高亮、数量×单价公式、差异分解、CRUD、loadData/toJSON
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'

vi.mock('element-plus', () => ({
  ElMessageBox: {
    prompt: vi.fn(),
    confirm: vi.fn(),
  },
  ElMessage: {
    success: vi.fn(),
  },
}))

import {
  useG6SppiFairValue,
  enrichFairValueRow,
  migrateFairValueRow,
  getLevelValidationErrors,
  G6_FV_DIFF_THRESHOLD,
  type FairValueItem,
  type FairValueTestData,
} from '../useG6SppiFairValue'
import { ElMessageBox } from 'element-plus'
import {
  calcFairValueAmount,
  calcFairValueQtyImpact,
  calcFairValuePriceImpact,
  calcFairValueDiff,
} from '@/composables/useG6SppiFormulaEngine'

function createMockRow(overrides: Partial<FairValueItem> = {}): FairValueItem {
  return enrichFairValueRow({
    id: `fv-test-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    seq: 1,
    investProject: '测试债券A',
    unadjQty: 10,
    unadjPrice: 100,
    unadjFairValue: 0,
    unadjFairValueLevel: '',
    auditedQty: 10,
    auditedPrice: 100,
    auditedFairValue: 0,
    auditedFairValueLevel: '',
    qtyImpact: 0,
    priceImpact: 0,
    difference: 0,
    diffReason: '',
    valuationMethod: '',
    consistencyWithPrior: '',
    sourceInstitution: '',
    inputSource: '',
    valuationTechnique: '',
    unobservableInputs: '',
    inputValue: '',
    valuationFileRef: '',
    ...overrides,
  })
}

describe('公式引擎 — 公允价值金额与差异分解', () => {
  it('calcFairValueAmount = 数量 × 单价', () => {
    expect(calcFairValueAmount(10, 100.5)).toBe(1005)
    expect(calcFairValueAmount(0, 100)).toBe(0)
  })

  it('数量影响 + 价格影响 = 总差异', () => {
    const unadjQty = 10
    const auditedQty = 12
    const unadjPrice = 100
    const auditedPrice = 105
    const qtyImpact = calcFairValueQtyImpact(auditedQty, unadjQty, unadjPrice)
    const priceImpact = calcFairValuePriceImpact(auditedQty, auditedPrice, unadjPrice)
    const unadjFv = calcFairValueAmount(unadjQty, unadjPrice)
    const auditedFv = calcFairValueAmount(auditedQty, auditedPrice)
    const diff = calcFairValueDiff(auditedFv, unadjFv)
    expect(qtyImpact).toBe(200) // (12-10)×100
    expect(priceImpact).toBe(60) // 12×(105-100)
    expect(qtyImpact + priceImpact).toBe(diff)
  })

  it('enrichFairValueRow 自动重算公式列', () => {
    const row = enrichFairValueRow(createMockRow({
      unadjQty: 10,
      unadjPrice: 100,
      auditedQty: 12,
      auditedPrice: 105,
    }))
    expect(row.unadjFairValue).toBe(1000)
    expect(row.auditedFairValue).toBe(1260)
    expect(row.qtyImpact).toBe(200)
    expect(row.priceImpact).toBe(60)
    expect(row.difference).toBe(260)
  })
})

describe('useG6SppiFairValue — 分层必填校验', () => {
  it('L1 缺来源说明时报错', () => {
    const row = createMockRow({ auditedFairValueLevel: 'L1', sourceInstitution: '' })
    expect(getLevelValidationErrors(row)).toEqual(['公允价值来源说明'])
  })

  it('L2 缺估值方法/可观察输入值时报错', () => {
    const row = createMockRow({ auditedFairValueLevel: 'L2' })
    expect(getLevelValidationErrors(row)).toEqual(['估值方法', '可观察输入值来源'])
  })

  it('非分层行无校验错误', () => {
    const { getL3ValidationErrors, hasL3Errors } = useG6SppiFairValue()
    const row = createMockRow({ auditedFairValueLevel: 'L1', sourceInstitution: '上交所' })
    expect(getL3ValidationErrors(row)).toEqual([])
    expect(hasL3Errors(row)).toBe(false)
  })

  it('L3 行缺失必填字段时报告全部错误', () => {
    const { getL3ValidationErrors, hasL3Errors } = useG6SppiFairValue()
    const row = createMockRow({ auditedFairValueLevel: 'L3' })
    const errors = getL3ValidationErrors(row)
    expect(errors).toContain('估值方法')
    expect(errors).toContain('估值技术')
    expect(errors).toContain('不可观察输入值')
    expect(errors).toContain('输入值/估值结果')
    expect(errors).toContain('估值文件索引')
    expect(errors).toHaveLength(5)
    expect(hasL3Errors(row)).toBe(true)
  })

  it('L3 行填写完整后无校验错误', () => {
    const { getL3ValidationErrors } = useG6SppiFairValue()
    const row = createMockRow({
      auditedFairValueLevel: 'L3',
      valuationMethod: '收益法',
      valuationTechnique: 'DCF',
      unobservableInputs: '折现率5%',
      inputValue: '16%',
      valuationFileRef: 'G6-5-1',
    })
    expect(getL3ValidationErrors(row)).toEqual([])
  })

  it('兼容旧 fairValueLevel 字段', () => {
    const row = createMockRow({ fairValueLevel: 'L3', auditedFairValueLevel: '' })
    expect(getLevelValidationErrors(row)).toHaveLength(5)
  })

  it('l3ValidationSummary 统计全表分层校验问题', async () => {
    const { rows, l3ValidationSummary } = useG6SppiFairValue()
    rows.value = [
      createMockRow({ id: 'r1', auditedFairValueLevel: 'L3' }),
      createMockRow({ id: 'r2', auditedFairValueLevel: 'L1', sourceInstitution: '上交所' }),
      createMockRow({
        id: 'r3',
        auditedFairValueLevel: 'L3',
        valuationMethod: '收益法',
        valuationTechnique: 'DCF',
        unobservableInputs: '折现率',
        inputValue: '5%',
        valuationFileRef: 'idx-1',
      }),
    ]
    await nextTick()
    expect(l3ValidationSummary.value).toHaveLength(1)
    expect(l3ValidationSummary.value[0].row.id).toBe('r1')
    expect(l3ValidationSummary.value[0].errors).toHaveLength(5)
  })
})

describe('useG6SppiFairValue — 差异红色高亮', () => {
  it('审定=未审时无差异，不高亮', () => {
    const { hasDifference, getDiffCellStyle } = useG6SppiFairValue()
    const row = createMockRow({ auditedPrice: 100, unadjPrice: 100 })
    expect(hasDifference(row)).toBe(false)
    expect(getDiffCellStyle(row)).toEqual({})
  })

  it('|差异|>阈值时高亮红色', () => {
    const { hasDifference, getDiffCellStyle } = useG6SppiFairValue()
    const row = createMockRow({ auditedPrice: 150, unadjPrice: 100 }) // diff=500
    expect(row.difference).toBe(500)
    expect(hasDifference(row)).toBe(true)
    const style = getDiffCellStyle(row)
    expect(style.color).toBe('#dc2626')
    expect(style.backgroundColor).toBe('#fef2f2')
    expect(style.fontWeight).toBe('600')
  })

  it('低于阈值的舍入差异不触发高亮', () => {
    const { hasDifference } = useG6SppiFairValue()
    // 直接构造差异=阈值（不经 enrich 覆盖）
    const row = { ...createMockRow(), difference: G6_FV_DIFF_THRESHOLD }
    expect(hasDifference(row)).toBe(false)
  })

  it('负差异也高亮', () => {
    const { hasDifference, getDiffCellStyle } = useG6SppiFairValue()
    const row = createMockRow({ auditedPrice: 80, unadjPrice: 100 }) // diff=-200
    expect(row.difference).toBe(-200)
    expect(hasDifference(row)).toBe(true)
    expect(getDiffCellStyle(row).color).toBe('#dc2626')
  })

  it('diffCount / missingDiffReasonCount 统计', async () => {
    const { rows, diffCount, missingDiffReasonCount } = useG6SppiFairValue()
    rows.value = [
      createMockRow({ id: 'a', auditedPrice: 110, unadjPrice: 100 }), // diff=100, no reason
      createMockRow({ id: 'b', auditedPrice: 100, unadjPrice: 100 }), // diff=0
      createMockRow({ id: 'c', auditedPrice: 80, unadjPrice: 85, diffReason: '价格下调' }), // diff=-50
    ]
    await nextTick()
    expect(diffCount.value).toBe(2)
    expect(missingDiffReasonCount.value).toBe(1)
  })
})

describe('useG6SppiFairValue — Tab行同步', () => {
  it('selectedRowIndex 在两个Tab间共享', () => {
    const { selectedRowIndex, activeTab } = useG6SppiFairValue()
    expect(selectedRowIndex.value).toBe(0)
    activeTab.value = 'tab2'
    selectedRowIndex.value = 3
    activeTab.value = 'tab1'
    expect(selectedRowIndex.value).toBe(3)
  })

  it('activeTab 默认为 tab1', () => {
    const { activeTab } = useG6SppiFairValue()
    expect(activeTab.value).toBe('tab1')
  })
})

describe('useG6SppiFairValue — 行CRUD', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('addRow 成功新增行', async () => {
    vi.mocked(ElMessageBox.prompt).mockResolvedValue({ value: '新债券A' } as any)
    const { rows, addRow, selectedRowIndex } = useG6SppiFairValue()
    await addRow()
    expect(rows.value).toHaveLength(1)
    expect(rows.value[0].investProject).toBe('新债券A')
    expect(rows.value[0].seq).toBe(1)
    expect(selectedRowIndex.value).toBe(0)
  })

  it('addRow 用户取消不新增', async () => {
    vi.mocked(ElMessageBox.prompt).mockRejectedValue('cancel')
    const { rows, addRow } = useG6SppiFairValue()
    await addRow()
    expect(rows.value).toHaveLength(0)
  })

  it('updateRow 不可改写公式列', async () => {
    const { rows, updateRow } = useG6SppiFairValue()
    rows.value = [createMockRow({ id: 'r1', unadjPrice: 100, auditedPrice: 100 })]
    await nextTick()
    updateRow('r1', 'auditedFairValue', 9999 as any)
    expect(rows.value[0].auditedFairValue).toBe(1000)
  })

  it('updateRow 改单价后重算公允价值', async () => {
    const { rows, updateRow } = useG6SppiFairValue()
    rows.value = [createMockRow({ id: 'r1' })]
    await nextTick()
    updateRow('r1', 'auditedPrice', 120)
    expect(rows.value[0].auditedFairValue).toBe(1200)
    expect(rows.value[0].difference).toBe(200)
  })

  it('removeRow 确认后删除并重排序号', async () => {
    vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as any)
    const { rows, removeRow } = useG6SppiFairValue()
    rows.value = [
      createMockRow({ id: 'r1', seq: 1, investProject: 'A' }),
      createMockRow({ id: 'r2', seq: 2, investProject: 'B' }),
      createMockRow({ id: 'r3', seq: 3, investProject: 'C' }),
    ]
    await removeRow('r2')
    expect(rows.value).toHaveLength(2)
    expect(rows.value.map(r => r.investProject)).toEqual(['A', 'C'])
  })

  it('removeRow 用户取消不删除', async () => {
    vi.mocked(ElMessageBox.confirm).mockRejectedValue('cancel')
    const { rows, removeRow } = useG6SppiFairValue()
    rows.value = [createMockRow({ id: 'r1' })]
    await removeRow('r1')
    expect(rows.value).toHaveLength(1)
  })
})

describe('useG6SppiFairValue — loadData/toJSON', () => {
  it('loadData 按数量×单价重算差异', () => {
    const { rows, conclusion, loadData } = useG6SppiFairValue()
    const data: FairValueTestData = {
      rows: [
        createMockRow({ id: 'r1', auditedPrice: 120, unadjPrice: 100 }),
        createMockRow({ id: 'r2', auditedPrice: 100, unadjPrice: 100 }),
      ],
      conclusion: '公允价值计量准确',
    }
    loadData(data)
    expect(rows.value).toHaveLength(2)
    expect(rows.value[0].unadjFairValue).toBe(1000)
    expect(rows.value[0].auditedFairValue).toBe(1200)
    expect(rows.value[0].difference).toBe(200)
    expect(rows.value[1].difference).toBe(0)
    expect(conclusion.value).toBe('公允价值计量准确')
  })

  it('旧数据仅存 FV 时可反推单价', () => {
    const migrated = migrateFairValueRow(
      { id: 'legacy', investProject: '旧债', unadjFairValue: 5000, auditedFairValue: 5200 },
      1,
    )
    expect(migrated.unadjQty).toBe(1)
    expect(migrated.unadjPrice).toBe(5000)
    expect(migrated.auditedPrice).toBe(5200)
    expect(migrated.difference).toBe(200)
  })

  it('旧 fairValueLevel 迁移到双层次', () => {
    const migrated = migrateFairValueRow(
      { id: 'l', fairValueLevel: 'L2', unadjQty: 1, unadjPrice: 100, auditedQty: 1, auditedPrice: 100 },
      1,
    )
    expect(migrated.unadjFairValueLevel).toBe('L2')
    expect(migrated.auditedFairValueLevel).toBe('L2')
  })

  it('loadData null 清空数据', () => {
    const { rows, loadData } = useG6SppiFairValue()
    rows.value = [createMockRow()]
    loadData(null)
    expect(rows.value).toHaveLength(0)
  })

  it('loadData → toJSON round-trip', () => {
    const { loadData, toJSON } = useG6SppiFairValue()
    const original: FairValueTestData = {
      rows: [
        createMockRow({
          id: 'rt1',
          investProject: '测试round-trip',
          faceValue: 50000,
          auditedPrice: 200,
          unadjPrice: 180,
          auditedFairValueLevel: 'L3',
          valuationMethod: '收益法',
          valuationTechnique: 'DCF',
          unobservableInputs: '折现率5%',
          inputValue: '5%',
          valuationFileRef: 'G6-5-1',
        }),
      ],
      conclusion: 'round-trip结论',
    }
    loadData(original)
    const result = toJSON()
    expect(result.rows[0].investProject).toBe('测试round-trip')
    expect(result.rows[0].faceValue).toBe(50000)
    expect(result.rows[0].auditedFairValueLevel).toBe('L3')
    expect(result.rows[0].fairValueLevel).toBe('L3')
    expect(result.rows[0].difference).toBe(200) // (200-180)×10
    expect(result.conclusion).toBe('round-trip结论')
  })
})

describe('useG6SppiFairValue — levelSummary / totals', () => {
  it('按审定层次分组统计', async () => {
    const { rows, levelSummary } = useG6SppiFairValue()
    rows.value = [
      createMockRow({ id: 'a', auditedFairValueLevel: 'L1' }),
      createMockRow({ id: 'b', auditedFairValueLevel: 'L1' }),
      createMockRow({ id: 'c', auditedFairValueLevel: 'L2' }),
      createMockRow({ id: 'd', auditedFairValueLevel: 'L3' }),
      createMockRow({ id: 'e', auditedFairValueLevel: '' }),
    ]
    await nextTick()
    expect(levelSummary.value).toEqual({ L1: 2, L2: 1, L3: 1, unset: 1 })
  })

  it('totals 汇总未审/审定/差异', async () => {
    const { rows, totals } = useG6SppiFairValue()
    rows.value = [
      createMockRow({ id: 'a', auditedPrice: 110, unadjPrice: 100 }),
      createMockRow({ id: 'b', auditedPrice: 90, unadjPrice: 100 }),
    ]
    await nextTick()
    expect(totals.value.unadjFairValue).toBe(2000)
    expect(totals.value.auditedFairValue).toBe(2000)
    expect(totals.value.difference).toBe(0)
  })
})
