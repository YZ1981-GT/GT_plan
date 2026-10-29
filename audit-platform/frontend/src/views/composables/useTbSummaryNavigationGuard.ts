import { onMounted, onUnmounted, type Ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElMessageBox } from 'element-plus'

interface TbSummaryNavigationState {
  dirty: Ref<boolean>
  errorMessage: Ref<string>
  flush: () => Promise<boolean>
  discard: () => void
}

type ConfirmDiscard = (message: string, action: string) => Promise<boolean>

async function defaultConfirmDiscard(message: string, action: string): Promise<boolean> {
  try {
    await ElMessageBox.confirm(
      `${message || '自动保存未完成'}。${action}将丢弃本地未保存修改，是否继续？`,
      '自动保存未完成',
      { type: 'warning', confirmButtonText: `仍要${action}`, cancelButtonText: '留在当前页面' },
    )
    return true
  } catch {
    return false
  }
}

export async function settleTbSummaryNavigation(
  state: TbSummaryNavigationState,
  action: string,
  confirmDiscard: ConfirmDiscard = defaultConfirmDiscard,
): Promise<boolean> {
  if (!state.dirty.value) return true
  if (await state.flush()) return true
  if (!await confirmDiscard(state.errorMessage.value, action)) return false
  state.discard()
  return true
}

export function useTbSummaryNavigationGuard(state: TbSummaryNavigationState) {
  const settle = (action: string) => settleTbSummaryNavigation(state, action)
  onBeforeRouteLeave(() => settle('离开页面'))
  onBeforeRouteUpdate(() => settle('切换项目或年度'))

  const beforeUnload = (event: BeforeUnloadEvent) => {
    if (!state.dirty.value) return
    event.preventDefault()
    event.returnValue = ''
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onUnmounted(() => window.removeEventListener('beforeunload', beforeUnload))
  return { settle }
}
