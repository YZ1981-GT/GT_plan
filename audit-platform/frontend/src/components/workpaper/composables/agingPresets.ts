/**
 * agingPresets.ts — 全局账龄段预设定义（3年段/5年段/自定义）
 *
 * 供所有往来科目审定表(D1/D2/D3/F1/F4/K1/K3/G5等)的按账龄分类区块使用。
 * 明细表(X-2)的账龄列使用 useAgingConfig（项目级配置），审定表(X-1)使用本文件预设。
 * 两者应保持一致：审定表预设切换时同步更新项目配置。
 */

export type AgingPresetType = 'THREE_YEAR' | 'FIVE_YEAR' | 'CUSTOM'

export interface AgingRowDef {
  rowKey: string
  label: string
}

/** 3年段预设（默认） */
export const AGING_ROWS_3YEAR: AgingRowDef[] = [
  { rowKey: 'within-1-year', label: '1年以内（含1年）' },
  { rowKey: '1-to-2-years', label: '1至2年（含2年）' },
  { rowKey: '2-to-3-years', label: '2至3年（含3年）' },
  { rowKey: 'over-3-years', label: '3年以上' },
]

/** 5年段预设 */
export const AGING_ROWS_5YEAR: AgingRowDef[] = [
  { rowKey: 'within-1-year', label: '1年以内（含1年）' },
  { rowKey: '1-to-2-years', label: '1至2年（含2年）' },
  { rowKey: '2-to-3-years', label: '2至3年（含3年）' },
  { rowKey: '3-to-4-years', label: '3至4年（含4年）' },
  { rowKey: '4-to-5-years', label: '4至5年（含5年）' },
  { rowKey: 'over-5-years', label: '5年以上' },
]

/** 根据预设类型获取行定义 */
export function getAgingRowsByPreset(preset: AgingPresetType, customRows?: AgingRowDef[]): AgingRowDef[] {
  if (preset === 'FIVE_YEAR') return AGING_ROWS_5YEAR
  if (preset === 'CUSTOM' && customRows?.length) return customRows
  return AGING_ROWS_3YEAR
}

/** 从用户输入文本（每行一个）解析自定义行 */
export function parseCustomAgingRows(text: string): AgingRowDef[] {
  return text
    .split('\n')
    .map(l => l.trim())
    .filter(Boolean)
    .map((label, i) => ({ rowKey: `custom-${i}`, label }))
}
