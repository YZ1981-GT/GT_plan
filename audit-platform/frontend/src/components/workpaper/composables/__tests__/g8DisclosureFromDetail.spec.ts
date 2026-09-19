/**
 * g8DisclosureFromDetail — 附注从 G8-2 带入 / 槽位溢出 / 指定原因
 */
import { describe, it, expect } from 'vitest'
import {
  packDisclosureSlots,
  buildG8DesignationNarrative,
  pullG8DisclosureFromDetail,
} from '../g8DisclosureFromDetail'
import type { ChecklistResponse } from '../useF1FormData'

function mapOf(entries: Record<string, Partial<ChecklistResponse>>) {
  const m = new Map<string, ChecklistResponse>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, conclusion: null, remark: null, ...v } as ChecklistResponse)
  }
  return m
}

describe('packDisclosureSlots', () => {
  it('不足槽位时补空行', () => {
    const { packed, overflowCount } = packDisclosureSlots(
      [{ label: '甲', closing: 100, prior: 50 }],
      3,
      ['closing', 'prior'],
    )
    expect(packed).toHaveLength(3)
    expect(packed[0].label).toBe('甲')
    expect(packed[1].label).toBe('')
    expect(overflowCount).toBe(0)
  })

  it('超额汇总为其他', () => {
    const items = [
      { label: 'A', closing: 300, prior: 1 },
      { label: 'B', closing: 200, prior: 2 },
      { label: 'C', closing: 100, prior: 3 },
      { label: 'D', closing: 50, prior: 4 },
    ]
    const { packed, overflowCount } = packDisclosureSlots(items, 3, ['closing', 'prior'])
    expect(packed).toHaveLength(3)
    expect(packed[0].label).toBe('A')
    expect(packed[1].label).toBe('B')
    expect(packed[2].label).toBe('其他')
    expect(packed[2].closing).toBe(150)
    expect(packed[2].prior).toBe(7)
    expect(overflowCount).toBe(2)
  })
})

describe('buildG8DesignationNarrative', () => {
  it('有原因时优先使用原文', () => {
    const text = buildG8DesignationNarrative([
      { investeeName: '甲公司', openingAdjusted: 0, closingAdjusted: 1, designationReason: '战略长期持有指定为 FVOCI', ociCurrentChange: 0, ociCumulativeChange: 0, ociToRetainedEarnings: 0, transferReason: '' },
    ])
    expect(text).toContain('战略长期持有')
  })

  it('无原因时生成模板句', () => {
    const text = buildG8DesignationNarrative([
      { investeeName: '乙公司', openingAdjusted: 0, closingAdjusted: 1, designationReason: '', ociCurrentChange: 0, ociCumulativeChange: 0, ociToRetainedEarnings: 0, transferReason: '' },
    ])
    expect(text).toContain('乙公司')
    expect(text).toContain('其他综合收益')
  })
})

describe('pullG8DisclosureFromDetail', () => {
  it('上市：带入余额与 OCI，标记 dividend 缺失', () => {
    const m = mapOf({
      'G8-detail-rows': {
        remark: JSON.stringify([
          {
            investeeName: '大额',
            openingAdjusted: 10,
            closingAdjusted: 1000,
            designationReason: '战略持有',
            ociCurrentChange: 50,
            ociCumulativeChange: 200,
            ociToRetainedEarnings: 0,
            transferReason: '',
          },
          {
            investeeName: '小额',
            openingAdjusted: 5,
            closingAdjusted: 100,
            designationReason: '',
            ociCurrentChange: 10,
            ociCumulativeChange: 20,
            ociToRetainedEarnings: 5,
            transferReason: '处置',
          },
        ]),
      },
    })
    const res = pullG8DisclosureFromDetail(m, 'listed')
    expect(res.sourceCount).toBe(2)
    expect(res.store.balanceRows[0].label).toBe('大额')
    expect(res.store.balanceRows[0].closing).toBe(1000)
    expect(res.store.balanceRows[0].prior).toBe(10)
    expect(res.store.ociRows?.[0].ociPeriod).toBe(50)
    expect(res.store.ociRows?.[1].transferToRE).toBe(5)
    expect(res.store.designationText).toContain('战略')
    expect(res.missingFields).toContain('dividend')
  })

  it('国企：明细 4 槽，超额进其他', () => {
    const rows = Array.from({ length: 6 }, (_, i) => ({
      investeeName: `公${i + 1}`,
      openingAdjusted: i,
      closingAdjusted: (6 - i) * 100,
      designationReason: '',
      ociCurrentChange: i,
      ociCumulativeChange: i * 2,
      ociToRetainedEarnings: 0,
      transferReason: '',
    }))
    const m = mapOf({ 'G8-detail-rows': { remark: JSON.stringify(rows) } })
    const res = pullG8DisclosureFromDetail(m, 'soe')
    expect(res.sourceCount).toBe(6)
    expect(res.overflowCount).toBeGreaterThan(0)
    expect(res.store.balanceRows).toHaveLength(3)
    expect(res.store.balanceRows[2].label).toBe('其他')
    expect(res.store.detailRows).toHaveLength(4)
    expect(res.store.detailRows?.[3].label).toBe('其他')
  })
})
