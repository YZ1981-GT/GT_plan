/**
 * agingPresets.ts — 全局账龄段预设定义（3年段/5年段/自定义）
 *
 * 供所有往来科目审定表(D1/D2/D3/F1/F4/K1/K3/G5等)的按账龄分类区块使用。
 * 明细表(X-2)的账龄列使用 useAgingConfig（项目级配置），审定表(X-1)使用本文件预设。
 * 两者应保持一致：rowKey 采用 segment.key（within1 / y1to2 …），与 F1-2 跨表聚合对齐。
 */

export type AgingPresetType = 'THREE_YEAR' | 'FIVE_YEAR' | 'CUSTOM'

export interface AgingRowDef {
  rowKey: string
  label: string
}

/** 审定表 Excel 风格标签（半角括号，与底稿模板一致） */
export const ADJUDICATION_LABEL_BY_SEGMENT_KEY: Record<string, string> = {
  within1: '1年以内(含1年)',
  y1to2: '1至2年(含2年)',
  y2to3: '2至3年(含3年)',
  over3: '3年以上',
  y3to4: '3至4年(含4年)',
  y4to5: '4至5年(含5年)',
  over5: '5年以上',
}

/** 3年段预设（F1/D3 默认）— rowKey = useAgingConfig segment.key */
export const AGING_ROWS_3YEAR: AgingRowDef[] = [
  { rowKey: 'within1', label: ADJUDICATION_LABEL_BY_SEGMENT_KEY.within1 },
  { rowKey: 'y1to2', label: ADJUDICATION_LABEL_BY_SEGMENT_KEY.y1to2 },
  { rowKey: 'y2to3', label: ADJUDICATION_LABEL_BY_SEGMENT_KEY.y2to3 },
  { rowKey: 'over3', label: ADJUDICATION_LABEL_BY_SEGMENT_KEY.over3 },
]

/** 5年段预设 */
export const AGING_ROWS_5YEAR: AgingRowDef[] = [
  { rowKey: 'within1', label: ADJUDICATION_LABEL_BY_SEGMENT_KEY.within1 },
  { rowKey: 'y1to2', label: ADJUDICATION_LABEL_BY_SEGMENT_KEY.y1to2 },
  { rowKey: 'y2to3', label: ADJUDICATION_LABEL_BY_SEGMENT_KEY.y2to3 },
  { rowKey: 'y3to4', label: ADJUDICATION_LABEL_BY_SEGMENT_KEY.y3to4 },
  { rowKey: 'y4to5', label: ADJUDICATION_LABEL_BY_SEGMENT_KEY.y4to5 },
  { rowKey: 'over5', label: ADJUDICATION_LABEL_BY_SEGMENT_KEY.over5 },
]

/** 默认 THREE_YEAR 段 key（跨表聚合兜底） */
export const DEFAULT_AGING_SEGMENT_KEYS = AGING_ROWS_3YEAR.map(r => r.rowKey)

/** 根据预设类型获取行定义 */
export function getAgingRowsByPreset(preset: AgingPresetType, customRows?: AgingRowDef[]): AgingRowDef[] {
  if (preset === 'FIVE_YEAR') return AGING_ROWS_5YEAR
  if (preset === 'CUSTOM' && customRows?.length) return customRows
  return AGING_ROWS_3YEAR
}

/**
 * 由项目级 segments 生成审定表账龄行。
 * 优先使用 Excel 风格标签；自定义段回退 segment.label。
 */
export function resolveAdjudicationAgingRows(
  segments: Array<{ key: string; label: string }>,
): AgingRowDef[] {
  if (!segments.length) return AGING_ROWS_3YEAR
  return segments.map(seg => ({
    rowKey: seg.key,
    label: ADJUDICATION_LABEL_BY_SEGMENT_KEY[seg.key] || seg.label,
  }))
}

/** 从用户输入文本（每行一个）解析自定义行 */
export function parseCustomAgingRows(text: string): AgingRowDef[] {
  return text
    .split('\n')
    .map(l => l.trim())
    .filter(Boolean)
    .map((label, i) => ({ rowKey: `custom-${i}`, label }))
}

/** 段 key → 展示标签（审定表口径优先，否则用配置 label） */
export function resolveAgingLabel(
  key: string,
  segments?: Array<{ key: string; label: string }>,
): string {
  if (ADJUDICATION_LABEL_BY_SEGMENT_KEY[key]) return ADJUDICATION_LABEL_BY_SEGMENT_KEY[key]
  const hit = segments?.find(s => s.key === key)
  return hit?.label || key
}

/** 将 nested 账龄金额拼成「标签:金额」提示（F1-4/F1-6 导入用） */
export function formatAgingAmountHint(
  aging: Record<string, number> | undefined | null,
  segments?: Array<{ key: string; label: string }>,
): string {
  if (!aging || typeof aging !== 'object') return ''
  const parts: string[] = []
  for (const [k, v] of Object.entries(aging)) {
    const n = Number(v) || 0
    if (n !== 0) parts.push(`${resolveAgingLabel(k, segments)}:${n}`)
  }
  return parts.join('; ')
}
