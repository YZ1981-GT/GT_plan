import { describe, expect, it } from 'vitest'
import {
  buildG10DetailRowsFromAdjudication,
  pullG10DetailFromAdjudicationResponses,
} from '../g10DetailFromAdjudication'
import { G10_ADJ_ROWS_KEY } from '../g10AdjStorage'
import { enrichG10DetailRow } from '../useG10Detail'

describe('g10DetailFromAdjudication', () => {
  it('从 G10-1 book/init/fv 分项生成明细骨架行', () => {
    const store: Record<string, { openingUnadjusted?: number; closingUnadjusted?: number }> = {
      init_trading_bond: { openingUnadjusted: 80, closingUnadjusted: 90 },
      fv_trading_bond: { openingUnadjusted: 20, closingUnadjusted: 25 },
      book_trading_bond: { openingUnadjusted: 100, closingUnadjusted: 115 },
    }
    const result = buildG10DetailRowsFromAdjudication(
      store,
      [],
      () => 'row-1',
    )
    expect(result.filled).toBe(1)
    expect(result.added).toBe(1)
    // 🔴 C-7：`liabilityType` 已移除（模板无此列）⇒ 分类判别只剩 A 列 `liabilityCategory`
    //    与 B 列 `liabilityName`（名称取 G10-1 分项的 defaultName）。
    expect(result.rows[0].liabilityName).toBe('发行的交易性债券')
    expect(result.rows[0].liabilityCategory).toBe('交易类')
    expect(result.rows[0]).not.toHaveProperty('liabilityType')
    expect(result.rows[0].openingFairValue).toBe(100)
    // M = K + L；K = C + H = 80 + 10 = 90；L = D + I + J = 20 + 5 + 0 = 25 ⇒ 115
    expect(result.rows[0].closingFairValue).toBe(115)
    expect(result.rows[0].openingInitialAmount).toBe(80)
    expect(result.rows[0].movementInitialAmount).toBe(10)
  })

  it('fill-empty 模式更新空白同名行', () => {
    const store = {
      book_derivative_liability: { openingUnadjusted: 50, closingUnadjusted: 60 },
      init_derivative_liability: { openingUnadjusted: 50, closingUnadjusted: 60 },
      fv_derivative_liability: { openingUnadjusted: 0, closingUnadjusted: 0 },
    }
    const existing = [
      // 🔴 C-7：匹配键从「类型 + 类别」改为「类别 + 名称」（模板 A + B 两个受管列）
      enrichG10DetailRow({
        rowId: 'd1',
        liabilityCategory: '交易类',
        liabilityName: '衍生金融负债',
      }, 1),
    ]
    const result = buildG10DetailRowsFromAdjudication(store, existing, () => 'row-x', 'fill-empty')
    expect(result.updated).toBe(1)
    expect(result.added).toBe(0)
    expect(result.rows[0].closingFairValue).toBe(60)
    expect(result.rows[0].liabilityName).toContain('衍生')
  })

  it('pullG10DetailFromAdjudicationResponses 读取 responses', () => {
    const responses = new Map<string, any>([
      [G10_ADJ_ROWS_KEY, {
        remark: JSON.stringify({
          book_other: { openingUnadjusted: 10, closingUnadjusted: 12 },
          init_other: { openingUnadjusted: 10, closingUnadjusted: 12 },
          fv_other: { openingUnadjusted: 0, closingUnadjusted: 0 },
        }),
      }],
    ])
    const result = pullG10DetailFromAdjudicationResponses(responses, [], () => 'new-1')
    expect(result.filled).toBe(1)
    expect(result.rows[0].liabilityCategory).toBe('交易类')
  })
})
