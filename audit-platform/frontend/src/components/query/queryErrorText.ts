/**
 * queryErrorText.ts — 高级查询请求失败 → 中文原因 + 追踪号（advanced-query-linkage-closure 任务 27，design §4.1；R11.1、R11.2，AQ-29）
 *
 * 构建器（任务 30）、弹窗与页面版（任务 28 / 29）都经 `describeQueryError` 把失败显示给用户，不显示 axios 的英文
 * （「Request failed with status code …」）与 pydantic 的英文明细。读取顺序：
 * 1. 响应体 detail（拦截器 `normaliseErrorEnvelope` 已把信封的 message 补成 detail；未经拦截器的错误对象也认对象形态的 message）：
 *    - 数组 = 请求模型校验（422）：acnr-foundation-defect-closure 的自定义中文类型（unknown_field / acnr_target / template_acnr）原样，
 *      其余按 pydantic `type` 译成「字段中文名 + 规则」；
 *    - 对象 = 业务拒绝 `{error_code, message, issues?}`：message；带引用问题清单时「message：引用：原因；…」（与 acnr 同口径）；
 *    - 字符串：原样（starlette / FastAPI 的英文缺省文案译成中文）。
 * 2. 取不到时按状态码给中文兜底；没有响应（断网 / 超时）给网络提示。
 * 追踪号：detail.correlation_id → 响应头 X-Correlation-ID → 响应头 X-Request-ID（每个响应都有，`middleware/request_id`）。
 *
 * blob 请求（导出）的错误体是 Blob：调用方先 `await readBlobErrorBody(e)`（custom-query/queryPayloads）再交给本函数。
 */
import { formatRefIssues } from '@/utils/formulaRefIssues'
import { resolveColumnLabel } from './queryColumnLabels'

export interface QueryErrorText {
  /** 显示给用户的中文原因 */
  message: string
  /** 可复制给支持人员的追踪号（取不到时缺省） */
  correlationId?: string
  /** HTTP 状态码；没有响应（断网 / 超时 / 取消）时为 0 */
  status: number
  /** 后端错误码（业务拒绝才有，如 TABLE_ROLE_FORBIDDEN / EXPORT_BUSY） */
  errorCode?: string
}

/** 请求体字段 → 中文（构建器 QueryDSL / ExportDSL、业务视图 QueryRequest 的字段与条件子字段） */
export const REQUEST_FIELD_LABELS: Readonly<Record<string, string>> = {
  project_id: '项目', year: '审计年度', source: '数据源', filters: '筛选', conditions: '条件',
  condition_logic: '条件逻辑', columns: '显示列', sort: '排序', group: '分组', pivot: '透视',
  limit: '每页行数', offset: '起始行', table: '数据表', fields: '返回字段', filter_logic: '条件逻辑',
  order_by: '排序', joins: '关联表', aggregates: '聚合', group_by: '分组字段', headers: '表头',
  file_name: '文件名', acnr_targets: '单元格取值目标', field: '字段', op: '操作符', value: '值',
  direction: '排序方向', func: '聚合函数', alias: '别名',
}

export const NETWORK_ERROR_TEXT = '网络连接失败，请检查网络后重试'
const CANCELED_TEXT = '请求已取消'
const SERVER_ERROR_TEXT = '服务器内部错误，请稍后重试'
const FALLBACK_TEXT = '请求失败，请稍后重试'
const STATUS_TEXT: Readonly<Record<number, string>> = {
  400: '请求参数有误', 401: '登录已失效，请重新登录', 403: '无权执行此操作', 404: '请求的数据不存在',
  408: '查询超时，请缩小查询范围后重试', 409: '数据已变化，请刷新后重试', 413: '请求内容过大',
  422: '参数校验失败', 429: '请求过于频繁，请稍后再试', 502: '服务暂时不可用，请稍后重试',
  503: '服务暂时不可用，请稍后重试', 504: '服务响应超时，请稍后重试',
}
/** starlette / FastAPI 的英文缺省文案 → 中文 */
const BUILTIN_TEXT: Readonly<Record<string, string>> = {
  'Not Found': '请求的数据不存在', 'Method Not Allowed': '不支持的请求方式', 'Not authenticated': '登录已失效，请重新登录',
  Forbidden: '无权执行此操作', 'Internal Server Error': SERVER_ERROR_TEXT, 'Unprocessable Entity': '参数校验失败',
}
/** 已是中文、原样显示的请求模型校验类型（acnr-foundation-defect-closure 的自定义类型，msg 为中文） */
const NATIVE_CHINESE_TYPE = /^(unknown_field|acnr_target|template_acnr)/

type Dict = Record<string, unknown>

function text(v: unknown): string {
  return typeof v === 'string' ? v.trim() : ''
}

function headerOf(resp: { headers?: unknown } | undefined, name: string): string {
  const h = resp?.headers as { get?: (n: string) => unknown } & Dict | undefined
  if (!h) return ''
  const v = typeof h.get === 'function' ? h.get(name) : (h[name] ?? h[name.toLowerCase()])
  return v === undefined || v === null ? '' : String(v).trim()
}

/** pydantic loc → 字段中文名（跳过 body / query 等位置段；数组下标译成「第 n 项」） */
function fieldLabel(loc: unknown): string {
  const labels: string[] = []
  for (const part of Array.isArray(loc) ? loc : []) {
    if (part === 'body' || part === 'query' || part === 'path' || part === 'header') continue
    if (typeof part === 'number') labels.push(`第 ${part + 1} 项`)
    else labels.push(REQUEST_FIELD_LABELS[String(part)] ?? resolveColumnLabel(String(part)))
  }
  return labels.join(' · ') || '请求参数'
}

/** pydantic 错误类型 → 中文规则（ctx 里的界限值原样带出） */
function ruleText(item: Dict): string {
  const ctx = (item.ctx && typeof item.ctx === 'object' ? item.ctx : {}) as Dict
  switch (String(item.type ?? '')) {
    case 'greater_than_equal': return `不能小于 ${ctx.ge}`
    case 'less_than_equal': return `不能大于 ${ctx.le}`
    case 'greater_than': return `必须大于 ${ctx.gt}`
    case 'less_than': return `必须小于 ${ctx.lt}`
    case 'missing': return '为必填项'
    case 'literal_error': {
      const expected = text(ctx.expected).replace(/ or /g, '、')
      return expected ? `取值无效，可选：${expected}` : '取值无效'
    }
    case 'string_too_long': return `长度不能超过 ${ctx.max_length} 个字符`
    case 'string_too_short': return `长度不能少于 ${ctx.min_length} 个字符`
    case 'too_long': return `最多 ${ctx.max_length} 项`
    case 'too_short': return `至少 ${ctx.min_length} 项`
    case 'int_parsing': case 'int_type': case 'int_from_float': return '必须是整数'
    case 'float_parsing': case 'float_type': case 'decimal_parsing': return '必须是数字'
    case 'uuid_parsing': case 'uuid_type': return '不是有效的标识'
    case 'bool_parsing': case 'bool_type': return '必须是「是」或「否」'
    case 'extra_forbidden': return '不是可识别的字段'
    default: return '取值无效'
  }
}

/** 422 请求模型校验数组 → 中文 */
function describeValidationItems(items: unknown[]): string {
  const native: string[] = []
  const translated: string[] = []
  for (const raw of items) {
    if (!raw || typeof raw !== 'object') continue
    const item = raw as Dict
    if (NATIVE_CHINESE_TYPE.test(String(item.type ?? '')) && text(item.msg)) native.push(text(item.msg))
    else translated.push(`${fieldLabel(item.loc)}${ruleText(item)}`)
  }
  const parts = [...new Set(native)]
  if (translated.length) parts.push(`参数校验失败：${[...new Set(translated)].join('；')}`)
  return parts.join('；')
}

/** 业务拒绝对象 → 中文：message（带引用问题清单时「message：清单」） */
function describeDetailObject(detail: Dict): string {
  const head = text(detail.message) || text(detail.msg)
  const list = formatRefIssues(detail.issues)
  const shown = BUILTIN_TEXT[head] ?? head
  return shown && list ? `${shown}：${list}` : shown || list
}

/** 请求失败 → 中文原因 + 追踪号（单一实现） */
export function describeQueryError(err: unknown): QueryErrorText {
  const e = (err ?? {}) as { name?: string; code?: string; response?: { status?: number; data?: unknown; headers?: unknown } }
  if (e.name === 'CanceledError' || e.code === 'ERR_CANCELED') return { message: CANCELED_TEXT, status: 0 }
  const resp = e.response
  if (!resp) return { message: NETWORK_ERROR_TEXT, status: 0 }
  const status = Number(resp.status) || 0
  const data = (resp.data && typeof resp.data === 'object' && !(resp.data instanceof Blob) ? resp.data : {}) as Dict
  const detail = data.detail !== undefined ? data.detail : (typeof data.message === 'object' ? data.message : undefined)
  const detailObj = detail && typeof detail === 'object' && !Array.isArray(detail) ? (detail as Dict) : null

  let message = ''
  if (Array.isArray(detail)) message = describeValidationItems(detail)
  else if (detailObj) message = describeDetailObject(detailObj)
  else if (text(detail)) message = BUILTIN_TEXT[text(detail)] ?? text(detail)
  if (!message && text(data.message)) message = BUILTIN_TEXT[text(data.message)] ?? text(data.message)
  if (!message) message = STATUS_TEXT[status] ?? (status >= 500 ? SERVER_ERROR_TEXT : FALLBACK_TEXT)

  const correlationId = text(detailObj?.correlation_id) || text(data.correlation_id)
    || headerOf(resp, 'x-correlation-id') || headerOf(resp, 'x-request-id')
  const out: QueryErrorText = { message, status }
  if (correlationId) out.correlationId = correlationId
  const errorCode = text(detailObj?.error_code)
  if (errorCode) out.errorCode = errorCode
  return out
}

/**
 * 一次性提示（ElMessage）里的文案：「{操作}：{原因}」；服务器错误（5xx）附追踪号。
 * 参数类错误（4xx）用户自己能改，不附追踪号以免喧宾夺主；结果区的持久提示另给「复制追踪号」。
 */
export function queryErrorToast(context: string, described: QueryErrorText): string {
  const tail = described.status >= 500 && described.correlationId ? `（追踪号 ${described.correlationId}）` : ''
  return `${context}：${described.message}${tail}`
}
