/**
 * 函数里的 await 必须在 async 函数内 —— 全前端语法可解析性守卫。
 *
 * 回归背景：2026-10-31 的提交 6f4c5a54a（spec lan-http-insecure-context-compat）把同步剪贴板调用
 * 换成 `await copyText(...)` / `await copyRichText(...)`，但没把宿主函数改成 async ⇒ 25 处 await
 * 落在非 async 函数里，15 个文件整体 SyntaxError：试算表、附注编辑器、序时账穿透、合并入口、
 * 合并附注、高级查询、多年对比等核心页全部打不开（vite 在编译期就挂，运行时拿不到任何提示）。
 *
 * 这类缺陷单测抓不到（被测文件根本无法加载，只会报"采集失败"而非指出原因），类型检查也不会先于
 * 语法解析报告，所以必须有一条独立的语法判据。
 *
 * 判据：
 *  A. 全前端（src 下 .ts/.tsx/.vue 的 script 段）没有「await 在非 async 函数内」；
 *  B. SFC 本身可被 @vue/compiler-sfc 解析（解析错误同样是编译期挂）；
 *  C. 扫描范围非空（防止 glob 失配导致判据空转）；
 *  D. 扫描器自检：合成的违规样本必须被抓到，合法写法（async 函数、嵌套 async、顶层 await）不得误报。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import ts from 'typescript'
import { parse as parseSfc } from '@vue/compiler-sfc'
import { describe, expect, it } from 'vitest'

const SRC = resolve(__dirname, '..')
const SOURCE_EXT = /\.(?:ts|tsx|vue)$/

export interface AwaitViolation {
  file: string
  line: number
  text: string
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules') continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (SOURCE_EXT.test(name)) out.push(full)
  }
  return out
}

function isFunctionLike(node: ts.Node): boolean {
  return ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node) || ts.isArrowFunction(node)
    || ts.isMethodDeclaration(node) || ts.isGetAccessorDeclaration(node) || ts.isSetAccessorDeclaration(node)
    || ts.isConstructorDeclaration(node)
}

function isAsync(node: ts.Node): boolean {
  return !!(node as ts.FunctionLikeDeclaration).modifiers?.some((m) => m.kind === ts.SyntaxKind.AsyncKeyword)
}

/** 一段脚本里「落在非 async 函数内」的 await；模块顶层 await 不算（ESM 合法）。 */
function scanScript(file: string, code: string, baseLine: number): AwaitViolation[] {
  const sf = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const lines = code.split('\n')
  const found: AwaitViolation[] = []
  const visit = (node: ts.Node, asyncDepth: number, insideFunction: boolean) => {
    if (isFunctionLike(node)) {
      const nextDepth = isAsync(node) ? asyncDepth + 1 : 0
      ts.forEachChild(node, (child) => visit(child, nextDepth, true))
      return
    }
    if (ts.isAwaitExpression(node) && insideFunction && asyncDepth === 0) {
      const line = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line
      found.push({ file, line: baseLine + line + 1, text: (lines[line] ?? '').trim().slice(0, 100) })
    }
    ts.forEachChild(node, (child) => visit(child, asyncDepth, insideFunction))
  }
  visit(sf, 0, false)
  return found
}

export function scanAwaitOutsideAsync(file: string, source: string): { violations: AwaitViolation[]; parseErrors: string[] } {
  if (!file.endsWith('.vue')) {
    return { violations: scanScript(file, source, 0), parseErrors: [] }
  }
  const { descriptor, errors } = parseSfc(source, { filename: file })
  const violations: AwaitViolation[] = []
  for (const block of [descriptor.script, descriptor.scriptSetup]) {
    if (block?.content) violations.push(...scanScript(file, block.content, Math.max(0, block.loc.start.line - 1)))
  }
  return { violations, parseErrors: errors.map((e) => String((e as Error).message ?? e)) }
}

const FILES = walk(SRC)
const RESULTS = FILES.map((absolute) => {
  const rel = relative(SRC, absolute).replace(/\\/g, '/')
  return { rel, ...scanAwaitOutsideAsync(rel, readFileSync(absolute, 'utf-8')) }
})

describe('await 必须在 async 函数内（全前端语法守卫）', () => {
  it('A：没有 await 落在非 async 函数内', () => {
    const offenders = RESULTS.flatMap((r) => r.violations).map((v) => `${v.file}:${v.line} ${v.text}`)
    expect(offenders, '给宿主函数加 async（否则该文件整体 SyntaxError、页面打不开）').toEqual([])
  })

  it('B：所有 SFC 都能被解析', () => {
    const broken = RESULTS.filter((r) => r.parseErrors.length).map((r) => `${r.rel}: ${r.parseErrors.join('; ')}`)
    expect(broken).toEqual([])
  })

  it('C：扫描范围非空（防判据空转）', () => {
    expect(FILES.length).toBeGreaterThan(1000)
    expect(RESULTS.filter((r) => r.rel.endsWith('.vue')).length).toBeGreaterThan(500)
  })

  it('D：扫描器抓得到违规样本，合法写法不误报', () => {
    const bad = [
      'function copyTable() {',
      '  const text = build()',
      '  await copyText(text)',
      '}',
    ].join('\n')
    expect(scanAwaitOutsideAsync('bad.ts', bad).violations).toHaveLength(1)

    const badVue = [
      '<template><button @click="handleCopy" /></template>',
      '<script setup lang="ts">',
      'function handleCopy() {',
      '  await copyRichText(html, text)',
      '}',
      '</script>',
    ].join('\n')
    const vueHit = scanAwaitOutsideAsync('bad.vue', badVue)
    expect(vueHit.violations).toHaveLength(1)
    // 行号按 SFC 整体计（script 块偏移已加上），便于直接定位
    expect(vueHit.violations[0].line).toBe(4)

    const good = [
      'async function a() { await f() }',
      'const b = async () => { await f() }',
      'class C { async m() { await f() } }',
      'const obj = { async m() { await f() } }',
      'async function outer() { const inner = async () => { await f() }; await inner() }',
      'await topLevel()',
    ].join('\n')
    expect(scanAwaitOutsideAsync('good.ts', good).violations).toEqual([])

    // 非 async 外层套 async 内层：内层的 await 合法，外层自己的 await 才违规
    const mixed = [
      'function outer() {',
      '  const inner = async () => { await ok() }',
      '  void inner',
      '  await bad()',
      '}',
    ].join('\n')
    const mixedHit = scanAwaitOutsideAsync('mixed.ts', mixed).violations
    expect(mixedHit).toHaveLength(1)
    expect(mixedHit[0].text).toContain('await bad()')
  })
})
