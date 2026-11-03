/**
 * 前端直接读 `business_category` 的静态计数（spec trim-generation-plan-followup-optimizations R4.5）。
 *
 * 计数口径只有这一份：棘轮 spec 与它的反向自检都调这里，不各写一套（各写一套时变异只改一份、守卫照绿）。
 * - script：TypeScript AST（注释天然不进 AST）。读属性 `x.business_category`（赋值左侧不算）、
 *   `x['business_category']`、字符串 / 模板字面量里出现的词；类型声明里的字段名、对象字面量的键不算（写入 / 载荷）。
 * - template：去掉 script / style 块与 HTML 注释后按词计数（模板里出现即读取，含 v-model 双向绑定）。
 *
 * 本文件不是 spec（无 `.spec.ts` 后缀），vitest 不会当测试收集。
 */
import * as ts from 'typescript'
import { FRONTEND_SRC, readSource, stripHtmlComments, toSrcRelative, walkSourceFiles } from './frontendSourceScan'

const FIELD = 'business_category'
const WORD = /\bbusiness_category\b/g

function countWord(text: string): number {
  return (text.match(WORD) ?? []).length
}

function isAssignmentTarget(node: ts.Node): boolean {
  const parent = node.parent
  if (!parent || !ts.isBinaryExpression(parent) || parent.left !== node) return false
  const kind = parent.operatorToken.kind
  return kind >= ts.SyntaxKind.FirstAssignment && kind <= ts.SyntaxKind.LastAssignment
}

function isNonReadingStringPosition(node: ts.Node): boolean {
  const parent = node.parent
  if (!parent) return false
  if (ts.isPropertyAssignment(parent) && parent.name === node) return true // { 'business_category': v }
  if (ts.isLiteralTypeNode(parent)) return true // type K = 'business_category'
  if (ts.isElementAccessExpression(parent) && parent.argumentExpression === node && isAssignmentTarget(parent)) return true
  return false
}

/** 一段 TS / Vue script 代码里的直接读者数。 */
export function countScriptReaders(code: string): number {
  if (!code.includes(FIELD)) return 0
  const sourceFile = ts.createSourceFile('scan.ts', code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  let count = 0
  const walk = (node: ts.Node): void => {
    if (ts.isPropertyAccessExpression(node) && node.name.text === FIELD && !isAssignmentTarget(node)) {
      count += 1
    } else if (
      (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)
        || ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node))
      && !isNonReadingStringPosition(node)
    ) {
      count += countWord(node.text)
    }
    ts.forEachChild(node, walk)
  }
  walk(sourceFile)
  return count
}

const SCRIPT_BLOCK = /<script\b[^>]*>([\s\S]*?)<\/script>/gi
const STYLE_BLOCK = /<style\b[^>]*>[\s\S]*?<\/style>/gi

/** 一个文件（.ts / .vue）里的直接读者数。 */
export function countFileReaders(fileName: string, source: string): number {
  if (!source.includes(FIELD)) return 0
  if (!fileName.endsWith('.vue')) return countScriptReaders(source)
  let count = 0
  for (const match of source.matchAll(SCRIPT_BLOCK)) count += countScriptReaders(match[1])
  const template = stripHtmlComments(source.replace(SCRIPT_BLOCK, '').replace(STYLE_BLOCK, ''))
  return count + countWord(template)
}

/** 扫 `src/` 下全部生产源码（排除测试），返回 `相对 src 的路径 → 读者数`（只含非零项，按路径排序）。 */
export function scanBusinessCategoryReaders(): Record<string, number> {
  const out: Record<string, number> = {}
  for (const file of walkSourceFiles(FRONTEND_SRC).sort()) {
    const count = countFileReaders(file, readSource(file))
    if (count) out[toSrcRelative(file)] = count
  }
  return out
}
