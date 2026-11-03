/**
 * Playwright 用例目录必须排除在 vitest 之外（spec trim-generation-plan-followup-optimizations 7.2 全量回归抓到）。
 *
 * vitest 的 include 是 `**\/*.spec.ts`，会把 Playwright 用例一起收进来；Playwright 的 `test()` / `test.describe()`
 * 在 vitest 里一调就抛「Playwright Test did not expect test.describe() to be called here」，整个文件红。
 * 新增 `playwright*.config.ts`（或改它的 testDir）时，必须把 `<testDir>/**` 同步进 vitest.config.ts 的 exclude。
 * 两边都用 TS AST 取字面量；取不到（写成变量 / 表达式）直接打红，不静默跳过。
 */
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

const FRONTEND = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')

function parse(file: string): ts.SourceFile {
  return ts.createSourceFile(file, readFileSync(resolve(FRONTEND, file), 'utf-8'), ts.ScriptTarget.Latest, true,
    ts.ScriptKind.TS)
}

/** 任意深度里名为 key 的对象属性的初始化表达式 */
function propertyValues(sf: ts.SourceFile, key: string): ts.Expression[] {
  const out: ts.Expression[] = []
  const visit = (node: ts.Node): void => {
    if (ts.isPropertyAssignment(node) && (ts.isIdentifier(node.name) || ts.isStringLiteral(node.name))
      && node.name.text === key) out.push(node.initializer)
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return out
}

function literal(expr: ts.Expression): string | null {
  return ts.isStringLiteral(expr) || ts.isNoSubstitutionTemplateLiteral(expr) ? expr.text : null
}

function normalizeDir(dir: string): string {
  return dir.replace(/\\/g, '/').replace(/^\.\//, '').replace(/\/+$/, '')
}

const PLAYWRIGHT_CONFIGS = readdirSync(FRONTEND).filter((name) => /^playwright[.-][\w.-]*config\.ts$/.test(name)).sort()

function testDirOf(file: string): string | null {
  const values = propertyValues(parse(file), 'testDir')
  if (values.length !== 1) return null
  const text = literal(values[0])
  return text === null ? null : normalizeDir(text)
}

function vitestExclude(): string[] | null {
  const values = propertyValues(parse('vitest.config.ts'), 'exclude')
  if (values.length !== 1 || !ts.isArrayLiteralExpression(values[0])) return null
  const items = values[0].elements.map((el) => literal(el as ts.Expression))
  return items.every((item): item is string => item !== null) ? items : null
}

describe('Playwright 用例目录排除在 vitest 之外', () => {
  it('自检：能找到主配置与独立配置、能读出 vitest 的 exclude（判据不空转）', () => {
    expect(PLAYWRIGHT_CONFIGS).toContain('playwright.config.ts')
    expect(PLAYWRIGHT_CONFIGS).toContain('playwright.readonly-uat.config.ts')
    expect(testDirOf('playwright.config.ts')).toBe('e2e')
    expect(vitestExclude()).toContain('e2e/**')
  })

  it('每个 playwright*.config.ts 都有唯一的字面量 testDir', () => {
    const unreadable = PLAYWRIGHT_CONFIGS.filter((file) => testDirOf(file) === null)
    expect(unreadable, 'testDir 必须是唯一的字符串字面量（否则本守卫无法核对 vitest 排除）').toEqual([])
  })

  it('每个 Playwright testDir 都在 vitest.config.ts 的 exclude 里', () => {
    const exclude = vitestExclude()
    expect(exclude, 'vitest.config.ts 的 test.exclude 必须是字符串字面量数组').not.toBeNull()
    const missing = PLAYWRIGHT_CONFIGS
      .map((file) => ({ file, dir: testDirOf(file) }))
      .filter(({ dir }) => dir !== null && !exclude!.includes(`${dir}/**`))
      .map(({ file, dir }) => `${file} → ${dir}/**`)
    expect(missing, 'vitest 会把这些 Playwright 用例当单测跑、整文件报错；请加进 vitest.config.ts 的 exclude').toEqual([])
  })
})
