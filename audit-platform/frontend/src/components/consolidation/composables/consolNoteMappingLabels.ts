/**
 * 合并附注明细映射弹窗：建议行的就绪判定与匹配方式中文名（spec note-pull-header-formula-closure R6.2）。
 *
 * 就绪 = 后端判为可自动确认（`auto_confirmable`：下推行 / 精确 / 别名 / 通用别名 / 历史，且有目标行）。
 * 原先「有建议目标就算就绪」⇒ 模糊匹配、上年规则这类需要看一眼的建议也显示「就绪」。
 * （「规则模板」一级随 V202 规则模板库退役，后端不再给出，spec note-pull-followup-closure R16。）
 */

export interface MappingSuggestionLike {
  suggested_target?: { target_row_id?: string } | null
  auto_confirmable?: boolean
  match_type?: string
}

/** 弹窗行状态：可自动确认的为「就绪」，其余「待确认」。 */
export function suggestionStatus(s: MappingSuggestionLike): 'ready' | 'pending' {
  return s.auto_confirmable === true && !!s.suggested_target?.target_row_id ? 'ready' : 'pending'
}

const MATCH_TYPE_LABELS: Record<string, string> = {
  exact_id: '下推行',
  exact: '精确',
  alias: '别名',
  global_alias: '通用别名',
  previous_year: '上年',
  history: '历史',
  fuzzy: '模糊',
  // 同名行只能按第几次出现配对（分组对不上，spec note-chain-followup-optimizations R3）：须人工复核
  position: '按位置',
  manual: '手动',
}

/** 同名行的位置说明：按分组（「二、累计折旧合计」下、组内第 2 行）或按第几次出现（旧规则）；只出现一次的行没有。 */
export function sourceRowPlace(row: {
  source_group?: string | null
  source_group_label?: string | null
  source_group_occurrence?: number | null
  source_occurrence?: number | null
}): string {
  if (row.source_group != null) {
    const where = row.source_group_label ? `「${row.source_group_label}」下` : '顶层'
    return row.source_group_occurrence ? `${where}第 ${row.source_group_occurrence + 1} 行` : where
  }
  return row.source_occurrence != null ? `同名第 ${row.source_occurrence + 1} 行` : ''
}

/** 匹配方式中文名（未登记的值显示「其他」，不把英文代码露给用户）。 */
export function matchTypeLabel(matchType: string | null | undefined): string {
  if (!matchType) return '手动'
  return MATCH_TYPE_LABELS[matchType] ?? '其他'
}

/** 匹配方式标签颜色：可自动确认的绿 / 蓝，需要看一眼的橙，未匹配灰。 */
export function matchTypeTagType(matchType: string | null | undefined): 'success' | 'primary' | 'warning' | 'info' {
  if (matchType === 'exact_id' || matchType === 'exact') return 'success'
  if (matchType === 'alias' || matchType === 'global_alias' || matchType === 'history') return 'primary'
  if (matchType === 'previous_year' || matchType === 'fuzzy' || matchType === 'position') return 'warning'
  return 'info'
}
