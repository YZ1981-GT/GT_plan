/**
 * useD4EntryDualMode — D4 入口级 HTML ↔ OnlyOffice 双模式
 */
import { type Ref } from 'vue'
import { resolveD4SheetLabel } from './d4SheetLabels'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type D4RenderMode = WorkpaperRenderMode

export function useD4EntryDualMode(options: {
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
      if (code === 'D4' || code === 'skip' || code === 'directory') return 'D4'
      return resolveD4SheetLabel(code, availableSheets.value) || code
    },
  })
}

export default useD4EntryDualMode
