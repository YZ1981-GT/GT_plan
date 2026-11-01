/**
 * 写请求必须按 HTTP 状态码判成功（formula-writer-ownership-and-stale R4 / ADR-WOS-06）。
 *
 * 生产源码中的 POST / PUT / PATCH / DELETE 不得用宽 `validateStatus` 把 4xx/5xx 放进成功分支。
 * 扫描器使用 TypeScript Compiler API，能识别导入别名、包装客户端和局部配置变量；测试夹具不进生产分母。
 * 若业务明确把某个非 2xx 当正常状态，必须用严格相等显式列举，并在同一函数内按 response.status 处理。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import ts from 'typescript'
import { parse as parseSfc } from '@vue/compiler-sfc'
import { describe, expect, it } from 'vitest'

const SRC = resolve(__dirname, '..')
const SOURCE_EXT = /\.(?:ts|tsx|vue)$/
const WRITE_METHODS = new Set(['post', 'put', 'patch', 'delete'])

interface SourceUnit {
  sourceFile: ts.SourceFile
  baseLine: number
}

export interface WriteStatusFinding {
  file: string
  line: number
  method: string
  predicate: string
  reason: 'accepts-error-range' | 'unsupported-predicate' | 'unhandled-explicit-status'
  acceptedErrorStatuses: number[]
}

export function isTestSourcePath(posixPath: string): boolean {
  return (
    /(?:^|\/)(?:__tests__|test|tests)(?:\/|$)/.test(posixPath)
    || /\.(?:spec|test|stories)\.[cm]?[jt]sx?$/.test(posixPath)
    || /(?:^|\/)test_[^/]+\.[cm]?[jt]sx?$/.test(posixPath)
  )
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

function sourceUnits(file: string, text: string): SourceUnit[] {
  const make = (code: string, kind: ts.ScriptKind, baseLine = 0): SourceUnit => ({
    sourceFile: ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, kind),
    baseLine,
  })
  if (!file.endsWith('.vue')) {
    return [make(text, file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)]
  }
  const { descriptor } = parseSfc(text, { filename: file })
  return [descriptor.script, descriptor.scriptSetup]
    .filter((block): block is NonNullable<typeof block> => !!block?.content)
    .map((block) => make(block.content, ts.ScriptKind.TS, Math.max(0, block.loc.start.line - 1)))
}

function unwrap<T extends ts.Node>(node: T): ts.Node {
  let current: ts.Node = node
  while (
    ts.isParenthesizedExpression(current)
    || ts.isAsExpression(current)
    || ts.isTypeAssertionExpression(current)
    || ts.isNonNullExpression(current)
    || ts.isSatisfiesExpression(current)
  ) current = current.expression
  return current
}

function propertyName(node: ts.PropertyName): string | null {
  if (ts.isIdentifier(node) || ts.isStringLiteral(node) || ts.isNumericLiteral(node)) return node.text
  return null
}

function calledMethod(call: ts.CallExpression): string | null {
  const expression = unwrap(call.expression)
  if (ts.isPropertyAccessExpression(expression)) return expression.name.text
  if (ts.isElementAccessExpression(expression)) {
    const key = expression.argumentExpression && unwrap(expression.argumentExpression)
    return key && ts.isStringLiteral(key) ? key.text : null
  }
  return null
}

/** 唯一命名的局部对象配置可安全解引用；同名多定义时 fail-closed，不猜作用域。 */
function objectInitializers(sf: ts.SourceFile): Map<string, ts.ObjectLiteralExpression | null> {
  const found = new Map<string, ts.ObjectLiteralExpression | null>()
  const visit = (node: ts.Node) => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      const value = unwrap(node.initializer)
      if (ts.isObjectLiteralExpression(value)) {
        found.set(node.name.text, found.has(node.name.text) ? null : value)
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return found
}

function resolveObject(
  node: ts.Expression | undefined,
  objects: Map<string, ts.ObjectLiteralExpression | null>,
): ts.ObjectLiteralExpression | null {
  if (!node) return null
  const value = unwrap(node)
  if (ts.isObjectLiteralExpression(value)) return value
  if (ts.isIdentifier(value)) return objects.get(value.text) ?? null
  return null
}

function validateStatusInitializer(config: ts.ObjectLiteralExpression): ts.Expression | null {
  for (const member of config.properties) {
    if (ts.isPropertyAssignment(member) && propertyName(member.name) === 'validateStatus') return member.initializer
    if (ts.isMethodDeclaration(member) && propertyName(member.name) === 'validateStatus') return member as unknown as ts.Expression
  }
  return null
}

type Scalar = number | boolean | 'unknown'

function evalStatusExpression(node: ts.Expression, parameter: string, status: number): Scalar {
  const value = unwrap(node)
  if (ts.isIdentifier(value)) {
    if (value.text === parameter) return status
    if (value.text === 'true') return true
    if (value.text === 'false') return false
    return 'unknown'
  }
  if (ts.isNumericLiteral(value)) return Number(value.text)
  if (value.kind === ts.SyntaxKind.TrueKeyword) return true
  if (value.kind === ts.SyntaxKind.FalseKeyword) return false
  if (ts.isPrefixUnaryExpression(value) && value.operator === ts.SyntaxKind.ExclamationToken) {
    const operand = evalStatusExpression(value.operand, parameter, status)
    return typeof operand === 'boolean' ? !operand : 'unknown'
  }
  if (!ts.isBinaryExpression(value)) return 'unknown'
  const left = evalStatusExpression(value.left, parameter, status)
  const right = evalStatusExpression(value.right, parameter, status)
  const op = value.operatorToken.kind
  if (op === ts.SyntaxKind.AmpersandAmpersandToken) {
    return typeof left === 'boolean' && typeof right === 'boolean' ? left && right : 'unknown'
  }
  if (op === ts.SyntaxKind.BarBarToken) {
    return typeof left === 'boolean' && typeof right === 'boolean' ? left || right : 'unknown'
  }
  if (left === 'unknown' || right === 'unknown') return 'unknown'
  switch (op) {
    case ts.SyntaxKind.LessThanToken: return left < right
    case ts.SyntaxKind.LessThanEqualsToken: return left <= right
    case ts.SyntaxKind.GreaterThanToken: return left > right
    case ts.SyntaxKind.GreaterThanEqualsToken: return left >= right
    case ts.SyntaxKind.EqualsEqualsToken:
    case ts.SyntaxKind.EqualsEqualsEqualsToken: return left === right
    case ts.SyntaxKind.ExclamationEqualsToken:
    case ts.SyntaxKind.ExclamationEqualsEqualsToken: return left !== right
    default: return 'unknown'
  }
}

function isFunctionNode(node: ts.Node): node is ts.FunctionLikeDeclaration {
  return ts.isArrowFunction(node) || ts.isFunctionExpression(node) || ts.isFunctionDeclaration(node)
    || ts.isMethodDeclaration(node) || ts.isGetAccessorDeclaration(node) || ts.isSetAccessorDeclaration(node)
}

function singleReturn(body: ts.ConciseBody): ts.Expression | null {
  if (!ts.isBlock(body)) return body
  const returns: ts.Expression[] = []
  const visit = (node: ts.Node) => {
    if (node !== body && isFunctionNode(node)) return
    if (ts.isReturnStatement(node) && node.expression) returns.push(node.expression)
    else ts.forEachChild(node, visit)
  }
  visit(body)
  return returns.length === 1 ? returns[0] : null
}

function predicateParts(initializer: ts.Node): { parameter: string; expression: ts.Expression } | null {
  if (!isFunctionNode(initializer) || !initializer.parameters.length || !initializer.body) return null
  const parameter = initializer.parameters[0].name
  if (!ts.isIdentifier(parameter)) return null
  const expression = singleReturn(initializer.body)
  return expression ? { parameter: parameter.text, expression } : null
}

function explicitEqualityStatuses(expression: ts.Expression, parameter: string): Set<number> {
  const statuses = new Set<number>()
  const visit = (node: ts.Node) => {
    if (ts.isBinaryExpression(node)) {
      const op = node.operatorToken.kind
      if (op === ts.SyntaxKind.EqualsEqualsToken || op === ts.SyntaxKind.EqualsEqualsEqualsToken) {
        const left = unwrap(node.left)
        const right = unwrap(node.right)
        if (ts.isIdentifier(left) && left.text === parameter && ts.isNumericLiteral(right)) statuses.add(Number(right.text))
        if (ts.isIdentifier(right) && right.text === parameter && ts.isNumericLiteral(left)) statuses.add(Number(left.text))
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(expression)
  return statuses
}

function enclosingFunctionOrFile(node: ts.Node): ts.Node {
  let current: ts.Node = node
  while (current.parent) {
    current = current.parent
    if (isFunctionNode(current) || ts.isSourceFile(current)) return current
  }
  return node.getSourceFile()
}

function isStatusValue(node: ts.Node): boolean {
  const value = unwrap(node)
  return (ts.isIdentifier(value) && value.text === 'status')
    || (ts.isPropertyAccessExpression(value) && value.name.text === 'status')
}

/** 显式放行的非 2xx 必须在同一函数、该请求之后按响应 status 分支处理。 */
function handlesStatuses(call: ts.CallExpression, statuses: number[]): boolean {
  const root = enclosingFunctionOrFile(call)
  const handled = new Set<number>()
  const visit = (node: ts.Node) => {
    if (node !== root && isFunctionNode(node)) return
    if (node.getStart() > call.end && ts.isBinaryExpression(node)) {
      const op = node.operatorToken.kind
      if (op === ts.SyntaxKind.EqualsEqualsToken || op === ts.SyntaxKind.EqualsEqualsEqualsToken) {
        const left = unwrap(node.left)
        const right = unwrap(node.right)
        if (isStatusValue(left) && ts.isNumericLiteral(right)) handled.add(Number(right.text))
        if (isStatusValue(right) && ts.isNumericLiteral(left)) handled.add(Number(left.text))
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(root)
  return statuses.every((status) => handled.has(status))
}

export function scanWriteStatusSource(file: string, text: string): WriteStatusFinding[] {
  const findings: WriteStatusFinding[] = []
  for (const { sourceFile: sf, baseLine } of sourceUnits(file, text)) {
    const objects = objectInitializers(sf)
    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node)) {
        const method = calledMethod(node)
        if (method && WRITE_METHODS.has(method)) {
          const configArg = node.arguments[method === 'delete' ? 1 : 2]
          const config = resolveObject(configArg, objects)
          const initializer = config && validateStatusInitializer(config)
          if (initializer) {
            const parts = predicateParts(initializer)
            const line = baseLine + sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1
            const base = { file, line, method, predicate: initializer.getText(sf) }
            if (!parts) {
              findings.push({ ...base, reason: 'unsupported-predicate', acceptedErrorStatuses: [] })
            } else {
              const accepted: number[] = []
              let unsupported = false
              for (let status = 400; status < 600; status++) {
                const result = evalStatusExpression(parts.expression, parts.parameter, status)
                if (result === 'unknown') unsupported = true
                else if (result === true) accepted.push(status)
              }
              if (unsupported) {
                findings.push({ ...base, reason: 'unsupported-predicate', acceptedErrorStatuses: accepted })
              } else if (accepted.length) {
                const explicit = explicitEqualityStatuses(parts.expression, parts.parameter)
                const explicitlyEnumerated = accepted.every((status) => explicit.has(status))
                if (!explicitlyEnumerated) {
                  findings.push({ ...base, reason: 'accepts-error-range', acceptedErrorStatuses: accepted })
                } else if (!handlesStatuses(node, accepted)) {
                  findings.push({ ...base, reason: 'unhandled-explicit-status', acceptedErrorStatuses: accepted })
                }
              }
            }
          }
        }
      }
      ts.forEachChild(node, visit)
    }
    visit(sf)
  }
  return findings
}

const PRODUCTION_FILES = walk(SRC).filter((absolute) => {
  const rel = relative(SRC, absolute).replace(/\\/g, '/')
  return !isTestSourcePath(rel) && !absolute.endsWith('.d.ts')
})

const PRODUCTION_FINDINGS = PRODUCTION_FILES.flatMap((absolute) => {
  const rel = relative(SRC, absolute).replace(/\\/g, '/')
  return scanWriteStatusSource(rel, readFileSync(absolute, 'utf-8'))
})

function describeFinding(finding: WriteStatusFinding): string {
  const statuses = finding.acceptedErrorStatuses
  const accepted = statuses.length > 8
    ? `${statuses[0]}…${statuses[statuses.length - 1]}（${statuses.length} 个）`
    : statuses.join(',') || '无法静态求值'
  return `${finding.file}:${finding.line} ${finding.method.toUpperCase()} ${finding.reason}；放行=${accepted}；${finding.predicate}`
}

describe('写请求 validateStatus 状态码守卫（formula-writer-ownership-and-stale R4）', () => {
  it('扫描范围非空且生产写请求没有宽放行或未处理的显式非 2xx', () => {
    expect(PRODUCTION_FILES.length).toBeGreaterThan(1000)
    expect(PRODUCTION_FINDINGS.map(describeFinding)).toEqual([])
  })

  it('抓得到导入别名、包装客户端、配置变量和四种写方法的宽放行', () => {
    const source = `
      import { api as renamed } from '@/services/apiProxy'
      const cfg = { validateStatus: (status: number) => status < 600 }
      async function run(deps: any) {
        await renamed.post('/a', {}, cfg)
        await deps.api.put('/b', {}, { validateStatus: (s: number) => s >= 200 })
        await deps.clients.httpApi['patch']('/c', {}, { validateStatus: () => true })
        await deps.http.delete('/d', { validateStatus(s: number) { return s < 500 } })
      }
    `
    const findings = scanWriteStatusSource('synthetic.ts', source)
    expect(findings.map((f) => f.method)).toEqual(['post', 'put', 'patch', 'delete'])
    expect(findings.every((f) => f.reason !== 'unhandled-explicit-status')).toBe(true)
  })

  it('显式 404 仅在同一函数处理 response.status 时合法', () => {
    const handled = `
      async function run(client: any) {
        const response = await client.post('/already-done', {}, {
          validateStatus: (status: number) => (status >= 200 && status < 300) || status === 404,
        })
        if (response.status === 404) return null
        return response.data
      }
    `
    expect(scanWriteStatusSource('handled.ts', handled)).toEqual([])

    const unhandled = `
      async function run(client: any) {
        return client.post('/already-done', {}, {
          validateStatus: (status: number) => status < 300 || status === 404,
        })
      }
    `
    expect(scanWriteStatusSource('unhandled.ts', unhandled)).toEqual([
      expect.objectContaining({ reason: 'unhandled-explicit-status', acceptedErrorStatuses: [404] }),
    ])
  })

  it('标准 2xx 判定和 GET 兼容配置不误报，无法求值的写判定 fail-closed', () => {
    const safe = `
      await api.post('/ok', {}, { validateStatus: (s: number) => s >= 200 && s < 300 })
      await api.get('/blob', { validateStatus: (s: number) => s < 600 })
    `
    expect(scanWriteStatusSource('safe.ts', safe)).toEqual([])

    const unsupported = `
      const accepted = (s: number) => s < 600
      await api.post('/x', {}, { validateStatus: accepted })
    `
    expect(scanWriteStatusSource('unsupported.ts', unsupported)).toEqual([
      expect.objectContaining({ reason: 'unsupported-predicate' }),
    ])
  })

  it('测试夹具不进生产扫描分母，生产路径不会被误排除', () => {
    expect(isTestSourcePath('components/Foo.spec.ts')).toBe(true)
    expect(isTestSourcePath('components/__tests__/Foo.ts')).toBe(true)
    expect(isTestSourcePath('components/tests/fixture.ts')).toBe(true)
    expect(isTestSourcePath('components/Foo.test.tsx')).toBe(true)
    expect(isTestSourcePath('components/Foo.vue')).toBe(false)
    expect(isTestSourcePath('services/httpClient.ts')).toBe(false)
  })
})
