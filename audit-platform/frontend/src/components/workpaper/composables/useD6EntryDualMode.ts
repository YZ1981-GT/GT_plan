/**
 * useD6EntryDualMode — D6 入口级 HTML ↔ OnlyOffice 双模式
 */
import { type Ref } from 'vue'
import { resolveD6SheetLabel } from './d6SheetLabels'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type D6RenderMode = WorkpaperRenderMode

export function useD6EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  availableSheets: Ref<Array<{ sheet_name?: string }>>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, availableSheets, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      if (code === 'D6' || code === 'skip' || code === 'directory') return '底稿目录'
      if (code === '附注上市') return resolveD6SheetLabel('D6-附注上市', availableSheets.value)
      if (code === '附注国企') return resolveD6SheetLabel('D6-附注国企', availableSheets.value)
      return resolveD6SheetLabel(code, availableSheets.value) || code
    },
  })
}

export default useD6EntryDualMode
