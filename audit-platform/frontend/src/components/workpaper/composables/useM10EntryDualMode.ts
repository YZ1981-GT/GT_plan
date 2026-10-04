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
  // 🔴 MC-23 修正：真名含中间空格，禁 strip（MC-10）
  procedure: '其他权益工具实质性程序表 M10A',
  'M10-1': '审定表M10-1',
  'M10-2': '明细表M10-2',
  'M10-3': '调整分录汇总M10-3',
  'M10-4': '负债与权益区分检查表M10-4',
  'M10-5': '其他权益工具检查表M10-5',
  // 🔴 MC-23 + MC-25 修正：M10 真名为「核对」非「披露信息」，且国企用「国企」非「国有企业」
  // 原值来自已归档 spec m10-other-equity-instruments 的错误记录（BP-12 同源）
  'disclosure-listed': '附注披露信息核对（上市公司）',
  'disclosure-soe': '附注披露信息核对（国企）',
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
