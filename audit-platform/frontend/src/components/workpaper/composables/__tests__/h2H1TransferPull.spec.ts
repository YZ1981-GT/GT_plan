/**
 * h2H1TransferPull — H2-5 ↔ H1 反向勾稽纯函数单测
 */
import { describe, it, expect } from 'vitest'
import {
  extractH1CipAdditions,
  matchH1AmountByName,
  buildH2H1TransferReconcile,
  isCipTransferMethod,
} from '../h2H1TransferPull'

describe('isCipTransferMethod', () => {
  it('命中在建工程转入相关口径', () => {
    expect(isCipTransferMethod('在建工程转入')).toBe(true)
    expect(isCipTransferMethod('cip')).toBe(true)
    expect(isCipTransferMethod('在建转入')).toBe(true)
    expect(isCipTransferMethod('在建结转')).toBe(true)
  })
  it('非在建转入返回 false', () => {
    expect(isCipTransferMethod('外购')).toBe(false)
    expect(isCipTransferMethod('')).toBe(false)
    expect(isCipTransferMethod(null)).toBe(false)
  })
})

describe('extractH1CipAdditions', () => {
  it('仅提取在建工程转入行并汇总入账原值', () => {
    const rows = [
      { name: '1号厂房', additionMethod: '在建工程转入', originalCost: 1000, voucherNo: 'V1', assetCategory: '房屋' },
      { name: '设备A', additionMethod: '外购', originalCost: 500 },
      { name: '2号线', additionMethod: 'cip', originalCost: 2000 },
      { isSubtotal: true, additionMethod: '在建工程转入', originalCost: 3000 },
    ]
    const { total, rows: out } = extractH1CipAdditions(rows)
    expect(total).toBe(3000)
    expect(out).toHaveLength(2)
    expect(out[0]).toMatchObject({ name: '1号厂房', recordedAmount: 1000, assetCategory: '房屋', voucherNo: 'V1' })
  })
  it('金额为 0 或非数组安全返回', () => {
    expect(extractH1CipAdditions(null)).toEqual({ total: 0, rows: [] })
    expect(extractH1CipAdditions([{ additionMethod: '在建工程转入', originalCost: 0 }])).toEqual({ total: 0, rows: [] })
  })
})

describe('matchH1AmountByName', () => {
  const h1 = [
    { name: '1号厂房', recordedAmount: 1000, assetCategory: '房屋', voucherNo: '' },
    { name: '2号生产线', recordedAmount: 2000, assetCategory: '设备', voucherNo: '' },
  ]
  it('精确匹配优先', () => {
    expect(matchH1AmountByName('1号厂房', h1)?.recordedAmount).toBe(1000)
  })
  it('去空白/双向包含兜底', () => {
    expect(matchH1AmountByName(' 1号厂房 ', h1)?.recordedAmount).toBe(1000)
    expect(matchH1AmountByName('2号生产线（一期）', h1)?.recordedAmount).toBe(2000)
  })
  it('无匹配返回 null', () => {
    expect(matchH1AmountByName('3号仓库', h1)).toBeNull()
    expect(matchH1AmountByName('', h1)).toBeNull()
  })
})

describe('buildH2H1TransferReconcile', () => {
  it('容差内视为一致', () => {
    const r = buildH2H1TransferReconcile(1000.5, 1000, 1)
    expect(r.matched).toBe(true)
    expect(r.diff).toBeCloseTo(0.5, 5)
  })
  it('超容差为差异', () => {
    const r = buildH2H1TransferReconcile(1200, 1000)
    expect(r.matched).toBe(false)
    expect(r.diff).toBe(200)
  })
})
