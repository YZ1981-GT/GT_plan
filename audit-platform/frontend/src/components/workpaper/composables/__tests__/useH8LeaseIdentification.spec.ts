/**
 * useH8LeaseIdentification — H8-4 公式与迁移单测
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  calcIdentifiedAsset,
  calcDirectUseRight,
  resolveDirectUse,
  calcLeaseIdentificationConclusion,
  calcSplitConclusion,
  calcCombineConclusion,
  calcTermWithin12,
  calcShortTermConclusion,
  calcLowValueConclusion,
  isContainsLease,
  useH8LeaseIdentification,
  suggestTipForField,
  calcCompletenessGaps,
  LOW_VALUE_THRESHOLD,
} from '../useH8LeaseIdentification'

describe('H8-4 Excel formula helpers', () => {
  it('F11: 物理可区分=是 且 替换权=否 → 已识别资产=是', () => {
    expect(calcIdentifiedAsset('是', '否')).toBe('是')
    expect(calcIdentifiedAsset('是', '是')).toBe('否')
    expect(calcIdentifiedAsset('否', '否')).toBe('否')
    expect(calcIdentifiedAsset('', '否')).toBe('')
  })

  it('F15: 路径①或路径②(预先确定+运营/设计)', () => {
    expect(calcDirectUseRight('是', '', '', '')).toBe('是')
    expect(calcDirectUseRight('否', '是', '是', '否')).toBe('是')
    expect(calcDirectUseRight('否', '是', '否', '是')).toBe('是')
    expect(calcDirectUseRight('否', '是', '否', '否')).toBe('否')
    expect(calcDirectUseRight('否', '否', '', '')).toBe('否')
  })

  it('directUseOverride 优先于自动', () => {
    expect(resolveDirectUse({
      directUseOverride: '否',
      canDirectPurposeManner: '是',
      usePredetermined: '',
      canOperateAsset: '',
      designedAsset: '',
    })).toBe('否')
  })

  it('C21: 三要素 AND', () => {
    expect(calcLeaseIdentificationConclusion('是', '是', '是')).toBe('合同为租赁或者包含租赁')
    expect(calcLeaseIdentificationConclusion('是', '是', '否')).toBe('不包含租赁')
    expect(calcLeaseIdentificationConclusion('是', '', '是')).toBe('待填写三要素后自动判定')
    expect(isContainsLease('合同为租赁或者包含租赁')).toBe(true)
  })

  it('C27 / C36 分拆与合并', () => {
    expect(calcSplitConclusion('是', '是')).toBe('构成合同中的一项单独租赁')
    expect(calcSplitConclusion('是', '否')).toBe('无须分拆')
    expect(calcCombineConclusion('否', '否', '是')).toBe('应当合并为一份合同进行会计处理')
    expect(calcCombineConclusion('否', '否', '否')).toBe('单项租赁')
  })

  it('F41 / C45 短期租赁', () => {
    expect(calcTermWithin12('是', '是')).toBe('是')
    expect(calcTermWithin12('是', '否')).toBe('否')
    expect(calcShortTermConclusion('是', '是')).toBe('属于短期租赁')
    expect(calcShortTermConclusion('是', '否')).toBe('不属于短期租赁')
  })

  it('C54 低价值', () => {
    expect(calcLowValueConclusion('是', '是')).toBe('属于低价值资产租赁')
    expect(calcLowValueConclusion('是', '否')).toBe('不属于低价值资产租赁')
    expect(LOW_VALUE_THRESHOLD).toBe(40000)
  })
})

describe('useH8LeaseIdentification', () => {
  it('新增合同 + 替换权两条件联动 + 三要素结论', () => {
    const saved: any[] = []
    const allResponses = ref(new Map())
    const api = useH8LeaseIdentification({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      onSave: (_id, value) => { saved.push(value) },
    })

    api.addRecord('ZL-001')
    expect(api.records.value).toHaveLength(1)

    const id = api.records.value[0].recordId
    api.updateField(id, 'physicallyDistinct', '是')
    api.updateField(id, 'substitutionBothConditions', '是')
    expect(api.records.value[0].supplierSubstantiveSubstitution).toBe('是')
    expect(calcIdentifiedAsset(
      api.records.value[0].physicallyDistinct,
      api.records.value[0].supplierSubstantiveSubstitution,
    )).toBe('否')

    api.updateField(id, 'supplierSubstantiveSubstitution', '否')
    api.updateField(id, 'canDirectPurposeManner', '是')
    api.updateField(id, 'economicBenefits', '是')
    expect(api.records.value[0].conclusion).toBe('是')
    expect(api.leaseCount.value).toBe(1)
    expect(saved.length).toBeGreaterThan(0)
  })

  it('兼容旧版 items[] 结构迁移', () => {
    const legacy = [{
      recordId: 'old1',
      contractNo: 'OLD-1',
      finalConclusion: '是',
      auditNote: '旧说明',
      items: [
        { itemId: 'a', label: '资产是否明确指定', category: 'identifiedAsset', conclusion: '是', explanation: '' },
        { itemId: 'b', label: '供应商是否有实质性替换权', category: 'substitutionRight', conclusion: '否', explanation: '' },
        { itemId: 'c', label: '客户是否有权主导资产使用', category: 'controlRight', conclusion: '是', explanation: '' },
        { itemId: 'd', label: '客户是否获得几乎全部经济利益', category: 'controlRight', conclusion: '是', explanation: '' },
      ],
    }]
    const allResponses = ref(new Map([
      ['H8-4-records', { remark: JSON.stringify(legacy) }],
    ]))
    const api = useH8LeaseIdentification({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
    })
    expect(api.records.value).toHaveLength(1)
    expect(api.records.value[0].physicallyDistinct).toBe('是')
    expect(api.records.value[0].supplierSubstantiveSubstitution).toBe('否')
    expect(api.records.value[0].canDirectPurposeManner).toBe('是')
    expect(api.records.value[0].economicBenefits).toBe('是')
    expect(api.records.value[0].explanation).toBe('旧说明')
  })

  it('从 H8-2 带入 + 推送 H8-5 / H8-13', () => {
    const saved: Array<{ id: string; value: any }> = []
    const allResponses = ref(new Map([
      ['H8-2-rows', {
        remark: JSON.stringify([
          { contractNo: 'C-1', assetName: '办公室', lessor: '甲', startDate: '2024-01-01', endDate: '2026-12-31' },
          { contractNo: 'C-2', assetName: '车辆', lessor: '乙', startDate: '2025-01-01', endDate: '2025-06-30' },
        ]),
      }],
    ]))
    const api = useH8LeaseIdentification({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      onSave: (id, value) => { saved.push({ id, value }) },
    })

    expect(api.missingH82Contracts.value.map(c => c.contractNo)).toEqual(['C-1', 'C-2'])
    const pull = api.pullFromH82()
    expect(pull.added).toBe(2)
    expect(api.records.value).toHaveLength(2)
    expect(api.missingH82Contracts.value).toHaveLength(0)

    const c1 = api.records.value.find(r => r.contractNo === 'C-1')!
    api.updateField(c1.recordId, 'physicallyDistinct', '是')
    api.updateField(c1.recordId, 'supplierSubstantiveSubstitution', '否')
    api.updateField(c1.recordId, 'canDirectPurposeManner', '是')
    api.updateField(c1.recordId, 'economicBenefits', '是')
    expect(api.pendingPushH85.value.map(r => r.contractNo)).toContain('C-1')

    const p85 = api.pushToH85()
    expect(p85.added).toBe(1)
    expect(saved.some(s => s.id === 'H8-5-records')).toBe(true)
    expect(api.pendingPushH85.value).toHaveLength(0)

    api.updateField(c1.recordId, 'shortTermApplicable', '是')
    api.updateField(c1.recordId, 'termWithRenewalWithin12', '是')
    api.updateField(c1.recordId, 'renewContractWithin12', '是')
    api.updateField(c1.recordId, 'noPurchaseOption', '是')
    expect(api.pendingPushH813.value.map(r => r.contractNo)).toContain('C-1')
    const p813 = api.pushToH813()
    expect(p813.added).toBe(1)
    expect(saved.some(s => s.id === 'H8-13-rows')).toBe(true)
  })

  it('suggestTipForField / calcCompletenessGaps', () => {
    expect(suggestTipForField('supplierSubstantiveSubstitution', '是')).toBe('s1-asset')
    expect(suggestTipForField('physicallyDistinct', '是')).toBeNull()
    const gaps = calcCompletenessGaps({
      recordId: 'x',
      contractNo: 'T',
      assetDesc: '',
      physicallyDistinct: '',
      physicallyDistinctInfo: '',
      physicallyDistinctIndex: '',
      supplierSubstantiveSubstitution: '',
      substitutionInfo: '',
      substitutionIndex: '',
      substitutionBothConditions: '',
      canDirectPurposeManner: '',
      directPurposeInfo: '',
      usePredetermined: '',
      predeterminedInfo: '',
      canOperateAsset: '',
      operateInfo: '',
      designedAsset: '',
      designInfo: '',
      directUseIndex: '',
      economicBenefits: '',
      economicBenefitsInfo: '',
      economicBenefitsIndex: '',
      directUseOverride: '',
      splitApplicable: '',
      canBenefitSeparately: '',
      canBenefitSeparatelyInfo: '',
      canBenefitSeparatelyIndex: '',
      notHighlyDependent: '',
      notHighlyDependentInfo: '',
      notHighlyDependentIndex: '',
      electNotSplitNonLease: '',
      combineApplicable: '',
      packageCommercialPurpose: '',
      packageInfo: '',
      packageIndex: '',
      considerationDepends: '',
      considerationInfo: '',
      considerationIndex: '',
      combinedSingleLease: '',
      combinedInfo: '',
      combinedIndex: '',
      shortTermApplicable: '',
      termWithRenewalWithin12: '',
      termWithRenewalInfo: '',
      renewContractWithin12: '',
      renewContractInfo: '',
      shortTermIndex: '',
      noPurchaseOption: '',
      noPurchaseOptionInfo: '',
      lowValueApplicable: '',
      lowValueWhenNew: '',
      lowValueInfo: '',
      lowValueIndex: '',
      newAssetValue: 0,
      noSubleaseExpected: '',
      noSubleaseInfo: '',
      noSubleaseIndex: '',
      explanation: '',
      conclusion: '',
    })
    expect(gaps.some(g => g.includes('物理可区分'))).toBe(true)
  })
})
