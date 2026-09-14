/**
 * useM3EntryDualMode — M3 库存股入口级 HTML ↔ OnlyOffice 双模式
 *
 * 复用共享 useWorkpaperEntryDualMode（健康门控"拉取成功才切"），
 * 提供 M3 内部 sheet code → 源 xlsx tab 名解析逻辑（对齐 useM1EntryDualMode 范式）。
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type M3RenderMode = WorkpaperRenderMode

/**
 * M3 内部 sheet code（GtM3TreasuryStock.currentSheet 的取值）→ 源 xlsx tab 名映射。
 * tab 名与源 xlsx 完全一致，供 OnlyOffice 精确定位工作表。
 */
const M3_SHEET_MAP: Record<string, string> = {
  index: '底稿目录',
  procedure: '库存股实质性程序表M3A',
  'M3-1': '审定表M3-1',
  'disclosure-listed': '附注披露信息（上市公司）',
  'M3-2': '明细表M3-2',
  'M3-3': '调整分录汇总M3-3',
  'M3-4': '外币投资汇率测算表M3-4',
  'M3-5': '库存股检查表M3-5',
}

export function useM3EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      return M3_SHEET_MAP[code] || code || '审定表M3-1'
    },
  })
}

export default useM3EntryDualMode
