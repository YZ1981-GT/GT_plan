/**
 * 测试基座不得在顶层 import 应用模块（spec platform-global-display-settings-closure A4）。
 *
 * 回归：`setup.ts` 顶层 `await import('@/stores/displayPrefs')` 在测试文件自己的 `vi.mock` 生效之前
 * 执行，把 displayPrefs → project → services/auditPlatformApi 这条链以真实实现塞进模块注册表；
 * 之后测试文件 mock `@/services/auditPlatformApi` 不再生效，31 个用例的 spy 变成零调用、组件真发请求。
 * 判据是 AST：顶层只许 import 测试基座自己的东西（`node:*`、vitest、相对路径），`@/` 一律进 beforeEach。
 */
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import ts from 'typescript'

const SETUP_PATH = resolve(dirname(fileURLToPath(import.meta.url)), '../setup.ts')

/** 返回顶层（不在任何函数体内）出现的模块说明符。 */
function topLevelSpecifiers(source: string): string[] {
  const file = ts.createSourceFile('setup.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const found: string[] = []
  const visit = (node: ts.Node, insideFunction: boolean): void => {
    const entersFunction = ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node)
      || ts.isArrowFunction(node) || ts.isMethodDeclaration(node)
    if (!insideFunction) {
      if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
        found.push(node.moduleSpecifier.text)
      }
      if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword) {
        const [arg] = node.arguments
        if (arg && ts.isStringLiteral(arg)) found.push(arg.text)
      }
    }
    node.forEachChild((child) => visit(child, insideFunction || entersFunction))
  }
  visit(file, false)
  return found
}

describe('测试基座 setup.ts', () => {
  const source = readFileSync(SETUP_PATH, 'utf-8')

  it('顶层不 import 任何 @/ 应用模块', () => {
    const specifiers = topLevelSpecifiers(source)
    expect(specifiers.length, '扫描口径失效：一个顶层 import 都没找到').toBeGreaterThan(0)
    expect(specifiers.filter((s) => s.startsWith('@/'))).toEqual([])
  })

  it('偏好初始化仍在用例边界里按需加载（判据非空分母）', () => {
    const file = ts.createSourceFile('setup.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
    let lazyPrefsImports = 0
    const visit = (node: ts.Node, insideFunction: boolean): void => {
      const entersFunction = ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node)
        || ts.isArrowFunction(node) || ts.isMethodDeclaration(node)
      if (insideFunction && ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword) {
        const [arg] = node.arguments
        if (arg && ts.isStringLiteral(arg) && arg.text === '@/stores/displayPrefs') lazyPrefsImports += 1
      }
      node.forEachChild((child) => visit(child, insideFunction || entersFunction))
    }
    visit(file, false)
    expect(lazyPrefsImports).toBe(1)
  })

  it('变异反证：把同一条 import 挪回顶层即判失败', () => {
    const mutated = "import { useDisplayPrefsStore } from '@/stores/displayPrefs'\n" + source
    expect(topLevelSpecifiers(mutated).filter((s) => s.startsWith('@/'))).toEqual(['@/stores/displayPrefs'])
  })
})
