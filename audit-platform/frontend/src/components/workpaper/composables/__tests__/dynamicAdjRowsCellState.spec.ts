/**
 * Task 13：逐格四态覆盖状态机 resolveCellState 穷举判据（P11/P12）。
 *
 * spec: d4-html-to-oo-store-contract-alignment · Task 13
 * Requirements 6.1, 6.2 · Property 11（四态穷举封闭）/ Property 12（上游变化不误判覆盖）
 *
 * 判据按「两个布尔量 × 2」穷举驱动，不逐场景手写——手写必漏 S4（唯一会静默丢数据的态）。
 * P12 是反证式：只改 derived 不动 stored/snap，覆盖标记数必须为 0（钉「stored≠derived 判覆盖」的错法）。
 */
import { describe, it, expect } from 'vitest'
import {
  resolveCellState,
  displayValueForCellState,
  type DerivedCellState,
} from '../shared/dynamicAdjudicationRows'

describe('P11：resolveCellState 四态穷举封闭', () => {
  // 用「两个布尔量」构造四组代表值：overridden = stored≠snap，upstreamChanged = snap≠derived。
  // 取一组基准 snap=100，用是否偏离表达两个维度。
  const cases: Array<{
    name: string
    stored: number | null
    snap: number | null
    derived: number | null
    expect: DerivedCellState
  }> = [
    { name: 'S1 纯派生', stored: 100, snap: 100, derived: 100, expect: 'S1' },
    { name: 'S2 覆盖上游未变', stored: 150, snap: 100, derived: 100, expect: 'S2' },
    { name: 'S3 无覆盖上游变了', stored: 100, snap: 100, derived: 200, expect: 'S3' },
    { name: 'S4 覆盖且上游变了', stored: 150, snap: 100, derived: 200, expect: 'S4' },
  ]

  it.each(cases)('$name → $expect', ({ stored, snap, derived, expect: exp }) => {
    expect(resolveCellState(stored, snap, derived)).toBe(exp)
  })

  it('输出域恰为 {S1,S2,S3,S4} —— 穷举两个布尔量无第五态', () => {
    const seen = new Set<DerivedCellState>()
    // 两个布尔量各 true/false → 4 组，每组用一对满足/不满足容差的值构造。
    for (const overridden of [false, true]) {
      for (const changed of [false, true]) {
        const snap = 100
        const stored = overridden ? 150 : 100
        const derived = changed ? 200 : 100
        seen.add(resolveCellState(stored, snap, derived))
      }
    }
    expect([...seen].sort()).toEqual(['S1', 'S2', 'S3', 'S4'])
  })

  it('容差内的微小差异不算覆盖/变化（表示差异不误判）', () => {
    // JSON/openpyxl 往返的表示差异（153431246.16 vs .160000001）不得判成 S2/S3。
    expect(resolveCellState(153431246.16, 153431246.160000001, 153431246.16)).toBe('S1')
  })

  it('null 语义：都无值=S1；一方 null 一方有值=不等', () => {
    expect(resolveCellState(null, null, null)).toBe('S1')
    // stored 有值 snap null ⇒ overridden；snap null derived null ⇒ 不变 ⇒ S2
    expect(resolveCellState(5, null, null)).toBe('S2')
    // stored=snap=null（未覆盖），derived 出现新值 ⇒ upstreamChanged ⇒ S3
    expect(resolveCellState(null, null, 5)).toBe('S3')
  })
})

describe('P12：上游变化后纯派生格不得被标成人工覆盖（反证式）', () => {
  it('只改 derived、不动 stored/snap ⇒ 全部纯派生格判为 S3（覆盖数=0）', () => {
    // 模拟一批纯派生格（stored==snap），上游 D4-2 变了（derived 全变）。
    const grid = Array.from({ length: 20 }, (_, i) => {
      const base = (i + 1) * 100
      return { stored: base, snap: base, derived: base + 999 } // 上游全变、无人工覆盖
    })
    const states = grid.map((c) => resolveCellState(c.stored, c.snap, c.derived))
    const overriddenCount = states.filter((s) => s === 'S2' || s === 'S4').length
    expect(overriddenCount).toBe(0) // 🔴 一个都不该被误判成覆盖
    expect(states.every((s) => s === 'S3')).toBe(true)
  })

  it('对照：若错用 stored≠derived 判覆盖，同样输入会全判成覆盖（证明本判据有区分力）', () => {
    // 这条不调用生产代码，只证明「错法」在同一输入下会全错——说明 P12 抓的是真问题。
    const grid = Array.from({ length: 5 }, (_, i) => ({ stored: i * 10, snap: i * 10, derived: i * 10 + 7 }))
    const wrongOverridden = grid.filter((c) => Math.abs(c.stored - c.derived) > 0.005).length
    expect(wrongOverridden).toBe(5) // 错法把 5 个纯派生格全当覆盖
    // 而正确实现（resolveCellState）对同样输入是 0 个覆盖：
    const rightOverridden = grid
      .map((c) => resolveCellState(c.stored, c.snap, c.derived))
      .filter((s) => s === 'S2' || s === 'S4').length
    expect(rightOverridden).toBe(0)
  })
})

describe('displayValueForCellState：S1/S3 显示 derived，S2/S4 显示 stored', () => {
  it('S1 显示 derived', () => {
    expect(displayValueForCellState('S1', 150, 100)).toBe(100)
  })
  it('S3 显示 derived（跟随上游）', () => {
    expect(displayValueForCellState('S3', 100, 200)).toBe(200)
  })
  it('S2 显示 stored（覆盖值）', () => {
    expect(displayValueForCellState('S2', 150, 100)).toBe(150)
  })
  it('S4 显示 stored（覆盖值，非派生）', () => {
    expect(displayValueForCellState('S4', 150, 200)).toBe(150)
  })
})
