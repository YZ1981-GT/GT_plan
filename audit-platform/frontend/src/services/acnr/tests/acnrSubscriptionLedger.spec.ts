/**
 * acnrSubscriptionLedger.spec.ts — 无参 useAcnr() 登记守卫（D9 / T27 / 需求 11.4）
 *
 * useAcnr 默认应带当前 projectId（按项目订阅 SSE 失效 + 隔离解析缓存）。少数消费者与项目无关
 * （全局模板库 / 只列目录），保留无参 `useAcnr()` 并登记在
 * `services/acnr/acnrCatalogOnlyCallers.ts`。
 *
 * 本守卫用 TypeScript 编译器 API 解析非测试 `.ts` 与 `.vue` 的 `<script>` / `<script setup>`，
 * 收集仓库里所有零参 `useAcnr()` 调用的文件集合，断言它恰好等于登记集合——
 *  - 多了一个未登记的无参调用 → 红（漏传当前项目）；
 *  - 登记集合里有文件已不存在该无参调用 / 文件已删 → 红（失效条目）。
 * 注释不计（AST 天然排除）。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import ts from 'typescript'
import { parse as parseSfc } from '@vue/compiler-sfc'
import { ACNR_CATALOG_ONLY_CALLERS } from '../acnrCatalogOnlyCallers'

const SRC = resolve(__dirname, '../../..')

function isTestPath(posix: string): boolean {
  return (
    posix.endsWith('.spec.ts') ||
    posix.endsWith('.test.ts') ||
    posix.includes('/__tests__/') ||
    posix.includes('/tests/') ||
    /(^|\/)test_[^/]+\.ts$/.test(posix)
  )
}

function walkFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) {
      if (name === 'node_modules') continue
      walkFiles(p, out)
    } else if (name.endsWith('.ts') || name.endsWith('.vue')) {
      out.push(p)
    }
  }
  return out
}

/** 在给定源码里数零参 `useAcnr()` 调用（callee 为标识符 useAcnr，实参为空）。 */
function countNoArgUseAcnr(source: string, scriptKind: ts.ScriptKind): number {
  const sf = ts.createSourceFile('x', source, ts.ScriptTarget.Latest, true, scriptKind)
  let count = 0
  const visit = (node: ts.Node) => {
    if (
      ts.isCallExpression(node) &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === 'useAcnr' &&
      node.arguments.length === 0
    ) {
      count++
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return count
}

function scanRepository(): { noArgFiles: Set<string>; countByFile: Map<string, number> } {
  const noArgFiles = new Set<string>()
  const countByFile = new Map<string, number>()
  for (const abs of walkFiles(SRC)) {
    const posix = relative(SRC, abs).replace(/\\/g, '/')
    if (isTestPath(posix)) continue
    const text = readFileSync(abs, 'utf-8')
    if (!text.includes('useAcnr')) continue
    let total = 0
    if (posix.endsWith('.vue')) {
      const { descriptor } = parseSfc(text)
      for (const block of [descriptor.script, descriptor.scriptSetup]) {
        if (!block?.content) continue
        total += countNoArgUseAcnr(block.content, ts.ScriptKind.TS)
      }
    } else {
      total += countNoArgUseAcnr(text, ts.ScriptKind.TS)
    }
    if (total > 0) {
      noArgFiles.add(posix)
      countByFile.set(posix, total)
    }
  }
  return { noArgFiles, countByFile }
}

describe('无参 useAcnr() 登记守卫（D9 T27）', () => {
  const { noArgFiles } = scanRepository()
  const registered = new Set(ACNR_CATALOG_ONLY_CALLERS)

  it('仓库里零参 useAcnr() 的文件集合恰好等于登记集合', () => {
    const extra = [...noArgFiles].filter((f) => !registered.has(f)).sort()
    const missing = [...registered].filter((f) => !noArgFiles.has(f)).sort()
    expect(extra, `未登记的无参 useAcnr()（应带当前项目）：\n${extra.join('\n')}`).toEqual([])
    expect(missing, `登记了却已无无参调用（失效条目）：\n${missing.join('\n')}`).toEqual([])
  })

  it('登记集合里的文件都真实存在', () => {
    const gone = [...registered].filter((f) => !existsSync(join(SRC, f)))
    expect(gone, `登记指向不存在的文件：\n${gone.join('\n')}`).toEqual([])
  })

  it('扫描有命中（防空转）', () => {
    // 登记集合非空 ⇒ 扫描必然命中这些文件；否则说明扫描器失效。
    expect(registered.size).toBeGreaterThan(0)
    expect(noArgFiles.size).toBe(registered.size)
  })
})
