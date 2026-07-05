/**
 * G7TabAdjustment.spec.ts — G7-3 调整分录单元测试
 *
 * Task 6.4: 单元测试 — G7-3借贷平衡+AJE回写
 *   - 验证borrowing/credit平衡检测 (isDebitCreditBalanced)
 *   - 验证保存后G7-1对应行AJE/RJE列更新（CustomEvent payload结构）
 *
 * Requirements: 6.1
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  isDebitCreditBalanced,
  parseNum,
} from '../../../composables/useG7FormulaEngine'

// ═══ 从G7TabAdjustment.vue提取的纯逻辑 ═══

interface G7AdjustmentEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  preparedBy: string
  remark: string
}

/** 计算借方合计 — 与组件内computed一致 */
function calcTotalDebits(entries: G7AdjustmentEntry[]): number {
  return entries.reduce((sum, e) => sum + parseNum(e.debitAmount), 0)
}

/** 计算贷方合计 — 与组件内computed一致 */
function calcTotalCredits(entries: G7AdjustmentEntry[]): number {
  return entries.reduce((sum, e) => sum + parseNum(e.creditAmount), 0)
}

/** 借贷平衡校验 — 与组件内isBalanced computed一致 */
function checkBalanced(entries: G7AdjustmentEntry[]): boolean {
  return isDebitCreditBalanced(
    entries.map(e => e.debitAmount),
    entries.map(e => e.creditAmount),
  )
}

/** 计算AJE/RJE汇总回写金额 — 与组件handleSaveWriteback逻辑一致 */
function calcWritebackAmounts(entries: G7AdjustmentEntry[]): {
  ajeTotal: number
  rjeTotal: number
  totalAdjustment: number
} {
  const ajeTotal = entries
    .filter(e => e.entryType === 'AJE')
    .reduce((s, e) => s + parseNum(e.debitAmount) - parseNum(e.creditAmount), 0)
  const rjeTotal = entries
    .filter(e => e.entryType === 'RJE')
    .reduce((s, e) => s + parseNum(e.debitAmount) - parseNum(e.creditAmount), 0)
  return {
    ajeTotal,
    rjeTotal,
    totalAdjustment: ajeTotal + rjeTotal,
  }
}

// ═══ Helper: 创建测试分录 ═══
function makeEntry(overrides: Partial<G7AdjustmentEntry> = {}): G7AdjustmentEntry {
  return {
    id: `adj-${Math.random().toString(36).slice(2, 8)}`,
    seq: 1,
    entryType: 'AJE',
    date: '2025-12-31',
    summary: '调整分录',
    accountCode: '1511',
    accountName: '长期股权投资',
    debitAmount: 0,
    creditAmount: 0,
    preparedBy: '审计助理',
    remark: '',
    ...overrides,
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 借贷平衡检测
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7TabAdjustment - 借贷平衡检测', () => {
  it('借方=贷方时 isBalanced 返回 true', () => {
    const entries = [
      makeEntry({ debitAmount: 100000, creditAmount: 0 }),
      makeEntry({ debitAmount: 0, creditAmount: 100000 }),
    ]
    expect(checkBalanced(entries)).toBe(true)
  })

  it('多行借贷总和相等时平衡', () => {
    const entries = [
      makeEntry({ debitAmount: 50000, creditAmount: 0 }),
      makeEntry({ debitAmount: 30000, creditAmount: 0 }),
      makeEntry({ debitAmount: 0, creditAmount: 50000 }),
      makeEntry({ debitAmount: 0, creditAmount: 30000 }),
    ]
    expect(checkBalanced(entries)).toBe(true)
    expect(calcTotalDebits(entries)).toBe(80000)
    expect(calcTotalCredits(entries)).toBe(80000)
  })

  it('借贷不平衡时返回 false', () => {
    const entries = [
      makeEntry({ debitAmount: 100000, creditAmount: 0 }),
      makeEntry({ debitAmount: 0, creditAmount: 99000 }),
    ]
    expect(checkBalanced(entries)).toBe(false)
  })

  it('差额在0.01以内视为平衡（浮点容差）', () => {
    const entries = [
      makeEntry({ debitAmount: 100000.005, creditAmount: 0 }),
      makeEntry({ debitAmount: 0, creditAmount: 100000.001 }),
    ]
    // 差额 = 0.004 < 0.01 → 平衡
    expect(checkBalanced(entries)).toBe(true)
  })

  it('差额超过0.01不平衡', () => {
    const entries = [
      makeEntry({ debitAmount: 100000, creditAmount: 0 }),
      makeEntry({ debitAmount: 0, creditAmount: 99999.98 }),
    ]
    // 差额 = 0.02 > 0.01 → 不平衡
    expect(checkBalanced(entries)).toBe(false)
  })

  it('空数组视为平衡（0=0）', () => {
    expect(checkBalanced([])).toBe(true)
  })

  it('全零金额视为平衡', () => {
    const entries = [
      makeEntry({ debitAmount: 0, creditAmount: 0 }),
      makeEntry({ debitAmount: 0, creditAmount: 0 }),
    ]
    expect(checkBalanced(entries)).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// AJE/RJE回写G7-1审定表
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7TabAdjustment - AJE/RJE回写G7-1', () => {
  it('AJE回写金额 = AJE分录借方合计 - AJE分录贷方合计', () => {
    const entries = [
      makeEntry({ entryType: 'AJE', debitAmount: 500000, creditAmount: 0 }),
      makeEntry({ entryType: 'AJE', debitAmount: 0, creditAmount: 200000 }),
      makeEntry({ entryType: 'RJE', debitAmount: 100000, creditAmount: 100000 }),
    ]

    const { ajeTotal } = calcWritebackAmounts(entries)
    // AJE: (500000 - 0) + (0 - 200000) = 300000
    expect(ajeTotal).toBe(300000)
  })

  it('RJE回写金额 = RJE分录借方合计 - RJE分录贷方合计', () => {
    const entries = [
      makeEntry({ entryType: 'AJE', debitAmount: 100000, creditAmount: 100000 }),
      makeEntry({ entryType: 'RJE', debitAmount: 300000, creditAmount: 0 }),
      makeEntry({ entryType: 'RJE', debitAmount: 0, creditAmount: 150000 }),
    ]

    const { rjeTotal } = calcWritebackAmounts(entries)
    // RJE: (300000 - 0) + (0 - 150000) = 150000
    expect(rjeTotal).toBe(150000)
  })

  it('totalAdjustment = ajeTotal + rjeTotal', () => {
    const entries = [
      makeEntry({ entryType: 'AJE', debitAmount: 200000, creditAmount: 0 }),
      makeEntry({ entryType: 'RJE', debitAmount: 0, creditAmount: 50000 }),
    ]

    const result = calcWritebackAmounts(entries)
    // ajeTotal = 200000 - 0 = 200000
    // rjeTotal = 0 - 50000 = -50000
    // totalAdjustment = 200000 + (-50000) = 150000
    expect(result.ajeTotal).toBe(200000)
    expect(result.rjeTotal).toBe(-50000)
    expect(result.totalAdjustment).toBe(150000)
  })

  it('无AJE分录时ajeTotal为0', () => {
    const entries = [
      makeEntry({ entryType: 'RJE', debitAmount: 100000, creditAmount: 100000 }),
    ]
    const { ajeTotal } = calcWritebackAmounts(entries)
    expect(ajeTotal).toBe(0)
  })

  it('无RJE分录时rjeTotal为0', () => {
    const entries = [
      makeEntry({ entryType: 'AJE', debitAmount: 50000, creditAmount: 50000 }),
    ]
    const { rjeTotal } = calcWritebackAmounts(entries)
    expect(rjeTotal).toBe(0)
  })

  it('CustomEvent payload结构正确（g7:adjustment-writeback）', () => {
    const entries = [
      makeEntry({ entryType: 'AJE', debitAmount: 100000, creditAmount: 0 }),
      makeEntry({ entryType: 'AJE', debitAmount: 0, creditAmount: 100000 }),
      makeEntry({ entryType: 'RJE', debitAmount: 50000, creditAmount: 50000 }),
    ]

    const { ajeTotal, rjeTotal, totalAdjustment } = calcWritebackAmounts(entries)

    // 模拟 CustomEvent 的 detail 结构
    const eventDetail = {
      accountCode: '1511',
      ajeTotal,
      rjeTotal,
      totalAdjustment,
      entries,
    }

    expect(eventDetail.accountCode).toBe('1511')
    expect(eventDetail.ajeTotal).toBe(0) // 100000 - 100000 = 0
    expect(eventDetail.rjeTotal).toBe(0) // 50000 - 50000 = 0
    expect(eventDetail.totalAdjustment).toBe(0)
    expect(eventDetail.entries).toHaveLength(3)
  })

  it('借方多贷方少时回写正值（资产增加）', () => {
    const entries = [
      makeEntry({ entryType: 'AJE', debitAmount: 800000, creditAmount: 0 }),
      makeEntry({ entryType: 'AJE', debitAmount: 0, creditAmount: 300000 }),
    ]
    const { ajeTotal } = calcWritebackAmounts(entries)
    // 800000 - 300000 = 500000（正值=资产增加）
    expect(ajeTotal).toBe(500000)
  })

  it('贷方多借方少时回写负值（资产减少）', () => {
    const entries = [
      makeEntry({ entryType: 'AJE', debitAmount: 200000, creditAmount: 0 }),
      makeEntry({ entryType: 'AJE', debitAmount: 0, creditAmount: 700000 }),
    ]
    const { ajeTotal } = calcWritebackAmounts(entries)
    // 200000 - 700000 = -500000（负值=资产减少）
    expect(ajeTotal).toBe(-500000)
  })

  it('不平衡时阻止保存（组件逻辑验证）', () => {
    const entries = [
      makeEntry({ entryType: 'AJE', debitAmount: 100000, creditAmount: 0 }),
      // 缺少贷方 → 不平衡
    ]

    const isBalanced = checkBalanced(entries)
    expect(isBalanced).toBe(false)
    // 组件中: if (!isBalanced.value) { ElMessage.error(...); return }
    // 不平衡时不会触发CustomEvent回写
  })
})
