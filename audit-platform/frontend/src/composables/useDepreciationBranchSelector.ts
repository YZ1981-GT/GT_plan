/**
 * useDepreciationBranchSelector — H/I 循环折旧/摊销分支选择器 composable
 *
 * spec workpaper-h-fixed-assets-cycle ADR-H3（Task 2.1）
 * spec workpaper-i-intangible-assets-cycle ADR-I1（Task 2.1）— I 循环扩展
 *
 * H 循环（同 wp_code 多版本 sheet，按减值次数或计算频率区分，正则匹配）：
 *   - H1-12: 3 版（不含减值-直线法 / 含减值 / 多次减值）
 *   - H3-7:  2 版（成本模式不含减值 / 成本模式含减值）
 *   - H5-12: 2 版（不含减值 / 含减值）
 *   - H7-11: 2 版（不含减值-直线法 / 含减值）
 *   - H8-8:  2 版（不含减值 / 含减值）
 *
 * I 循环（不同 wp_code 但业务相关 sheet，按 sheet 全名精确匹配）：
 *   - I1 摊销: I1-10 不含减值-剩余年限法 / I1-11 含减值
 *   - I4 摊销: I4-6 直线法           / I4-7 工作量法
 *
 *   注意：I 循环 sheet 名带括号修饰词（如"摊销测算表（不含减值）I1-10（剩余年限法）"），
 *   必须用 sheet 全名匹配，不能用 startsWith('I1-10') 前缀（会误命中"明细表I1-10"等）。
 *
 * 接口：{ branches, activeBranch, switchBranch }
 * 切换分支 = 调用 sheetNav.switchTo(targetSheetName)，不清空前一分支数据
 */
import { computed, type Ref } from 'vue'

// ===== 类型定义 =====

export interface BranchOption {
  sheetName: string   // 真实 sheet 名（含括号修饰词）
  label: string       // 显示标签（如"不含减值-直线法" / "含减值" / "多次减值" / "直线法" / "工作量法"）
  isMain: boolean     // 是否主版本
}

export interface IBranchGroup {
  groupId: string                 // 分组 ID（仅日志/调试用）
  label: string                   // 分组显示名（如"I1 摊销测算"）
  branches: BranchOption[]        // 该分组的全部分支（sheet 全名 + 标签 + isMain）
}

// ===== H 循环分支识别正则（ADR-H3） =====

export const BRANCH_PATTERNS: Record<string, RegExp[]> = {
  'H1-12': [/不含减值.*直线法/, /(?<!不)含减值(?!.*多次)/, /多次减值/],
  'H3-7':  [/不含减值/, /(?<!不)含减值/],
  'H5-12': [/不含减值/, /(?<!不)含减值/],
  'H7-11': [/不含减值.*直线法/, /(?<!不)含减值/],
  'H8-8':  [/不含减值/, /(?<!不)含减值/],
}

// ===== I 循环分支组（ADR-I1，按 sheet 全名精确匹配） =====

export const I_BRANCH_GROUPS: IBranchGroup[] = [
  {
    groupId: 'I1-amortization',
    label: 'I1 摊销测算',
    branches: [
      {
        sheetName: '摊销测算表（不含减值）I1-10（剩余年限法）',
        label: '不含减值-剩余年限法',
        isMain: true,
      },
      {
        sheetName: '摊销测算表（含减值）I1-11',
        label: '含减值',
        isMain: false,
      },
    ],
  },
  {
    groupId: 'I4-amortization',
    label: 'I4 摊销测算',
    branches: [
      {
        sheetName: '摊销测算I4-6',
        label: '直线法',
        isMain: true,
      },
      {
        sheetName: '摊销测算表I4-7（工作量法）',
        label: '工作量法',
        isMain: false,
      },
    ],
  },
]

/** 从 sheet 名中提取分支标签（H 循环用） */
function extractBranchLabel(sheetName: string, pattern: RegExp): string {
  const match = sheetName.match(pattern)
  if (match) return match[0]
  // fallback: 提取括号内容作为标签
  const parenMatch = sheetName.match(/[（(]([^）)]+)[）)]/)
  if (parenMatch) return parenMatch[1]
  return sheetName
}

/** 判断 sheet 是否为主版本（含"不含减值"或"-直线法"优先，H 循环用） */
function isMainVersion(sheetName: string): boolean {
  return /不含减值/.test(sheetName) || /-直线法/.test(sheetName)
}

/**
 * H 循环分支检测：从 sheet 名列表中提取指定 wp_code 的 branch 信息（正则匹配）
 */
export function detectBranches(wpCode: string, allSheetNames: string[]): BranchOption[] {
  const patterns = BRANCH_PATTERNS[wpCode]
  if (!patterns) return []

  // 筛选出包含该 wp_code 的 sheet
  const matches = allSheetNames.filter((s) => s.includes(wpCode))
  if (matches.length <= 1) return []

  const branches: BranchOption[] = []
  for (const pattern of patterns) {
    const hit = matches.find((s) => pattern.test(s))
    if (hit) {
      branches.push({
        sheetName: hit,
        label: extractBranchLabel(hit, pattern),
        isMain: isMainVersion(hit),
      })
    }
  }

  return branches
}

/**
 * I 循环分支检测：基于 active sheet 全名精确匹配 I_BRANCH_GROUPS。
 *
 * 与 H 循环不同：I 循环 I1-10/I1-11 / I4-6/I4-7 是不同 wp_code 但业务相关，
 * 必须用 sheet 全名匹配，不能用前缀（"摊销测算I4-6" 与 "明细表I4-2" 都含 "I4-"）。
 *
 * @returns 仅当 active sheet 命中某 I_BRANCH_GROUPS 且分组内 ≥ 2 个分支真实存在时返回；否则空数组
 */
export function detectIBranches(
  activeSheetName: string,
  allSheetNames: string[],
): BranchOption[] {
  if (!activeSheetName) return []

  // 找到包含 active sheet 的 group
  const group = I_BRANCH_GROUPS.find((g) =>
    g.branches.some((b) => b.sheetName === activeSheetName),
  )
  if (!group) return []

  // 仅保留真实存在于 allSheetNames 中的分支
  const present: BranchOption[] = group.branches.filter((b) =>
    allSheetNames.includes(b.sheetName),
  )

  // 单分支时不渲染选择器
  if (present.length <= 1) return []
  return present
}

/**
 * 从 sheet 名中提取 wp_code（如 "折旧测算表（不含减值）-直线法H1-12" → "H1-12"）
 *
 * 支持 H 和 I 循环。注意 I 循环 sheet 名后可能还有括号修饰词
 * （如 "摊销测算表（不含减值）I1-10（剩余年限法）"），正则只取第一段 wp_code。
 */
export function extractWpCode(sheetName: string): string | null {
  const match = sheetName.match(/[HI]\d+-\d+/)
  return match ? match[0] : null
}

// ===== composable =====

/**
 * H/I 循环折旧/摊销分支选择器 composable
 *
 * @param activeSheetName - 当前活跃 sheet 名（响应式）
 * @param allSheetNames - 全部 sheet 名列表（响应式）
 * @param onSwitchTo - 切换 sheet 的回调（调用 sheetNav.switchTo）
 */
export function useDepreciationBranchSelector(
  activeSheetName: Ref<string>,
  allSheetNames: Ref<string[]>,
  onSwitchTo: (sheetName: string) => void,
) {
  /** 当前 active sheet 对应的 wp_code（如 H1-12 / I1-10） */
  const activeWpCode = computed(() => {
    return extractWpCode(activeSheetName.value) || ''
  })

  /** 当前位置的所有分支选项（先 H 模式正则，再回退 I 模式精确匹配） */
  const branches = computed<BranchOption[]>(() => {
    const sheet = activeSheetName.value
    if (!sheet) return []

    // H 循环模式：wp_code → BRANCH_PATTERNS 正则匹配
    const wpCode = activeWpCode.value
    if (wpCode && BRANCH_PATTERNS[wpCode]) {
      const hBranches = detectBranches(wpCode, allSheetNames.value)
      if (hBranches.length > 0) return hBranches
    }

    // I 循环模式：sheet 全名 → I_BRANCH_GROUPS 精确匹配
    return detectIBranches(sheet, allSheetNames.value)
  })

  /** 当前活跃分支的 sheet 名 */
  const activeBranch = computed<string>(() => {
    return activeSheetName.value
  })

  /** 切换分支 — 调用 sheetNav.switchTo(targetSheetName) */
  function switchBranch(sheetName: string) {
    if (sheetName === activeSheetName.value) return
    onSwitchTo(sheetName)
  }

  return {
    branches,
    activeBranch,
    switchBranch,
  }
}
