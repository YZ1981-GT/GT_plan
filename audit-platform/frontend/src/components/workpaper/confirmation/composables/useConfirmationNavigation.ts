/**
 * useConfirmationNavigation — 跨底稿跳转 composable
 *
 * 渲染跳转链接（D0-4/D0-5/D0-6），复用 addressRegistry jump_route 模式。
 */
import { type Ref } from 'vue'

export interface NavigationTarget {
  label: string
  wpCode: string
  refIndex: string
  exists: boolean
}

export function useConfirmationNavigation(projectId: Ref<string>) {
  /**
   * 构建跳转目标
   * - 差异索引 → D0-4
   * - 替代索引 → D0-5 或 D0-6
   */
  function buildTargets(diffRef?: string, altRef?: string): NavigationTarget[] {
    const targets: NavigationTarget[] = []

    if (diffRef) {
      targets.push({
        label: '差异调节表',
        wpCode: 'D0-4',
        refIndex: diffRef,
        exists: true, // 桩：后续接入 addressRegistry 查询
      })
    }

    if (altRef) {
      targets.push({
        label: '替代程序',
        wpCode: 'D0-5', // 默认指向 D0-5，后续可根据 account_type 决定 D0-5 或 D0-6
        refIndex: altRef,
        exists: true,
      })
    }

    return targets
  }

  /**
   * 执行跳转（调用路由导航）
   * 桩实现：后续接入 router.push 或 addressRegistry.jump()
   */
  function navigateTo(target: NavigationTarget) {
    // Future: router.push({
    //   name: 'workpaper-detail',
    //   params: { projectId: projectId.value, wpCode: target.wpCode },
    //   query: { ref: target.refIndex }
    // })
    console.log(`[ConfirmationNav] Jump to ${target.wpCode} ref=${target.refIndex}`)
  }

  return { buildTargets, navigateTo }
}
