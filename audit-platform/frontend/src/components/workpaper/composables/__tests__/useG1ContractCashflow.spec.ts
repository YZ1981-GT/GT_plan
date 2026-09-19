/**
 * useG1ContractCashflow — G1-10 SPPI 判定单元测试
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  suggestBondSppi,
  suggestWealthStep1,
  suggestWealthStep2,
  suggestPerpetual,
  suggestConvertible,
  suggestProject,
  suggestAbs,
  useG1ContractCashflow,
} from '../useG1ContractCashflow'
import type { ChecklistResponse } from '../useF1FormData'

describe('suggestBondSppi', () => {
  it('无特殊条款 → PASS', () => {
    expect(suggestBondSppi({
      hasEarlyRedemption: 'no', hasExtension: 'no',
      hasEquityConversion: 'no', hasLeverage: 'no',
    })).toBe('PASS')
  })

  it('权益转换或杠杆 → FAIL', () => {
    expect(suggestBondSppi({
      hasEarlyRedemption: 'no', hasExtension: 'no',
      hasEquityConversion: 'yes', hasLeverage: 'no',
    })).toBe('FAIL')
    expect(suggestBondSppi({
      hasEarlyRedemption: 'no', hasExtension: 'no',
      hasEquityConversion: 'no', hasLeverage: 'yes',
    })).toBe('FAIL')
  })

  it('仅提前赎回/展期 → FURTHER_ANALYSIS', () => {
    expect(suggestBondSppi({
      hasEarlyRedemption: 'yes', hasExtension: 'no',
      hasEquityConversion: 'no', hasLeverage: 'no',
    })).toBe('FURTHER_ANALYSIS')
  })
})

describe('suggestWealth', () => {
  it('不保本 → FAIL', () => {
    expect(suggestWealthStep1({
      guaranteesPrincipal: 'no', fixedGuaranteed: 'yes', floatingGuaranteed: 'no',
    })).toBe('FAIL')
  })

  it('保本+固定 → PASS；保本+浮动 → 待分析', () => {
    expect(suggestWealthStep1({
      guaranteesPrincipal: 'yes', fixedGuaranteed: 'yes', floatingGuaranteed: 'no',
    })).toBe('PASS')
    expect(suggestWealthStep1({
      guaranteesPrincipal: 'yes', fixedGuaranteed: 'yes', floatingGuaranteed: 'yes',
    })).toBe('FURTHER_ANALYSIS')
  })

  it('浮动不现实 → PASS；现实 → FAIL', () => {
    expect(suggestWealthStep2({ isUnrealistic: 'yes' })).toBe('PASS')
    expect(suggestWealthStep2({ isUnrealistic: 'no' })).toBe('FAIL')
  })
})

describe('suggestPerpetual / convertible', () => {
  it('可转固定数量权益 → FAIL', () => {
    expect(suggestPerpetual({
      convertibleToFixedEquity: 'yes', hasDeferredDividend: 'no',
    })).toBe('FAIL')
  })

  it('可转债含转股 → FAIL（修正模板错误示例）', () => {
    expect(suggestConvertible({ hasConversionFeature: 'yes' })).toBe('FAIL')
    expect(suggestConvertible({ hasConversionFeature: 'no' })).toBe('PASS')
  })
})

describe('suggestProject / abs', () => {
  it('依赖项目运营且无支持 → FAIL', () => {
    expect(suggestProject({
      cfDependsOnProjectOps: 'yes', deficiencyCompensation: '', guarantee: '',
    })).toBe('FAIL')
  })

  it('有差额补足 → 待分析', () => {
    expect(suggestProject({
      cfDependsOnProjectOps: 'yes', deficiencyCompensation: '母公司补足', guarantee: '',
    })).toBe('FURTHER_ANALYSIS')
  })

  it('ABS 次级 → FAIL；优先+穿透通过 → PASS', () => {
    expect(suggestAbs({ tranche: 'subordinated', lookThroughOk: '' })).toBe('FAIL')
    expect(suggestAbs({ tranche: 'senior', lookThroughOk: 'yes' })).toBe('PASS')
    expect(suggestAbs({ tranche: 'senior', lookThroughOk: 'no' })).toBe('FAIL')
  })
})

describe('useG1ContractCashflow', () => {
  it('迁移旧版扁平数组到债券分区', () => {
    const legacy = [{
      id: '1',
      investItem: '旧债券',
      sppiConclusion: 'pass',
      auditEval: '无特殊条款',
    }]
    const map = ref(new Map<string, ChecklistResponse>([
      ['G1-10-rows', { conclusion: JSON.stringify(legacy) } as ChecklistResponse],
    ]))
    const { store } = useG1ContractCashflow({
      allResponses: map,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    expect(store.value.version).toBe(2)
    expect(store.value.bondRows[0].investItem).toBe('旧债券')
  })

  it('更新债券权益转换自动建议 FAIL', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const save = vi.fn()
    const { store, updateBond } = useG1ContractCashflow({
      allResponses: map,
      debouncedSave: save,
      isReadonly: ref(false),
    })
    const id = store.value.bondRows[0].id
    updateBond(id, { hasEquityConversion: 'yes' })
    expect(store.value.bondRows[0].suggested).toBe('FAIL')
    expect(store.value.bondRows[0].conclusion).toBe('FAIL')
    expect(save).toHaveBeenCalled()
  })

  it('浮动项可带入第二步', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const { store, updateWealth1, pullFloatingToStep2 } = useG1ContractCashflow({
      allResponses: map,
      debouncedSave: vi.fn(),
      isReadonly: ref(false),
    })
    const id = store.value.wealthStep1[0].id
    updateWealth1(id, {
      investItem: 'XX结构性存款',
      guaranteesPrincipal: 'yes',
      floatingGuaranteed: 'yes',
    })
    // 清空默认空第二步行名以便带入
    store.value.wealthStep2 = []
    const n = pullFloatingToStep2()
    expect(n).toBe(1)
    expect(store.value.wealthStep2[0].investItem).toBe('XX结构性存款')
  })
})
