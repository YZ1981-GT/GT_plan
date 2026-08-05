/**
 * Property 4 / 5 — 函证域「渲染宿主存在性」守卫
 *
 * spec: confirmation-orphan-and-amount-format-closure（Requirement 2）
 *
 * ## 为什么这条守卫必须递归到「有渲染宿主」
 *
 * G0 Task 23 实测命名的缺陷模式：**A 有消费方 B，但 B 自己没有消费方**。
 * `buildCrossWorkpaperNavDefs` 的既有守卫断言「有真实非测试消费方」并通过，
 * 而那个消费方 `CrossWorkpaperNav.vue` 全仓零渲染宿主 → 修复正确但用户不可达。
 *
 * 故本守卫的判据不是「被谁 import」，而是：
 * - 组件：被某个**非测试** `.vue` 以 `<PascalName` 或 `<kebab-name` 渲染，
 *   或被 `htmlRendererRegistry.ts` 按 componentType 注册（那是宿主级入口）。
 * - 模块：被某个**非测试** `.vue`/`.ts` import 或引用其导出符号。
 *
 * ## 排除项与其理由
 *
 * `__tests__/**` 与 `components.d.ts` 不算消费方 —— 前者是「守卫保护着死代码」，
 * 后者是 unplugin 自动生成的全局注册声明（对 `.vue` 里未使用的组件也会写一条）。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  KNOWN_ORPHAN_COMPONENTS,
  KNOWN_ORPHAN_MODULES,
  type OrphanEntry,
} from './orphanHostBaseline'

// ─── REPO_ROOT：**双哨兵文件**向上查找（禁写死回退级数）───────────────────
// 🔴 与同目录 crossWorkpaperNavWiring.spec.ts 同一范式。两条铁律：
//    ① 禁写死 `resolve(__dirname, '../../..')` —— 级数一错整个 spec 文件 ENOENT，
//       报告里表现为「文件级失败」而非断言失败，极易被当噪声跳过（本仓已实测踩过）。
//    ② 哨兵必须是**具体文件**且取两个：`audit-platform/backend/app/routers` 是历史遗留
//       空目录，用目录当哨兵会在 `audit-platform` 层提前停下；单哨兵也不够稳
//       （将来子目录里出现同名文件即误停）。
const SENTINELS = [
  path.join('backend', 'app', 'data', 'wp_code_overrides.json'),
  path.join('audit-platform', 'frontend', 'package.json'),
] as const

function findRepoRoot(start: string): string {
  let dir = path.resolve(start)
  for (let i = 0; i < 20; i += 1) {
    if (SENTINELS.every((s) => fs.existsSync(path.join(dir, s)))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能从 ${start} 向上找到同时含哨兵文件的仓库根：${SENTINELS.join(' + ')}`)
}
const REPO_ROOT = findRepoRoot(__dirname)
const SRC = path.join(REPO_ROOT, 'audit-platform/frontend/src')
const WP = path.join(SRC, 'components/workpaper')
const SCAN_DIRS = [path.join(WP, 'confirmation'), path.join(WP, 'g0-confirmation')]

function walk(dir: string, exts: string[]): string[] {
  const out: string[] = []
  if (!fs.existsSync(dir)) return out
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) out.push(...walk(p, exts))
    else if (exts.some((x) => e.name.endsWith(x))) out.push(p)
  }
  return out
}

function rel(abs: string): string {
  return path.relative(WP, abs).replace(/\\/g, '/')
}

function kebab(name: string): string {
  return name.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()
}

/**
 * 剥注释（**带字符串状态的扫描器**，不是裸正则）。
 *
 * 🔴 必需：`blockColumnConfigs.ts` 的文件头注释里写着「`blockColumnAmountRegistry.ts` 的
 * NON_AMOUNT_NUMBER_COLUMNS 里登记理由」→ 不剥注释会把该说明数成真实引用，
 * 于是 registry 被判「有消费方」= **假阴性**（孤儿被漏掉）。
 *
 * 同族坑：`accept="image/*"` 的 `/*` 会被当块注释起点一直吞到几千字符后
 * （memory 已登记两个真实宿主因此逃出扫描面）→ 故必须带引号状态。
 *
 * ## 性能形态：**逐段 slice**，不是逐字符 `out += c`
 *
 * 语义与逐字符版**逐字节等价**（保留原文的一切非注释字符，每段注释换成一个空格），
 * 只把「输出」从 58 MB 次字符串拼接改成「攒 span → 一次 join」，并用 `charCodeAt`
 * 代替 `src[i]`（后者每次分配一个单字符串）。实测该函数从 3926 ms 降到 ~230 ms。
 *
 * 🔴 刻意**不**丢弃 `<style>` 整段：现行判据从未丢过它，加上就是改「判什么」
 * （CSS 选择器里不会出现 `<Tag`，收益为零而语义风险非零）。
 */
const CH_QUOTE_D = 34 /* " */
const CH_QUOTE_S = 39 /* ' */
const CH_BACKTICK = 96 /* ` */
const CH_SLASH = 47 /* / */
const CH_STAR = 42 /* * */
const CH_BACKSLASH = 92 /* \ */
const CH_LT = 60 /* < */
const CH_BANG = 33 /* ! */
const CH_DASH = 45 /* - */

function stripComments(src: string): string {
  const len = src.length
  const parts: string[] = []
  let seg = 0
  let i = 0
  let quote = 0
  while (i < len) {
    const c = src.charCodeAt(i)
    if (quote !== 0) {
      if (c === CH_BACKSLASH) {
        i += 2
        continue
      }
      if (c === quote) quote = 0
      i += 1
      continue
    }
    if (c === CH_QUOTE_D || c === CH_QUOTE_S || c === CH_BACKTICK) {
      quote = c
      i += 1
      continue
    }
    if (c === CH_SLASH) {
      const n = src.charCodeAt(i + 1)
      if (n === CH_STAR) {
        parts.push(src.slice(seg, i), ' ')
        const end = src.indexOf('*/', i + 2)
        i = end === -1 ? len : end + 2
        seg = i
        continue
      }
      if (n === CH_SLASH) {
        parts.push(src.slice(seg, i), ' ')
        const end = src.indexOf('\n', i)
        i = end === -1 ? len : end
        seg = i
        continue
      }
      i += 1
      continue
    }
    if (
      c === CH_LT &&
      src.charCodeAt(i + 1) === CH_BANG &&
      src.charCodeAt(i + 2) === CH_DASH &&
      src.charCodeAt(i + 3) === CH_DASH
    ) {
      parts.push(src.slice(seg, i), ' ')
      const end = src.indexOf('-->', i)
      i = end === -1 ? len : end + 3
      seg = i
      continue
    }
    i += 1
  }
  parts.push(src.slice(seg))
  return parts.join('')
}

type Consumer = { readonly path: string; readonly text: string; readonly code?: string }

/**
 * ─── 倒排索引：把 O(目标数 × 全仓字节) 改成 O(全仓字节) ──────────────────────
 *
 * 改造前每个目标都拿自己的正则重扫一遍全仓 5080 个文件的**剥注释文本**（58 MB），
 * 71 个组件 + 126 个模块 × 若干调用点 ≈ 1.6 M 次正则 `.test()` → 实测 ~9.3 s。
 * 现在改成：全仓**只扫一遍**，抽出「本文件出现过哪些标签名 / import 了哪些路径末段」，
 * 建两张 `名字 → 出现在哪些文件` 的 Map，之后每个目标 O(1) 查表。
 *
 * 🔴 判据（判什么）逐条不变，两处等价性是这次优化的全部风险面：
 *
 * 1. **标签**：`<STEM(?![\w-])` 命中 ⟺ `/<([\w-]+)/g` 抽出的 token 里**恰好等于** STEM。
 *    负向断言 `(?![\w-])` 与 token 的最大 `[\w-]+` 取法是同一个字符类，故
 *    `<FooREMOVED` 抽出 `FooREMOVED ≠ Foo`（不命中）、`<Foo/>`/`<Foo>`/`<Foo :a="1"`
 *    抽出 `Foo`（命中）—— **标签名边界仍在**，且从「负向 lookahead」升级成「全等」。
 *
 * 2. **import**：原正则 `['"][^'"]*\/STEM(?:\.ts)?['"]` 要求引号内以 `/STEM` 或
 *    `/STEM.ts` **结尾**（`[^'"]*` 虽含 `/` 但后面必须紧跟闭合引号，故只有**末段**算）。
 *    倒排用**同一个形状**的泛化正则 `['"][^'"]*\/([^'"/]*)['"]`（把 STEM 换成捕获组、
 *    `[^'"/]*` 强制「最后一个斜杠之后」），再把末段连同去掉 `.ts` 的形态一起入表 →
 *    与逐目标版在同一起始位置、同一回溯路径上取同一个 match。
 *    覆盖 `'./x'` / `'@/a/b/x'` / `'../x.ts'` / `export … from` / `import('...')` 全形态；
 *    反引号仍**不**算（原正则字符类里就没有 `` ` ``，保持不变）。
 *
 * 上述等价性由三重手段兜住：①下方内联 fixture 的「新旧判据逐例比对」自检；
 * ②全仓「优化前/优化后逐目标判定明细」diff（组件 71 + 模块 126 全条一致）；
 * ③既有的正/反向自检与基线集合断言原样保留。
 */
interface ScanIndex {
  /** 标签名 token → 出现该标签的消费方绝对路径 */
  readonly tags: Map<string, string[]>
  /** import 路径末段（同时登记含 `.ts` 与去掉 `.ts` 两种键）→ 消费方绝对路径 */
  readonly imports: Map<string, string[]>
  /** `htmlRendererRegistry.ts`（componentType 动态 import 入口，按文件名整体兜底） */
  readonly registries: { path: string; code: string }[]
}

const TAG_RE = /<([\w-]+)/g
const IMPORT_TAIL_RE = /['"][^'"]*\/([^'"/]*)['"]/g

function pushHit(map: Map<string, string[]>, key: string, file: string): void {
  const arr = map.get(key)
  // 同一文件的多次命中必然连续（按文件逐个入表）→ 比尾即可去重
  if (arr === undefined) map.set(key, [file])
  else if (arr[arr.length - 1] !== file) arr.push(file)
}

function indexOne(index: ScanIndex, file: string, code: string): void {
  let m: RegExpExecArray | null
  TAG_RE.lastIndex = 0
  while ((m = TAG_RE.exec(code)) !== null) pushHit(index.tags, m[1], file)
  IMPORT_TAIL_RE.lastIndex = 0
  while ((m = IMPORT_TAIL_RE.exec(code)) !== null) {
    const tail = m[1]
    pushHit(index.imports, tail, file)
    if (tail.endsWith('.ts')) pushHit(index.imports, tail.slice(0, -3), file)
  }
  if (file.replace(/\\/g, '/').endsWith('htmlRendererRegistry.ts'))
    index.registries.push({ path: file, code })
}

function buildScanIndex(consumers: readonly Consumer[]): ScanIndex {
  const index: ScanIndex = { tags: new Map(), imports: new Map(), registries: [] }
  for (const c of consumers) indexOne(index, c.path, c.code ?? c.text)
  return index
}

/** 全仓候选消费方：`src/**` 的 `.vue`/`.ts`，排除 `__tests__` 与 `components.d.ts` */
const CONSUMER_PATHS = walk(SRC, ['.vue', '.ts']).filter((p) => {
  const n = p.replace(/\\/g, '/')
  return !n.includes('/__tests__/') && !n.endsWith('components.d.ts') && !n.endsWith('.d.ts')
})

const GLOBAL_INDEX: ScanIndex = { tags: new Map(), imports: new Map(), registries: [] }
/**
 * 读盘 + 剥注释 + 入索引一趟走完；**只保留原文**不保留剥注释后的副本
 * （剥注释文本是入索引的中间产物，留着白占 58 MB 且无消费方 —— 唯一读 `text` 的
 * 是下方「内联的不存在组件名在全仓原文里零命中」那条反向自检）。
 */
const CONSUMERS: Consumer[] = CONSUMER_PATHS.map((p) => {
  const text = fs.readFileSync(p, 'utf-8')
  indexOne(GLOBAL_INDEX, p, stripComments(text))
  return { path: p, text }
})

const TARGET_COMPONENTS = SCAN_DIRS.flatMap((d) => walk(d, ['.vue']))
const TARGET_MODULES = SCAN_DIRS.flatMap((d) => walk(d, ['.ts'])).filter(
  (p) => !p.replace(/\\/g, '/').includes('/__tests__/') && !p.endsWith('.spec.ts'),
)

/** 组件的**全部**渲染宿主（标签形式，或被 registry 按 componentType 引用） */
function componentHostsIn(abs: string, index: ScanIndex): string[] {
  const stem = path.basename(abs, '.vue')
  const hits = new Set<string>()
  for (const name of [stem, kebab(stem)]) {
    for (const p of index.tags.get(name) ?? []) if (p !== abs) hits.add(p)
  }
  // htmlRendererRegistry 按 componentType 动态 import → 出现文件名即视为宿主级入口
  for (const r of index.registries) {
    if (r.path !== abs && r.code.includes(stem)) hits.add(r.path)
  }
  return [...hits].sort()
}

/** 组件是否有渲染宿主（标签形式）或被 registry 注册 */
function componentHasHost(abs: string, consumers?: readonly Consumer[]): boolean {
  return componentHostsIn(abs, consumers ? buildScanIndex(consumers) : GLOBAL_INDEX).length > 0
}

function exportedSymbols(src: string): Set<string> {
  const out = new Set<string>()
  for (const m of src.matchAll(
    /export\s+(?:declare\s+)?(?:abstract\s+)?(?:const|let|var|function\*?|async\s+function\*?|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)/g,
  ))
    out.add(m[1])
  return out
}

/**
 * 模块是否有生产消费方（import 路径命中，或导出符号在**未自行声明该符号**的文件里被引用）。
 *
 * 🔴 两条必需的排除，缺一即假阴性（孤儿被漏判）：
 * 1. **剥注释**：说明文字里提到符号名不是引用（实测 `blockColumnConfigs.ts` 注释提到
 *    `NON_AMOUNT_NUMBER_COLUMNS`）。
 * 2. **只按 import 路径判定，不做符号级匹配**。三轮实测证明符号匹配对本场景
 *    只产生假阴性（把孤儿漏判成有消费方）：
 *      - `CONVERGENCE_TARGET` 在 4 个文件里**各自** `export const`（收敛锚点范式）；
 *      - `E1RestrictedRowLike` 在 `e1NoteSectionMap.ts` 独立 `export interface` 一份；
 *      - `BlockKey` 是通用类型名，`useB22CDesignEffectiveness.ts` 导出它，
 *        而消费它的 `.vue` **只 import 不 export** → 「跳过自行导出者」也救不了。
 *    而在 TS/Vue 里跨文件消费一个模块**必须**先 import 它（无隐式全局），
 *    故 import 路径命中就是充分且必要判据，符号匹配纯属噪声来源。
 *
 * import 形态覆盖：静态 `from '...'` / `import type` / 动态 `import('...')` /
 * `export ... from '...'` 再导出 / `@/` 别名 —— 全部落在「引号内以 `/stem` 结尾」
 * 这一个形状上（可带 `.ts` 后缀）。
 */
function moduleConsumersIn(abs: string, index: ScanIndex): string[] {
  const stem = path.basename(abs, '.ts')
  return (index.imports.get(stem) ?? []).filter((p) => p !== abs).sort()
}

function moduleHasConsumer(abs: string, consumers?: readonly Consumer[]): boolean {
  return moduleConsumersIn(abs, consumers ? buildScanIndex(consumers) : GLOBAL_INDEX).length > 0
}

function baselineFiles(list: readonly OrphanEntry[]): Set<string> {
  return new Set(list.map((e) => e.path))
}

describe('自检：扫描面与判据非空（解析失效必须打红而非空转）', () => {
  it('REPO_ROOT 与扫描目录真实存在（路径解析失效必须打红，不得静默空扫）', () => {
    // 🔴 fail-closed 支点：路径错时 walk() 返回 []，下游全部「零孤儿」= 假绿。
    for (const s of SENTINELS) expect(fs.existsSync(path.join(REPO_ROOT, s)), s).toBe(true)
    for (const d of SCAN_DIRS) expect(fs.existsSync(d), d).toBe(true)
    // registry 是 Req 2.3 的宿主级入口判据来源，路径写错会让「registry 注册即算有宿主」静默失效
    expect(fs.existsSync(path.join(WP, 'htmlRendererRegistry.ts'))).toBe(true)
  })

  it('候选消费方与被扫目标数量锚定', () => {
    expect(CONSUMERS.length).toBeGreaterThan(500)
    expect(TARGET_COMPONENTS.length).toBeGreaterThan(50)
    expect(TARGET_MODULES.length).toBeGreaterThan(50)
  })

  it('倒排索引非空且含 registry 入口（索引构建失效必须打红，不得让全体目标变孤儿）', () => {
    // 🔴 fail-closed 支点之二：索引为空时**所有**目标都会被判孤儿 → Property 4 会大面积打红，
    //    但那时失败信息会指向「几十个组件突然没宿主」而非真因，故在这里先把真因钉死。
    expect(GLOBAL_INDEX.tags.size).toBeGreaterThan(500)
    expect(GLOBAL_INDEX.imports.size).toBeGreaterThan(500)
    expect(GLOBAL_INDEX.registries.length).toBe(1)
    expect(GLOBAL_INDEX.registries[0].path.replace(/\\/g, '/')).toMatch(
      /components\/workpaper\/htmlRendererRegistry\.ts$/,
    )
  })

  it('被扫目标名全是纯标识符（保证「token 全等」与旧「正则负向断言」等价）', () => {
    // 旧判据 `new RegExp('<' + stem + '(?![\\w-])')` 未转义 stem —— 只要出现一个含
    // 正则元字符（`.` `+` `(` 等）的文件名，旧判据就是通配匹配、新判据是全等 → 会分叉。
    // 全域文件名都是纯标识符时两者严格等价，故把这个前提显式钉住。
    const bad: string[] = []
    for (const p of TARGET_COMPONENTS) {
      const stem = path.basename(p, '.vue')
      if (!/^[A-Za-z][\w-]*$/.test(stem)) bad.push(rel(p))
    }
    for (const p of TARGET_MODULES) {
      const stem = path.basename(p, '.ts')
      if (!/^[A-Za-z][\w-]*$/.test(stem)) bad.push(rel(p))
    }
    expect(bad, `以下目标文件名含正则元字符，倒排索引的「全等」判据与旧正则会分叉：\n${bad.join('\n')}`).toEqual([])
  })

  it('等价性锁：倒排索引判定与「逐目标正则」判定在全部边界形态上逐例一致', () => {
    // 🔴 这条是本次性能优化的**语义护栏**：把改造前的判据（逐目标正则）当参照实现，
    //    对涵盖全部已知边界形态的内联语料逐例比对。任何一天有人「顺手改」抽取正则，
    //    只要判定发生偏移，这条立刻打红 —— 不必等到全仓明细 diff。
    const legacyComponent = (stem: string, code: string): boolean =>
      new RegExp(`<${stem}(?![\\w-])`).test(code) ||
      new RegExp(`<${kebab(stem)}(?![\\w-])`).test(code)
    const legacyModule = (stem: string, code: string): boolean =>
      new RegExp(
        `['"][^'"]*\\/${stem}(?:\\.ts)?['"]|['"]\\.\\/${stem}(?:\\.ts)?['"]`,
      ).test(code)

    const componentCases: string[] = [
      '<RealHost />',
      '<RealHost/>',
      '<RealHost>x</RealHost>',
      '<RealHost :a="1" @b="c" />',
      '<real-host />',
      '<real-host-old />',
      '<RealHostREMOVED />',
      '<RealHostExtra/>',
      '< RealHost />',
      '<<RealHost />',
      '<a><RealHost /></a>',
      '<RealHost.Sub />',
      'const s = "<RealHost />"',
      'x < RealHost > y',
      '<template><component :is="RealHost" /></template>',
    ]
    for (const code of componentCases) {
      const viaIndex = componentHasHost(path.join(WP, 'confirmation/RealHost.vue'), [
        { path: 'probe.vue', text: code, code },
      ])
      expect(viaIndex, `组件判定分叉：${code}`).toBe(legacyComponent('RealHost', code))
    }

    const moduleCases: string[] = [
      "import x from './realModule'",
      'import x from "./realModule"',
      "import x from '../a/realModule'",
      "import x from '@/components/realModule'",
      "import x from './realModule.ts'",
      "import type { A } from './realModule'",
      "export { a } from './realModule'",
      "export * from './realModule'",
      "const m = await import('./realModule')",
      "import x from './realModuleExtra'",
      "import x from './prefixRealModule'",
      "import x from './realModule/index'",
      "import x from 'realModule'",
      'const s = `./realModule`',
      "const s = 'see \"/realModule\" here'",
      "const a = 'x'; const b = 'y/realModule'",
      "const a = 'q/other'; const b = 'q/realModule'",
    ]
    for (const code of moduleCases) {
      const viaIndex = moduleHasConsumer(path.join(WP, 'confirmation/realModule.ts'), [
        { path: 'probe.ts', text: code, code },
      ])
      expect(viaIndex, `模块判定分叉：${code}`).toBe(legacyModule('realModule', code))
    }
    // 语料非退化自检：两侧都必须既有 true 也有 false，否则这条断言是空转
    expect(componentCases.some((c) => legacyComponent('RealHost', c))).toBe(true)
    expect(componentCases.some((c) => !legacyComponent('RealHost', c))).toBe(true)
    expect(moduleCases.some((c) => legacyModule('realModule', c))).toBe(true)
    expect(moduleCases.some((c) => !legacyModule('realModule', c))).toBe(true)
  })

  it('反向自检：stripComments 剥各类注释，且不被引号内的斜杠/星号骗到（内联 fixture）', () => {
    // 🔴 用**内联 fixture** 而非真实文件的注释：真实注释日后可能被清理 → 自检空转。
    //    `accept="image/*"` 这一条是 memory 已登记的真实事故（裸正则把它当块注释起点，
    //    一路吞到几千字符后的 `*/`，让 2 个真实宿主静默逃出扫描面而守卫仍绿）。
    const fixture = [
      '<template>',
      '  <!-- 注释里提到 <OrphanProbeWidget /> 与 NON_AMOUNT_NUMBER_COLUMNS -->',
      '  <input accept="image/*" />',
      '  <a href="https://example.com/x" />',
      '  <RealHost :a="1" />',
      '</template>',
      "<script setup lang=\"ts\">",
      '/* 块注释：import x from "./orphanProbeModule" */',
      "// 行注释：import y from './orphanProbeModule'",
      'const s = "a/*b*/c//d"',
      "import z from './realModule'",
      '</script>',
    ].join('\n')
    const out = stripComments(fixture)
    // 注释里的内容全部消失
    expect(out).not.toContain('OrphanProbeWidget')
    expect(out).not.toContain('NON_AMOUNT_NUMBER_COLUMNS')
    expect(out).not.toContain('orphanProbeModule')
    // 引号内内容原样保留（证明没被块注释起点吞掉后续几千字符）
    expect(out).toContain('accept="image/*"')
    expect(out).toContain('https://example.com/x')
    expect(out).toContain('"a/*b*/c//d"')
    // 真实代码与调用点还在
    expect(out).toContain('<RealHost')
    expect(out).toContain("'./realModule'")
  })

  it('反向自检：标签存在性带标签名边界（改名/加后缀不算「已渲染」）', () => {
    // 🔴 `toContain('<Foo')` 会被 `<FooREMOVED` 骗过 —— 「组件已删除」这个最核心的变异
    //    会静默逃逸（前序变异检验实测抓到）。componentHasHost 用 `<Foo(?![\w-])` 负向断言边界。
    const fake = path.join(WP, 'confirmation/RealHost.vue')
    const c = (text: string) => [{ path: 'x.vue', text, code: text }]
    expect(componentHasHost(fake, c('<RealHost :a="1" />'))).toBe(true)
    expect(componentHasHost(fake, c('<RealHost/>'))).toBe(true)
    expect(componentHasHost(fake, c('<real-host />'))).toBe(true)
    // 下面三种都是「实际没渲染」，子串匹配会误判为已渲染
    expect(componentHasHost(fake, c('<RealHostREMOVED :a="1" />'))).toBe(false)
    expect(componentHasHost(fake, c('<RealHostExtra />'))).toBe(false)
    expect(componentHasHost(fake, c('<real-host-old />'))).toBe(false)
  })

  it('已知有宿主的组件被判为有宿主（正向自检，防判据恒假）', () => {
    // GtConfirmationSummary 被 htmlRendererRegistry 注册；CrossWorkpaperNav 本 spec 刚接上宿主
    const summary = TARGET_COMPONENTS.find((p) => p.endsWith('GtConfirmationSummary.vue'))
    const nav = TARGET_COMPONENTS.find((p) => p.endsWith('CrossWorkpaperNav.vue'))
    expect(summary, 'GtConfirmationSummary.vue 应存在').toBeTruthy()
    expect(nav, 'CrossWorkpaperNav.vue 应存在').toBeTruthy()
    expect(componentHasHost(summary!)).toBe(true)
    expect(componentHasHost(nav!)).toBe(true)
  })

  it('已知有消费方的模块被判为有消费方（正向自检）', () => {
    const spec = TARGET_MODULES.find((p) => p.endsWith('confirmationColumnSpec.ts'))
    expect(spec).toBeTruthy()
    expect(moduleHasConsumer(spec!)).toBe(true)
  })
})

describe('Property 4: 函证域无未登记的无宿主组件（Validates 2.1, 2.2, 2.3, 2.4）', () => {
  it('每个 .vue 都有渲染宿主，或已在组件基线内登记', () => {
    const allowed = baselineFiles(KNOWN_ORPHAN_COMPONENTS)
    const found = TARGET_COMPONENTS.filter((p) => !componentHasHost(p)).map(rel)
    const unexpected = found.filter((f) => !allowed.has(f))
    expect(
      unexpected,
      `以下组件全仓零渲染宿主（用户不可达）。要么接线，要么写进 orphanHostBaseline.KNOWN_ORPHAN_COMPONENTS 并说明 owner/reason：\n${unexpected.join('\n')}`,
    ).toEqual([])
  })

  /**
   * 🔴 Req 2.4 目标是「组件基线为空数组」，本 spec **未达成**（实测函证域仍有 2 个孤儿组件）。
   *
   * 不把断言写成 `toEqual([])` 的理由：那会让守卫长期红着 = 噪声，且掩盖真正的新增孤儿。
   * 改为**集合精确等于**这 2 条已知遗留 + 下方「条目数不得增长」封顶 2：
   *   · 新增任何孤儿组件 → 集合断言 + 封顶断言双双打红；
   *   · 这 2 条任一被接线 → stale 断言打红，逼着把它移出并把上限减一；
   *   · 想靠往基线加条目绕过 → 集合断言打红。
   * 两条的归属都在别的 spec（接线需先定「E0 下区 vs 七枢纽共享下区」的边界），
   * 故本 spec 只登记不接线，差距如实暴露在这条断言的注释与失败信息里。
   */
  it('组件基线只含 2 条已知跨 spec 遗留（Req 2.4 目标为空，当前差距被精确钉死）', () => {
    expect(new Set(baselineFiles(KNOWN_ORPHAN_COMPONENTS))).toEqual(
      new Set([
        'confirmation/E0SummaryLowerZone.vue',
        'confirmation/e0-send-list/SendListConsistencyPanel.vue',
      ]),
    )
    // 每条都必须归属一个别的 spec（禁止把本 spec 自己的活登记进来绕过 Req 2.4）
    for (const e of KNOWN_ORPHAN_COMPONENTS) {
      expect(
        ['e0-confirmation-completion', 'e0-send-list-dedicated-components'],
        `${e.path} 的 owner 不在已裁决的两个 E0 spec 内：${e.owner}`,
      ).toContain(e.owner)
    }
  })

  it('CrossWorkpaperNav.vue 已不在组件基线内（本 spec 已接线）', () => {
    const files = baselineFiles(KNOWN_ORPHAN_COMPONENTS)
    expect([...files].some((f) => f.endsWith('CrossWorkpaperNav.vue'))).toBe(false)
  })

  it('每个 .ts 都有生产消费方，或已在模块基线内登记', () => {
    const allowed = baselineFiles(KNOWN_ORPHAN_MODULES)
    const found = TARGET_MODULES.filter((p) => !moduleHasConsumer(p)).map(rel)
    const unexpected = found.filter((f) => !allowed.has(f))
    expect(
      unexpected,
      `以下模块零生产消费方。要么接线/删除，要么写进 KNOWN_ORPHAN_MODULES：\n${unexpected.join('\n')}`,
    ).toEqual([])
  })

  it('三个已删的 G0 孤儿 composable 不在基线里（真删除，不是登记豁免）', () => {
    const all = [...baselineFiles(KNOWN_ORPHAN_COMPONENTS), ...baselineFiles(KNOWN_ORPHAN_MODULES)]
    for (const stem of ['useG0DualMode', 'useG0ImportExport', 'useG0ReviewDialogProvide']) {
      expect(
        all.some((f) => f.includes(stem)),
        `${stem} 应已被删除而非登记豁免`,
      ).toBe(false)
    }
  })
})

describe('Property 5: 扫描非恒真 + 基线只许缩短（Validates 2.5, 2.6）', () => {
  it('反向自检：内联的必然不存在的组件名被判为孤儿', () => {
    const fake = path.join(WP, 'confirmation/__NoSuchComponentXyz.vue')
    // 不写盘：直接用替身消费方集合验证判据（零命中 ⇒ 判孤儿）
    const fakeStem = '__NoSuchComponentXyz'
    const hit = CONSUMERS.some((c) => new RegExp(`<${fakeStem}(?![\\w-])`).test(c.text))
    expect(hit).toBe(false)
    expect(componentHasHost(fake, [{ path: 'x', text: '<SomethingElse />' }])).toBe(false)
  })

  it('反向自检：把「被 __tests__ 引用」当消费方会漏判（故必须排除测试目录）', () => {
    const testDirIncluded = CONSUMERS.some((c) => c.path.replace(/\\/g, '/').includes('/__tests__/'))
    expect(testDirIncluded, '候选消费方里不得含 __tests__（否则守卫保护死代码）').toBe(false)
    // 举一个实证：confirmationColumnSourceManifest 有测试消费方但零生产消费方，仍应判孤儿
    const manifest = TARGET_MODULES.find((p) => p.endsWith('confirmationColumnSourceManifest.ts'))
    expect(manifest).toBeTruthy()
    expect(moduleHasConsumer(manifest!)).toBe(false)
  })

  it('反向自检：符号级匹配是假阴性源，判据必须只认 import 路径', () => {
    const target = TARGET_MODULES.find((p) => p.endsWith('blockColumnAmountRegistry.ts'))
    expect(target, 'blockColumnAmountRegistry.ts 应存在').toBeTruthy()

    // 成因 1：注释里提到符号名。
    // 🔴 核心判据用**内联 fixture**，不依赖真实文件的注释（它日后可能被清理 → 自检空转）。
    const syms = [...exportedSymbols(fs.readFileSync(target!, 'utf-8'))]
    expect(syms.length, '未抽出任何导出符号 → 正则失效').toBeGreaterThan(0)
    const fixtureComment = `/**\n * 登记理由见 ${syms[0]}（本行是注释，不是引用）\n */\nexport const X = 1\n`
    const naiveSymbolMatch = (consumerSrc: string) =>
      syms.some((sym) => new RegExp(`\\b${sym}\\b`).test(consumerSrc))
    expect(naiveSymbolMatch(fixtureComment), '朴素符号匹配会误判（这正是废弃它的理由）').toBe(true)
    // 现行判据（剥注释 + 只认 import 路径）→ 正确判为孤儿
    expect(
      moduleHasConsumer(target!, [
        { path: 'x.ts', text: fixtureComment, code: stripComments(fixtureComment) },
      ]),
      '注释里提到符号名不算引用',
    ).toBe(false)

    // 现场实证（同族真实形态）：blockColumnConfigs.ts 里没有 import 本 registry → 判孤儿
    const configs = fs.readFileSync(
      path.join(WP, 'confirmation/alternativeD05/blockColumnConfigs.ts'),
      'utf-8',
    )
    expect(configs.length, '未读到 blockColumnConfigs.ts → 路径失效').toBeGreaterThan(500)
    expect(moduleHasConsumer(target!, [{ path: 'x', text: configs, code: stripComments(configs) }])).toBe(
      false,
    )
    // 真 import 则判为有消费方（防判据恒假）
    const real = "import { isNonAmountNumberColumn } from './blockColumnAmountRegistry'\n"
    expect(moduleHasConsumer(target!, [{ path: 'real.ts', text: real, code: real }])).toBe(true)
  })

  it('反向自检：平台有意的多副本同名导出不算引用（收敛锚点范式）', () => {
    const k0 = TARGET_MODULES.find((p) => p.endsWith('k0LowerZoneSpec.ts'))
    expect(k0, 'k0LowerZoneSpec.ts 应存在').toBeTruthy()
    // CONVERGENCE_TARGET 在 4 个矩阵/下区副本里各自 export 一份（memory 已登记为范式，勿统一）
    const twin = "export const CONVERGENCE_TARGET = 'confirmation-summary-matrix-convergence'\n"
    expect(
      moduleHasConsumer(k0!, [{ path: 'twin.ts', text: twin, code: twin }]),
      '同名 export ≠ 引用',
    ).toBe(false)
    // 通用类型名撞车同样不算：BlockKey 由 useB22CDesignEffectiveness.ts 导出，
    // 消费它的 .vue 只 import 不 export → 「跳过自行导出者」这类补丁救不回来，
    // 只有「只认 import 路径」才不误判。
    const generic = 'function f(k: BlockKey) { return k }\n'
    const reg = TARGET_MODULES.find((p) => p.endsWith('blockColumnAmountRegistry.ts'))
    expect(exportedSymbols(fs.readFileSync(reg!, 'utf-8')).has('BlockKey')).toBe(true)
    expect(
      moduleHasConsumer(reg!, [{ path: 'g.vue', text: generic, code: generic }]),
      '通用类型名同名不算引用',
    ).toBe(false)
  })

  it('每条基线的 owner 非空、reason ≥8 字且不含占位词', () => {
    for (const e of [...KNOWN_ORPHAN_COMPONENTS, ...KNOWN_ORPHAN_MODULES]) {
      expect(e.owner.trim().length, `${e.path} 缺 owner`).toBeGreaterThan(0)
      expect(e.reason.replace(/\s/g, '').length, `${e.path} 的 reason 过短`).toBeGreaterThanOrEqual(8)
      for (const bad of ['待处理', 'TODO', '待补充', '暂时']) {
        expect(e.reason.includes(bad), `${e.path} 的 reason 是占位词「${bad}」`).toBe(false)
      }
    }
  })

  it('基线内每条都指向真实存在的文件（防登记漂移成噪声）', () => {
    for (const e of [...KNOWN_ORPHAN_COMPONENTS, ...KNOWN_ORPHAN_MODULES]) {
      expect(fs.existsSync(path.join(WP, e.path)), `基线条目不存在：${e.path}`).toBe(true)
    }
  })

  it('基线内每条**当前确实仍是孤儿**（已接线/已删除必须移出，防常量变死代码）', () => {
    const stale: string[] = []
    for (const e of KNOWN_ORPHAN_COMPONENTS) {
      if (componentHasHost(path.join(WP, e.path))) stale.push(e.path)
    }
    for (const e of KNOWN_ORPHAN_MODULES) {
      if (moduleHasConsumer(path.join(WP, e.path))) stale.push(e.path)
    }
    expect(
      stale,
      `以下条目已有消费方/宿主，应从基线移出（R2.6 只许缩短）：\n${stale.join('\n')}`,
    ).toEqual([])
  })

  it('基线无重复条目', () => {
    const all = [...KNOWN_ORPHAN_COMPONENTS, ...KNOWN_ORPHAN_MODULES].map((e) => e.path)
    expect(new Set(all).size).toBe(all.length)
  })

  /**
   * 🔴 「只许缩短」的最后一把锁（R2.6）。
   *
   * 上面三条只保证：新孤儿会打红（子集断言）、已接线的必须移出（stale 断言）。
   * 但它们都能被**往基线里再加一条**绕过 —— 那正是 R2.6 要禁的动作。
   * 故这里对条目数封顶：接线/删除一个就把上限减一，**永远不许调高**。
   *
   * 当前值来自实测（非立项估计）：组件 2 / 模块 23。
   * 🔴 模块侧只有 K0/L0 两个 ImportExport 包装是孤儿 —— requirements.md「范围外」并列的
   *    `useH0ImportExport` 实测被 `GtConfirmationAlternativeH05.vue` 真实 import，不是孤儿。
   */
  it('基线条目数不得增长（接线或删除后必须同步下调上限）', () => {
    expect(
      KNOWN_ORPHAN_COMPONENTS.length,
      '组件基线只许缩短：新增无宿主组件必须接线或删除，不许往基线里加条目',
    ).toBeLessThanOrEqual(2)
    expect(
      KNOWN_ORPHAN_MODULES.length,
      '模块基线只许缩短：新增无消费方模块必须接线或删除，不许往基线里加条目',
    ).toBeLessThanOrEqual(23)
  })
})
