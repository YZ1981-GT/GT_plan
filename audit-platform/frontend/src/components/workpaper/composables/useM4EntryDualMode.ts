/**
 * useM4EntryDualMode — M4 资本公积入口级 HTML ↔ OnlyOffice 双模式
 *
 * 复用共享 useWorkpaperEntryDualMode（健康门控"拉取成功才切"），
 * 提供 M4 内部 sheet code → 源 xlsx tab 名解析逻辑（对齐 useM1EntryDualMode 范式）。
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type M4RenderMode = WorkpaperRenderMode

/**
 * M4 内部 sheet code（GtM4CapitalReserve.currentSheet 的取值）→ 源 xlsx tab 名映射。
 * tab 名与源 xlsx 完全一致，供 OnlyOffice 精确定位工作表。
 */
const M4_SHEET_MAP: Record<string, string> = {
  index: '底稿目录',
  procedure: '资本公积实质性程序表M4A',
  'M4-1': '审定表M4-1',
  'M4-2': '明细表M4-2',
  'M4-3': '调整分录汇总M4-3',
  'M4-4': '资本公积检查表M4-4',
  'disclosure-listed': '附注披露信息（上市公司）',
  'disclosure-soe': '附注披露信息（国有企业）',
}

export function useM4EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      return M4_SHEET_MAP[code] || code || '审定表M4-1'
    },
  })
}

export default useM4EntryDualMode
