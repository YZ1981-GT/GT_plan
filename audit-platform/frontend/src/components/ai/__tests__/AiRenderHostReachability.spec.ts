/**
 * 渲染宿主可达性守卫 —— 抓「组件孤岛」这一整类假绿
 *
 * ## 它防的是什么
 *
 * 2026-08-16 实测：`ChatMentionPicker.vue` 与 `ChatContextInspector.vue` 存在、
 * 有 23 条 vitest 守卫全绿、Task 15 标记 `[x]`，但**没有任何宿主 import 它们** ——
 * `PlatformAiChatPanel.vue` 只挂了 ChatAttachmentPicker / ChatReviewModeBar。
 * 后果：浏览器里用户打不出 `@`、看不到 Context Manifest，Req 5.1/5.4/5.7/5.9
 * 在运行产品里等于没实现。而 23 条 vitest 全绿，因为它们直接 `mount(组件)`，
 * **从不问「有没有人挂载它」**。
 *
 * 这与 G7 的「模型声明 `column.group`、三向守卫 39 例全绿、任何 `.vue` 零引用
 * ⇒ 两级表头 0/38 从未渲染」是同一形状：**声明齐全 + 单测全绿 + 零渲染宿主**。
 *
 * ## 判据（三层，缺一不可）
 *
 * 1. 组件必须有**至少一个非测试文件**的引用方（`__tests__` / `*.spec.ts` / e2e 不算）
 * 2. 引用方必须**真的把它当标签用**（`.vue` 宿主：`<Foo>` / `<foo-bar>` /
 *    `<component :is="Foo">`；`.ts` 宿主：出现在 import 语句之外，如注册表/路由懒加载）
 *    —— 只 import 不用同样是死代码
 * 3. 判定必须**基于结构化解析**（注释感知的 import 语句解析 + template 块提取），
 *    不是裸 grep 符号名 —— 符号名出现在注释、字符串、import 行里都不算使用
 *
 * 并附**反向自检**：构造「有 import 无标签」的假样本判据必须识别，
 * 构造「正常使用」的样本判据必须放过。没有这两条，判据自己就可能已经恒真。
 *
 * ## 为什么按前缀扫全目录而不是点名两个组件
 *
 * 抓的是「组件孤岛」这个**类**，不是某两个具体组件 ——
 * 以后新加 `Chat*.vue` / `Platform*.vue` / `Dsh*.vue` 忘接线会自动打红。
 *
 * Feature: dsh-agent-panel-integration / Task 15 接线补口
 * Validates: Requirements 5.1, 5.4, 5.7, 5.9
 * Properties: 12, 13
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'fs'
import { resolve, dirname, basename, join, sep } from 'path'

// ---------------------------------------------------------------------------
// 路径
// ---------------------------------------------------------------------------

const FRONTEND_SRC = resolve(__dirname, '../../..')
const AI_DIR = resolve(FRONTEND_SRC, 'components/ai')

/** 纳入扫描的组件名前缀（本 spec 的职责域） */
const TARGET_PREFIXES = ['Chat', 'Platform', 'Dsh'] as const

// ---------------------------------------------------------------------------
// 解析工具（纯函数 —— 反向自检直接喂合成源码验证它们）
// ---------------------------------------------------------------------------

/**
 * 剥掉 JS/TS 注释，但**保留字符串与模板字面量里的内容**。
 *
 * 不能用 `src.replace(/\/\/.*$/gm, '')`：那会把 `'https://x'` 截断成 `'https:`，
 * 于是紧跟其后的 import 语句被吃掉半行，解析结果静默变少。
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

/** 一条 import 记录：本地绑定名 + 模块说明符。 */
export interface ImportRecord {
  localName: string
  specifier: string
}

/**
 * 抽出源码里的模块引用（注释已剥）。覆盖四种形态：
 *   `import Foo from 'x'` · `import Foo, { a } from 'x'` ·
 *   `const Foo = defineAsyncComponent(() => import('x'))` ·
 *   `const Foo = () => import('x')`
 */
export function parseComponentImports(rawSource: string): ImportRecord[] {
  const source = stripJsComments(rawSource)
  const records: ImportRecord[] = []

  const staticDefault = /import\s+([A-Za-z_$][\w$]*)\s*(?:,\s*\{[^}]*\})?\s*from\s*['"]([^'"]+)['"]/g
  for (const m of source.matchAll(staticDefault)) {
    records.push({ localName: m[1], specifier: m[2] })
  }

  const lazy = /(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:defineAsyncComponent\s*\(\s*)?\(\s*\)\s*=>\s*import\s*\(\s*['"]([^'"]+)['"]/g
  for (const m of source.matchAll(lazy)) {
    records.push({ localName: m[1], specifier: m[2] })
  }

  return records
}

/**
 * 取 `.vue` 的顶层 `<template>` 块正文（注释已剥）。
 *
 * 用**行首锚定**的 `<template>` / `</template>` 作边界：嵌套的
 * `<template #slot>` 都有缩进，不会被当成块边界。
 */
export function extractTemplateBlock(vueSource: string): string {
  const open = vueSource.match(/^<template[^>]*>/m)
  if (!open || open.index === undefined) return ''
  const start = open.index + open[0].length
  const closeIdx = vueSource.lastIndexOf('\n</template>')
  const end = closeIdx > start ? closeIdx : vueSource.length
  return stripHtmlComments(vueSource.slice(start, end))
}

/** PascalCase → kebab-case（`ChatMentionPicker` → `chat-mention-picker`）。 */
export function toKebabCase(name: string): string {
  return name
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1-$2')
    .toLowerCase()
}

/**
 * 模板里是否**真的把 `localName` 当组件用**。
 *
 * 三种合法形态：PascalCase 标签、kebab-case 标签、`<component :is="Foo">`。
 * 注释里的标签不算（调用前已剥注释）；`<script>` 里的字符串不算
 * （本函数只接受 template 块正文）。
 */
export function templateUsesComponent(templateBlock: string, localName: string): boolean {
  const kebab = toKebabCase(localName)
  const patterns = [
    new RegExp(`<${localName}(?=[\\s/>])`),
    new RegExp(`<${kebab}(?=[\\s/>])`),
    new RegExp(`:is=["']${localName}["']`),
    new RegExp(`:is=["']\\s*${localName}\\s*["']`),
  ]
  return patterns.some((p) => p.test(templateBlock))
}

/**
 * `.ts` 宿主里是否在 import 之外真的用到（注册表 / 路由懒加载 / 数组登记）。
 *
 * 做法：剥注释 → 删掉所有 import 语句本身 → 再看标识符是否还出现。
 */
export function scriptUsesIdentifierOutsideImport(rawSource: string, localName: string): boolean {
  const withoutImports = stripJsComments(rawSource)
    .replace(/import\s+[^;\n]*from\s*['"][^'"]+['"];?/g, '')
    .replace(/import\s*\(\s*['"][^'"]+['"]\s*\)/g, '')
  return new RegExp(`\\b${localName}\\b`).test(withoutImports)
}

// ---------------------------------------------------------------------------
// 文件系统扫描
// ---------------------------------------------------------------------------

const SKIP_DIR_NAMES = new Set(['node_modules', 'dist', '__tests__', '__snapshots__'])

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    const st = statSync(full)
    if (st.isDirectory()) {
      if (SKIP_DIR_NAMES.has(entry)) continue
      walk(full, out)
    } else if (/\.(vue|ts)$/.test(entry) && !/\.(spec|test)\.ts$/.test(entry)) {
      out.push(full)
    }
  }
  return out
}

/** 把 import specifier 解析成绝对路径（支持 `@/` 别名与相对路径；补 `.vue`/`.ts` 后缀）。 */
function resolveSpecifier(fromFile: string, specifier: string): string | null {
  let base: string
  if (specifier.startsWith('@/')) {
    base = resolve(FRONTEND_SRC, specifier.slice(2))
  } else if (specifier.startsWith('.')) {
    base = resolve(dirname(fromFile), specifier)
  } else {
    return null // 裸包名
  }
  if (/\.(vue|ts)$/.test(base)) return base
  return null
}

/** 待检组件清单（按前缀过滤，排除 index/测试） */
function targetComponents(): string[] {
  return readdirSync(AI_DIR)
    .filter((f) => f.endsWith('.vue'))
    .filter((f) => TARGET_PREFIXES.some((p) => f.startsWith(p)))
    .map((f) => resolve(AI_DIR, f))
    .sort()
}

interface Referrer {
  file: string
  localName: string
  /** 真的当标签/注册项用了（不只是 import） */
  used: boolean
}

/** 找出引用 `componentPath` 的全部非测试文件。 */
function findReferrers(componentPath: string, allFiles: string[]): Referrer[] {
  const referrers: Referrer[] = []
  for (const file of allFiles) {
    if (file === componentPath) continue // 自引用不算（组件递归引用自己）
    const source = readFileSync(file, 'utf-8')
    for (const rec of parseComponentImports(source)) {
      const resolved = resolveSpecifier(file, rec.specifier)
      if (resolved !== componentPath) continue
      const used = file.endsWith('.vue')
        ? templateUsesComponent(extractTemplateBlock(source), rec.localName)
        : scriptUsesIdentifierOutsideImport(source, rec.localName)
      referrers.push({ file, localName: rec.localName, used })
    }
  }
  return referrers
}

const ALL_SOURCE_FILES = walk(FRONTEND_SRC)
const TARGETS = targetComponents()

function rel(p: string): string {
  return p.slice(FRONTEND_SRC.length + 1).split(sep).join('/')
}

// ===========================================================================
// 判据自身不空洞
// ===========================================================================

describe('渲染宿主可达性守卫：判据自身不空洞', () => {
  it('扫描到的组件清单非空且覆盖 Chat*/Platform*/Dsh* 三类', () => {
    const names = TARGETS.map((p) => basename(p))
    // 空清单会让下面的 for 循环一条测试都不生成 ⇒ 整个守卫静默变成 0 条
    expect(names.length).toBeGreaterThanOrEqual(6)
    for (const prefix of TARGET_PREFIXES) {
      expect(names.some((n) => n.startsWith(prefix))).toBe(true)
    }
    // 本次接线的两个组件必须在清单里（它们就是本守卫的由来）
    expect(names).toContain('ChatMentionPicker.vue')
    expect(names).toContain('ChatContextInspector.vue')
  })

  it('扫描到的源文件集合足够大且排除了测试文件', () => {
    expect(ALL_SOURCE_FILES.length).toBeGreaterThan(200)
    expect(ALL_SOURCE_FILES.some((f) => f.includes('__tests__'))).toBe(false)
    expect(ALL_SOURCE_FILES.some((f) => f.endsWith('.spec.ts'))).toBe(false)
  })
})

// ===========================================================================
// 主判据：每个组件都有非测试宿主，且宿主真的把它当标签用
// ===========================================================================

describe('渲染宿主可达性：src/components/ai 下 Chat*/Platform*/Dsh* 全部组件', () => {
  for (const componentPath of TARGETS) {
    const name = basename(componentPath, '.vue')

    it(`${name} 至少被一个非测试文件 import`, () => {
      const referrers = findReferrers(componentPath, ALL_SOURCE_FILES)
      expect(
        referrers.map((r) => rel(r.file)),
        `${name}.vue 零宿主引用 —— 组件孤岛：它在浏览器里永远不会出现。`
          + `要么接线到宿主，要么删掉。`,
      ).not.toEqual([])
    })

    it(`${name} 至少有一个宿主真的把它当标签/注册项使用（只 import 不用也是死代码）`, () => {
      const referrers = findReferrers(componentPath, ALL_SOURCE_FILES)
      const rendering = referrers.filter((r) => r.used)
      expect(
        rendering.map((r) => rel(r.file)),
        `${name}.vue 被 ${referrers.length} 个文件 import，但没有任何一个在 <template> 里`
          + `真的用作标签（或在 .ts 里登记）⇒ import 了不用，等同死代码。`
          + `引用方：${referrers.map((r) => rel(r.file)).join(', ') || '（无）'}`,
      ).not.toEqual([])
    })
  }
})

// ===========================================================================
// 本次接线的点名判据（防止「守卫在、但恰好这两个又被摘掉」）
// ===========================================================================

describe('PlatformAiChatPanel 必须挂载 Task 15 的两个组件', () => {
  const PANEL = resolve(AI_DIR, 'PlatformAiChatPanel.vue')

  for (const child of ['ChatMentionPicker', 'ChatContextInspector', 'ChatAttachmentPicker', 'ChatReviewModeBar']) {
    it(`面板 template 里真的渲染 <${child}>`, () => {
      const source = readFileSync(PANEL, 'utf-8')
      const imported = parseComponentImports(source).some(
        (r) => r.localName === child && resolveSpecifier(PANEL, r.specifier) === resolve(AI_DIR, `${child}.vue`),
      )
      expect(imported, `${child} 未被 PlatformAiChatPanel.vue import`).toBe(true)
      expect(
        templateUsesComponent(extractTemplateBlock(source), child),
        `${child} 被 import 了但 template 里没有 <${child}> 标签`,
      ).toBe(true)
    })
  }
})

// ===========================================================================
// 反向自检 —— 判据必须能识别「有 import 无标签」，且必须放过正常使用
// ===========================================================================

describe('反向自检：判据在合成样本上必须有正确结论', () => {
  const IMPORT_LINE = `import ChatMentionPicker from './ChatMentionPicker.vue'`

  function makeVue(templateBody: string, scriptBody = IMPORT_LINE): string {
    return `<template>\n${templateBody}\n</template>\n\n<script setup lang="ts">\n${scriptBody}\n</script>\n`
  }

  it('有 import 但 template 无标签 ⇒ 必须判为未使用', () => {
    const src = makeVue('  <div class="panel">只有壳，没有 picker</div>')
    expect(parseComponentImports(src).map((r) => r.localName)).toContain('ChatMentionPicker')
    expect(templateUsesComponent(extractTemplateBlock(src), 'ChatMentionPicker')).toBe(false)
  })

  it('PascalCase 标签 ⇒ 必须放过', () => {
    const src = makeVue('  <ChatMentionPicker :open="true" />')
    expect(templateUsesComponent(extractTemplateBlock(src), 'ChatMentionPicker')).toBe(true)
  })

  it('kebab-case 标签 ⇒ 必须放过', () => {
    const src = makeVue('  <chat-mention-picker :open="true" />')
    expect(templateUsesComponent(extractTemplateBlock(src), 'ChatMentionPicker')).toBe(true)
  })

  it('动态 <component :is> ⇒ 必须放过', () => {
    const src = makeVue('  <component :is="ChatMentionPicker" />')
    expect(templateUsesComponent(extractTemplateBlock(src), 'ChatMentionPicker')).toBe(true)
  })

  it('标签只出现在模板注释里 ⇒ 必须判为未使用', () => {
    const src = makeVue('  <!-- <ChatMentionPicker /> 以后再接 -->\n  <div />')
    expect(templateUsesComponent(extractTemplateBlock(src), 'ChatMentionPicker')).toBe(false)
  })

  it('标签只出现在 script 字符串里 ⇒ 必须判为未使用', () => {
    const src = makeVue('  <div />', `${IMPORT_LINE}\nconst tpl = '<ChatMentionPicker />'`)
    expect(templateUsesComponent(extractTemplateBlock(src), 'ChatMentionPicker')).toBe(false)
  })

  it('前缀相同的另一个组件不得被误判为同一个（ChatMentionPickerV2 ≠ ChatMentionPicker）', () => {
    const src = makeVue('  <ChatMentionPickerV2 />')
    expect(templateUsesComponent(extractTemplateBlock(src), 'ChatMentionPicker')).toBe(false)
  })

  it('import 被注释掉 ⇒ 解析结果里不得出现', () => {
    const src = makeVue('  <div />', `// ${IMPORT_LINE}`)
    expect(parseComponentImports(src).map((r) => r.localName)).not.toContain('ChatMentionPicker')
  })

  it('注释剥离不得截断含 // 的字符串（否则同行后续 import 会被吃掉）', () => {
    const src = `const doc = 'https://example.com/a'\n${IMPORT_LINE}\n`
    const stripped = stripJsComments(src)
    expect(stripped).toContain('https://example.com/a')
    expect(parseComponentImports(src).map((r) => r.localName)).toContain('ChatMentionPicker')
  })

  it('.ts 宿主：只 import 不用 ⇒ 未使用；登记进注册表 ⇒ 已使用', () => {
    const onlyImport = `import ChatMentionPicker from '@/components/ai/ChatMentionPicker.vue'\n`
    expect(scriptUsesIdentifierOutsideImport(onlyImport, 'ChatMentionPicker')).toBe(false)

    const registered = `${onlyImport}export const registry = { mention: ChatMentionPicker }\n`
    expect(scriptUsesIdentifierOutsideImport(registered, 'ChatMentionPicker')).toBe(true)
  })

  it('kebab 转换对连续大写正确（DshPanel → dsh-panel，AIChatView → ai-chat-view）', () => {
    expect(toKebabCase('DshPanel')).toBe('dsh-panel')
    expect(toKebabCase('ChatMentionPicker')).toBe('chat-mention-picker')
    expect(toKebabCase('AIChatView')).toBe('ai-chat-view')
  })

  it('顶层 template 提取不被嵌套 <template #slot> 打断', () => {
    const src = makeVue(
      '  <el-table>\n    <template #default>\n      <ChatMentionPicker />\n    </template>\n  </el-table>',
    )
    const block = extractTemplateBlock(src)
    expect(block).toContain('#default')
    expect(templateUsesComponent(block, 'ChatMentionPicker')).toBe(true)
  })
})
