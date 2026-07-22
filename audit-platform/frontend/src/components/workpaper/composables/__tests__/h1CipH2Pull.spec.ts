/**
 * H1-7 在建工程转入 ↔ H2 转固 勾稽 — 纯函数单测
 */
import { describe, it, expect } from 'vitest'
import { extractH2TransferToFa, buildCipH2Reconcile } from '../h1CipH2Pull'

describe('extractH2TransferToFa', () => {
  it('sums transferAmount + transferAdj, skips subtotal/zero rows', () => {
    const rows = [
      { projectName: '厂房A', transferAmount: 1_000_000, transferDate: '2025-06-30' },
      { projectName: '设备安装B', transferAmount: 500_000, transferAdj: 20_000 },
      { name: '其他减少行', transferAmount: 0 }, // 无转固 → 跳过
      { isSubtotal: true, transferAmount: 9_999 }, // 小计 → 跳过
    ]
    const { total, rows: out } = extractH2TransferToFa(rows)
    expect(total).toBeCloseTo(1_520_000)
    expect(out).toHaveLength(2)
    expect(out[0].name).toBe('厂房A')
    expect(out[1].transferAmount).toBeCloseTo(520_000)
  })

  it('falls back to legacy decreaseTransfer field', () => {
    const { total } = extractH2TransferToFa([{ name: 'X', decreaseTransfer: 300_000 }])
    expect(total).toBeCloseTo(300_000)
  })

  it('handles empty / non-array input', () => {
    expect(extractH2TransferToFa(null).total).toBe(0)
    expect(extractH2TransferToFa(undefined).rows).toEqual([])
    expect(extractH2TransferToFa('bad').total).toBe(0)
  })
})

describe('buildCipH2Reconcile', () => {
  it('matches within tolerance', () => {
    const r = buildCipH2Reconcile(1_000_000, 1_000_000.5)
    expect(r.diff).toBeCloseTo(-0.5)
    expect(r.matched).toBe(true)
  })

  it('flags mismatch beyond tolerance', () => {
    const r = buildCipH2Reconcile(1_000_000, 900_000)
    expect(r.diff).toBeCloseTo(100_000)
    expect(r.matched).toBe(false)
  })

  it('respects custom tolerance', () => {
    expect(buildCipH2Reconcile(100, 150, 100).matched).toBe(true)
    expect(buildCipH2Reconcile(100, 150, 10).matched).toBe(false)
  })

  it('coerces invalid numbers to 0', () => {
    const r = buildCipH2Reconcile(NaN as unknown as number, undefined as unknown as number)
    expect(r.h1CipTransferIn).toBe(0)
    expect(r.h2TransferToFa).toBe(0)
    expect(r.matched).toBe(true)
  })
})
