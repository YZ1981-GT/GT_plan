/**
 * useM9EntryDualMode — M9 其他综合收益入口级 HTML ↔ OnlyOffice 双模式
 *
 * 复用共享 useWorkpaperEntryDualMode（健康门控"拉取成功才切"），
 * 提供 M9 内部 sheet code → 源 xlsx tab 名解析逻辑（对齐 useM1EntryDualMode 范式）。
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type M9RenderMode = WorkpaperRenderMode

/**
 * M9 内部 sheet code（GtM9OtherComprehensiveIncome.currentSheet 的取值）→ 源 xlsx tab 名映射。
 * tab 名与源 xlsx 完全一致，供 OnlyOffice 精确定位工作表。
 */
const M9_SHEET_MAP: Record<string, string> = {
  index: '底稿目录',
  procedure: '其他综合收益实质性程序表M9A',
  'M9-1': '审定表M9-1',
  'M9-2': '明细表M9-2',
  'M9-3': '调整分录汇总M9-3',
  'M9-4': 'OCI核对表M9-4',
  'disclosure-listed': '附注披露信息（上市公司）',
  'disclosure-soe': '附注披露信息（国有企业）',
}

export function useM9EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      return M9_SHEET_MAP[code] || code || '审定表M9-1'
    },
  })
}

export default useM9EntryDualMode
