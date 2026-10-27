/**
 * acnrArchitectureStatusDoc.spec.ts — 架构提案「现状」节前端组件行的符号核对（T32 / 段四审计 F4-02）
 *
 * 后端守卫 backend/tests/acnr/test_acnr_architecture_status_doc.py 用 Python AST 核对后端行，
 * 前端行它只能核对文件存在。本守卫补上前端：用 TypeScript 编译器 API 解析「已落地：组件」表里
 * 类型为「前端」的模块，断言所列符号确实被导出、所列测试文件里确有 it / test 用例。
 *
 * 登记制（段四复审第 2 轮 F4-02 残留二）：前端行的「组件」描述也是陈述，必须在 FRONTEND_CLAIMS 里逐字登记
 * 并绑定编译器 API 判据（例如「按项目订阅失效」= useAcnr 首参为 projectId 且调用 subscribeInvalidation）；
 * 未登记的描述、判据不成立、登记表里表格已不存在的描述（失效条目）都打红。后端登记制守卫见
 * backend/tests/acnr/test_acnr_status_doc_statements.py。
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

function exportedFunction(sf: ts.SourceFile, name: string): ts.FunctionDeclaration | undefined {
  return sf.statements.find((st): st is ts.FunctionDeclaration =>
    ts.isFunctionDeclaration(st) && st.name?.text === name
    && (ts.getCombinedModifierFlags(st) & ts.ModifierFlags.Export) !== 0)
}

function paramNames(fn: ts.FunctionDeclaration): string[] {
  return fn.parameters.map((p) => (ts.isIdentifier(p.name) ? p.name.text : ''))
}

function callsIdentifier(node: ts.Node, name: string): boolean {
  let hit = false
  const visit = (n: ts.Node) => {
    if (hit) return
    if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && n.expression.text === name) {
      hit = true
      return
    }
    ts.forEachChild(n, visit)
  }
  visit(node)
  return hit
}

/** 前端组件行「组件」描述 → 编译器 API 判据（返回不成立的原因；登记制：未登记的描述即红）。 */
const FRONTEND_CLAIMS: Record<string, (sf: ts.SourceFile) => string[]> = {
  '前端 ACNR SDK，按项目订阅失效': (sf) => {
    const problems: string[] = []
    const use = exportedFunction(sf, 'useAcnr')
    const sub = exportedFunction(sf, 'subscribeInvalidation')
    if (!use || paramNames(use)[0] !== 'projectId') problems.push('useAcnr 的首个参数须为 projectId（按项目）')
    if (!sub || paramNames(sub)[0] !== 'projectId') problems.push('subscribeInvalidation 的首个参数须为 projectId')
    if (!use || !callsIdentifier(use, 'subscribeInvalidation')) problems.push('useAcnr 内须调用 subscribeInvalidation 订阅失效')
    return problems
  },
  '前端当前项目上下文': (sf) => {
    const fn = exportedFunction(sf, 'useCurrentProjectId')
    if (!fn) return ['未导出函数 useCurrentProjectId']
    const problems: string[] = []
    if (fn.parameters.length !== 0) problems.push('useCurrentProjectId 不应有参数（从上下文取当前项目）')
    if (!callsIdentifier(fn, 'useRoute')) problems.push('须读取路由（useRoute）')
    if (!callsIdentifier(fn, 'useProjectStore')) problems.push('须读取项目 store（useProjectStore）')
    return problems
  },
  '高级查询单元格取值的请求构造与拒绝提示（业务视图与构建器的请求体由同一模块构造：有项目才发送单元格目标，构建器的项目与年度只随单元格目标发送、年度未知不发；拒绝、无权、解析不可用转成中文提示）': (sf) => {
    const problems: string[] = []
    /** 函数体内对 payload.<key> 的赋值，及其外层 if 条件文本（由内到外） */
    const guardsOf = (fn: ts.FunctionDeclaration, key: string): string[][] => {
      const out: string[][] = []
      const visit = (n: ts.Node, conds: string[]) => {
        if (ts.isIfStatement(n)) {
          ts.forEachChild(n, (c) => visit(c, c === n.expression ? conds : [n.expression.getText(sf), ...conds]))
          return
        }
        if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.EqualsToken
          && ts.isPropertyAccessExpression(n.left) && n.left.name.text === key) out.push(conds)
        ts.forEachChild(n, (c) => visit(c, conds))
      }
      visit(fn, [])
      return out
    }
    for (const name of ['buildBusinessPayload', 'buildBuilderPayload']) {
      const fn = exportedFunction(sf, name)
      if (!fn) { problems.push(`未导出函数 ${name}`); continue }
      const g = guardsOf(fn, 'acnr_targets')
      if (!g.length || !g.every((c) => c.some((t) => t.includes('projectId')))) {
        problems.push(`${name}：acnr_targets 须只在有项目（条件含 projectId）时写入`)
      }
    }
    const builder = exportedFunction(sf, 'buildBuilderPayload')
    if (builder) {
      for (const key of ['project_id', 'year']) {
        const g = guardsOf(builder, key)
        if (!g.length || !g.every((c) => c.some((t) => t.includes('acnrTargets.length')))) {
          problems.push(`buildBuilderPayload：${key} 须只随单元格目标（条件含 acnrTargets.length）写入`)
        }
      }
      if (!guardsOf(builder, 'year').every((c) => c.some((t) => t.includes('isKnownYear')))) {
        problems.push('buildBuilderPayload：year 须只在年度已知（isKnownYear）时写入')
      }
    }
    const errText = exportedFunction(sf, 'queryErrorText')
    const literals = new Set<string>()
    if (errText) {
      const v = (n: ts.Node) => { if (ts.isStringLiteral(n)) literals.add(n.text); ts.forEachChild(n, v) }
      v(errText)
    }
    for (const want of ['无权访问该项目', '地址解析服务暂不可用，请稍后重试']) {
      if (!literals.has(want)) problems.push(`queryErrorText 须给出中文提示「${want}」`)
    }
    return problems
  },
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

  it('每行前端组件的描述都已登记判据，且判据成立（登记制）', () => {
    const problems: string[] = []
    for (const [name, , module] of rows) {
      const claim = FRONTEND_CLAIMS[name]
      if (!claim) { problems.push(`未登记的前端组件描述：${name}`); continue }
      const modPath = join(REPO, strip(module))
      if (!existsSync(modPath)) { problems.push(`${name}: 模块不存在 ${strip(module)}`); continue }
      const sf = ts.createSourceFile(modPath, readFileSync(modPath, 'utf-8'), ts.ScriptTarget.Latest, true)
      problems.push(...claim(sf).map((p) => `${name}：${p}`))
    }
    expect(problems, problems.join('\n')).toEqual([])
  })

  it('前端判据登记表没有失效条目', () => {
    const names = new Set(rows.map((r) => r[0]))
    const stale = Object.keys(FRONTEND_CLAIMS).filter((k) => !names.has(k))
    expect(stale, `登记表里表格已不存在的描述：${stale.join('、')}`).toEqual([])
  })
})
