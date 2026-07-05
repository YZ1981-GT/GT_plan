/**
 * useG6SppiFairValue — G6-5 公允价值测试 单元测试
 *
 * 覆盖：Level3必填校验逻辑、差异红色高亮条件、Tab行同步、行CRUD、loadData/toJSON
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 4.3
 * Validates: Requirements 2.2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessageBox: {
    prompt: vi.fn(),
    confirm: vi.fn(),
  },
  ElMessage: {
    success: vi.fn(),
  },
}))

import { useG6SppiFairValue, type FairValueItem, type FairValueTestData } from '../useG6SppiFairValue'
import { ElMessageBox } from 'element-plus'

function createMockRow(overrides: Partial<FairValueItem> = {}): FairValueItem {
  return {
    id: `fv-test-${Date.now()}`,
    seq: 1,
    investProject: '测试债券A',
    faceValue: 100000,
    unadjQty: 10,
    unadjPrice: 100,
    unadjFairValue: 1000,
    auditedQty: 10,
    auditedPrice: 100,
    auditedFairValue: 1000,
    difference: 0,
    fairValueLevel: '',
    valuationMethod: '',
    consistencyWithPrior: '',
    sourceInstitution: '',
    inputSource: '',
    valuationTechnique: '',
    unobservableInputs: '',
    valuationFileRef: '',
    ...overrides,
  }
}

describe('useG6SppiFairValue — Level3必填校验', () => {
  it('非L3行无校验错误', () => {
    const { getL3ValidationErrors, hasL3Errors } = useG6SppiFairValue()
    const row = createMockRow({ fairValueLevel: 'L1' })
    expect(getL3ValidationErrors(row)).toEqual([])
    expect(hasL3Errors(row)).toBe(false)
  })

  it('L3行缺失必填字段时报告错误', () => {
    const { getL3ValidationErrors, hasL3Errors } = useG6SppiFairValue()
    const row = createMockRow({
      fairValueLevel: 'L3',
      valuationMethod: '',
      valuationTechnique: '',
      unobservableInputs: '',
    })
    const errors = getL3ValidationErrors(row)
    expect(errors).toContain('估值方法')
    expect(errors).toContain('估值技术')
    expect(errors).toContain('不可观察输入值')
    expect(errors).toHaveLength(3)
    expect(hasL3Errors(row)).toBe(true)
  })

  it('L3行填写完整后无校验错误', () => {
    const { getL3ValidationErrors } = useG6SppiFairValue()
    const row = createMockRow({
      fairValueLevel: 'L3',
      valuationMethod: '收益法',
      valuationTechnique: 'DCF',
      unobservableInputs: '折现率5%',
    })
    expect(getL3ValidationErrors(row)).toEqual([])
  })

  it('L3行部分填写则仅报告缺失字段', () => {
    const { getL3ValidationErrors } = useG6SppiFairValue()
    const row = createMockRow({
      fairValueLevel: 'L3',
      valuationMethod: '市场法',
      valuationTechnique: '',
      unobservableInputs: '信用利差',
    })
    const errors = getL3ValidationErrors(row)
    expect(errors).toEqual(['估值技术'])
  })

  it('l3ValidationSummary computed 统计全表L3校验问题', async () => {
    const { rows, l3ValidationSummary } = useG6SppiFairValue()
    rows.value = [
      createMockRow({ id: 'r1', fairValueLevel: 'L3', valuationMethod: '', valuationTechnique: '', unobservableInputs: '' }),
      createMockRow({ id: 'r2', fairValueLevel: 'L1' }),
      createMockRow({ id: 'r3', fairValueLevel: 'L3', valuationMethod: '收益法', valuationTechnique: 'DCF', unobservableInputs: '折现率' }),
    ]
    await nextTick()
    expect(l3ValidationSummary.value).toHaveLength(1)
    expect(l3ValidationSummary.value[0].row.id).toBe('r1')
    expect(l3ValidationSummary.value[0].errors).toHaveLength(3)
  })
})

describe('useG6SppiFairValue — 差异红色高亮', () => {
  it('审定=未审时无差异，不高亮', () => {
    const { hasDifference, getDiffCellStyle } = useG6SppiFairValue()
    const row = createMockRow({ auditedFairValue: 1000, unadjFairValue: 1000, difference: 0 })
    expect(hasDifference(row)).toBe(false)
    expect(getDiffCellStyle(row)).toEqual({})
  })

  it('|审定-未审|>0时高亮红色', () => {
    const { hasDifference, getDiffCellStyle } = useG6SppiFairValue()
    const row = createMockRow({ difference: 500 })
    expect(hasDifference(row)).toBe(true)
    const style = getDiffCellStyle(row)
    expect(style.color).toBe('#dc2626')
    expect(style.backgroundColor).toBe('#fef2f2')
    expect(style.fontWeight).toBe('600')
  })

  it('负差异也高亮（未审>审定）', () => {
    const { hasDifference, getDiffCellStyle } = useG6SppiFairValue()
    const row = createMockRow({ difference: -200 })
    expect(hasDifference(row)).toBe(true)
    expect(getDiffCellStyle(row).color).toBe('#dc2626')
  })

  it('diffCount computed 统计差异行数', async () => {
    const { rows, diffCount } = useG6SppiFairValue()
    rows.value = [
      createMockRow({ id: 'a', auditedFairValue: 1100, unadjFairValue: 1000 }), // diff = 100
      createMockRow({ id: 'b', auditedFairValue: 1000, unadjFairValue: 1000 }), // diff = 0
      createMockRow({ id: 'c', auditedFairValue: 800, unadjFairValue: 850 }),   // diff = -50
    ]
    await nextTick()
    expect(diffCount.value).toBe(2)
  })
})

describe('useG6SppiFairValue — Tab行同步', () => {
  it('selectedRowIndex 在两个Tab间共享', () => {
    const { selectedRowIndex, activeTab } = useG6SppiFairValue()
    expect(selectedRowIndex.value).toBe(0)
    activeTab.value = 'tab2'
    selectedRowIndex.value = 3
    activeTab.value = 'tab1'
    // selectedRowIndex remains synced across tab switches
    expect(selectedRowIndex.value).toBe(3)
  })

  it('activeTab 默认为 tab1', () => {
    const { activeTab } = useG6SppiFairValue()
    expect(activeTab.value).toBe('tab1')
  })
})

describe('useG6SppiFairValue — 行CRUD (addRow/removeRow)', () => {
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
    expect(rows.value[0].seq).toBe(1)
    expect(rows.value[1].seq).toBe(2)
    expect(rows.value.map(r => r.investProject)).toEqual(['A', 'C'])
  })

  it('removeRow 用户取消不删除', async () => {
    vi.mocked(ElMessageBox.confirm).mockRejectedValue('cancel')
    const { rows, removeRow } = useG6SppiFairValue()
    rows.value = [createMockRow({ id: 'r1' })]
    await removeRow('r1')
    expect(rows.value).toHaveLength(1)
  })

  it('removeRow 不存在的id无效', async () => {
    const { rows, removeRow } = useG6SppiFairValue()
    rows.value = [createMockRow({ id: 'r1' })]
    await removeRow('nonexistent')
    expect(rows.value).toHaveLength(1)
  })
})

describe('useG6SppiFairValue — loadData/toJSON round-trip', () => {
  it('loadData 加载数据并重算差异', () => {
    const { rows, conclusion, loadData } = useG6SppiFairValue()
    const data: FairValueTestData = {
      rows: [
        createMockRow({ id: 'r1', auditedFairValue: 1200, unadjFairValue: 1000 }),
        createMockRow({ id: 'r2', auditedFairValue: 800, unadjFairValue: 800 }),
      ],
      conclusion: '公允价值计量准确',
    }
    loadData(data)
    expect(rows.value).toHaveLength(2)
    expect(rows.value[0].difference).toBe(200) // 1200 - 1000
    expect(rows.value[1].difference).toBe(0)   // 800 - 800
    expect(conclusion.value).toBe('公允价值计量准确')
  })

  it('loadData null/empty 清空数据', () => {
    const { rows, loadData } = useG6SppiFairValue()
    rows.value = [createMockRow()]
    loadData(null)
    expect(rows.value).toHaveLength(0)
  })

  it('toJSON 输出正确结构', () => {
    const { rows, conclusion, toJSON } = useG6SppiFairValue()
    rows.value = [createMockRow({ id: 'r1', investProject: 'XX债券', auditedFairValue: 500, unadjFairValue: 450, difference: 50 })]
    conclusion.value = '测试结论'
    const json = toJSON()
    expect(json.rows).toHaveLength(1)
    expect(json.rows[0].investProject).toBe('XX债券')
    expect(json.conclusion).toBe('测试结论')
  })

  it('loadData → toJSON round-trip 数据不丢失', () => {
    const { loadData, toJSON } = useG6SppiFairValue()
    const original: FairValueTestData = {
      rows: [
        createMockRow({
          id: 'rt1',
          investProject: '测试round-trip',
          faceValue: 50000,
          auditedFairValue: 2000,
          unadjFairValue: 1800,
          fairValueLevel: 'L3',
          valuationMethod: '收益法',
          valuationTechnique: 'DCF',
          unobservableInputs: '折现率5%',
        }),
      ],
      conclusion: 'round-trip结论',
    }
    loadData(original)
    const result = toJSON()
    expect(result.rows[0].investProject).toBe('测试round-trip')
    expect(result.rows[0].faceValue).toBe(50000)
    expect(result.rows[0].fairValueLevel).toBe('L3')
    expect(result.rows[0].valuationMethod).toBe('收益法')
    expect(result.rows[0].difference).toBe(200) // 2000-1800
    expect(result.conclusion).toBe('round-trip结论')
  })
})

describe('useG6SppiFairValue — levelSummary', () => {
  it('按层次分组统计行数', async () => {
    const { rows, levelSummary } = useG6SppiFairValue()
    rows.value = [
      createMockRow({ id: 'a', fairValueLevel: 'L1' }),
      createMockRow({ id: 'b', fairValueLevel: 'L1' }),
      createMockRow({ id: 'c', fairValueLevel: 'L2' }),
      createMockRow({ id: 'd', fairValueLevel: 'L3' }),
      createMockRow({ id: 'e', fairValueLevel: '' }),
    ]
    await nextTick()
    expect(levelSummary.value).toEqual({ L1: 2, L2: 1, L3: 1, unset: 1 })
  })
})
