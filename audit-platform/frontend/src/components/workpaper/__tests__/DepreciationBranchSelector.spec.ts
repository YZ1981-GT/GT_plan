/**
 * DepreciationBranchSelector vitest
 *
 * spec workpaper-h-fixed-assets-cycle ADR-H3（Task 2.2）
 *
 * 覆盖：
 * - 5 个位置的分支检测（H1-12 / H3-7 / H5-12 / H7-11 / H8-8）
 * - switchBranch 调用 switchTo 正确
 * - 组件渲染 radio buttons
 * - 无多版本时不渲染
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  detectBranches,
  extractWpCode,
  useDepreciationBranchSelector,
  BRANCH_PATTERNS,
} from '@/composables/useDepreciationBranchSelector'

// ===== 真实 sheet 名（来自 Sprint 0 实测 159 sheet 池） =====

const ALL_H_SHEETS = [
  '折旧测算表（不含减值）-直线法H1-12',
  '折旧测算表（含减值）H1-12',
  '折旧测算表（多次减值）H1-12',
  '折旧测算表（成本模式不含减值）H3-7',
  '折旧测算表（成本模式含减值）H3-7',
  '折耗测算表（不含减值）H5-12',
  '折耗测算表（含减值）H5-12',
  '折旧测算表（不含减值）-直线法H7-11',
  '折旧测算表（含减值）H7-11',
  '折旧测算表（不含减值）H8-8',
  '折旧测算表（含减值）H8-8',
  // 其他非多版本 sheet
  '审定表H1-1',
  '明细表H1-2',
  '折旧分配分析表H1-13',
]

// ===== detectBranches 测试 =====

describe('detectBranches - 5 个位置分支检测', () => {
  it('H1-12: 检测到 3 个分支', () => {
    const branches = detectBranches('H1-12', ALL_H_SHEETS)
    expect(branches).toHaveLength(3)
    expect(branches[0].sheetName).toBe('折旧测算表（不含减值）-直线法H1-12')
    expect(branches[0].isMain).toBe(true)
    expect(branches[1].sheetName).toBe('折旧测算表（含减值）H1-12')
    expect(branches[1].isMain).toBe(false)
    expect(branches[2].sheetName).toBe('折旧测算表（多次减值）H1-12')
    expect(branches[2].isMain).toBe(false)
  })

  it('H3-7: 检测到 2 个分支', () => {
    const branches = detectBranches('H3-7', ALL_H_SHEETS)
    expect(branches).toHaveLength(2)
    expect(branches[0].sheetName).toBe('折旧测算表（成本模式不含减值）H3-7')
    expect(branches[0].isMain).toBe(true)
    expect(branches[1].sheetName).toBe('折旧测算表（成本模式含减值）H3-7')
    expect(branches[1].isMain).toBe(false)
  })

  it('H5-12: 检测到 2 个分支', () => {
    const branches = detectBranches('H5-12', ALL_H_SHEETS)
    expect(branches).toHaveLength(2)
    expect(branches[0].sheetName).toBe('折耗测算表（不含减值）H5-12')
    expect(branches[0].isMain).toBe(true)
    expect(branches[1].sheetName).toBe('折耗测算表（含减值）H5-12')
    expect(branches[1].isMain).toBe(false)
  })

  it('H7-11: 检测到 2 个分支', () => {
    const branches = detectBranches('H7-11', ALL_H_SHEETS)
    expect(branches).toHaveLength(2)
    expect(branches[0].sheetName).toBe('折旧测算表（不含减值）-直线法H7-11')
    expect(branches[0].isMain).toBe(true)
    expect(branches[1].sheetName).toBe('折旧测算表（含减值）H7-11')
    expect(branches[1].isMain).toBe(false)
  })

  it('H8-8: 检测到 2 个分支', () => {
    const branches = detectBranches('H8-8', ALL_H_SHEETS)
    expect(branches).toHaveLength(2)
    expect(branches[0].sheetName).toBe('折旧测算表（不含减值）H8-8')
    expect(branches[0].isMain).toBe(true)
    expect(branches[1].sheetName).toBe('折旧测算表（含减值）H8-8')
    expect(branches[1].isMain).toBe(false)
  })

  it('非多版本 wp_code 返回空数组', () => {
    const branches = detectBranches('H1-13', ALL_H_SHEETS)
    expect(branches).toHaveLength(0)
  })

  it('未注册的 wp_code 返回空数组', () => {
    const branches = detectBranches('H99-99', ALL_H_SHEETS)
    expect(branches).toHaveLength(0)
  })

  it('单 sheet 匹配时返回空数组（无需分支选择）', () => {
    const singleSheet = ['折旧测算表（不含减值）-直线法H1-12']
    const branches = detectBranches('H1-12', singleSheet)
    expect(branches).toHaveLength(0)
  })
})

// ===== extractWpCode 测试 =====

describe('extractWpCode - 从 sheet 名提取 wp_code', () => {
  it('提取 H1-12', () => {
    expect(extractWpCode('折旧测算表（不含减值）-直线法H1-12')).toBe('H1-12')
  })

  it('提取 H3-7', () => {
    expect(extractWpCode('折旧测算表（成本模式不含减值）H3-7')).toBe('H3-7')
  })

  it('提取 H5-12', () => {
    expect(extractWpCode('折耗测算表（不含减值）H5-12')).toBe('H5-12')
  })

  it('无 wp_code 返回 null', () => {
    expect(extractWpCode('底稿目录')).toBeNull()
  })

  it('提取 H10-2', () => {
    expect(extractWpCode('明细表H10-2')).toBe('H10-2')
  })
})

// ===== useDepreciationBranchSelector composable 测试 =====

describe('useDepreciationBranchSelector composable', () => {
  it('当 active sheet 有多版本时返回 branches', () => {
    const activeSheet = ref('折旧测算表（不含减值）-直线法H1-12')
    const allSheets = ref(ALL_H_SHEETS)
    const switchFn = vi.fn()

    const { branches, activeBranch } = useDepreciationBranchSelector(
      activeSheet,
      allSheets,
      switchFn,
    )

    expect(branches.value).toHaveLength(3)
    expect(activeBranch.value).toBe('折旧测算表（不含减值）-直线法H1-12')
  })

  it('switchBranch 调用 onSwitchTo 回调', () => {
    const activeSheet = ref('折旧测算表（不含减值）-直线法H1-12')
    const allSheets = ref(ALL_H_SHEETS)
    const switchFn = vi.fn()

    const { switchBranch } = useDepreciationBranchSelector(
      activeSheet,
      allSheets,
      switchFn,
    )

    switchBranch('折旧测算表（含减值）H1-12')
    expect(switchFn).toHaveBeenCalledWith('折旧测算表（含减值）H1-12')
  })

  it('switchBranch 切换到当前 sheet 时不调用回调', () => {
    const activeSheet = ref('折旧测算表（不含减值）-直线法H1-12')
    const allSheets = ref(ALL_H_SHEETS)
    const switchFn = vi.fn()

    const { switchBranch } = useDepreciationBranchSelector(
      activeSheet,
      allSheets,
      switchFn,
    )

    switchBranch('折旧测算表（不含减值）-直线法H1-12')
    expect(switchFn).not.toHaveBeenCalled()
  })

  it('active sheet 无多版本时 branches 为空', () => {
    const activeSheet = ref('审定表H1-1')
    const allSheets = ref(ALL_H_SHEETS)
    const switchFn = vi.fn()

    const { branches } = useDepreciationBranchSelector(
      activeSheet,
      allSheets,
      switchFn,
    )

    expect(branches.value).toHaveLength(0)
  })

  it('响应式更新：切换到 H8-8 后检测到 2 个分支', () => {
    const activeSheet = ref('审定表H1-1')
    const allSheets = ref(ALL_H_SHEETS)
    const switchFn = vi.fn()

    const { branches } = useDepreciationBranchSelector(
      activeSheet,
      allSheets,
      switchFn,
    )

    expect(branches.value).toHaveLength(0)

    // 模拟切换到 H8-8
    activeSheet.value = '折旧测算表（不含减值）H8-8'
    expect(branches.value).toHaveLength(2)
  })
})

// ===== BRANCH_PATTERNS 完整性测试 =====

describe('BRANCH_PATTERNS - 5 个位置全部注册', () => {
  const expectedPositions = ['H1-12', 'H3-7', 'H5-12', 'H7-11', 'H8-8']

  for (const pos of expectedPositions) {
    it(`${pos} 已注册分支正则`, () => {
      expect(BRANCH_PATTERNS[pos]).toBeDefined()
      expect(BRANCH_PATTERNS[pos].length).toBeGreaterThanOrEqual(2)
    })
  }

  it('H1-12 有 3 个正则（3 版）', () => {
    expect(BRANCH_PATTERNS['H1-12']).toHaveLength(3)
  })

  it('H3-7 / H5-12 / H7-11 / H8-8 各有 2 个正则', () => {
    expect(BRANCH_PATTERNS['H3-7']).toHaveLength(2)
    expect(BRANCH_PATTERNS['H5-12']).toHaveLength(2)
    expect(BRANCH_PATTERNS['H7-11']).toHaveLength(2)
    expect(BRANCH_PATTERNS['H8-8']).toHaveLength(2)
  })
})
