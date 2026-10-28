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
  manual: '手动',
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
  if (matchType === 'previous_year' || matchType === 'fuzzy') return 'warning'
  return 'info'
}
