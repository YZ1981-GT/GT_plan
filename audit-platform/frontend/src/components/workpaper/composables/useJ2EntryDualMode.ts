/**
 * useJ2EntryDualMode — J2 设定受益计划入口级 HTML ↔ OnlyOffice 双模式
 *
 * 复用共享 useWorkpaperEntryDualMode，提供 J2 sheet 名解析逻辑。
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type J2RenderMode = WorkpaperRenderMode

/**
 * J2 内部 sheet code → 源 xlsx tab 名映射
 */
const J2_SHEET_MAP: Record<string, string> = {
  '底稿目录': 'J2-目录',
  'J2A': 'J2A',
  'J2-1': 'J2-1',
  'J2-2': 'J2-2',
  'J2-3': 'J2-3',
  'J2-4': 'J2-4',
  'J2附注(上市)': 'J2附注(上市)',
  'J2附注(国企)': 'J2附注(国企)',
}

export function useJ2EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      return J2_SHEET_MAP[code] || code || 'J2-1'
    },
  })
}

export default useJ2EntryDualMode
