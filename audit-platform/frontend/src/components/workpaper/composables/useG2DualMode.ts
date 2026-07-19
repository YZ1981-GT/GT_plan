/**
 * useG2DualMode — G2 应收利息 HTML ↔ OnlyOffice 双模式
 *
 * 对齐 D4 useD4EntryDualMode：复用 useWorkpaperEntryDualMode，目录页 OO 解析到业务 sheet。
 */
import { computed, type Ref } from 'vue'
import { resolveG2SheetLabel } from './g2SheetLabels'
import { dualModeHtmlOoOptions } from './dualModeLabels'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type G2RenderMode = WorkpaperRenderMode

export function useG2DualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  availableSheets: Ref<Array<{ sheet_name?: string }>>
  sheetName?: Ref<string>
  reloadAll: () => Promise<void>
}) {
  const { currentSheet, availableSheets, sheetName, reloadAll } = options

  const dual = useWorkpaperEntryDualMode({
    reloadAllResponses: reloadAll,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      // 目录页不对 OnlyOffice 传「底稿目录」——对齐 D4（directory → D4）与后端 preferred skip
      if (!code || code === '底稿目录') {
        return (
          resolveG2SheetLabel('G2A', availableSheets.value, sheetName?.value)
          || resolveG2SheetLabel('G2-1', availableSheets.value)
          || '应收利息实质性程序表G2A'
        )
      }
      return resolveG2SheetLabel(code, availableSheets.value, sheetName?.value) || code
    },
  })

  function onModeChange(val: string | number | boolean): void {
    void dual.switchMode(val as G2RenderMode)
  }

  function onOoFallback(): void {
    void dual.switchMode('html')
  }

  return {
    currentMode: dual.mode,
    isOoAvailable: dual.ooAvailable,
    checking: dual.checking,
    modeOptions: computed(() => dualModeHtmlOoOptions({ onlineDisabled: !dual.ooAvailable.value })),
    switchMode: dual.switchMode,
    onModeChange,
    checkOOHealth: dual.checkOOHealth,
    resolveOoSheetName: dual.resolveOoSheetName,
    onOoFallback,
  }
}

export default useG2DualMode
