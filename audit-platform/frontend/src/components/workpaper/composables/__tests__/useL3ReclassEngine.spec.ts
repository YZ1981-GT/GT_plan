/**
 * Unit Tests — L3 长期借款一年内到期重分类引擎
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 2.3
 *
 * 已知值验证，互补 PBT 测试。
 * 覆盖 Property P7 的具体场景 + buildReclassEntry。
 * Requirements: 5.1-5.4, 10.3
 */
import { describe, it, expect } from 'vitest'
import {
  calcCurrentPortion,
  buildReclassEntry,
} from '../useL3ReclassEngine'

// ─── 1. calcCurrentPortion ──────────────────────────────────

describe('calcCurrentPortion', () => {
  // ─── 标准场景 ─────────────────────────────────────────────

  it('到期日在报告日后6个月 → 需重分类（全额）', () => {
    // 报告日2024-12-31，到期日2025-06-30（6个月后）→ 在一年内
    expect(calcCurrentPortion('2025-06-30', '2024-12-31', 10_000_000)).toBe(10_000_000)
  })

  it('到期日在报告日后11个月 → 需重分类', () => {
    expect(calcCurrentPortion('2025-11-30', '2024-12-31', 20_000_000)).toBe(20_000_000)
  })

  it('到期日在报告日后超过1年 → 不需重分类', () => {
    // 报告日2024-12-31，到期日2026-06-30（超过1年）
    expect(calcCurrentPortion('2026-06-30', '2024-12-31', 30_000_000)).toBe(0)
  })

  it('到期日在报告日后恰好13个月 → 不需重分类', () => {
    // 报告日2024-12-31，到期日2026-01-31（超过1年1天）
    expect(calcCurrentPortion('2026-01-31', '2024-12-31', 15_000_000)).toBe(0)
  })

  // ─── 边界场景 ─────────────────────────────────────────────

  it('到期日恰好等于报告日+1年（边界含当天）→ 需重分类', () => {
    // 报告日2024-12-31 + 1年 = 2025-12-31
    expect(calcCurrentPortion('2025-12-31', '2024-12-31', 50_000_000)).toBe(50_000_000)
  })

  it('到期日 = 报告日+1年+1天 → 不需重分类', () => {
    // 报告日2024-12-31 + 1年 = 2025-12-31, 到期日2026-01-01 > 边界
    expect(calcCurrentPortion('2026-01-01', '2024-12-31', 50_000_000)).toBe(0)
  })

  it('到期日等于报告日当天（已到期）→ 需重分类', () => {
    expect(calcCurrentPortion('2024-12-31', '2024-12-31', 8_000_000)).toBe(8_000_000)
  })

  it('到期日已过（逾期借款）→ 需重分类', () => {
    // 到期日2024-06-30 < 报告日2024-12-31
    expect(calcCurrentPortion('2024-06-30', '2024-12-31', 5_000_000)).toBe(5_000_000)
  })

  // ─── 闰年边界 ─────────────────────────────────────────────

  it('报告日2024-02-29（闰年）+ 1年 = 2025-02-28', () => {
    // 到期日2025-02-28 ≤ 2025-02-28 → 需重分类
    expect(calcCurrentPortion('2025-02-28', '2024-02-29', 12_000_000)).toBe(12_000_000)
  })

  it('报告日2024-02-29（闰年）, 到期日2025-03-01 → 不需重分类', () => {
    // 2024-02-29 + 1年 = 2025-02-28, 到期日2025-03-01 > 边界
    expect(calcCurrentPortion('2025-03-01', '2024-02-29', 12_000_000)).toBe(0)
  })

  // ─── 无效输入 ─────────────────────────────────────────────

  it('空dueDate → 0', () => {
    expect(calcCurrentPortion('', '2024-12-31', 10_000_000)).toBe(0)
  })

  it('空reportDate → 0', () => {
    expect(calcCurrentPortion('2025-06-30', '', 10_000_000)).toBe(0)
  })

  it('无效日期格式 → 0', () => {
    expect(calcCurrentPortion('invalid', '2024-12-31', 10_000_000)).toBe(0)
  })

  it('amount=0 → 0', () => {
    expect(calcCurrentPortion('2025-06-30', '2024-12-31', 0)).toBe(0)
  })

  it('amount<0 → 0（防御性）', () => {
    expect(calcCurrentPortion('2025-06-30', '2024-12-31', -5_000_000)).toBe(0)
  })
})

// ─── 2. buildReclassEntry ───────────────────────────────────

describe('buildReclassEntry', () => {
  it('生成标准重分类分录', () => {
    const entry = buildReclassEntry(10_000_000)

    expect(entry.description).toBe('一年内到期的长期借款重分类')
    expect(entry.debit.account).toBe('长期借款')
    expect(entry.debit.accountCode).toBe('2501')
    expect(entry.debit.amount).toBe(10_000_000)
    expect(entry.credit.account).toBe('一年内到期的非流动负债')
    expect(entry.credit.accountCode).toBe('2801')
    expect(entry.credit.amount).toBe(10_000_000)
  })

  it('借贷平衡：debit.amount === credit.amount', () => {
    const entry = buildReclassEntry(25_000_000)
    expect(entry.debit.amount).toBe(entry.credit.amount)
  })

  it('金额为0时仍返回合法结构', () => {
    const entry = buildReclassEntry(0)
    expect(entry.debit.amount).toBe(0)
    expect(entry.credit.amount).toBe(0)
    expect(entry.description).toBe('一年内到期的长期借款重分类')
  })

  it('负数防御性处理（取绝对值）', () => {
    const entry = buildReclassEntry(-5_000_000)
    expect(entry.debit.amount).toBe(5_000_000)
    expect(entry.credit.amount).toBe(5_000_000)
  })

  it('大金额场景', () => {
    const entry = buildReclassEntry(500_000_000)
    expect(entry.debit.amount).toBe(500_000_000)
    expect(entry.credit.amount).toBe(500_000_000)
  })
})

// ─── 3. 集成场景：重分类判定+分录生成全流程 ─────────────────

describe('集成场景：一年内到期重分类全流程', () => {
  it('一笔一年内到期借款 → 生成RJE', () => {
    // 3年期借款，到期日2025-03-15，报告日2024-12-31
    const portion = calcCurrentPortion('2025-03-15', '2024-12-31', 30_000_000)
    expect(portion).toBe(30_000_000)

    const entry = buildReclassEntry(portion)
    expect(entry.debit.amount).toBe(30_000_000)
    expect(entry.credit.amount).toBe(30_000_000)
    expect(entry.debit.accountCode).toBe('2501')
    expect(entry.credit.accountCode).toBe('2801')
  })

  it('一笔非一年内到期借款 → 无需RJE', () => {
    // 5年期借款，到期日2028-06-30，报告日2024-12-31
    const portion = calcCurrentPortion('2028-06-30', '2024-12-31', 100_000_000)
    expect(portion).toBe(0)

    const entry = buildReclassEntry(portion)
    expect(entry.debit.amount).toBe(0)
    expect(entry.credit.amount).toBe(0)
  })

  it('多笔借款汇总一年内到期', () => {
    // 模拟多笔借款
    const loans = [
      { dueDate: '2025-03-15', amount: 10_000_000 }, // 一年内
      { dueDate: '2025-09-30', amount: 20_000_000 }, // 一年内
      { dueDate: '2027-12-31', amount: 50_000_000 }, // 非一年内
      { dueDate: '2025-12-31', amount: 15_000_000 }, // 边界（含）
    ]
    const reportDate = '2024-12-31'

    const totalCurrentPortion = loans.reduce(
      (sum, loan) => sum + calcCurrentPortion(loan.dueDate, reportDate, loan.amount),
      0,
    )

    expect(totalCurrentPortion).toBe(10_000_000 + 20_000_000 + 15_000_000) // 45,000,000

    const entry = buildReclassEntry(totalCurrentPortion)
    expect(entry.debit.amount).toBe(45_000_000)
    expect(entry.credit.amount).toBe(45_000_000)
  })
})
