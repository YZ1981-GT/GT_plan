/**
 * useM7EntryDualMode — M7 专项储备入口级 HTML ↔ OnlyOffice 双模式
 *
 * 复用共享 useWorkpaperEntryDualMode（健康门控"拉取成功才切"），
 * 提供 M7 内部 sheet code → 源 xlsx tab 名解析逻辑（对齐 useM1EntryDualMode 范式）。
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type M7RenderMode = WorkpaperRenderMode

/**
 * M7 内部 sheet code（GtM7SpecialReserve.currentSheet 的取值）→ 源 xlsx tab 名映射。
 * tab 名与源 xlsx 完全一致，供 OnlyOffice 精确定位工作表。
 */
const M7_SHEET_MAP: Record<string, string> = {
  index: '底稿目录',
  procedure: '专项储备实质性程序表M7A',
  'M7-1': '审定表M7-1',
  'M7-2': '明细表M7-2',
  'M7-3': '调整分录汇总M7-3',
  'M7-4': '专项储备计提测试表M7-4',
  'M7-5': '专项储备支出检查表M7-5',
  'disclosure-listed': '附注披露信息（上市公司）',
  'disclosure-soe': '附注披露信息（国有企业）',
}

export function useM7EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      return M7_SHEET_MAP[code] || code || '审定表M7-1'
    },
  })
}

export default useM7EntryDualMode
