/**
 * 前端请求路径必须带 /api 前缀（spec platform-performance-residual-findings-closure 验收期发现）。
 *
 * `utils/http` 的 baseURL 是 '/'，开发代理（vite.config.ts）与部署都只把 /api、/wopi 转给后端：
 * `api.get('/projects/…')` 这类请求落到前端页面本身 —— GET 拿到首页 HTML、PUT / POST 404，调用方多半 catch 静默
 * ⇒ 功能从未生效、页面也不报错。2026-10-31 现算 15 处：A18-2 沟通函读写 / 建议 / 表头带出 5 处、I1/I3~I6
 * OnlyOffice 健康检查 5 处（恒判不可用，在线编辑入口从不出现）、H3 产权抵押 / 转让勾稽 2 处、K10 识别 2 处、
 * H5 自取渲染配置 1 处、侧栏 PBC 1 处、凭证识别弹窗 1 处。
 *
 * 判据：api / http / apiProxy / httpApi 客户端的 get / post / put / patch / delete，第一个参数是以 / 开头的字面量
 * 时必须以 /api/（或 /wopi/）开头；动态拼接（`${base}/x`）与访问器不在此列。`services/apiPaths` 里以 / 开头的
 * 路径字面量同样须带前缀。只看 `<script>`、先剥注释（注释里的示例路径不算）。
 */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { FRONTEND_SRC, stripJsComments, toSrcRelative, walkSourceFiles } from './_helpers/frontendSourceScan'

const BACKEND_PREFIXES = ['/api/', '/wopi/']
const CALL_RE = /\b(?:api|http|apiProxy|httpApi)\s*\.\s*(?:get|post|put|patch|delete)\s*(?:<[^>()]*>)?\s*\(\s*([`'"])(\/[^`'"]*)/g
const PATH_LITERAL_RE = /([`'"])(\/[^`'"\s]*)/g

function scriptOf(rel: string, text: string): string {
  if (!rel.endsWith('.vue')) return text
  return [...text.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]).join('\n')
}

const backendPath = (p: string) => BACKEND_PREFIXES.some((prefix) => p.startsWith(prefix))

/** 一个文件里「客户端调用第一个参数是 / 开头字面量」的全部路径；返回（全部, 不带前缀的）。 */
export function scanCalls(rel: string, text: string): { all: string[]; bad: string[] } {
  const code = stripJsComments(scriptOf(rel, text))
  const all = [...code.matchAll(CALL_RE)].map((m) => m[2])
  return { all, bad: all.filter((p) => !backendPath(p)) }
}

/** apiPaths 文件里以 / 开头、却不以后端前缀开头的路径字面量（单独的 '/' 与 '/api' 不算）。 */
export function scanApiPathLiterals(text: string): string[] {
  const code = stripJsComments(text)
  return [...code.matchAll(PATH_LITERAL_RE)].map((m) => m[2]).filter((p) => p !== '/' && p !== '/api' && !backendPath(p))
}

const sources = walkSourceFiles(FRONTEND_SRC)
  .filter((f) => /\.(ts|vue)$/.test(f))
  .map((f) => ({ rel: toSrcRelative(f), text: readFileSync(f, 'utf8') }))

describe('前端请求路径带 /api 前缀', () => {
  it('客户端调用的字面量路径都以 /api/ 开头', () => {
    const bad = sources.flatMap(({ rel, text }) => scanCalls(rel, text).bad.map((p) => `${rel}  ${p}`))
    expect(bad, `以下请求落到前端页面本身（少 /api 前缀）：\n${bad.join('\n')}`).toEqual([])
  })

  it('扫描面不塌缩（字面量调用 ≥ 2000 处）', () => {
    const total = sources.reduce((n, { rel, text }) => n + scanCalls(rel, text).all.length, 0)
    expect(total).toBeGreaterThanOrEqual(2000)
  })

  it('services/apiPaths 里的路径字面量都带后端前缀', () => {
    const files = sources.filter(({ rel }) => rel.startsWith('services/apiPaths/'))
    expect(files.length).toBeGreaterThan(5)
    const bad = files.flatMap(({ rel, text }) => scanApiPathLiterals(text).map((p) => `${rel}  ${p}`))
    expect(bad).toEqual([])
  })
})

describe('扫描器自检', () => {
  it('少前缀的字面量调用必报（模板串 / 泛型 / 多种客户端）', () => {
    const src = [
      "await api.get('/projects/p1')",
      'await api.get<any>(`/workpapers/${id}/render-config`)',
      "await http.put('/projects/p1/x', body)",
      "await apiProxy.post(\n  `/projects/${pid}/document-recognize`,\n  {},\n)",
    ].join('\n')
    expect(scanCalls('a.ts', src).bad).toEqual(['/projects/p1', '/workpapers/${id}/render-config', '/projects/p1/x', '/projects/${pid}/document-recognize'])
  })

  it('带前缀、动态拼接、前端路由跳转、注释里的示例都不报', () => {
    const src = [
      "await http.post('/api/x', fd)",
      "await api.get('/wopi/files/1')",
      'await api.get(`${base}/check-incomplete`)',
      'await api.get(P_proj.myAssignments)',
      "router.push('/projects/p1/reports')",
      "// api.get('/items')",
      '/**',
      " * const { data } = useFirstLoad(() => api.get('/items'))",
      ' */',
    ].join('\n')
    const { all, bad } = scanCalls('a.ts', src)
    expect(bad).toEqual([])
    expect(all).toEqual(['/api/x', '/wopi/files/1'])
  })

  it('.vue 只看 <script>：模板文字里的写法不算', () => {
    const vue = "<template><p>例：api.get('/items')</p></template>\n<script setup lang=\"ts\">\nawait api.get('/projects/x')\n</script>\n"
    expect(scanCalls('a.vue', vue).bad).toEqual(['/projects/x'])
  })

  it('apiPaths 字面量：少前缀必报，/api/ 与单独的 / 不报', () => {
    expect(scanApiPathLiterals("export const a = { list: '/projects/', ok: '/api/x', root: '/' }")).toEqual(['/projects/'])
  })
})
