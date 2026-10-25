/**
 * 绕过 http.ts 拦截器的原生请求 · 鉴权头守卫
 *
 * ## 它防的是什么
 *
 * 平台只有 `utils/http.ts` 的 axios 实例（`api.*` / `http.*` 经它）会自动附加 `Authorization`。
 * 另外三种写法都**不会**：
 *   - 原生 `fetch(url, …)` / `new EventSource(url)`；
 *   - **axios 默认实例**（`import axios from 'axios'` 或 `await import('axios')` 后直接 `axios.post`）——
 *     它和 http.ts 不是同一个实例，拦截器不生效。
 * 后端几乎所有端点都依赖 HTTPBearer ⇒ 这些请求恒 401；而调用点多半 `catch {}` 静默吞掉，
 * 用户只看到「点了没反应 / 附注永远没同步」。
 *
 * 2026-09-30 现算（后端 `/openapi.json` 逐端点比对 security 声明 + 真请求复核）：
 *   - J2 附注同步 ×3（上市 / 国企 / 净资产分支）：axios 默认实例 ⇒ 401；且载荷形状也不对
 *     （缺 wp_id / section_id / current_standard，422）⇒ **从未同步成功过**，真库五、49 / 八、54 / 五、17
 *     共 8 个章节 `_last_sync_wp_id` 全 0；
 *   - E0-3 发函清单「AI 生成」：axios 默认实例 ⇒ 401；
 *   - D2 导入导出 ×3、D2/D4/F3/F4 切「在线编辑」×4：原生 fetch 无鉴权头 ⇒ 401
 *     （切在线编辑失败后被 catch 成「OnlyOffice 不可用」；F3/F4 另缺必填 `project_id` ⇒ 带鉴权也 422）；
 *   - 高级查询批量执行：axios 默认实例 ⇒ 401，且未解 `{code,message,data}` 信封；
 *   - 账表导入进度、全链路进度、附件页实时刷新：原生 EventSource ⇒ 从未连上。
 * 已全部改走 `api.*`（经拦截器）/ `getAuthHeaders()`（原生请求唯一鉴权入口）/ `createSSE`（fetch 流）/
 * `subscribeProjectEvent`（项目事件总线）。
 *
 * ## 判据
 *
 * 生产源码里：
 *   1. 除 `KNOWN_UNAUTH_AXIOS` 登记的站点外，不得用 axios **默认实例**发请求
 *      （`import axios from 'axios'` / `await import('axios')` 后 `axios.get/post/…`；`axios.create` 工厂不算）；
 *   2. 原生 `fetch('/api/…')` 的字面量 URL 若不在 `PUBLIC_API_PREFIXES`（后端无鉴权依赖的公开端点），
 *      其实参区须出现 `getAuthHeaders` / `getAuthToken` / `Authorization`；
 *   3. 不得 `new EventSource(…)`：原生 EventSource 不能带请求头，而后端 SSE 端点几乎都只认 Bearer 头
 *      （账表导入进度 / 全链路进度 `?token=` 实测 401；附件页连的 `/api/sse/projects/{pid}` 路由根本不存在）。
 * 带反向自检（各判据对合成样本真能命中 / 不误报）与扫描面非空断言。
 */
import { describe, expect, it } from 'vitest'
import {
  FRONTEND_SRC,
  isTestFile,
  readSource,
  stripHtmlComments,
  stripJsComments,
  toSrcRelative,
  walkSourceFiles,
} from './_helpers/frontendSourceScan'

/** 后端无鉴权依赖的公开端点前缀（`/openapi.json` 现算：operation 无 security 声明） */
const PUBLIC_API_PREFIXES = ['/api/workpapers/onlyoffice/health', '/api/version', '/api/health']

/**
 * 有意用 axios 默认实例直接发请求的文件（只减不增；现为空，新增须写明理由并经评审）。
 *
 * 注：`axios.create()` 出来的独立实例不在本判据内 —— `stores/auth.ts` 的 `authHttp`（登录 / 刷新 / 登出，
 * 本就不带 access token）与 `DegradedBanner.vue` 的健康轮询实例（每次显式附 Authorization）都属此类。
 */
const KNOWN_UNAUTH_AXIOS: ReadonlyArray<{ file: string; reason: string }> = []

/** 取得 axios **默认实例**绑定的写法（静态默认导入 / 动态 import 解构 default） */
const AXIOS_DEFAULT_BINDING_RE =
  /import\s+axios\b[^;\n]*from\s+['"]axios['"]|\{\s*default\s*:\s*axios\s*\}\s*=\s*await\s+import\(\s*['"]axios['"]\s*\)/
/** 用默认实例**发请求**（`axios.create` / `axios.isCancel` 等工厂与工具函数不算） */
const AXIOS_DEFAULT_REQUEST_RE = /(?<![\w.$])axios\s*\.\s*(?:get|post|put|patch|delete|head|request)\s*\(/
/** 不落绑定、直接链式调用：`(await import('axios')).default.post(...)` */
const AXIOS_INLINE_REQUEST_RE =
  /import\(\s*['"]axios['"]\s*\)\s*\)\s*\.\s*default\s*\.\s*(?:get|post|put|patch|delete|head|request)\s*\(/
const FETCH_LITERAL_RE = /(?<![\w.$])fetch\s*\(\s*(['"`])(\/api\/[^'"`]*)\1/g
const AUTH_RE = /getAuthHeaders|getAuthToken|Authorization/
/** 鉴权头常在调用前组装成变量再传入（`const headers = {..., ...getAuthHeaders()}`）；只在实参确实传了 headers 时回看 */
const LOOKBACK_CHARS = 400

function codeOf(file: string, source: string): string {
  const code = stripJsComments(source)
  return file.endsWith('.vue') ? stripHtmlComments(code) : code
}

/** 从 `(` 起按括号配平截出实参区（字符串 / 模板串内的括号不计）。 */
export function callArgs(code: string, openIdx: number): string {
  let depth = 0
  let quote: string | null = null
  for (let i = openIdx; i < code.length; i += 1) {
    const c = code[i]
    if (quote) {
      if (c === '\\') { i += 1; continue }
      if (c === quote) quote = null
      continue
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; continue }
    if (c === '(') depth += 1
    else if (c === ')') {
      depth -= 1
      if (depth === 0) return code.slice(openIdx, i + 1)
    }
  }
  return code.slice(openIdx)
}

export function findUnauthFetch(code: string): string[] {
  const out: string[] = []
  FETCH_LITERAL_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = FETCH_LITERAL_RE.exec(code)) !== null) {
    const url = m[2]
    if (PUBLIC_API_PREFIXES.some((p) => url.startsWith(p))) continue
    const args = callArgs(code, code.indexOf('(', m.index))
    if (AUTH_RE.test(args)) continue
    const passesHeaders = /\bheaders\b/.test(args)
    if (passesHeaders && AUTH_RE.test(code.slice(Math.max(0, m.index - LOOKBACK_CHARS), m.index))) continue
    out.push(url)
  }
  return out
}

export function usesAxiosDefault(code: string): boolean {
  return (AXIOS_DEFAULT_BINDING_RE.test(code) && AXIOS_DEFAULT_REQUEST_RE.test(code))
    || AXIOS_INLINE_REQUEST_RE.test(code)
}

const FILES = walkSourceFiles(FRONTEND_SRC).filter((f) => !isTestFile(f))
const ALLOWED_AXIOS = new Set(KNOWN_UNAUTH_AXIOS.map((k) => k.file))

describe('原生请求鉴权守卫 · 判据自身不空洞', () => {
  it('扫描面覆盖足够多的生产源文件', () => {
    expect(FILES.length).toBeGreaterThan(2000)
  })

  it('反向自检：不带鉴权的原生 fetch 能识别（含多行实参 / 模板串 URL）', () => {
    expect(findUnauthFetch("await fetch('/api/x/1')")).toEqual(['/api/x/1'])
    expect(findUnauthFetch('await fetch(`/api/w/${id}/d2/export-data?s=${a}`, {\n  method: "POST",\n})'))
      .toEqual(['/api/w/${id}/d2/export-data?s=${a}'])
  })

  it('反向自检：带鉴权 / 公开端点 / 非 /api 不误报', () => {
    expect(findUnauthFetch("fetch('/api/x', { headers: getAuthHeaders() })")).toEqual([])
    expect(findUnauthFetch("fetch('/api/x', {\n  headers: { Authorization: `Bearer ${t}` },\n})")).toEqual([])
    // 鉴权头先组装成变量再传入
    expect(findUnauthFetch("const headers = { ...getAuthHeaders() }\nfetch('/api/x', { method: 'POST', headers })")).toEqual([])
    expect(findUnauthFetch("fetch('/api/workpapers/onlyoffice/health')")).toEqual([])
    expect(findUnauthFetch("fetch('https://cdn.example.com/a.js')")).toEqual([])
    expect(findUnauthFetch("refetch('/api/x')")).toEqual([])
  })

  it('反向自检：回看只在实参真的传了 headers 时生效（附近有鉴权取值但本请求没带 ⇒ 仍报）', () => {
    expect(findUnauthFetch("const h = getAuthHeaders()\nfetch('/api/x', { method: 'POST', body: fd })")).toEqual(['/api/x'])
  })

  it('反向自检：axios 默认实例发请求的三种写法都能识别；工厂 / 工具函数 / apiProxy / 类型导入不误报', () => {
    expect(usesAxiosDefault("import axios from 'axios'\nawait axios.post('/api/x', {})")).toBe(true)
    expect(usesAxiosDefault("const { default: axios } = await import('axios')\nawait axios.post(u, b)")).toBe(true)
    expect(usesAxiosDefault("const r = await (await import('axios')).default.get(u)")).toBe(true)
    expect(usesAxiosDefault("import axios from 'axios'\nconst http = axios.create({ baseURL: '/' })\naxios.isCancel(e)")).toBe(false)
    expect(usesAxiosDefault("import type { AxiosRequestConfig } from 'axios'")).toBe(false)
    expect(usesAxiosDefault("import { api } from '@/services/apiProxy'\nawait api.post(u)")).toBe(false)
  })
})

describe('绕过 http.ts 拦截器的请求必须自带鉴权', () => {
  it('除已登记文件外，不用 axios 默认实例发请求（它不经 http.ts 拦截器，不带 Authorization）', () => {
    const offenders = FILES
      .filter((f) => usesAxiosDefault(codeOf(f, readSource(f))))
      .map(toSrcRelative)
      .filter((rel) => !ALLOWED_AXIOS.has(rel))
    expect(offenders, '改用 `import { api } from \'@/services/apiProxy\'`').toEqual([])
  })

  it('原生 fetch 打受保护的 /api 端点必须带 getAuthHeaders()', () => {
    const offenders: string[] = []
    for (const f of FILES) {
      for (const url of findUnauthFetch(codeOf(f, readSource(f)))) offenders.push(`${toSrcRelative(f)} → ${url}`)
    }
    expect(offenders, '原生 fetch 不经拦截器；改走 api.* 或加 headers: getAuthHeaders()').toEqual([])
  })

  it('不用原生 EventSource 连 /api（它不能带请求头；改用 createSSE 或项目事件总线 subscribeProjectEvent）', () => {
    const offenders = FILES
      .filter((f) => /new\s+EventSource\s*\(/.test(codeOf(f, readSource(f))))
      .map(toSrcRelative)
    expect(offenders).toEqual([])
  })

  it('已登记的 axios 默认实例文件仍在使用它（名单无失效条目）且写明理由', () => {
    const stale = KNOWN_UNAUTH_AXIOS.filter((k) => {
      const abs = FILES.find((f) => toSrcRelative(f) === k.file)
      return !abs || !usesAxiosDefault(codeOf(abs, readSource(abs)))
    })
    expect(stale.map((s) => s.file)).toEqual([])
    expect(KNOWN_UNAUTH_AXIOS.every((k) => k.reason.trim().length > 10)).toBe(true)
  })
})
