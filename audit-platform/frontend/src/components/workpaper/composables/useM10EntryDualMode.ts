/**
 * useM10EntryDualMode — M10 其他权益工具入口级 HTML ↔ OnlyOffice 双模式
 *
 * 复用共享 useWorkpaperEntryDualMode（健康门控"拉取成功才切"），
 * 提供 M10 内部 sheet code → 源 xlsx tab 名解析逻辑（对齐 useM1EntryDualMode 范式）。
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type M10RenderMode = WorkpaperRenderMode

/**
 * M10 内部 sheet code（GtM10OtherEquityInstruments.currentSheet 的取值）→ 源 xlsx tab 名映射。
 * tab 名与源 xlsx 完全一致，供 OnlyOffice 精确定位工作表。
 */
const M10_SHEET_MAP: Record<string, string> = {
  index: '底稿目录',
  procedure: '其他权益工具实质性程序表M10A',
  'M10-1': '审定表M10-1',
  'M10-2': '明细表M10-2',
  'M10-3': '调整分录汇总M10-3',
  'M10-4': '负债与权益区分检查表M10-4',
  'M10-5': '其他权益工具检查表M10-5',
  'disclosure-listed': '附注披露信息（上市公司）',
  'disclosure-soe': '附注披露信息（国有企业）',
}

export function useM10EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      return M10_SHEET_MAP[code] || code || '审定表M10-1'
    },
  })
}

export default useM10EntryDualMode
