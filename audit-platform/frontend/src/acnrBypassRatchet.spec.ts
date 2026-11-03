/**
 * acnrBypassRatchet.spec.ts — ACNR 前端绕过点棘轮与台账符号核对（acnr-foundation-defect-closure T24 / 需求 13 / design §14.1）
 *
 * 与后端 `backend/scripts/check/acnr_bypass_scan.py` 读同一份基线 `backend/data/acnr/bypass_baseline.json`：
 *  - BP-3：`services/apiPaths/` 之外引用 `addressRegistry` 路径常量（含 `as` 别名与 `.v2.*`，按属性链计），
 *          或直写 `/api/address-registry` 字面量；
 *  - BP-4：调用 `useWorkpaperRegistry(`（定义文件除外），或使用 `/api/workpapers/index-resolve`、
 *          `/api/wp-index-resolve` 两个 legacy 导航门面。
 * 识别用 TS 编译器 API；`.vue` 取 `<script>` / `<script setup>` 与模板表达式（@vue/compiler-sfc）。注释不进语法树。
 * 现算超出基线（新增绕过）或基线条目现算找不到（失效条目）都红。
 * 另核对消费方台账 `backend/data/acnr/consumer_ledger.json` 里前端文件的符号由语法树定义。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import ts from 'typescript'
import { parse as parseSfc } from '@vue/compiler-sfc'

const REPO = resolve(__dirname, '../../..')
const SRC = resolve(__dirname)
const SRC_REL = 'audit-platform/frontend/src/'
const BASELINE = JSON.parse(readFileSync(join(REPO, 'backend/data/acnr/bypass_baseline.json'), 'utf-8'))
const LEDGER = JSON.parse(readFileSync(join(REPO, 'backend/data/acnr/consumer_ledger.json'), 'utf-8'))

const API_PATHS_DIR = 'services/apiPaths/'
const V1_LITERAL = '/api/address-registry'
const NAV_LITERALS = ['/api/workpapers/index-resolve', '/api/wp-index-resolve']
const REGISTRY_DEF = 'composables/useWorkpaperRegistry.ts'

type Key = string // `${file}|${kind}|${name}`
export type Counts = Map<Key, number>

function isTestPath(posix: string): boolean {
  return (
    posix.endsWith('.spec.ts') || posix.endsWith('.test.ts') || posix.includes('/__tests__/') ||
    posix.includes('/tests/') || /(^|\/)test_[^/]+\.ts$/.test(posix)
  )
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      if (name !== 'node_modules') walk(p, out)
    } else if (name.endsWith('.ts') || name.endsWith('.vue')) out.push(p)
  }
  return out
}

/** 一段源码的语法树片段：脚本整体，或模板里的一个表达式（包成括号表达式解析）。 */
function sourcesOf(text: string, isVue: boolean): ts.SourceFile[] {
  const mk = (code: string) => ts.createSourceFile('x.ts', code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  if (!isVue) return [mk(text)]
  const { descriptor } = parseSfc(text)
  const out: ts.SourceFile[] = []
  for (const block of [descriptor.script, descriptor.scriptSetup]) if (block?.content) out.push(mk(block.content))
  const exprs: string[] = []
  const visit = (node: any) => {
    if (!node) return
    if (node.type === 5 && node.content?.content) exprs.push(node.content.content) // 插值
    for (const prop of node.props ?? []) {
      if (prop.type === 7 && prop.exp?.content) exprs.push(prop.exp.content) // 指令表达式
      if (prop.type === 6 && prop.value?.content) exprs.push(JSON.stringify(prop.value.content)) // 静态属性值
    }
    for (const child of node.children ?? []) visit(child)
  }
  visit(descriptor.template?.ast)
  for (const e of exprs) out.push(mk(`(${e})`))
  return out
}

function literalText(node: ts.Node): string | null {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text
  if (ts.isTemplateExpression(node)) return [node.head.text, ...node.templateSpans.map((s) => s.literal.text)].join('')
  return null
}

function bump(m: Counts, file: string, kind: string, name: string) {
  const k = `${file}|${kind}|${name}`
  m.set(k, (m.get(k) ?? 0) + 1)
}

/** 现算一个文件的 BP-3 / BP-4 命中；导出供测试对内存样本跑同一实现。 */
export function scanText(file: string, text: string, isVue: boolean): { bp3: Counts; bp4: Counts } {
  const bp3: Counts = new Map()
  const bp4: Counts = new Map()
  const inApiPaths = file.startsWith(SRC_REL + API_PATHS_DIR)
  const isRegistryDef = file === SRC_REL + REGISTRY_DEF
  const sources = sourcesOf(text, isVue)
  const locals = new Set<string>()
  for (const sf of sources) {
    for (const st of sf.statements) {
      if (!ts.isImportDeclaration(st) || !ts.isStringLiteral(st.moduleSpecifier)) continue
      if (!/services\/apiPaths(\/|$)/.test(st.moduleSpecifier.text)) continue
      const nb = st.importClause?.namedBindings
      if (nb && ts.isNamedImports(nb)) {
        for (const el of nb.elements) if ((el.propertyName ?? el.name).text === 'addressRegistry') locals.add(el.name.text)
      }
    }
  }
  for (const sf of sources) {
    const visit = (node: ts.Node) => {
      if (ts.isImportDeclaration(node)) return
      const lit = literalText(node)
      if (lit !== null && !inApiPaths) {
        if (lit.includes(V1_LITERAL)) bump(bp3, file, 'literal', V1_LITERAL)
        for (const nav of NAV_LITERALS) if (lit.includes(nav)) bump(bp4, file, 'literal', nav)
      }
      if (ts.isIdentifier(node) && locals.has(node.text) && !inApiPaths) {
        const p = node.parent
        const isName = (ts.isPropertyAccessExpression(p) && p.name === node) || ts.isPropertyAssignment(p) && p.name === node
        if (!isName) {
          let cur: ts.Node = node
          const chain = ['addressRegistry']
          while (ts.isPropertyAccessExpression(cur.parent) && cur.parent.expression === cur) {
            chain.push(cur.parent.name.text)
            cur = cur.parent
          }
          bump(bp3, file, 'path_const', chain.join('.'))
        }
      }
      if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) &&
          node.expression.text === 'useWorkpaperRegistry' && !isRegistryDef) {
        bump(bp4, file, 'call', 'useWorkpaperRegistry')
      }
      ts.forEachChild(node, visit)
    }
    visit(sf)
  }
  return { bp3, bp4 }
}

function scanRepository(): { bp3: Counts; bp4: Counts; files: number } {
  const bp3: Counts = new Map()
  const bp4: Counts = new Map()
  let files = 0
  for (const abs of walk(SRC)) {
    const posix = relative(SRC, abs).replace(/\\/g, '/')
    if (isTestPath(posix)) continue
    files++
    const r = scanText(SRC_REL + posix, readFileSync(abs, 'utf-8'), posix.endsWith('.vue'))
    for (const [k, v] of r.bp3) bp3.set(k, (bp3.get(k) ?? 0) + v)
    for (const [k, v] of r.bp4) bp4.set(k, (bp4.get(k) ?? 0) + v)
  }
  return { bp3, bp4, files }
}

function baselineCounts(entries: Array<{ file: string; kind: string; name: string; count: number }>): Counts {
  const m: Counts = new Map()
  for (const e of entries) m.set(`${e.file}|${e.kind}|${e.name}`, (m.get(`${e.file}|${e.kind}|${e.name}`) ?? 0) + e.count)
  return m
}

/** 现算对基线：超出（新增绕过）与不足（失效条目）。 */
export function diff(current: Counts, baseline: Counts): { extra: string[]; stale: string[] } {
  const extra: string[] = []
  const stale: string[] = []
  for (const [k, v] of current) if (v > (baseline.get(k) ?? 0)) extra.push(`${k} 超出 ${v - (baseline.get(k) ?? 0)}`)
  for (const [k, v] of baseline) if (v > (current.get(k) ?? 0)) stale.push(`${k} 失效 ${v - (current.get(k) ?? 0)}`)
  return { extra: extra.sort(), stale: stale.sort() }
}

/** 文件里由语法树定义的名字：顶层函数 / 类 / 变量（导出与否都算），类方法按 `类.方法`。 */
function definedNames(text: string, isVue: boolean): Set<string> {
  const names = new Set<string>()
  const sources = isVue ? sourcesOf(text, true).slice(0, 2) : sourcesOf(text, false)
  for (const sf of sources) {
    for (const st of sf.statements) {
      if ((ts.isFunctionDeclaration(st) || ts.isClassDeclaration(st)) && st.name) names.add(st.name.text)
      if (ts.isClassDeclaration(st) && st.name) {
        for (const m of st.members) if (m.name && ts.isIdentifier(m.name)) names.add(`${st.name.text}.${m.name.text}`)
      }
      if (ts.isVariableStatement(st)) {
        for (const d of st.declarationList.declarations) if (ts.isIdentifier(d.name)) names.add(d.name.text)
      }
    }
  }
  return names
}

describe('ACNR 前端绕过点棘轮（T24）', () => {
  const current = scanRepository()

  it('BP-3 现算与基线逐条相等（新增绕过或失效条目都红）', () => {
    const d = diff(current.bp3, baselineCounts(BASELINE.bp3))
    expect(d.extra, `新增绕过：\n${d.extra.join('\n')}`).toEqual([])
    expect(d.stale, `失效条目：\n${d.stale.join('\n')}`).toEqual([])
  })

  it('BP-4 现算与基线逐条相等（新增绕过或失效条目都红）', () => {
    const d = diff(current.bp4, baselineCounts(BASELINE.bp4))
    expect(d.extra, `新增绕过：\n${d.extra.join('\n')}`).toEqual([])
    expect(d.stale, `失效条目：\n${d.stale.join('\n')}`).toEqual([])
  })

  it('扫描有命中且覆盖 src（防空转）', () => {
    expect(current.files).toBeGreaterThan(500)
    expect(current.bp3.size).toBeGreaterThan(0)
    expect(current.bp4.size).toBeGreaterThan(0)
  })

  it('只在注释里提到 legacy 写法不算；新增一处路径常量引用或门面字面量即命中', () => {
    const f = SRC_REL + 'x/sample.ts'
    const quiet = scanText(f, "// import { addressRegistry } from '@/services/apiPaths'\n/* '/api/wp-index-resolve' useWorkpaperRegistry() */\nexport const a = 1\n", false)
    expect([...quiet.bp3.keys(), ...quiet.bp4.keys()]).toEqual([])
    const noisy = scanText(f, "import { addressRegistry as P } from '@/services/apiPaths'\nexport const u = P.v2.resolve\nexport const w = `/api/wp-index-resolve?x=${1}`\nuseWorkpaperRegistry()\n", false)
    expect([...noisy.bp3.keys()]).toEqual([`${f}|path_const|addressRegistry.v2.resolve`])
    expect([...noisy.bp4.keys()].sort()).toEqual([`${f}|call|useWorkpaperRegistry`, `${f}|literal|/api/wp-index-resolve`])
  })

  it('.vue 模板表达式里的字面量也计入', () => {
    const f = SRC_REL + 'x/Sample.vue'
    const r = scanText(f, `<template><a :href="'/api/address-registry/jump'">x</a></template>\n<script setup lang="ts">\nconst n = 1\n</script>\n`, true)
    expect([...r.bp3.keys()]).toEqual([`${f}|literal|${V1_LITERAL}`])
  })

  it('台账里前端文件的符号由语法树定义（不存在的符号即红）', () => {
    const missing: string[] = []
    let checked = 0
    for (const e of LEDGER.entries) {
      for (const s of e.symbols ?? []) {
        if (!String(s.file).startsWith(SRC_REL)) continue
        checked++
        const text = readFileSync(join(REPO, s.file), 'utf-8')
        if (!definedNames(text, s.file.endsWith('.vue')).has(s.name)) missing.push(`${e.id}：${s.file} 没有定义 ${s.name}`)
      }
    }
    expect(missing).toEqual([])
    expect(checked).toBeGreaterThan(0)
  })
})
