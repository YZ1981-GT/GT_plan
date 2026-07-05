/**
 * useD1EntryDualMode — D1 入口级 HTML ↔ OnlyOffice 双模式
 */
import { type Ref } from 'vue'
import { resolveD1SheetLabel, getSheetNameFromD1Code } from './d1SheetLabels'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type D1RenderMode = WorkpaperRenderMode

export function useD1EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  availableSheets?: Ref<Array<{ sheet_name?: string }>>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, availableSheets, reloadAllResponses } = options

  const dual = useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      if (code === 'D1' || code === 'skip' || code === 'directory') return '底稿目录'
      if (code === '附注上市') return resolveD1SheetLabel('D1-附注上市', availableSheets?.value)
      if (code === '附注国企') return resolveD1SheetLabel('D1-附注国企', availableSheets?.value)
      return resolveD1SheetLabel(code, availableSheets?.value) || code
    },
  })

  return {
    ...dual,
    getSheetNameFromCode: getSheetNameFromD1Code,
    ooSheetName: () => getSheetNameFromD1Code(currentSheet.value),
  }
}

export default useD1EntryDualMode
