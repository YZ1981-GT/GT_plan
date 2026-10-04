/**
 * 公式管理「公式推送」面板的展示逻辑（纯函数，全中文）。
 *
 * spec: chain-closure-phase2-formula-push-engine · 任务 14 · 需求 1.4 / 3.4
 * 载荷形状 = backend/app/routers/formula_push.py（rules / latest / states）。
 */

export interface PushRuleView {
  rule_id: string
  stage: string
  policy: string
  triggers: string[]
  description: string
  formula: string
  target: { domain: string; sheet_code?: string | null; item_id?: string | null; sections?: Record<string, string> }
}

export interface PushStateView {
  addr_id: string
  rule_id: string
  domain: string
  state: string
  current_value: unknown
  formula_value: unknown
  differs: boolean
  updated_at: string | null
}

export const STAGE_LABELS: Record<string, string> = { source: '源值', derived: '派生', note: '附注' }
export const POLICY_LABELS: Record<string, string> = {
  system: '系统值（总是跟随公式）',
  derived: '派生值（总是跟随公式）',
  editable: '可编辑（人工改过则保留）',
}
export const TRIGGER_LABELS: Record<string, string> = {
  TRIAL_BALANCE_UPDATED: '试算表更新',
  WORKPAPER_SAVED: '底稿保存',
  manual: '手动',
}
export const STATE_LABELS: Record<string, string> = {
  auto: '自动',
  manual: '人工修改',
  locked: '已锁定',
  pending_confirm: '待确认',
}
export const RUN_STATUS_LABELS: Record<string, string> = {
  running: '进行中',
  succeeded: '成功',
  partial: '部分成功（有并发修改）',
  failed: '失败',
}
const RUN_STATUS_TAG: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
  succeeded: 'success',
  partial: 'warning',
  failed: 'danger',
  running: 'info',
}

/** 运行状态对应的标签颜色。 */
export function runStatusTag(status: string | null | undefined): 'success' | 'warning' | 'danger' | 'info' {
  return (status && RUN_STATUS_TAG[status]) || 'info'
}

export function labelOf(map: Record<string, string>, key: string | null | undefined): string {
  return (key && map[key]) || key || '—'
}

export function triggersText(triggers: readonly string[]): string {
  return triggers.map((t) => labelOf(TRIGGER_LABELS, t)).join('、')
}

/** 目标位置（中文）：底稿「E1 / E1-1 / 条目」或附注「五、1 货币资金」。 */
export function targetText(rule: PushRuleView): string {
  const t = rule.target
  if (t.domain === 'note') {
    const sections = Object.entries(t.sections || {}).map(([k, v]) => `${k === 'listed' ? '上市' : '国企'} ${v}`)
    return `附注 ${sections.join(' / ')}`
  }
  return `底稿 ${t.sheet_code || ''} ${t.item_id || ''}`.trim()
}

/** 数值展示：数值按千分位两位小数，空 = 「（空）」，其余原样。 */
export function valueText(value: unknown): string {
  if (value === null || value === undefined || (typeof value === 'string' && value.trim() === '')) return '（空）'
  const n = typeof value === 'number' ? value : Number(value)
  if (Number.isFinite(n)) {
    return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(value)
}

/** 待处理差异：人工修改 / 待确认 / 锁定且有差异（自动态有差异 = 下次推送会跟随，不列）。 */
export function pendingStates(states: readonly PushStateView[]): PushStateView[] {
  return states.filter((s) => s.state !== 'auto' && s.differs)
}

/** 面板能对哪些目标做「采用 / 锁定」：只有底稿可编辑目标（附注以附注自身标记为准，后端同样拒绝）。 */
export function actionable(state: PushStateView): boolean {
  return state.domain === 'workpaper'
}
