/**
 * useWorkpaperEntryInjections — 底稿入口 shell 通用 provide（jumpToSection + reloadWorkpaperData）
 * 并监听版本回滚完成事件，刷新包内 checklist 内存态。
 */
import { onBeforeUnmount, onMounted, unref, provide, type Ref } from 'vue'

export function useWorkpaperEntryInjections(options: {
  onJumpToSection: (sheetLabel: string) => void
  reloadFn: () => Promise<void> | void
  /** 传入后：回滚成功会自动调用 reloadFn */
  wpId?: string | Ref<string>
}) {
  function jumpToSection(sheetLabel: string): void {
    options.onJumpToSection(sheetLabel)
  }

  provide('jumpToSection', jumpToSection)
  provide('reloadWorkpaperData', () => options.reloadFn())

  function onRollbackCompleted(ev: Event) {
    const detail = (ev as CustomEvent).detail || {}
    const eventWpId = String(detail.workpaperId || '')
    const selfWpId = options.wpId != null ? String(unref(options.wpId) || '') : ''
    if (!selfWpId || !eventWpId || eventWpId !== selfWpId) return
    void options.reloadFn()
  }

  if (options.wpId != null) {
    onMounted(() => {
      window.addEventListener('workpaper:rollback-completed', onRollbackCompleted)
    })
    onBeforeUnmount(() => {
      window.removeEventListener('workpaper:rollback-completed', onRollbackCompleted)
    })
  }

  return { jumpToSection }
}

export default useWorkpaperEntryInjections
