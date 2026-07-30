/**
 * K2 披露引擎单测
 *
 * spec: .kiro/specs/k2-other-current-assets-disclosure-alignment/ Task 5.4
 */
import { describe, expect, it } from 'vitest'
import { K2_CONTRACT_COST_ROWS } from '../k2NoteSectionMap'
import {
  K2_TOLERANCE,
  checkK2Consistency,
  contractCostRowTotal,
  k2ConsistencySummary,
  recalcContractCost,
  sumMainRows,
} from '../useK2DisclosureEngine'

describe('sumMainRows', () => {
  it('逐列求和，非数字视为 0', () => {
    expect(
      sumMainRows([
        { label: 'a', endAmount: 10, priorAmount: 4 },
        { label: 'b', endAmount: 2.5, priorAmount: Number.NaN },
      ]),
    ).toEqual({ end: 12.5, prior: 4 })
  })

  it('空数组返回零', () => {
    expect(sumMainRows([])).toEqual({ end: 0, prior: 0 })
  })
})

describe('recalcContractCost', () => {
  const idx = (label: string) => K2_CONTRACT_COST_ROWS.indexOf(label)

  it('期末余额 = 期初 + 增加 − 摊销 − 减值（逐类别）', () => {
    const out = recalcContractCost(
      [
        [100, 50],
        [30, 10],
        [20, 5],
        [5, 1],
        [999, 999], // 旧的期末值应被覆盖
      ],
      2,
    )
    expect(out[idx('期末余额')]).toEqual([100 + 30 - 20 - 5, 50 + 10 - 5 - 1])
  })

  it('补齐缺失单元格为 0，行数固定为模板行数', () => {
    const out = recalcContractCost([], 3)
    expect(out).toHaveLength(K2_CONTRACT_COST_ROWS.length)
    for (const row of out) expect(row).toEqual([0, 0, 0])
  })

  it('不修改入参', () => {
    const input = [[1], [0], [0], [0], [0]]
    const snapshot = JSON.stringify(input)
    recalcContractCost(input, 1)
    expect(JSON.stringify(input)).toBe(snapshot)
  })

  it('catCount 为 0 时兜底为 1 列', () => {
    expect(recalcContractCost([], 0)[0]).toEqual([0])
  })
})

describe('contractCostRowTotal', () => {
  it('按类别数求和，越界取 0', () => {
    expect(contractCostRowTotal([[1, 2]], 0, 3)).toBe(3)
  })
})

describe('checkK2Consistency', () => {
  const mainRows = [
    { label: '进项税额', endAmount: 100, priorAmount: 60 },
    { label: '合同取得成本', endAmount: 105, priorAmount: 100 },
  ]

  it('审定数一致 → ok；不一致 → error', () => {
    const ok = checkK2Consistency({ variant: 'soe', mainRows, auditedEnd: 205 })
    expect(ok[0].level).toBe('ok')

    const bad = checkK2Consistency({ variant: 'soe', mainRows, auditedEnd: 200 })
    expect(bad[0].level).toBe('error')
    expect(bad[0].diff).toBe(5)
  })

  it('容差 0.01 元内视为通过', () => {
    const items = checkK2Consistency({ variant: 'soe', mainRows, auditedEnd: 205 + K2_TOLERANCE })
    expect(items[0].level).toBe('ok')
  })

  it('审定数缺失 → 跳过该项（不制造假阳性）', () => {
    expect(checkK2Consistency({ variant: 'soe', mainRows })).toEqual([])
  })

  it('国企末列名用「期初余额」，上市用「上年年末余额」', () => {
    const soe = checkK2Consistency({ variant: 'soe', mainRows, auditedPrior: 1 })
    const listed = checkK2Consistency({ variant: 'listed', mainRows, auditedPrior: 1 })
    expect(soe[0].label).toContain('期初余额')
    expect(listed[0].label).toContain('上年年末余额')
  })

  it('上市启用合同取得成本 → 追加公式校验与两表口径校验', () => {
    const cells = recalcContractCost(
      [
        [100],
        [30],
        [20],
        [5],
        [0],
      ],
      1,
    )
    const items = checkK2Consistency({
      variant: 'listed',
      mainRows,
      contractCost: { enabled: true, categories: ['佣金支出'], cells },
    })
    const formula = items.find(i => i.label === '合同取得成本期末余额')
    expect(formula?.level).toBe('ok')

    const cross = items.find(i => i.label.includes('②表期末余额'))
    expect(cross?.left).toBe(105)
    expect(cross?.right).toBe(105)
    expect(cross?.level).toBe('ok')
  })

  it('合同取得成本关闭 → 不追加该组校验', () => {
    const items = checkK2Consistency({
      variant: 'listed',
      mainRows,
      auditedEnd: 205,
      contractCost: { enabled: false, categories: ['佣金支出'], cells: [] },
    })
    expect(items.map(i => i.label)).toEqual(['明细表合计期末 = 审定数'])
  })
})

describe('k2ConsistencySummary', () => {
  it('error 优先于 warn', () => {
    expect(
      k2ConsistencySummary([
        { label: 'a', rule: '', left: 0, right: 0, diff: 0, level: 'ok' },
        { label: 'b', rule: '', left: 1, right: 0, diff: 1, level: 'warn' },
        { label: 'c', rule: '', left: 1, right: 0, diff: 1, level: 'error' },
      ]),
    ).toEqual({ total: 3, failed: 2, level: 'error' })
  })

  it('全通过 → ok', () => {
    expect(k2ConsistencySummary([])).toEqual({ total: 0, failed: 0, level: 'ok' })
  })
})
