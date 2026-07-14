/**
 * useJ3EntryDualMode — J3 股份支付入口级 HTML ↔ OnlyOffice 双模式
 *
 * 复用共享 useWorkpaperEntryDualMode，提供 J3 sheet 名解析逻辑。
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type J3RenderMode = WorkpaperRenderMode

/**
 * J3 内部 sheet code → 源 xlsx tab 名映射
 */
const J3_SHEET_MAP: Record<string, string> = {
  'J3': 'J3-目录',
  'J3A': 'J3A',
  'J3-1': 'J3-1',
  'J3-2': 'J3-2',
}

export function useJ3EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      return J3_SHEET_MAP[code] || code || 'J3-1'
    },
  })
}

export default useJ3EntryDualMode
