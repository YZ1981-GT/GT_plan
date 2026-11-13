/**
 * Node 执行器里的 `@/utils/http`（构建时按别名替换，见同目录 vite.config.ts；spec note-disclosure-pull-regression-and-headless-backend
 * 任务 11 / 13，design §5.2 / §5.4）。
 *
 * 只实现离屏 provider 闭包实际用到的面（get / post / put / patch / delete、`getLastTraceId`、`isRequestCancelled`），
 * 返回形态与浏览器端拦截器一致：成功 = `{ data: 解包后的业务数据, status, headers }`；失败抛出带
 * `response: { status, data: { detail } }` 的错误（`headlessErrorMessage` 读 `detail`）。
 *
 * 安全：
 * - 只连 `configureNodeHttp` 给的环回地址（127.0.0.1 / ::1 / localhost），只发相对路径请求，带一枚服务端发的短期令牌；
 * - 写请求（非 GET）先过 `allowWrite`（必填，fail-closed）：不在名单里的写请求不发出、直接报错；
 * - 写请求带 `X-Client-Instance`（与浏览器窗口编号同一个头，后端编辑锁按它认窗口）。
 * `intercept`：干跑时拦下写请求、记下请求体，不发出（D2 / E1 逐字节对拍用）。
 */
/** `intercept` 返回它 = 这条照常发出 */
export const PASS = Symbol('nodeHttp.pass')

/** 发给后端的 User-Agent：操作日志 / 观测里认得出是离屏执行器 */
export const HEADLESS_USER_AGENT = 'gt-headless-disclosure/1'

export interface InterceptedRequest {
  method: string
  url: string
  body: unknown
  params?: Record<string, unknown>
}

export interface NodeHttpConfig {
  baseUrl: string
  token: string
  clientInstance: string
  /** 写请求名单（必填）：回 false 的写请求不发出、抛错。GET 不过名单（只读，且照常受令牌主人的权限约束）。 */
  allowWrite: (req: InterceptedRequest) => boolean
  /** 写请求（非 GET）过名单后再过这里：回 `PASS` 照常发出，回别的值 = 不发、以它作响应业务数据（干跑记下请求体）。 */
  intercept?: (req: InterceptedRequest) => unknown
}

let current: NodeHttpConfig | null = null
let lastTraceId = ''

const LOOPBACK = /^http:\/\/(?:127\.0\.0\.1|\[::1\]|localhost)(?::\d+)?$/

export function configureNodeHttp(config: NodeHttpConfig): void {
  const base = config.baseUrl.replace(/\/+$/, '')
  if (!LOOPBACK.test(base)) throw new Error(`离屏执行器只连本机环回地址，拒绝 ${config.baseUrl}`)
  if (!config.token) throw new Error('离屏执行器缺少服务端令牌')
  if (typeof config.allowWrite !== 'function') throw new Error('离屏执行器缺少写请求名单（allowWrite）')
  current = { ...config, baseUrl: base }
}

interface RequestConfig {
  params?: Record<string, unknown>
  headers?: Record<string, string>
  [key: string]: unknown
}

export class NodeHttpError extends Error {
  response?: { status: number; data: any }
  constructor(message: string, response?: { status: number; data: any }) {
    super(message)
    this.response = response
  }
}

function buildUrl(url: string, params?: Record<string, unknown>): string {
  if (!current) throw new Error('离屏执行器未配置 http（configureNodeHttp）')
  if (/^[a-z][a-z0-9+.-]*:/i.test(url) || url.startsWith('//')) throw new Error(`离屏执行器只发相对路径请求，拒绝 ${url}`)
  const u = new URL(current.baseUrl + (url.startsWith('/') ? url : `/${url}`))
  for (const [k, v] of Object.entries(params || {})) {
    if (v === undefined || v === null) continue
    if (Array.isArray(v)) v.forEach((item) => u.searchParams.append(k, String(item)))
    else u.searchParams.set(k, String(v))
  }
  return u.toString()
}

function unwrap(body: any): any {
  return body && typeof body === 'object' && 'code' in body && 'data' in body ? body.data : body
}

function errorDetail(body: any, status: number): any {
  if (body && typeof body === 'object') {
    if (body.detail !== undefined) return body
    if (typeof body.message === 'string') return { ...body, detail: body.message }
  }
  return { detail: typeof body === 'string' && body ? body : `HTTP ${status}` }
}

async function send(method: string, url: string, data?: unknown, config?: RequestConfig): Promise<any> {
  const cfg = current
  if (!cfg) throw new Error('离屏执行器未配置 http（configureNodeHttp）')
  const full = buildUrl(url, config?.params)
  if (method !== 'GET') {
    const req: InterceptedRequest = { method, url, body: data, params: config?.params }
    if (!cfg.allowWrite(req)) throw new NodeHttpError(`离屏执行器不发这类写请求：${method} ${url.split('?')[0]}`)
    if (cfg.intercept) {
      const answer = cfg.intercept(req)
      if (answer !== PASS) return { data: answer, status: 200, headers: {} }
    }
  }
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(config?.headers || {}),
    Authorization: `Bearer ${cfg.token}`,
    'User-Agent': HEADLESS_USER_AGENT,
  }
  let body: string | undefined
  if (method !== 'GET' && data !== undefined && data !== null) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(data)
  }
  if (method !== 'GET') headers['X-Client-Instance'] = cfg.clientInstance
  const res = await fetch(full, { method, headers, body })
  lastTraceId = res.headers.get('x-request-id') || ''
  const text = await res.text()
  let parsed: any = text
  try {
    parsed = text ? JSON.parse(text) : null
  } catch {
    /* 非 JSON 原样 */
  }
  if (!res.ok) {
    const payload = errorDetail(parsed, res.status)
    throw new NodeHttpError(typeof payload.detail === 'string' ? payload.detail : `HTTP ${res.status}`,
      { status: res.status, data: payload })
  }
  return { data: unwrap(parsed), status: res.status, headers: Object.fromEntries(res.headers.entries()) }
}

const http = {
  get: (url: string, config?: RequestConfig) => send('GET', url, undefined, config),
  delete: (url: string, config?: RequestConfig) => send('DELETE', url, undefined, config),
  post: (url: string, data?: unknown, config?: RequestConfig) => send('POST', url, data, config),
  put: (url: string, data?: unknown, config?: RequestConfig) => send('PUT', url, data, config),
  patch: (url: string, data?: unknown, config?: RequestConfig) => send('PATCH', url, data, config),
}

export function getLastTraceId(): string {
  return lastTraceId
}

export function isRequestCancelled(_error: unknown): boolean {
  return false
}

export type GtRequestConfig = RequestConfig

export default http
