/**
 * 五、42 / 八、42 的 L2、M1、K3 表级 owner 守卫。
 *
 * 三个底稿仅写各自独占明细表；共享主表由服务端从三家明细合计派生。
 * 模板常量中的同名键不代表 K3 仍拥有股利/利息表。
 */
import { describe, it, expect } from 'vitest'
import { L2_TABLE_SCOPE } from '../l2NoteSectionMap'
import { M1_LISTED_SUBTABLES, M1_SOE_SUBTABLES, M1_TABLE_SCOPE } from '../m1NoteSectionMap'
import { K3_LISTED_SUBTABLE, K3_SOE_SUBTABLE, K3_TABLE_SCOPE } from '../k3NoteSectionMap'

describe('M1 vs K3 键隔离', () => {
  it('M1 上市键逐字对应模板 dividend 族（不侵入 summary/interest/nature）', () => {
    const m1Keys = new Set(Object.values(M1_LISTED_SUBTABLES))
    const k3DividendKeys = new Set([K3_LISTED_SUBTABLE.dividend, K3_LISTED_SUBTABLE.dividendOverdue])
    const k3NonDividendKeys = new Set([
      K3_LISTED_SUBTABLE.summary,
      K3_LISTED_SUBTABLE.interest,
    ])

    // M1 推的所有键必须在 K3 dividend 族内
    for (const key of m1Keys) {
      expect(k3DividendKeys.has(key), `M1 键 "${key}" 不在 K3 dividend 族`).toBe(true)
    }

    // M1 不得推 K3 非 dividend 表
    for (const key of m1Keys) {
      expect(k3NonDividendKeys.has(key), `M1 键 "${key}" 侵入了 K3 非 dividend 表`).toBe(false)
    }
  })

  it('M1 国企键逐字对应模板 dividend 族', () => {
    const m1Keys = new Set(Object.values(M1_SOE_SUBTABLES))
    const k3DividendKeys = new Set([K3_SOE_SUBTABLE.dividend])
    const k3NonDividendKeys = new Set([
      K3_SOE_SUBTABLE.summary,
      K3_SOE_SUBTABLE.interest,
    ])

    for (const key of m1Keys) {
      expect(k3DividendKeys.has(key), `M1 soe 键 "${key}" 不在 K3 dividend 族`).toBe(true)
    }
    for (const key of m1Keys) {
      expect(k3NonDividendKeys.has(key), `M1 soe 键 "${key}" 侵入了 K3 非 dividend 表`).toBe(false)
    }
  })

  it('同一模板键不等于共享写权，三家 owner scope 两两不交且均不含主表', () => {
    expect(M1_LISTED_SUBTABLES.dividend).toBe(K3_LISTED_SUBTABLE.dividend)
    expect(M1_LISTED_SUBTABLES.dividendOverdue).toBe(K3_LISTED_SUBTABLE.dividendOverdue)
    expect(M1_SOE_SUBTABLES.dividend).toBe(K3_SOE_SUBTABLE.dividend)
    for (const variant of ['listed', 'soe'] as const) {
      const scopes = [
        new Set<string>(L2_TABLE_SCOPE[variant]),
        new Set<string>(M1_TABLE_SCOPE[variant]),
        new Set<string>(K3_TABLE_SCOPE[variant]),
      ]
      for (let left = 0; left < scopes.length; left += 1) {
        for (let right = left + 1; right < scopes.length; right += 1) {
          expect([...scopes[left]].filter((key) => scopes[right].has(key))).toEqual([])
        }
      }
      expect(scopes.some((scope) => scope.has(variant === 'listed' ? K3_LISTED_SUBTABLE.summary : K3_SOE_SUBTABLE.summary))).toBe(false)
    }
  })
})
