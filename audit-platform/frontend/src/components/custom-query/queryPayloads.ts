/**
 * queryPayloads.ts — 高级查询两类请求体的唯一构造处（acnr-foundation-defect-closure T16，design §2.6 / R2-F10）
 *
 * - `buildBuilderPayload`：构建器 `/api/query/{preview,execute,export-excel}`（后端 `QueryDSL`）。
 * - `buildBusinessPayload`：业务视图 `/api/custom-query/execute`（后端 `QueryRequest`），全部前端调用点都经它构造。
 *
 * 单元格取值目标 `acnr_targets` 的规则（需求 1.6）：只有在有项目上下文时才发送；没有项目时不发，界面在地址选择区
 * 提示先进入（选择）项目。构建器的 `project_id` / `year` 只随单元格取值目标一起发送（不带目标的常规查询保持原来的
 * 跨项目范围不变）；`year` 只在项目审计年度已知时发送，未知时由后端按项目补齐、仍未知返回 `YEAR_REQUIRED`，前端不用
 * 日历年兜底。两个函数都是纯函数；`queryErrorText` 把后端的拒绝形状转成中文提示，`notifyQueryError` 负责弹出。
 *
 * advanced-query-linkage-closure 任务 30 在构建器请求体上加了三个可选参数（不另造第二个构造函数）：`scopeToProject`
 * 为真时不带目标也发 `project_id` / `year`（从项目页打开的构建器默认限定当前项目与审计年度，R3.5；「跨项目」时为假，
 * 规则同上一段）；`offset` 翻页；`headers` 是「导出全部」的中文表头（R8.1）。不传这三个参数时输出与原先逐键相同。
 */
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { formatRefIssues } from '@/utils/formulaRefIssues'

/** 构建器没有项目上下文时，地址选择区的提示 */
export const BUILDER_NO_PROJECT_HINT = '请先进入项目再选择单元格'
/** 业务视图没有选项目时，地址选择区的提示 */
export const BUSINESS_NO_PROJECT_HINT = '请先选择项目再选择单元格'

export interface BuilderFilterRow { field: string; op: string; value: string | null }
export interface BuilderDslState {
  table: string
  fields: string[]
  filters: BuilderFilterRow[]
  filter_logic: 'and' | 'or'
  order_by: { field: string; direction: 'asc' | 'desc' }[]
  joins: { table: string; type: 'inner' | 'left' }[]
  aggregates: { func: string; field: string; alias: string }[]
  group_by: string[]
  limit: number
}

/** 项目上下文：构建器取路由项目与项目审计年度；业务视图取页面所选项目与年度 */
export interface QueryProjectContext {
  projectId?: string | null
  year?: number | null
}

/** 审计年度是否可用（与后端 `ge=2000, le=2100` 同口径） */
export function isKnownYear(year: unknown): year is number {
  return typeof year === 'number' && Number.isInteger(year) && year >= 2000 && year <= 2100
}

function tryNumber(v: string): any {
  if (v === '' || v === null || v === undefined) return v
  const n = Number(v)
  return Number.isFinite(n) && /^-?\d+(\.\d+)?$/.test(v) ? n : v
}

/** 把构建器过滤行的字符串值转成后端期望的类型 / 数组。 */
function builderFilterValue(op: string, raw: string | null): unknown {
  if (op === 'is_null' || op === 'is_not_null') return null
  if (op === 'in' || op === 'not_in') return String(raw || '').split(',').map((s) => s.trim()).filter(Boolean)
  if (op === 'between') {
    const [lo, hi] = String(raw || '').split(',').map((s) => s.trim())
    return [tryNumber(lo), tryNumber(hi)]
  }
  if (['gt', 'gte', 'lt', 'lte', 'eq', 'neq'].includes(op)) return tryNumber(String(raw ?? ''))
  return raw
}

/** 构建器请求的项目上下文与翻页 / 导出参数（advanced-query-linkage-closure 任务 30） */
export interface BuilderPayloadContext extends QueryProjectContext {
  /** 限定当前项目（与审计年度）查询：从项目页打开构建器的默认范围（R3.5）；「跨项目」时为 false */
  scopeToProject?: boolean
  /** 翻页起始行（后端 `QueryDSL.offset`）；0 或缺省不发 */
  offset?: number
  /** 服务端签发的精确 COUNT 凭证；同一查询翻页时复用。 */
  countToken?: string | null
  /** 「导出全部」的中文表头（后端 `ExportDSL.headers`，键为结果列名）；只在导出请求里传 */
  headers?: Record<string, string>
}

/** 构建器请求体（后端 `QueryDSL` / 导出时 `ExportDSL`）。 */
export function buildBuilderPayload(
  dsl: BuilderDslState, acnrTargets: readonly string[], ctx: BuilderPayloadContext,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    table: dsl.table,
    fields: dsl.fields,
    filters: dsl.filters.filter((f) => f.field && f.op)
      .map((f) => ({ field: f.field, op: f.op, value: builderFilterValue(f.op, f.value) })),
    filter_logic: dsl.filter_logic,
    order_by: dsl.order_by.filter((o) => o.field),
    joins: dsl.joins.filter((j) => j.table).map((j) => ({ table: j.table, type: j.type })),
    aggregates: dsl.aggregates.filter((a) => a.func && a.field)
      .map((a) => ({ func: a.func, field: a.field, alias: a.alias || `${a.func}_${a.field}` })),
    group_by: dsl.group_by,
    limit: dsl.limit,
  }
  const withTargets = !!ctx.projectId && acnrTargets.length > 0
  if (ctx.projectId && (ctx.scopeToProject || withTargets)) {
    payload.project_id = ctx.projectId
    if (isKnownYear(ctx.year)) payload.year = ctx.year
  }
  if (withTargets) payload.acnr_targets = [...acnrTargets]
  if (typeof ctx.offset === 'number' && Number.isInteger(ctx.offset) && ctx.offset > 0) payload.offset = ctx.offset
  if (ctx.countToken) payload.count_token = ctx.countToken
  if (ctx.headers && Object.keys(ctx.headers).length) payload.headers = { ...ctx.headers }
  return payload
}

/** 业务视图请求体（后端 `QueryRequest`）的入参：`project_id` / `year` / `source` 之外按需传。 */
export interface BusinessQueryInput extends QueryProjectContext {
  source: string
  filters?: Record<string, unknown>
  columns?: string[]
  /** 结构化条件与组合逻辑（后端 `QueryRequest.conditions` / `condition_logic`；advanced-query-linkage-closure 任务 29，R6.1） */
  conditions?: { field: string; op: string; value: unknown }[]
  condition_logic?: 'and' | 'or'
  /** 排序项（后端 `QueryRequest.sort`：数据库内对全量排序、空值在后；R2.2） */
  sort?: QuerySort[]
  limit?: number
  offset?: number
  /** 服务端签发的精确 COUNT 凭证；翻页时发送，查询变化时省略。 */
  countToken?: string | null
}

/** 业务视图的一个排序项（后端 `SortSpec`） */
export interface QuerySort {
  field: string
  direction: 'asc' | 'desc'
}

/** 业务视图请求体（后端 `QueryRequest`）。`project_id` 恒发送（模板浏览模式为空串，与原行为一致）。 */
export function buildBusinessPayload(
  input: BusinessQueryInput, acnrTargets: readonly string[] = [],
): Record<string, unknown> {
  const { projectId, year, source, countToken, ...rest } = input
  const payload: Record<string, unknown> = { project_id: projectId || '', source, filters: {} }
  if (isKnownYear(year)) payload.year = year
  if (countToken) payload.count_token = countToken
  for (const [key, value] of Object.entries(rest)) {
    if (value !== undefined) payload[key] = value
  }
  if (projectId && acnrTargets.length) payload.acnr_targets = [...acnrTargets]
  return payload
}

/**
 * 后端拒绝 → 中文提示（design §2.6）；不是这几类返回 null（调用方交给 `handleApiError`）。
 * 422 的 detail 有两种形状：业务拒绝 `{error_code, message, issues?}`；请求模型校验是数组 `[{type, msg, loc}]`，
 * 只认本 spec 的中文消息类型（未声明字段、单元格引用）。
 */
export function queryErrorText(e: unknown): string | null {
  const resp = (e as { response?: { status?: number; data?: { detail?: unknown } } })?.response
  const status = resp?.status
  const detail = resp?.data?.detail
  if (status === 403) return '无权访问该项目'
  if (status === 503) return '地址解析服务暂不可用，请稍后重试'
  if (status !== 422) return null
  if (Array.isArray(detail)) {
    const msgs = detail
      .filter((d) => /^(unknown_field|acnr_target|template_acnr)/.test(String(d?.type || '')))
      .map((d) => String(d?.msg || '').trim()).filter(Boolean)
    return msgs.length ? [...new Set(msgs)].join('；') : null
  }
  if (detail && typeof detail === 'object') {
    const d = detail as Record<string, unknown>
    const head = typeof d.message === 'string' ? d.message.trim() : ''
    const list = formatRefIssues(d.issues)
    return head && list ? `${head}：${list}` : head || list || null
  }
  return null
}

/** 查询失败、又识别不出拒绝原因时，结果区持久显示的中文兜底（不显示 axios 的英文 message） */
export const QUERY_FAILED_FALLBACK = '查询失败，请稍后重试'

/** 结果区持久显示的失败原因：能识别的拒绝显示逐项中文原因，其余用中文兜底。 */
export function queryFailureText(e: unknown): string {
  return queryErrorText(e) || QUERY_FAILED_FALLBACK
}

/**
 * blob 请求（构建器导出）失败时错误体是 Blob：读成 JSON 写回 `response.data`（与 utils/http 信封补齐同口径：
 * 缺 detail 时用 message），使 `queryErrorText` / `handleApiError` 按 JSON 识别；读不出 JSON 时原样返回。
 */
export async function readBlobErrorBody<T>(e: T): Promise<T> {
  const resp = (e as { response?: { data?: unknown } } | null)?.response
  if (!resp || !(resp.data instanceof Blob)) return e
  const blob = resp.data
  try {
    const text = typeof blob.text === 'function' ? await blob.text() : await new Promise<string>((ok, fail) => {
      const reader = new FileReader()
      reader.onload = () => ok(String(reader.result ?? ''))
      reader.onerror = () => fail(reader.error)
      reader.readAsText(blob)
    })
    const parsed = JSON.parse(text)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      && parsed.detail === undefined && parsed.message !== undefined) parsed.detail = parsed.message
    resp.data = parsed
  } catch { /* 不是 JSON：保持原样交给 handleApiError */ }
  return e
}

/** 查询失败的统一提示：能识别的拒绝显示中文原因，其余交给 `handleApiError`。 */
export function notifyQueryError(e: unknown, context: string): void {
  const text = queryErrorText(e)
  if (text) ElMessage.warning(`${context}：${text}`)
  else handleApiError(e, context)
}
