/**
 * 公式全局设置 / 本项目适配 / 待确认 / 公式模板：类型 + 小工具（spec formula-global-settings-sync，design §11 / §16.6）。
 *
 * - 请求封装在 `services/formulaSettingsApi.ts`（本文件转出 `formulaSettingsApi`）；全部带 `_silent`，
 *   错误提示由调用方给，统一文案用 `formulaErrorText(e, 兜底)`。
 * - 冲突决策的键 = 预览条目的 `key`（服务端给出 `{域}|{项目id}|{公式位}`，公式位可含 `|`），原样回传、
 *   前端不拼接也不解析，与后端 `Decisions` 同口径（spec formula-hub-integrity-closure 需求 8.4）。
 * - 状态字面量比较集中在本文件（.vue 里写 `=== 'pending'` 会触发 no-status-string-literal）。
 */
import { ElMessage } from 'element-plus'
import { refIssueDetailText } from '@/utils/formulaRefIssues'

// ── 类型 ──────────────────────────────────────────────────────────────────────

export type Definition = Record<string, any>
export type ConflictChoice = 'adopt' | 'keep' | 'ask'
export type ProjectChoice = 'apply' | 'defer'
export type ResolutionChoice = 'adopt' | 'keep' | 'custom'
export type ApplyTargetKind = 'global' | 'candidate' | 'projects'
export type ShareScope = 'personal' | 'team' | 'group' | 'firm'

export interface DomainScopeOption { value: string; label: string }
export interface FormulaDomainInfo {
  key: string
  label: string
  scope_kind: string
  /** 消费方已改读有效定义（未接入的域只存不生效） */
  wired: boolean
  /** 未接入时后端给的中文说明（已接入不带） */
  wired_reason?: string
  scopes: DomainScopeOption[]
  exec_fields: string[]
  desc_fields: string[]
}
export interface GlobalSlot {
  slot_key: string
  label: string
  /** global = 全局设置；preset = 只有系统预设 */
  layer: string
  definition: Definition | null
  version: number | null
  structure?: Record<string, any> | null
}
export interface SlotChange {
  slot_key: string
  /** null = 删除该公式位 */
  definition: Definition | null
  expected_version?: number | null
  label?: string
  structure?: Record<string, any> | null
}
/** 同步预览的一条（项目 × 公式位）。全局发布 / 模板发布 / 订阅 / 退订 / 应用到指定项目同形。 */
export interface PlanItem {
  /** 冲突决策键（服务端给出，原样回传）：两个域的同名公式位 key 不同 */
  key: string
  project_id: string
  project_name: string
  project_status?: string
  frozen: boolean
  slot_key: string
  label: string
  category: string
  category_label: string
  domain?: string
  base_formula: string
  old_formula?: string
  new_formula: string
  local_formula: string
  base_definition?: Definition | null
  new_upstream?: Definition | null
  local_definition?: Definition | null
  local_version?: number | null
  new_origin?: string
  pinned?: boolean
  layer?: string
}
export interface ProjectSummary {
  project_id: string
  name: string
  status?: string
  frozen: boolean
  counts: Record<string, number>
  pending: number
  changed: boolean
}
export interface PreviewSummary {
  counts: Record<string, number>
  projects: ProjectSummary[]
  affected_project_count: number
  conflict_count: number
  pending_total: number
  changed_projects?: string[]
}
export interface ChangeRow {
  slot_key: string
  label: string
  old: Definition | null
  new: Definition | null
  old_version?: number | null
  new_version?: number | null
  deleted?: boolean
  domain?: string
}
export interface SyncPreview {
  domain?: string
  scope?: string
  changes?: ChangeRow[]
  version_problems?: Array<Record<string, any>>
  summary?: Partial<PreviewSummary>
  items: PlanItem[]
  /** 「应用到指定项目」预览给的是平铺计数 */
  counts?: Record<string, number>
  conflict_count?: number
  /** 「应用到指定项目」里不会写入的（项目 × 公式位）及原因：域不适用 / 底稿域该项目没有这张底稿 */
  skipped?: ApplySkipped[]
  [extra: string]: any
}
export interface ApplySkipped {
  project_id: string
  project_name?: string
  /** 只跳过某个公式位时给出（底稿域）；整个项目不适用时不给 */
  slot_key?: string
  reason: string
}
export interface Decisions {
  project_choices: Record<string, ProjectChoice>
  conflict_choices: Record<string, ConflictChoice>
  default_conflict: ConflictChoice
}
export interface PendingItem {
  id: string
  project_id: string
  domain: string
  slot_key: string
  slot_label: string
  reason: string
  reason_label: string
  upstream_origin: string
  upstream_origin_label: string
  upstream_template_id: string | null
  base_definition: Definition | null
  upstream_definition: Definition | null
  upstream_deleted: boolean
  local_definition: Definition | null
  base_formula: string
  upstream_formula: string
  local_formula: string
  upstream_version: number | null
  /** 修订号：新建为 1，每次被新的发布覆盖 +1；处理时原样回传（spec formula-hub-integrity-closure 需求 8.1） */
  revision: number
  publish_id: string | null
  created_at: string | null
  updated_at: string | null
}
/** 公式变更联动失败明细（后端 propagation_status.recent_failures） */
export interface PropagationFailure {
  outbox_id: string
  domain: string
  domain_label: string
  source: string
  slot_count: number
  attempt_count: number
  /** 尝试次数已达上限：不再自动重试（之后进死信，需人工处理） */
  gave_up: boolean
  last_error: string
  created_at: string | null
}
/** 本项目公式变更的联动（传播）状态（`GET /api/projects/{pid}/formula-settings/propagation`） */
export interface PropagationStatus {
  project_id: string
  window: number
  /** idle = 无待处理；running = 有处理中；failed = 有失败（含自动重试中） */
  state: 'idle' | 'running' | 'failed'
  counts: { pending: number; failed: number; published: number }
  retrying: number
  gave_up: number
  dead_letter: number
  max_attempts: number | null
  last_published_at: string | null
  recent_failures: PropagationFailure[]
}
export interface Resolution {
  item_id: string
  choice: ResolutionChoice
  /** 列表给出的修订号：缺 → 428，与服务端当前不等 → 409（需求 8.2、8.3） */
  revision: number
  custom_definition?: Definition | null
}
export interface EffectiveSlot {
  slot_key: string
  label: string
  layer: string
  layer_label: string
  definition: Definition | null
  disabled: boolean
  pending: boolean
  structure: Record<string, any>
  global_definition: Definition | null
  global_version: number | null
  preset_definition: Definition | null
  local_definition: Definition | null
  local_version: number | null
  base_definition: Definition | null
  base_version: number | null
  base_origin: string | null
  base_template_id: string | null
  pinned: boolean
}
export interface EffectiveResult {
  domain: string
  project_id: string
  scope: string
  frozen: boolean
  can_edit_global: boolean
  slots: EffectiveSlot[]
}
export interface ApplyTarget { project_id: string; name: string; scope: string; same_scope: boolean }
export interface PublishRecord {
  id: string
  domain: string
  scope: string
  target: string
  source: string
  status: string
  template_id: string | null
  source_project_id: string | null
  change_set: ChangeRow[]
  summary: Record<string, any>
  note: string | null
  published_by: string | null
  published_at: string | null
  reviewed_by: string | null
  reviewed_at: string | null
}
export interface FormulaTemplateInfo {
  id: string
  name: string
  description: string | null
  share_scope: ShareScope
  share_scope_label: string
  owner_user_id: string | null
  owner_project_id: string | null
  applicable_scope: string
  domains: string[]
  version: number
  status: string
  can_manage: boolean
  updated_at: string | null
  /** 列表接口附带：在用订阅数（模板列表按它排序） */
  subscriber_count?: number
}
/** 全平台校对规则目录的一条规则（后端 formula_check_catalog，spec formula-governance-coverage-closure R3） */
export interface CheckRule {
  id: string
  label: string
  expression: string
  severity: string
  severity_label: string
  scope: string
  /** 表间审核预置：原始字段（「从预置选用」填表用） */
  fields?: Record<string, any>
}
export interface CheckRuleSource {
  key: string
  label: string
  /** 报表 / 附注 / 底稿 / 质控 / 关系 */
  category: string
  /** 在哪里执行（现查代码得出；无调用方会如实写明） */
  runs_in: string
  editable: boolean
  edit_where: string
  files: string[]
  from_db: boolean
  rule_count: number
  error: string | null
  /** 带 source 或 q 查询时才有 */
  matched?: number
  rules?: CheckRule[]
}
export interface TemplateSlot {
  slot_key: string
  label: string
  definition: Definition | null
  structure: Record<string, any>
  version: number
}
/**
 * 模板「全局已变」提示的分类（后端 template_service.global_hints，spec formula-management-repair-closure R6.1）：
 * follow = 模板没改过、可一键同步；same = 模板已与新全局一致、只需更新基线；conflict = 真冲突；deleted = 全局删了该公式位。
 */
export type TemplateHintKind = 'follow' | 'same' | 'conflict' | 'deleted'
export interface TemplateGlobalHint {
  domain: string
  slot_key: string
  label: string
  kind: TemplateHintKind
  template_definition: Definition | null
  /** 模板写入（或上次「保留模板」）时的全局定义 */
  base_definition: Definition | null
  base_version: number | null
  /** 当前全局；全局已删为 null */
  global_definition: Definition | null
  global_version: number | null
  same_as_template: boolean
}
export const TEMPLATE_HINT_LABELS: Record<TemplateHintKind, string> = {
  follow: '模板未改，可直接同步', same: '模板已与新全局一致', conflict: '模板与新全局都改了', deleted: '全局已删除该公式位',
}
export interface TemplateDetail extends FormulaTemplateInfo {
  definitions: Record<string, TemplateSlot[]>
  global_hints: TemplateGlobalHint[]
  subscriber_count: number
}
export interface TemplateVersion {
  version: number
  note: string | null
  change_set: ChangeRow[]
  published_by: string | null
  published_at: string | null
}
export interface TemplateDiffChange extends ChangeRow {
  kind: 'added' | 'removed' | 'changed'
}
export interface TemplateDiff {
  template_id: string
  from_version: number
  to_version: number
  changes: TemplateDiffChange[]
}
export interface TemplateSubscriber {
  project_id: string
  project_name: string
  domain: string
  template_version: number
  pinned: boolean
  behind: boolean
  local_modified: number
  pending: number
  subscribed_at: string | null
}
export interface TemplateSubscription {
  domain: string
  template_id: string
  template_name: string
  template_version: number
  current_version: number
  pinned: boolean
  behind: boolean
}

// ── 标签与小工具 ──────────────────────────────────────────────────────────────

export const SHARE_SCOPE_OPTIONS: ReadonlyArray<{ value: ShareScope; label: string; hint: string }> = [
  { value: 'personal', label: '个人', hint: '只有自己可见' },
  { value: 'team', label: '项目组', hint: '所属项目的全部成员可见' },
  { value: 'group', label: '集团', hint: '所属集团根项目及其全部下级项目的成员可见' },
  { value: 'firm', label: '事务所', hint: '全体可见（仅管理员可创建）' },
]

/** 模板「适用范围」：完整准则对所有域都有效；国企版 / 上市版只对附注类（按模板类型分）的域有效。 */
export const APPLICABLE_SCOPE_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: '', label: '通用（不限准则）' },
  { value: 'soe_standalone', label: '国企单体' }, { value: 'soe_consolidated', label: '国企合并' },
  { value: 'listed_standalone', label: '上市单体' }, { value: 'listed_consolidated', label: '上市合并' },
  { value: 'enterprise', label: '企业会计准则（通用）' },
  { value: 'soe', label: '国企版（附注类）' }, { value: 'listed', label: '上市版（附注类）' },
]

export function scopeLabel(value: string | null | undefined): string {
  if (value === '*') return '全部（通用）'
  return APPLICABLE_SCOPE_OPTIONS.find((o) => o.value === (value || ''))?.label || String(value || '')
}

/** 定义字段的中文名（执行字段参与冲突判定，说明字段跟随）。 */
export const FIELD_LABELS: Record<string, string> = {
  formula: '公式', aje_formula: '调整分录公式', rje_formula: '重分类公式', formula_category: '公式类别',
  formula_description: '说明', formula_source: '来源标注', row_name: '行名称', left_ref: '左侧取数',
  operator: '比较符', right_ref: '右侧取数', tolerance: '容差', label: '规则名称', description: '说明',
  expression: '表达式', formula_type: '公式类型', category: '类别', source: '来源',
}

/** el-tag 颜色：全局 / 系统预设 = 灰；模板 = 绿；本项目 = 橙；暂缓 = 红。 */
export function layerTagType(layer?: string | null): 'info' | 'success' | 'warning' | 'danger' {
  if (layer === 'template') return 'success'
  if (layer === 'project') return 'warning'
  if (layer === 'pinned') return 'danger'
  return 'info'
}

/** 层级中文标签（与后端 effective.LAYER_LABELS 同口径）；试算表明细 / 表间审核等行上标注用。 */
export const LAYER_LABELS: Record<string, string> = {
  global: '全局', template: '模板', project: '本项目', pinned: '暂缓采用', preset: '系统预设',
}
export const layerLabel = (layer?: string | null): string => LAYER_LABELS[layer || ''] || ''

/** 同步分类（R3.1）的中文名与展示顺序；与后端 sync.CATEGORY_LABELS 同口径。 */
export const CATEGORY_LABELS: Record<string, string> = {
  inherit: '直接生效', follow: '自动跟随', same: '已一致', conflict: '冲突',
  pinned: '已暂缓（仍用旧定义）', frozen: '冻结（已归档，不改动）', template: '模板覆盖（不受影响）',
}
export const CATEGORY_ORDER = ['inherit', 'follow', 'same', 'conflict', 'pinned', 'frozen', 'template'] as const

// ── 全局设置页的公式位分组（spec formula-management-repair-closure R5） ──────────────────────────

/** 各域公式位里「分组段」后面的分隔符：报表 `报表类型:行次`、底稿 `编码|sheet|格`、附注 `章节|格`、表间审核 `节点#规则`、推送 `底稿.规则` */
const SLOT_GROUP_SEPARATOR: Record<string, string> = {
  report: ':', wp: '|', note: '|', consol_note: '|', cross_check: '#', push: '.',
}
const SLOT_GROUP_LABELS: Record<string, Record<string, string>> = {
  report: {
    balance_sheet: '资产负债表', income_statement: '利润表', cash_flow_statement: '现金流量表',
    equity_statement: '所有者权益变动表', cash_flow_supplement: '现金流量表补充资料', impairment_provision: '资产减值准备表',
  },
  tb_detail: { 1: '资产类科目', 2: '负债类科目', 3: '共同类科目', 4: '所有者权益类科目', 5: '成本类科目', 6: '损益类科目',
    added: '自定义科目' },
}

/** 公式位所在的分组键：报表类型 / 底稿编码 / 附注章节 / 表间审核节点 / 推送规则的底稿；试算表明细按科目大类（首位数字） */
export function slotGroupKey(domain: string, slotKey: string): string {
  if (domain === 'tb_detail') return slotKey.startsWith('added:') ? 'added' : (slotKey.trim()[0] || '')
  const sep = SLOT_GROUP_SEPARATOR[domain]
  const at = sep ? slotKey.indexOf(sep) : -1
  return at > 0 ? slotKey.slice(0, at) : slotKey
}

/** 分组的中文名（报表类型、科目大类有名字；底稿编码 / 章节 / 节点原样显示） */
export function slotGroupLabel(domain: string, groupKey: string): string {
  return SLOT_GROUP_LABELS[domain]?.[groupKey] || groupKey || '其他'
}

/**
 * 未接入计算的域的提示文字（spec formula-management-repair-closure R3.1）：用后端 `/domains` 的 `wired_reason`，
 * 公式管理节点 / 应用范围弹窗 / 全局设置页同一来源；已接入或取不到域信息返回空串（不提示）。
 */
export function domainNotWiredText(info: Pick<FormulaDomainInfo, 'wired' | 'wired_reason'> | null | undefined): string {
  if (!info || info.wired) return ''
  return info.wired_reason || '该类公式目前只保存、不参与计算。'
}

export const isConflict = (item: Pick<PlanItem, 'category'>) => item.category === 'conflict'
export const isPendingRecord = (r: Pick<PublishRecord, 'status'>) => r.status === 'pending'
export const isPresetSlot = (s: Pick<GlobalSlot, 'layer'>) => s.layer === 'preset'

export function newRequestId(): string {
  const c = globalThis.crypto as Crypto | undefined
  return c?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

export function emptyDecisions(defaultConflict: ConflictChoice = 'ask'): Decisions {
  return { project_choices: {}, conflict_choices: {}, default_conflict: defaultConflict }
}

/**
 * 定义的单行展示（与后端 display_formula 同思路：优先公式类字段）。
 * 停用显示「（已停用）」；没有公式字段时用结构里的中文算式（推送规则的四表明细 / 派生计算来源）。
 */
export function definitionText(d: Definition | null | undefined, structure?: Record<string, any> | null): string {
  if (d == null) return '（已删除）'
  if (d.disabled) return '（已停用）'
  for (const k of ['formula', 'expression']) if (d[k]) return String(d[k])
  if (d.left_ref || d.right_ref) return `${d.left_ref || ''} ${d.operator || '='} ${d.right_ref || ''}`.trim()
  const text = structure?.formula_text
  return typeof text === 'string' && text.trim() ? text.trim() : '（空）'
}

/** 后端错误 → 中文提示；取不到具体原因时用兜底文案。 */
export function formulaErrorText(e: any, fallback: string): string {
  const status = e?.response?.status || e?.status || 0
  const detail = e?.response?.data?.detail ?? e?.data?.detail
  // 公式引用校验 422 逐条列「引用：原因」（与全局提示、handleApiError 同一格式化）
  const msg = typeof detail === 'string' ? detail : (refIssueDetailText(detail) || String(detail?.message || ''))
  if (!status) return `${fallback}：网络不通，请检查连接`
  if (status === 403) return msg || '没有权限执行此操作'
  if (status === 428) return msg || '缺少版本信息，请刷新后重试'
  if (status === 409) return msg || '数据已被他人修改，请刷新后重试'
  if (status === 423) return msg || '项目已归档（只读），不能修改'
  if (status === 404) return msg || `${fallback}：内容不存在或无权查看`
  return msg ? `${fallback}：${msg}` : fallback
}

/** 统一错误提示：权限 / 版本 / 归档类用警告，其余用错误。 */
export function showFormulaError(e: any, fallback: string): void {
  const status = e?.response?.status || e?.status || 0
  const text = formulaErrorText(e, fallback)
  if ([403, 409, 423, 428].includes(status)) ElMessage.warning(text)
  else ElMessage.error(text)
}

export function errorCodeOf(e: any): string {
  const detail = e?.response?.data?.detail ?? e?.data?.detail
  return (detail && typeof detail === 'object' && String(detail.error_code || '')) || ''
}

// 请求封装放在 services（axios 包装层的惯例位置），这里转出，组件一处导入即可
export { formulaSettingsApi } from '@/services/formulaSettingsApi'
