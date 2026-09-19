/**
 * useD3EntryDualMode — D3 入口级 HTML ↔ OnlyOffice 双模式
 */
import { type Ref } from 'vue'
import { resolveD3SheetLabel } from './d3SheetLabels'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type D3RenderMode = WorkpaperRenderMode

export function useD3EntryDualMode(options: {
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
      if (code === 'directory' || code === 'D3' || code === 'skip') return '底稿目录'
      if (code === '附注上市') return resolveD3SheetLabel('D3-附注上市', availableSheets.value)
      if (code === '附注国企') return resolveD3SheetLabel('D3-附注国企', availableSheets.value)
      return resolveD3SheetLabel(code, availableSheets.value) || code
    },
  })
}

export default useD3EntryDualMode
