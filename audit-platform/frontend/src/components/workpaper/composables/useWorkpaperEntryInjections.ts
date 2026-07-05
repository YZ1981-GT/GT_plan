/**
 * useWorkpaperEntryInjections — 底稿入口 shell 通用 provide（jumpToSection + reloadWorkpaperData）
 */
import { provide } from 'vue'

export function useWorkpaperEntryInjections(options: {
  onJumpToSection: (sheetLabel: string) => void
  reloadFn: () => Promise<void> | void
}) {
  function jumpToSection(sheetLabel: string): void {
    options.onJumpToSection(sheetLabel)
  }

  provide('jumpToSection', jumpToSection)
  provide('reloadWorkpaperData', () => options.reloadFn())

  return { jumpToSection }
}

export default useWorkpaperEntryInjections
