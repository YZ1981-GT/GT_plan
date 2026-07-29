/**
 * mapD01ReliabilityRow — 从 D0-1 汇总行映射为 D0-7 可靠性验证行
 *
 * 纯函数，可独立单测。
 * 映射字段：confirm_index / entity_name / reply_method / reply_date + _source:'auto'
 */
import type { SummaryRow } from '../../coordination/importFromSummary'

export interface PartialReliabilityRow {
  confirm_index?: string
  entity_name?: string
  reply_method?: string
  reply_date?: string
  _source?: string
}

/**
 * 映射 D0-1 汇总行 → D0-7 可靠性验证行
 */
export function mapSummaryToReliabilityRow(row: SummaryRow): PartialReliabilityRow {
  return {
    confirm_index: row.confirm_index || '',
    entity_name: row.entity_name || '',
    reply_method: String(row.reply_method || ''),
    reply_date: row.reply_date || '',
    _source: 'auto',
  }
}
