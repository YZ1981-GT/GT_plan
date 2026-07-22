/**
 * useI1PolicyCheck — 单元测试（聚合/模板/完成度核心）
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  aggregateCategoriesFromDetail,
  useI1PolicyCheck,
  DEFAULT_CATEGORIES,
} from '../useI1PolicyCheck'

describe('aggregateCategoriesFromDetail', () => {
  it('按类别汇总寿命众数与笔数', () => {
    const agg = aggregateCategoriesFromDetail([
      { category: '软件', usefulLifeMonths: 60, amortMethod: '直线法' },
      { category: '软件', usefulLifeMonths: 60, amortMethod: '直线法' },
      { category: '软件', usefulLifeMonths: 36, amortMethod: '直线法' },
      { category: '土地使用权', usefulLifeYears: 50, amortMethod: '直线法' },
    ])
    const soft = agg.find((a) => a.category === '软件')!
    expect(soft.detailCount).toBe(3)
    expect(soft.usefulLife).toBe('5年')
    expect(soft.amortMethod).toBe('直线法')
    const land = agg.find((a) => a.category === '土地使用权')!
    expect(land.usefulLife).toBe('50年')
  })

  it('空数组返回空', () => {
    expect(aggregateCategoriesFromDetail([])).toEqual([])
  })
})

describe('useI1PolicyCheck', () => {
  it('初始化默认类别与完成度未达标', () => {
    const map = ref(new Map())
    const api = useI1PolicyCheck(map)
    expect(api.policyParams.value.length).toBe(DEFAULT_CATEGORIES.length)
    expect(api.completenessOk.value).toBe(false)
    expect(api.completionProgress.value).toBeLessThan(100)
  })

  it('标记变更后显示表C并生成结论模板C路径可区分', () => {
    const map = ref(new Map())
    const saved: Record<string, any> = {}
    const api = useI1PolicyCheck(map, {
      onSave: (id, v) => { saved[id] = v },
    })
    api.policyParams.value[0].hasChange = 'Y'
    api.persistParams()
    expect(api.showPriorEstimates.value).toBe(true)
    expect(api.priorEstimates.value.some((p) => p.category === api.policyParams.value[0].category)).toBe(true)

    const tplA = api.suggestConclusionTemplate()
    expect(tplA.startsWith('B、') || tplA.startsWith('A、')).toBe(true)

    api.policyParams.value[0].meetsStandards = 'N'
    const tplC = api.suggestConclusionTemplate()
    expect(tplC.startsWith('C、')).toBe(true)
  })

  it('syncFromDetail 带入类别', () => {
    const map = ref(new Map())
    const api = useI1PolicyCheck(map)
    const n = api.syncFromDetail([
      { category: '专利权', usefulLifeMonths: 120, amortMethod: '直线法' },
      { category: '专利权', usefulLifeMonths: 120, amortMethod: '直线法' },
    ])
    expect(n).toBe(1)
    expect(api.policyParams.value.some((r) => r.category === '专利权' && r.usefulLife === '10年')).toBe(true)
  })

  it('applyIndustryTemplate 填充同业公司与政策格', () => {
    const map = ref(new Map())
    const api = useI1PolicyCheck(map)
    api.applyIndustryTemplate('software')
    expect(api.peerCompanies.value[0].name).toBeTruthy()
    expect(api.peerPolicies.value.some((r) => r.category === '软件')).toBe(true)
  })
})
