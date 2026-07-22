/**
 * useH1Adjudication — H1-1 审定表单元测试
 * 覆盖：减值区块、净值=原值−折旧−减值、变动率≥30%、持久化、H1-3同步
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useH1Adjudication } from '../useH1Adjudication'

function makeMap(entries: Record<string, any> = {}) {
  const m = new Map<string, any>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, {
      item_id: k,
      conclusion: null,
      remark: typeof v === 'string' ? v : JSON.stringify(v),
    })
  }
  return m
}

describe('useH1Adjudication', () => {
  const wpId = ref('wp-1')
  const projectId = ref('proj-1')
  let saved: Record<string, any>
  let onSave: ReturnType<typeof vi.fn>

  beforeEach(() => {
    saved = {}
    onSave = vi.fn((id: string, val: any) => {
      saved[id] = val
    })
  })

  it('默认生成五类原值/折旧/减值行，净值含减值', async () => {
    const allResponses = ref(makeMap())
    const api = useH1Adjudication(wpId, projectId, allResponses as any, { onSave })
    await nextTick()

    expect(api.costRows.value).toHaveLength(5)
    expect(api.depRows.value).toHaveLength(5)
    expect(api.impairRows.value).toHaveLength(5)
    expect(api.costRows.value.map((r) => r.category)).toContain('房屋及建筑物')
    expect(api.costRows.value.map((r) => r.category)).toContain('其他设备')

    // 填原值/折旧/减值后净值正确
    api.updateCell('cost', api.costRows.value[0].rowId, 'unadjusted', 1000)
    api.updateCell('dep', api.depRows.value[0].rowId, 'unadjusted', 300)
    api.updateCell('impair', api.impairRows.value[0].rowId, 'unadjusted', 50)
    expect(api.netValueAudited.value).toBe(650)
  })

  it('三角勾稽：原值期末=期初+借−贷；备抵期末=期初+贷−借', async () => {
    const allResponses = ref(makeMap())
    const api = useH1Adjudication(wpId, projectId, allResponses as any, { onSave })
    await nextTick()

    const c = api.costRows.value[0]
    api.updateCell('cost', c.rowId, 'beginBalance', 100)
    api.updateCell('cost', c.rowId, 'debit', 40)
    api.updateCell('cost', c.rowId, 'credit', 10)
    expect(c.endBalance).toBe(130)

    const d = api.depRows.value[0]
    api.updateCell('dep', d.rowId, 'beginBalance', 20)
    api.updateCell('dep', d.rowId, 'credit', 5) // 计提
    api.updateCell('dep', d.rowId, 'debit', 2) // 转销
    expect(d.endBalance).toBe(23)

    expect(api.reconciliationResults.value.every((r) => r.isBalanced)).toBe(true)
  })

  it('净值变动率≥30% 标记 isSignificant', async () => {
    const allResponses = ref(makeMap())
    const api = useH1Adjudication(wpId, projectId, allResponses as any, { onSave })
    await nextTick()

    const c = api.costRows.value[0]
    api.updateCell('cost', c.rowId, 'beginBalance', 100)
    api.updateCell('cost', c.rowId, 'unadjusted', 150) // 审定150，期初净≈100 → +50%
    const net = api.netRows.value.find((r) => r.category === c.category)
    expect(net?.changeRate).toBeCloseTo(50, 5)
    expect(net?.isSignificant).toBe(true)
    expect(api.significantNetChanges.value.length).toBeGreaterThanOrEqual(1)
  })

  it('持久化含 impair-rows 与 qualitative-notes', async () => {
    const allResponses = ref(makeMap())
    const api = useH1Adjudication(wpId, projectId, allResponses as any, { onSave })
    await nextTick()

    api.updateCell('impair', api.impairRows.value[0].rowId, 'unadjusted', 12)
    expect(onSave).toHaveBeenCalledWith('H1-1-impair-rows', expect.any(Array))

    api.saveQualitativeNotes({ fluctuation: '机器设备购置增加' })
    expect(saved['H1-1-qualitative-notes']).toMatchObject({
      fluctuation: '机器设备购置增加',
    })
  })

  it('旧分类「电子设备」迁移为「办公设备」', async () => {
    const allResponses = ref(
      makeMap({
        'H1-1-cost-rows': [
          {
            rowId: 'r1',
            category: '电子设备',
            beginBalance: 1,
            debit: 0,
            credit: 0,
            unadjusted: 1,
            aje: 0,
            rje: 0,
          },
        ],
      }),
    )
    const api = useH1Adjudication(wpId, projectId, allResponses as any, { onSave })
    await nextTick()
    expect(api.costRows.value[0].category).toBe('办公设备')
  })

  it('旧分类「其他」迁移为「其他设备」', async () => {
    const allResponses = ref(
      makeMap({
        'H1-1-cost-rows': [
          {
            rowId: 'r1',
            category: '其他',
            beginBalance: 1,
            debit: 0,
            credit: 0,
            unadjusted: 1,
            aje: 0,
            rje: 0,
          },
        ],
      }),
    )
    const api = useH1Adjudication(wpId, projectId, allResponses as any, { onSave })
    await nextTick()
    expect(api.costRows.value[0].category).toBe('其他设备')
  })

  it('syncAdjustmentsFromH3 按科目码分摊到分类而非首行', async () => {
    const allResponses = ref(
      makeMap({
        'H1-3-rows': [
          {
            accountCode: '1601.02',
            accountName: '机器设备',
            category: '账项调整',
            debitAmount: 800,
            creditAmount: 0,
          },
          {
            accountCode: '1602.03',
            accountName: '运输设备累计折旧',
            category: '账项调整',
            debitAmount: 0,
            creditAmount: 120,
          },
        ],
      }),
    )
    const api = useH1Adjudication(wpId, projectId, allResponses as any, { onSave })
    await nextTick()

    const r = api.syncAdjustmentsFromH3()
    expect(r.applied).toBe(true)
    const machine = api.costRows.value.find((x) => x.category === '机器设备')!
    const transportDep = api.depRows.value.find((x) => x.category === '运输设备')!
    expect(machine.aje).toBe(800)
    expect(transportDep.aje).toBe(120)
    // 首行房屋不应被误写入合计
    const building = api.costRows.value.find((x) => x.category === '房屋及建筑物')!
    expect(building.aje).toBe(0)
  })

  it('applyCategoryPrefill 从 TB 预填未审数', async () => {
    const allResponses = ref(makeMap())
    const categoryPrefill = ref({
      categories: [
        {
          category: '房屋及建筑物',
          cost: { begin: 100, debit: 10, credit: 0, end: 110, unadjusted: 110 },
          dep: { begin: 20, debit: 0, credit: 5, end: 25, unadjusted: 25 },
          impair: { begin: 0, debit: 0, credit: 0, end: 0, unadjusted: 0 },
        },
      ],
      totals: { cost1601: 110, dep1602: 25, impair1603: 0 },
    })
    const api = useH1Adjudication(wpId, projectId, allResponses as any, {
      onSave,
      categoryPrefill: categoryPrefill as any,
    })
    await nextTick()
    const r = api.applyCategoryPrefill(true)
    expect(r.applied).toBe(true)
    const b = api.costRows.value.find((x) => x.category === '房屋及建筑物')!
    expect(b.unadjusted).toBe(110)
    expect(b.beginBalance).toBe(100)
    expect(api.depRows.value.find((x) => x.category === '房屋及建筑物')!.unadjusted).toBe(25)
  })

  it('setChangeExplanation 写入 H1-6-change-explanations 实现双向联动', async () => {
    const allResponses = ref(makeMap())
    const api = useH1Adjudication(wpId, projectId, allResponses as any, { onSave })
    await nextTick()
    api.setChangeExplanation('机器设备', '本年购置产线')
    expect(saved['H1-6-change-explanations']).toMatchObject({
      机器设备: '本年购置产线',
    })
  })

  it('publishAdjudicated 回写含减值并发布事件', async () => {
    const allResponses = ref(makeMap())
    const onWritebackTB = vi.fn(async () => {})
    const onPublishEvent = vi.fn()
    const api = useH1Adjudication(wpId, projectId, allResponses as any, {
      onSave,
      onWritebackTB,
      onPublishEvent,
    })
    await nextTick()
    api.updateCell('cost', api.costRows.value[0].rowId, 'unadjusted', 1000)
    api.updateCell('impair', api.impairRows.value[0].rowId, 'unadjusted', 80)

    await api.publishAdjudicated()
    expect(onWritebackTB).toHaveBeenCalledWith(1000, 0, 80)
    expect(onPublishEvent).toHaveBeenCalledWith(
      'substantive:adjudicated',
      expect.objectContaining({
        account_codes: ['1601', '1602', '1603'],
        impair_audited: 80,
        net_value: 920,
      }),
    )
  })
})
