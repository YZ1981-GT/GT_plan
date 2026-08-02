/**
 * m1K3KeyIsolation — M1 与 K3 推送同一章节子表键隔离守卫
 *
 * M1 应付股利浅合并推 K3 章节（§五、42 / §八、42），K3 自身也推该章节。
 * 两者推的 sub_table_data 键如果交集 → 同步互相覆盖（谁最后保存谁赢）。
 *
 * 🔴 当前设计：M1 **就是**推 K3 的 dividend/dividendOverdue 键（浅合并范式，
 * 两底稿共管同一张子表，最后保存覆盖）。与 H4→H2 工程物资 / H6→H1 清理同款。
 * 本守卫确认这一设计意图未被意外破坏：M1 只推 dividend 相关键，不侵入 K3 的其他表。
 */
import { describe, it, expect } from 'vitest'
import { M1_LISTED_SUBTABLES, M1_SOE_SUBTABLES } from '../m1NoteSectionMap'
import { K3_LISTED_SUBTABLE, K3_SOE_SUBTABLE } from '../k3NoteSectionMap'

describe('M1 vs K3 键隔离', () => {
  it('M1 上市推送的键集 ⊆ K3 dividend 族（不侵入 summary/interest/late）', () => {
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

  it('M1 国企推送的键集 ⊆ K3 dividend 族', () => {
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

  it('M1 键名与 K3 dividend 键逐字相同（确认浅合并意图）', () => {
    expect(M1_LISTED_SUBTABLES.dividend).toBe(K3_LISTED_SUBTABLE.dividend)
    expect(M1_LISTED_SUBTABLES.dividendOverdue).toBe(K3_LISTED_SUBTABLE.dividendOverdue)
    expect(M1_SOE_SUBTABLES.dividend).toBe(K3_SOE_SUBTABLE.dividend)
  })
})
