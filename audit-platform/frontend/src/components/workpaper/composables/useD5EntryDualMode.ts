/**
 * useD5EntryDualMode — D5 入口级 HTML ↔ OnlyOffice 双模式
 */
import { type Ref } from 'vue'
import { resolveD5SheetLabel } from './d5SheetLabels'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type D5RenderMode = WorkpaperRenderMode

export function useD5EntryDualMode(options: {
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
      if (code === 'D5' || code === 'skip' || code === 'directory') return '底稿目录'
      if (code === '附注上市') return resolveD5SheetLabel('D5-附注上市', availableSheets.value)
      if (code === '附注国企') return resolveD5SheetLabel('D5-附注国企', availableSheets.value)
      return resolveD5SheetLabel(code, availableSheets.value) || code
    },
  })
}

export default useD5EntryDualMode
