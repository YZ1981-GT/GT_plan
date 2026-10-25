/**
 * D7.3：前端 IPO 判定来源边界守卫。
 *
 * 本守卫只扫描 src/ 下的生产脚本（排除 __tests__），先提取 Vue 的 script，再用
 * TypeScript AST 识别声明、导入别名、调用和条件分支。不能用全局关键词计数：
 * F2 的中文 IPO_CATEGORIES、project_type、template_type 是历史兼容协议，不能被
 * 统一成核心 business_category 关键词。
 *
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4
 */
import { readFileSync } from 'node:fs'
import * as ts from 'typescript'
import { describe, expect, it } from 'vitest'
import {
  FRONTEND_SRC,
  toSrcRelative,
  walkSourceFiles,
} from '../../__tests__/_helpers/frontendSourceScan'

const CORE_REL = 'utils/ipoProjectUtils.ts'
const F2_REL = 'components/workpaper/composables/useF2SpecialFormData.ts'
const D4_REL = 'components/workpaper/composables/useD4CrossSheet.ts'
const A_PROGRAM_REL = 'composables/useAProgramData.ts'
const CORE_MODULE = '@/utils/ipoProjectUtils'

const EXPECTED_KEYWORDS = ['ipo', 'listed', 'neeq', 'restructuring', 'refinancing']
const EXPECTED_F2_CATEGORIES = ['IPO', '上市公司年审', '新三板', '重大资产重组']
const F2_CONTEXT_FIELDS = ['business_category', 'project_type', 'template_type']

// 只用于减少解析量，不参与任何通过/失败判定。候选一旦入选，所有定义、调用和
// 分支判断都由 TypeScript AST 完成；精确标识符不会被注释/字符串单独当作证据。
const AST_CANDIDATE_MARKERS = [
  'isIpoProject',
  'isF2IpoProject',
  'IPO_BIZ_KEYWORDS',
  'IPO_CATEGORIES',
  'isIpoGroupVisible',
  'project_type',
  'template_type',
]

interface SourceUnit {
  file: string
  code: string
  sourceFile: ts.SourceFile
  lineOffset: number
}

interface DefinitionRecord {
  unit: SourceUnit
  node: ts.FunctionDeclaration | ts.VariableDeclaration
  kind: 'function' | 'variable'
}

interface CallRecord {
  unit: SourceUnit
  node: ts.CallExpression
  localName: string
}

function relative(file: string): string {
  return toSrcRelative(file).replace(/\\/g, '/')
}

function lineOf(unit: SourceUnit, node: ts.Node): number {
  return unit.lineOffset + unit.sourceFile.getLineAndCharacterOfPosition(node.getStart(unit.sourceFile)).line + 1
}

function location(unit: SourceUnit, node: ts.Node): string {
  return `${relative(unit.file)}:${lineOf(unit, node)}`
}

function parseUnit(file: string, code: string, lineOffset = 0): SourceUnit {
  return {
    file,
    code,
    sourceFile: ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS),
    lineOffset,
  }
}

/** Vue 模板不参与判定；只把每个 script block 交给 TypeScript parser。 */
function unitsForFile(file: string, source: string): SourceUnit[] {
  if (!file.endsWith('.vue')) return [parseUnit(file, source)]

  const units: SourceUnit[] = []
  const scriptRe = /<script\b[^>]*>([\s\S]*?)<\/script>/gi
  let match: RegExpExecArray | null
  while ((match = scriptRe.exec(source)) !== null) {
    const code = match[1]
    const contentStart = match.index + match[0].indexOf(code)
    const lineOffset = source.slice(0, contentStart).split('\n').length - 1
    units.push(parseUnit(file, code, lineOffset))
  }
  return units
}

function loadProductionUnits(): SourceUnit[] {
  return walkSourceFiles(FRONTEND_SRC).flatMap((file) => {
    const source = readFileSync(file, 'utf-8')
    // 目录仍全量枚举，避免维护手写白名单；只有包含目标标识符的文件进入 AST。
    if (!AST_CANDIDATE_MARKERS.some((marker) => source.includes(marker))) return []
    return unitsForFile(file, source)
  })
}

function visit(unit: SourceUnit, callback: (node: ts.Node) => void): void {
  const walk = (node: ts.Node): void => {
    callback(node)
    ts.forEachChild(node, walk)
  }
  walk(unit.sourceFile)
}

function declarationName(node: ts.DeclarationName | undefined): string | null {
  if (!node) return null
  if (ts.isIdentifier(node) || ts.isStringLiteral(node)) return node.text
  return null
}

function functionDefinitions(units: SourceUnit[], name: string): DefinitionRecord[] {
  const found: DefinitionRecord[] = []
  for (const unit of units) {
    visit(unit, (node) => {
      if (ts.isFunctionDeclaration(node) && node.name?.text === name) {
        found.push({ unit, node, kind: 'function' })
      }
    })
  }
  return found
}

function variableDefinitions(units: SourceUnit[], name: string): DefinitionRecord[] {
  const found: DefinitionRecord[] = []
  for (const unit of units) {
    visit(unit, (node) => {
      if (ts.isVariableDeclaration(node) && declarationName(node.name) === name) {
        found.push({ unit, node, kind: 'variable' })
      }
    })
  }
  return found
}

function allNamedDefinitions(units: SourceUnit[], name: string): DefinitionRecord[] {
  return [...functionDefinitions(units, name), ...variableDefinitions(units, name)]
}

function hasExportModifier(node: ts.Node): boolean {
  // `export const X = ...` 的修饰符挂在 VariableStatement，声明节点要沿父链上查。
  let current: ts.Node | undefined = node
  while (current) {
    if (current.modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword)) return true
    current = current.parent
  }
  return false
}

function unwrapExpression(expression: ts.Expression): ts.Expression {
  let current = expression
  while (
    ts.isParenthesizedExpression(current)
    || ts.isAsExpression(current)
    || ts.isTypeAssertionExpression(current)
    || ts.isSatisfiesExpression(current)
  ) {
    current = current.expression
  }
  return current
}

function stringValue(expression: ts.Expression | undefined): string | null {
  if (!expression) return null
  const value = unwrapExpression(expression)
  return ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value) ? value.text : null
}

function propertyPath(expression: ts.Expression | undefined): string | null {
  if (!expression) return null
  const value = unwrapExpression(expression)
  if (ts.isIdentifier(value)) return value.text
  if (ts.isPropertyAccessExpression(value)) {
    const parent = propertyPath(value.expression)
    return parent ? `${parent}.${value.name.text}` : value.name.text
  }
  return null
}

function namedImportsFrom(unit: SourceUnit, moduleName: string): Map<string, string> {
  const aliases = new Map<string, string>()
  visit(unit, (node) => {
    if (!ts.isImportDeclaration(node) || stringValue(node.moduleSpecifier) !== moduleName) return
    const named = node.importClause?.namedBindings
    if (!named || !ts.isNamedImports(named)) return
    for (const element of named.elements) {
      const imported = element.propertyName?.text ?? element.name.text
      aliases.set(element.name.text, imported)
    }
  })
  return aliases
}

function coreCalls(units: SourceUnit[]): CallRecord[] {
  const found: CallRecord[] = []
  for (const unit of units) {
    const aliases = new Set(
      [...namedImportsFrom(unit, CORE_MODULE).entries()]
        .filter(([, imported]) => imported === 'isIpoProject')
        .map(([local]) => local),
    )
    if (!aliases.size) continue
    visit(unit, (node) => {
      if (!ts.isCallExpression(node)) return
      const callee = unwrapExpression(node.expression)
      if (ts.isIdentifier(callee) && aliases.has(callee.text)) {
        found.push({ unit, node, localName: callee.text })
      }
    })
  }
  return found
}

function wrapperCalls(units: SourceUnit[]): CallRecord[] {
  const found: CallRecord[] = []
  for (const unit of units) {
    visit(unit, (node) => {
      if (!ts.isCallExpression(node)) return
      const callee = unwrapExpression(node.expression)
      if (ts.isIdentifier(callee) && callee.text === 'isF2IpoProject') {
        found.push({ unit, node, localName: callee.text })
      }
    })
  }
  return found
}

function methodCalls(units: SourceUnit[], receiver: string, method: string): CallRecord[] {
  const found: CallRecord[] = []
  for (const unit of units) {
    visit(unit, (node) => {
      if (!ts.isCallExpression(node) || !ts.isPropertyAccessExpression(node.expression)) return
      if (node.expression.name.text !== method) return
      if (propertyPath(node.expression.expression) !== receiver) return
      found.push({ unit, node, localName: `${receiver}.${method}` })
    })
  }
  return found
}

function arrayStringValues(expression: ts.Expression | undefined): string[] | null {
  if (!expression) return null
  const value = unwrapExpression(expression)
  if (!ts.isArrayLiteralExpression(value)) return null
  const values: string[] = []
  for (const element of value.elements) {
    const text = stringValue(element as ts.Expression)
    if (text === null) return null
    values.push(text)
  }
  return values
}

function interfaceFieldNames(unit: SourceUnit, interfaceName: string): string[] {
  const fields: string[] = []
  visit(unit, (node) => {
    if (!ts.isInterfaceDeclaration(node) || node.name.text !== interfaceName) return
    for (const member of node.members) {
      if (ts.isPropertySignature(member)) {
        const name = declarationName(member.name)
        if (name) fields.push(name)
      }
    }
  })
  return fields
}

function isNullishBusinessCategory(expression: ts.Expression | undefined): boolean {
  if (!expression) return false
  const value = unwrapExpression(expression)
  return ts.isBinaryExpression(value)
    && value.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken
    && propertyPath(value.left) === 'ctx.business_category'
    && stringValue(value.right) === ''
}

function equalityBranch(expression: ts.Expression | undefined): string | null {
  if (!expression) return null
  const value = unwrapExpression(expression)
  if (!ts.isBinaryExpression(value) || value.operatorToken.kind !== ts.SyntaxKind.EqualsEqualsEqualsToken) return null
  const left = propertyPath(value.left)
  const right = stringValue(value.right)
  return left && right !== null ? `${left}=${right}` : null
}

function f2BranchShape(unit: SourceUnit): string[] {
  const definition = functionDefinitions([unit], 'isF2IpoProject')[0]
  if (!definition || !definition.node.body) return []
  const shape: string[] = []
  for (const statement of definition.node.body.statements) {
    if (ts.isIfStatement(statement)) {
      const condition = unwrapExpression(statement.expression)
      if (ts.isCallExpression(condition) && ts.isIdentifier(condition.expression)) {
        if (condition.expression.text === 'isCoreIpoProject' && condition.arguments.length === 1) {
          shape.push(isNullishBusinessCategory(condition.arguments[0]) ? 'core-business_category' : 'core-invalid')
        } else {
          shape.push(`call:${condition.expression.text}`)
        }
        continue
      }
      shape.push(equalityBranch(condition) ?? 'if-invalid')
      continue
    }
    if (ts.isReturnStatement(statement) && statement.expression) {
      const expression = unwrapExpression(statement.expression)
      if (
        ts.isCallExpression(expression)
        && ts.isPropertyAccessExpression(expression.expression)
        && propertyPath(expression.expression.expression) === 'IPO_CATEGORIES'
        && expression.expression.name.text === 'includes'
      ) {
        shape.push('IPO_CATEGORIES.includes')
      } else {
        shape.push('return-invalid')
      }
    }
  }
  return shape
}

function d4AllowedCategories(call: CallRecord): string[] | null {
  const second = call.node.arguments[1]
  if (!second) return null
  const value = unwrapExpression(second)
  if (!ts.isArrayLiteralExpression(value)) return null
  const categories: string[] = []
  for (const element of value.elements) {
    if (ts.isSpreadElement(element) && propertyPath(element.expression) === 'IPO_BIZ_KEYWORDS') {
      categories.push('...IPO_BIZ_KEYWORDS')
    } else {
      const text = stringValue(element as ts.Expression)
      if (text === null) return null
      categories.push(text)
    }
  }
  return categories
}

function sourceBoundaryViolations(units: SourceUnit[]): string[] {
  const errors: string[] = []
  const coreDefs = functionDefinitions(units, 'isIpoProject')
  const wrapperDefs = functionDefinitions(units, 'isF2IpoProject')
  const keywordDefs = variableDefinitions(units, 'IPO_BIZ_KEYWORDS')
  const categoryDefs = variableDefinitions(units, 'IPO_CATEGORIES')
  const adapterDefs = variableDefinitions(units, 'isIpoProject')
  const legacyDefs = allNamedDefinitions(units, 'isIpoGroupVisible')

  if (coreDefs.length !== 1 || relative(coreDefs[0]?.unit.file ?? '') !== CORE_REL) {
    errors.push(`isIpoProject 函数定义应仅有 1 个且位于 ${CORE_REL}：${coreDefs.map((d) => location(d.unit, d.node)).join(', ')}`)
  } else if (!hasExportModifier(coreDefs[0].node)) {
    errors.push(`isIpoProject 核心函数必须 export：${location(coreDefs[0].unit, coreDefs[0].node)}`)
  }

  if (wrapperDefs.length !== 1 || relative(wrapperDefs[0]?.unit.file ?? '') !== F2_REL) {
    errors.push(`isF2IpoProject wrapper 应仅有 1 个且位于 ${F2_REL}：${wrapperDefs.map((d) => location(d.unit, d.node)).join(', ')}`)
  } else if (!hasExportModifier(wrapperDefs[0].node)) {
    errors.push(`isF2IpoProject wrapper 必须 export：${location(wrapperDefs[0].unit, wrapperDefs[0].node)}`)
  }

  if (keywordDefs.length !== 1 || relative(keywordDefs[0]?.unit.file ?? '') !== CORE_REL) {
    errors.push(`IPO_BIZ_KEYWORDS 定义应仅有 1 个且位于 ${CORE_REL}：${keywordDefs.map((d) => location(d.unit, d.node)).join(', ')}`)
  } else if (!hasExportModifier(keywordDefs[0].node)) {
    errors.push(`IPO_BIZ_KEYWORDS 必须 export：${location(keywordDefs[0].unit, keywordDefs[0].node)}`)
  } else if (arrayStringValues(keywordDefs[0].node.initializer) === null
    || JSON.stringify(arrayStringValues(keywordDefs[0].node.initializer)) !== JSON.stringify(EXPECTED_KEYWORDS)) {
    errors.push(`IPO_BIZ_KEYWORDS 内容漂移：${JSON.stringify(arrayStringValues(keywordDefs[0].node.initializer))}`)
  }

  if (categoryDefs.length !== 1 || relative(categoryDefs[0]?.unit.file ?? '') !== F2_REL) {
    errors.push(`中文 IPO_CATEGORIES 定义应仅有 1 个且位于 ${F2_REL}：${categoryDefs.map((d) => location(d.unit, d.node)).join(', ')}`)
  } else if (!hasExportModifier(categoryDefs[0].node)) {
    errors.push(`IPO_CATEGORIES 必须 export：${location(categoryDefs[0].unit, categoryDefs[0].node)}`)
  } else if (JSON.stringify(arrayStringValues(categoryDefs[0].node.initializer)) !== JSON.stringify(EXPECTED_F2_CATEGORIES)) {
    errors.push(`IPO_CATEGORIES 中文内容漂移：${JSON.stringify(arrayStringValues(categoryDefs[0].node.initializer))}`)
  }

  if (adapterDefs.length !== 1 || relative(adapterDefs[0]?.unit.file ?? '') !== F2_REL) {
    errors.push(`对外 isIpoProject computed 适配器应仅存在于 F2：${adapterDefs.map((d) => location(d.unit, d.node)).join(', ')}`)
  }
  if (legacyDefs.length) {
    errors.push(`D4 仍存在独立 isIpoGroupVisible 定义：${legacyDefs.map((d) => location(d.unit, d.node)).join(', ')}`)
  }

  const coreCallRecords = coreCalls(units)
  const coreCallFiles = [...new Set(coreCallRecords.map((call) => relative(call.unit.file)))]
  const expectedCoreCallFiles = [A_PROGRAM_REL, D4_REL, F2_REL].sort()
  if (JSON.stringify([...coreCallFiles].sort()) !== JSON.stringify(expectedCoreCallFiles)) {
    errors.push(`核心 isIpoProject 调用来源漂移：${JSON.stringify(coreCallFiles)}`)
  }

  const f2Unit = units.find((unit) => relative(unit.file) === F2_REL)
  const f2Calls = coreCallRecords.filter((call) => relative(call.unit.file) === F2_REL)
  if (!f2Unit || f2Calls.length !== 1 || f2Calls[0].node.arguments.length !== 1) {
    errors.push(`F2 首级必须只调用核心且不替换三级兼容字段：${f2Calls.map((call) => location(call.unit, call.node)).join(', ')}`)
  }
  if (f2Unit) {
    const fields = interfaceFieldNames(f2Unit, 'ProjectContext')
    for (const field of F2_CONTEXT_FIELDS) {
      if (!fields.includes(field)) errors.push(`F2 ProjectContext 缺少三级字段 ${field}`)
    }
    const shape = f2BranchShape(f2Unit)
    const expectedShape = ['core-business_category', 'ctx.project_type=ipo', 'ctx.template_type=listed', 'IPO_CATEGORIES.includes']
    if (JSON.stringify(shape) !== JSON.stringify(expectedShape)) {
      errors.push(`F2 三级瀑布顺序/语义漂移：${JSON.stringify(shape)}`)
    }
  }

  const d4Calls = coreCallRecords.filter((call) => relative(call.unit.file) === D4_REL)
  if (d4Calls.length !== 1) {
    errors.push(`D4 应只有 1 个核心 IPO 调用：${d4Calls.map((call) => location(call.unit, call.node)).join(', ')}`)
  } else if (JSON.stringify(d4AllowedCategories(d4Calls[0])) !== JSON.stringify(['...IPO_BIZ_KEYWORDS', 'fraud_risk'])) {
    errors.push(`D4 必须通过 allowedCats 扩展 fraud_risk：${JSON.stringify(d4AllowedCategories(d4Calls[0]))}`)
  }

  const f2WrapperCalls = wrapperCalls(units)
  if (f2WrapperCalls.length !== 1 || relative(f2WrapperCalls[0]?.unit.file ?? '') !== F2_REL) {
    errors.push(`F2 wrapper 调用应仅来自 F2 composable：${f2WrapperCalls.map((call) => location(call.unit, call.node)).join(', ')}`)
  }

  const keywordMethodCalls = methodCalls(units, 'IPO_BIZ_KEYWORDS', 'some')
  if (keywordMethodCalls.length !== 1 || relative(keywordMethodCalls[0]?.unit.file ?? '') !== CORE_REL) {
    errors.push(`默认 IPO 关键词应仅由核心工具消费：${keywordMethodCalls.map((call) => location(call.unit, call.node)).join(', ')}`)
  }
  const categoryMethodCalls = methodCalls(units, 'IPO_CATEGORIES', 'includes')
  if (categoryMethodCalls.length !== 1 || relative(categoryMethodCalls[0]?.unit.file ?? '') !== F2_REL) {
    errors.push(`中文 IPO_CATEGORIES 应仅由 F2 wrapper 消费：${categoryMethodCalls.map((call) => location(call.unit, call.node)).join(', ')}`)
  }

  return errors
}

function inventoryReport(units: SourceUnit[]): string {
  const coreDefs = functionDefinitions(units, 'isIpoProject')
  const wrapperDefs = functionDefinitions(units, 'isF2IpoProject')
  const keywordDefs = variableDefinitions(units, 'IPO_BIZ_KEYWORDS')
  const categoryDefs = variableDefinitions(units, 'IPO_CATEGORIES')
  const coreCallRecords = coreCalls(units)
  const wrapperCallRecords = wrapperCalls(units)
  const categoryCallRecords = methodCalls(units, 'IPO_CATEGORIES', 'includes')
  return [
    `isIpoProject function definitions: ${coreDefs.map((d) => location(d.unit, d.node)).join(', ')}`,
    `isF2IpoProject wrapper definitions: ${wrapperDefs.map((d) => location(d.unit, d.node)).join(', ')}`,
    `IPO_BIZ_KEYWORDS definitions: ${keywordDefs.map((d) => location(d.unit, d.node)).join(', ')}`,
    `IPO_CATEGORIES definitions: ${categoryDefs.map((d) => location(d.unit, d.node)).join(', ')}`,
    `core calls: ${coreCallRecords.map((call) => `${location(call.unit, call.node)}(${call.localName})`).join(', ')}`,
    `F2 wrapper calls: ${wrapperCallRecords.map((call) => location(call.unit, call.node)).join(', ')}`,
    `IPO_CATEGORIES.includes calls: ${categoryCallRecords.map((call) => location(call.unit, call.node)).join(', ')}`,
  ].join('\n')
}

const productionUnits = loadProductionUnits()

function unitWithCode(unit: SourceUnit, code: string): SourceUnit {
  return parseUnit(unit.file, code, unit.lineOffset)
}

describe('D7.3 IPO 判定来源边界（AST）', () => {
  it('现算定义、调用与 F2 三级字段后，只有核心工具和 F2 wrapper 两个判定来源', () => {
    const violations = sourceBoundaryViolations(productionUnits)
    expect(violations, inventoryReport(productionUnits)).toEqual([])
  })

  it('D4 只通过核心 allowedCats 调用，并保留 fraud_risk 扩展', () => {
    const d4Calls = coreCalls(productionUnits).filter((call) => relative(call.unit.file) === D4_REL)
    expect(d4Calls).toHaveLength(1)
    expect(d4AllowedCategories(d4Calls[0])).toEqual(['...IPO_BIZ_KEYWORDS', 'fraud_risk'])
  })

  it('反向自检：注入第二个核心函数定义时 AST 守卫必须打红', () => {
    const core = productionUnits.find((unit) => relative(unit.file) === CORE_REL)
    expect(core).toBeDefined()
    const injected = unitWithCode(
      core!,
      `export function isIpoProject(_injected: string): boolean { return false }\n${core!.code}`,
    )
    const violations = sourceBoundaryViolations([
      ...productionUnits.filter((unit) => unit !== core),
      injected,
    ])
    expect(violations.some((message) => message.includes('isIpoProject 函数定义应仅有 1 个'))).toBe(true)
  })

  it('反向自检：把中文 F2 类别替换成统一英文关键词时必须打红', () => {
    const f2 = productionUnits.find((unit) => relative(unit.file) === F2_REL)
    expect(f2).toBeDefined()
    const mutatedCode = f2!.code.replace("'上市公司年审'", "'listed'")
    expect(mutatedCode).not.toBe(f2!.code)
    const mutated = unitWithCode(f2!, mutatedCode)
    const violations = sourceBoundaryViolations([
      ...productionUnits.filter((unit) => unit !== f2),
      mutated,
    ])
    expect(violations.some((message) => message.includes('IPO_CATEGORIES 中文内容漂移'))).toBe(true)
  })

  it('反向自检：删除 project_type 分支时必须识别三级语义缺失', () => {
    const f2 = productionUnits.find((unit) => relative(unit.file) === F2_REL)
    expect(f2).toBeDefined()
    const mutatedCode = f2!.code.replace("  if (ctx.project_type === 'ipo') return true", '')
    expect(mutatedCode).not.toBe(f2!.code)
    const mutated = unitWithCode(f2!, mutatedCode)
    const violations = sourceBoundaryViolations([
      ...productionUnits.filter((unit) => unit !== f2),
      mutated,
    ])
    expect(violations.some((message) => message.includes('F2 三级瀑布顺序/语义漂移'))).toBe(true)
  })
})
