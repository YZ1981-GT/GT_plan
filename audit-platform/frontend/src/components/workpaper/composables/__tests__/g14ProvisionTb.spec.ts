import { describe, it, expect } from 'vitest'
import {
  matchProvisionTbRow,
  pickProvisionTbClosing,
  isClosingReconciledWithTb,
} from '../g14ProvisionTb'
import { G14_LINE_ITEMS, isG14OciCounterpart, g14CounterpartHint } from '../g14Constants'

describe('g14ProvisionTb', () => {
  // 🔴 C-9：模板 `明细表G14-2` 固定行集无「合同资产减值损失」专行 ⇒ 1142 的取数落
  //    模板 R19「其他」行（`rowKey: 'other'`），原 `ca` 行已删。
  it('1142 直接匹配合同资产减值准备（落「其他」行）', () => {
    const def = G14_LINE_ITEMS.find((d) => d.rowKey === 'other')!
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

  it('🔴 合同资产并入「其他」行：对应科目名与 D6 的 ECL 交叉索引都挂该行', async () => {
    const { G14_ECL_CROSS_REF } = await import('../g14Constants')
    const other = G14_LINE_ITEMS.find((d) => d.rowKey === 'other')!
    expect(other.provisionAccount).toContain('合同资产减值准备')
    expect(G14_ECL_CROSS_REF.other).toBe('wp:D6-1')
    expect(G14_ECL_CROSS_REF).not.toHaveProperty('ca')
  })
})
