/** G8-1 审定表行定义 — source: G8.xlsx 审定表G8-1 + wp_fine_rules detail_discovery */

import { G8_ADJUDICATION_SCHEMA_LABELS } from './g8SchemaRows'

export interface G8AdjudicationLineDef {
  rowKey: string
  label: string
  group: 'fair_value'
}

export const G8_GROUP_LABEL = '公允价值'

/** 10 行：单分组公允价值计量（xlsx rows 8-17） */
export const G8_ADJUDICATION_ITEMS: G8AdjudicationLineDef[] = G8_ADJUDICATION_SCHEMA_LABELS.map(
  (label, i) => ({
    rowKey: `fv_${i + 1}`,
    label,
    group: 'fair_value' as const,
  }),
)
