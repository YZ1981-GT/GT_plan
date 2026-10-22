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
  /** 本项目实际推送的来源公式（改写过即改写后的） */
  formula: string
  target: { domain: string; sheet_code?: string | null; item_id?: string | null; sections?: Record<string, string> }
  // ── 公式治理内核叠加（spec formula-governance-coverage-closure R2.8，后端 push_settings.rule_actions）──
  /** active / disabled（停用）/ invalid（有效定义已不可用，本次跳过） */
  status?: string
  issue?: string | null
  layer?: string
  layer_label?: string
  disabled?: boolean
  pending?: boolean
  /** 来源是公式：可改写（系统值 / 派生值不能停用，只能改写公式） */
  editable_formula?: boolean
  can_disable?: boolean
  has_local?: boolean
  local_version?: number | null
  /** 规则清单原文 */
  preset_formula?: string
}

export type RuleActionKey = 'rewrite' | 'disable' | 'enable' | 'restore'
export interface RuleAction {
  key: RuleActionKey
  label: string
  enabled: boolean
  /** 不可用原因（按钮悬停提示） */
  reason: string
  /** 启用：有本项目层 ⇒ 删除本项目层回到上游；否则在本项目层写「启用」 */
  via?: 'restore' | 'save'
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
  FORMULA_CONFIG_CHANGED: '公式规则变更',
}
type TagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'
/** 规则层级标签颜色（与公式管理中心层级同口径） */
const LAYER_TAG: Record<string, TagType> = {
  preset: 'info', global: 'primary', template: 'success', project: 'warning', pinned: 'danger',
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

export function layerTagType(layer: string | null | undefined): TagType {
  return (layer && LAYER_TAG[layer]) || 'info'
}

export function isRuleDisabled(rule: PushRuleView): boolean {
  return rule.status === 'disabled' || !!rule.disabled
}

/** 规则状态的中文标记（无异常返回空串）。 */
export function ruleStatusText(rule: PushRuleView): string {
  if (rule.status === 'invalid') return '定义失效，本次未推送'
  if (isRuleDisabled(rule)) return '已停用'
  return rule.pending ? '有待确认的上游变更' : ''
}

/**
 * 规则表每行的操作与不可用原因（后端规则：系统值 / 派生值不能停用；只有公式来源能改写）。
 * 已停用的规则只给「启用」：本项目层停用的删掉本项目层即回到上游，上游停用的在本项目层写启用。
 */
export function ruleActions(rule: PushRuleView, canEdit: boolean): RuleAction[] {
  const noEdit = canEdit ? '' : '需要本项目编辑权限'
  const off = isRuleDisabled(rule)
  const out: RuleAction[] = []
  if (rule.editable_formula && !off) out.push({ key: 'rewrite', label: '改写公式', enabled: canEdit, reason: noEdit })
  if (rule.can_disable) {
    out.push(off
      ? { key: 'enable', label: '启用', enabled: canEdit, reason: noEdit, via: rule.has_local ? 'restore' : 'save' }
      : { key: 'disable', label: '本项目停用', enabled: canEdit, reason: noEdit })
  }
  if (rule.has_local && !(off && rule.can_disable)) {
    out.push({ key: 'restore', label: '恢复上游', enabled: canEdit, reason: noEdit })
  }
  return out
}

/** 没有任何可用操作时的说明（派生值由引擎算、四表明细等只能启停）。 */
export function ruleReadonlyText(rule: PushRuleView): string {
  if (rule.policy === 'derived') return '派生值：由引擎按规则计算，只读'
  return '只读'
}
