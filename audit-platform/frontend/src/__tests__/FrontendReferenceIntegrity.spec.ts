/**
 * 前端引用完整性守卫 —— 抓「引用了不存在的目标」这一整类
 *
 * ## 它防的是什么
 *
 * 两个真实缺陷，形态相同、都通过了全部既有检查：
 *
 * **① 路由孤儿（AC 1.5）**：`DshPanel.openInNewWindow()` 执行
 * `window.open('/ai-chat')`，而 commit 55c5e0fe 的 `router/index.ts` 里
 * `/ai-chat` 的 path 声明数为 **0**（原文还写着 "Do NOT re-add these routes"）。
 * 点「新窗口打开」落到 404。Task 9 标 `[x]` 且 Validates 列了 1.5，
 * Task 34 的 Playwright 也声称覆盖 new-window ——
 * 但那条 e2e 判据是 `expect(newPage.url()).toContain('/ai-chat')`，
 * 而 Vue Router 的 catch-all **不改变 URL** ⇒ 打开 404 时该断言照样通过。
 *
 * **② 模块孤儿（import 深度错）**：`GtConfirmationAlternativeF05.vue` 写
 * `'../../composables/f0MasterLabels'`（真源在 `../composables/`）。
 * 后果是**整个前端生产构建挂掉**（rollup 解析整张模块图，一处失败即终止），
 * 于是所有人都无法用 `vite build` 校验自己的改动。实测同批共 **7 处**，
 * 而 rollup 一次只报一个，逐个 build 试错要跑 7 轮。
 *
 * ## 为什么既有检查全都看不见
 *
 * `window.open('/x')` 与 import specifier 都是**字符串字面量** ——
 * Volar / vue-tsc / eslint / vitest 都不校验它指向的目标是否存在。
 * 唯一会报的是 `vite build`，而它①没人跑②一次只报一条③本机默认堆会 OOM。
 * 这与 memory 记的「Vue 传不存在的 prop = 静默失效，四层全查不出」同族。
 *
 * ## 判据
 *
 * §1 模块引用：全仓生产源码的相对/别名 import 必须可解析。
 *    当前有一批**目标文件已被删除**的死代码（见 `KNOWN_DEAD_MODULE_FILES`），
 *    它们登记在册且**只减不增**；同时断言它们确实零生产消费方 ——
 *    豁免的语义是「这个文件是死代码待删」，不是「这个错可以接受」。
 * §2 路由导航：写死的站内导航目标必须匹配到**非 catch-all** 的声明路由。
 *
 * 两节都带反向自检（判据自己不能恒真），并断言扫描面不空洞。
 *
 * Feature: dsh-agent-panel-integration / P0 收口
 * Validates: Requirements 1.5, 1.9
 */
import { describe, it, expect } from 'vitest'
import { resolve } from 'path'
import {
  FRONTEND_SRC,
  walkSourceFiles,
  readSource,
  isTestFile,
  findBrokenModuleReferences,
  stripJsComments,
  stripHtmlComments,
  parseDeclaredRoutes,
  countNestedChildren,
  parseNavigationTargets,
  pathMatchesDeclaredRoute,
  toSrcRelative,
  moduleExists,
  CATCH_ALL_PATTERN,
} from './_helpers/frontendSourceScan'

// ---------------------------------------------------------------------------
// 已登记的死代码文件（目标 import 已被删除 ⇒ 这些文件加载即报错，不可能在生产工作）
//
// 语义：待清理，**不是**「这个错可以接受」。
// 清单只减不增；§1 另有一条断言它们确实零生产消费方 ——
// 一旦有人给它们接上消费方，必须先修 import，不能继续躺在这里。
// ---------------------------------------------------------------------------

const KNOWN_DEAD_MODULE_FILES: ReadonlyArray<{ file: string; reason: string }> = [
  {
    file: 'components/ai/index.js',
    reason: '旧 AI barrel，导出的 7 个组件文件均已删除（含本 spec 删掉的 AIChatPanel.vue）；零生产消费方',
  },
  {
    file: 'components/ai/AIInsightsDashboard.vue',
    reason: '旧 AI 组件，import 的 @/api 目录不存在（加载即报错）；唯一引用方是死 barrel 与自动生成的 components.d.ts',
  },
  {
    file: 'components/ai/ConfirmationAIAssistant.vue',
    reason: '旧 AI 组件，import 的 @/api 目录不存在（加载即报错）；唯一引用方是死 barrel 与自动生成的 components.d.ts',
  },
  {
    file: 'components/ai/NLCommandInput.vue',
    reason: '旧 AI 组件，import 的 @/api 目录不存在（加载即报错）；唯一引用方是死 barrel 与自动生成的 components.d.ts',
  },
  {
    file: 'components/ai/WorkpaperAIFill.vue',
    reason: '旧 AI 组件，import 的 @/api 目录不存在（加载即报错）；唯一引用方是死 barrel 与自动生成的 components.d.ts',
  },
  {
    file: 'views/ai/AIWorkpaperView.vue',
    reason: 'Phase 11 已移除其路由，import 的 AIWorkpaperFill.vue 也已删除；router 里只剩注释提及',
  },
]

const DEAD_FILE_SET = new Set(KNOWN_DEAD_MODULE_FILES.map((d) => d.file))

// ---------------------------------------------------------------------------
// 扫描面（模块级计算一次）
// ---------------------------------------------------------------------------

const ALL_SOURCE_FILES = walkSourceFiles(FRONTEND_SRC).filter((f) => !isTestFile(f))
const ROUTER_FILE = resolve(FRONTEND_SRC, 'router/index.ts')
const ROUTER_SOURCE = readSource(ROUTER_FILE)
const DECLARED_ROUTES = parseDeclaredRoutes(ROUTER_SOURCE)

// ---------------------------------------------------------------------------

describe('前端引用完整性 · 判据自身不空洞', () => {
  it('扫描面覆盖足够多的生产源文件', () => {
    // 没有这条，`walkSourceFiles` 一旦扫空（路径算错、跳过规则写宽），
    // 整个守卫会静默变成 0 条断言全绿。
    expect(ALL_SOURCE_FILES.length).toBeGreaterThan(2000)
    expect(ALL_SOURCE_FILES.every((f) => !isTestFile(f))).toBe(true)
  })

  it('路由声明集合非空且形态可信', () => {
    expect(DECLARED_ROUTES.length).toBeGreaterThan(100)
    // 每条 full 都以 / 开头（拼接逻辑生效的最低要求）
    expect(DECLARED_ROUTES.every((r) => r.full.startsWith('/'))).toBe(true)
    // catch-all 必须存在（它是本守卫要排除的对象；不存在说明解析出错）
    expect(DECLARED_ROUTES.some((r) => CATCH_ALL_PATTERN.test(r.full))).toBe(true)
  })

  it('路由结构假设仍成立：单层嵌套', () => {
    // `parseDeclaredRoutes` 把「不以 / 开头的子路由」直接拼到 '/' 下面，
    // 这只在「唯一的 children 属于 '/' 路由」时正确。
    // 一旦出现第二层嵌套，可达集合会算错 —— 必须打红而不是静默变宽。
    expect(countNestedChildren(ROUTER_SOURCE)).toBe(1)
  })
})

describe('§1 模块引用完整性', () => {
  const broken = findBrokenModuleReferences(ALL_SOURCE_FILES)

  it('不存在未登记的坏 import', () => {
    const unexpected = broken.filter((b) => !DEAD_FILE_SET.has(b.file))
    const detail = unexpected.map((b) => `${b.file}:${b.line} -> ${b.specifier}`).join('\n')
    expect(
      unexpected,
      `发现解析不到目标的 import（会让 vite build 整体失败）：\n${detail}\n` +
        `修法：核对真源实际位置后改正相对深度，跨 3 级以上建议用 @/ 别名。`,
    ).toEqual([])
  })

  it('已登记的死代码文件确实零**活**消费方', () => {
    // 豁免桶不是垃圾桶：如果死文件被**活代码**引用了，就必须修它的 import，
    // 而不是继续留在清单里 —— 那会让一个加载即崩的模块进入运行时。
    //
    // 🔴 「活」的定义要排除两类，否则判据会自指而恒红：
    //   ① 死清单成员之间的互相引用（死 barrel 引用死组件是同一坨死代码的内部结构）
    //   ② `components.d.ts` —— unplugin-vue-components 自动生成的全局组件声明，
    //      是工具产物不是人写的消费方（它会把 src 下所有 .vue 都列进去）
    const referenced: string[] = []
    for (const { file } of KNOWN_DEAD_MODULE_FILES) {
      const abs = resolve(FRONTEND_SRC, file)
      const absNoExt = abs.replace(/\\/g, '/').replace(/\.\w+$/, '')
      for (const candidate of ALL_SOURCE_FILES) {
        if (candidate === abs) continue
        const candidateRel = toSrcRelative(candidate)
        if (candidateRel === 'components.d.ts') continue
        if (DEAD_FILE_SET.has(candidateRel)) continue // 死代码内部互引不算复活

        const code = stripJsComments(readSource(candidate))
        for (const m of code.matchAll(/(?:from\s*|import\s*\(\s*|import\s*)['"]([^'"]+)['"]/g)) {
          const spec = m[1]
          if (!spec.startsWith('.') && !spec.startsWith('@/')) continue
          const target = (
            spec.startsWith('@/')
              ? resolve(FRONTEND_SRC, spec.slice(2))
              : resolve(candidate, '..', spec)
          )
            .replace(/\\/g, '/')
            .replace(/\.\w+$/, '')
          if (target === absNoExt) {
            referenced.push(`${candidateRel}:${code.slice(0, m.index).split('\n').length} -> ${file}`)
          }
        }
      }
    }
    expect(
      referenced,
      `死代码文件被活代码引用，须先修其 import 再决定去留：\n${referenced.join('\n')}`,
    ).toEqual([])
  })

  it('判据自检：死清单本身不空洞，且每条都给了原因', () => {
    // 没有这条，清单被清空后 §1 第一条判据会退化成「零坏 import」的空断言 ——
    // 而实际上那 6 个文件仍在仓库里带着坏 import。
    expect(KNOWN_DEAD_MODULE_FILES.length).toBeGreaterThan(0)
    expect(KNOWN_DEAD_MODULE_FILES.every((d) => d.reason.trim().length > 10)).toBe(true)
    // 清单里的每个文件必须**确实**有坏 import（否则它不该在豁免桶里）
    const brokenFiles = new Set(broken.map((b) => b.file))
    const clean = KNOWN_DEAD_MODULE_FILES.filter((d) => !brokenFiles.has(d.file)).map((d) => d.file)
    expect(
      clean,
      `以下文件已无坏 import，应从 KNOWN_DEAD_MODULE_FILES 移除（清单只减不增）：\n${clean.join('\n')}`,
    ).toEqual([])
  })

  it('判据自检：坏 import 必须被检出，好 import 必须放过', () => {
    // 用真实存在的文件当载体，只验解析函数的判断力
    const realFile = resolve(FRONTEND_SRC, 'router/index.ts')
    expect(moduleExists(realFile, './index')).toBe(true) // router/index.ts 自身
    expect(moduleExists(realFile, '@/components/ai/DshPanel.vue')).toBe(true)
    expect(moduleExists(realFile, './__definitely_not_here__')).toBe(false)
    expect(moduleExists(realFile, '@/components/__definitely_not_here__.vue')).toBe(false)
    // vite query 后缀必须被剥掉后再判
    expect(moduleExists(realFile, '@/components/ai/DshPanel.vue?raw')).toBe(true)
    // 裸包名与动态拼接不在职责内，一律放过
    expect(moduleExists(realFile, 'vue')).toBe(true)
  })

  it('判据自检：stripJsComments 不得截断含 // 的字符串', () => {
    // 这是本工具最容易出错的一处：用 /\/\/.*$/gm 会把 'https://x' 吃掉，
    // 于是同行后续的 import 消失、扫描结果静默变少。
    const src = `const u = 'https://example.com/a' // 真注释\nimport X from './x'`
    const out = stripJsComments(src)
    expect(out).toContain("'https://example.com/a'")
    expect(out).toContain("import X from './x'")
    expect(out).not.toContain('真注释')
  })
})

describe('§2 路由导航目标可达性（AC 1.5）', () => {
  const targets = ALL_SOURCE_FILES.flatMap((f) => parseNavigationTargets(f, readSource(f)))

  it('扫到的导航目标不空洞', () => {
    expect(targets.length).toBeGreaterThan(5)
  })

  it('所有写死的站内导航目标都能匹配到非 catch-all 路由', () => {
    const unreachable = targets.filter((t) => !pathMatchesDeclaredRoute(t.path, DECLARED_ROUTES))
    const detail = unreachable.map((t) => `${t.file}:${t.line} ${t.via} -> ${t.path}`).join('\n')
    expect(
      unreachable,
      `以下导航目标没有对应的路由声明，用户点击后会落到 404：\n${detail}\n` +
        `注意 Vue Router 的 catch-all 不改变 URL，所以只断言 URL 的测试抓不到这类缺陷。`,
    ).toEqual([])
  })

  it('AC 1.5：新窗口聊天路由 /ai-chat 已注册', () => {
    // 点名判据。上一条通用判据依赖「有人写了 window.open('/ai-chat')」才会覆盖到它；
    // 这条不依赖调用方存在，直接锁住路由本身。
    const hit = DECLARED_ROUTES.filter((r) => r.full === '/ai-chat')
    expect(hit.length, "router/index.ts 必须声明 '/ai-chat'（DshPanel 新窗口按钮的目标）").toBe(1)
  })

  it('判据自检：catch-all 不得参与匹配', () => {
    // 🔴 本守卫的核心。catch-all 若算进可达集合，任何路径都"匹配得上"，
    // 判据恒真 —— 这正是 AC 1.5 那条 e2e 判据失效的同一机制。
    expect(pathMatchesDeclaredRoute('/__definitely_not_a_route__', DECLARED_ROUTES)).toBe(false)
    expect(pathMatchesDeclaredRoute('/a/b/c/d/e/f/g', DECLARED_ROUTES)).toBe(false)
  })

  it('判据自检：动态段匹配任意单段，段数必须相等', () => {
    // 真实存在：'projects/:projectId/workpapers' 与 'projects/:projectId/workpapers/:wpId/edit'
    expect(pathMatchesDeclaredRoute('/projects/abc-123/workpapers', DECLARED_ROUTES)).toBe(true)
    expect(pathMatchesDeclaredRoute('/projects/abc/workpapers/w1/edit', DECLARED_ROUTES)).toBe(true)
    // 段数不等不得匹配（防 startsWith 式宽判据）
    expect(pathMatchesDeclaredRoute('/projects/abc/workpapers/extra/deep/nope', DECLARED_ROUTES)).toBe(
      false,
    )
  })

  it('判据自检：导航目标抽取覆盖四种形态且忽略注释', () => {
    const synthetic = `
      <template>
        <router-link to="/real-a">A</router-link>
        <!-- <router-link to="/commented-out">X</router-link> -->
      </template>
      <script setup lang="ts">
      // window.open('/also-commented')
      function go() {
        window.open('/real-b', '_blank')
        router.push('/real-c')
        router.replace('/real-d?x=1#y')
      }
      </script>
    `
    const found = parseNavigationTargets(resolve(FRONTEND_SRC, 'fake.vue'), synthetic).map(
      (t) => t.path,
    )
    expect(found).toContain('/real-a')
    expect(found).toContain('/real-b')
    expect(found).toContain('/real-c')
    expect(found).toContain('/real-d') // query/hash 已剥
    expect(found).not.toContain('/commented-out')
    expect(found).not.toContain('/also-commented')
  })

  it('判据自检：stripHtmlComments 只吃注释', () => {
    const out = stripHtmlComments('<a to="/keep" /><!-- <a to="/drop" /> -->')
    expect(out).toContain('/keep')
    expect(out).not.toContain('/drop')
  })
})
