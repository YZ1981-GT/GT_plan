/**
 * useWpOnboardingGuide — 底稿首次使用引导 composable
 *
 * 功能：
 * - A 类程序表增加 el-tour 3 步引导
 * - localStorage 记录已看过不重复显示
 * - 工具栏「?」按钮可重新触发引导
 *
 * @example
 * const { showGuide, guideSteps, triggerGuide } = useWpOnboardingGuide('a-program-console')
 *
 * Validates: Requirements US-13
 */
import { ref, watch } from 'vue'

// ─── 常量 ─────────────────────────────────────────────────────────────────────

const GUIDE_KEY = 'gt_wp_guide_shown'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface GuideStep {
  target: string
  title: string
  description: string
}

// ─── 引导步骤配置 ─────────────────────────────────────────────────────────────

const A_PROGRAM_CONSOLE_STEPS: GuideStep[] = [
  {
    target: '.gt-a-program-console__progress',
    title: '程序表中控台',
    description: '这里显示整体完成进度，包括已完成、已裁剪、进行中和待执行的程序数量。',
  },
  {
    target: '.gt-a-program-console__table .el-table__expand-icon',
    title: '展开查看详情',
    description: '点击展开按钮查看完整程序描述、历史决策记录和关联底稿。',
  },
  {
    target: '.gt-a-program-console__actions',
    title: '批量裁剪',
    description: '选中多条程序后可一次性裁剪并填写理由，大幅提升效率。',
  },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useWpOnboardingGuide(componentType?: string) {
  const showGuide = ref(false)

  /** 获取当前组件类型对应的引导步骤 */
  function getSteps(): GuideStep[] {
    switch (componentType) {
      case 'a-program-console':
        return A_PROGRAM_CONSOLE_STEPS
      default:
        return []
    }
  }

  const guideSteps = getSteps()

  /** 检查是否已看过引导 */
  function hasSeenGuide(): boolean {
    try {
      const raw = localStorage.getItem(GUIDE_KEY)
      if (!raw) return false
      const seen: Record<string, boolean> = JSON.parse(raw)
      return !!seen[componentType || 'default']
    } catch {
      return false
    }
  }

  /** 标记引导已看过 */
  function markGuideSeen() {
    try {
      const raw = localStorage.getItem(GUIDE_KEY)
      const seen: Record<string, boolean> = raw ? JSON.parse(raw) : {}
      seen[componentType || 'default'] = true
      localStorage.setItem(GUIDE_KEY, JSON.stringify(seen))
    } catch {
      // 静默忽略
    }
  }

  /** 手动触发引导（工具栏「?」按钮） */
  function triggerGuide() {
    showGuide.value = true
  }

  /** 引导关闭时标记已看过 */
  watch(showGuide, (val) => {
    if (!val) {
      markGuideSeen()
    }
  })

  // 首次使用时自动显示（仅当有步骤且未看过时）
  if (guideSteps.length > 0 && !hasSeenGuide()) {
    // 延迟显示，等待 DOM 渲染完成
    setTimeout(() => {
      showGuide.value = true
    }, 1000)
  }

  return {
    showGuide,
    guideSteps,
    triggerGuide,
    hasSeenGuide,
  }
}
