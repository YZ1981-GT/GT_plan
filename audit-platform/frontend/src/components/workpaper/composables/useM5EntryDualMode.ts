/**
 * useM5EntryDualMode — M5 盈余公积入口级 HTML ↔ OnlyOffice 双模式
 *
 * 复用共享 useWorkpaperEntryDualMode（健康门控"拉取成功才切"），
 * 提供 M5 内部 sheet code → 源 xlsx tab 名解析逻辑（对齐 useM1EntryDualMode 范式）。
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type M5RenderMode = WorkpaperRenderMode

/**
 * M5 内部 sheet code（GtM5SurplusReserve.currentSheet 的取值）→ 源 xlsx tab 名映射。
 * tab 名与源 xlsx 完全一致，供 OnlyOffice 精确定位工作表。
 */
const M5_SHEET_MAP: Record<string, string> = {
  index: '底稿目录',
  procedure: '盈余公积实质性程序表 M5A',
  'M5-1': '审定表M5-1',
  'disclosure-listed': '附注披露信息（上市公司）',
  'disclosure-soe': '附注披露信息（国有企业）',
  'M5-2': '明细表M5-2',
  'M5-3': '调整分录汇总M5-3',
  'M5-4': '盈余公积计提检查表M5-4',
  'M5-5': '盈余公积检查表M5-5',
}

export function useM5EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      return M5_SHEET_MAP[code] || code || '审定表M5-1'
    },
  })
}

export default useM5EntryDualMode
