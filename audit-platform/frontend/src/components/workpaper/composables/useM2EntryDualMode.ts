/**
 * useM2EntryDualMode — M2 实收资本（股本）入口级 HTML ↔ OnlyOffice 双模式
 *
 * 复用共享 useWorkpaperEntryDualMode（健康门控"拉取成功才切"），
 * 提供 M2 内部 sheet code → 源 xlsx tab 名解析逻辑（对齐 useM1EntryDualMode/useJ1EntryDualMode 范式）。
 */
import { type Ref } from 'vue'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './useWorkpaperEntryDualMode'

export type M2RenderMode = WorkpaperRenderMode

/**
 * M2 内部 sheet code（GtM2PaidInCapital.currentSheet 的取值）→ 源 xlsx tab 名映射。
 * tab 名与源 xlsx 完全一致，供 OnlyOffice 精确定位工作表。
 */
const M2_SHEET_MAP: Record<string, string> = {
  index: '底稿目录',
  // 🔴 MC-23 修正：真名含前导空格 + 中间空格，禁 strip（MC-10）
  procedure: ' 实收资本实质性程序表 M2A',
  'M2-1': '审定表M2-1',
  'disclosure-listed': '附注披露信息（上市公司）',
  'disclosure-soe': '附注披露信息（国有企业）',
  // 🔴 MC-23 修正：真名含「（上市公司）」限定，原值整段不同
  'M2-2': '明细表（上市公司）M2-2',
  'M2-3': '调整分录汇总M2-3',
  'M2-4': '外币投资汇率测算表M2-4',
  // 🔴 MC-23 修正：真名含「实收资本（股本）」前缀，原值整段不同
  'M2-5': '实收资本（股本）检查表M2-5',
}

export function useM2EntryDualMode(options: {
  wpId: Ref<string>
  currentSheet: Ref<string>
  reloadAllResponses: () => Promise<void>
}) {
  const { currentSheet, reloadAllResponses } = options

  return useWorkpaperEntryDualMode({
    reloadAllResponses,
    resolveOoSheetName: () => {
      const code = currentSheet.value
      // 已迁移 HTML sheet 映射到源 tab 名；未匹配（fallback）时 code 本身即 GtWpRenderer 传入的原始 sheet 名。
      return M2_SHEET_MAP[code] || code || '审定表M2-1'
    },
  })
}

export default useM2EntryDualMode
