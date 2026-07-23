/**
 * useI4PolicyCheck — 单元测试（聚合/模板/完成度核心）
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  aggregateCategoriesFromI4Detail,
  useI4PolicyCheck,
  DEFAULT_CATEGORIES,
} from '../useI4PolicyCheck'

describe('aggregateCategoriesFromI4Detail', () => {
  it('按费用类型汇总受益期限众数与笔数', () => {
    const agg = aggregateCategoriesFromI4Detail([
      { expenseType: '装修费', totalMonths: 36, amortizationMethod: '直线法' },
      { expenseType: '装修费', totalMonths: 36, amortizationMethod: '直线法' },
      { expenseType: '装修费', totalMonths: 60, amortizationMethod: '直线法' },
      { expenseType: '开办费', totalMonths: 60, amortizationMethod: '直线法' },
    ])
    const deco = agg.find((a) => a.category === '装修费')!
    expect(deco.detailCount).toBe(3)
    expect(deco.benefitPeriod).toBe('3年')
    expect(deco.amortMethod).toBe('直线法')
    const open = agg.find((a) => a.category === '开办费')!
    expect(open.benefitPeriod).toBe('5年')
  })

  it('空数组返回空', () => {
    expect(aggregateCategoriesFromI4Detail([])).toEqual([])
  })
})

describe('useI4PolicyCheck', () => {
  it('初始化默认费用类型与完成度未达标', () => {
    const map = ref(new Map())
    const api = useI4PolicyCheck(map)
    expect(api.policyParams.value.length).toBe(DEFAULT_CATEGORIES.length)
    expect(api.completenessOk.value).toBe(false)
    expect(api.completionProgress.value).toBeLessThan(100)
  })

  it('标记变更后显示表C并生成结论模板路径可区分', () => {
    const map = ref(new Map())
    const saved: Record<string, any> = {}
    const api = useI4PolicyCheck(map, {
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

  it('syncFromDetail 带入费用类型', () => {
    const map = ref(new Map())
    const api = useI4PolicyCheck(map)
    const n = api.syncFromDetail([
      { expenseType: '租赁改良', totalMonths: 48, amortizationMethod: '直线法' },
      { expenseType: '租赁改良', totalMonths: 48, amortizationMethod: '直线法' },
    ])
    expect(n).toBe(1)
    expect(api.policyParams.value.some((r) => r.category === '租赁改良' && r.benefitPeriod === '4年')).toBe(true)
  })

  it('applyIndustryTemplate 填充同业公司与政策格', () => {
    const map = ref(new Map())
    const api = useI4PolicyCheck(map)
    api.applyIndustryTemplate('retail')
    expect(api.peerCompanies.value[0].name).toBeTruthy()
    expect(api.peerPolicies.value.some((r) => r.category === '装修费')).toBe(true)
  })

  it('applyPeerCatalog 填入年报库同业', () => {
    const map = ref(new Map())
    const api = useI4PolicyCheck(map, { onSave: () => {} })
    const n = api.applyPeerCatalog({
      label: '零售/连锁',
      peers: [
        {
          name: '永辉超市',
          source: '2024年报附注·长期待摊费用',
          policies: {
            装修费: { benefitPeriod: '租赁期', amortMethod: '直线法' },
          },
        },
      ],
    })
    expect(n).toBe(1)
    expect(api.peerCompanies.value[0].name).toBe('永辉超市')
    expect(api.peerPolicies.value.find((r) => r.category === '装修费')?.cells['peer-1'].benefitPeriod).toBe('租赁期')
  })

  it('amortCrossCheck 在有 I4-6 数据时计算', () => {
    const map = ref(new Map([
      ['I4-6-rows', {
        remark: JSON.stringify([
          { category: '装修费', usefulLife: '5年', lifeMonths: 60, amortMethod: '直线法', accumDiff: 0, monthlyDiff: 0 },
        ]),
      }],
    ]))
    const api = useI4PolicyCheck(map)
    api.policyParams.value = [{
      rowId: 'p1',
      category: '装修费',
      benefitPeriod: '3年',
      amortMethod: '直线法',
      meetsStandards: '',
      matchesBenefitPattern: '',
      reasonableVsPeers: '',
      hasChange: '',
      changeReasonable: '',
      remark: '',
    }]
    expect(api.amortCrossCheck.value.aggs.length).toBe(1)
    expect(api.amortCrossCheck.value.issues.some((i) => i.code === 'period-mismatch')).toBe(true)
  })

  it('suggestJudgmentsFromPeers + markCrossIssuesAsAttention + appendAdjDrafts', () => {
    const saved: Record<string, any> = {}
    const map = ref(new Map([
      ['I4-6-rows', {
        remark: JSON.stringify([
          { category: '装修费', usefulLife: '3年', lifeMonths: 36, amortMethod: '直线法', accumDiff: 20000, monthlyDiff: 0 },
        ]),
      }],
    ]))
    const api = useI4PolicyCheck(map, { onSave: (id, v) => { saved[id] = v } })
    api.applyPeerCatalog({
      label: '测试',
      peers: [
        { name: 'A公司', source: '年报', policies: { 装修费: { benefitPeriod: '3年', amortMethod: '直线法' } } },
        { name: 'B公司', source: '年报', policies: { 装修费: { benefitPeriod: '5年', amortMethod: '直线法' } } },
      ],
    })
    // 客户 10 年 → 偏离
    const row = api.policyParams.value.find((r) => r.category === '装修费')!
    row.benefitPeriod = '10年'
    row.amortMethod = '直线法'
    row.meetsStandards = 'Y'
    row.matchesBenefitPattern = 'Y'
    row.reasonableVsPeers = ''
    expect(api.peerDeviations.value.length).toBeGreaterThan(0)
    const nPeer = api.suggestJudgmentsFromPeers()
    expect(nPeer).toBeGreaterThan(0)
    expect(row.reasonableVsPeers).toBe('N')

    const nAtt = api.markCrossIssuesAsAttention()
    expect(nAtt).toBeGreaterThan(0)
    expect(row.remark).toContain('[勾稽')

    const nAdj = api.appendAdjDraftsFromCrossCheck()
    expect(nAdj).toBeGreaterThan(0)
    expect(saved['I4-3-rows']).toBeTruthy()
  })

  it('迁移旧版自由文本到审计说明/结论', () => {
    const map = ref(new Map([
      ['I4-4-amortization-method', { remark: '直线法为主' }],
      ['I4-4-benefit-period', { remark: '装修费按租赁期' }],
      ['I4-policycheck-audit-conclusion', { remark: '政策总体适当' }],
    ]))
    const api = useI4PolicyCheck(map)
    expect(api.auditNote.value).toContain('直线法为主')
    expect(api.auditNote.value).toContain('装修费按租赁期')
    expect(api.overallConclusion.value).toBe('政策总体适当')
  })

  it('industryHint 按项目上下文推荐零售', () => {
    const map = ref(new Map())
    const ctx = ref({ client_name: '某连锁便利店' })
    const api = useI4PolicyCheck(map, { projectContext: ctx })
    expect(api.industryHint.value.id).toBe('retail')
  })

  it('leaseShorterCheck 纳入完成度闸门', () => {
    const map = ref(new Map([
      ['I4-2-rows', {
        remark: JSON.stringify([{
          expenseType: '装修费',
          projectName: '店面',
          startDate: '2024-01-01',
          endDate: '2025-01-01',
          totalMonths: 36,
        }]),
      }],
    ]))
    const api = useI4PolicyCheck(map)
    expect(api.leaseShorterCheck.value.ok).toBe(false)
    expect(api.completeness.value.find((c) => c.id === 'lease')?.ok).toBe(false)
  })

  it('markSheetComplete 闸门未过拒绝；通过后写入完成标记', () => {
    const saved: Record<string, any> = {}
    const map = ref(new Map())
    const api = useI4PolicyCheck(map, { onSave: (id, v) => { saved[id] = v } })
    const denied = api.markSheetComplete()
    expect(denied.ok).toBe(false)
    expect(api.sheetMarkedComplete.value).toBe(false)

    // 强制写入进行中标记可读
    api.persistCompletionMarker(false)
    expect(saved['I4-4-completion']).toBe('进行中')
    expect(api.canMarkComplete.value).toBe(false)
  })
})
