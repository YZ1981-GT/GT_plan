/**
 * useH2CrossSheet — 披露取数 / 增减来源口径单元测试
 * 验证：H2-1 无增减列时，disc_increase/decrease/transfer 取自 H2-2
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useH2CrossSheet } from '../useH2CrossSheet'

function makeMap(entries: Record<string, unknown>) {
  const m = new Map<string, { item_id: string; conclusion: null; remark: string }>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, {
      item_id: k,
      conclusion: null,
      remark: typeof v === 'string' ? v : JSON.stringify(v),
    })
  }
  return m
}

describe('useH2CrossSheet disclosureAutoFill', () => {
  it('增减/转固取自 H2-2，审定取自 H2-1 xlsx 字段；利息按分支', () => {
    const allResponses = ref(
      makeMap({
        'H2-1-rows': [
          {
            rowId: 'a1',
            name: '厂房',
            beginUnadjusted: 100,
            endUnadjusted: 180,
            endAudited: 200,
          },
        ],
        'H2-2-rows': [
          {
            rowId: 'd1',
            name: '厂房',
            cipBegin: 100,
            increaseMaterial: 50,
            increaseLabor: 30,
            increaseTotal: 80,
            decrease: 10,
            transferAmount: 20,
            cipEnd: 150,
            endAudited: 200,
          },
        ],
        'H2-interest-cap-branch': 'withBorrow',
        'H2-10-cap-result': { totalCap: 999, branch: 'noBorrow' },
        'H2-11-cap-result': { totalCap: 42, branch: 'withBorrow' },
      }),
    )

    const { disclosureAutoFill } = useH2CrossSheet(allResponses as any)
    const d = disclosureAutoFill.value

    expect(d.disc_cip_begin).toBe(100)
    expect(d.disc_cip_end).toBe(180)
    expect(d.disc_audited).toBe(200)
    expect(d.disc_increase).toBe(80)
    expect(d.disc_decrease).toBe(10)
    expect(d.disc_transfer).toBe(20)
    expect(d.disc_project_count).toBe(1)
    expect(d.disc_interest_cap).toBe(42)
  })

  it('忽略 H2-1 旧增减字段，仍以 H2-2 为准', () => {
    const allResponses = ref(
      makeMap({
        'H2-1-rows': [
          {
            name: '旧数据',
            beginUnadjusted: 1,
            endUnadjusted: 1,
            endAudited: 1,
            increase: 999,
            decrease: 888,
            transfer: 777,
          },
        ],
        'H2-2-rows': [
          {
            name: '旧数据',
            increaseTotal: 5,
            decrease: 2,
            transferAmount: 3,
            cipEnd: 1,
            endAudited: 1,
          },
        ],
      }),
    )

    const { disclosureAutoFill } = useH2CrossSheet(allResponses as any)
    expect(disclosureAutoFill.value.disc_increase).toBe(5)
    expect(disclosureAutoFill.value.disc_decrease).toBe(2)
    expect(disclosureAutoFill.value.disc_transfer).toBe(3)
  })
})
