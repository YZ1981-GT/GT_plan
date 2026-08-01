import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type N2RenderMode = WorkpaperRenderMode

export function useN2DualMode(options: {
  currentSheet: Ref<string>
  sheetName: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  return useWorkpaperEntryDualMode({
    reloadAllResponses: options.reloadAllResponses,
    resolveOoSheetName: () => options.sheetName.value?.trim() || options.currentSheet.value || 'N2',
  })
}

export default useN2DualMode
