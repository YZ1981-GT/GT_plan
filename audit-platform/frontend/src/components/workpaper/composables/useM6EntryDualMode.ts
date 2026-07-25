/**
 * useM6EntryDualMode — M6 未分配利润入口级 HTML ↔ OnlyOffice 双模式
 *
 * 复用共享 useWorkpaperEntryDualMode（健康门控"拉取成功才切"），
 * 提供 M6 内部 sheet code → 源 xlsx tab 名解析逻辑（对齐 useM1EntryDualMode 范式）。
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type M6RenderMode = WorkpaperRenderMode

/**
 * M6 内部 sheet code（GtM6RetainedEarnings.currentSheet 的取值）→ 源 xlsx tab 名映射。
 * tab 名与源 xlsx 完全一致，供 OnlyOffice 精确定位工作表。
 *
 * 注：index/procedure/skip-q6a 不参与双模式，故不在此映射中。
 */
const M6_SHEET_MAP: Record<string, string> = {
  'M6-1': '审定表M6-1',
  'M6-2': '明细表M6-2',
  'M6-3': '调整分录汇总M6-3',
  'M6-4': '未分配利润检查表M6-4',
  'disclosure-listed': '附注披露信息（上市公司）',
  'disclosure-soe': '附注披露信息（国有企业）',
}

export function useM6EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      return M6_SHEET_MAP[code] || code || '审定表M6-1'
    },
  })
}

export default useM6EntryDualMode
