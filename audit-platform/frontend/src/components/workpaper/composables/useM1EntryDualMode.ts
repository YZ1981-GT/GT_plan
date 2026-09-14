/**
 * useM1EntryDualMode — M1 应付股利（利润）入口级 HTML ↔ OnlyOffice 双模式
 *
 * 复用共享 useWorkpaperEntryDualMode（健康门控"拉取成功才切"），
 * 提供 M1 内部 sheet code → 源 xlsx tab 名解析逻辑（对齐 useJ1EntryDualMode 范式）。
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type M1RenderMode = WorkpaperRenderMode

/**
 * M1 内部 sheet code（GtM1DividendsPayable.currentSheet 的取值）→ 源 xlsx tab 名映射。
 * tab 名与源 xlsx 完全一致，供 OnlyOffice 精确定位工作表。
 */
const M1_SHEET_MAP: Record<string, string> = {
  index: '底稿目录',
  procedure: '应付股利实质性程序表M1',
  'M1-1': '审定表M1-1',
  'disclosure-listed': '附注披露信息（上市公司）',
  'disclosure-soe': '附注披露信息（国有企业）',
  'M1-2': '明细表M1-2',
  'M1-3': '调整分录汇总M1-3',
  'M1-4': '外币汇率测算表M1-4',
  'M1-5': '应付股利（利润）测算表M1-5',
  'M1-6': '应付股利（利润）检查表M1-6',
}

export function useM1EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      return M1_SHEET_MAP[code] || code || '审定表M1-1'
    },
  })
}

export default useM1EntryDualMode
