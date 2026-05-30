/**
 * useEditorTour — 底稿编辑器首次渐进引导 [wp-frontend-ux-polish Task 3]
 *
 * 接入 el-tour（Element Plus 2.4+），首次打开底稿编辑器时 spotlight 引导。
 * 引导步骤：保存 / 侧面板 / 穿透溯源
 * localStorage 记录"已引导"，可跳过/不再提示。
 *
 * @example
 * const { tourVisible, tourSteps, startTour, closeTour, skipForever } = useEditorTour()
 */
import { ref, onMounted } from 'vue'

const TOUR_STORAGE_KEY = 'gt_editor_tour_dismissed'

export interface EditorTourStep {
  /** el-tour target CSS selector */
  target: string
  title: string
  description: string
  placement?: 'top' | 'bottom' | 'left' | 'right'
}

const EDITOR_TOUR_STEPS: EditorTourStep[] = [
  {
    target: '.gt-editor-toolbar__save-btn',
    title: '保存底稿',
    description: '点击此按钮保存当前底稿内容。系统也会每 60 秒自动保存一次。',
    placement: 'bottom',
  },
  {
    target: '.gt-wp-side-panel',
    title: '侧面板功能组',
    description: '右侧面板分为 4 个功能组：编制辅助、质量检查、追溯关联、历史版本。点击切换查看不同信息。',
    placement: 'left',
  },
  {
    target: '.gt-editor-toolbar__penetrate-btn',
    title: '穿透溯源',
    description: '选中单元格后点击此按钮，可追溯数据来源（试算表/其他底稿/报表），支持多级穿透跳转。',
    placement: 'bottom',
  },
]

export function useEditorTour() {
  const tourVisible = ref(false)
  const tourSteps = EDITOR_TOUR_STEPS

  /** 检查是否已永久跳过 */
  function isDismissed(): boolean {
    try {
      return localStorage.getItem(TOUR_STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  }

  /** 标记永久跳过 */
  function skipForever() {
    try {
      localStorage.setItem(TOUR_STORAGE_KEY, 'true')
    } catch { /* noop */ }
    tourVisible.value = false
  }

  /** 关闭引导（本次关闭，下次仍显示） */
  function closeTour() {
    tourVisible.value = false
    // 关闭也标记为已看过（不再提示）
    skipForever()
  }

  /** 手动触发引导 */
  function startTour() {
    tourVisible.value = true
  }

  onMounted(() => {
    if (!isDismissed()) {
      // 延迟 1.5s 等 DOM 渲染完成
      setTimeout(() => {
        tourVisible.value = true
      }, 1500)
    }
  })

  return {
    tourVisible,
    tourSteps,
    startTour,
    closeTour,
    skipForever,
    isDismissed,
  }
}
