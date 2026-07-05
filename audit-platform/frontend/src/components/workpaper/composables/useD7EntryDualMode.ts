/**
 * useD7EntryDualMode — D7 入口级 HTML ↔ OnlyOffice 双模式
 */
import { type Ref } from 'vue'
import { resolveD7SheetLabel } from './d7SheetLabels'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type D7RenderMode = WorkpaperRenderMode

export function useD7EntryDualMode(options: {
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
      if (code === 'D7' || code === 'skip' || code === 'directory') return '底稿目录'
      if (code === '附注上市') return resolveD7SheetLabel('D7-附注上市', availableSheets.value)
      if (code === '附注国企') return resolveD7SheetLabel('D7-附注国企', availableSheets.value)
      return resolveD7SheetLabel(code, availableSheets.value) || code
    },
  })
}

export default useD7EntryDualMode
