/**
 * useM8EntryDualMode — M8 一般风险准备入口级 HTML ↔ OnlyOffice 双模式
 *
 * 复用共享 useWorkpaperEntryDualMode（健康门控"拉取成功才切"），
 * 提供 M8 内部 sheet code → 源 xlsx tab 名解析逻辑（对齐 useM1EntryDualMode 范式）。
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type M8RenderMode = WorkpaperRenderMode

/**
 * M8 内部 sheet code（GtM8GeneralRiskReserve.currentSheet 的取值）→ 源 xlsx tab 名映射。
 * tab 名与源 xlsx 完全一致，供 OnlyOffice 精确定位工作表。
 * 注意：procedure sheet 名首尾含空格（源 xlsx 原样），index/procedure 不参与双模式，
 * 仅为完整性登记；实际参与双模式的是 M8-1~M8-4 与两张附注。
 */
const M8_SHEET_MAP: Record<string, string> = {
  index: '底稿目录',
  procedure: '一般风险准备实质性程序表 M8A ',
  'M8-1': '审定表M8-1',
  'M8-2': '明细表M8-2',
  'M8-3': '调整分录汇总M8-3',
  'M8-4': '一般风险准备测试表M8-4',
  'disclosure-listed': '附注披露信息（上市公司）',
  'disclosure-soe': '附注披露信息（国有企业）',
}

export function useM8EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      return M8_SHEET_MAP[code] || code || '审定表M8-1'
    },
  })
}

export default useM8EntryDualMode
