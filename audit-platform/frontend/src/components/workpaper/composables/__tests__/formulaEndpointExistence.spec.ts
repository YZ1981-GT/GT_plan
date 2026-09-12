/**
 * 平台级守卫：前端公式端点 ⊆ 后端真实注册路由
 *
 * spec: formula-management-runtime-closure Task 3
 *   (Requirements 1.3, 1.4, 1.6, 8.3, 8.5, 8.6 / Property 2, 3, 4)
 *
 * 🔴 **为什么需要这条守卫**：`useFormulaStatus.ts` 长期请求两个**后端零命中**的端点
 * （`GET /api/projects/{pid}/workpapers/{wpId}/formulas` 与
 * `POST /api/projects/{pid}/workpapers/{wpId}/prefill`），且读的响应键 `formulas`
 * 与后端 `items` 不符，被 `catch { = [] }` 吞成「暂无公式」——
 * `get_diagnostics` / vitest / Vite transform **四层全绿**，只有真实请求才暴露。
 * 错配能静默存在数月，正是因为**无人钉住「前端 URL ⊆ 后端路由」这条不变式**。
 *
 * 判据设计三条：
 * 1. **读后端 router 源码抽真实路径做交叉锁死**（R1.4），不用手写期望清单
 *    —— 手写清单会与后端漂移，等于第二份真源。
 * 2. **BASE 前缀式引用要按「前缀关系」判定**：`useFormulaImportExport.ts` 的
 *    `const BASE = '/api/formula-management/import-export'` 本身不是完整端点，
 *    真实请求是 `${BASE}/export-template` —— 只做全等比对会误报。
 * 3. **豁免必须逐条登记两个判据**（后端未实现 + 前端有降级路径），
 *    否则会把有意的前瞻占位打红、逼人删掉可用的 404 提示。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

// ── 仓库根定位：双哨兵具体文件向上查找（禁写死回退级数 / 禁用目录做哨兵） ──
function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    const s1 = path.join(dir, 'backend', 'app', 'routers', 'wp_formula.py')
    const s2 = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(s1) && fs.existsSync(s2)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repo root not found (双哨兵均未命中)')
}

const REPO_ROOT = findRepoRoot()
const FE_SRC = path.join(REPO_ROOT, 'audit-platform', 'frontend', 'src')
const BE_ROUTERS = path.join(REPO_ROOT, 'backend', 'app', 'routers')

// ---------------------------------------------------------------------------
// 后端真实注册路由抽取
// ---------------------------------------------------------------------------

interface BackendRoute {
  verb: string
  /** prefix + 装饰器 path，如 `/api/workpapers/{wp_id}/formulas` */
  fullPath: string
  file: string
}

function walk(dir: string, ext: string[]): string[] {
  const acc: string[] = []
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name)
    const st = fs.statSync(full)
    if (st.isDirectory()) {
      if (name === '__pycache__' || name === 'node_modules') continue
      acc.push(...walk(full, ext))
    } else if (ext.some((e) => name.endsWith(e))) {
      acc.push(full)
    }
  }
  return acc
}

function collectBackendRoutes(): BackendRoute[] {
  const routes: BackendRoute[] = []
  for (const py of walk(BE_ROUTERS, ['.py'])) {
    const src = fs.readFileSync(py, 'utf-8')
    // `APIRouter(... prefix="/api/xxx" ...)`；同一文件可能有多个 router，
    // 取第一个 prefix 作为默认（本仓库实测每个 router 文件只有一个 APIRouter）
    const pm = /APIRouter\([^)]*?prefix\s*=\s*["']([^"']*)["']/s.exec(src)
    const prefix = pm ? pm[1] : ''
    const re = /@\w+\.(get|put|post|delete|patch)\(\s*["']([^"']*)["']/g
    let m: RegExpExecArray | null
    while ((m = re.exec(src)) !== null) {
      routes.push({
        verb: m[1].toUpperCase(),
        fullPath: prefix + m[2] || '/',
        file: path.relative(REPO_ROOT, py),
      })
    }
  }
  return routes
}

/** `${x}` / `{x}` / `{x:path}` 插值统一归一为 `{}`，尾斜杠去掉。 */
function normalizeUrl(url: string): string {
  let u = url.replace(/\$\{[^}]*\}/g, '{}')
  u = u.replace(/\{[^}]*\}/g, '{}')
  u = u.replace(/\?.*$/, '')
  return u.replace(/\/+$/, '') || '/'
}

// ---------------------------------------------------------------------------
// 前端公式端点抽取
// ---------------------------------------------------------------------------

/** 剥注释（块注释 + 行注释），带字符串状态机避免被 `https://` 与 `image/*` 骗。 */
function stripComments(src: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (quote) {
      out += c
      if (c === '\\') {
        out += n ?? ''
        i += 2
        continue
      }
      if (c === quote) quote = null
      i += 1
      continue
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c
      out += c
      i += 1
      continue
    }
    if (c === '/' && n === '*') {
      const end = src.indexOf('*/', i + 2)
      i = end < 0 ? src.length : end + 2
      out += ' '
      continue
    }
    if (c === '/' && n === '/') {
      const end = src.indexOf('\n', i)
      i = end < 0 ? src.length : end
      out += ' '
      continue
    }
    out += c
    i += 1
  }
  return out
}

/** 公式端点扫描面（与 design §组件 7 一致：formula 组件 + useFormula* + apiPaths）。 */
const SCAN_DIRS = [
  path.join(FE_SRC, 'components', 'formula'),
  path.join(FE_SRC, 'components', 'workpaper'),
  path.join(FE_SRC, 'composables'),
  path.join(FE_SRC, 'services', 'apiPaths'),
]

interface FeUrl {
  url: string
  file: string
}

function collectFrontendFormulaUrls(): FeUrl[] {
  const acc: FeUrl[] = []
  for (const dir of SCAN_DIRS) {
    if (!fs.existsSync(dir)) continue
    for (const f of walk(dir, ['.ts', '.vue'])) {
      if (f.includes('__tests__')) continue
      // 只扫 formula 相关文件（避免把全平台端点拉进来）
      const base = path.basename(f)
      const inFormulaDir = f.includes(path.join('components', 'formula'))
      const isFormulaFile = /formula/i.test(base)
      const isApiPaths = f.includes(path.join('services', 'apiPaths'))
      if (!inFormulaDir && !isFormulaFile && !isApiPaths) continue
      const src = stripComments(fs.readFileSync(f, 'utf-8'))
      const re = /[`'"](\/api\/[^`'"\s]*)[`'"]/g
      let m: RegExpExecArray | null
      while ((m = re.exec(src)) !== null) {
        if (!/formula/i.test(m[1])) continue
        acc.push({ url: m[1], file: path.relative(FE_SRC, f) })
      }
    }
  }
  return acc
}

/**
 * 显式豁免登记 —— 每条 SHALL 写明两个判据：①后端未实现 ②前端有降级路径。
 *
 * 🔴 无豁免机制会把「有意的前瞻占位」打红，逼人删掉可用的 404 降级提示
 * （requirements 缺陷 7 已实证）。豁免条目只许减少。
 */
const ENDPOINT_EXEMPTIONS: ReadonlyArray<{
  normalized: string
  reason: string
  fallback: string
}> = Object.freeze([
  // 2026-09-11 清空：唯一条目 `/api/projects/{}/formula/auto-generate` 已删除。
  // 「把报表预设落入项目」改走既有 `POST /api/report-config/clone`（mode=sync），
  // 前端 apiPaths 的 autoGenerate 占位与调用点一并移除 ⇒ 无需豁免（判据更严）。
])

// ---------------------------------------------------------------------------
// apiPaths 访问器交叉锁死 helper
// ---------------------------------------------------------------------------

/**
 * 从 `apiPaths/formula.ts` 抽出某个访问器实际产出的 URL 模板串。
 *
 * spec: formula-management-runtime-closure Task 14（Property 19）
 *
 * 🔴 **为什么必须交叉锁死**：Task 14 把公式端点收敛进 `apiPaths` 后，
 * 调用点写的是 `projectFormula.autoGenerate(pid)` 而不再是字面量 URL。
 * 若守卫只断言「访问器被调用了」，就挡不住「访问器名字对、URL 指到别处」
 * 这类静默错误（memory 已登记该同族坑）。
 *
 * 🔴 **判据不能用 `[^,}]*` 之类的字符类截断** —— 返回值里的
 * `${projectId}` 自带 `}`，会让匹配在模板变量处提前结束。
 * 这里精确抓「反引号包裹的模板串本体」。
 *
 * @returns 访问器返回的模板串（含 `${...}` 原文），未找到返回 `null`
 */
function apiPathsAccessorUrl(accessor: string): string | null {
  const src = fs.readFileSync(
    path.join(FE_SRC, 'services', 'apiPaths', 'formula.ts'),
    'utf-8',
  )
  // 形态一：箭头函数 `name: (args) => `/api/...``
  const arrow = new RegExp(
    `\\b${accessor}\\s*:\\s*\\([^)]*\\)\\s*=>\\s*\`([^\`]+)\``,
  ).exec(src)
  if (arrow) return arrow[1]
  // 形态二：常量字符串 `name: '/api/...'` 或模板串
  const plain = new RegExp(
    `\\b${accessor}\\s*:\\s*(?:\`([^\`]+)\`|'([^']+)')`,
  ).exec(src)
  if (plain) return plain[1] ?? plain[2] ?? null
  return null
}

// ---------------------------------------------------------------------------
// 断言
// ---------------------------------------------------------------------------

const backendRoutes = collectBackendRoutes()
const backendNorm = new Set(backendRoutes.map((r) => normalizeUrl(r.fullPath)))
const feUrls = collectFrontendFormulaUrls()

describe('提取器自检（判据失效必打红）', () => {
  it('后端路由抽取非空且含已知的 wp_formula 三个端点', () => {
    expect(backendRoutes.length).toBeGreaterThan(500)
    expect(backendNorm.has('/api/workpapers/{}/formulas')).toBe(true)
    expect(backendNorm.has('/api/workpapers/{}/formulas/{}')).toBe(true)
    expect(backendNorm.has('/api/workpapers/{}/user-formulas')).toBe(true)
  })

  it('前端公式 URL 抽取非空', () => {
    expect(feUrls.length).toBeGreaterThan(20)
    const distinct = new Set(feUrls.map((u) => u.url))
    expect(distinct.size).toBeGreaterThan(15)
  })

  it('stripComments 确实剥掉注释（不剥则 docstring 里的反例会被数成真实代码）', () => {
    const fixture = [
      "/* 旧实现曾请求 '/api/projects/${pid}/workpapers/${wpId}/formulas' */",
      "// 也曾有 '/api/projects/${pid}/workpapers/${wpId}/prefill'",
      "const ok = '/api/workpapers/${id}/formulas'",
    ].join('\n')
    const stripped = stripComments(fixture)
    expect(stripped).not.toContain('workpapers/${wpId}/formulas')
    expect(stripped).not.toContain('prefill')
    expect(stripped).toContain('/api/workpapers/${id}/formulas')
  })

  it('stripComments 不被 URL 双斜杠与 MIME 通配骗（反向自检）', () => {
    const fixture = "const a = 'https://x.y/z'\nconst b = 'image/*'\nconst c = 1"
    const stripped = stripComments(fixture)
    expect(stripped).toContain('https://x.y/z')
    expect(stripped).toContain('image/*')
    expect(stripped).toContain('const c = 1')
  })

  it('normalizeUrl 归一插值（含 FastAPI 的 :path 转换器）', () => {
    expect(normalizeUrl('/api/workpapers/${wpId}/formulas')).toBe(
      '/api/workpapers/{}/formulas',
    )
    expect(normalizeUrl('/api/workpapers/{wp_id}/user-formulas/{cell_key:path}')).toBe(
      '/api/workpapers/{}/user-formulas/{}',
    )
  })
})

describe('Property 2: 全仓无 projects 作用域的 formula 端点', () => {
  const FORBIDDEN = [
    /\/api\/projects\/[^/'"`]*\/workpapers\/[^/'"`]*\/formulas/,
    /\/api\/projects\/[^/'"`]*\/workpapers\/[^/'"`]*\/prefill/,
  ]

  it('两种坏形态在扫描面内零命中', () => {
    const hits: string[] = []
    for (const { url, file } of feUrls) {
      if (FORBIDDEN.some((re) => re.test(url))) hits.push(`${file}: ${url}`)
    }
    expect(hits).toEqual([])
  })

  it('反向自检：注入该形态必被 FORBIDDEN 命中', () => {
    const injected = '/api/projects/${pid}/workpapers/${wpId}/formulas'
    expect(FORBIDDEN.some((re) => re.test(injected))).toBe(true)
    const injected2 = '/api/projects/${pid}/workpapers/${wpId}/prefill'
    expect(FORBIDDEN.some((re) => re.test(injected2))).toBe(true)
  })
})

describe('Property 3: 前端公式端点 ⊆ 后端真实注册路由', () => {
  /**
   * BASE 前缀式引用：常量本身不是完整端点，真实请求是 `${BASE}/xxx`。
   * 判据 = 存在某个后端路由以该归一路径为前缀（且后面接 `/`）。
   */
  function isBackendPrefix(norm: string): boolean {
    return [...backendNorm].some((b) => b.startsWith(norm + '/'))
  }

  const exemptSet = new Set(ENDPOINT_EXEMPTIONS.map((e) => e.normalized))

  it('每个前端公式 URL 都能匹配到后端路由（或已登记豁免）', () => {
    const unmatched: string[] = []
    for (const { url, file } of feUrls) {
      const norm = normalizeUrl(url)
      if (backendNorm.has(norm)) continue
      if (isBackendPrefix(norm)) continue
      if (exemptSet.has(norm)) continue
      unmatched.push(`${file}: ${url}  (norm=${norm})`)
    }
    expect(unmatched).toEqual([])
  })

  it('反向自检：替身 URL 既不命中后端也不在豁免 → 必被判 unmatched', () => {
    const fake = normalizeUrl('/api/workpapers/${id}/formulas-NOPE')
    expect(backendNorm.has(fake)).toBe(false)
    expect(isBackendPrefix(fake)).toBe(false)
    expect(exemptSet.has(fake)).toBe(false)
  })

  it('豁免条目逐条带两个判据且只许减少', () => {
    expect(ENDPOINT_EXEMPTIONS.length).toBeLessThanOrEqual(1)
    for (const e of ENDPOINT_EXEMPTIONS) {
      expect(e.normalized.startsWith('/api/')).toBe(true)
      // 判据 ①：后端确实没有该路由（豁免不得掩盖已存在的路由）
      expect(backendNorm.has(e.normalized)).toBe(false)
      // 判据 ②：理由与降级路径都要写实
      expect(e.reason.length).toBeGreaterThan(20)
      expect(e.fallback.length).toBeGreaterThan(20)
    }
  })

  /**
   * 前瞻占位已清零：`auto-generate` 访问器与调用点都不得复活。
   *
   * 「把报表预设落入项目」现走既有 `POST /api/report-config/clone`（mode=sync），
   * 该端点真实存在 ⇒ 不需要豁免，也不该再留 404 降级分支冒充可用功能。
   */
  it('auto-generate 占位不复活（访问器与调用点均已删除）', () => {
    const dlg = path.join(FE_SRC, 'components', 'formula', 'FormulaManagerDialog.vue')
    const src = stripComments(fs.readFileSync(dlg, 'utf-8'))
    expect(/\bprojectFormula\s*\.\s*autoGenerate\s*\(/.test(src)).toBe(false)
    expect(apiPathsAccessorUrl('autoGenerate')).toBeNull()

    // 替代路径必须真的接上（否则等于把功能删了没补）
    expect(src).toMatch(/P_rc\s*\.\s*clone/)
    expect(src).toContain("mode: 'sync'")
  })
})

describe('Property 1: 孤儿三件套已删且不复活', () => {
  const ORPHANS = [
    'composables/useFormulaStatus.ts',
    'components/workpaper/composables/useFormulaStatus.ts',
    'components/workpaper/FormulaTooltip.vue',
    'components/workpaper/FormulaSourceDrawer.vue',
    // Task 3 顺带清理：零消费方 + 调后端零命中端点 + catch 静默吞（同族）
    'components/workpaper/FormulaDependencyGraph.vue',
  ]

  it('五个孤儿路径都不存在', () => {
    const alive = ORPHANS.filter((rel) => fs.existsSync(path.join(FE_SRC, rel)))
    expect(alive).toEqual([])
  })

  it('全仓无 useFormulaStatus / FormulaDependencyGraph 的 import 或标签引用', () => {
    const hits: string[] = []
    for (const dir of [FE_SRC]) {
      for (const f of walk(dir, ['.ts', '.vue'])) {
        if (f.includes('__tests__')) continue
        if (path.basename(f) === 'components.d.ts') {
          // 自动生成文件：条目残留也算未清理干净
          const raw = fs.readFileSync(f, 'utf-8')
          for (const n of ['useFormulaStatus', 'FormulaDependencyGraph', 'FormulaTooltip', 'FormulaSourceDrawer']) {
            if (raw.includes(n)) hits.push(`components.d.ts: ${n}`)
          }
          continue
        }
        const src = stripComments(fs.readFileSync(f, 'utf-8'))
        for (const n of ['useFormulaStatus', 'FormulaDependencyGraph']) {
          if (new RegExp(`from\\s+['"][^'"]*${n}['"]`).test(src)) {
            hits.push(`${path.relative(FE_SRC, f)}: import ${n}`)
          }
          if (new RegExp(`<${n}(?=[\\s/>])`).test(src)) {
            hits.push(`${path.relative(FE_SRC, f)}: <${n}>`)
          }
        }
      }
    }
    expect(hits).toEqual([])
  })
})

describe('Property 4: 活面板端点与响应键与后端一致（已修状态不可回退）', () => {
  const panelPath = path.join(FE_SRC, 'components', 'workpaper', 'FormulaStatusPanel.vue')
  const panelSrc = fs.readFileSync(panelPath, 'utf-8')
  const panelCode = stripComments(panelSrc)

  /**
   * 面板存在且请求无 projects 前缀的端点。
   *
   * 🔴 **Task 14 后两形态都认**：面板已改走 `wpFormula.list/upsert/remove`。
   * 只按字面量 `/api/workpapers/${'$'}{props.wpId}/formulas` 断言会把正确写法打红。
   * 走 apiPaths 时**交叉锁死**该访问器真指向 `/api/workpapers/{wpId}/formulas`。
   *
   * 反向断言（`/api/projects/.../workpapers`）保持不变 —— 它钉死的是
   * Task 2 修掉的那两个后端零命中端点不得复活，与搬迁无关。
   */
  it('面板存在且请求无 projects 前缀的端点', () => {
    expect(fs.existsSync(panelPath)).toBe(true)

    const literal = panelCode.includes('/api/workpapers/${props.wpId}/formulas')
    const viaPaths = /\bwpFormula\s*\.\s*(?:list|upsert|remove)\s*\(/.test(panelCode)
    expect(literal || viaPaths).toBe(true)

    if (!literal) {
      // 访问器必须真的产出 `/api/workpapers/{wpId}/formulas`
      expect(apiPathsAccessorUrl('list')).toBe(
        '/api/workpapers/${wpId}/formulas',
      )
      expect(apiPathsAccessorUrl('remove')).toBe(
        '/api/workpapers/${wpId}/formulas/${formulaId}',
      )
    }

    expect(panelCode).not.toMatch(/\/api\/projects\/[^`'"]*\/workpapers/)
  })

  it('面板读的响应键 = 后端 list_formulas 返回体的键（交叉锁死）', () => {
    const wpFormulaPy = fs.readFileSync(
      path.join(BE_ROUTERS, 'wp_formula.py'),
      'utf-8',
    )
    // 后端 list_formulas 返回体里承载公式数组的键
    expect(/["']items["']\s*:/.test(wpFormulaPy)).toBe(true)
    expect(panelCode).toContain('data?.items')
    // 反向：不得读回旧的 `formulas` 键
    expect(/data\?\.formulas\b/.test(panelCode)).toBe(false)
  })
})
