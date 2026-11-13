/**
 * 只读 UAT 浏览器防火墙（spec trim-generation-plan-followup-optimizations R5.4）。
 *
 * 安全边界是后端 readonly 权限 + 本防火墙两层；不依赖按钮隐藏。防火墙装在 BrowserContext 上（含弹窗），
 * 必须在建 page 之前装好：
 * - 非 GET / HEAD 的请求（POST / PUT / PATCH / DELETE / OPTIONS / beacon / 表单提交）一律中止并记入 attemptedWrites；
 * - WebSocket 一律不连服务器并记入 attemptedWrites（Vite 开发服务的热更新连接单独记 blockedInfra，不算写入）；
 * - API 的 GET / HEAD 只放行显式白名单；未知 API GET 也中止（防「名为 GET 的副作用」），记入 blockedReads；
 * - 只放行应用同源的静态资源，外部域名一律中止，记入 blockedExternal；
 * - 放行的请求用 `route.fallback()`（交给后续路由或网络），便于测试里在其后挂桩。
 * Service Worker 由 context 选项 `serviceWorkers: 'block'` 关掉（见 newGuardedContext）。
 */
import type { Browser, BrowserContext, BrowserContextOptions, Route, WebSocketRoute } from '@playwright/test'

export type RequestVerdict = 'allow' | 'write' | 'blocked_read' | 'external'

export interface ReadonlyGuardOptions {
  /** 应用源，如 `http://127.0.0.1:3030` */
  appOrigin: string
  /** 允许的 API 读路径（匹配 pathname，含 `/api/` 前缀） */
  apiReadAllowlist: readonly RegExp[]
}

export interface GuardEntry {
  method: string
  url: string
}

export interface GuardLog {
  attemptedWrites: Array<GuardEntry & { kind: 'http' | 'websocket' }>
  blockedReads: GuardEntry[]
  blockedExternal: GuardEntry[]
  blockedInfra: GuardEntry[]
  allowed: GuardEntry[]
}

const READ_METHODS = new Set(['GET', 'HEAD'])

/** 纯函数：一条请求该怎么处理（单测与守卫共用）。 */
export function classifyRequest(method: string, url: string, options: ReadonlyGuardOptions): RequestVerdict {
  if (!READ_METHODS.has(method.toUpperCase())) return 'write'
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return 'external'
  }
  if (parsed.protocol === 'data:' || parsed.protocol === 'blob:') return 'allow'
  if (parsed.origin !== new URL(options.appOrigin).origin) return 'external'
  if (parsed.pathname === '/api' || parsed.pathname.startsWith('/api/')) {
    return options.apiReadAllowlist.some((re) => re.test(parsed.pathname)) ? 'allow' : 'blocked_read'
  }
  return 'allow'
}

/**
 * 回环主机名：Vite 客户端有两条 HMR 连接地址 —— `socketHost`（按页面 URL 的 hostname 拼）和
 * `directSocketHost`（**构建期硬编码**，`server.host` 是 `0.0.0.0` 时固定为 `localhost:<port>/`）。
 * 第一条被本防火墙关掉后，Vite 会回退到第二条，于是出现「页面开在 127.0.0.1、HMR 连 localhost」。
 */
const LOOPBACK_HOSTNAMES = new Set(['localhost', '127.0.0.1', '[::1]', '::1'])

/**
 * Vite 开发服务的热更新 WebSocket：根路径 + 带 `token` 查询 + 与应用同端口（不是业务通道）。
 *
 * 🔴 主机名不能要求与 appOrigin 严格相等。2026-11-06 真实项目只读走查实测：第一条
 * `ws://127.0.0.1:3030/?token=…` 被本防火墙按 infra 正确拦下并 `close(1008)`，Vite 据此判定
 * 连接失败、回退到硬编码的 `ws://localhost:3030/?token=…`，而旧判据按 `host` 字符串比 ⇒ 回退那条
 * 被记成 `attemptedWrites`，使 R5.5 的「零写入」断言在开发模式下**恒红**（恒红门禁等于没有门禁）。
 * 现判据：端口必须等于应用端口、路径必须是根、必须带 Vite 的 `token`，主机名同源或回环。
 * 口径仍然是紧的：业务 WebSocket 不会落在应用端口的根路径上并带 `token`（平台项目事件走 SSE，
 * OnlyOffice 在自己的端口），非回环的外部主机、换路径、换端口、缺 token 都仍记为写入尝试。
 */
export function isViteHmrSocket(url: string, appOrigin: string): boolean {
  try {
    const parsed = new URL(url)
    const app = new URL(appOrigin)
    if (parsed.pathname !== '/') return false
    if (!parsed.searchParams.has('token')) return false
    const defaultPort = (protocol: string) => (protocol === 'wss:' || protocol === 'https:' ? '443' : '80')
    const port = parsed.port || defaultPort(parsed.protocol)
    const appPort = app.port || defaultPort(app.protocol)
    if (port !== appPort) return false
    return parsed.hostname === app.hostname || LOOPBACK_HOSTNAMES.has(parsed.hostname)
  } catch {
    return false
  }
}

export function emptyGuardLog(): GuardLog {
  return { attemptedWrites: [], blockedReads: [], blockedExternal: [], blockedInfra: [], allowed: [] }
}

/** 在 context 上装防火墙（必须早于 newPage）。返回持续累积的拦截记录。 */
export async function installReadonlyGuard(context: BrowserContext, options: ReadonlyGuardOptions): Promise<GuardLog> {
  const log = emptyGuardLog()
  await context.route('**/*', async (route: Route) => {
    const request = route.request()
    const entry = { method: request.method(), url: request.url() }
    const verdict = classifyRequest(entry.method, entry.url, options)
    if (verdict === 'allow') {
      log.allowed.push(entry)
      await route.fallback()
      return
    }
    if (verdict === 'write') log.attemptedWrites.push({ ...entry, kind: 'http' })
    else if (verdict === 'blocked_read') log.blockedReads.push(entry)
    else log.blockedExternal.push(entry)
    await route.abort('blockedbyclient')
  })
  await context.routeWebSocket(/.*/, (ws: WebSocketRoute) => {
    const entry = { method: 'WEBSOCKET', url: ws.url() }
    if (isViteHmrSocket(entry.url, options.appOrigin)) log.blockedInfra.push(entry)
    else log.attemptedWrites.push({ ...entry, kind: 'websocket' })
    // 不调用 connectToServer：连接从不到达服务器
    ws.close({ code: 1008, reason: 'readonly-uat-guard' })
  })
  return log
}

/** 建一个装好防火墙、禁用 Service Worker、关掉录像的独立 context。 */
export async function newGuardedContext(
  browser: Browser,
  options: ReadonlyGuardOptions,
  contextOptions: BrowserContextOptions = {},
): Promise<{ context: BrowserContext; log: GuardLog }> {
  const context = await browser.newContext({
    ...contextOptions,
    serviceWorkers: 'block',
    recordVideo: undefined,
    recordHar: undefined,
  })
  const log = await installReadonlyGuard(context, options)
  return { context, log }
}

/** 报告用：只留方法 + 去掉查询串的路径，避免把令牌等查询参数写进测试输出。 */
export function summarizeLog(log: GuardLog): Record<keyof GuardLog, string[]> {
  const strip = (e: GuardEntry) => {
    try {
      const u = new URL(e.url)
      return `${e.method} ${u.origin}${u.pathname}`
    } catch {
      return `${e.method} ${e.url.split('?')[0]}`
    }
  }
  return {
    attemptedWrites: log.attemptedWrites.map(strip),
    blockedReads: log.blockedReads.map(strip),
    blockedExternal: log.blockedExternal.map(strip),
    blockedInfra: log.blockedInfra.map(strip),
    allowed: [...new Set(log.allowed.map(strip))],
  }
}
