/**
 * useI1UsefulLifeCheck — I1-7 使用寿命检查单元测试
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useI1UsefulLifeCheck,
  calcRemainingYears,
  isIndefiniteRow,
  blankUsefulLifeRow,
} from '../useI1UsefulLifeCheck'

function makeMap(entries: Record<string, any>): Map<string, any> {
  const m = new Map<string, any>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, typeof v === 'string' ? { remark: v } : { remark: JSON.stringify(v) })
  }
  return m
}

describe('useI1UsefulLifeCheck', () => {
  it('剩余年限公式：寿命月/12 − 已用年限', () => {
    const row = blankUsefulLifeRow('软件')
    row.usefulLifeMonths = 120
    row.usedYears = 3
    expect(calcRemainingYears(row)).toBeCloseTo(7)
  })

  it('寿命不确定：usefulLifeMonths=0 或 isIndefinite=Y', () => {
    const a = blankUsefulLifeRow('A')
    a.usefulLifeMonths = 0
    a.isIndefinite = 'Y'
    expect(isIndefiniteRow(a)).toBe(true)
    expect(calcRemainingYears(a)).toBeNull()

    const b = blankUsefulLifeRow('B')
    b.usefulLifeMonths = 60
    b.isIndefinite = 'Y'
    expect(isIndefiniteRow(b)).toBe(true)
  })

  it('兼容旧数据：仅有 usefulLifeMonths/结论字段可加载', () => {
    const map = ref(makeMap({
      'I1-7-rows': [
        {
          rowId: 'r1',
          name: '旧专利',
          usefulLifeMonths: 60,
          usedYears: 1,
          lifeBasis: '合同',
          isChanged: '否',
          changeReason: '',
          conclusion: '合理',
        },
      ],
    }))
    const api = useI1UsefulLifeCheck({ allResponses: map })
    expect(api.rows.value).toHaveLength(1)
    expect(api.rows.value[0]!.name).toBe('旧专利')
    expect(api.rows.value[0]!.legalApplicable).toBe('')
    expect(api.rows.value[0]!.isIndefinite).toBe('N')
    expect(api.isIndefiniteRow(api.rows.value[0]!)).toBe(false)
  })

  it('标记不确定后自动进入询问表', () => {
    const saved: string[] = []
    const map = ref(makeMap({ 'I1-7-rows': [] }))
    const api = useI1UsefulLifeCheck({
      allResponses: map,
      onSave: (id) => saved.push(id),
    })
    const row = api.addRow('商标权')
    api.updateField(row.rowId, 'isIndefinite', 'Y')
    expect(row.usefulLifeMonths).toBe(0)
    expect(api.inquiryRows.value.some((q) => q.name === '商标权')).toBe(true)
    expect(api.indefiniteCount.value).toBe(1)
  })

  it('从 I1-2 带入名称/寿命/净值', () => {
    const map = ref(makeMap({
      'I1-2-rows': [
        { rowId: 'd1', name: '专利甲', usefulLifeMonths: 120, costEnd: 1000, accAmortEnd: 200, impairmentEnd: 0, netValue: 800 },
        { rowId: 'd2', name: '商誉类', usefulLifeMonths: 0, netValue: 5000 },
      ],
    }))
    const api = useI1UsefulLifeCheck({ allResponses: map })
    const r = api.seedFromDetail()
    expect(r.ok).toBe(true)
    expect(api.rows.value).toHaveLength(2)
    expect(api.rows.value.find((x) => x.name === '专利甲')!.netBookValue).toBe(800)
    expect(api.rows.value.find((x) => x.name === '商誉类')!.isIndefinite).toBe('Y')
    expect(api.inquiryRows.value.some((q) => q.name === '商誉类')).toBe(true)
  })

  it('编制校验：不确定项缺判断依据 / 询问未完成', () => {
    const map = ref(makeMap({}))
    const api = useI1UsefulLifeCheck({ allResponses: map })
    const row = api.addRow('数据资源')
    api.updateField(row.rowId, 'isIndefinite', 'Y')
    expect(api.prepValidation.value.ok).toBe(false)
    expect(api.prepValidation.value.messages.some((m) => m.includes('判断依据'))).toBe(true)

    api.updateField(row.rowId, 'indefiniteJudgmentBasis', '无法预见受益期限')
    const inq = api.inquiryRows.value.find((q) => q.name === '数据资源')!
    api.updateInquiryField(inq.rowId, 'identifiedFiniteFactors', 'N')
    api.updateInquiryField(inq.rowId, 'continuedOriginalUse', 'Y')
    expect(api.prepValidation.value.ok).toBe(true)
  })

  it('发布不确定清单', () => {
    const saved: Array<{ id: string; value: any }> = []
    const map = ref(makeMap({}))
    const api = useI1UsefulLifeCheck({
      allResponses: map,
      onSave: (id, value) => saved.push({ id, value }),
    })
    const row = api.addRow('特许经营权')
    api.updateField(row.rowId, 'isIndefinite', 'Y')
    api.updateField(row.rowId, 'indefiniteJudgmentBasis', '无明确到期日')
    api.publishIndefiniteList()
    const pub = saved.find((s) => s.id === 'I1-7-indefinite-list')
    expect(pub?.value.count).toBe(1)
    expect(pub?.value.assets[0].name).toBe('特许经营权')
  })
})
