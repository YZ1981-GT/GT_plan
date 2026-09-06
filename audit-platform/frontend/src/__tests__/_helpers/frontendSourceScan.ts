/**
 * 前端源码静态扫描工具 —— 供「引用完整性」类守卫共用
 *
 * 为什么单独成模块：`AiRenderHostReachability.spec.ts`（组件孤岛）与
 * `FrontendReferenceIntegrity.spec.ts`（模块/路由孤儿）判据不同，但都需要
 * 「注释感知的源码解析」。`stripJsComments` 有个隐蔽坑（见其 docstring），
 * 抄第二份等于把坑复制一遍，故收敛到这里作单一真源。
 *
 * 本文件不是 spec（无 `.spec.ts` 后缀），vitest 不会当测试收集。
 */
import { readFileSync, readdirSync, statSync } from 'fs'
import { join, resolve, dirname } from 'path'

// ---------------------------------------------------------------------------
// 注释剥离（纯函数，可直接喂合成源码做反向自检）
// ---------------------------------------------------------------------------

/**
 * 剥掉 JS/TS 注释，但**保留字符串与模板字面量里的内容**。
 *
 * 🔴 不能用 `src.replace(/\/\/.*$/gm, '')`：那会把 `'https://x'` 截断成 `'https:`，
 * 于是紧跟其后的 import 语句被吃掉半行，解析结果静默变少 —— 判据于是变宽而不报错。
 * 必须写成识别引号状态的字符扫描。
 */
export function stripJsComments(source: string): string {
  let out = ''
  let i = 0
  const n = source.length
  let quote: string | null = null

  while (i < n) {
    const c = source[i]
    const next = source[i + 1]

    if (quote) {
      if (c === '\\') {
        out += c + (next ?? '')
        i += 2
        continue
      }
      if (c === quote) quote = null
      out += c
      i += 1
      continue
    }

    if (c === '"' || c === "'" || c === '`') {
      quote = c
      out += c
      i += 1
      continue
    }

    if (c === '/' && next === '/') {
      while (i < n && source[i] !== '\n') i += 1
      continue
    }

    if (c === '/' && next === '*') {
      i += 2
      while (i < n && !(source[i] === '*' && source[i + 1] === '/')) i += 1
      i += 2
      continue
    }

    out += c
    i += 1
  }
  return out
}

/** 剥掉 HTML/Vue 模板注释（`<!-- ... -->`）。 */
export function stripHtmlComments(source: string): string {
  return source.replace(/<!--[\s\S]*?-->/g, '')
}

/**
 * 逐字符标记「该位置是否处于字符串/模板字面量**内部**」（引号本身标 false）。
 *
 * 🔴 为什么需要它：`stripJsComments` 有意保留字符串内容（否则 `'https://x'` 会被
 * 当行注释截断），于是**数据文件里记录的代码快照**也留在扫描面上。实测
 * `sync/workpaperSyncLegacyBaseline.generated.ts` 是一个 `.ts` 数据文件，形如
 * `{ "snippet": "import { useB60DualMode } from './composables/useB60DualMode'" }` ——
 * 那些 legacy 模块**已按计划删除**，于是 §1 判据被 8 条假红长期钉在红灯上。
 *
 * 后果不是"多报几条"这么轻：守卫一旦长期红，输出就没人再看，
 * 真缺陷会混在同一堆里溜过去。2026-09-03 实测溜过一条 ——
 * `d2/D2TabAnalysis.vue` 把 `@/composables/useExcelIO` 写成
 * `../composables/useExcelIO`，Vite transform 500，点开 D2-5 直接整页崩。
 *
 * 故 import 提取改用 **statement-position 口径**：`import`/`export` 关键字本身
 * 必须不在字符串内。specifier 自己在引号里是正常的，只看关键字位置即可区分。
 */
export function computeStringMask(source: string): Uint8Array {
  const mask = new Uint8Array(source.length)
  let i = 0
  const n = source.length
  let quote: string | null = null

  while (i < n) {
    const c = source[i]
    const next = source[i + 1]

    if (quote) {
      if (c === '\\') {
        mask[i] = 1
        if (i + 1 < n) mask[i + 1] = 1
        i += 2
        continue
      }
      if (c === quote) {
        quote = null // 收尾引号本身不算内部
        i += 1
        continue
      }
      mask[i] = 1
      i += 1
      continue
    }

    if (c === '"' || c === "'" || c === '`') {
      quote = c // 起始引号本身不算内部
      i += 1
      continue
    }

    // 注释已由 stripJsComments 剥除，这里无需再处理
    if (c === '/' && next === '/') {
      while (i < n && source[i] !== '\n') i += 1
      continue
    }
    if (c === '/' && next === '*') {
      i += 2
      while (i < n && !(source[i] === '*' && source[i + 1] === '/')) i += 1
      i += 2
      continue
    }

    i += 1
  }
  return mask
}

// ---------------------------------------------------------------------------
// 文件遍历
// ---------------------------------------------------------------------------

export const FRONTEND_SRC = resolve(__dirname, '../..')

const DEFAULT_SKIP_DIRS = new Set([
  'node_modules',
  'dist',
  '__snapshots__',
  '.vite',
  '__tests__',
])

const SOURCE_EXT = /\.(vue|ts|tsx|js)$/

/** 判断是否测试文件（`__tests__` 目录内 / `*.spec.*` / `*.test.*` / e2e 目录）。 */
export function isTestFile(absPath: string): boolean {
  const normalized = absPath.replace(/\\/g, '/')
  return (
    normalized.includes('/__tests__/') ||
    /\.(spec|test)\.[tj]sx?$/.test(normalized) ||
    normalized.includes('/e2e/')
  )
}

/**
 * 递归收集源码文件。默认跳过 `__tests__` 与构建产物 ——
 * 测试里的 `./realModule`、`` `${cycle}` `` 是反向自检的**合成样本**，
 * 把它们算进真实引用会让判据永远打红。
 */
export function walkSourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    const st = statSync(full)
    if (st.isDirectory()) {
      if (DEFAULT_SKIP_DIRS.has(entry)) continue
      walkSourceFiles(full, out)
    } else if (SOURCE_EXT.test(entry) && !/\.(spec|test)\.[tj]sx?$/.test(entry)) {
      out.push(full)
    }
  }
  return out
}

export function readSource(absPath: string): string {
  return readFileSync(absPath, 'utf-8')
}

// ---------------------------------------------------------------------------
// 模块说明符解析
// ---------------------------------------------------------------------------

/** 覆盖 `import x from 'm'` / `import 'm'` / `export … from 'm'` / `import('m')` 四形态。 */
export const MODULE_SPECIFIER_RE =
  /(?:import\s+[^;'"]*?from\s*|import\s*|export\s+[^;'"]*?from\s*|import\s*\(\s*)['"]([^'"]+)['"]/g

const SUFFIX_CANDIDATES = ['', '.ts', '.vue', '.js', '.tsx', '.jsx', '.json', '.md', '.mjs', '.d.ts']
const INDEX_CANDIDATES = ['index.ts', 'index.vue', 'index.js', 'index.tsx', 'index.mjs', 'index.d.ts']

/** 该 specifier 是否需要静态解析（裸包名 / 动态拼接 交给运行时）。 */
export function isResolvableSpecifier(specifier: string): boolean {
  if (!specifier.startsWith('.') && !specifier.startsWith('@/')) return false
  if (specifier.includes('${')) return false // 模板字面量拼出来的动态路径
  return true
}

/**
 * 按 vite 规则判断 specifier 能否解析到真实文件。
 * 会剥掉 `?raw` / `?url` / `?worker` 这类 vite query 后缀。
 */
export function moduleExists(fromFile: string, specifier: string): boolean {
  const bare = specifier.split('?')[0]
  if (!bare) return true

  let base: string
  if (bare.startsWith('@/')) {
    base = resolve(FRONTEND_SRC, bare.slice(2))
  } else if (bare.startsWith('.')) {
    base = resolve(dirname(fromFile), bare)
  } else {
    return true
  }

  for (const suf of SUFFIX_CANDIDATES) {
    try {
      if (statSync(base + suf).isFile()) return true
    } catch {
      /* not a file */
    }
  }
  try {
    if (statSync(base).isDirectory()) {
      for (const idx of INDEX_CANDIDATES) {
        try {
          if (statSync(join(base, idx)).isFile()) return true
        } catch {
          /* not a file */
        }
      }
    }
  } catch {
    /* not a dir */
  }
  return false
}

export interface BrokenReference {
  /** 相对 `src/` 的 posix 路径 */
  file: string
  line: number
  specifier: string
}

/**
 * 扫出一批文件里所有解析失败的模块引用。
 *
 * 只认 **statement-position** 的 import/export（关键字不在字符串字面量内），
 * 见 `computeStringMask` 的 docstring —— 否则数据文件里记录的代码快照
 * 会把判据长期钉红，真缺陷随之被淹没。
 */
export function findBrokenModuleReferences(files: string[]): BrokenReference[] {
  const broken: BrokenReference[] = []
  for (const file of files) {
    const code = stripJsComments(readSource(file))
    const inString = computeStringMask(code)
    MODULE_SPECIFIER_RE.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = MODULE_SPECIFIER_RE.exec(code)) !== null) {
      if (inString[m.index]) continue // 字符串里的代码快照，不是真引用
      const spec = m[1]
      if (!isResolvableSpecifier(spec)) continue
      if (moduleExists(file, spec)) continue
      broken.push({
        file: toSrcRelative(file),
        line: code.slice(0, m.index).split('\n').length,
        specifier: spec,
      })
    }
  }
  return broken
}

export function toSrcRelative(absPath: string): string {
  return absPath.replace(/\\/g, '/').replace(`${FRONTEND_SRC.replace(/\\/g, '/')}/`, '')
}

// ---------------------------------------------------------------------------
// 路由声明与导航目标
// ---------------------------------------------------------------------------

/**
 * Vue Router 的 catch-all 通配路由。
 *
 * 🔴 它**必须被排除**在「可达路由集合」之外，否则任何字符串都能匹配上，
 * 判据恒真。这不是理论风险 —— AC 1.5 的实际缺陷正是这个机制造成的：
 * `window.open('/ai-chat')` 在路由未注册时命中 catch-all 渲染 404，
 * 而 catch-all **不改变 URL**，于是只断言 URL 的 e2e 判据全绿。
 */
export const CATCH_ALL_PATTERN = /^\/:pathMatch/

export interface DeclaredRoute {
  /** 源码里写的原始 path 字面量 */
  raw: string
  /** 拼接父路径后的完整路径（以 `/` 开头） */
  full: string
}

/**
 * 从 router 源码抽出全部声明的路由路径。
 *
 * 本仓库的路由结构是「若干顶层路由 + 一个 `/`（DefaultLayout）带 children」
 * 的单层嵌套（`children:` 仅出现一次）。子路由不以 `/` 开头，其父只可能是 `/`。
 * 守卫会断言这个结构假设仍然成立 —— 一旦有人加了第二层嵌套，
 * 本函数的拼接就不再正确，必须打红而不是静默给出错误的可达集合。
 */
export function parseDeclaredRoutes(routerSource: string): DeclaredRoute[] {
  const code = stripJsComments(routerSource)
  const raws = [...code.matchAll(/path:\s*'([^']*)'/g)].map((m) => m[1])
  return raws.map((raw) => ({
    raw,
    full: raw.startsWith('/') ? raw : `/${raw}`,
  }))
}

/** router 源码里 `children:` 出现的次数（结构假设的自检值）。 */
export function countNestedChildren(routerSource: string): number {
  return (stripJsComments(routerSource).match(/children:/g) ?? []).length
}

export interface NavigationTarget {
  file: string
  line: number
  /** 导航目标路径（已剥 query / hash） */
  path: string
  /** 触发方式，用于报错时定位 */
  via: string
}

/**
 * 抽出源码里**写死的**站内导航目标。
 *
 * 只认字面量（`window.open('/x')` / `router.push('/x')` / `to="/x"`）——
 * 变量、模板拼接、对象形式（`{ name: 'X' }`）由运行时决定，静态判不了，
 * 不在本判据职责内（宁可漏判也不误判）。
 */
export function parseNavigationTargets(file: string, source: string): NavigationTarget[] {
  const out: NavigationTarget[] = []
  const code = stripHtmlComments(stripJsComments(source))

  const patterns: Array<{ via: string; re: RegExp }> = [
    { via: "window.open('…')", re: /window\.open\(\s*['"](\/[^'"?#]*)[^'"]*['"]/g },
    { via: "router.push('…')", re: /\$?router\.push\(\s*['"](\/[^'"?#]*)[^'"]*['"]/g },
    { via: "router.replace('…')", re: /\$?router\.replace\(\s*['"](\/[^'"?#]*)[^'"]*['"]/g },
    { via: 'to="…"', re: /\bto=["'](\/[^"'?#]*)[^"']*["']/g },
  ]

  for (const { via, re } of patterns) {
    re.lastIndex = 0
    let m: RegExpExecArray | null
    while ((m = re.exec(code)) !== null) {
      out.push({
        file: toSrcRelative(file),
        line: code.slice(0, m.index).split('\n').length,
        path: m[1],
        via,
      })
    }
  }
  return out
}

/**
 * 目标路径能否匹配到一条**非 catch-all** 的声明路由。
 * 动态段（`:id`）匹配任意单个非空 segment。
 */
export function pathMatchesDeclaredRoute(target: string, declared: DeclaredRoute[]): boolean {
  const targetSegs = target.split('/').filter(Boolean)

  for (const route of declared) {
    if (CATCH_ALL_PATTERN.test(route.full)) continue // 🔴 catch-all 不算可达
    const routeSegs = route.full.split('/').filter(Boolean)

    if (routeSegs.length === 0) {
      if (targetSegs.length === 0) return true
      continue
    }
    if (routeSegs.length !== targetSegs.length) continue

    const ok = routeSegs.every((seg, i) => seg.startsWith(':') || seg === targetSegs[i])
    if (ok) return true
  }
  // 根路径 '/' 单独放行（`path: '/'` 拼出来的 full 就是 '/'）
  return targetSegs.length === 0 && declared.some((r) => r.full === '/')
}
