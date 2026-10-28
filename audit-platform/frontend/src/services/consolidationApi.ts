/**
 * 合并报表 API 服务层
 * Phase 11 Task 22.1 — 完整重建
 */
import { api } from '@/services/apiProxy'
import { parseAuditYear } from '@/utils/resolveAuditYear'
import { downloadFile } from '@/utils/http'
import {
  consolidation as P,
  consolNoteFormulas as P_cnf,
  consolNoteSections as P_cn,
} from '@/services/apiPaths'

// ─── TypeScript 类型定义 ──────────────────────────────────────────────────────

export interface ConsolScopeItem {
  id: string
  project_id: string
  year: number
  company_code: string
  company_name: string
  shareholding: number
  consol_method: string
  is_included: boolean
  scope_change_type?: string
  acquisition_date?: string
  parent_code?: string
  functional_currency?: string
}

export interface ConsolScopeSummary {
  total_companies: number
  included_companies: number
  excluded_companies: number
  scope_changes: number
}

export interface ConsolTrialRow {
  id: string
  project_id: string
  year: number
  standard_account_code: string
  account_name: string
  account_category: string
  individual_sum: number
  consol_adjustment: number
  consol_elimination: number
  consol_amount: number
}

export interface ConsistencyCheckResult {
  is_balanced: boolean
  total_debit: number
  total_credit: number
  difference: number
  row_count: number
}

export type EliminationType = 'equity' | 'internal_trade' | 'internal_ar_ap' | 'unrealized_profit' | 'other'
export type EliminationReviewStatus = 'draft' | 'pending_review' | 'approved' | 'rejected'

/** 分录明细行（金额以明细行为准；后端 Decimal 序列化为字符串） */
export interface EliminationLine {
  account_code: string
  account_name?: string | null
  debit_amount: string | number
  credit_amount: string | number
}

export interface EliminationEntry {
  id: string
  project_id: string
  entry_no: string
  year: number
  entry_type: EliminationType | string
  description: string | null
  /** 只作留痕与筛选，不参与金额分摊（ADR-CTREE-003） */
  related_company_codes: string[] | null
  /** 归属差额节点：空 = 本合并项目的「合并差额」；非空 = 该企业的「母分差额」 */
  branch_entity_code?: string | null
  review_status: EliminationReviewStatus | string
  debit_amount: string | number
  credit_amount: string | number
  lines?: EliminationLine[]
  /** 来源：空 = 手工录入；ws_* = 合并工作底稿生成；legacy_sheet = 旧版明细表转入（V172） */
  origin?: EliminationOrigin | string | null
  /** 来源键：同来源内确定且稳定，重复生成按它更新同一笔草稿 */
  origin_key?: string | null
  entry_group_id?: string
  reviewer_id?: string | null
  reviewed_at?: string | null
  created_at?: string
  updated_at?: string
}

/** 新增 / 修改分录请求体（修改时字段可选；branch_entity_code 显式 null = 改回合并差额） */
export interface EliminationEntryPayload {
  project_id?: string
  year?: number
  entry_type?: EliminationType
  description?: string | null
  related_company_codes?: string[] | null
  branch_entity_code?: string | null
  lines?: EliminationLine[]
}

/** revoke = 撤销审批（已审批 → 草稿；合并锁定时后端 423 拒绝），审批与撤销都会触发合并推送 */
export type EliminationReviewAction =
  | { action: 'submit' }
  | { action: 'approve' }
  | { action: 'reject'; rejection_reason?: string }
  | { action: 'revoke' }

// ─── 合并抵消分录明细表（spec consol-elimination-single-source-push 需求 1~2）──────────

/** 工作底稿来源（可由生成接口写入） */
export type WorksheetOrigin = 'ws_equity_sim' | 'ws_internal_arap' | 'ws_internal_trade'
/** 分录来源：工作底稿三类 + 旧版明细表转入 */
export type EliminationOrigin = WorksheetOrigin | 'legacy_sheet'

/** 明细表的一行 = 一笔分录的一条明细（金额为到分的字符串；明细无法识别的分录占一行、金额为 null） */
export interface ElimTreeLine {
  entry_id: string
  entry_no: string
  origin: EliminationOrigin | string | null
  origin_label: string
  origin_key: string | null
  /** 归属差额节点（与合并计算同一归属结果）；null = 找不到归属（见 orphan_reason） */
  node_key: string | null
  node_label: string | null
  branch_entity_code: string | null
  host_project_id: string
  host_project_name: string | null
  /** 由其他合并项目承载（下级合并企业的差额）⇒ 只读，到承载项目操作 */
  readonly: boolean
  entry_type: EliminationType | string
  entry_type_label: string
  description: string | null
  review_status: EliminationReviewStatus | string
  review_status_label: string
  /** 已审批且找到归属 ⇒ 计入合并数 */
  counted: boolean
  orphan_reason: string | null
  related_company_codes: string[]
  line_index: number
  line_count: number
  account_code: string | null
  account_name: string | null
  debit: string | null
  credit: string | null
}

/** 由当前合并项目承载的差额节点（新增分录的「归属节点」下拉） */
export interface ElimHostedNode {
  node_key: string
  label: string
  /** null = 合并差额；企业代码 = 该企业的母分差额 */
  branch_entity_code: string | null
}

export interface ElimLineTotals { debit: string; credit: string; difference: string; entry_count: number }

export interface ElimTreeLinesResponse {
  year: number
  project_id: string
  rows: ElimTreeLine[]
  hosted_nodes: ElimHostedNode[]
  /** all = 全部分录；approved = 已审批；counted = 实际计入合并数（已审批且归属成功） */
  totals: { all: ElimLineTotals; approved: ElimLineTotals; counted: ElimLineTotals }
}

/** 工作底稿来源分组的一行（科目按名称，编码由后端映射） */
export interface WorksheetSourceLine {
  subject: string
  detail?: string | null
  /** 借 / 贷（后端也认 debit / credit）；负金额由后端换向 */
  direction: string
  amount: string | number | null
}

/** 一个来源分组 ⇒ 一笔草稿分录 */
export interface WorksheetSourceGroup {
  origin: WorksheetOrigin
  origin_key: string
  description?: string | null
  /** 不传 ⇒ 已有草稿沿用其类型，新建取来源默认类型 */
  entry_type?: EliminationType | null
  lines: WorksheetSourceLine[]
  related_company_codes: string[]
}

export type GenerateAction = 'created' | 'updated' | 'unchanged' | 'blocked' | 'review_locked' | 'empty' | 'discarded'

/** 来源行的映射结果：reason 非空 ⇒ 该组不生成；warning 只提示 */
export interface GeneratePlannedLine {
  index: number
  subject: string
  detail: string | null
  direction: 'debit' | 'credit' | null
  amount: string | null
  account_code: string | null
  account_name: string | null
  /** 本集团科目 / 合并报表行次 / 标准科目表 */
  source: string | null
  note: string | null
  in_report: boolean
  warning: string | null
  reason: string | null
}

export interface GenerateGroupResult {
  origin: string
  origin_label: string
  origin_key: string
  action: GenerateAction | string
  entry_id: string | null
  entry_no: string | null
  review_status: string | null
  entry_type: string
  entry_type_label: string
  description: string
  related_company_codes: string[]
  debit_total: string
  credit_total: string
  lines: GeneratePlannedLine[]
  reasons: string[]
  warnings: string[]
}

export interface GenerateReviewNote {
  origin: string | null
  origin_key: string | null
  entry_id: string
  entry_no: string
  review_status: string
  reason: string
}

export interface GenerateFromWorksheetResult {
  year: number
  standard: string
  dry_run: boolean
  created: number
  updated: number
  unchanged: number
  discarded: number
  deleted: number
  blocked: Array<{ origin: string; origin_key: string; reason: string; reasons: string[]; entry_id: string | null }>
  /** 待审批 / 已审批分录的来源数据变了：分录未改动，只报告 */
  changed_after_review: GenerateReviewNote[]
  deleted_entries: Array<{ origin: string | null; origin_key: string | null; entry_id: string; entry_no: string; review_status: string }>
  warnings: string[]
  groups: GenerateGroupResult[]
}

/** 旧版明细表（consol_worksheet_data['elimination']）自定义行：检测 / 转入结果 */
export interface LegacySheetResult extends GenerateFromWorksheetResult {
  custom_row_count: number
  skipped_zero_rows: number
  group_count: number
  /** 还没有对应分录的组数（0 且有自定义行 ⇒ 已全部转入） */
  pending: number
  message: string
}

// ─── 按报表行次读时计算：试算平衡表页 / 报表差额表 / 穿透（需求 4~5）────────────────

export type ConsolReportType =
  | 'balance_sheet' | 'income_statement' | 'cash_flow_statement'
  | 'equity_statement' | 'cash_flow_supplement' | 'impairment_provision'

/** 试算平衡表页的五列（均为按科目自然方向归一后的净额） */
export type ConsolTrialMeasure = 'individual' | 'elim_equity' | 'elim_trade' | 'adjustment' | 'consolidated'
/** 试算页列：五列净额 + 「含草稿预览」（已审批 + 草稿 + 待审批分录的合并数，只作对照） */
export type ConsolTrialColumnKey = ConsolTrialMeasure | 'consolidated_with_drafts'

/** 节点合并数按科目自然方向的借贷平衡检查（spec consol-autotree-linkage-closure R8.5） */
export interface ConsolTrialBalanceCheck {
  debit_total: string
  credit_total: string
  difference: string
  balanced: boolean
}

export interface ConsolReportRowMeta {
  row_code: string
  row_name: string
  row_number: number | null
  indent_level: number | null
  is_total_row: boolean
  has_formula: boolean
}

export interface ConsolReportTrialRow extends ConsolReportRowMeta {
  individual: string | null
  elim_equity: string | null
  elim_trade: string | null
  adjustment: string | null
  consolidated: string | null
  /** 含草稿预览（已审批 + 草稿 + 待审批；不含已驳回）；合并审定数仍只认已审批 */
  consolidated_with_drafts?: string | null
  /** 公式线性 ⇒ 可按分录 / 企业分解 */
  linear: boolean
  /** 留空原因（取不到数的列） */
  note: string | null
}

export interface ConsolReportTrialResponse {
  year: number
  applicable_standard: string
  node_key: string
  node_label: string
  /** aggregate 汇总节点 / elim 差额户 / data 单体数据（列口径说明按它给） */
  node_kind?: ConsolNodeKind
  node_role?: ConsolNodeRole | string
  report_type: string
  columns: Array<{ key: ConsolTrialColumnKey; label: string }>
  rows: ConsolReportTrialRow[]
  balance?: ConsolTrialBalanceCheck
  /** 计入「含草稿预览」的未审批分录笔数（本节点子树内） */
  draft_pending_entries?: number | null
}

export interface ConsolBreakdownColumn {
  node_key: string
  label: string
  /** elim = 差额节点（合并差额 / 母分差额）；data = 单户；aggregate = 下级汇总 */
  kind: ConsolNodeKind
  role: ConsolNodeRole | string
  company_code: string
}

export interface ConsolReportBreakdownRow extends ConsolReportRowMeta {
  cells: Record<string, string | null>
  total: string | null
  linear: boolean
  note: string | null
}

export interface ConsolReportBreakdownResponse {
  year: number
  applicable_standard: string
  /** 可选的差额表节点（汇总节点，树序） */
  aggregate_nodes: Array<{ node_key: string; label: string; role: ConsolNodeRole | string }>
  node_key: string
  node_label: string
  report_type: string
  columns: ConsolBreakdownColumn[]
  rows: ConsolReportBreakdownRow[]
}

export type ConsolDrillMeasure = 'elim_equity' | 'elim_trade' | 'adjustment' | 'consolidated'

export interface ConsolEntryDrillLine {
  entry_id: string
  entry_no: string
  entry_type: string
  /** 分录类型中文（与分录枚举一致：other = 其他调整） */
  entry_type_label?: string
  /** 分录说明 */
  description?: string | null
  node_key: string
  node_label: string
  account_code: string
  account_name: string | null
  debit: string
  credit: string
  /** 对该行该列的贡献（行不能展开到科目时为 null） */
  contribution: string | null
}

export interface ConsolEntryDrillResponse {
  year: number
  node_key: string
  row_code: string
  row_name: string
  measure: ConsolDrillMeasure
  /** 行公式能展开到科目取数项 ⇒ 贡献之和 = 该行该列 */
  decomposable: boolean
  note: string | null
  total: string | null
  lines: ConsolEntryDrillLine[]
  /** 合并审定数列的完整构成：审定汇总 + 分录贡献 = 合并数（只在 measure=consolidated 时给） */
  individual_total?: string | null
  consolidated_total?: string | null
}

export interface ConsolIndividualDrillRow {
  node_key: string
  node_label: string
  /** 该数据节点在企业树上的直接上级 */
  parent_label?: string | null
  project_id: string | null
  amount: string | null
  reason: string | null
}

// ─── 分录汇总表（spec consol-autotree-linkage-closure R9：与合并试算同一计算口径）───────────

export interface ConsolEntrySummaryRow {
  node_key: string
  node_label: string
  /** 差额户由本合并项目承载（否则在下级合并项目录入） */
  hosted_here: boolean
  account_code: string
  account_name: string | null
  entry_type: string
  type_label: string
  measure: string
  debit: string
  credit: string
  /** 按科目自然方向归一的净额 */
  net: string
  /** 含草稿（已审批 + 草稿 + 待审批）的净额 */
  draft_net: string | null
  entry_count: number
}

export interface ConsolEntrySummaryByType {
  entry_type: string
  type_label: string
  debit: string
  credit: string
  net: string
  draft_net: string
  entry_count: number
}

export interface ConsolEntrySummaryMismatch {
  account_code: string
  account_name: string | null
  summary_adjustment: string
  trial_adjustment: string
  summary_elimination: string
  trial_elimination: string
}

export interface ConsolEntrySummary {
  year: number | null
  rows: ConsolEntrySummaryRow[]
  by_type: ConsolEntrySummaryByType[]
  totals: { debit: string; credit: string; difference: string; balanced: boolean; entry_count: number }
  reconcile: { matched: boolean; mismatches: ConsolEntrySummaryMismatch[]; persisted_stale: boolean; stale_accounts: string[] }
  orphans: Array<{ entry_no: string; reason: string; review_status: string | null; review_status_label: string | null }>
  warnings: string[]
}

// ─── 报表页右键「查看合并明细」（R8.2：报表行次读时计算）───────────────────────────────

export interface ConsolRowBreakdownItem {
  company_code: string
  company_name: string
  display_name?: string
  amount: string | null
  /** 占合并数的比例（4 位小数；读时路径另给 pct 百分数） */
  ratio: string | null
  pct?: string | null
  node_key?: string
  kind?: ConsolNodeKind | string
  /** 个别数 / 抵销与调整 / 下级汇总 */
  source?: string
  source_project_id?: string | null
  reason?: string | null
}

export interface ConsolRowBreakdown {
  account_code: string
  row_code?: string
  row_name?: string
  node_key?: string
  node_label?: string
  by_company: ConsolRowBreakdownItem[]
  elimination: string | null
  /** 后端合计（合并数） */
  consolidated: string | null
  individual_sum?: string
  linear?: boolean
  /** read_time = 按报表行读时计算（与报表差额表同源） */
  basis?: 'read_time'
  computed_at?: string | null
  has_breakdown: boolean
  message: string | null
}

// ─── 合并推送（需求 8）────────────────────────────────────────────────────────

export type ConsolPushTrigger = 'manual' | 'formula_changed'
export type ConsolPushRunTrigger = ConsolPushTrigger | 'elimination_approved' | 'elimination_revoked'
export type ConsolPushRunStatus = 'running' | 'succeeded' | 'partial' | 'failed'
export type ConsolPushStepName = 'worksheet' | 'trial' | 'report' | 'notes'
export type ConsolPushStepStatus = 'succeeded' | 'failed' | 'skipped'

export interface ConsolPushAck {
  queued: boolean
  message: string
  project_id: string
  year: number
}

export interface ConsolPushStep {
  project_id: string
  project_name: string
  step: ConsolPushStepName
  step_label: string
  status: ConsolPushStepStatus
  detail: string | null
}

export interface ConsolPushRun {
  id: string
  project_id: string
  year: number
  trigger_source: ConsolPushRunTrigger
  trigger_label: string
  triggered_by: string | null
  status: ConsolPushRunStatus
  steps: ConsolPushStep[]
  warnings: string[]
  started_at: string | null
  finished_at: string | null
}

export interface ConsolPushStatus {
  last_run: ConsolPushRun | null
  /** 子企业试算表在最近一次推送后又变了 ⇒ 建议重新推送 */
  is_stale: boolean
  stale_rows: number
}

// ─── 合并附注公式与差额（需求 6 / 7.2）────────────────────────────────────────

export type ConsolNoteTemplateType = 'soe' | 'listed'

export interface ConsolNoteFormula {
  id: string
  template_type: ConsolNoteTemplateType
  section_id: string
  row_index: number
  col_index: number
  row_label: string | null
  col_name: string
  /** 「第 r 行 · 列名（项目名）」 */
  position: string
  formula: string
  /** seed = 自动种子；manual = 人工（自动种子不再覆盖） */
  source: 'seed' | 'manual' | string
  source_label: string
  description: string | null
  updated_at: string | null
  updated_by?: string | null
  /** 版本号：修改 / 删除须原样带回（缺失 428、已被他人修改 409） */
  version?: number
}

export interface ConsolNoteFormulaSection {
  section_id: string
  title: string | null
  parent_section: string | null
  formulas: ConsolNoteFormula[]
}

export interface ConsolNoteFormulaList {
  template_type: ConsolNoteTemplateType
  count: number
  sections: ConsolNoteFormulaSection[]
}

export interface ConsolNoteFormulaPayload {
  template_type: ConsolNoteTemplateType
  section_id: string
  row_index: number
  col_index: number
  formula: string
  description?: string | null
}

export interface ConsolNoteBreakdownCell {
  row_index: number
  col_index: number
  formula: string
  source: string | null
  individual: string | null
  adjustment: string | null
  elim_equity: string | null
  elim_trade: string | null
  /** 抵销 = 权益抵销 + 往来交易抵销 */
  elimination: string | null
  consolidated: string | null
  linear: boolean
  note: string | null
  /** 所选汇总节点各直接子节点的合并数贡献 */
  children: Record<string, string | null>
  row_label: string | null
  col_name: string | null
}

export interface ConsolNoteBreakdown {
  project_id: string
  year: number
  template_type: ConsolNoteTemplateType
  section_id: string
  title: string | null
  parent_section: string | null
  node_key: string
  node_label: string | null
  columns: Array<{ key: string; label: string }>
  children: Array<{ node_key: string; label: string | null; kind: ConsolNodeKind }>
  cells: ConsolNoteBreakdownCell[]
}

export interface ConsolNoteFillResult {
  project_id: string
  year: number
  section_id: string
  template_type: ConsolNoteTemplateType
  filled: Array<{ row_index: number; col_index: number; target_row: number; value: string }>
  /** 手工单元格：保留原值，列出公式值供对照 */
  kept_manual: Array<{ row_index: number; col_index: number; target_row: number; current: string; formula_value: string | null }>
  blank: Array<{ row_index: number; col_index: number; target_row: number | null; reason: string }>
  is_stale: boolean
  data: { headers: any[]; rows: string[][]; manual_cells?: Array<{ row: number; col: number }>; [k: string]: any }
}

// ─── 重新汇总：节点子树逐节点更新 + 自下而上汇总（spec consol-note-header-library-and-node-reaggregate）───

/** 本轮对节点做的事：数据叶子从单体附注拉数 / 差额节点按抵销分录算差额 / 汇总节点 Σ 直接下级 + 差额 */
export type ConsolNoteReaggregateAction = 'pull' | 'elim' | 'aggregate'

export interface ConsolNoteReaggregateNode {
  node_key: string
  kind: ConsolNodeKind
  action: ConsolNoteReaggregateAction
  label: string
  written: number
  skipped: number
  failed: number
  /** 跳过 / 失败原因及章节数 */
  reasons: Array<{ reason: string; count: number }>
}

export interface ConsolNoteReaggregateResult {
  success: boolean
  status: 'persisted' | 'partial' | 'failed' | 'skipped'
  project_id: string
  year: number
  /** 所选节点（请求不带节点 = 根合并节点） */
  node_key: string | null
  legacy_null: boolean
  template_type: ConsolNoteTemplateType
  mode: 'subtree'
  sections_processed: number
  /** 所选节点写入的章节数 */
  sections_updated: number
  /** 所选节点的逐章节结果 */
  results: Array<{
    section_id: string
    node_key: string
    action: ConsolNoteReaggregateAction
    status: 'persisted' | 'skipped' | 'failed'
    reason: string | null
    [k: string]: unknown
  }>
  failures: Array<{ section_id: string; node_key: string | null; status: 'failed'; error: string }>
  errors: string[]
  nodes: ConsolNoteReaggregateNode[]
  /** 需要到「📋 明细映射」确认映射的企业 */
  pending_entities: Array<{ node_key: string; label: string; section_count: number; sections: string[]; reasons: string[] }>
}

/**
 * 试算表变动后自动按公式刷新合并附注的开关（spec consol-note-header-library-and-node-reaggregate R7.1）。
 * 生效值 = 全局 OR 项目；从单体附注拉来的数不覆盖、只标待更新。
 */
export interface ConsolNoteAutoRefreshState {
  project_enabled: boolean
  global_enabled: boolean
  effective_enabled: boolean
}

/** 读开关（调用方自管错误提示） */
export async function getConsolNoteAutoRefresh(projectId: string): Promise<ConsolNoteAutoRefreshState> {
  return api.get(P.notes.autoRefresh(projectId), { _silent: true } as any)
}

/** 写项目级开关（需本项目编辑权限；调用方自管错误提示） */
export async function setConsolNoteAutoRefresh(projectId: string, enabled: boolean): Promise<ConsolNoteAutoRefreshState> {
  return api.put(P.notes.autoRefresh(projectId), { enabled }, { _silent: true } as any)
}

// ─── 合并企业树（三码推导，spec consol-tree-three-code-autobuild）─────────────────

/** 节点角色：合并 / 合并差额 / 母公司 / 本部 / 母分差额 / 子公司 / 分公司 */
export type ConsolNodeRole = 'consol' | 'consol_elim' | 'parent' | 'hq' | 'branch_elim' | 'subsidiary' | 'branch'
/** 节点类型：aggregate = Σ 直接子节点；elim = 归属本节点的已审批分录；data = 单户审定数 */
export type ConsolNodeKind = 'aggregate' | 'elim' | 'data'

/**
 * 当前选中合并主体（树节点）的上下文身份。
 * nodeKey 是必需的节点唯一身份（`{企业代码}:{角色}`），
 * 附注和报表的读写、缓存分区都以此为键。
 * 设计：consol-node-key-isolation-and-shared-context §七
 */
export interface CurrentConsolEntity {
  code: string
  name: string
  /** 树节点唯一键，必需。同企业不同角色（合并/母公司/本部）各有独立 nodeKey。 */
  nodeKey: string
}
/** 合并方式识别：母子合并 / 总分汇总 / 两者并存 / 未识别到下级 */
export type ConsolMode = 'subsidiary' | 'branch' | 'mixed' | 'none'

export interface ConsolTreeNode {
  /** 数据节点 = 单户项目；合并节点 = 合并项目；差额与有分公司的汇总节点为 null */
  project_id: string | null
  company_code: string
  company_name: string
  parent_company_code: string | null
  ultimate_company_code: string | null
  consol_level: number
  children: ConsolTreeNode[]
  /** 树内唯一键：{企业代码}:{角色} */
  node_key: string
  role: ConsolNodeRole
  kind: ConsolNodeKind
  /** 带角色后缀的名称，如「某集团（差额户）」（后端 consol_node_naming） */
  display_name: string
  relation: 'subsidiary' | 'branch' | null
  /** 差额节点：承载其分录的合并项目 */
  host_project_id: string | null
  flags: string[]
  /** 经中间企业间接持有（企业代码，外层在前） */
  via: string[]
  mode: ConsolMode | null
  /** 旧数据字段（持股比例），三码树不再填写 */
  shareholding?: number | null
}

export interface ConsolTreeDiagnostic {
  code: string
  message: string
  company_code: string | null
  node_key: string | null
  level: 'warning' | 'info'
}

/** 两版企业树的节点差异（后端 `structural_diff`；改名只进 renamed，不算结构变化） */
export interface ConsolTreeDiffItem {
  node_key: string
  label?: string | null
  role?: string | null
}
export interface ConsolTreeDiff {
  added: ConsolTreeDiffItem[]
  removed: ConsolTreeDiffItem[]
  moved: Array<ConsolTreeDiffItem & { from: string | null; from_label: string | null; to: string | null; to_label: string | null }>
  changed: Array<ConsolTreeDiffItem & { fields: string[] }>
  renamed: Array<{ node_key: string; from: string | null; to: string | null }>
  structural: boolean
}

/** 企业树版本（spec consol-autotree-linkage-closure R1：推送时自动记录，手动「记录为新版本」为 user） */
export interface ConsolScopeVersion {
  /** 当前有效（已记录）的版本号；0 = 尚未记录 */
  revision: number
  latest_revision: number
  mode: 'user' | 'auto' | null
  recorded_at: string | null
  /** 当前树与已记录版本一致 */
  matches: boolean
  /** 与已记录版本相比有新增 / 移除 / 上级变化 / 类型或关系变化（改名不算） */
  structural_change: boolean
  diff: ConsolTreeDiff | null
  fingerprint: string
  can_record: boolean
}

/** `GET /api/consolidation/worksheet/tree` 响应 */
export interface ConsolTreeResponse {
  tree: ConsolTreeNode | null
  mode: ConsolMode | null
  mode_label: string | null
  diagnostics: ConsolTreeDiagnostic[]
  year: number | null
  message?: string
  /** 企业树版本；非合并项目 / 取不到时为 null */
  scope_version?: ConsolScopeVersion | null
}

/** 差额录入可选科目（方向与金额归一同一判定） */
export interface ConsolAccountOption {
  account_code: string
  account_name: string | null
  account_category: string | null
  direction: 'debit' | 'credit'
  in_trial_balance: boolean
  in_entries: boolean
}

export interface NodeAmountRow {
  account_code: string
  account_name: string | null
  direction: 'debit' | 'credit'
  children_amount_sum: string
  adjustment_debit: string
  adjustment_credit: string
  elimination_debit: string
  elimination_credit: string
  net_difference: string
  consolidated_amount: string
}

export interface NodeAmountsResponse {
  year: number | null
  node_key: string
  display_name: string
  kind: ConsolNodeKind
  rows: NodeAmountRow[]
}

export interface EliminationSummary {
  entry_type: string
  count: number
  total_debit: number
  total_credit: number
}

export interface InternalTrade {
  id: string
  seller_company_code: string
  buyer_company_code: string
  trade_type: string
  trade_amount: number
  cost_amount?: number
  unrealized_profit?: number
}

export interface InternalArAp {
  id: string
  debtor_company_code: string
  creditor_company_code: string
  debtor_amount: number
  creditor_amount: number
  difference_amount?: number
}

export interface TransactionMatrix {
  company_codes: string[]
  matrix: Record<string, Record<string, number>>
}

export interface ComponentAuditor {
  id: string
  project_id: string
  firm_name: string
  contact_person?: string
  auditor_name?: string
  auditor_email?: string
  component_name?: string
  scope?: string
  status?: string
}

export interface Instruction {
  id: string
  component_auditor_id: string
  instruction_no?: string
  status: string
  content?: string
}

export interface InstructionResult {
  id: string
  component_auditor_id: string
  instruction_id?: string
  result_no?: string
  evaluation_status: string
  opinion_type?: string
  status?: string
  content?: string
}

export interface ComponentDashboard {
  total_auditors: number
  pending_instructions: number
  pending_results: number
  received_results: number
  non_standard_opinions: number
}

export interface GoodwillRow {
  id: string
  year: number
  subsidiary_company_code: string
  acquisition_cost?: number
  goodwill_amount?: number
  accumulated_impairment?: number
  is_negative_goodwill: boolean
}

export interface ForexRow {
  id: string
  year: number
  company_code: string
  functional_currency: string
  reporting_currency: string
  bs_closing_rate?: number
  pl_average_rate?: number
}

export interface MinorityInterestRow {
  id: string
  year: number
  subsidiary_company_code: string
  minority_share_ratio?: number
  minority_equity?: number
  minority_profit?: number
}

export interface ConsolReportRow {
  row_code: string
  row_name: string
  current_period_amount: number
  prior_period_amount: number
  is_bold: boolean
  is_total: boolean
}

export interface ConsolReportData {
  rows: ConsolReportRow[]
  report_type: string
}

export interface YoYAnalysis {
  row_code: string
  row_name: string
  current: number
  prior: number
  change: number
  change_pct: number
}

export interface WorksheetNode {
  company_code: string
  company_name: string
  children?: WorksheetNode[]
  [key: string]: any
}

export interface PivotResult {
  headers: string[]
  rows: Record<string, any>[]
  totals?: Record<string, number>
}

export interface QueryTemplate {
  id: string
  name: string
  row_dimension: string
  col_dimension: string
  value_field: string
  filters?: Record<string, any>
  transpose: boolean
  aggregation_mode: string
}

// ─── 合并范围 API ─────────────────────────────────────────────────────────────

/** 年度必填（端点 year 必填；原先缺省时兜底去年） */
export async function getConsolScope(projectId: string, year: number): Promise<ConsolScopeItem[]> {
  return api.get(`${P.scope.list}?project_id=${projectId}&year=${year}`)
}

export async function createConsolScope(projectId: string, data: Partial<ConsolScopeItem>): Promise<ConsolScopeItem> {
  return api.post(`${P.scope.list}?project_id=${projectId}`, data)
}

export async function updateConsolScope(scopeId: string, projectId: string, data: Partial<ConsolScopeItem>): Promise<ConsolScopeItem> {
  return api.put(`${P.scope.detail(scopeId)}?project_id=${projectId}`, data)
}

export async function deleteConsolScope(scopeId: string, projectId: string): Promise<void> {
  return api.delete(`${P.scope.detail(scopeId)}?project_id=${projectId}`)
}

export async function batchUpdateScope(projectId: string, items: Partial<ConsolScopeItem>[]): Promise<ConsolScopeItem[]> {
  return api.post(`${P.scope.batch}?project_id=${projectId}`, { scope_items: items })
}

export async function getConsolScopeSummary(projectId: string, year: number): Promise<ConsolScopeSummary> {
  return api.get(`${P.scope.summary}?project_id=${projectId}&year=${year}`)
}

// ─── 合并试算表 API ───────────────────────────────────────────────────────────

export async function getConsolTrial(projectId: string, year: number): Promise<ConsolTrialRow[]> {
  return api.get(`${P.trial.list}?project_id=${projectId}&year=${year}`)
}

export async function getConsolTrialBalance(projectId: string, year: number): Promise<ConsolTrialRow[]> {
  return getConsolTrial(projectId, year)
}

export async function recalculateConsolTrial(projectId: string, year: number): Promise<ConsolTrialRow[]> {
  return api.post(`${P.trial.recalculate}?project_id=${projectId}&year=${year}`)
}

export async function checkConsolTrialConsistency(projectId: string, year: number): Promise<ConsistencyCheckResult> {
  return api.get(`${P.trial.consistencyCheck}?project_id=${projectId}&year=${year}`)
}

// ─── 抵消分录 API ─────────────────────────────────────────────────────────────

/**
 * 分录列表。``nodeKey`` 按归属差额节点筛选（``{企业代码}:consol_elim`` / ``{企业代码}:branch_elim``）；
 * ``silent`` 为真时不弹全局错误提示（调用方自行处理，如查看其他合并项目的分录可能无权限）。
 */
export async function getEliminations(
  projectId: string,
  year?: number | null,
  opts: { nodeKey?: string; silent?: boolean } = {},
): Promise<EliminationEntry[]> {
  const params: Record<string, string | number> = { project_id: projectId }
  if (year) params.year = year
  if (opts.nodeKey) params.node_key = opts.nodeKey
  const config: Record<string, unknown> = { params }
  if (opts.silent) config._silent = true
  return api.get(P.eliminations.list, config)
}

export async function createElimination(projectId: string, data: EliminationEntryPayload): Promise<EliminationEntry> {
  return api.post(`${P.eliminations.list}?project_id=${projectId}`, data)
}

export async function updateElimination(
  entryId: string, projectId: string, data: EliminationEntryPayload,
): Promise<EliminationEntry> {
  return api.put(`${P.eliminations.detail(entryId)}?project_id=${projectId}`, data)
}

export async function deleteElimination(entryId: string, projectId: string): Promise<void> {
  return api.delete(`${P.eliminations.detail(entryId)}?project_id=${projectId}`)
}

/**
 * 复核：submit 提交审批（草稿/已驳回 → 待审批）、approve 审批、reject 驳回（可带原因）、
 * revoke 撤销审批（已审批 → 草稿）。审批与撤销审批后端会触发合并推送（结果经 SSE consol.pushed 通知）。
 */
export async function reviewElimination(
  entryId: string, projectId: string, action: EliminationReviewAction,
): Promise<EliminationEntry> {
  return api.post(`${P.eliminations.review(entryId)}?project_id=${projectId}`, action)
}

export async function getEliminationSummary(projectId: string, year: number): Promise<EliminationSummary[]> {
  return api.get(`${P.eliminations.summary}?project_id=${projectId}&year=${year}`)
}

/** 合并抵消分录明细表：本树全部未删分录展开为明细行 + 归属 + 只读判定 + 三行合计 + 本项目承载的差额节点 */
export async function getEliminationTreeLines(projectId: string, year?: number | null): Promise<ElimTreeLinesResponse> {
  const params: Record<string, string | number> = { project_id: projectId }
  if (year) params.year = year
  return api.get(P.eliminations.treeLines, { params })
}

/**
 * 工作底稿来源分组 ⇒ 草稿分录（按来源键幂等 upsert；已提交 / 已审批的不改只报告）。
 * ``origins`` 声明本次负责的来源：其中本次没出现的来源键 ⇒ 草稿软删（某张表本次一组都没算出时须显式列出）。
 * ``dryRun`` 只预演（明细表「待生成」预览），不写库。
 */
export async function generateEliminationsFromWorksheet(
  projectId: string,
  body: { year: number; groups: WorksheetSourceGroup[]; origins?: WorksheetOrigin[]; dry_run?: boolean },
  opts: { silent?: boolean } = {},
): Promise<GenerateFromWorksheetResult> {
  // 预演随页面打开自动发起：silent 时失败由调用方显示在页面上，不弹全局提示
  const config: Record<string, unknown> = {}
  if (opts.silent) config._silent = true
  return api.post(`${P.eliminations.generateFromWorksheet}?project_id=${projectId}`, body, config)
}

/** 旧版明细表（JSON）自定义行检测：返回预演结果与提示文案（不写库） */
export async function getLegacyEliminationSheet(projectId: string, year?: number | null): Promise<LegacySheetResult> {
  const params: Record<string, string | number> = { project_id: projectId }
  if (year) params.year = year
  return api.get(P.eliminations.legacySheet, { params })
}

/** 旧版明细表自定义行转为草稿分录（按借贷平衡处切分；转入后不再按旧数据改写） */
export async function convertLegacyEliminationSheet(
  projectId: string, year: number, entryType?: EliminationType | null,
): Promise<LegacySheetResult> {
  const body: Record<string, unknown> = { year }
  if (entryType) body.entry_type = entryType
  return api.post(`${P.eliminations.legacySheetConvert}?project_id=${projectId}`, body)
}

// ─── 内部交易 API ─────────────────────────────────────────────────────────────

export async function getInternalTrades(projectId: string, year: number): Promise<InternalTrade[]> {
  return api.get(`${P.internalTrade.trades}?project_id=${projectId}&year=${year}`)
}

export async function createInternalTrade(projectId: string, data: any): Promise<InternalTrade> {
  return api.post(`${P.internalTrade.trades}?project_id=${projectId}`, data)
}

export async function getInternalArAp(projectId: string, year: number): Promise<InternalArAp[]> {
  return api.get(`${P.internalTrade.arap}?project_id=${projectId}&year=${year}`)
}

export async function getTransactionMatrix(projectId: string, year: number): Promise<TransactionMatrix> {
  return api.get(`${P.internalTrade.matrix}?project_id=${projectId}&year=${year}`)
}

// ─── 组成部分审计师 API ───────────────────────────────────────────────────────

export async function getComponentAuditors(projectId: string): Promise<ComponentAuditor[]> {
  return api.get(`${P.componentAuditor.auditors}?project_id=${projectId}`)
}

export async function createComponentAuditor(projectId: string, data: any): Promise<ComponentAuditor> {
  return api.post(`${P.componentAuditor.auditors}?project_id=${projectId}`, data)
}

export async function getInstructions(projectId: string, auditorId?: string): Promise<Instruction[]> {
  let url = `${P.componentAuditor.instructions}?project_id=${projectId}`
  if (auditorId) url += `&auditor_id=${auditorId}`
  return api.get(url)
}

export async function getResults(projectId: string, auditorId?: string): Promise<InstructionResult[]> {
  let url = `${P.componentAuditor.results.list}?project_id=${projectId}`
  if (auditorId) url += `&auditor_id=${auditorId}`
  return api.get(url)
}

export async function createResult(projectId: string, data: any): Promise<InstructionResult> {
  return api.post(`${P.componentAuditor.results.list}?project_id=${projectId}`, data)
}

export async function updateResult(resultId: string, projectId: string, data: any): Promise<InstructionResult> {
  return api.put(`${P.componentAuditor.results.detail(resultId)}?project_id=${projectId}`, data)
}

export async function getComponentDashboard(projectId: string): Promise<ComponentDashboard> {
  return api.get(`${P.componentAuditor.dashboard}?project_id=${projectId}`)
}

// ─── 商誉 API ─────────────────────────────────────────────────────────────────

export async function getGoodwillRows(projectId: string, year: number): Promise<GoodwillRow[]> {
  return api.get(`${P.goodwill}?project_id=${projectId}&year=${year}`)
}

export async function createGoodwill(projectId: string, data: any): Promise<GoodwillRow> {
  return api.post(`${P.goodwill}?project_id=${projectId}`, data)
}

// ─── 外币折算 API ─────────────────────────────────────────────────────────────

export async function getForexRows(projectId: string, year: number): Promise<ForexRow[]> {
  return api.get(`${P.forex}?project_id=${projectId}&year=${year}`)
}

// ─── 少数股东权益 API ─────────────────────────────────────────────────────────

export async function getMinorityInterestRows(projectId: string, year: number): Promise<MinorityInterestRow[]> {
  return api.get(`${P.minorityInterest}?project_id=${projectId}&year=${year}`)
}

export async function getMinorityInterest(projectId: string, year: number): Promise<MinorityInterestRow[]> {
  return getMinorityInterestRows(projectId, year)
}

// ─── 合并报表 API ─────────────────────────────────────────────────────────────

export async function getConsolReports(projectId: string, year: number): Promise<ConsolReportRow[]> {
  return api.get(`${P.reports.list(projectId, year)}?report_type=balance_sheet`)
}

export async function getConsolReport(
  projectId: string, reportType: string, period: string, nodeKey?: string | null,
): Promise<ConsolReportData> {
  // period 解析不出年度 ⇒ 不请求（原先兜底去年，取的是别的年度的合并报表）
  const year = parseAuditYear(parseInt(period))
  if (year == null) return { rows: [], report_type: reportType }
  const params: Record<string, string | number> = { report_type: reportType }
  if (nodeKey) params.node_key = nodeKey
  const rows = await api.get(`${P.reports.list(projectId, year)}`, { params })
  return { rows: Array.isArray(rows) ? rows : [], report_type: reportType }
}

export async function saveConsolReport(_projectId: string, _reportType: string, _period: string, data: ConsolReportData): Promise<ConsolReportData> {
  return data // 报表数据由后端生成，前端只读
}

export async function getYoYAnalysis(_projectId: string, _reportType: string, _period: string): Promise<YoYAnalysis[]> {
  return [] // 同比分析待后端实现
}

/**
 * 生成合并报表（全部报表类型）。口径不传 ⇒ 后端按项目模板类型解析（soe_consolidated / listed_consolidated）；
 * 旧实现默认传 'CAS'，库里没有该口径的报表配置 ⇒ 一行也生成不出来（需求 3.4）。
 */
export async function generateConsolReports(projectId: string, year: number, standard?: string): Promise<any> {
  const body: Record<string, unknown> = { project_id: projectId, year }
  if (standard) body.applicable_standard = standard
  return api.post(P.reports.generate, body, { params: { project_id: projectId } })
}

export async function checkConsolBalance(projectId: string, year: number): Promise<any> {
  return api.get(P.reports.balanceCheck(projectId, year))
}

// ─── 差额表 / 工作底稿 API ───────────────────────────────────────────────────

/** 合并企业树（三码推导）+ 合并方式识别 + 诊断 + 年度 */
export async function getWorksheetTree(projectId: string): Promise<ConsolTreeResponse> {
  return api.get(`${P.worksheet.tree}?project_id=${projectId}`, { _dedupe: false } as any)
}

/** 差额录入可选科目：本树数据叶子试算表科目 ∪ 本树分录明细行科目 */
export async function getWorksheetAccounts(
  projectId: string, year?: number | null,
): Promise<{ year: number | null; accounts: ConsolAccountOption[] }> {
  const params: Record<string, string | number> = { project_id: projectId }
  if (year) params.year = year
  return api.get(P.worksheet.accounts, { params })
}

/** 某节点按科目归一后的金额（实时按计算口径求值，只计已审批分录） */
export async function getNodeAmounts(
  projectId: string, nodeKey: string, year?: number | null,
): Promise<NodeAmountsResponse> {
  const params: Record<string, string | number> = { project_id: projectId, node_key: nodeKey }
  if (year) params.year = year
  return api.get(P.worksheet.nodeAmounts, { params })
}

export async function recalcWorksheet(projectId: string, year: number): Promise<any> {
  return api.post(P.worksheet.recalc, { project_id: projectId, year })
}

export async function getWorksheetAggregate(projectId: string, year: number, nodeCode: string, mode: string = 'self'): Promise<any> {
  return api.get(`${P.worksheet.aggregate}?project_id=${projectId}&year=${year}&node_code=${nodeCode}&mode=${mode}`)
}

export async function drillToCompanies(projectId: string, year: number, nodeCode: string, accountCode?: string): Promise<any> {
  let url = `${P.worksheet.drillCompanies}?project_id=${projectId}&year=${year}&node_code=${nodeCode}`
  if (accountCode) url += `&account_code=${accountCode}`
  return api.get(url)
}

export async function drillToEliminations(projectId: string, year: number, companyCode: string, accountCode?: string): Promise<any> {
  let url = `${P.worksheet.drillEliminations}?project_id=${projectId}&year=${year}&company_code=${companyCode}`
  if (accountCode) url += `&account_code=${accountCode}`
  return api.get(url)
}

export async function drillToTrialBalance(projectId: string, companyCode: string): Promise<any> {
  return api.get(`${P.worksheet.drillTrialBalance}?project_id=${projectId}&company_code=${companyCode}`)
}

export async function executePivotQuery(projectId: string, year: number, params: any): Promise<PivotResult> {
  return api.post(P.worksheet.pivot, { project_id: projectId, year, ...params })
}

export async function exportPivotExcel(projectId: string, year: number, params: any): Promise<void> {
  // 经 http 取 blob 再保存：原先 window.open 新标签页带不上 Bearer 头，恒 401
  await downloadFile(P.worksheet.pivotExport, {
    params: {
      project_id: projectId, year: String(year),
      row_dimension: params.row_dimension || 'account',
      col_dimension: params.col_dimension || 'company',
      value_field: params.value_field || 'consolidated_amount',
      transpose: String(params.transpose || false),
      aggregation_mode: params.aggregation_mode || 'self',
    },
    fileName: `合并透视_${year}.xlsx`,
  })
}

export async function saveQueryTemplate(projectId: string, name: string, params: any): Promise<QueryTemplate> {
  return api.post(P.worksheet.pivotTemplates, { project_id: projectId, name, ...params })
}

export async function listQueryTemplates(projectId: string): Promise<QueryTemplate[]> {
  const res = await api.get(`${P.worksheet.pivotTemplates}?project_id=${projectId}`)
  return res?.templates || []
}

// ─── 按报表行次读时计算（与合并报表同一求值；需求 4~5）──────────────────────────

function viewParams(projectId: string, opts: { reportType?: string; nodeKey?: string | null; year?: number | null }) {
  const params: Record<string, string | number> = { project_id: projectId }
  if (opts.reportType) params.report_type = opts.reportType
  if (opts.nodeKey) params.node_key = opts.nodeKey
  if (opts.year) params.year = opts.year
  return params
}

/** 合并试算平衡表页：某汇总节点按报表行次的五列净额（审定汇总 / 权益抵销 / 往来交易抵销 / 报表调整 / 合并审定数） */
export async function getConsolReportTrial(
  projectId: string, opts: { reportType: string; nodeKey?: string | null; year?: number | null; signal?: AbortSignal },
): Promise<ConsolReportTrialResponse> {
  return api.get(P.worksheet.reportTrial, { params: viewParams(projectId, opts), signal: opts.signal })
}

/** 报表差额表：汇总节点的直接子节点各一列 + 合计（= 该节点合并数） */
export async function getConsolReportBreakdown(
  projectId: string, opts: { reportType: string; nodeKey?: string | null; year?: number | null; signal?: AbortSignal },
): Promise<ConsolReportBreakdownResponse> {
  return api.get(P.worksheet.reportBreakdown, { params: viewParams(projectId, opts), signal: opts.signal })
}

/** 报表行某列 → 构成它的分录明细（只计已审批；贡献之和 = 该行该列） */
export async function drillConsolRowEntries(
  projectId: string,
  opts: { rowCode: string; measure: ConsolDrillMeasure; nodeKey?: string | null; year?: number | null; signal?: AbortSignal },
): Promise<ConsolEntryDrillResponse> {
  const params = viewParams(projectId, opts)
  params.row_code = opts.rowCode
  params.measure = opts.measure
  return api.get(P.worksheet.drillEntries, { params, signal: opts.signal })
}

/** 报表行审定汇总列 → 各数据节点的个别数 */
export async function drillConsolRowIndividual(
  projectId: string, opts: { rowCode: string; nodeKey?: string | null; year?: number | null; signal?: AbortSignal },
): Promise<{ year: number; row_code: string; rows: ConsolIndividualDrillRow[] }> {
  const params = viewParams(projectId, opts)
  params.row_code = opts.rowCode
  return api.get(P.worksheet.drillIndividual, { params })
}

// ─── 合并推送（需求 8）────────────────────────────────────────────────────────

/** 分录汇总表：差额户 × 科目 × 类型，与合并试算逐科目对账（只读） */
export async function getConsolEntrySummary(projectId: string, year: number): Promise<ConsolEntrySummary> {
  // 调用方（分录汇总表）自己显示失败原因 ⇒ 静默全局错误提示，避免弹两次
  return api.get(P.worksheet.entrySummary, { params: { project_id: projectId, year }, _dedupe: false, _silent: true } as any)
}

/** 报表页右键「查看合并明细」：报表行次按所选汇总节点（默认根）读时计算直接下级构成（弹窗自己显示失败原因） */
export async function getConsolRowBreakdown(
  projectId: string, year: number, rowCode: string, nodeKey?: string | null,
): Promise<ConsolRowBreakdown> {
  const params = nodeKey ? { node_key: nodeKey } : undefined
  return api.get(P.reports.consolBreakdown(projectId, year, rowCode), { params, _silent: true } as any)
}

/** 立即推送：本项目 + 上层合并项目依次重算差额表 → 合并试算 → 合并报表 → 标记附注待更新（后台执行） */
export async function pushConsolidation(
  projectId: string, year: number, trigger: ConsolPushTrigger = 'manual',
): Promise<ConsolPushAck> {
  return api.post<ConsolPushAck>(P.push(projectId, year), { trigger })
}

export async function getConsolPushRuns(projectId: string, year: number, limit = 10): Promise<ConsolPushRun[]> {
  const res = await api.get<{ runs: ConsolPushRun[] }>(P.pushRuns(projectId, year), { params: { limit } })
  return res?.runs || []
}

export async function getConsolPushStatus(projectId: string, year: number): Promise<ConsolPushStatus> {
  return api.get<ConsolPushStatus>(P.pushStatus(projectId, year))
}

// ─── 合并附注公式与差额（需求 6 / 7.2）────────────────────────────────────────

export async function listConsolNoteFormulas(
  templateType: ConsolNoteTemplateType, sectionId?: string, signal?: AbortSignal,
): Promise<ConsolNoteFormulaList> {
  const params: Record<string, string> = { template_type: templateType }
  if (sectionId) params.section_id = sectionId
  return api.get(P_cnf.list, { params, signal })
}

/** 写入仅限 admin / partner / manager（后端 require_role） */
export async function createConsolNoteFormula(payload: ConsolNoteFormulaPayload): Promise<ConsolNoteFormula> {
  return api.post(P_cnf.list, payload)
}

/** 改公式 ⇒ 来源变为「人工」（自动种子不再覆盖）；只改空白不算改 */
export async function updateConsolNoteFormula(
  formulaId: string,
  payload: { formula?: string; description?: string | null; expected_version?: number },
): Promise<ConsolNoteFormula> {
  return api.put(P_cnf.detail(formulaId), payload)
}

/** 删除（软删；自动种子不再补回该单元格）；须带当前版本号（spec formula-global-settings-sync） */
export async function deleteConsolNoteFormula(
  formulaId: string, expectedVersion?: number,
): Promise<{ id: string; deleted: boolean }> {
  return api.delete(P_cnf.detail(formulaId), { params: { expected_version: expectedVersion } })
}

/** 按当前模板与合并口径报表配置重新种子化（幂等；不覆盖人工、不补回人工删除的） */
export async function reseedConsolNoteFormulas(templateType: ConsolNoteTemplateType): Promise<Record<string, number>> {
  return api.post(`${P_cnf.seed}?template_type=${templateType}`)
}

/** 附注章节差额：有公式单元格的个别数汇总 / 调整 / 抵销 / 合并数 + 子节点贡献 */
export async function getConsolNoteBreakdown(
  projectId: string, year: number, sectionId: string,
  opts: { nodeKey?: string | null; standard?: string | null; signal?: AbortSignal } = {},
): Promise<ConsolNoteBreakdown> {
  const params: Record<string, string> = {}
  if (opts.nodeKey) params.node_key = opts.nodeKey
  if (opts.standard) params.standard = opts.standard
  return api.get(P_cn.breakdown(projectId, year, sectionId), { params, signal: opts.signal })
}

/**
 * 按公式填入：合并数写入章节数据（手工单元格保留并列出；清除待更新标记；合并锁定时 423）。
 * nodeKey 可选：新版合并页面传入当前树节点，后端按节点行写入；旧调用省略时走 NULL 兼容路径。
 * 设计：consol-node-key-isolation-and-shared-context §四
 */
export async function fillConsolNoteByFormula(
  projectId: string, year: number, sectionId: string,
  standard?: string | null, nodeKey?: string | null,
): Promise<ConsolNoteFillResult> {
  const url = P_cn.fillByFormula(projectId, year, sectionId)
  const qs = new URLSearchParams()
  if (standard) qs.set('standard', standard)
  if (nodeKey) qs.set('node_key', nodeKey)
  const qstr = qs.toString()
  // 400（模板口径不匹配）/ 423（合并锁定）须由附注页带具体操作语境展示，抑制全局重复 toast
  return api.post(qstr ? `${url}?${qstr}` : url, undefined, { _silent: true } as any)
}


// ═══════════════════════════════════════════════════════════════════════════════
// 合并附注明细模板与多企业行映射规则（spec: consol-note-detail-template-and-mapping）
// ═══════════════════════════════════════════════════════════════════════════════

export interface DetailTemplateRow { target_row_id: string; canonical_name: string; aliases: string[]; sort_order: number; row_type: 'data' | 'total' | 'subtotal' }
export interface DetailTemplateVersion { id: string; template_id: string; version_number: number; rows: DetailTemplateRow[]; change_note: string | null; created_by: string | null; created_at: string | null }
export interface DetailTemplate { id: string; template_type: 'soe' | 'listed'; section_id: string; name: string; visibility: 'draft' | 'project' | 'firm'; created_by: string | null; created_at: string | null; latest_version?: DetailTemplateVersion }
export interface DetailTemplateBinding { id: string; project_id: string; section_id: string; template_version_id: string; version_number: number | null; bound_by: string | null; bound_at: string | null }
export interface MappingRuleItem { source_label: string; source_row_key?: string; target_row_id: string; mapping_action: 'map' | 'map_merge' | 'create' | 'ignore'; ignore_reason?: string; /** 同名行第几次出现（从 0 起；不写 = 全部同名行） */ source_occurrence?: number }
export interface MappingRule { id: string; project_id: string; section_id: string; template_version_id: string; source_structure_hash: string; version_number: number; mappings: MappingRuleItem[]; confirmed_by: string | null; confirmed_at: string | null; is_active: boolean }
export interface SourceGroup { hash: string; section_id: string; source_rows: Array<{ label: string; row_type: string; key: string; occurrence?: number }>; entities: Array<{ node_key: string; project_id: string; company_name: string }>; has_rule: boolean; rule_id: string | null; all_confirmed: boolean }
export interface StaleEntity { node_key: string; company_name: string; old_hash: string; new_hash: string; status: 'stale' }
/** 明细映射建议：`auto_confirmable` = 下推行 / 精确 / 别名 / 通用别名 / 历史且有目标行（「⚡ 自动映射」只确认这类） */
export interface MappingSuggestion { source_label: string; /** 同名行逐个建议时的出现序号（R11） */ source_occurrence?: number; suggested_target: { target_row_id: string; canonical_name: string } | null; confidence: number; match_type: 'exact_id' | 'exact' | 'alias' | 'global_alias' | 'previous_year' | 'history' | 'fuzzy' | 'manual'; candidates: any[]; auto_confirmable?: boolean }
/** 一家企业单体附注的来源读取状态（found 已读到 / missing 未生成 / not_applicable 本期无此情形 / no_source 合并特有章节 / unreadable 读不出表） */
export interface EntitySourceStatus { node_key: string; project_id: string; company_name: string; status: 'found' | 'missing' | 'not_applicable' | 'no_source' | 'unreadable'; reason: string | null; table_name?: string | null; row_count?: number; unmatched_columns?: string[]; ratio_columns?: string[] }
export interface DetailRefreshPreview { preview_token: string; project_id: string; section_id: string; year: number; template_version_id: string | null; template_rows: DetailTemplateRow[]; groups: SourceGroup[]; stale_entities: StaleEntity[]; suggestions: MappingSuggestion[]; entity_count: number; group_count: number; stale_count: number; entity_sources?: EntitySourceStatus[]; missing_count?: number }
export interface ConfirmMappingResult { action: 'confirmed'; rule_id: string; version_number: number; bound_count: number; excluded_count: number }
export interface ApplyDetailResult { status: 'applied' | 'skipped_locked'; section_id: string; node_key?: string | null; applied_entity_count?: number; filled_count?: number; kept_manual_count?: number; reason?: string; skipped_entities?: Array<{ node_key: string; reason: string }>; unbound_entities?: Array<{ node_key: string; company_name: string }>; out_of_scope_count?: number }
export interface SuggestTemplateResult { section_id: string; entity_count: number; group_count: number; suggested_rows: Array<DetailTemplateRow & { frequency: number; total_amount: number; entity_total: number; origin?: 'template' | 'source' }>; entity_sources?: EntitySourceStatus[] }

export async function createDetailTemplate(data: { template_type: string; section_id: string; name?: string; visibility?: string; rows: Array<Partial<DetailTemplateRow>>; change_note?: string }): Promise<DetailTemplate> { return api.post('/api/consol-note-templates', data) }
export async function listDetailTemplates(params?: { template_type?: string; section_id?: string; visibility?: string }): Promise<DetailTemplate[]> { const qs = new URLSearchParams(); if (params?.template_type) qs.set('template_type', params.template_type); if (params?.section_id) qs.set('section_id', params.section_id); if (params?.visibility) qs.set('visibility', params.visibility); const q = qs.toString(); return api.get(`/api/consol-note-templates${q ? `?${q}` : ''}`) }
export async function getDetailTemplate(templateId: string): Promise<DetailTemplate> { return api.get(`/api/consol-note-templates/${templateId}`) }
export async function addDetailTemplateVersion(templateId: string, data: { rows: Array<Partial<DetailTemplateRow>>; change_note?: string }): Promise<DetailTemplateVersion> { return api.post(`/api/consol-note-templates/${templateId}/versions`, data) }
export async function getDetailTemplateVersions(templateId: string): Promise<DetailTemplateVersion[]> { return api.get(`/api/consol-note-templates/${templateId}/versions`) }
export async function deleteDetailTemplate(templateId: string): Promise<{ id: string; deleted: boolean }> { return api.delete(`/api/consol-note-templates/${templateId}`) }
export async function checkRowDeletion(templateId: string, targetRowIds: string[]): Promise<{ affected_rule_count: number; affected_entity_count: number; details: any[] }> { return api.post(`/api/consol-note-templates/${templateId}/check-row-deletion`, { target_row_ids: targetRowIds }) }
export async function bindDetailTemplate(projectId: string, sectionId: string, data: { template_version_id: string; confirm?: boolean }): Promise<any> { return api.put(`/api/projects/${projectId}/consol-note-template-binding/${sectionId}`, data) }
export async function getDetailTemplateBindings(projectId: string): Promise<DetailTemplateBinding[]> { return api.get(`/api/projects/${projectId}/consol-note-template-binding`) }
export async function getDetailTemplateBinding(projectId: string, sectionId: string): Promise<DetailTemplateBinding | null> { try { return await api.get(`/api/projects/${projectId}/consol-note-template-binding/${sectionId}`) } catch { return null } }
export async function getDetailMappingRules(projectId: string, sectionId?: string): Promise<MappingRule[]> { const qs = sectionId ? `?section_id=${encodeURIComponent(sectionId)}` : ''; return api.get(`/api/projects/${projectId}/consol-note-mapping/rules${qs}`) }
export async function createDetailMappingRule(projectId: string, data: { section_id: string; template_version_id: string; source_structure_hash: string; mappings: MappingRuleItem[] }): Promise<MappingRule> { return api.post(`/api/projects/${projectId}/consol-note-mapping/rules`, data) }
export async function deactivateDetailMappingRule(projectId: string, ruleId: string): Promise<{ id: string; deactivated: boolean }> { return api.put(`/api/projects/${projectId}/consol-note-mapping/rules/${ruleId}/deactivate`, {}) }
export async function previewDetailRefresh(projectId: string, sectionId: string, year: number): Promise<DetailRefreshPreview> { return api.post(`/api/projects/${projectId}/consol-note-detail-refresh/preview`, { section_id: sectionId, year }) }
export async function suggestDetailTemplate(projectId: string, sectionId: string, year: number): Promise<SuggestTemplateResult> { return api.post(`/api/projects/${projectId}/consol-note-detail-refresh/suggest-template`, { section_id: sectionId, year }) }
export async function confirmDetailMapping(projectId: string, data: { section_id: string; year: number; template_version_id: string; source_structure_hash: string; mappings: MappingRuleItem[]; entity_node_keys: Array<{ node_key: string; project_id: string; hash: string }>; excluded_node_keys?: string[]; preview_token?: string; current_entity_hashes?: Record<string, string> }): Promise<ConfirmMappingResult> { return api.post(`/api/projects/${projectId}/consol-note-detail-refresh/confirm-mapping`, data) }
export async function applyDetailRefresh(projectId: string, data: { section_id: string; year: number; node_key?: string | null; preview_entity_hashes?: Record<string, string> }): Promise<ApplyDetailResult> { return api.post(`/api/projects/${projectId}/consol-note-detail-refresh/apply`, data) }
/** ⚡ 自动映射逐章节结果：mapped 全部确认 / partial 部分企业待确认 / pending 都待确认 / skipped 没读到来源 / failed */
export interface AutoMapSection { section_id: string; status: 'mapped' | 'partial' | 'pending' | 'skipped' | 'failed'; reason: string | null; template_action: 'created' | 'versioned' | 'existing' | null; confirmed: Array<{ node_key: string; company_name: string }>; already: Array<{ node_key: string; company_name: string }>; pending: Array<{ node_key: string; company_name: string; labels: string[] }> }
export interface AutoMapResult { template_type: string; sections: AutoMapSection[]; summary: { sections: number; mapped: number; partial: number; pending: number; skipped: number; failed: number; templates_created: number; confirmed_entities: number; pending_entities: number } }
/** ⚡ 自动映射（调用方自管提示 ⇒ 静默）；`section_ids` 为空 = 全部有单体对应的章节 */
export async function autoMapDetail(projectId: string, data: { year: number; section_ids?: string[] | null }): Promise<AutoMapResult> { return api.post(`/api/projects/${projectId}/consol-note-detail-refresh/auto-map`, data, { _silent: true } as any) }
