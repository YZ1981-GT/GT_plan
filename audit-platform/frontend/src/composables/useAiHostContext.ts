/**
 * useAiHostContext — AI 面板宿主上下文 adapter（唯一真源）
 *
 * Feature: dsh-agent-panel-integration / Task 2
 * Requirements:
 *   - 3.1：宿主类型受后端枚举约束（取值与 `backend/app/services/ai_chat/contracts.py`
 *     的 `HostType` 逐字对齐，由 `useAiHostContext.spec.ts` 对账）。
 *   - 3.2：每个宿主提交自己的**稳定标识** —— 底稿是 working paper instance ID，
 *     附注是 instance ID 或稳定 section key，报表是 report type，知识库是 folder/doc ID。
 *   - 3.3：不存在的字段用 `null`，**绝不用空字符串伪装有效 ID**。
 *   - 3.4：页面解析不出项目上下文时 `projectToolsEnabled=false` 并给出中文原因，
 *     不发空 `project_id`、不猜测最近项目。
 *   - 3.5：`ReportView` / `DisclosureEditor` / `KnowledgeBase` / `WorkpaperEditor` /
 *     全局 `DshPanel` / 独立聊天窗口都通过本模块构造**同一形状**的 HostContext 请求，
 *     **不得把 project ID 当作 document ID**。
 *
 * 修正前的真实缺陷（本模块就是为消除它们而存在）：
 *   - `ReportView` 传 `:doc-id="projectId"` —— 项目 ID 当文档 ID；
 *   - `KnowledgeBase` 传 `:project-id="''"` —— 空串伪装项目 ID，并用 `new Date()` 猜年度；
 *   - `DisclosureEditor` 在 instance ID 与 section key 之间随机二选一，服务端无法判形态；
 *   - `WorkpaperEditor` 用 `new Date().getFullYear() - 1` 兜底年度 —— 会构造出与服务端
 *     反查值冲突的 year 断言，Task 2 起服务端按 `host_context_mismatch` 拒绝。
 *
 * 服务端只把 `projectId` / `year` 当**一致性断言**：本模块宁可传 `null`，也不猜。
 */

// ---------------------------------------------------------------------------
// 后端枚举镜像（单一真源在后端；此处只做取值镜像并由测试对账）
// ---------------------------------------------------------------------------

/** 宿主类型取值域（镜像后端 `HostType`）。 */
export const AI_HOST_TYPES = [
  'workpaper',
  'note',
  'report',
  'knowledge_doc',
  'knowledge_folder',
  'global_knowledge',
] as const

export type AiHostType = (typeof AI_HOST_TYPES)[number]

/** 受限全局知识模式的显式 sentinel（镜像后端 `GLOBAL_KNOWLEDGE_HOST_ID`）。 */
export const GLOBAL_KNOWLEDGE_HOST_ID = 'global-knowledge'

/** 报表宿主的稳定 ID 取值域（镜像后端 `REPORT_HOST_IDS` / `FinancialReportType`）。 */
export const AI_REPORT_HOST_IDS = [
  'balance_sheet',
  'income_statement',
  'cash_flow_statement',
  'equity_statement',
  'cash_flow_supplement',
  'impairment_provision',
] as const

export type AiReportHostId = (typeof AI_REPORT_HOST_IDS)[number]

/** 宿主类型 → 中文标签（全中文 UI，NFR-5）。 */
export const AI_HOST_LABELS: Record<AiHostType, string> = {
  workpaper: '底稿',
  note: '附注',
  report: '报表',
  knowledge_doc: '知识文档',
  knowledge_folder: '知识库文件夹',
  global_knowledge: '全局知识库',
}

// ---------------------------------------------------------------------------
// 契约类型
// ---------------------------------------------------------------------------

/** 提交给服务端的最小宿主标识（服务端据此反查权威上下文）。 */
export interface AiHostRef {
  type: AiHostType
  /** 稳定资源标识；`null` = 当前页面尚未选定资源（不发空串）。 */
  id: string | null
  /** 项目断言；`null` = 本宿主无项目绑定（全局知识模式）或页面未解析出项目。 */
  projectId: string | null
  /** 年度断言；`null` = 不猜测（服务端自行反查）。 */
  year: number | null
}

/** 宿主 adapter 的统一产物：六个宿主形状完全一致。 */
export interface AiHostRequest {
  /** 可用时为完整 HostRef；不可用时为 `null`（面板据此禁用发送）。 */
  host: AiHostRef | null
  /** 宿主是否可用于 AI 对话。 */
  available: boolean
  /** 不可用原因（中文，直接展示给用户）；可用时为 `null`。 */
  unavailableReason: string | null
  /** 项目工具是否可用（Req 3.4：无项目绑定时必须关闭）。 */
  projectToolsEnabled: boolean
  /** 宿主中文标签（面板上下文条展示）。 */
  label: string
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** 是否是形态合法的 UUID（空串 / undefined / 'null' 一律 false）。 */
export function isUuid(value: unknown): boolean {
  return typeof value === 'string' && UUID_RE.test(value.trim())
}

function normalizeId(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

function normalizeYear(value: unknown): number | null {
  const n = typeof value === 'string' ? Number(value) : value
  if (typeof n !== 'number' || !Number.isInteger(n) || n < 1900 || n > 2999) return null
  return n
}

function unavailable(type: AiHostType, reason: string): AiHostRequest {
  return {
    host: null,
    available: false,
    unavailableReason: reason,
    projectToolsEnabled: false,
    label: AI_HOST_LABELS[type],
  }
}

function available(host: AiHostRef): AiHostRequest {
  return {
    host,
    available: true,
    unavailableReason: null,
    projectToolsEnabled: host.projectId !== null,
    label: AI_HOST_LABELS[host.type],
  }
}

// ---------------------------------------------------------------------------
// 六个宿主 adapter
// ---------------------------------------------------------------------------

/**
 * 底稿宿主：稳定标识 = working paper instance ID。
 *
 * `year` 传项目 `audit_year`；取不到就传 `null` —— **不用 `当前年份-1` 兜底**，
 * 否则会构造出与服务端反查值冲突的断言并被判 `host_context_mismatch`。
 */
export function buildWorkpaperHost(input: {
  wpId: unknown
  projectId: unknown
  auditYear?: unknown
}): AiHostRequest {
  const projectId = normalizeId(input.projectId)
  if (!isUuid(projectId)) {
    return unavailable('workpaper', '当前页面未解析到项目，项目工具不可用')
  }
  const wpId = normalizeId(input.wpId)
  if (!isUuid(wpId)) {
    return unavailable('workpaper', '尚未选定底稿，请先打开一份底稿')
  }
  return available({
    type: 'workpaper',
    id: wpId,
    projectId,
    year: normalizeYear(input.auditYear),
  })
}

/**
 * 附注宿主：稳定标识优先取 instance ID，其次取稳定 section key（`section_id`/`note_section`）。
 *
 * 服务端按"是否 UUID"区分两种形态；section key 形态必须带 project 断言才能唯一定位，
 * 因此无项目上下文时直接不可用。
 */
export function buildNoteHost(input: {
  noteId?: unknown
  sectionId?: unknown
  noteSection?: unknown
  projectId: unknown
  year?: unknown
}): AiHostRequest {
  const projectId = normalizeId(input.projectId)
  if (!isUuid(projectId)) {
    return unavailable('note', '当前页面未解析到项目，项目工具不可用')
  }
  const instanceId = normalizeId(input.noteId)
  const stableKey = normalizeId(input.sectionId) ?? normalizeId(input.noteSection)
  const id = isUuid(instanceId) ? instanceId : stableKey
  if (!id) {
    return unavailable('note', '尚未选定附注章节，请先在左侧目录选择章节')
  }
  return available({
    type: 'note',
    id,
    projectId,
    year: normalizeYear(input.year),
  })
}

/**
 * 报表宿主：稳定标识 = report type（`balance_sheet` 等）。
 *
 * **绝不用 projectId 当 doc ID**（旧 `ReportView` 的真实缺陷）。跨表核对 / 多年度对比 /
 * 报表分析这些 tab 不是单张报表，无法解析成报表宿主 → 显式不可用 + 中文原因。
 */
export function buildReportHost(input: {
  reportType: unknown
  projectId: unknown
  year?: unknown
}): AiHostRequest {
  const projectId = normalizeId(input.projectId)
  if (!isUuid(projectId)) {
    return unavailable('report', '当前页面未解析到项目，项目工具不可用')
  }
  const reportType = normalizeId(input.reportType)
  if (!reportType || !(AI_REPORT_HOST_IDS as readonly string[]).includes(reportType)) {
    return unavailable(
      'report',
      '当前标签页不是单张报表（跨表核对 / 多年度对比 / 报表分析），请切换到具体报表后再使用 AI 对话',
    )
  }
  return available({
    type: 'report',
    id: reportType,
    projectId,
    year: normalizeYear(input.year),
  })
}

/** 知识文档宿主：稳定标识 = document ID；知识资源可跨项目共享，项目断言可为 null。 */
export function buildKnowledgeDocHost(input: {
  docId: unknown
  projectId?: unknown
}): AiHostRequest {
  const docId = normalizeId(input.docId)
  if (!isUuid(docId)) {
    return unavailable('knowledge_doc', '尚未选定知识文档，请先选择一个文档')
  }
  const projectId = normalizeId(input.projectId)
  return available({
    type: 'knowledge_doc',
    id: docId,
    projectId: isUuid(projectId) ? projectId : null,
    year: null,
  })
}

/** 知识文件夹宿主：稳定标识 = folder ID；无项目页面 projectId 传 `null` 而不是 `''`。 */
export function buildKnowledgeFolderHost(input: {
  folderId: unknown
  projectId?: unknown
}): AiHostRequest {
  const folderId = normalizeId(input.folderId)
  if (!isUuid(folderId)) {
    return unavailable('knowledge_folder', '尚未选定知识库文件夹，请先在左侧选择文件夹')
  }
  const projectId = normalizeId(input.projectId)
  return available({
    type: 'knowledge_folder',
    id: folderId,
    projectId: isUuid(projectId) ? projectId : null,
    year: null,
  })
}

/**
 * 受限全局知识模式：显式 sentinel + 无项目绑定 → 项目工具关闭。
 *
 * 全局面板与独立聊天窗口在没有项目上下文时用它，而不是发空 `project_id`。
 */
export function buildGlobalKnowledgeHost(): AiHostRequest {
  return {
    host: {
      type: 'global_knowledge',
      id: GLOBAL_KNOWLEDGE_HOST_ID,
      projectId: null,
      year: null,
    },
    available: true,
    unavailableReason: null,
    // 全局模式没有项目绑定：项目工具必须关闭（Req 3.4）
    projectToolsEnabled: false,
    label: AI_HOST_LABELS.global_knowledge,
  }
}

/**
 * 全局面板 / 独立窗口的宿主选择：有项目上下文时按当前页面宿主，否则退回显式全局模式。
 *
 * 注意"退回全局模式"不是伪装成功：`projectToolsEnabled` 为 false，
 * `hostScopeHint()` 会给出中文说明，面板据此禁用项目类入口。
 */
export function buildAmbientHost(input: {
  projectId?: unknown
  wpId?: unknown
  auditYear?: unknown
}): AiHostRequest {
  const projectId = normalizeId(input.projectId)
  if (!isUuid(projectId)) return buildGlobalKnowledgeHost()
  const wpId = normalizeId(input.wpId)
  if (isUuid(wpId)) {
    return buildWorkpaperHost({
      wpId,
      projectId,
      auditYear: input.auditYear,
    })
  }
  // 有项目但没有具体文档宿主：仍用显式全局模式（不伪造一个项目级文档宿主）。
  return buildGlobalKnowledgeHost()
}

/** 面板上下文条的中文范围说明（可用/不可用共用一条渲染路径）。 */
export function hostScopeHint(request: AiHostRequest): string {
  if (!request.available) return request.unavailableReason ?? '当前页面无法使用 AI 对话'
  if (!request.projectToolsEnabled) {
    // 🔴 别写成「仅检索你有权访问的公共知识」——服务端在无项目绑定时是**不检索**的：
    // ContextBuilder._get_global_knowledge_content() 直接返回空串，
    // _search_related_knowledge() 在 project_id 为 None 时跳过 semantic_search。
    // 承诺"会检索"会让审计师把「上下文空」当成故障来排查。
    return '全局知识模式：未绑定项目，不自动检索项目数据与知识库，项目工具不可用'
  }
  return `当前范围：${request.label}`
}

// ---------------------------------------------------------------------------
// 请求载荷（服务端只把这些字段当断言）
// ---------------------------------------------------------------------------

/** 宿主的 REST 路径片段：`/api/ai-chat/doc/{docType}/{docId}`。 */
export function hostPathSegments(host: AiHostRef): { docType: string; docId: string } {
  return { docType: host.type, docId: host.id ?? '' }
}

/** 历史 / 清除请求的 project 查询串（无项目绑定时**不发**该参数）。 */
export function hostQueryString(host: AiHostRef): string {
  return host.projectId ? `?project_id=${encodeURIComponent(host.projectId)}` : ''
}
