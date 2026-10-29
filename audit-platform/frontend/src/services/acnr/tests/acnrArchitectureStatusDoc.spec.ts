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

/**
 * 写入条件的布尔式（RV9.3-02）：if / && / || 条件化成布尔式，函数体内 const 中间变量按初值展开（认得出
 * `withTargets`），子式按角色归成原子——P 有项目（projectId）、S 限定当前项目（scopeToProject）、
 * T 有单元格目标（acnrTargets.length / > 0 / !== 0 / >= 1）、Y 年度已知（isKnownYear(...)），其余按原文成独立原子。
 */
type BoolExpr = { k: 'atom'; key: string } | { k: 'const'; v: boolean } | { k: 'not'; e: BoolExpr }
  | { k: 'and' | 'or'; l: BoolExpr; r: BoolExpr }
const B_TRUE: BoolExpr = { k: 'const', v: true }
const bAnd = (l: BoolExpr, r: BoolExpr): BoolExpr => ({ k: 'and', l, r })
const bOr = (l: BoolExpr, r: BoolExpr): BoolExpr => ({ k: 'or', l, r })
const bNot = (e: BoolExpr): BoolExpr => ({ k: 'not', e })
const atom = (key: string): BoolExpr => ({ k: 'atom', key })

function constLocals(fn: ts.FunctionDeclaration): Map<string, ts.Expression> {
  const out = new Map<string, ts.Expression>()
  const visit = (n: ts.Node) => {
    if (ts.isVariableDeclarationList(n) && (n.flags & ts.NodeFlags.Const)) {
      for (const d of n.declarations) if (ts.isIdentifier(d.name) && d.initializer) out.set(d.name.text, d.initializer)
    }
    ts.forEachChild(n, visit)
  }
  visit(fn)
  return out
}

function atomRole(e: ts.Expression): string | null {
  const isTargetsLength = (x: ts.Expression) => ts.isPropertyAccessExpression(x) && x.name.text === 'length'
    && ts.isIdentifier(x.expression) && x.expression.text === 'acnrTargets'
  if ((ts.isIdentifier(e) && e.text === 'projectId') || (ts.isPropertyAccessExpression(e) && e.name.text === 'projectId')) return 'P'
  if (ts.isPropertyAccessExpression(e) && e.name.text === 'scopeToProject') return 'S'
  if (isTargetsLength(e)) return 'T'
  if (ts.isBinaryExpression(e) && isTargetsLength(e.left) && ts.isNumericLiteral(e.right)) {
    const op = e.operatorToken.kind
    const v = e.right.text
    if ((op === ts.SyntaxKind.GreaterThanToken && v === '0') || (op === ts.SyntaxKind.ExclamationEqualsEqualsToken && v === '0')
      || (op === ts.SyntaxKind.GreaterThanEqualsToken && v === '1')) return 'T'
  }
  if (ts.isCallExpression(e) && ts.isIdentifier(e.expression) && e.expression.text === 'isKnownYear') return 'Y'
  return null
}

function toBool(e: ts.Expression, sf: ts.SourceFile, locals: Map<string, ts.Expression>, depth = 0): BoolExpr {
  if (ts.isParenthesizedExpression(e)) return toBool(e.expression, sf, locals, depth)
  if (ts.isPrefixUnaryExpression(e) && e.operator === ts.SyntaxKind.ExclamationToken) return bNot(toBool(e.operand, sf, locals, depth))
  if (ts.isBinaryExpression(e) && e.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) {
    return bAnd(toBool(e.left, sf, locals, depth), toBool(e.right, sf, locals, depth))
  }
  if (ts.isBinaryExpression(e) && e.operatorToken.kind === ts.SyntaxKind.BarBarToken) {
    return bOr(toBool(e.left, sf, locals, depth), toBool(e.right, sf, locals, depth))
  }
  if (e.kind === ts.SyntaxKind.TrueKeyword) return B_TRUE
  if (e.kind === ts.SyntaxKind.FalseKeyword) return { k: 'const', v: false }
  if (ts.isIdentifier(e) && locals.has(e.text) && depth < 8) return toBool(locals.get(e.text)!, sf, locals, depth + 1)
  return atom(atomRole(e) ?? `其他:${e.getText(sf)}`)
}

/** 函数体内对 payload 的 key 的全部写入（属性赋值、字符串下标赋值、对象字面量属性）各自的条件（外层条件的合取）。 */
function writeGuards(fn: ts.FunctionDeclaration, sf: ts.SourceFile, key: string): BoolExpr[] {
  const locals = constLocals(fn)
  const out: BoolExpr[] = []
  const conj = (conds: BoolExpr[]) => conds.reduce((a, b) => bAnd(a, b), B_TRUE)
  const isKeyTarget = (n: ts.Expression) => (ts.isPropertyAccessExpression(n) && n.name.text === key)
    || (ts.isElementAccessExpression(n) && ts.isStringLiteral(n.argumentExpression) && n.argumentExpression.text === key)
  const visit = (n: ts.Node, conds: BoolExpr[]) => {
    if (ts.isIfStatement(n)) {
      const c = toBool(n.expression, sf, locals)
      visit(n.expression, conds)
      visit(n.thenStatement, [...conds, c])
      if (n.elseStatement) visit(n.elseStatement, [...conds, bNot(c)])
      return
    }
    if (ts.isConditionalExpression(n)) {
      const c = toBool(n.condition, sf, locals)
      visit(n.condition, conds)
      visit(n.whenTrue, [...conds, c])
      visit(n.whenFalse, [...conds, bNot(c)])
      return
    }
    if (ts.isBinaryExpression(n) && (n.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken
      || n.operatorToken.kind === ts.SyntaxKind.BarBarToken)) {
      const c = toBool(n.left, sf, locals)
      visit(n.left, conds)
      visit(n.right, [...conds, n.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken ? c : bNot(c)])
      return
    }
    if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.EqualsToken && isKeyTarget(n.left)) out.push(conj(conds))
    if (ts.isPropertyAssignment(n) && (ts.isIdentifier(n.name) || ts.isStringLiteral(n.name)) && n.name.text === key) out.push(conj(conds))
    ts.forEachChild(n, (c) => visit(c, conds))
  }
  if (fn.body) visit(fn.body, [])
  return out
}

function atomsOf(e: BoolExpr, acc = new Set<string>()): Set<string> {
  if (e.k === 'atom') acc.add(e.key)
  else if (e.k === 'not') atomsOf(e.e, acc)
  else if (e.k === 'and' || e.k === 'or') { atomsOf(e.l, acc); atomsOf(e.r, acc) }
  return acc
}

function evalBool(e: BoolExpr, env: Record<string, boolean>): boolean {
  switch (e.k) {
    case 'atom': return env[e.key]
    case 'const': return e.v
    case 'not': return !evalBool(e.e, env)
    case 'and': return evalBool(e.l, env) && evalBool(e.r, env)
    default: return evalBool(e.l, env) || evalBool(e.r, env)
  }
}

/** 真值表穷举：返回使 pred 不成立的第一组取值（中文描述），全部成立返回 null。 */
function counterExample(exprs: BoolExpr[], pred: (vals: boolean[]) => boolean): string | null {
  const keys = [...exprs.reduce((s, e) => atomsOf(e, s), new Set<string>(['P', 'S', 'T', 'Y']))].sort()
  for (let mask = 0; mask < 1 << keys.length; mask++) {
    const env: Record<string, boolean> = {}
    keys.forEach((k, i) => { env[k] = !!(mask & (1 << i)) })
    if (!pred(exprs.map((e) => evalBool(e, env)))) return keys.map((k) => `${k}=${env[k] ? '真' : '假'}`).join(' ')
  }
  return null
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
  '高级查询单元格取值的请求构造与拒绝提示（业务视图与构建器的请求体由同一模块构造：有项目且有单元格目标才发送单元格目标；构建器的项目与年度在限定当前项目或带单元格目标时发送、年度未知不发；拒绝、无权、解析不可用转成中文提示）': (sf) => {
    const problems: string[] = []
    // RV9.3-02：按写入条件的真值表判定（不按条件文本找子串），认得出 withTargets 这类中间变量
    for (const name of ['buildBusinessPayload', 'buildBuilderPayload']) {
      const fn = exportedFunction(sf, name)
      if (!fn) { problems.push(`未导出函数 ${name}`); continue }
      const g = writeGuards(fn, sf, 'acnr_targets')
      // 任一写入点条件为真 ⇒ 有项目且有单元格目标
      const bad = g.length ? counterExample([...g, atom('P'), atom('T')],
        (v) => v.slice(0, g.length).every((w) => !w) || (v[g.length] && v[g.length + 1])) : '没有写入'
      if (bad) problems.push(`${name}：acnr_targets 须只在有项目且有单元格目标时写入（反例：${bad}）`)
    }
    const builder = exportedFunction(sf, 'buildBuilderPayload')
    if (builder) {
      // 期望：project_id 恰在 P ∧ (S ∨ T) 时写入；year 恰在 P ∧ (S ∨ T) ∧ Y 时写入（写入条件 = 各写入点条件的析取）
      const sent = bAnd(atom('P'), bOr(atom('S'), atom('T')))
      for (const [key, want, label] of [
        ['project_id', sent, '有项目且（限定当前项目或有单元格目标）'],
        ['year', bAnd(sent, atom('Y')), '有项目且（限定当前项目或有单元格目标）且年度已知（isKnownYear）'],
      ] as const) {
        const g = writeGuards(builder, sf, key)
        if (!g.length) { problems.push(`buildBuilderPayload：没有写入 ${key}`); continue }
        const when = g.reduce((a, b) => bOr(a, b))
        const bad = counterExample([when, want], ([a, b]) => a === b)
        if (bad) problems.push(`buildBuilderPayload：${key} 的写入条件须恰为「${label}」（反例：${bad}）`)
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
  '底稿短链页（`/workpapers/:wpId` 定位后替换到底稿编辑器、保留 sheet / cell；失败显示中文原因不跳转）与后端跳转路由形态契约': (sf) => {
    const problems: string[] = []
    const fn = exportedFunction(sf, 'resolveShortLink')
    if (!fn) return ['未导出函数 resolveShortLink']
    if (!callsIdentifier(fn, 'workpaperEditorRoute')) problems.push('resolveShortLink 须用 workpaperEditorRoute 生成编辑器路由（不手拼路径）')
    if (!callsIdentifier(fn, 'shortLinkQuery')) problems.push('resolveShortLink 须经 shortLinkQuery 把查询串带过去')
    if (!/\/api\/acnr\/workpapers\/\$\{/.test(fn.getText(sf))) problems.push('resolveShortLink 须调定位端点 /api/acnr/workpapers/{id}/locate')
    const routeFile = join(REPO, 'audit-platform/frontend/src/router/domains/workpapers.ts')
    if (!readFileSync(routeFile, 'utf-8').includes("path: 'workpapers/:wpId'")) problems.push('底稿域路由表未登记短链 workpapers/:wpId')
    if (!existsSync(join(REPO, 'audit-platform/frontend/src/router/__tests__/backendRouteShapes.contract.spec.ts'))) {
      problems.push('缺后端跳转路由形态契约 backendRouteShapes.contract.spec.ts')
    }
    return problems
  },
  '前端显示名只读目录（选址器、高级查询选字段、公式管理与公式编辑三棵树，公式选址器、地址库搜索、已选字段、取值结果区与索引 chip 都读目录的 display_label / cell_label，前端只按编码排序、父节点标题加科目简称；停用 cell 由同一谓词过滤）': (sf) => {
    const problems: string[] = []
    const sort = exportedFunction(sf, 'sortSheetsForGroup')
    const head = exportedFunction(sf, 'groupHeaderLabel')
    // 函数体内读取的属性名（AST，注释与字符串不计）
    const read = (fn: ts.Node | undefined) => {
      const s = new Set<string>()
      const v = (n: ts.Node) => { if (ts.isPropertyAccessExpression(n)) s.add(n.name.text); ts.forEachChild(n, v) }
      if (fn) v(fn)
      return s
    }
    const sortReads = read(sort)
    if (!sort || !sortReads.has('display_label')) problems.push('sortSheetsForGroup 须读 display_label 作标签')
    for (const p of ['sheet_name', 'mapped_sheet_name', 'account_name']) if (sortReads.has(p)) problems.push(`sortSheetsForGroup 不得读 ${p} 拼名`)
    if (!head || !read(head).has('account_name')) problems.push('groupHeaderLabel 须读科目简称 account_name')
    for (const gone of ['composeSheetLabelsForGroup', 'cleanSheetLabelName']) if (exportedFunction(sf, gone)) problems.push(`不应再导出 ${gone}`)
    for (const f of ['audit-platform/frontend/src/acnrDisplaySingleSource.spec.ts', 'audit-platform/frontend/src/services/acnr/cellListing.ts']) {
      if (!existsSync(join(REPO, f))) problems.push(`缺 ${f}`)
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
