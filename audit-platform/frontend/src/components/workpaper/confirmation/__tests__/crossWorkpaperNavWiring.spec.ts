/**
 * crossWorkpaperNavWiring.spec.ts — 跨表导航条「接入渲染宿主」守卫
 *
 * spec: confirmation-orphan-and-amount-format-closure
 *   Property 1（导航条有渲染宿主且 prop 名合法）
 *   Property 2（点击不再被 exists 门挡住 + 定位值取主码）
 *   Property 3（完整表格视图与未选中行不渲染导航条）
 *
 * ── 为什么需要本守卫 ────────────────────────────────────────────────────────
 *
 * `CrossWorkpaperNav.vue` 改造前**全仓零渲染宿主**：`buildCrossWorkpaperNavDefs`
 * 有消费方（就是它），但它自己没有任何 `.vue` 渲染 → 整条链是死的，用户点不到。
 * 既有守卫 `coordination/__tests__/crossWorkpaperNav.spec.ts` 的 Property 13 只断言
 * 「该函数有非测试消费方」，因此**放过了**这个缺陷（缺陷模式：链条上游合格、整条链仍是死的）。
 * 本文件补上「递归到渲染宿主为止」的那一环，并锁死接线细节。
 *
 * ── 平台铁律在本文件的落法 ──────────────────────────────────────────────────
 *
 * 1. 读源码前必 `stripComments()`：`CrossWorkpaperNav.vue` 与 `GtConfirmationSummary.vue`
 *    的注释里**逐字写着 `!item.exists` 这个反例**（解释「为什么去掉早退」），不剥注释
 *    Property 2 必假阳性。`stripComments` 自身用**内联 fixture** 反向自检 —— 不依赖真实
 *    文件的注释（它日后可能被清理 → 自检空转）。
 * 2. `<style>` 段整段丢弃再扫，且注释剥离用**带字符串状态的扫描器**而不是裸正则
 *    （裸正则会被 `accept="image/(星号)"` 一类属性骗到几千字符之后的块注释结束符，
 *    memory 已登记该事故；`GtConfirmationSummary.vue` 既有 `accept=".xlsx,..."`
 *    属性又有 `<style scoped>`，两个条件都满足）。
 * 3. 截函数体用**花括号配对**，且先用**圆括号配对**跳过参数列表（参数里的内联类型
 *    字面量 `{...}` 会让「声明后第一个左花括号」定位到错误位置）。
 * 4. fail-closed：每处结构断言前先确认抽取结果非空，解析失效必须打红而不是静默通过。
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CrossWorkpaperNav from '../coordination/CrossWorkpaperNav.vue'
import { locatorOf, type NavLocatorInput } from '../coordination/crossWorkpaperNavLocator'

// ─── REPO_ROOT：哨兵**文件**向上查找（禁写死回退级数） ───────────────────────
// 🔴 同目录既有守卫（h0DictConsumption / g0SharedComponentCoverage / memoTemplatesH0）
//    都是这个范式。写死 `resolve(__dirname, '../../../../../../..')` 曾让整个 spec
//    文件 ENOENT（表现为「文件级失败」而非断言失败，极易被当噪声跳过）。
//    哨兵必须是**具体文件**：写成目录会在 `audit-platform` 层提前停下（那里有个同名空目录）。
const SENTINELS = [
  join('backend', 'app', 'data', 'wp_code_overrides.json'),
  join('audit-platform', 'frontend', 'package.json'),
] as const

function findRepoRoot(start: string): string {
  let dir = resolve(start)
  for (let i = 0; i < 20; i += 1) {
    if (SENTINELS.every((s) => existsSync(join(dir, s)))) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未能从 ${start} 向上找到同时含哨兵文件的仓库根：${SENTINELS.join(' + ')}`)
}

const REPO_ROOT = findRepoRoot(__dirname)
const CONFIRMATION_DIR = join(
  REPO_ROOT,
  'audit-platform',
  'frontend',
  'src',
  'components',
  'workpaper',
  'confirmation',
)
const HOST_VUE = join(CONFIRMATION_DIR, 'GtConfirmationSummary.vue')
const NAV_VUE = join(CONFIRMATION_DIR, 'coordination', 'CrossWorkpaperNav.vue')
const LOCATOR_TS = join(CONFIRMATION_DIR, 'coordination', 'crossWorkpaperNavLocator.ts')

// ─── 源码工具 ────────────────────────────────────────────────────────────────

/** `<style>` 段整段丢弃（CSS 注释与选择器不参与任何断言） */
function stripStyleBlocks(src: string): string {
  return src.replace(/<style[\s\S]*?<\/style>/gi, '')
}

/**
 * 带字符串状态的注释剥离器（HTML 注释 + JS 块注释 + JS 行注释）。
 *
 * 引号内的 `/` 与 `<!--` 不参与判定 → `accept=".xlsx,.xls,.csv"`、URL 里的双斜杠
 * 都不会被误当注释起点。裸正则做不到这一点（memory 已登记两次事故）。
 */
function stripComments(input: string): string {
  const src = stripStyleBlocks(input)
  const n = src.length
  let out = ''
  let i = 0
  while (i < n) {
    const c = src[i]
    if (src.startsWith('<!--', i)) {
      const end = src.indexOf('-->', i + 4)
      i = end === -1 ? n : end + 3
      continue
    }
    if (c === '"' || c === "'" || c === '`') {
      const quote = c
      out += c
      i += 1
      while (i < n) {
        if (src[i] === '\\') {
          out += src[i] + (src[i + 1] ?? '')
          i += 2
          continue
        }
        out += src[i]
        const cur = src[i]
        i += 1
        if (cur === quote) break
      }
      continue
    }
    if (c === '/' && src[i + 1] === '*') {
      const end = src.indexOf('*/', i + 2)
      i = end === -1 ? n : end + 2
      continue
    }
    if (c === '/' && src[i + 1] === '/') {
      const end = src.indexOf('\n', i)
      i = end === -1 ? n : end
      continue
    }
    out += c
    i += 1
  }
  return out
}

/** 从 `from` 起找第一个 `open`，做括号配对，返回其内部内容（不含边界）。找不到返回 `''` */
function sliceBalanced(src: string, from: number, open: string, close: string): string {
  const start = src.indexOf(open, from)
  if (start === -1) return ''
  let depth = 0
  for (let i = start; i < src.length; i += 1) {
    if (src[i] === open) depth += 1
    else if (src[i] === close) {
      depth -= 1
      if (depth === 0) return src.slice(start + 1, i)
    }
  }
  return ''
}

/**
 * 截取 `function name(...)` 的函数体（花括号配对）。
 *
 * 🔴 先用**圆括号配对**跳过整个参数列表再找左花括号 —— 否则 `function f(p: { a: 1 })`
 *    会把参数里的内联类型字面量当成函数体（memory 登记的「低报主因」）。
 */
function extractFunctionBody(src: string, name: string): string {
  const decl = new RegExp(`function\\s+${name}\\s*\\(`).exec(src)
  if (!decl) return ''
  const parenStart = src.indexOf('(', decl.index)
  let depth = 0
  let afterParams = -1
  for (let i = parenStart; i < src.length; i += 1) {
    if (src[i] === '(') depth += 1
    else if (src[i] === ')') {
      depth -= 1
      if (depth === 0) {
        afterParams = i + 1
        break
      }
    }
  }
  if (afterParams === -1) return ''
  return sliceBalanced(src, afterParams, '{', '}')
}

function toKebab(camel: string): string {
  return camel.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)
}

/** 从 `CrossWorkpaperNav.vue` 的 `defineProps<{...}>()` 动态抽合法 prop 名（kebab-case） */
function navPropNames(): Set<string> {
  const src = stripComments(readFileSync(NAV_VUE, 'utf-8'))
  const idx = src.indexOf('defineProps<')
  if (idx === -1) return new Set()
  const block = sliceBalanced(src, idx, '{', '}')
  const names = [...block.matchAll(/^\s*([a-zA-Z][a-zA-Z0-9]*)\??\s*:/gm)].map((m) => m[1])
  return new Set(names.map(toKebab))
}

/**
 * 标签存在性判定：必须带**标签名边界**（下一个字符是空白 / `/` / `>`）。
 *
 * 🔴 变异检验抓出的守卫缺陷：首版用 `toContain('<CrossWorkpaperNav')`，
 *    把标签改名成 `<CrossWorkpaperNavREMOVED`（= 组件没被渲染）时**仍然通过**
 *    ——「删掉渲染块」这个最核心的变异逃过了守卫。子串匹配在标签断言上永远不够。
 */
function tagPresenceRe(tag: string): RegExp {
  return new RegExp(`<${tag}(?=[\\s/>])`)
}

function hasTag(template: string, tag: string): boolean {
  return tagPresenceRe(tag).test(template)
}

/** 取某个标签的调用点原文与其属性名列表（扫到闭合 `>`，跳过引号内内容） */
function extractTagAttrs(template: string, tag: string): { raw: string; attrs: string[] } | null {
  const m = tagPresenceRe(tag).exec(template)
  if (!m) return null
  const start = m.index
  let i = start + tag.length + 1
  let quote: string | null = null
  for (; i < template.length; i += 1) {
    const ch = template[i]
    if (quote) {
      if (ch === quote) quote = null
      continue
    }
    if (ch === '"' || ch === "'") {
      quote = ch
      continue
    }
    if (ch === '>') break
  }
  const raw = template.slice(start, i + 1)
  const attrs = [...raw.matchAll(/(?:^|\s)([@:#]?[A-Za-z][A-Za-z0-9-]*)(?==|[\s/>])/g)].map(
    (m) => m[1],
  )
  return { raw, attrs }
}

/** 属性名归一：剥掉 `:` / `v-bind:` 前缀；返回 null 表示「不是 prop」（指令/保留属性） */
const RESERVED_ATTRS = new Set(['key', 'ref', 'class', 'style', 'id'])

function normalizeAttr(attr: string): string | null {
  if (attr.startsWith('@') || attr.startsWith('#')) return null
  if (attr.startsWith('v-')) return null
  const name = attr.startsWith(':') ? attr.slice(1) : attr
  if (RESERVED_ATTRS.has(name)) return null
  return name
}

const HOST_SRC = stripComments(readFileSync(HOST_VUE, 'utf-8'))
const NAV_SRC = stripComments(readFileSync(NAV_VUE, 'utf-8'))

// ─── 自检：解析器可用（fail-closed 支点） ────────────────────────────────────

describe('自检：源码解析非空（解析失效必须打红而非空转）', () => {
  it('三个源文件存在且剥注释后仍含关键锚点', () => {
    for (const f of [HOST_VUE, NAV_VUE, LOCATOR_TS]) expect(existsSync(f), f).toBe(true)
    expect(HOST_SRC.length).toBeGreaterThan(2000)
    expect(NAV_SRC.length).toBeGreaterThan(500)
    expect(HOST_SRC).toContain('ConfirmationDetail')
    expect(NAV_SRC).toContain('defineProps<')
  })

  it('反向自检：stripComments 剥掉注释里的反例，且不被引号内的斜杠骗到', () => {
    // 🔴 用**内联 fixture** 而非真实文件的注释 —— 真实注释日后可能被清理，自检会空转。
    const fixture = [
      '<template>',
      '  <!-- 改造前 handleNavigate 在 !item.exists 时早退 -->',
      '  <input accept="image/*" />',
      '  <a href="https://example.com/x" />',
      '  <CrossWorkpaperNav :confirm-index="x" />',
      '</template>',
      '<script setup lang="ts">',
      '/* 说明：旧实现写的是 if (!item.exists) return */',
      '// 另一条说明：if (!item.exists) return',
      'const url = "a/*b*/c"',
      'function handleNavigate(item) { emit("navigate-sheet", locatorOf(item)) }',
      '</script>',
      '<style scoped>',
      '/* CSS 注释里也写着 !item.exists 反例 */',
      '.x { color: red; }',
      '</style>',
    ].join('\n')
    const out = stripComments(fixture)
    // 注释里的反例已消失
    expect(out).not.toContain('!item.exists')
    // 引号内的内容原样保留（证明没被块注释剥离吞掉后续几千字符）
    expect(out).toContain('accept="image/*"')
    expect(out).toContain('https://example.com/x')
    expect(out).toContain('"a/*b*/c"')
    // 真实代码与调用点都还在
    expect(out).toContain('emit("navigate-sheet"')
    expect(out).toContain('<CrossWorkpaperNav')
    // `<style>` 整段丢弃
    expect(out).not.toContain('color: red')
  })

  it('反向自检：hasTag 带标签名边界，改名/加后缀的标签不算「已渲染」', () => {
    // 🔴 这条是变异检验（P1-M1）逼出来的：`toContain('<CrossWorkpaperNav')` 会把
    //    `<CrossWorkpaperNavREMOVED`（组件实际没被渲染）判成通过 → 最核心的
    //    「删掉渲染块」变异逃过守卫。标签断言必须带边界。
    expect(hasTag('<CrossWorkpaperNav :a="1" />', 'CrossWorkpaperNav')).toBe(true)
    expect(hasTag('<CrossWorkpaperNav/>', 'CrossWorkpaperNav')).toBe(true)
    expect(hasTag('<CrossWorkpaperNav>', 'CrossWorkpaperNav')).toBe(true)
    expect(hasTag('<CrossWorkpaperNavREMOVED :a="1" />', 'CrossWorkpaperNav')).toBe(false)
    expect(hasTag('<CrossWorkpaperNavExtra />', 'CrossWorkpaperNav')).toBe(false)
    // extractTagAttrs 共用同一判据 → 改名后也定位不到调用点
    expect(extractTagAttrs('<CrossWorkpaperNavREMOVED :a="1" />', 'CrossWorkpaperNav')).toBeNull()
  })

  it('反向自检：extractFunctionBody 用括号配对，不被参数里的内联类型字面量骗到', () => {
    const fixture = 'function f(p: { a: number }) { return p.a }\nfunction g() { return 2 }'
    expect(extractFunctionBody(fixture, 'f').trim()).toBe('return p.a')
    expect(extractFunctionBody(fixture, 'nope')).toBe('')
  })
})

// ─── Property 1: 导航条有渲染宿主且 prop 名合法 ──────────────────────────────

describe('Property 1: 导航条有渲染宿主且 prop 名合法（Validates 1.1, 1.6, 1.7）', () => {
  it('GtConfirmationSummary.vue 是 CrossWorkpaperNav 的渲染宿主（import + 模板标签）', () => {
    // 🔴 「有 import」不等于「有渲染」：本平台已有「8 个组件写好从未渲染」的先例
    //    （E1 循环）→ 两侧都要断言。
    expect(HOST_SRC).toMatch(/import\s+CrossWorkpaperNav\s+from\s+['"]\.\/coordination\/CrossWorkpaperNav\.vue['"]/)
    // 🔴 用带边界的 hasTag，不用 toContain：`<CrossWorkpaperNavREMOVED` 也含该子串
    expect(hasTag(HOST_SRC, 'CrossWorkpaperNav'), '宿主模板未渲染 <CrossWorkpaperNav>').toBe(true)
  })

  it('反向自检：标签断言带边界（改名/加后缀即视为未渲染）', () => {
    expect(hasTag('<CrossWorkpaperNav :confirm-index="x" />', 'CrossWorkpaperNav')).toBe(true)
    expect(hasTag('<CrossWorkpaperNav/>', 'CrossWorkpaperNav')).toBe(true)
    // 首版 toContain 会误判这三种为「已渲染」
    expect(hasTag('<CrossWorkpaperNavREMOVED :confirm-index="x" />', 'CrossWorkpaperNav')).toBe(false)
    expect(hasTag('<CrossWorkpaperNavOld />', 'CrossWorkpaperNav')).toBe(false)
    expect(hasTag('<div />', 'CrossWorkpaperNav')).toBe(false)
  })

  it('宿主 defineEmits 已声明 navigate-sheet（否则事件冒不到 GtWpRenderer）', () => {
    const idx = HOST_SRC.indexOf('defineEmits<')
    expect(idx, '未找到 defineEmits → 解析失效').toBeGreaterThan(-1)
    const block = sliceBalanced(HOST_SRC, idx, '{', '}')
    expect(block.length).toBeGreaterThan(0)
    expect(block).toContain("'navigate-sheet'")
  })

  it('调用点属性全部是 CrossWorkpaperNav 的合法 prop（防「传不存在的 prop = 静默失效」）', () => {
    // 🔴 Vue 对未知属性不报错：它们落到根元素当 HTML 属性 → Volar / vitest / Vite
    //    transform 四层全绿，只有浏览器才暴露（G5 溯源面板曾因此从未渲染过）。
    const legal = navPropNames()
    expect(legal.size, '未能从 defineProps 抽出 prop 名 → 正则失效').toBeGreaterThanOrEqual(4)
    expect(legal).toEqual(new Set(['confirm-index', 'wp-code', 'current-wp-code', 'exists-map']))

    const tag = extractTagAttrs(HOST_SRC, 'CrossWorkpaperNav')
    expect(tag, '未能在宿主模板定位 <CrossWorkpaperNav> 调用点').not.toBeNull()
    const passed = tag!.attrs.map(normalizeAttr).filter((n): n is string => n !== null)
    expect(passed.length, `未抽出任何属性：${tag!.raw}`).toBeGreaterThan(0)
    for (const name of passed) {
      expect(
        legal.has(name),
        `宿主传了 "${name}" 但组件 defineProps 里没有。合法 props: [${[...legal].join(', ')}]`,
      ).toBe(true)
    }
  })

  it('必填 prop confirm-index 已传（缺它组件内部 v-if 恒 false = 挂了也不渲染）', () => {
    const tag = extractTagAttrs(HOST_SRC, 'CrossWorkpaperNav')!
    const passed = new Set(tag.attrs.map(normalizeAttr).filter((n): n is string => n !== null))
    expect(passed.has('confirm-index')).toBe(true)
    // current-wp-code 决定「当前底稿」高亮落在哪个 chip → 必须传且不得是字面量
    expect(passed.has('current-wp-code')).toBe(true)
    expect(tag.raw).not.toMatch(/current-wp-code="[A-Z]\d/)
  })

  it('current-wp-code 由 getCycleConfirmationMeta 派生，不写死 D0-1', () => {
    // 🔴 写死会让 E0/F0/G0/H0/K0/L0 六个循环全部高亮到 D0-1（既有平台缺陷同款）
    expect(HOST_SRC).toMatch(/getCycleConfirmationMeta\(\s*props\.wpCode\s*\)\.summaryCode/)
    const decl = /const\s+currentSummaryCode\s*=/.exec(HOST_SRC)
    expect(decl, '未找到 currentSummaryCode 声明').not.toBeNull()
    expect(HOST_SRC.slice(decl!.index, decl!.index + 200)).not.toMatch(/'D0-1'/)
  })

  it('反向自检：内联 fixture 里的 :bogus-prop 被判为非法', () => {
    const legal = navPropNames()
    const fixture = '<template><CrossWorkpaperNav :confirm-index="a" :bogus-prop="b" /></template>'
    const tag = extractTagAttrs(fixture, 'CrossWorkpaperNav')!
    const passed = tag.attrs.map(normalizeAttr).filter((n): n is string => n !== null)
    expect(passed).toContain('bogus-prop')
    expect(legal.has('bogus-prop')).toBe(false)
    // 同时证明指令/保留属性会被正确排除，不至于误报
    const fixture2 =
      '<template><CrossWorkpaperNav v-if="x" :key="k" class="c" @navigate-sheet="f" :wp-code="w" /></template>'
    const tag2 = extractTagAttrs(fixture2, 'CrossWorkpaperNav')!
    const passed2 = tag2.attrs.map(normalizeAttr).filter((n): n is string => n !== null)
    expect(passed2).toEqual(['wp-code'])
  })
})

// ─── Property 2: 点击不再被 exists 门挡住，且定位值取主码 ─────────────────────

describe('Property 2: 点击不被 exists 门挡住 + 定位值取主码（Validates 1.3, 1.4, 1.5）', () => {
  const item = (over: Partial<NavLocatorInput>): NavLocatorInput => ({
    wpCode: 'D0-1',
    sheetName: null,
    sameWorkbook: false,
    ...over,
  })

  it('同工作簿且有真实 tab 名 → 返回 sheetName', () => {
    expect(
      locatorOf(item({ wpCode: 'G0-4', sheetName: '函证差异核对表G0-3（证券投资）', sameWorkbook: true })),
    ).toBe('函证差异核对表G0-3（证券投资）')
  })

  it('组合替代程序 wpCode=D0-5/D0-6 且 sheetName=null → 返回主码 D0-5', () => {
    // 🔴 整串 `D0-5/D0-6` 不可能命中任何 sheet 名 → 必须取首段
    expect(locatorOf(item({ wpCode: 'D0-5/D0-6' }))).toBe('D0-5')
    expect(locatorOf(item({ wpCode: 'K0-5/K0-6' }))).toBe('K0-5')
    expect(locatorOf(item({ wpCode: 'F0-5/F0-6' }))).toBe('F0-5')
  })

  it('sameWorkbook=false → 取 wpCode 首段（六枢纽靠归一后 includes 命中中文 tab 名）', () => {
    expect(locatorOf(item({ wpCode: 'H0-1', sheetName: 'H0-1', sameWorkbook: false }))).toBe('H0-1')
    expect(locatorOf(item({ wpCode: 'L0-7', sheetName: null }))).toBe('L0-7')
  })

  it('sameWorkbook=true 但 sheetName 为 null → 回退 wpCode 首段（不返回 null/空串）', () => {
    expect(locatorOf(item({ wpCode: 'E0-2', sheetName: null, sameWorkbook: true }))).toBe('E0-2')
  })

  it('locatorOf 恒返回非空字符串（下游 resolveSheetNameByDeepLink 拿空串会静默失败）', () => {
    for (const w of ['D0-1', 'D0-5/D0-6', 'G0-8', 'K0-5/K0-6', 'L0-3']) {
      const v = locatorOf(item({ wpCode: w }))
      expect(v.length, w).toBeGreaterThan(0)
      expect(v.includes('/'), w).toBe(false)
    }
  })

  it('handleNavigate 体内不含 !item.exists 早退（剥注释后判定）', () => {
    // 🔴 组件注释里逐字写着 `!item.exists`（解释「为什么去掉早退」）→ 不剥注释必假阳性。
    //    前一个会话已实测踩中这一点。
    const body = extractFunctionBody(NAV_SRC, 'handleNavigate')
    expect(body.length, '未截到 handleNavigate 函数体 → 解析失效').toBeGreaterThan(0)
    expect(body).not.toMatch(/!\s*item\.exists/)
    expect(body).not.toMatch(/item\.exists\s*===?\s*false/)
    // 正面：仍然只挡「当前页」，并统一走 navigate-sheet + locatorOf
    expect(body).toMatch(/item\.wpCode\s*===\s*props\.currentWpCode/)
    expect(body).toMatch(/emit\(\s*'navigate-sheet'\s*,\s*locatorOf\(\s*item\s*\)/)
  })

  it('exists 只驱动视觉/tooltip：模板仍用它做 class 与提示，但不禁用点击', () => {
    expect(NAV_SRC).toMatch(/chip--disabled['"]?\s*:\s*!item\.exists/)
    expect(NAV_SRC).toContain('@click="handleNavigate(item)"')
    // 灰态可点 → tooltip 必须说明「灰=暂无数据」，否则视觉与行为矛盾
    expect(NAV_SRC).toContain('本笔暂无数据')
  })

  it('反向自检：复现旧实现（含 !item.exists 早退）时 exists=false 项判为不跳转', () => {
    const emitted: string[] = []
    // 旧实现
    const legacyNavigate = (it: { wpCode: string; exists: boolean }) => {
      if (!it.exists) return
      emitted.push(it.wpCode)
    }
    legacyNavigate({ wpCode: 'D0-4', exists: false })
    expect(emitted).toEqual([])
    // 现行实现（exists 不参与判定）
    const currentNavigate = (it: { wpCode: string; exists: boolean }) => {
      if (it.wpCode === 'D0-1') return
      emitted.push(it.wpCode)
    }
    currentNavigate({ wpCode: 'D0-4', exists: false })
    expect(emitted).toEqual(['D0-4'])

    // 并证明「旧实现的源码形态」确实会被上面那条源码断言抓住
    const legacySrc = 'function handleNavigate(item) { if (!item.exists) return\n emit("x") }'
    expect(extractFunctionBody(legacySrc, 'handleNavigate')).toMatch(/!\s*item\.exists/)
  })
})

// ─── Property 3: 完整表格视图与未选中行不渲染导航条 ──────────────────────────

describe('Property 3: 完整表格视图与未选中行不渲染导航条（Validates 1.2）', () => {
  /** 列表视图分支的模板片段（`v-if="viewMode...==='list'"` 的 <template> 内部） */
  function listViewBranch(): string {
    const anchor = HOST_SRC.indexOf("viewMode.viewMode.value === 'list'")
    expect(anchor, '未定位列表视图分支 → 解析失效').toBeGreaterThan(-1)
    // 该 <template v-if> 一直延续到配对的 </template>；用「下一个 <template v-else」作右界，
    // 它是同级兄弟分支，紧随列表视图分支之后。
    const elseIdx = HOST_SRC.indexOf('<template v-else', anchor)
    expect(elseIdx, '未找到 <template v-else> 右界').toBeGreaterThan(anchor)
    return HOST_SRC.slice(anchor, elseIdx)
  }

  it('导航块在列表视图分支内，且紧随 ConfirmationDetail 之后', () => {
    const branch = listViewBranch()
    const detailM = tagPresenceRe('ConfirmationDetail').exec(branch)
    const navM = tagPresenceRe('CrossWorkpaperNav').exec(branch)
    expect(detailM, 'ConfirmationDetail 不在列表视图分支内').not.toBeNull()
    expect(navM, 'CrossWorkpaperNav 不在列表视图分支内').not.toBeNull()
    const detail = detailM!.index
    const nav = navM!.index
    expect(nav).toBeGreaterThan(detail)
    // 两者之间不得插入其它组件（「紧随」）
    const between = branch.slice(detail, nav)
    expect(between.match(/<[A-Z][A-Za-z0-9]*/g)).toEqual(['<ConfirmationDetail'])
  })

  it('完整表格视图分支内没有导航块', () => {
    // 🔴 必须从列表视图锚点之后再找 `<template v-else` —— 文件里在此之前还有别的
    //    `<template v-else`（首版漏了 fromIndex，切出来的其实是列表视图分支，
    //    断言「不含导航块」于是假红；这正是「固定字符窗口/裸 indexOf 截片段」的坑）。
    const anchor = HOST_SRC.indexOf("viewMode.viewMode.value === 'list'")
    expect(anchor, '未定位列表视图分支 → 解析失效').toBeGreaterThan(-1)
    const elseIdx = HOST_SRC.indexOf('<template v-else', anchor)
    expect(elseIdx, '未找到完整表格视图分支').toBeGreaterThan(anchor)
    const gridBranch = HOST_SRC.slice(elseIdx, HOST_SRC.indexOf('</template>', elseIdx))
    expect(gridBranch.length, '切出的分支为空 → 解析失效').toBeGreaterThan(50)
    expect(hasTag(gridBranch, 'ConfirmationFullGrid')).toBe(true)
    expect(hasTag(gridBranch, 'CrossWorkpaperNav')).toBe(false)
  })

  it('宿主侧有 v-if="currentRowConfirmIndex" 门控（未选中行 / 行无索引号即不渲染）', () => {
    const tag = extractTagAttrs(HOST_SRC, 'CrossWorkpaperNav')!
    expect(tag.raw).toContain('v-if="currentRowConfirmIndex"')
    // 该 computed 取选中行的 confirm_index，且对 null 安全
    expect(HOST_SRC).toMatch(
      /const\s+currentRowConfirmIndex\s*=\s*computed\([\s\S]{0,200}?currentRow\.value\?\.confirm_index/,
    )
  })

  it('组件自身第二道门 v-if="confirmIndex" 仍在（宿主门控之外的兜底）', () => {
    expect(NAV_SRC).toMatch(/<div\s+v-if="confirmIndex"/)
  })

  it('挂载：confirmIndex 为空串时 DOM 无导航条；非空时渲染出 chip', () => {
    /*
     * 🔴 折中说明（有意不挂载 GtConfirmationSummary）：
     *    该宿主 setup 期要 inject 审计上下文、拉 render-config、初始化 7+ 个 composable
     *    与函证字典，挂载它需要大量 mock，而本 Property 要验的是「未选中行时导航条不出现」
     *    这一条渲染事实。故拆成两半各用**最贴合的手段**：
     *      · 宿主侧门控 → 上面那条源码级 `v-if="currentRowConfirmIndex"` 断言
     *        （宿主 computed 在 currentRow 为 null 时返回空串，与本挂载用例的入参等价）
     *      · 组件侧门控 → 这里真实挂载 CrossWorkpaperNav 断言 DOM
     *    两条合起来覆盖 R1.2 的两种「不渲染」成因，且都不是恒真断言。
     */
    const empty = mount(CrossWorkpaperNav, {
      props: { confirmIndex: '', wpCode: 'D0-1', currentWpCode: 'D0-1' },
    })
    expect(empty.find('.cross-workpaper-nav').exists()).toBe(false)
    expect(empty.text()).toBe('')

    const filled = mount(CrossWorkpaperNav, {
      props: { confirmIndex: 'D0-1-001', wpCode: 'D0-1', currentWpCode: 'D0-1' },
    })
    expect(filled.find('.cross-workpaper-nav').exists()).toBe(true)
    expect(filled.findAll('.cross-workpaper-nav__chip').length).toBeGreaterThan(0)
    empty.unmount()
    filled.unmount()
  })

  it('挂载：点击非当前页 chip 会 emit navigate-sheet（即便 existsMap 缺省）', () => {
    // existsMap 缺省 → 全部 exists=false；放开 exists 门后仍必须可点（R1.5）
    const w = mount(CrossWorkpaperNav, {
      props: { confirmIndex: 'D0-1-001', wpCode: 'D0-1', currentWpCode: 'D0-1' },
    })
    const chips = w.findAll('.cross-workpaper-nav__chip')
    const target = chips.find((c) => c.text() !== 'D0-1')
    expect(target, '未找到非当前页 chip').toBeTruthy()
    target!.trigger('click')
    const evs = w.emitted('navigate-sheet') as unknown[][] | undefined
    expect(evs, '点击灰态 chip 未 emit → exists 门仍在').toBeTruthy()
    expect(evs![0][1]).toBe('D0-1-001')
    expect(String(evs![0][0]).length).toBeGreaterThan(0)
    // 当前页 chip 不跳
    const self = chips.find((c) => c.text() === 'D0-1')!
    const before = (w.emitted('navigate-sheet') as unknown[][]).length
    self.trigger('click')
    expect((w.emitted('navigate-sheet') as unknown[][]).length).toBe(before)
    w.unmount()
  })
})
