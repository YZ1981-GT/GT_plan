/**
 * useH8Detail 单元测试 — H8-2 源模板公式链 + 旧数据迁移 + 兼容别名
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  createEmptyH8DetailRow,
  normalizeH8DetailRow,
  recalcH8DetailRow,
  useH8Detail,
} from '../useH8Detail'

describe('recalcH8DetailRow — 对齐源模板公式', () => {
  it('原值：期初+三项增−三项减=期末；审定=未审+调整', () => {
    const row = createEmptyH8DetailRow({
      costBeginUnadj: 1000,
      costIncLease: 200,
      costIncReval: 50,
      costIncOther: 30,
      costDecSublease: 40,
      costDecDisposal: 20,
      costDecOther: 10,
      costOpenAdj: 5,
      costAjeIncLease: 15,
      costAjeDecDisposal: 8,
    })
    // 期末未审 = 1000+200+50+30 − 40−20−10 = 1210
    expect(row.costEndUnadj).toBe(1210)
    // 审定期初 = 1000+5 = 1005
    expect(row.costBeginAud).toBe(1005)
    // 审定增 = 280+15 = 295
    expect(row.costIncAud).toBe(295)
    // 审定减 = 70+8 = 78
    expect(row.costDecAud).toBe(78)
    // 审定期末 = 1005+295−78 = 1222
    expect(row.costEndAud).toBe(1222)
  })

  it('累计折旧备抵：期初+计提+其他增−三项减', () => {
    const row = createEmptyH8DetailRow({
      depBeginUnadj: 100,
      depProvUnadj: 40,
      depOtherIncUnadj: 5,
      depDecSublease: 10,
      depDecDisposal: 8,
      depOtherDecUnadj: 2,
      depOpenAdj: 3,
      depAjeProv: 4,
    })
    expect(row.depEndUnadj).toBe(125) // 100+40+5−10−8−2
    expect(row.depBeginAud).toBe(103)
    expect(row.depIncAud).toBe(49) // 40+5+4
    expect(row.depDecAud).toBe(20)
    expect(row.depEndAud).toBe(132) // 103+49−20
  })

  it('净值 = 原值 − 折旧 − 减值；兼容别名同步', () => {
    const row = createEmptyH8DetailRow({
      costBeginUnadj: 1000,
      depBeginUnadj: 200,
      depProvUnadj: 50,
      impairBeginUnadj: 30,
      impairProvUnadj: 10,
      h9InitialAmount: 800,
      directCost: 20,
      incentive: 5,
    })
    expect(row.costEndUnadj).toBe(1000)
    expect(row.depEndUnadj).toBe(250)
    expect(row.impairEndUnadj).toBe(40)
    expect(row.netEndUnadj).toBe(710) // 1000-250-40
    expect(row.netEndAud).toBe(710)
    expect(row.initialAmount).toBe(815) // CAS21 优先
    expect(row.accDepBegin).toBe(200)
    expect(row.depCurrentPeriod).toBe(50)
    expect(row.accDepEnd).toBe(250)
    expect(row.netValue).toBe(710)
  })

  it('CAS21 未填时入账值回退原值审定期末', () => {
    const row = createEmptyH8DetailRow({
      costBeginUnadj: 500,
      costIncLease: 100,
    })
    expect(row.initialAmount).toBe(600)
  })
})

describe('normalizeH8DetailRow — 旧数据迁移', () => {
  it('旧精简字段迁入原值期初与折旧未审', () => {
    const row = normalizeH8DetailRow({
      contractNo: 'ZL-1',
      assetName: '办公楼',
      leaseType: '房屋及建筑物',
      h9InitialAmount: 100,
      directCost: 10,
      incentive: 5,
      initialAmount: 105,
      accDepBegin: 20,
      depCurrentPeriod: 8,
      modificationAmount: 1,
    })
    expect(row.category).toBe('房屋及建筑物')
    expect(row.costBeginUnadj).toBe(105)
    expect(row.costEndAud).toBe(105)
    expect(row.depBeginUnadj).toBe(20)
    expect(row.depProvUnadj).toBe(8)
    expect(row.depEndAud).toBe(28)
    expect(row.netValue).toBe(77) // 105-28
    expect(row.initialAmount).toBe(105)
  })

  it('新字段优先，不被旧别名覆盖', () => {
    const row = normalizeH8DetailRow({
      contractNo: 'ZL-2',
      costBeginUnadj: 1000,
      costIncLease: 100,
      depBeginUnadj: 50,
      depProvUnadj: 10,
      accDepBegin: 999, // 应忽略
      depCurrentPeriod: 999,
    })
    expect(row.costEndUnadj).toBe(1100)
    expect(row.depBeginUnadj).toBe(50)
    expect(row.depProvUnadj).toBe(10)
  })
})

describe('useH8Detail composable', () => {
  it('增删改持久化并重算', () => {
    const saved: { id: string; value: any }[] = []
    const allResponses = ref(new Map())
    const api = useH8Detail({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      onSave: (id, value) => saved.push({ id, value }),
    })

    api.addRow('C-1')
    expect(api.rows.value).toHaveLength(1)
    expect(saved.some(s => s.id === 'H8-2-rows')).toBe(true)

    const id = api.rows.value[0].rowId
    api.updateCell(id, 'h9InitialAmount', 1000)
    api.updateCell(id, 'directCost', 50)
    api.updateCell(id, 'incentive', 30)
    expect(api.rows.value[0].initialAmount).toBe(1020)

    api.updateCell(id, 'costBeginUnadj', 1020)
    api.updateCell(id, 'depProvUnadj', 100)
    expect(api.rows.value[0].netEndAud).toBe(920)

    api.deleteRow(id)
    expect(api.rows.value).toHaveLength(0)
  })

  it('与 H8-1 勾稽：一致 / 差额告警', () => {
    const map = new Map<string, any>([
      ['H8-1-cost-audited-total', { remark: '1100' }],
      ['H8-1-dep-audited-total', { remark: '100' }],
      ['H8-1-impair-audited-total', { remark: '0' }],
      ['H8-1-net-audited', { remark: '1000' }],
      ['H8-2-rows', {
        remark: JSON.stringify([{
          contractNo: 'C-1',
          costBeginUnadj: 1100,
          depProvUnadj: 100,
        }]),
      }],
    ])
    const api = useH8Detail({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: ref(map),
    })
    expect(api.rows.value).toHaveLength(1)
    expect(api.crossValidation.value.costTotal).toBe(1100)
    expect(api.crossValidation.value.depTotal).toBe(100)
    expect(api.crossValidation.value.isConsistent).toBe(true)
    expect(api.crossValidation.value.hasCostWarning).toBe(false)

    api.updateCell(api.rows.value[0].rowId, 'costIncLease', 50)
    expect(api.crossValidation.value.hasCostWarning).toBe(true)
    expect(api.crossValidation.value.costDiff).toBe(50)
  })

  it('从 H8-8 回填本期计提 + 入账值填本期租入', () => {
    const map = new Map<string, any>([
      ['H8-8-dep-rows', {
        remark: JSON.stringify([{
          contractNo: 'ZL-9',
          periodDep: 12000,
          originalCost: 240000,
          bookAccDepEnd: 36000,
        }]),
      }],
    ])
    const saved: any[] = []
    const api = useH8Detail({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: ref(map),
      onSave: (id, v) => saved.push({ id, v }),
    })
    api.addRow('ZL-9')
    const id = api.rows.value[0].rowId
    api.updateCell(id, 'h9InitialAmount', 200000)
    api.updateCell(id, 'directCost', 0)
    api.updateCell(id, 'incentive', 0)
    // 先清空因旧迁移可能写入的 costBegin（addRow 时空行）
    // seed：原值全空时填本期租入
    const seed = api.seedCostIncFromInitial()
    expect(seed.updated).toBe(1)
    expect(api.rows.value[0].costIncLease).toBe(200000)

    const pull = api.pullDepFromH88()
    expect(pull.updated).toBe(1)
    expect(api.rows.value[0].depProvUnadj).toBe(12000)
  })

  it('短期候选：租赁期≤12', () => {
    const api = useH8Detail({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: ref(new Map()),
      onSave: () => {},
    })
    api.addRow('S-1')
    api.updateCell(api.rows.value[0].rowId, 'leaseTermMonths', 12)
    expect(api.shortTermCandidates.value).toHaveLength(1)
    api.updateCell(api.rows.value[0].rowId, 'leaseTermMonths', 24)
    expect(api.shortTermCandidates.value).toHaveLength(0)
  })
})

describe('recalc idempotent', () => {
  it('多次 recalc 结果稳定', () => {
    const row = createEmptyH8DetailRow({
      costBeginUnadj: 10,
      costIncReval: 5,
      depProvUnadj: 2,
      impairProvUnadj: 1,
    })
    const a = { ...row }
    recalcH8DetailRow(row)
    expect(row.costEndAud).toBe(a.costEndAud)
    expect(row.netEndAud).toBe(a.netEndAud)
  })
})
