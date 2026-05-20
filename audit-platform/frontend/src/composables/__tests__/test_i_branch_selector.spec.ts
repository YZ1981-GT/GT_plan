/**
 * I-cycle Branch Selector vitest
 *
 * spec workpaper-i-intangible-assets-cycle ADR-I1（Task 2.2）
 *
 * 覆盖：
 * - I_BRANCH_GROUPS 配置（2 个分组：I1 摊销 / I4 摊销）
 * - detectIBranches 函数（基于 active sheet 全名精确匹配，不能用前缀）
 * - useDepreciationBranchSelector composable 对 I 循环的支持
 *
 * 与 H 循环的关键差异：
 * - H 循环：同 wp_code 多版本 sheet，按减值次数/计算频率正则匹配
 * - I 循环：不同 wp_code 但业务相关 sheet（I1-10/I1-11、I4-6/I4-7），按 sheet 全名精确匹配
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  detectIBranches,
  useDepreciationBranchSelector,
  I_BRANCH_GROUPS,
} from '@/composables/useDepreciationBranchSelector'

// ===== 真实 sheet 名（来自 Sprint 0.X 实测，6 文件 86 sheet 池） =====

const I1_AMORTIZATION_NO_IMPAIRMENT = '摊销测算表（不含减值）I1-10（剩余年限法）'
const I1_AMORTIZATION_WITH_IMPAIRMENT = '摊销测算表（含减值）I1-11'
const I4_AMORTIZATION_STRAIGHT_LINE = '摊销测算I4-6'
const I4_AMORTIZATION_UNITS_OF_PRODUCTION = '摊销测算表I4-7（工作量法）'

/** 完整的 I 循环 sheet 列表（含 I1/I4 摊销 4 sheet + 其他常见底稿 sheet） */
const ALL_I_SHEETS = [
  I1_AMORTIZATION_NO_IMPAIRMENT,
  I1_AMORTIZATION_WITH_IMPAIRMENT,
  I4_AMORTIZATION_STRAIGHT_LINE,
  I4_AMORTIZATION_UNITS_OF_PRODUCTION,
  // 其他 I 循环 sheet（不属于摊销分支）
  '审定表I1-1',
  '明细表I1-2',
  '审定表I4-1',
  '明细表I4-2',
  '减值测试I3-6',
  '研发费用明细表I6-2',
]

// ===== I_BRANCH_GROUPS 配置完整性测试 =====

describe('I_BRANCH_GROUPS - 配置完整性', () => {
  it('注册了 2 个分支组（I1 摊销 + I4 摊销）', () => {
    expect(I_BRANCH_GROUPS).toHaveLength(2)
    expect(I_BRANCH_GROUPS.map((g) => g.groupId)).toEqual([
      'I1-amortization',
      'I4-amortization',
    ])
  })

  it('I1-amortization 分组包含 I1-10（主版本）+ I1-11', () => {
    const group = I_BRANCH_GROUPS.find((g) => g.groupId === 'I1-amortization')
    expect(group).toBeDefined()
    expect(group!.branches).toHaveLength(2)
    expect(group!.branches[0].sheetName).toBe(I1_AMORTIZATION_NO_IMPAIRMENT)
    expect(group!.branches[0].isMain).toBe(true)
    expect(group!.branches[1].sheetName).toBe(I1_AMORTIZATION_WITH_IMPAIRMENT)
    expect(group!.branches[1].isMain).toBe(false)
  })

  it('I4-amortization 分组包含 I4-6（主版本）+ I4-7', () => {
    const group = I_BRANCH_GROUPS.find((g) => g.groupId === 'I4-amortization')
    expect(group).toBeDefined()
    expect(group!.branches).toHaveLength(2)
    expect(group!.branches[0].sheetName).toBe(I4_AMORTIZATION_STRAIGHT_LINE)
    expect(group!.branches[0].isMain).toBe(true)
    expect(group!.branches[1].sheetName).toBe(I4_AMORTIZATION_UNITS_OF_PRODUCTION)
    expect(group!.branches[1].isMain).toBe(false)
  })
})

// ===== detectIBranches 测试 =====

describe('detectIBranches - I 循环分支检测（按 sheet 全名精确匹配）', () => {
  it('case 1: I1-10 active 时检测到 I1-10 + I1-11 共 2 个分支（I1-10 isMain=true）', () => {
    const branches = detectIBranches(I1_AMORTIZATION_NO_IMPAIRMENT, ALL_I_SHEETS)
    expect(branches).toHaveLength(2)
    expect(branches[0].sheetName).toBe(I1_AMORTIZATION_NO_IMPAIRMENT)
    expect(branches[0].isMain).toBe(true)
    expect(branches[0].label).toBe('不含减值-剩余年限法')
    expect(branches[1].sheetName).toBe(I1_AMORTIZATION_WITH_IMPAIRMENT)
    expect(branches[1].isMain).toBe(false)
    expect(branches[1].label).toBe('含减值')
  })

  it('case 1b: I1-11 active 时也能检测到同一分组的 2 个分支', () => {
    const branches = detectIBranches(I1_AMORTIZATION_WITH_IMPAIRMENT, ALL_I_SHEETS)
    expect(branches).toHaveLength(2)
    expect(branches[0].sheetName).toBe(I1_AMORTIZATION_NO_IMPAIRMENT)
    expect(branches[1].sheetName).toBe(I1_AMORTIZATION_WITH_IMPAIRMENT)
  })

  it('case 2: I4-6 active 时检测到 I4-6 + I4-7 共 2 个分支（I4-6 isMain=true）', () => {
    const branches = detectIBranches(I4_AMORTIZATION_STRAIGHT_LINE, ALL_I_SHEETS)
    expect(branches).toHaveLength(2)
    expect(branches[0].sheetName).toBe(I4_AMORTIZATION_STRAIGHT_LINE)
    expect(branches[0].isMain).toBe(true)
    expect(branches[0].label).toBe('直线法')
    expect(branches[1].sheetName).toBe(I4_AMORTIZATION_UNITS_OF_PRODUCTION)
    expect(branches[1].isMain).toBe(false)
    expect(branches[1].label).toBe('工作量法')
  })

  it('case 2b: I4-7 active 时也能检测到同一分组的 2 个分支', () => {
    const branches = detectIBranches(I4_AMORTIZATION_UNITS_OF_PRODUCTION, ALL_I_SHEETS)
    expect(branches).toHaveLength(2)
    expect(branches[0].sheetName).toBe(I4_AMORTIZATION_STRAIGHT_LINE)
    expect(branches[1].sheetName).toBe(I4_AMORTIZATION_UNITS_OF_PRODUCTION)
  })

  it('case 3: 单分支回退 — 只有 I1-10 没有 I1-11 时返回 [] 不渲染选择器', () => {
    const sheetsOnlyI1_10 = [
      I1_AMORTIZATION_NO_IMPAIRMENT,
      // I1-11 缺失
      '审定表I1-1',
      '明细表I1-2',
    ]
    const branches = detectIBranches(I1_AMORTIZATION_NO_IMPAIRMENT, sheetsOnlyI1_10)
    expect(branches).toHaveLength(0)
  })

  it('case 3b: 单分支回退 — 只有 I4-6 没有 I4-7 时返回 [] 不渲染选择器', () => {
    const sheetsOnlyI4_6 = [
      I4_AMORTIZATION_STRAIGHT_LINE,
      // I4-7 缺失
      '审定表I4-1',
      '明细表I4-2',
    ]
    const branches = detectIBranches(I4_AMORTIZATION_STRAIGHT_LINE, sheetsOnlyI4_6)
    expect(branches).toHaveLength(0)
  })

  it('active sheet 不属于任何分组时返回 []', () => {
    const branches = detectIBranches('明细表I1-2', ALL_I_SHEETS)
    expect(branches).toHaveLength(0)
  })

  it('active sheet 为空字符串时返回 []', () => {
    const branches = detectIBranches('', ALL_I_SHEETS)
    expect(branches).toHaveLength(0)
  })

  it('精确匹配验证：构造 "明细表I4-6" 不应误匹配 I4 摊销分组（前缀/包含都不匹配）', () => {
    // 构造一个同时含 I4-6 字符串但全名不在 I_BRANCH_GROUPS 的 sheet
    const sheets = [
      '明细表I4-6', // 字符串包含 I4-6 但全名 ≠ I_BRANCH_GROUPS 任意 sheet
      I4_AMORTIZATION_UNITS_OF_PRODUCTION,
      '审定表I4-1',
    ]
    const branches = detectIBranches('明细表I4-6', sheets)
    expect(branches).toHaveLength(0)
  })

  it('精确匹配验证：I1-10 的真实 sheet 名带括号修饰词，前缀 "I1-10" 不能命中', () => {
    // 给定一个错误版本的 sheet 名（去掉了括号修饰词）
    const sheets = [
      '摊销测算表 I1-10', // 错误：缺少 "（不含减值）" 与 "（剩余年限法）" 修饰词
      I1_AMORTIZATION_WITH_IMPAIRMENT,
    ]
    // active 用错误版本 — 不应命中
    const branches = detectIBranches('摊销测算表 I1-10', sheets)
    expect(branches).toHaveLength(0)
  })
})

// ===== Composable 集成测试 =====

describe('useDepreciationBranchSelector composable - I 循环集成', () => {
  it('I1-10 active 时 branches 返回 2 个分支', () => {
    const activeSheet = ref(I1_AMORTIZATION_NO_IMPAIRMENT)
    const allSheets = ref(ALL_I_SHEETS)
    const switchFn = vi.fn()

    const { branches, activeBranch } = useDepreciationBranchSelector(
      activeSheet,
      allSheets,
      switchFn,
    )

    expect(branches.value).toHaveLength(2)
    expect(activeBranch.value).toBe(I1_AMORTIZATION_NO_IMPAIRMENT)
  })

  it('I4-6 active 时 branches 返回 2 个分支（直线法 + 工作量法）', () => {
    const activeSheet = ref(I4_AMORTIZATION_STRAIGHT_LINE)
    const allSheets = ref(ALL_I_SHEETS)
    const switchFn = vi.fn()

    const { branches } = useDepreciationBranchSelector(
      activeSheet,
      allSheets,
      switchFn,
    )

    expect(branches.value).toHaveLength(2)
    expect(branches.value[0].label).toBe('直线法')
    expect(branches.value[1].label).toBe('工作量法')
  })

  it('switchBranch 调用 onSwitchTo 切换到 I1-11', () => {
    const activeSheet = ref(I1_AMORTIZATION_NO_IMPAIRMENT)
    const allSheets = ref(ALL_I_SHEETS)
    const switchFn = vi.fn()

    const { switchBranch } = useDepreciationBranchSelector(
      activeSheet,
      allSheets,
      switchFn,
    )

    switchBranch(I1_AMORTIZATION_WITH_IMPAIRMENT)
    expect(switchFn).toHaveBeenCalledWith(I1_AMORTIZATION_WITH_IMPAIRMENT)
  })

  it('响应式更新：activeSheetName 从非分支 sheet 切换到 I1-10 时 branches 更新', () => {
    const activeSheet = ref('明细表I1-2')
    const allSheets = ref(ALL_I_SHEETS)
    const switchFn = vi.fn()

    const { branches } = useDepreciationBranchSelector(
      activeSheet,
      allSheets,
      switchFn,
    )

    // 初始：明细表I1-2 不在任何分组 → 空
    expect(branches.value).toHaveLength(0)

    // 切换到 I1-10 → 应检测到 2 个分支
    activeSheet.value = I1_AMORTIZATION_NO_IMPAIRMENT
    expect(branches.value).toHaveLength(2)

    // 切换到 I4-6 → 应检测到另一组 2 个分支
    activeSheet.value = I4_AMORTIZATION_STRAIGHT_LINE
    expect(branches.value).toHaveLength(2)
    expect(branches.value[0].sheetName).toBe(I4_AMORTIZATION_STRAIGHT_LINE)
  })

  it('响应式更新：allSheetNames 从单分支扩到双分支时 branches 更新', () => {
    const activeSheet = ref(I1_AMORTIZATION_NO_IMPAIRMENT)
    const allSheets = ref([I1_AMORTIZATION_NO_IMPAIRMENT]) // 仅单分支
    const switchFn = vi.fn()

    const { branches } = useDepreciationBranchSelector(
      activeSheet,
      allSheets,
      switchFn,
    )

    // 单分支时不渲染
    expect(branches.value).toHaveLength(0)

    // 加入 I1-11 后应渲染 2 个分支
    allSheets.value = [I1_AMORTIZATION_NO_IMPAIRMENT, I1_AMORTIZATION_WITH_IMPAIRMENT]
    expect(branches.value).toHaveLength(2)
  })
})
