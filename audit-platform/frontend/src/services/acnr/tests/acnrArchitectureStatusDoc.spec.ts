/**
 * acnrArchitectureStatusDoc.spec.ts — 架构提案「现状」节前端组件行的符号核对（T32 / 段四审计 F4-02）
 *
 * 后端守卫 backend/tests/acnr/test_acnr_architecture_status_doc.py 用 Python AST 核对后端行，
 * 前端行它只能核对文件存在。本守卫补上前端：用 TypeScript 编译器 API 解析「已落地：组件」表里
 * 类型为「前端」的模块，断言所列符号确实被导出、所列测试文件里确有 it / test 用例。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { join, resolve } from 'node:path'
import ts from 'typescript'

const REPO = resolve(__dirname, '../../../../../..')
const DOC = join(REPO, 'docs/proposals/address-coordinate-name-registry-architecture.md')
const HEADING = '## 现状（2026-10-26）'
const END_MARKER = '> —— 现状节到此结束；以下为提案原文（未改动）——'
const SUB = '### 已落地：组件'

function cells(row: string): string[] {
  const parts = row.trim().split(/(?<!\\)\|/)
  return parts.slice(1, -1).map((s) => s.trim())
}

function strip(s: string): string {
  return s.trim().replace(/^`+|`+$/g, '').trim()
}

function frontendRows(): string[][] {
  const lines = readFileSync(DOC, 'utf-8').replace(/\r\n/g, '\n').split('\n')
  const start = lines.findIndex((l) => l.trim() === HEADING)
  const end = lines.findIndex((l, i) => i > start && l.trim() === END_MARKER)
  expect(start, '缺少现状节').toBeGreaterThanOrEqual(0)
  expect(end, '缺少现状节结束行').toBeGreaterThan(start)
  const section = lines.slice(start, end)
  const sub = section.findIndex((l) => l.trim() === SUB)
  expect(sub, `缺少子节 ${SUB}`).toBeGreaterThanOrEqual(0)
  const body: string[] = []
  for (const l of section.slice(sub + 1)) {
    if (l.startsWith('### ')) break
    body.push(l)
  }
  const tableRows = body.filter((l) => l.trim().startsWith('|')).slice(2).map(cells)
  return tableRows.filter((r) => r[1] === '前端')
}

function exportedNames(file: string): Set<string> {
  const sf = ts.createSourceFile(file, readFileSync(file, 'utf-8'), ts.ScriptTarget.Latest, true)
  const names = new Set<string>()
  const isExported = (n: ts.Node) =>
    (ts.getCombinedModifierFlags(n as ts.Declaration) & ts.ModifierFlags.Export) !== 0
  for (const st of sf.statements) {
    if ((ts.isFunctionDeclaration(st) || ts.isClassDeclaration(st) || ts.isInterfaceDeclaration(st)
      || ts.isTypeAliasDeclaration(st)) && st.name && isExported(st)) {
      names.add(st.name.text)
    } else if (ts.isVariableStatement(st) && isExported(st)) {
      for (const d of st.declarationList.declarations) {
        if (ts.isIdentifier(d.name)) names.add(d.name.text)
      }
    } else if (ts.isExportDeclaration(st) && st.exportClause && ts.isNamedExports(st.exportClause)) {
      for (const el of st.exportClause.elements) names.add(el.name.text)
    }
  }
  return names
}

function testCaseCount(file: string): number {
  const sf = ts.createSourceFile(file, readFileSync(file, 'utf-8'), ts.ScriptTarget.Latest, true)
  let n = 0
  const visit = (node: ts.Node) => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression)
      && (node.expression.text === 'it' || node.expression.text === 'test')) {
      n++
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return n
}

describe('架构提案现状节：前端组件行（TS 编译器 API）', () => {
  const rows = frontendRows()

  it('至少有一行前端组件（防空转）', () => {
    expect(rows.length).toBeGreaterThan(0)
  })

  it('每行模块导出所列符号、测试文件有用例', () => {
    const problems: string[] = []
    for (const [name, , module, symbols, test] of rows) {
      const modPath = join(REPO, strip(module))
      const testPath = join(REPO, strip(test))
      if (!existsSync(modPath)) { problems.push(`${name}: 模块不存在 ${strip(module)}`); continue }
      if (!existsSync(testPath)) { problems.push(`${name}: 测试不存在 ${strip(test)}`); continue }
      const exported = exportedNames(modPath)
      const want = symbols.split(/[、,，]/).map(strip).filter(Boolean)
      const absent = want.filter((s) => !exported.has(s))
      if (absent.length) problems.push(`${name}: ${strip(module)} 未导出 ${absent.join('、')}`)
      if (testCaseCount(testPath) === 0) problems.push(`${name}: ${strip(test)} 没有 it / test 用例`)
    }
    expect(problems, problems.join('\n')).toEqual([])
  })
})
