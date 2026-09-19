/**
 * 通用 API 服务 — 覆盖各页面直接 http 调用的端点
 * 规则：所有页面必须通过 API 服务层调用，不允许直接拼 URL
 */
import http from '@/utils/http'
import {
  projects as P_proj, staff as P_staff, procedures as P_proc,
  procedureRowTasks as P_prt, workpaperLeads as P_leads,
  dashboard as P_dash, disclosureNotes as P_dn, users as P_usr,
  system as P_sys, recycleBin as P_rb, knowledge as P_kb,
  admin as P_admin, auth as P_auth, attachments as P_att,
  annotations as P_ann, reviewConversations as P_rc, forum as P_forum,
  reportReview as P_rr, ledger as P_ledger, tAccounts as P_ta,
  customTemplates as P_ct, regulatory as P_reg, templateLibrary as P_tl,
  excelHtml as P_eh, importIntelligence as P_ii, addressRegistry as P_ar,
  workpapers as P_wp, workHours as P_wh, aging as P_aging,
  consolidation as P_consol, wpManuals as P_wpm, wpFineRules as P_wfr,
  wpDependencies as P_wdep, reportFormatTemplates as P_rft,
  sampling as P_samp, processRecord as P_pr, wpAI as P_wpai,
  projects as P_projects, jobs as P_jobs,
  aiPlugins as P_aip, gtCoding as P_gtc,
  riskAssessments as P_risk,
} from '@/services/apiPaths'

// ── 项目 ──

export async function listProjects(params?: Record<string, any>): Promise<any[]> {
  const { data } = await http.get(P_proj.list, { params })
  return Array.isArray(data) ? data : data?.items || []
}

export async function listProjectsWithProgress(): Promise<any[]> {
  // 仪表盘甘特/卡片视图专用：含 start_date / due_date / overall_progress / partner_name / manager_name
  const { data } = await http.get(P_proj.listWithProgress, { validateStatus: () => true })
  return Array.isArray(data) ? data : data?.items || []
}

export async function getProjectWizardState(projectId: string): Promise<any> {
  const { data } = await http.get(P_proj.wizard(projectId), { _silent: true } as any)
  return data
}

// ── 企业子类型推荐（audit-report-template-integration 需求 7.6） ──

export interface TemplateRecommendation {
  subtype: string | null
  confidence: string
  candidates: string[]
  matched_rules: string[]
  source: string
  // 需求 1.7/1.8/14.3：项目当前已保存值（用户手动优先）+「待确认」横幅标志
  current_subtype?: string | null
  needs_confirmation?: boolean
}

/** 根据项目属性获取企业子类型（模板 A/B/C/D）推荐。 */
export async function fetchTemplateRecommendation(projectId: string): Promise<TemplateRecommendation> {
  const { data } = await http.get(P_proj.templateRecommendation(projectId), {
    validateStatus: () => true,
  })
  return data as TemplateRecommendation
}

// ── 人员 ──

export async function getMyStaffId(): Promise<string | null> {
  const { data } = await http.get(P_staff.meStaffId, { validateStatus: () => true })
  return data?.staff_id || data?.data?.staff_id || null
}

export async function getMyAssignments(): Promise<any[]> {
  // 后端真实端点是 /api/projects/my/assignments（assignments.py）；
  // P_staff.myAssignments 指向 /api/staff/my/assignments 是历史命名错误，已不存在。
  const { data } = await http.get(P_proj.myAssignments, { validateStatus: () => true })
  return Array.isArray(data) ? data : data || []
}

export async function getMyTodos(): Promise<any[]> {
  const { data } = await http.get(P_staff.myTodos, { validateStatus: () => true })
  return Array.isArray(data) ? data : data?.items || []
}

export async function searchStaff(query: string, limit = 20): Promise<any[]> {
  const { data } = await http.get(P_staff.list, { params: { search: query, limit } })
  return data?.items || (Array.isArray(data) ? data : [])
}

// ── 审计程序 ──

export async function getProcedures(projectId: string, cycle: string): Promise<any[]> {
  const { data } = await http.get(P_proc.list(projectId, cycle), { validateStatus: () => true })
  return Array.isArray(data) ? data : data || []
}

export async function updateProcedureTrim(projectId: string, cycle: string, items: any[]): Promise<void> {
  await http.put(P_proc.trim(projectId, cycle), { items })
}

// ── 程序行任务（procedure-delegation-notification / Task 12，V105 真源） ──

export interface ProcedureRowTaskItem {
  task_id: string
  project_id: string
  wp_index_id: string
  wp_id: string | null
  definition_key: string
  sheet_key: string
  wp_code: string | null
  sheet_name: string | null
  program_no: string | null
  procedure_text: string | null
  audit_cycle_snapshot: string
  applicability_status: string
  workflow_status: string
  assignee_staff_id: string | null
  reviewer_staff_id: string | null
  assignment_version: number
  lock_version: number
  due_at: string | null
  overdue: boolean
  materialization_required: boolean
  my_role: 'assignee' | 'reviewer' | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ProcedureRowTaskPage {
  items: ProcedureRowTaskItem[]
  pagination: { page: number; page_size: number; total: number; total_pages: number }
}

export interface ProcedureRowTaskQuery {
  projectId?: string
  cycle?: string
  wpIndexId?: string
  workflowStatus?: string
  role?: 'assignee' | 'reviewer'
  overdueOnly?: boolean
  page?: number
  pageSize?: number
}

function _rowTaskParams(q: ProcedureRowTaskQuery): Record<string, any> {
  const params: Record<string, any> = {}
  if (q.cycle) params.cycle = q.cycle
  if (q.wpIndexId) params.wp_index_id = q.wpIndexId
  if (q.workflowStatus) params.workflow_status = q.workflowStatus
  if (q.role) params.role = q.role
  if (q.overdueOnly) params.overdue_only = true
  if (q.page) params.page = q.page
  if (q.pageSize) params.page_size = q.pageSize
  return params
}

/** 跨项目"我的程序任务"分页查询（V105 任务真源，纯读）。 */
export async function listMyProcedureRowTasks(q: ProcedureRowTaskQuery = {}): Promise<ProcedureRowTaskPage> {
  const params = _rowTaskParams(q)
  if (q.projectId) params.project_id = q.projectId
  const { data } = await http.get(P_prt.listMine(), { params, validateStatus: () => true })
  return (data?.data ?? data) as ProcedureRowTaskPage
}

/** 项目级"我的程序任务"分页查询（纯读）。 */
export async function listProjectProcedureRowTasks(projectId: string, q: ProcedureRowTaskQuery = {}): Promise<ProcedureRowTaskPage> {
  const { data } = await http.get(P_prt.listByProject(projectId), {
    params: _rowTaskParams(q), validateStatus: () => true,
  })
  return (data?.data ?? data) as ProcedureRowTaskPage
}

/** 单任务详情 + 深链定位 key（纯读）。 */
export async function getProcedureRowTaskDetail(projectId: string, taskId: string): Promise<ProcedureRowTaskItem> {
  const { data } = await http.get(P_prt.detail(projectId, taskId))
  return (data?.data ?? data) as ProcedureRowTaskItem
}

export interface ProcedureRowTaskTransition {
  action: 'acknowledge' | 'start' | 'submit' | 'request_changes' | 'review' | 'assign' | 'reassign' | 'cancel' | 'reopen'
  request_id?: string
  expected_lock_version?: number
  expected_assignment_version?: number
  reason?: string
  execution_summary?: string
  evidence_snapshot?: any[]
  open_issue_count?: number
}

/**
 * 程序行任务状态转换（单一状态机入口）。
 * payload 必须携带 request_id + expected 版本（乐观锁 / assignment_version），
 * 绝不再走 updateProcedureTrim 提交 execution_status（旧 bug 已修）。
 */
export async function transitionProcedureRowTask(
  projectId: string, taskId: string, body: ProcedureRowTaskTransition,
): Promise<any> {
  const { data } = await http.post(P_prt.transition(projectId, taskId), body)
  return data?.data ?? data
}

// ── 两层裁剪 / 方案 preview-apply（Task 6，一次性 preview 凭证 + 真实统计） ──

export interface TrimSchemeEntry {
  kind: 'scope' | 'row'
  cycle?: string
  wp_index_code?: string
  target_status?: string
  template_code?: string
  sheet_key?: string
  definition_key?: string
  target_applicability?: string
}

/** 裁剪方案预览：解析计划 + 创建一次性 preview 凭证（返回 preview_id/token、目标统计、TTL）。 */
export async function previewProcedureTrim(
  projectId: string, entries: TrimSchemeEntry[], schemeId?: string,
): Promise<any> {
  const { data } = await http.post(P_prt.trimPreview(projectId), {
    entries, scheme_id: schemeId ?? null,
  })
  return data?.data ?? data
}

/** 裁剪方案应用：消费 preview，返回真实 applied/unchanged/conflict；篡改/过期/版本变化 → 409。 */
export async function applyProcedureTrim(
  projectId: string, previewId: string, requestId: string, entries: TrimSchemeEntry[], schemeId?: string,
): Promise<any> {
  const { data } = await http.post(P_prt.trimApply(projectId), {
    preview_id: previewId, request_id: requestId, entries, scheme_id: schemeId ?? null,
  })
  return data?.data ?? data
}

// ── canonical 粗裁（ProcedureTrimming.vue 主链入口）────────────────────────────
// 与 previewProcedureTrim/applyProcedureTrim 走同一端点，但签名更贴合粗裁页调用方。
// entries 里每条包含 kind/cycle/wp_index_code/target_status/skip_reason/reason_code。
//
// 🔴 `reason_code` 是 additive 可选字段（procedure-trimming-and-delegation-intelligence
//    Task 12）。它必须与 `target_status` **同一次请求**提交 —— 不得「先 apply 状态
//    再补写理由码」：一次性 preview 凭证不覆盖第二次写入，且会产生「状态已改、
//    理由码未写」的中间态。
//
// 🔴 不传该字段时请求体与扩展前**逐字节相同**（后端归一函数条件性写入该键），
//    故存量调用方零影响。传了则后端同事务写 `procedure_instances.suggestion_state.reason_code`。

/** canonical 粗裁 scope entry（`reason_code` 为 additive 可选字段）。 */
export interface CanonicalTrimScopeEntry {
  kind: string
  cycle: string
  wp_index_code: string
  target_status: string
  skip_reason?: string | null
  /** 结构化裁剪理由码（取值域见 composables/trimReasonCodes.ts，与后端 TrimReasonCode 交叉锁死）。 */
  reason_code?: string | null
}

/** 粗裁 canonical preview：构造 scope entries → 创建一次性 preview 凭证。 */
export async function canonicalTrimPreview(
  projectId: string,
  entries: CanonicalTrimScopeEntry[],
): Promise<any> {
  const { data } = await http.post(P_prt.trimPreview(projectId), { entries })
  return data?.data ?? data
}

/**
 * 驳回裁剪建议：写 `suggestion_state.rejected`，**不改 status/skip_reason**。
 *
 * 🔴 与「确认裁剪」走的是两条不同路径，不可混用：
 * - 确认 → canonical trim preview/apply（改适用性状态 + 写理由码）
 * - 驳回 → 本端点（只标记「不接受建议」，程序仍保留在原状态）
 *
 * 驳回后决策内核恒判 `keep`（`procedureTrimDecision` 档 2），不再重复提示（R6.4）。
 */
export async function rejectTrimSuggestions(
  projectId: string,
  cycle: string,
  wpIndexCodes: string[],
  reason?: string | null,
): Promise<{ rejected: number; not_found: string[] }> {
  const { data } = await http.post(P_prt.trimRejectSuggestions(projectId), {
    cycle,
    wp_index_codes: wpIndexCodes,
    reason: reason ?? null,
  })
  const p = data?.data ?? data
  return {
    rejected: Number(p?.rejected ?? 0),
    not_found: Array.isArray(p?.not_found) ? p.not_found : [],
  }
}

/** 粗裁 canonical apply：消费 preview + request_id 幂等。 */
export async function canonicalTrimApply(
  projectId: string,
  entries: CanonicalTrimScopeEntry[],
  previewId: string,
  requestId: string,
): Promise<any> {
  const { data } = await http.post(P_prt.trimApply(projectId), {
    entries, preview_id: previewId, request_id: requestId,
  })
  return data?.data ?? data
}

// ── 三粒度委派 preview-apply（Task 8，materialize 前置 + 一次性 preview 凭证） ──

export interface DelegationSelector {
  kind: 'cycle' | 'workpaper' | 'row'
  cycle?: string
  wp_index_ids?: string[]
  task_ids?: string[]
}

export interface DelegationPreviewBody {
  selector: DelegationSelector
  assignee_staff_id: string
  reviewer_staff_id?: string | null
  unassigned_only?: boolean
  conflict_policy?: string
  reason?: string
  best_effort?: boolean
  due_at?: string | null
}

/** 委派预览：materialize 前置 job + 目标/冲突分类 + 一次性 preview 凭证（status=ready/materialization_pending）。 */
export async function previewProcedureDelegation(
  projectId: string, body: DelegationPreviewBody,
): Promise<any> {
  const { data } = await http.post(P_prt.delegationPreview(projectId), body)
  return data?.data ?? data
}

/** 委派应用：消费 preview，真实 assign/reassign；默认整批原子（冲突 409），best_effort 逐任务结果。 */
export async function applyProcedureDelegation(
  projectId: string, previewId: string, requestId: string, body: DelegationPreviewBody,
): Promise<any> {
  const { data } = await http.post(P_prt.delegationApply(projectId), {
    ...body, preview_id: previewId, request_id: requestId,
  })
  return data?.data ?? data
}

/**
 * 成员负载批量视图（只读）。
 *
 * 口径 = 各执行人当前**非终态任务数**，与委派 preview 返回的
 * `membership_load.active_task_count` 同源（后端同一 service 方法族）。
 *
 * 🔴 前端**不得**再自行按"底稿张数"聚合一份负载 —— 那是双真源且口径不同
 * （历史实现还依赖先打开全项目概览才有值）。
 *
 * 未出现在返回 `loads` 里的成员 = 当前无非终态任务（负载 0）；
 * 请求失败时调用方须显示"负载未知"而非 0（0 会误导为"这个人很空闲"）。
 */
export async function fetchDelegationMemberLoads(
  projectId: string,
): Promise<Record<string, number>> {
  const { data } = await http.get(P_prt.delegationMemberLoads(projectId))
  const payload = data?.data ?? data
  const loads = payload?.loads
  return loads && typeof loads === 'object' ? loads as Record<string, number> : {}
}

/**
 * B50 认定层次风险行（只读）。
 *
 * 复用**既有**端点 `GET /api/b60/b50-risk-rows`（本为 B60 六/七章一键带入而建），
 * 它直接返回 `load_b50_accounts()` 输出 ⇒ 裁剪页取 B50 完成度**零后端改动**。
 *
 * 🔴 不要为此新建 `/api/b50/risk-rows` 之类的第二个端点 —— 那会让「B50 认定层次
 * 数据」出现两个读取口径，两侧下次各自演进即漂移。
 *
 * B50 未编制 / 查询失败时后端返回空列表（不报错），故调用方拿到 `[]` 时**不能**
 * 断定「B50 未填」—— 只能断定「读不到数据」；两者在裁剪页都显示为「未开始」，
 * 但请求本身失败要另标「状态未知」。
 */
export async function fetchB50RiskRows(projectId: string): Promise<{
  fs_risks: any[]
  assertion_risks: any[]
  accounts: any[]
}> {
  const { data } = await http.get(P_risk.b50RiskRows(), { params: { project_id: projectId } })
  const payload = data?.data ?? data
  return {
    fs_risks: Array.isArray(payload?.fs_risks) ? payload.fs_risks : [],
    assertion_risks: Array.isArray(payload?.assertion_risks) ? payload.assertion_risks : [],
    accounts: Array.isArray(payload?.accounts) ? payload.accounts : [],
  }
}

// ── 裁剪三维判据上下文（Task 9，只读） ──

/** 降级标注：`cause` 是 accounts 维度**专属**可选字段（其余维度只有 dimension+reason）。 */
export interface TrimDecisionDegradation {
  dimension:
    | 'accounts'
    | 'materiality'
    | 'risk'
    | 'completeness_override'
    | 'workpaper_entry'
    /** 报表行取数维度（spec procedure-trim-report-line-account-resolution Task 7） */
    | 'report_line'
  reason: string
  /** 仅 accounts 维度出现：query_failed / not_imported / no_material_accounts */
  cause?: 'query_failed' | 'not_imported' | 'no_material_accounts'
}

/**
 * 一条底稿的报表行科目金额（后端 `trim_report_line_amounts.ReportLineAmount`）。
 *
 * 🔴 `status !== 'resolved'` 时 `amount` 恒为 `null`，**绝不为 `0`** —— 编造 0 会让
 * 该程序被误判成「低于任何阈值」而产生裁剪建议，而正确结论是「这个判据对它不可用」。
 * 消费方一律先判 `status`，不要直接用 `amount ?? 0`。
 *
 * 四态成因各自可区分（`reason` 写明细节）：
 * - `no_report_line`：该底稿没有报表行落点（未登记 / 声明为空 / 非科目余额驱动循环）
 * - `formula_unavailable`：报表行存在但公式缺失、含 `ROW()` 引用、或求值失败
 * - `standard_unset`：项目适用准则未确定（未设置 / 两处声明分叉 / 无对应配置）
 */
export interface TrimReportLineAmount {
  status: 'resolved' | 'no_report_line' | 'formula_unavailable' | 'standard_unset'
  /** 🔴 非 resolved 态恒 null */
  amount: number | null
  /** 报表行编码（如 BS-002），溯源用 */
  row_code: string
  /** 报表行名（如 货币资金）—— 审计师据它发现「行名与循环语义不符」 */
  row_name: string
  /** 命中的取数公式原文 */
  formula: string | null
  /** 参与计算的标准科目码 */
  standard_codes: string[]
  /** 实际使用的准则变体 */
  applicable_standard: string
  /** 报表行编码的取值出处（如 e_cycle_specs.E1_REPORT_ROW_CODE） */
  source_symbol: string
  /** 非 resolved 态的中文原因 */
  reason: string
}

export interface TrimDecisionContext {
  /** {科目名: {amount, cycle}}；空 dict ⇒ 数据存在性判据不可用 ⇒ 不得裁剪 */
  accounts: Record<string, { amount: number; cycle: string }>
  /**
   * 两键齐全或整体 null，**不会半开**。
   * 🔴 后端刻意不下发 `overall_materiality` —— 前端也不得自行按比例推算实际执行重要性
   * （那是会计判断，Requirement 4.6）。
   */
  materiality: { performance_materiality: number; trivial_threshold: number } | null
  /** {科目名: B50 科目项（cells / max_risk / has_special / balance / category / is_estimate…）} */
  risk: Record<string, any>
  /** 「至少一个认定有 rmm」即为 true（不是「六认定全填」，两个口径有意不统一） */
  risk_dimension_available: boolean
  /** {cycle: bool}；键不存在 ⇒ 该循环未覆盖，退回平台默认清单。null ⇒ 读取失败 */
  completeness_override: Record<string, boolean> | null
  /** {wp_code: bool}；空 dict 必伴随一条 workpaper_entry degradation */
  workpaper_entry: Record<string, boolean>
  /**
   * {wp_code: 报表行科目金额}；空 dict 必伴随一条 `report_line` degradation。
   *
   * 键是 `procedure_instances.wp_code` **原样**（含 `D2-1至D2-4` 这类区间型），
   * 故按 `p.wp_code` 直接查即命中；`resolveAccountAmount` 另有归一兜底
   * （防后端将来改成按底稿主码下发）。
   *
   * 🔴 消费方一律经 `trimAmountSource.resolveAccountAmount()` 取金额，不要自己读这个
   * 字段 —— 裁剪页与复核视图各读一次就会分叉，而复核者无从知道该信哪个。
   */
  report_line_amounts: Record<string, TrimReportLineAmount>
  /** 🔴 前端摘要降级标注的**唯一来源** —— 不要自行判断「某维度是不是空的」 */
  degradations: TrimDecisionDegradation[]
}

/**
 * 裁剪三维判据上下文（只读）：风险评估 / 重要性 / 数据存在性 + 完整性豁免覆盖 + 底稿录入探测。
 *
 * 供前端决策内核 `procedureTrimDecision.ts` 消费。后端 fail-soft：任一维度取数失败 →
 * 该维度置 null/空 + `degradations` 记一条，**不抛异常也不伪造默认值**。
 *
 * 🔴 本函数**不吞**请求级错误（网络/权限/500）：整体拿不到判据时必须让调用方 catch 并
 * 显示「判据不可用，已阻断裁剪」。若在此吞成空上下文，前端决策内核会看到 `accounts={}`
 * 且 `degradations=[]` ⇒ 与「后端说没有任何降级」不可区分，可能被误判为"可以裁"。
 *
 * @param cycles 循环代号数组；空数组 = 全部科目余额驱动循环（不过滤）
 */
export async function fetchTrimDecisionContext(
  projectId: string,
  year: number,
  cycles: string[] = [],
): Promise<TrimDecisionContext> {
  const params: Record<string, any> = { year }
  const list = (cycles || []).map(c => String(c).trim()).filter(Boolean)
  if (list.length) params.cycles = list.join(',')
  const { data } = await http.get(P_proc.trimDecisionContext(projectId), { params })
  const p = data?.data ?? data
  const asObj = (v: any) => (v && typeof v === 'object' && !Array.isArray(v) ? v : {})
  return {
    accounts: asObj(p?.accounts),
    // null 与 {} 语义不同（缺失 vs 齐全），故不套 asObj 兜底
    materiality: p?.materiality ?? null,
    risk: asObj(p?.risk),
    risk_dimension_available: p?.risk_dimension_available === true,
    completeness_override: p?.completeness_override ?? null,
    workpaper_entry: asObj(p?.workpaper_entry),
    // 🔴 缺失时兜成 `{}` 而不是留 `undefined`：让每个调用方各自兜底会产生
    //    「一处判 undefined、一处判空对象」的不一致。空对象的语义已由
    //    `report_line` degradation 承载（后端保证空 dict 必伴随标注）。
    report_line_amounts: asObj(p?.report_line_amounts),
    degradations: Array.isArray(p?.degradations) ? p.degradations : [],
  }
}

// ── 完整性敏感清单的项目级覆盖（Task 14，R5.5 / R5.6 / R5.7） ──

/**
 * 一条项目级覆盖（落 `checklist_responses` 的 `B50-T3-cscope-{cycle}`）。
 *
 * 🔴 承载表**只保留当前值** —— `updated_by_name` / `updated_at` 是**最后一次**修改的
 * 留痕，不是变更历史。需要完整历史属另一议题（R5.5 明确只要求最后一次的 who/when/why）。
 */
export interface CompletenessScopeOverride {
  /** 循环代号（大写单字母，如 `L`） */
  cycle: string
  /** true = 本项目确认该循环属完整性敏感（豁免金额判据）；false = 确认不属 */
  sensitive: boolean
  /** 覆盖理由（写入时必填，供质控与项目质量控制复核人评价其适当性） */
  reason: string
  /** 最后一次修改时间（ISO 字符串）；null = 后端未记录 */
  updated_at: string | null
  /** 最后一次修改人用户名；null = 关联用户已删或未记录 */
  updated_by_name: string | null
}

/**
 * 读回本项目全部完整性敏感清单覆盖（含理由与留痕）。
 *
 * 🔴 **未出现在返回里的循环 = 未覆盖**（前端据此退回平台默认清单
 * `completenessExemption.COMPLETENESS_CYCLE_RULES` 并标注「使用平台默认，未经本项目确认」）。
 * 故本函数**不吞**请求级错误：吞成空数组会让「读不到」与「一条都没覆盖过」不可区分，
 * 从而把技术故障显示成「全部使用平台默认」这一实质结论。
 */
export async function fetchCompletenessScopeOverrides(
  projectId: string,
): Promise<CompletenessScopeOverride[]> {
  const { data } = await http.get(P_prt.trimCompletenessScope(projectId))
  const payload = data?.data ?? data
  const list = Array.isArray(payload?.overrides) ? payload.overrides : []
  return list.map((o: any) => ({
    cycle: String(o?.cycle ?? '').toUpperCase(),
    sensitive: o?.sensitive === true,
    reason: String(o?.reason ?? ''),
    updated_at: o?.updated_at ?? null,
    updated_by_name: o?.updated_by_name ?? null,
  })).filter((o: CompletenessScopeOverride) => o.cycle !== '')
}

/**
 * 写一条项目级覆盖（`sensitive` 为 `true`/`false` **都算已表态**）。
 *
 * 🔴 `reason` 必填且后端按空白串拒绝（400）—— 覆盖平台默认清单是一项要向质控解释的
 * 职业判断，无理由的覆盖在复核时无法评价其适当性。调用方须在发请求前自行校验并给出
 * 可操作提示，不要靠 400 兜底（那会把可预期的校验显示成"保存失败"）。
 */
export async function saveCompletenessScopeOverride(
  projectId: string,
  cycle: string,
  sensitive: boolean,
  reason: string,
): Promise<{ cycle: string; sensitive: boolean; created: boolean; updated: boolean }> {
  const { data } = await http.put(P_prt.trimCompletenessScope(projectId), {
    cycle, sensitive, reason,
  })
  const p = data?.data ?? data
  return {
    cycle: String(p?.cycle ?? cycle).toUpperCase(),
    sensitive: p?.sensitive === true,
    created: p?.created === true,
    updated: p?.updated === true,
  }
}

/**
 * 撤销某循环的项目级覆盖 → 该循环退回平台默认清单。
 *
 * 🔴 走 `DELETE` 删行而不是 `PUT` 写空值：读取侧以「该循环是否出现在返回里」区分
 * 「已表态」与「未覆盖」，写空值会留一条既非表态也非缺失的脏记录。
 */
export async function clearCompletenessScopeOverride(
  projectId: string,
  cycle: string,
): Promise<{ cycle: string; deleted: number }> {
  const { data } = await http.delete(P_prt.trimCompletenessScopeItem(projectId, cycle))
  const p = data?.data ?? data
  return { cycle: String(p?.cycle ?? cycle).toUpperCase(), deleted: Number(p?.deleted ?? 0) }
}

// ── 附注反向联动（Task 21，R13.1 / R13.2 / R13.3 / R13.4 / R13.6） ──

/** 联动清单里的一条附注章节。 */
export interface NoteLinkageItem {
  /** 章节号（如 `五、42`），真源 = `note_workpaper_sync_registry.json` */
  note_section: string
  /** 该章节对应的底稿编码（可多个：registry 实测有跨循环共有章节） */
  owners: string[]
  /** 这些底稿所属循环 */
  cycles: string[]
  /** 面向审计师的一句话判据说明 */
  narrative: string
  /** 附注侧章节标题；null = 后端未取到 */
  section_title: string | null
  /** 仅 `conflicts` 项有：该章节当前是否已被标为不适用 */
  currently_marked?: boolean
  /** 仅 `conflicts` / `unlocatable` / `skipped_foreign_mark` 项有 */
  reason?: string
}

export interface NoteLinkageView {
  /** 将被标为「本期不适用」的章节 */
  to_mark: NoteLinkageItem[]
  /** 已处于该状态（幂等，无需再写） */
  already_marked: NoteLinkageItem[]
  /**
   * 命中裁剪但**已有内容** → 只提示，两个方向都不自动动（R13.4）。
   *
   * 🔴 「不自动撤销」也是刻意的：撤销同样是自动动作。有人工内容时由审计师在附注侧决定。
   */
  conflicts: NoteLinkageItem[]
  /** 裁剪已撤销 → 本联动标过的标注将相应撤销（R13.3） */
  to_revoke: NoteLinkageItem[]
  /** 附注侧没有该章节行 → 跳过并记录，不阻断裁剪保存（R13.6） */
  unlocatable: NoteLinkageItem[]
  /** 审计师手工标的不适用（无 provenance 面包屑）→ 本联动无权撤销 */
  skipped_foreign_mark: NoteLinkageItem[]
  /** 取数降级（registry 不可用 / 映射为空 / 单章节写入失败） */
  degradations: { stage: string; reason: string; note_section?: string }[]
  /** 本项目已被整体裁剪的循环 */
  cycles_fully_trimmed: string[]
  summary: {
    to_mark: number
    already_marked: number
    conflicts: number
    to_revoke: number
    unlocatable: number
  }
}

const _emptyNoteLinkage = (): NoteLinkageView => ({
  to_mark: [], already_marked: [], conflicts: [], to_revoke: [],
  unlocatable: [], skipped_foreign_mark: [], degradations: [],
  cycles_fully_trimmed: [],
  summary: { to_mark: 0, already_marked: 0, conflicts: 0, to_revoke: 0, unlocatable: 0 },
})

function _normalizeNoteLinkage(raw: any): NoteLinkageView {
  const arr = (v: any): NoteLinkageItem[] => (Array.isArray(v) ? v : [])
  const base = _emptyNoteLinkage()
  const view: NoteLinkageView = {
    to_mark: arr(raw?.to_mark),
    already_marked: arr(raw?.already_marked),
    conflicts: arr(raw?.conflicts),
    to_revoke: arr(raw?.to_revoke),
    unlocatable: arr(raw?.unlocatable),
    skipped_foreign_mark: arr(raw?.skipped_foreign_mark),
    degradations: Array.isArray(raw?.degradations) ? raw.degradations : [],
    cycles_fully_trimmed: Array.isArray(raw?.cycles_fully_trimmed) ? raw.cycles_fully_trimmed : [],
    summary: { ...base.summary, ...(raw?.summary && typeof raw.summary === 'object' ? raw.summary : {}) },
  }
  return view
}

/**
 * 只读预览：本次程序裁剪会把哪些附注章节标为本期不适用 / 撤销 / 只提示。
 *
 * 🔴 `year` 必传：`procedure_instances` 没有 year 列，而 `disclosure_notes` 按
 * `(project, year, note_section)` 唯一 —— 缺 year 后端定位不到章节行，整份联动会返回空
 * （表现为「这个项目没有可标注的章节」这一实质结论）。
 */
export async function fetchTrimNoteLinkage(
  projectId: string,
  year: number,
): Promise<NoteLinkageView> {
  const { data } = await http.get(P_prt.trimNoteLinkage(projectId), { params: { year } })
  return _normalizeNoteLinkage(data?.data ?? data)
}

/**
 * 应用联动：后端**只写** `disclosure_notes.is_empty` + provenance 面包屑。
 *
 * 幂等：可反复调用，已处于目标态的章节零写入。
 */
export async function applyTrimNoteLinkage(
  projectId: string,
  year: number,
): Promise<NoteLinkageView & { marked: number; revoked: number }> {
  const { data } = await http.post(P_prt.trimNoteLinkageApply(projectId), { year })
  const raw = data?.data ?? data
  return {
    ..._normalizeNoteLinkage(raw),
    marked: Number(raw?.marked ?? 0),
    revoked: Number(raw?.revoked ?? 0),
  }
}

/** 查询 materialize job 状态（delegation preview 前置 job）。 */
export async function getProcedureMaterializeJob(projectId: string, jobId: string): Promise<any> {
  const { data } = await http.get(P_prt.materializeJobStatus(projectId, jobId), { validateStatus: () => true })
  return data?.data ?? data
}

// ── 程序行一级复核（Task 13，ReviewConversation + IssueTicket） ──

export interface ProcedureConversationView {
  task_id: string
  cell_ref: string
  conversation: any | null
  messages: any[]
  open_issue_count: number
  issues: any[]
  access?: string
  readonly?: boolean
}

/** 只读复核视图（对话 + 消息稳定排序 + 未解决 IssueTicket 数 + 问题单列表 + 访问级别）。 */
export async function getProcedureConversation(
  projectId: string, taskId: string,
): Promise<ProcedureConversationView> {
  const { data } = await http.get(P_prt.conversation(projectId, taskId), { validateStatus: () => true })
  return (data?.data ?? data) as ProcedureConversationView
}

/** 追加程序行复核消息（仅当前参与者可写；历史只读参与者 403）。 */
export async function postProcedureMessage(
  projectId: string, taskId: string, content: string,
): Promise<any> {
  const { data } = await http.post(P_prt.messages(projectId, taskId), { content })
  return data?.data ?? data
}

/** 关闭程序行 review_comment IssueTicket（review 前置门槛的解除动作）。 */
export async function closeProcedureIssue(
  projectId: string, taskId: string, issueId: string,
): Promise<any> {
  const { data } = await http.post(P_prt.closeIssue(projectId, taskId, issueId), {})
  return data?.data ?? data
}

/** 聚合端点：一次获取当前用户所有被委派的程序（避免逐循环请求） */
export async function getMyProcedureTasks(staffId: string): Promise<any[]> {
  // 后端暂无聚合端点，先用前端聚合（后续优化为后端聚合）
  const assignments = await getMyAssignments()
  const CYCLES = ['A','B','C','D','E','F','G','H','I','J','K','L','M','N','S','Q']
  const allTasks: any[] = []
  for (const proj of assignments) {
    const pid = proj.project_id
    for (const cycle of CYCLES) {
      try {
        const procs = await getProcedures(pid, cycle)
        const myProcs = procs.filter((p: any) => p.status === 'execute' && p.assigned_to === staffId)
        for (const p of myProcs) {
          allTasks.push({ ...p, project_id: pid, project_name: proj.project_name || proj.client_name })
        }
      } catch { /* 项目可能没有初始化程序 */ }
    }
  }
  return allTasks
}

// ── 看板 ──

export async function getDashboardProjectStaffHours(projectId: string): Promise<any> {
  const { data } = await http.get(P_dash.projectStaffHours, { params: { project_id: projectId } })
  return data
}

export async function getDashboardStaffDetail(staffId: string): Promise<any> {
  const { data } = await http.get(P_dash.staffDetail, { params: { staff_id: staffId } })
  return data
}

export async function getDashboardAvailableStaff(maxHours: number): Promise<any> {
  const { data } = await http.get(P_dash.availableStaff, { params: { max_hours: maxHours } })
  return data
}

// ── 一致性检查 ──

export async function runConsistencyCheck(projectId: string, year = 2025): Promise<any> {
  const { data } = await http.post(P_proj.consistencyCheck.run(projectId), null, { params: { year } })
  return data
}

export async function getConsistencyCheck(projectId: string, year = 2025): Promise<any> {
  const { data } = await http.get(P_proj.consistencyCheck.get(projectId), { params: { year } })
  return data
}

// ── 附注 ──

export interface RefreshFromWorkpapersResult {
  refreshed: number
  total_notes: number
  sections_recomputed: string[]
  text_only_sections: string[]
  errors: string[]
  cells_updated: number
}

export async function refreshDisclosureFromWorkpapers(projectId: string, year: number): Promise<RefreshFromWorkpapersResult> {
  const { data } = await http.post(P_dn.refreshFromWorkpapers(projectId, year))
  return data as RefreshFromWorkpapersResult
}

/** 只重算单个章节（当前页面刷新）— 后端仅动该节，前后端一致 */
export async function refreshDisclosureSection(projectId: string, year: number, section: string): Promise<RefreshFromWorkpapersResult> {
  const { data } = await http.post(P_dn.refreshSectionFromWorkpaper(projectId, year, section))
  return data as RefreshFromWorkpapersResult
}

// ── 附注就绪度看板（附注联动复盘 P0-1，只读）──

export interface NoteReadinessSection {
  note_section: string
  section_title: string
  account_name: string
  has_data: boolean
  is_stale: boolean
  stale_source: string | null
  last_sync_at: string | null
  last_sync_source: string | null
  last_sync_wp_id: string | null
  /** 该章节应由哪些底稿维护（生成自前端 *NoteSectionMap.ts 的注册表） */
  wp_codes: string[]
  /** wp_code → working_paper.id（仅已生成底稿，用于跳转） */
  wp_ids: Record<string, string>
  /** 底稿披露 sheet 真实 tab 名（跳转带 ?sheet=） */
  wp_sheet: string | null
  /** 有底稿映射但从未同步过 */
  needs_sync: boolean
  findings: { error: number; warning: number }
}

export interface NoteReadinessSummary {
  total: number
  with_data: number
  empty: number
  syncable: number
  never_synced: number
  stale: number
  stale_report: number
  stale_report_fallback?: number
  error_sections: number
  warning_sections: number
  validated_at: string | null
  validation_ran: boolean
  formula_enabled: boolean
}

export interface NoteReadinessResult {
  summary: NoteReadinessSummary
  sections: NoteReadinessSection[]
}

export async function getDisclosureReadiness(
  projectId: string,
  year: number,
): Promise<NoteReadinessResult> {
  const { data } = await http.get(P_dn.readiness(projectId, year))
  return (data?.data ?? data) as NoteReadinessResult
}

/**
 * 获取附注章节的 auto_pull 联动取数结果。
 * 原生 http 调用，手动解 {code,message,data} 信封取 body.data（铁律）。
 */
export interface AutoPullRefResult {
  ref_id: string
  target_wp: string | null
  source_label: string
  value: number | string | null
  available: boolean
  reason: string
}

export async function fetchNoteAutoPull(
  projectId: string,
  year: number,
  section: string,
): Promise<AutoPullRefResult[]> {
  const { data: body } = await http.get(P_dn.autoPull(projectId, year, section))
  // 手动解 {code, message, data} 信封
  const envelope = body as any
  const payload = envelope?.data ?? envelope
  return payload?.refs ?? []
}

// ── 附注 LLM 辅助 ──

export async function noteAiGeneratePolicy(projectId: string, params: {
  section_number: string; template_type?: string; industry?: string; year?: number
}): Promise<{ generated_text: string; reference_count: number }> {
  const { data } = await http.post(P_dn.ai.generatePolicy(projectId), params)
  return data
}

export async function noteAiGenerateAnalysis(projectId: string, params: {
  section_number: string; current_data?: Record<string, any>; prior_data?: Record<string, any>; year?: number
}): Promise<{ generated_text: string; reference_count: number }> {
  const { data } = await http.post(P_dn.ai.generateAnalysis(projectId), params)
  return data
}

export async function noteAiRewrite(projectId: string, params: {
  text: string; instruction?: string; section_number?: string; year?: number; knowledge_context?: string
}): Promise<{ original: string; rewritten: string; error?: string }> {
  const { data } = await http.post(P_dn.ai.rewrite(projectId), params)
  return data
}

export async function noteAiContinueWrite(projectId: string, params: {
  text: string; section_number?: string; year?: number; knowledge_context?: string
}): Promise<{ result: string; appended: string; error?: string }> {
  const { data } = await http.post(P_dn.ai.complete(projectId), params)
  return data
}

export async function noteAiCheckCompleteness(projectId: string): Promise<{ suggestions: string[] }> {
  const { data } = await http.post(P_dn.ai.checkCompleteness(projectId))
  return data
}

// ── 期后事项 ──

export async function listSubsequentEvents(projectId: string): Promise<any[]> {
  const { data } = await http.get(P_proj.subsequentEvents(projectId))
  return Array.isArray(data) ? data : []
}

export async function createSubsequentEvent(projectId: string, body: any): Promise<any> {
  const { data } = await http.post(P_proj.subsequentEvents(projectId), body)
  return data
}

// ── 用户管理 ──

export async function listUsers(projectId?: string): Promise<any[]> {
  const { data } = await http.get(P_usr.list, projectId ? { params: { project_id: projectId } } : undefined)
  return Array.isArray(data) ? data : []
}

export async function createUser(body: any): Promise<any> {
  const { data } = await http.post(P_usr.list, body)
  return data
}

export async function updateUser(userId: string, body: any): Promise<any> {
  const { data } = await http.put(P_usr.detail(userId), body)
  return data
}

// ── 系统设置 ──

export async function getSystemSettings(): Promise<any> {
  const { data } = await http.get(P_sys.settings)
  return data
}

export async function updateSystemSetting(key: string, value: any): Promise<any> {
  const { data } = await http.put(P_sys.settings, { updates: { [key]: value } })
  return data
}

export async function getSystemHealth(): Promise<any> {
  const { data } = await http.get(P_sys.health)
  return data
}

// ── 私人库 ──

export async function listPrivateFiles(userId: string): Promise<any[]> {
  const { data } = await http.get(P_usr.privateStorage.list(userId))
  return Array.isArray(data) ? data : data?.files || []
}

export async function getPrivateQuota(userId: string): Promise<any> {
  const { data } = await http.get(P_usr.privateStorage.quota(userId))
  return data
}

export async function uploadPrivateFile(userId: string, formData: FormData): Promise<void> {
  await http.post(P_usr.privateStorage.upload(userId), formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export async function downloadPrivateFile(userId: string, name: string): Promise<Blob> {
  const { data } = await http.get(P_usr.privateStorage.download(userId, name), {
    responseType: 'blob',
  })
  return data
}

export async function deletePrivateFile(userId: string, name: string): Promise<void> {
  await http.delete(P_usr.privateStorage.delete(userId, name))
}

// ── 文件下载工具（解决 window.open 不带 Authorization 头的问题） ──

export async function downloadFileAsBlob(url: string, filename: string): Promise<void> {
  const response = await http.get(url, { responseType: 'blob' })
  const blob = new Blob([response.data])
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}


// ── 回收站 ──

export async function getRecycleBinStats(): Promise<any> {
  const { data } = await http.get(P_rb.stats)
  return data
}

export async function listRecycleBinItems(params?: Record<string, any>): Promise<{ items: any[]; total: number }> {
  const { data } = await http.get(P_rb.list, { params })
  return { items: data?.items || [], total: data?.total || 0 }
}

export async function restoreRecycleBinItem(itemId: string): Promise<any> {
  const { data } = await http.post(P_rb.restore(itemId))
  return data
}

export async function permanentDeleteItem(itemId: string): Promise<any> {
  const { data } = await http.delete(P_rb.delete(itemId))
  return data
}

export async function emptyRecycleBin(): Promise<any> {
  const { data } = await http.post(P_rb.empty)
  return data
}

// ── 知识库 ──

export async function listKnowledgeDocuments(category: string, params?: Record<string, any>): Promise<any[]> {
  const { data } = await http.get(P_kb.category(category), { params })
  return Array.isArray(data) ? data : data?.documents || []
}

export async function uploadKnowledgeDocument(category: string, formData: FormData): Promise<any> {
  const { data } = await http.post(P_kb.upload(category), formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function deleteKnowledgeDocument(category: string, docId: string): Promise<void> {
  await http.delete(P_kb.doc(category, docId))
}

export async function searchKnowledge(query: string): Promise<any[]> {
  const { data } = await http.get(P_kb.search, { params: { q: query } })
  return Array.isArray(data) ? data : data?.results || []
}

export async function listProjectKnowledge(projectId: string): Promise<any[]> {
  const { data } = await http.get(P_proj.knowledge(projectId))
  return Array.isArray(data) ? data : data?.documents || []
}

// ── 性能监控 ──

export async function getPerformanceStats(): Promise<any> {
  const { data } = await http.get(P_admin.performanceStats)
  return data
}

export async function getSlowQueries(): Promise<any[]> {
  const { data } = await http.get(P_admin.slowQueries)
  return data?.queries || []
}

export async function getPerformanceMetrics(hours = 24): Promise<any> {
  const { data } = await http.get(P_admin.performanceMetrics, { params: { hours } })
  return data
}

// ── 注册 ──

export async function registerUser(body: { username: string; email: string; password: string }): Promise<any> {
  const { data } = await http.post(P_auth.register, body)
  return data
}

// ── 附件管理 ──

export async function listAttachments(projectId: string, params?: Record<string, any>): Promise<any[]> {
  const { data } = await http.get(P_att.list(projectId), { params })
  return Array.isArray(data) ? data : data?.items || []
}

export async function searchAttachments(projectId: string, query: string): Promise<any[]> {
  const { data } = await http.get(P_att.search, { params: { project_id: projectId, q: query } })
  return Array.isArray(data) ? data : []
}

export async function uploadAttachment(
  projectId: string,
  formData: FormData,
  onProgress?: (percent: number) => void,
): Promise<any> {
  const { data } = await http.post(P_att.upload(projectId), formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress
      ? (e: any) => {
          const percent = e.total ? Math.round((e.loaded / e.total) * 100) : 0
          onProgress(percent)
        }
      : undefined,
  })
  return data
}

// ── 审计程序裁剪 ──

export async function initProcedures(projectId: string, cycle: string): Promise<any[]> {
  const { data } = await http.post(P_proc.init(projectId, cycle))
  return data?.procedures || (Array.isArray(data) ? data : [])
}

export async function addCustomProcedure(projectId: string, cycle: string, body: any): Promise<any> {
  const { data } = await http.post(P_proc.custom(projectId, cycle), body)
  return data
}

export async function applyProcedureScheme(projectId: string, cycle: string, sourceProjectId: string): Promise<any> {
  const { data } = await http.post(P_proc.applyScheme(projectId, cycle), null, {
    params: { source_project_id: sourceProjectId },
  })
  return data
}

/** 设置底稿主编（Workpaper Lead API，替代旧 procedures/assign）。
 *
 * 调用新端点 PUT /api/projects/{pid}/workpaper-leads（procedure-mainline-convergence 需求 5）。
 * 兼容旧签名以便 ProcedureTrimming.vue onAssigneeChange 零改动消费。
 */
export async function assignProcedures(
  projectId: string,
  assignments: { procedure_id: string; staff_id: string | null; request_id?: string }[],
): Promise<{ updated: number }> {
  const { data } = await http.put(P_leads.set(projectId), { assignments })
  return data?.data ?? data
}

// ── 知识库（全局+项目级） ──

export async function listKnowledgeLibraries(): Promise<any[]> {
  const { data } = await http.get(P_kb.libraries)
  return Array.isArray(data) ? data : []
}

export async function listKnowledgeDocs(apiBase: string): Promise<any[]> {
  const { data } = await http.get(apiBase)
  return Array.isArray(data) ? data : data?.items || data?.documents || []
}

export async function uploadKnowledgeDoc(apiBase: string, formData: FormData): Promise<any> {
  const { data } = await http.post(apiBase, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function downloadKnowledgeDoc(apiBase: string, name: string): Promise<Blob> {
  const { data } = await http.get(`${apiBase}/${encodeURIComponent(name)}/download`, {
    responseType: 'blob',
  })
  return data
}

export async function deleteKnowledgeDoc(apiBase: string, name: string): Promise<void> {
  await http.delete(`${apiBase}/${encodeURIComponent(name)}`)
}

// ── 项目看板 ──

export async function getWorkpaperProgress(projectId: string): Promise<any> {
  const { data } = await http.get(P_wp.progress(projectId))
  return data
}

export async function getOverdueWorkpapers(projectId: string, days = 7): Promise<any[]> {
  const { data } = await http.get(P_wp.overdue(projectId), { params: { days } })
  return Array.isArray(data) ? data : []
}

export async function getProjectWorkHours(projectId: string): Promise<any[]> {
  const { data } = await http.get(P_proj.workHours(projectId))
  return Array.isArray(data) ? data : []
}


// ── T型账户 ──

export async function listTAccounts(projectId: string): Promise<any[]> {
  const { data } = await http.get(P_ta.list(projectId))
  return Array.isArray(data) ? data : []
}

export async function getTAccount(projectId: string, id: string): Promise<any> {
  const { data } = await http.get(P_ta.detail(projectId, id))
  return data
}

export async function createTAccount(projectId: string, body: any): Promise<any> {
  const { data } = await http.post(P_ta.list(projectId), body)
  return data
}

export async function addTAccountEntry(projectId: string, accountId: string, entry: any): Promise<any> {
  const { data } = await http.post(P_ta.entries(projectId, accountId), entry)
  return data
}

export async function calculateTAccount(projectId: string, accountId: string): Promise<any> {
  const { data } = await http.post(P_ta.calculate(projectId, accountId))
  return data
}

// ── 自定义模板 ──

export async function listCustomTemplates(params?: Record<string, any>): Promise<any[]> {
  const { data } = await http.get(P_ct.list, { params })
  return Array.isArray(data) ? data : []
}

export async function getCustomTemplate(id: string): Promise<any> {
  const { data } = await http.get(P_ct.detail(id))
  return data
}

export async function createCustomTemplate(fd: FormData): Promise<any> {
  const { data } = await http.post(P_ct.list, fd)
  return data
}

export async function updateCustomTemplate(id: string, fd: FormData): Promise<any> {
  const { data } = await http.put(P_ct.detail(id), fd)
  return data
}

export async function validateCustomTemplate(id: string): Promise<any> {
  const { data } = await http.post(P_ct.validate(id))
  return data
}

export async function publishCustomTemplate(id: string): Promise<void> {
  await http.post(P_ct.publish(id))
}

export async function copyCustomTemplate(id: string): Promise<void> {
  await http.post(P_ct.copy(id))
}

export async function deleteCustomTemplate(id: string): Promise<void> {
  await http.delete(P_ct.detail(id))
}

// ── 监管备案 ──

export async function listFilings(params?: Record<string, any>): Promise<any[]> {
  const { data } = await http.get(P_reg.filings, { params })
  return Array.isArray(data) ? data : []
}

export async function retryFiling(id: string): Promise<void> {
  await http.post(P_reg.retry(id))
}

// ── AI插件 ──

export async function listAIPlugins(): Promise<any[]> {
  const { data } = await http.get(P_aip.list)
  return Array.isArray(data) ? data : []
}

// ── GT编码 ──

export async function listGTCoding(): Promise<any[]> {
  const { data } = await http.get(P_gtc.list)
  return Array.isArray(data) ? data : []
}

// ── 复核对话 ──

export async function listReviewConversations(projectId: string): Promise<any[]> {
  const { data } = await http.get(P_rc.projectList(projectId))
  return Array.isArray(data) ? data : []
}

// ── 穿透查询（移动端） ──

export async function getLedgerBalance(projectId: string, year: number): Promise<any[]> {
  const { data } = await http.get(P_ledger.balance(projectId), { params: { year } })
  return Array.isArray(data) ? data : []
}

export async function getLedgerEntries(projectId: string, code: string, year: number, page = 1, pageSize = 50): Promise<any> {
  const { data } = await http.get(
    P_ledger.entries(projectId, code),
    { params: { year, page, page_size: pageSize } },
  )
  return data
}

// ── 科目余额树形（Layer 2 / Sprint 8） ──
// 主表 + 辅助余额嵌套，el-table :tree-props 直接渲染
// v2（2026-05-10）：支持三层嵌套（父科目 → 维度组节点 → 具体明细），
// mismatch 按单一 aux_type 校验

export interface LedgerBalanceAuxChild {
  aux_type: string
  aux_code: string | null
  aux_name: string | null
  aux_dimensions_raw: string | null
  opening_balance: number | null
  opening_debit: number | null
  opening_credit: number | null
  debit_amount: number | null
  credit_amount: number | null
  closing_balance: number | null
  closing_debit: number | null
  closing_credit: number | null
  currency_code: string | null
}

/** 维度组节点：代表某个 aux_type 在该科目下的聚合 */
export interface LedgerBalanceDimensionGroup {
  _is_dimension_group: true
  aux_type: string
  account_code: string
  account_name: string | null
  opening_balance: number
  debit_amount: number
  credit_amount: number
  closing_balance: number
  record_count: number
  has_children: boolean
  children: LedgerBalanceAuxChild[]
}

export interface LedgerBalanceTreeNode {
  account_code: string
  account_name: string | null
  level: number | null
  company_code: string
  opening_balance: number | null
  opening_debit: number | null
  opening_credit: number | null
  debit_amount: number | null
  credit_amount: number | null
  closing_balance: number | null
  closing_debit: number | null
  closing_credit: number | null
  currency_code: string | null
  aggregated_from_aux: boolean
  aux_row_count: number
  aux_types: string[]
  aux_rows_total: number
  has_children: boolean
  children: LedgerBalanceDimensionGroup[]
}

export interface LedgerBalanceTreeMismatch {
  company_code: string
  account_code: string
  aux_type: string
  parent_closing: number
  dim_sum: number
  record_count: number
  diff: number
}

export interface LedgerBalanceTreeResponse {
  year: number
  company_code: string | null
  tree: LedgerBalanceTreeNode[]
  pagination: {
    page: number
    page_size: number
    total: number
    total_pages: number
  }
  summary: {
    account_count: number
    aggregated_count: number
    with_children_count: number
    aux_total_rows: number
    mismatches: LedgerBalanceTreeMismatch[]
  }
}

export interface LedgerBalanceTreeParams {
  year: number
  companyCode?: string
  page?: number
  pageSize?: number
  keyword?: string
  onlyWithChildren?: boolean
  onlyWithActivity?: boolean
}

export async function getLedgerBalanceTree(
  projectId: string,
  params: number | LedgerBalanceTreeParams,
  companyCode?: string,
): Promise<LedgerBalanceTreeResponse> {
  // 兼容旧调用 getLedgerBalanceTree(pid, year, companyCode)
  const p: LedgerBalanceTreeParams =
    typeof params === 'number' ? { year: params, companyCode } : params

  const query: Record<string, any> = { year: p.year }
  if (p.companyCode) query.company_code = p.companyCode
  if (p.page !== undefined) query.page = p.page
  if (p.pageSize !== undefined) query.page_size = Math.min(p.pageSize, 200)
  if (p.keyword) query.keyword = p.keyword
  if (p.onlyWithChildren) query.only_with_children = true
  if (p.onlyWithActivity) query.only_with_activity = true

  const { data } = await http.get(P_ledger.balanceTree(projectId), { params: query })
  return data as LedgerBalanceTreeResponse
}

// ── 集团架构（合并页面） ──

export async function listChildProjects(parentProjectId: string): Promise<any[]> {
  const { data } = await http.get(P_proj.list, { params: { parent_project_id: parentProjectId } })
  return Array.isArray(data) ? data : data?.items || []
}


// ── 管理看板 ──

export async function getDashboardOverview(): Promise<any> {
  const { data } = await http.get(P_dash.overview)
  return data && typeof data === 'object' ? data : {}
}

export async function getDashboardProjectProgress(): Promise<any[]> {
  const { data } = await http.get(P_dash.projectProgress)
  return Array.isArray(data) ? data : []
}

export async function getDashboardStaffWorkload(): Promise<any[]> {
  const { data } = await http.get(P_dash.staffWorkload)
  return Array.isArray(data) ? data : []
}

export async function getDashboardRiskAlerts(): Promise<any[]> {
  const { data } = await http.get(P_dash.riskAlerts)
  return Array.isArray(data) ? data : []
}

export async function getDashboardGroupProgress(): Promise<any[]> {
  const { data } = await http.get(P_dash.groupProgress)
  return Array.isArray(data) ? data : []
}

export async function getDashboardHoursHeatmap(): Promise<any[]> {
  const { data } = await http.get(P_dash.hoursHeatmap)
  return Array.isArray(data) ? data : []
}


// ── 批注 ──

export async function listWorkpaperAnnotations(projectId: string, objectType: string, objectId: string): Promise<any[]> {
  const { data } = await http.get(P_ann.list(projectId), {
    params: { object_type: objectType, object_id: objectId },
  })
  return Array.isArray(data) ? data : []
}

export async function createAnnotation(projectId: string, body: any): Promise<any> {
  const { data } = await http.post(P_ann.list(projectId), body)
  return data
}

export async function updateAnnotation(id: string, body: any): Promise<any> {
  const { data } = await http.put(P_ann.update(id), body)
  return data
}

export async function listAnnotations(projectId: string, filters?: { status?: string; priority?: string }): Promise<any[]> {
  const { data } = await http.get(P_ann.list(projectId), { params: filters })
  return Array.isArray(data) ? data : (data || [])
}

// ── 功能开关 ──

export async function checkFeatureFlag(flag: string, projectId?: string): Promise<boolean> {
  const { data } = await http.get(P_sys.featureFlags.check(flag), {
    params: projectId ? { project_id: projectId } : undefined,
    validateStatus: () => true,
  })
  return !!data?.enabled
}

export async function getFeatureMaturity(): Promise<Record<string, string>> {
  const { data } = await http.get(P_sys.featureFlags.maturity)
  return data && typeof data === 'object' ? data : {}
}

// ── 底稿提交复核 ──

export async function submitWorkpaperReview(projectId: string, wpId: string): Promise<any> {
  const { data } = await http.post(P_wp.submitReview(projectId, wpId))
  return data
}


// ══════════════════════════════════════════════════════════
// 以下从 enhancedApi.ts 迁移（Phase 7 增强功能）
// ══════════════════════════════════════════════════════════

// ── 过程记录 ──

export async function getEditHistory(projectId: string, wpId: string): Promise<any[]> {
  const { data } = await http.get(P_pr.editHistory(projectId, wpId))
  return Array.isArray(data) ? data : []
}

export async function getWpAttachments(projectId: string, wpId: string): Promise<any[]> {
  const { data } = await http.get(P_pr.attachments(projectId, wpId))
  return Array.isArray(data) ? data : []
}

export async function getAttachmentWorkpapers(attachmentId: string): Promise<any[]> {
  const { data } = await http.get(P_pr.attachmentWorkpapers(attachmentId))
  return Array.isArray(data) ? data : []
}

export async function linkAttachment(attachmentId: string, wpId: string): Promise<void> {
  await http.post(P_pr.linkAttachment, { attachment_id: attachmentId, wp_id: wpId })
}

export async function getPendingAIContent(projectId: string, workpaperId?: string): Promise<any[]> {
  const params: Record<string, string> = {}
  if (workpaperId) params.workpaper_id = workpaperId
  const { data } = await http.get(P_pr.pendingAIContent(projectId), { params })
  return Array.isArray(data) ? data : []
}

export async function confirmAIContent(contentId: string, status: string): Promise<void> {
  await http.put(P_pr.confirmAIContent(contentId), { status })
}

export async function checkUnconfirmedAI(projectId: string, wpId: string): Promise<any> {
  const { data } = await http.get(P_pr.aiCheck(projectId, wpId))
  return data
}

// ── LLM 底稿对话 ──

export function wpChatSSE(wpId: string, message: string, context?: Record<string, any>) {
  return http.post(P_wpai.chat(wpId), { message, context }, { responseType: 'stream' })
}

export async function generateLedgerAnalysis(projectId: string, body: { account_codes?: string[]; year?: number }): Promise<any> {
  const { data } = await http.post(P_wpai.generateLedgerAnalysis(projectId), body)
  return data
}

// ── 抽样增强 ──

export interface AgingBracket { label: string; min_days: number; max_days: number | null }

export async function cutoffTest(projectId: string, body: {
  account_codes: string[]; year: number; days_before?: number; days_after?: number; amount_threshold?: number
}): Promise<any> {
  const { data } = await http.post(P_samp.cutoffTest(projectId), body)
  return data
}

export async function agingAnalysis(projectId: string, body: {
  account_code: string; aging_brackets: AgingBracket[]; base_date: string; year?: number
}): Promise<any> {
  const { data } = await http.post(P_samp.agingAnalysis(projectId), body)
  return data
}

export async function monthlyDetail(projectId: string, body: { account_code: string; year: number }): Promise<any> {
  const { data } = await http.post(P_samp.monthlyDetail(projectId), body)
  return data
}

// ── 复核对话 ──

export interface ConversationItem {
  id: string; project_id: string; initiator_id: string; target_id: string
  related_object_type: string; status: string; title: string
  message_count?: number; created_at?: string; closed_at?: string
}

export async function createConversation(projectId: string, body: {
  target_id: string; related_object_type: string; related_object_id?: string; cell_ref?: string; title: string
}): Promise<any> {
  const { data } = await http.post(`${P_rc.list}?project_id=${projectId}`, body)
  return data
}

export async function listConversations(projectId: string, status?: string): Promise<any[]> {
  const params: Record<string, string> = { project_id: projectId }
  if (status) params.status = status
  const { data } = await http.get(P_rc.list, { params })
  return Array.isArray(data) ? data : []
}

export async function getMessages(conversationId: string): Promise<any[]> {
  const { data } = await http.get(P_rc.messages(conversationId))
  return Array.isArray(data) ? data : []
}

export async function sendMessage(conversationId: string, body: {
  content: string; message_type?: string; attachment_path?: string
}): Promise<any> {
  const { data } = await http.post(P_rc.messages(conversationId), body)
  return data
}

export async function closeConversation(conversationId: string): Promise<void> {
  await http.put(P_rc.close(conversationId))
}

export async function exportConversation(conversationId: string): Promise<any> {
  const { data } = await http.post(P_rc.export(conversationId))
  return data
}

// ── 论坛 ──

export interface ForumPostItem {
  id: string; author_id?: string; is_anonymous: boolean; category: string
  title: string; content: string; like_count: number; comment_count?: number; created_at?: string
}

export async function listPosts(category?: string): Promise<any[]> {
  const params: Record<string, string> = {}
  if (category) params.category = category
  const { data } = await http.get(P_forum.posts, { params })
  return Array.isArray(data) ? data : data?.items || data?.posts || []
}

export async function createPost(body: { title: string; content: string; category?: string; is_anonymous?: boolean }): Promise<any> {
  const { data } = await http.post(P_forum.posts, body)
  return data
}

export async function getComments(postId: string): Promise<any[]> {
  const { data } = await http.get(P_forum.comments(postId))
  return Array.isArray(data) ? data : data?.items || data?.comments || []
}

export async function createComment(postId: string, content: string): Promise<void> {
  await http.post(P_forum.comments(postId), { content })
}

export async function likePost(postId: string): Promise<void> {
  await http.post(P_forum.like(postId))
}

// ── 溯源 ──

export async function traceSection(projectId: string, sectionNumber: string): Promise<any> {
  const { data } = await http.get(P_rr.trace(projectId, sectionNumber))
  return data
}

export async function findingsSummary(projectId: string): Promise<any> {
  const { data } = await http.get(P_proj.findingsSummary(projectId))
  return data
}

// ── 打卡 ──

export async function checkIn(staffId: string, body: {
  latitude?: number; longitude?: number; location_name?: string; check_type?: string
}): Promise<void> {
  await http.post(P_staff.checkIn(staffId), body)
}

export async function listCheckIns(staffId: string): Promise<any[]> {
  const { data } = await http.get(P_staff.checkIns(staffId))
  return Array.isArray(data) ? data : []
}

// ── 辅助余额汇总 ──

export async function auxSummary(projectId: string, year?: number): Promise<any[]> {
  const params: Record<string, any> = {}
  if (year) params.year = year
  const { data } = await http.get(P_ledger.auxSummary(projectId), { params })
  return Array.isArray(data) ? data : []
}

// ── 合并锁定 ──

export async function lockProject(projectId: string): Promise<void> {
  await http.post(P_consol.lock(projectId))
}

export async function unlockProject(projectId: string): Promise<void> {
  await http.post(P_consol.unlock(projectId))
}

export async function checkLockStatus(projectId: string): Promise<any> {
  const { data } = await http.get(P_consol.lockStatus(projectId))
  return data
}

// ── 快照 ──

export async function listSnapshots(projectId: string): Promise<any[]> {
  const { data } = await http.get(P_consol.snapshots(projectId))
  return Array.isArray(data) ? data : []
}

export async function createSnapshot(projectId: string, year: number = 2025): Promise<void> {
  await http.post(`${P_consol.snapshots(projectId)}?year=${year}`)
}

// ── 推荐 ──

export async function recommendWorkpapers(projectId: string): Promise<any> {
  const { data } = await http.post(P_wpai.recommendWorkpapers(projectId))
  return data
}

// ── 差异报告 ──

export async function annualDiffReport(projectId: string): Promise<any> {
  const { data } = await http.post(P_wpai.annualDiffReport(projectId))
  return data
}

// ── 附件分类 ──

export async function classifyAttachment(projectId: string, attachmentId: string, fileName: string): Promise<any> {
  const { data } = await http.post(P_att.classify(projectId), {
    attachment_id: attachmentId, file_name: fileName,
  })
  return data
}

// ── 排版模板 ──

export async function listFormatTemplates(): Promise<any[]> {
  const { data } = await http.get(P_rft.list)
  return Array.isArray(data) ? data : []
}

export async function createFormatTemplate(body: {
  template_name: string; template_type: string; config: Record<string, any>
}): Promise<any> {
  const { data } = await http.post(P_rft.create, body)
  return data
}

// ── 模板库三层体系 ──

export interface TemplateLibraryItem {
  id: string
  name: string
  type: string
  level: string
  level_label?: string
  wp_code?: string
  audit_cycle?: string
  report_scope?: string
  description?: string
  group_name?: string
  version?: string
  source_template_id?: string
}

export interface ProjectTemplateSelection {
  selection_id: string
  template_id: string
  template_name: string
  template_type: string
  level: string
  group_name?: string
  wp_code?: string
  report_scope?: string
  pulled_at?: string
  linked_trial_balance: boolean
  linked_adjustments: boolean
  linked_attachments: boolean
}

export async function getAvailableTemplates(params?: {
  template_type?: string
  group_id?: string
}): Promise<TemplateLibraryItem[]> {
  const { data } = await http.get(P_tl.available, { params })
  return Array.isArray(data) ? data : []
}

export async function listFirmTemplates(templateType?: string): Promise<TemplateLibraryItem[]> {
  const { data } = await http.get(P_tl.firm, {
    params: templateType ? { template_type: templateType } : undefined,
  })
  return Array.isArray(data) ? data : []
}

export async function createGroupTemplate(body: {
  source_template_id: string
  group_id: string
  group_name: string
}): Promise<{ id: string; name: string; message: string }> {
  const { data } = await http.post(P_tl.group.create, body)
  return data
}

export async function listGroupTemplates(groupId: string, templateType?: string): Promise<TemplateLibraryItem[]> {
  const { data } = await http.get(P_tl.group.list(groupId), {
    params: templateType ? { template_type: templateType } : undefined,
  })
  return Array.isArray(data) ? data : []
}

export async function selectTemplateForProject(projectId: string, templateId: string): Promise<{ selection_id: string }> {
  const { data } = await http.post(P_tl.project.select(projectId), { template_id: templateId })
  return data
}

export async function getProjectTemplates(projectId: string): Promise<ProjectTemplateSelection[]> {
  const { data } = await http.get(P_tl.project.templates(projectId))
  return Array.isArray(data) ? data : []
}

export async function pullTemplateToProject(projectId: string, templateId: string): Promise<{ template_name: string; target_path: string }> {
  const { data } = await http.post(P_tl.project.pull(projectId, templateId))
  return data
}

export async function createCustomWorkpaper(projectId: string, body: {
  wp_code: string
  wp_name: string
  audit_cycle?: string
  year?: number
}): Promise<{ wp_id: string; wp_code: string; message: string }> {
  const { data } = await http.post(P_wp.createCustom(projectId), body)
  return data
}

// ── Excel↔HTML 互转 ──

export async function uploadExcelForParse(projectId: string, file: File): Promise<any> {
  const fd = new FormData()
  fd.append('file', file)
  const { data } = await http.post(P_eh.uploadParse(projectId), fd)
  return data
}

export async function getExcelHtmlPreview(projectId: string, fileStem: string, sheetIndex = 0): Promise<{ html: string; version: number }> {
  const { data } = await http.get(P_eh.preview(projectId, fileStem), { params: { sheet_index: sheetIndex, editable: true } })
  return data
}

export async function saveExcelHtmlEdits(projectId: string, fileStem: string, edits: any[], sheetIndex = 0): Promise<any> {
  const { data } = await http.post(P_eh.saveEdits(projectId, fileStem), { edits, sheet_index: sheetIndex })
  return data
}

export async function confirmExcelAsTemplate(projectId: string, fileStem: string, body: {
  template_name: string; template_type?: string; wp_code?: string; audit_cycle?: string
}): Promise<any> {
  const { data } = await http.post(P_eh.confirmTemplate(projectId, fileStem), body)
  return data
}

/** @deprecated 已迁移至 Univer，保留向后兼容 */
export async function syncFromOnlyoffice(projectId: string, fileStem: string): Promise<any> {
  const { data } = await http.post(P_eh.syncFromOnlyoffice(projectId, fileStem))
  return data
}

// ── 三形式联动统一模块接口 ──

export async function getModuleStructure(projectId: string, module: string, params?: Record<string, any>): Promise<any> {
  const { data } = await http.get(P_eh.module.structure(projectId, module), { params })
  return data
}

export async function getModuleHtml(projectId: string, module: string, params?: Record<string, any>): Promise<{ module: string; html: string }> {
  const { data } = await http.get(P_eh.module.html(projectId, module), { params })
  return data
}

export async function exportModuleExcel(projectId: string, module: string, params?: Record<string, any>): Promise<Blob> {
  const response = await http.post(P_eh.module.exportExcel(projectId, module), null, {
    params,
    responseType: 'blob',
  })
  return response.data
}

export async function exportModuleWord(projectId: string, module: string, params?: Record<string, any>): Promise<Blob> {
  const response = await http.post(P_eh.module.exportWord(projectId, module), null, {
    params,
    responseType: 'blob',
  })
  return response.data
}

// ── 四式联动：编辑锁 ──

export async function acquireEditLock(projectId: string, fileStem: string): Promise<{ locked: boolean }> {
  const { data } = await http.post(P_eh.lock.acquire(projectId, fileStem))
  return data
}

export async function releaseEditLock(projectId: string, fileStem: string): Promise<void> {
  await http.delete(P_eh.lock.release(projectId, fileStem))
}

export async function refreshEditLock(projectId: string, fileStem: string): Promise<void> {
  await http.put(P_eh.lock.refresh(projectId, fileStem))
}

// ── 四式联动：版本管理 ──

export async function listFileVersions(projectId: string, fileStem: string): Promise<any[]> {
  const { data } = await http.get(P_eh.versions.list(projectId, fileStem))
  return Array.isArray(data) ? data : []
}

export async function diffFileVersions(projectId: string, fileStem: string, v1: number, v2: number): Promise<any> {
  const { data } = await http.get(P_eh.versions.diff(projectId, fileStem), { params: { v1, v2 } })
  return data
}

export async function rollbackFileVersion(projectId: string, fileStem: string, version: number): Promise<any> {
  const { data } = await http.post(P_eh.versions.rollback(projectId, fileStem, version))
  return data
}

// ── 四式联动：公式执行 ──

export async function executeFormulas(projectId: string, fileStem: string, params?: { sheet_index?: number; year?: number }): Promise<{
  executed: number; total_formulas: number; errors: any[]; version: number
}> {
  const { data } = await http.post(P_eh.executeFormulas(projectId, fileStem), null, { params })
  return data
}

// ── 四式联动：单元格信息 ──

export async function getCellInfo(projectId: string, fileStem: string, cell: string): Promise<any> {
  const { data } = await http.get(P_eh.cellInfo(projectId, fileStem), { params: { cell } })
  return data
}

// ── 导入智能增强 ──

export async function enhanceColumnMapping(projectId: string, headers: string[], existingMapping: Record<string, string>): Promise<{
  enhanced: Record<string, string>
  suggestions: Array<{ header: string; suggested_field: string; confidence: number }>
  unmatched: string[]
}> {
  const { data } = await http.post(P_ii.enhanceMapping(projectId), { headers, existing_mapping: existingMapping })
  return data
}

export async function getImportQualityCheck(projectId: string, year = 2025): Promise<{
  score: number; grade: string; findings: any[]; summary: string
}> {
  const { data } = await http.get(P_ii.qualityCheck(projectId), { params: { year } })
  return data
}

export async function prepareIncrementalImport(projectId: string, mode: string, period?: string, year = 2025): Promise<any> {
  const { data } = await http.post(P_ii.prepareIncremental(projectId), { mode, period }, { params: { year } })
  return data
}

export async function getImportOverview(projectId: string, year = 2025): Promise<any> {
  const { data } = await http.get(P_ii.overview(projectId), { params: { year } })
  return data
}

// ── 底稿看板+批量操作+穿透链接 ──

export async function getWorkpapersKanban(projectId: string, auditCycle?: string): Promise<any> {
  const { data } = await http.get(P_wp.kanban(projectId), { params: auditCycle ? { audit_cycle: auditCycle } : undefined })
  return data
}

export async function batchAssignWorkpapers(projectId: string, wpIds: string[], assignedTo?: string, reviewer?: string): Promise<any> {
  const { data } = await http.post(P_wp.batchAssign(projectId), { wp_ids: wpIds, assigned_to: assignedTo, reviewer })
  return data
}

export async function batchSubmitReview(projectId: string, wpIds: string[]): Promise<any> {
  const { data } = await http.post(P_wp.batchSubmit(projectId), { wp_ids: wpIds })
  return data
}

export async function batchExportWorkpapers(projectId: string, wpIds: string[]): Promise<Blob> {
  const response = await http.post(P_wp.batchExport(projectId), { wp_ids: wpIds }, { responseType: 'blob' })
  return response.data
}

export async function getWorkpaperEditTime(projectId: string, wpId: string): Promise<any> {
  const { data } = await http.get(P_wp.editTime(projectId, wpId))
  return data
}

export async function getWorkpaperCrossLinks(projectId: string, wpId: string): Promise<any> {
  const { data } = await http.get(P_wp.crossLinks(projectId, wpId))
  return data
}

export async function syncWorkpaperProcedure(projectId: string, wpId: string): Promise<any> {
  const { data } = await http.post(P_wp.syncProcedure(projectId, wpId))
  return data
}

// ── 工时与底稿编辑时间关联 ──

export async function getEditTimeSuggestions(staffId: string, targetDate: string): Promise<{
  suggestions: Array<{ wp_id: string; wp_name: string; duration_minutes: number; start_time: string; end_time: string }>
  total_hours: number
  message: string
}> {
  const { data } = await http.get(P_wh.editTimeSuggest, { params: { staff_id: staffId, target_date: targetDate } })
  return data
}

// ── 统一地址坐标注册表 ──

export interface AddressEntry {
  uri: string
  domain: string       // report / note / wp / tb / aux
  source: string
  path: string
  cell: string
  label: string
  formula_ref: string
  jump_route: string
  row_code: string
  account_code: string
  note_section: string
  wp_code: string
  tags: string[]
}

export async function searchAddresses(projectId: string, params?: {
  year?: number; keyword?: string; domain?: string; template_type?: string; limit?: number
}): Promise<{ total: number; items: AddressEntry[] }> {
  const { data } = await http.get(P_ar.search, {
    params: { project_id: projectId, ...params },
  })
  return data
}

export async function getAddressStats(projectId: string, year?: number, templateType?: string): Promise<{
  total: number; by_domain: Record<string, number>; domains: string[]
}> {
  const { data } = await http.get(P_ar.stats, {
    params: { project_id: projectId, year, template_type: templateType },
  })
  return data
}

export async function resolveAddress(uri: string, projectId: string, year?: number): Promise<{
  found: boolean; uri: string; label?: string; formula_ref?: string; jump_route?: string
}> {
  const { data } = await http.get(P_ar.resolve, {
    params: { uri, project_id: projectId, year },
  })
  return data
}

export async function validateFormulaRefs(formula: string, projectId: string, year?: number, templateType?: string): Promise<{
  valid: boolean; issues: Array<{ ref: string; uri: string; status: string; message: string }>
}> {
  const { data } = await http.post(P_ar.validate, {
    formula, project_id: projectId, year, template_type: templateType,
  })
  return data
}

export async function getJumpRoute(params: {
  uri?: string; formula_ref?: string; project_id: string; year?: number
}): Promise<{ route: string; uri: string; formula_ref: string }> {
  const { data } = await http.post(P_ar.jump, params)
  return data
}

export async function invalidateAddressCache(projectId: string, params?: {
  year?: number; domain?: string; template_type?: string; all?: boolean
}): Promise<void> {
  await http.post(P_ar.invalidate, {
    project_id: projectId, ...params,
  })
}

// ── 底稿三式联动 ──

export async function getWorkpaperStructure(projectId: string, wpId: string, forceRebuild = false): Promise<{
  wp_id: string; wp_code: string; structure: any; row_count: number; has_formulas: boolean
}> {
  const { data } = await http.get(P_wp.structure.get(projectId, wpId), {
    params: forceRebuild ? { force_rebuild: true } : undefined,
  })
  return data
}

export async function saveWorkpaperStructure(projectId: string, wpId: string, structure: any, syncExcel = true): Promise<{
  wp_id: string; version: number; excel_synced: boolean
}> {
  const { data } = await http.post(P_wp.structure.get(projectId, wpId), {
    structure, sync_excel: syncExcel,
  })
  return data
}

export async function rebuildWorkpaperStructure(projectId: string, wpId: string): Promise<any> {
  const { data } = await http.post(P_wp.structure.rebuild(projectId, wpId))
  return data
}

export async function getWorkpaperStructureHtml(projectId: string, wpId: string, page = 1, pageSize = 200): Promise<{
  html: string; total_rows: number; page: number; is_large: boolean
}> {
  const { data } = await http.get(P_wp.structure.html(projectId, wpId), {
    params: { page, page_size: pageSize },
  })
  return data
}

export async function batchGenerateStructures(projectId: string): Promise<{
  total: number; generated: number; skipped: number; errors: any[]
}> {
  const { data } = await http.post(P_wp.batchStructure(projectId))
  return data
}

export async function getWorkpaperAddresses(projectId: string, wpId: string): Promise<{
  wp_code: string; addresses: any[]; count: number
}> {
  const { data } = await http.get(P_wp.structure.addresses(projectId, wpId))
  return data
}

// ── 底稿操作手册 ──

export async function listWpManuals(): Promise<{ cycles: Record<string, any[]>; total: number }> {
  const { data } = await http.get(P_wpm.list)
  return data
}

export async function getWpManualStats(): Promise<any> {
  const { data } = await http.get(P_wpm.stats)
  return data
}

export async function getCycleManuals(cycle: string): Promise<{ cycle: string; files: any[]; count: number }> {
  const { data } = await http.get(P_wpm.cycle(cycle))
  return data
}

export async function getCycleManualContent(cycle: string): Promise<{ content: string }> {
  const { data } = await http.get(P_wpm.manual(cycle))
  return data
}

export async function getCycleLlmContext(cycle: string, wpCode?: string): Promise<{ context: string; char_count: number }> {
  const { data } = await http.get(P_wpm.context(cycle), {
    params: wpCode ? { wp_code: wpCode } : undefined,
  })
  return data
}

// ── 底稿精细化规则 ──

export async function listWpFineRules(): Promise<{ rules: Array<{ wp_code: string; name: string; sheets: number; checks: number }> }> {
  const { data } = await http.get(P_wfr.list)
  return data
}

export async function getWpFineRule(wpCode: string): Promise<any> {
  const { data } = await http.get(P_wfr.detail(wpCode))
  return data
}

export async function fineExtractWorkpaper(projectId: string, wpId: string): Promise<any> {
  const { data } = await http.post(P_wfr.fineExtract(projectId, wpId))
  return data
}

// ── 底稿依赖关系（B→C→D联动） ──

export async function getWpDependencies(projectId: string, wpId: string): Promise<{
  wp_code: string; cycle: string; dependencies: any[]; all_satisfied: boolean;
  warnings: string[]; control_effectiveness: string | null; impact: any
}> {
  const { data } = await http.get(P_wp.dependencies(projectId, wpId))
  return data
}

export async function getCycleDependencyGraph(cycle: string): Promise<{
  cycle: string; nodes: any[]; edges: any[]
}> {
  const { data } = await http.get(P_wdep.cycleGraph(cycle))
  return data
}

export async function listCycleDependencies(): Promise<Record<string, any>> {
  const { data } = await http.get(P_wdep.cycles)
  return data
}

// ── 账龄分析 ──

export async function getAgingPresets(): Promise<any> {
  const { data } = await http.get(P_aging.presets)
  return data
}

export async function getProjectAgingConfig(projectId: string): Promise<{
  preset: string; custom_segments: any[]; custom_rates: Record<string, number>; effective_segments: any[]
}> {
  const { data } = await http.get(P_aging.config(projectId))
  return data
}

export async function saveProjectAgingConfig(projectId: string, config: {
  preset: string; custom_segments?: any[]; custom_rates?: Record<string, number>
}): Promise<any> {
  const { data } = await http.put(P_aging.config(projectId), config)
  return data
}

export async function calculateAgingProvision(projectId: string, params: {
  year?: number; account_code?: string; preset?: string; custom_segments?: any[]; custom_rates?: Record<string, number>
}): Promise<{
  preset: string; segments: Array<{ key: string; label: string; balance: number; rate: number; provision: number }>;
  total_balance: number; total_provision: number; provision_rate: number
}> {
  const { data } = await http.post(P_aging.calculate(projectId), params)
  return data
}
