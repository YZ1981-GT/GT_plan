/**
 * useJ1EntryDualMode — J1 应付职工薪酬入口级 HTML ↔ OnlyOffice 双模式
 *
 * 复用共享 useWorkpaperEntryDualMode，提供 J1 sheet 名解析逻辑。
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type J1RenderMode = WorkpaperRenderMode

/**
 * J1 内部 sheet code → 源 xlsx tab 名映射
 */
const J1_SHEET_MAP: Record<string, string> = {
  'J1-index': 'J1-目录',
  'J1A': 'J1A',
  'J1-1': 'J1-1',
  'J1-2': 'J1-2',
  'J1-3': 'J1-3',
  'J1-4': 'J1-4',
  'J1-5': 'J1-5',
  'J1-6': 'J1-6',
  'J1-7': 'J1-7',
  'J1-8': 'J1-8',
  'J1-9': 'J1-9',
  'J1-10': 'J1-10',
  'J1附注(上市)': 'J1附注(上市)',
  'J1附注(国企)': 'J1附注(国企)',
  'IPO-tips': 'IPO薪酬审计提示',
}

export function useJ1EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      return J1_SHEET_MAP[code] || code || 'J1-1'
    },
  })
}

export default useJ1EntryDualMode
