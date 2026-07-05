/**
 * G7TabVoucherCheck 单元测试
 *
 * 测试 G7-18 凭证检查表的核心逻辑：
 * 1. 异常自动检测：check1-6任一false → isAbnormal=true
 * 2. 区段Tab行同步：切换Tab后选中行索引不变
 * 3. 借贷平衡汇总：差额≠0 → 红色显示（isDebitCreditBalanced）
 * 4. 虚拟滚动降级到分页：99行 / pageSize=30 → 4页
 *
 * Requirements: 6.1, 6.2
 */
import { describe, it, expect } from 'vitest'
import { isDebitCreditBalanced } from '../../../composables/useG7SubFormulaEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// 核心纯函数：异常自动检测
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 异常自动检测逻辑（G7-18 Tab2 → Tab3联动）
 * 当check1-6任一为false时，该行自动标记为异常
 * @source G7-18凭证检查表 Requirements 6.1, 6.2
 */
function isRowAbnormal(row: {
  check1: boolean
  check2: boolean
  check3: boolean
  check4: boolean
  check5: boolean
  check6: boolean
}): boolean {
  return !(row.check1 && row.check2 && row.check3 && row.check4 && row.check5 && row.check6)
}

// ═══════════════════════════════════════════════════════════════════════════════
// 核心纯函数：区段Tab行同步状态管理
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 区段Tab状态管理：切换Tab时保持行索引不变
 * 3区段Tab共享同一份rows数据，activeRowIndex跨Tab保持一致
 */
interface TabSyncState {
  activeTab: 'voucher' | 'check' | 'conclusion'
  activeRowIndex: number
  totalRows: number
}

function switchTab(state: TabSyncState, newTab: TabSyncState['activeTab']): TabSyncState {
  return { ...state, activeTab: newTab }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 核心纯函数：虚拟滚动降级到分页
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * 分页逻辑：当虚拟滚动不可用时降级为分页模式
 */
interface PaginationState {
  totalRows: number
  pageSize: number
  currentPage: number
}

function calcTotalPages(state: PaginationState): number {
  return Math.ceil(state.totalRows / state.pageSize)
}

function getPageRows<T>(rows: T[], state: PaginationState): T[] {
  const start = (state.currentPage - 1) * state.pageSize
  return rows.slice(start, start + state.pageSize)
}

function goToPage(state: PaginationState, page: number): PaginationState {
  const totalPages = calcTotalPages(state)
  const clampedPage = Math.max(1, Math.min(page, totalPages))
  return { ...state, currentPage: clampedPage }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 测试套件
// ═══════════════════════════════════════════════════════════════════════════════

describe('G7TabVoucherCheck - 异常自动检测逻辑', () => {
  /**
   * Validates: Requirements 6.1, 6.2
   * check1-6任一false → isAbnormal=true
   */
  it('所有check均为true → isAbnormal=false', () => {
    const row = { check1: true, check2: true, check3: true, check4: true, check5: true, check6: true }
    expect(isRowAbnormal(row)).toBe(false)
  })

  it('check1为false → isAbnormal=true', () => {
    const row = { check1: false, check2: true, check3: true, check4: true, check5: true, check6: true }
    expect(isRowAbnormal(row)).toBe(true)
  })

  it('check2为false → isAbnormal=true', () => {
    const row = { check1: true, check2: false, check3: true, check4: true, check5: true, check6: true }
    expect(isRowAbnormal(row)).toBe(true)
  })

  it('check3为false → isAbnormal=true', () => {
    const row = { check1: true, check2: true, check3: false, check4: true, check5: true, check6: true }
    expect(isRowAbnormal(row)).toBe(true)
  })

  it('check4为false → isAbnormal=true', () => {
    const row = { check1: true, check2: true, check3: true, check4: false, check5: true, check6: true }
    expect(isRowAbnormal(row)).toBe(true)
  })

  it('check5为false → isAbnormal=true', () => {
    const row = { check1: true, check2: true, check3: true, check4: true, check5: false, check6: true }
    expect(isRowAbnormal(row)).toBe(true)
  })

  it('check6为false → isAbnormal=true', () => {
    const row = { check1: true, check2: true, check3: true, check4: true, check5: true, check6: false }
    expect(isRowAbnormal(row)).toBe(true)
  })

  it('多个check为false → isAbnormal=true', () => {
    const row = { check1: false, check2: false, check3: true, check4: true, check5: false, check6: true }
    expect(isRowAbnormal(row)).toBe(true)
  })

  it('全部check为false → isAbnormal=true', () => {
    const row = { check1: false, check2: false, check3: false, check4: false, check5: false, check6: false }
    expect(isRowAbnormal(row)).toBe(true)
  })
})

describe('G7TabVoucherCheck - 区段Tab行同步', () => {
  /**
   * Validates: Requirements 6.1
   * 切换Tab后选中行索引不变
   */
  it('从Tab1切换到Tab2后activeRowIndex保持不变', () => {
    const state: TabSyncState = { activeTab: 'voucher', activeRowIndex: 15, totalRows: 99 }
    const newState = switchTab(state, 'check')
    expect(newState.activeRowIndex).toBe(15)
    expect(newState.activeTab).toBe('check')
  })

  it('从Tab2切换到Tab3后activeRowIndex保持不变', () => {
    const state: TabSyncState = { activeTab: 'check', activeRowIndex: 42, totalRows: 99 }
    const newState = switchTab(state, 'conclusion')
    expect(newState.activeRowIndex).toBe(42)
    expect(newState.activeTab).toBe('conclusion')
  })

  it('从Tab3切回Tab1后activeRowIndex保持不变', () => {
    const state: TabSyncState = { activeTab: 'conclusion', activeRowIndex: 0, totalRows: 99 }
    const newState = switchTab(state, 'voucher')
    expect(newState.activeRowIndex).toBe(0)
    expect(newState.activeTab).toBe('voucher')
  })

  it('连续多次切换Tab后activeRowIndex始终不变', () => {
    let state: TabSyncState = { activeTab: 'voucher', activeRowIndex: 88, totalRows: 99 }
    state = switchTab(state, 'check')
    state = switchTab(state, 'conclusion')
    state = switchTab(state, 'voucher')
    state = switchTab(state, 'check')
    expect(state.activeRowIndex).toBe(88)
  })

  it('activeRowIndex为边界值(最后一行)切换Tab不变', () => {
    const state: TabSyncState = { activeTab: 'voucher', activeRowIndex: 98, totalRows: 99 }
    const newState = switchTab(state, 'conclusion')
    expect(newState.activeRowIndex).toBe(98)
  })
})

describe('G7TabVoucherCheck - 借贷平衡汇总', () => {
  /**
   * Validates: Requirements 6.2
   * 差额≠0 → 红色显示 (isDebitCreditBalanced from useG7SubFormulaEngine)
   */
  it('借贷相等 → balanced=true（不显示红色）', () => {
    const debits = [1000, 2000, 3000]
    const credits = [1500, 2500, 2000]
    expect(isDebitCreditBalanced(debits, credits)).toBe(true)
  })

  it('借贷差额<0.01 → balanced=true（容差内）', () => {
    const debits = [100.005]
    const credits = [100.001]
    // 差额=0.004 < 0.01 → balanced
    expect(isDebitCreditBalanced(debits, credits)).toBe(true)
  })

  it('借方>贷方且差额≥0.01 → balanced=false（红色显示）', () => {
    const debits = [10000, 5000]
    const credits = [10000, 4000]
    // 差额=1000 → 不平衡
    expect(isDebitCreditBalanced(debits, credits)).toBe(false)
  })

  it('贷方>借方且差额≥0.01 → balanced=false（红色显示）', () => {
    const debits = [500]
    const credits = [600]
    // 差额=-100 → |差额|=100 → 不平衡
    expect(isDebitCreditBalanced(debits, credits)).toBe(false)
  })

  it('空数组 → balanced=true（0-0=0<0.01）', () => {
    expect(isDebitCreditBalanced([], [])).toBe(true)
  })

  it('多行凭证总计平衡 → balanced=true', () => {
    // 模拟G7-18 99行凭证的借贷汇总
    const debits = [15000, 8000, 3200, 1500, 22300]
    const credits = [15000, 8000, 3200, 1500, 22300]
    expect(isDebitCreditBalanced(debits, credits)).toBe(true)
  })

  it('单笔凭证借贷不等 → balanced=false', () => {
    const debits = [50000]
    const credits = [49999]
    expect(isDebitCreditBalanced(debits, credits)).toBe(false)
  })

  it('差额恰好等于0.01 → balanced=false（边界值）', () => {
    const debits = [100.01]
    const credits = [100]
    // 差额=0.01 → Math.abs(0.01) < 0.01 为false → 不平衡
    expect(isDebitCreditBalanced(debits, credits)).toBe(false)
  })
})

describe('G7TabVoucherCheck - 虚拟滚动降级到分页', () => {
  /**
   * Validates: Requirements 6.2
   * 99行 pageSize=30 → 4页; 分页状态正确
   */
  it('99行 pageSize=30 → 4页', () => {
    const state: PaginationState = { totalRows: 99, pageSize: 30, currentPage: 1 }
    expect(calcTotalPages(state)).toBe(4)
  })

  it('第1页返回前30行', () => {
    const rows = Array.from({ length: 99 }, (_, i) => ({ seq: i + 1 }))
    const state: PaginationState = { totalRows: 99, pageSize: 30, currentPage: 1 }
    const pageRows = getPageRows(rows, state)
    expect(pageRows).toHaveLength(30)
    expect(pageRows[0].seq).toBe(1)
    expect(pageRows[29].seq).toBe(30)
  })

  it('第4页(最后一页)返回剩余9行', () => {
    const rows = Array.from({ length: 99 }, (_, i) => ({ seq: i + 1 }))
    const state: PaginationState = { totalRows: 99, pageSize: 30, currentPage: 4 }
    const pageRows = getPageRows(rows, state)
    expect(pageRows).toHaveLength(9)
    expect(pageRows[0].seq).toBe(91)
    expect(pageRows[8].seq).toBe(99)
  })

  it('翻到第2页正确切片', () => {
    const rows = Array.from({ length: 99 }, (_, i) => ({ seq: i + 1 }))
    const state: PaginationState = { totalRows: 99, pageSize: 30, currentPage: 2 }
    const pageRows = getPageRows(rows, state)
    expect(pageRows).toHaveLength(30)
    expect(pageRows[0].seq).toBe(31)
    expect(pageRows[29].seq).toBe(60)
  })

  it('goToPage超过最大页数 → 锁定在最后一页', () => {
    const state: PaginationState = { totalRows: 99, pageSize: 30, currentPage: 1 }
    const newState = goToPage(state, 10)
    expect(newState.currentPage).toBe(4)
  })

  it('goToPage小于1 → 锁定在第1页', () => {
    const state: PaginationState = { totalRows: 99, pageSize: 30, currentPage: 3 }
    const newState = goToPage(state, 0)
    expect(newState.currentPage).toBe(1)
  })

  it('goToPage负数 → 锁定在第1页', () => {
    const state: PaginationState = { totalRows: 99, pageSize: 30, currentPage: 2 }
    const newState = goToPage(state, -5)
    expect(newState.currentPage).toBe(1)
  })

  it('30行恰好1页(pageSize=30)', () => {
    const state: PaginationState = { totalRows: 30, pageSize: 30, currentPage: 1 }
    expect(calcTotalPages(state)).toBe(1)
  })

  it('31行需要2页(pageSize=30)', () => {
    const state: PaginationState = { totalRows: 31, pageSize: 30, currentPage: 1 }
    expect(calcTotalPages(state)).toBe(2)
  })
})
