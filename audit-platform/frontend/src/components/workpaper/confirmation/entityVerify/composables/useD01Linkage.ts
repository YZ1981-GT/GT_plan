/**
 * useD01Linkage — D0-1 跨底稿联动 stub
 *
 * 通过 confirm_index 关联 D0-1 函证汇总表，提供跳转导航能力。
 * TODO: 接入真实路由 + EventBus 跨底稿跳转
 */
import { ref } from 'vue'

export interface D01LinkageReturn {
  /** 跳转到 D0-1 对应索引行 */
  navigateToD01: (confirmIndex: string) => void
  /** 是否正在跳转 */
  isNavigating: ReturnType<typeof ref<boolean>>
}

export function useD01Linkage(): D01LinkageReturn {
  const isNavigating = ref(false)

  function navigateToD01(confirmIndex: string) {
    if (!confirmIndex) return
    isNavigating.value = true
    // Stub: 实际实现通过 EventBus 或 router 跳转到 D0-1 底稿对应行
    console.info(`[D01Linkage] Navigate to D0-1, confirm_index=${confirmIndex}`)
    // Simulate async navigation
    setTimeout(() => {
      isNavigating.value = false
    }, 300)
  }

  return {
    navigateToD01,
    isNavigating,
  }
}
