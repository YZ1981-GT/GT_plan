import { describe, it, expect } from 'vitest'

/**
 * H3-14 租金勾稽纯函数测试。
 * 函数内联在 H3TabRentalIncome.vue 中（computed），此处测试其逻辑等价函数。
 *
 * 租金勾稽逻辑：
 * diff = tb6051Audited - h3AnnualTotal
 * - diff > 0 → info（差额为其他来源的其他业务收入）
 * - diff < 0 → warning（H3 测算 > TB，需关注）
 * - diff === 0 → ok
 * - tb6051 === null → unavailable
 */

// 抽出测试用纯函数（等价于组件内 computed 逻辑）
function buildH3RentalReconcile(
  h3AnnualTotal: number,
  tb6051Audited: number | null,
): { diff: number | null; status: 'ok' | 'info' | 'warning' | 'unavailable' } {
  if (tb6051Audited == null) {
    return { diff: null, status: 'unavailable' }
  }
  const diff = tb6051Audited - h3AnnualTotal
  if (Math.abs(diff) <= 1) {
    return { diff, status: 'ok' }
  }
  // diff > 0: TB 有其他来源收入（info）；diff < 0: H3 > TB（warning）
  return { diff, status: diff > 0 ? 'info' : 'warning' }
}

describe('h3RentalReconcile', () => {
  // P4: 方向性判定
  it('P4: diff > 0 (TB > H3) → info (other sources)', () => {
    const result = buildH3RentalReconcile(100000, 150000)
    expect(result.diff).toBe(50000)
    expect(result.status).toBe('info')
  })

  it('P4: diff < 0 (H3 > TB) → warning', () => {
    const result = buildH3RentalReconcile(150000, 100000)
    expect(result.diff).toBe(-50000)
    expect(result.status).toBe('warning')
  })

  it('P4: diff within tolerance → ok', () => {
    const result = buildH3RentalReconcile(100000, 100000.5)
    expect(result.diff).toBeCloseTo(0.5)
    expect(result.status).toBe('ok')
  })

  // P8: TB6051 为 null → unavailable
  it('P8: tb6051 null → unavailable, diff null', () => {
    const result = buildH3RentalReconcile(100000, null)
    expect(result.diff).toBeNull()
    expect(result.status).toBe('unavailable')
  })

  // 正常路径：精确一致
  it('exact match → ok', () => {
    const result = buildH3RentalReconcile(200000, 200000)
    expect(result.diff).toBe(0)
    expect(result.status).toBe('ok')
  })

  // 边界：H3=0 TB=0
  it('both zero → ok', () => {
    const result = buildH3RentalReconcile(0, 0)
    expect(result.diff).toBe(0)
    expect(result.status).toBe('ok')
  })
})
