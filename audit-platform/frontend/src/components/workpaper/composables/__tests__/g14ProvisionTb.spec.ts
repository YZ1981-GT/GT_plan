import { describe, it, expect } from 'vitest'
import {
  matchProvisionTbRow,
  pickProvisionTbClosing,
  isClosingReconciledWithTb,
} from '../g14ProvisionTb'
import { G14_LINE_ITEMS, isG14OciCounterpart, g14CounterpartHint } from '../g14Constants'

describe('g14ProvisionTb', () => {
  it('1142 直接匹配合同资产减值准备', () => {
    const def = G14_LINE_ITEMS.find((d) => d.rowKey === 'ca')!
    const hit = matchProvisionTbRow(
      [{ standard_account_code: '1142', account_name: '合同资产减值准备', audited_amount: -8000 }],
      def,
    )
    expect(hit?.standard_account_code).toBe('1142')
    expect(pickProvisionTbClosing(hit)).toBe(8000)
  })

  it('1231 按名称消歧应收账款 vs 应收票据', () => {
    const rows = [
      { standard_account_code: '1231.01', account_name: '坏账准备-应收票据', audited_amount: 100 },
      { standard_account_code: '1231.02', account_name: '坏账准备-应收账款', audited_amount: 500 },
    ]
    const ar = G14_LINE_ITEMS.find((d) => d.rowKey === 'ar')!
    const notes = G14_LINE_ITEMS.find((d) => d.rowKey === 'notes')!
    expect(matchProvisionTbRow(rows, ar)?.standard_account_code).toBe('1231.02')
    expect(matchProvisionTbRow(rows, notes)?.standard_account_code).toBe('1231.01')
  })

  it('同前缀多行且无名称命中时不误配', () => {
    const def = G14_LINE_ITEMS.find((d) => d.rowKey === 'ar')!
    const hit = matchProvisionTbRow(
      [
        { standard_account_code: '1231.01', account_name: '准备A', audited_amount: 1 },
        { standard_account_code: '1231.02', account_name: '准备B', audited_amount: 2 },
      ],
      def,
    )
    expect(hit).toBeNull()
  })

  it('期末对账容差', () => {
    expect(isClosingReconciledWithTb(100, 100)).toBe(true)
    expect(isClosingReconciledWithTb(100, 100.005)).toBe(true)
    expect(isClosingReconciledWithTb(100, 101)).toBe(false)
    expect(isClosingReconciledWithTb(100, null)).toBe(true)
  })
})

describe('G14 FVOCI / OCI counterpart', () => {
  it('othdebt 标记为 OCI 并给出提示', () => {
    expect(isG14OciCounterpart('othdebt')).toBe(true)
    expect(isG14OciCounterpart('ar')).toBe(false)
    expect(g14CounterpartHint('othdebt')).toContain('其他综合收益')
    expect(g14CounterpartHint('othdebt')).toContain('而非坏账准备贷方')
  })

  it('合同资产与 ECL 交叉索引', () => {
    expect(G14_LINE_ITEMS.find((d) => d.rowKey === 'ca')?.provisionAccount).toBe('合同资产减值准备')
  })
})
