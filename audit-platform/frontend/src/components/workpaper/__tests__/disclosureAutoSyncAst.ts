import { parse as parseSfc } from '@vue/compiler-sfc'
import ts from 'typescript'

export interface AutoSyncCallFacts {
  useCalls: Array<{ args: number; firstIsObject: boolean }>
  scheduleCalls: Array<{ args: number; firstIsCallableRef: boolean }>
  cancelCalls: number
  cancelInUnmount: boolean
}

function callName(node: ts.CallExpression): string | null {
  if (ts.isIdentifier(node.expression)) return node.expression.text
  if (ts.isPropertyAccessExpression(node.expression)) return node.expression.name.text
  return null
}

function containsCall(node: ts.Node, expected: string): boolean {
  let found = false
  const visit = (child: ts.Node): void => {
    if (found) return
    if (ts.isCallExpression(child) && callName(child) === expected) {
      found = true
      return
    }
    ts.forEachChild(child, visit)
  }
  ts.forEachChild(node, visit)
  return found
}

function callableReference(node: ts.Expression | undefined): boolean {
  return !!node && (
    ts.isIdentifier(node)
    || ts.isPropertyAccessExpression(node)
    || ts.isArrowFunction(node)
    || ts.isFunctionExpression(node)
  )
}

/** 按 SFC script AST 提取自动同步调用形态；注释和模板文本不会参与判定。 */
export function autoSyncCallFacts(file: string, source: string): AutoSyncCallFacts {
  const descriptor = parseSfc(source, { filename: file }).descriptor
  const script = [descriptor.script?.content, descriptor.scriptSetup?.content].filter(Boolean).join('\n')
  const sf = ts.createSourceFile(file, script, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const facts: AutoSyncCallFacts = {
    useCalls: [],
    scheduleCalls: [],
    cancelCalls: 0,
    cancelInUnmount: false,
  }
  const visit = (node: ts.Node): void => {
    if (ts.isCallExpression(node)) {
      const name = callName(node)
      if (name === 'useDisclosureAutoSync') {
        facts.useCalls.push({
          args: node.arguments.length,
          firstIsObject: node.arguments.length === 0 || ts.isObjectLiteralExpression(node.arguments[0]),
        })
      } else if (name === 'scheduleAutoSync') {
        facts.scheduleCalls.push({
          args: node.arguments.length,
          firstIsCallableRef: callableReference(node.arguments[0]),
        })
      } else if (name === 'cancelPending') {
        facts.cancelCalls += 1
      } else if (name === 'onBeforeUnmount' || name === 'onUnmounted') {
        if (node.arguments.some((arg) => containsCall(arg, 'cancelPending')
          || (ts.isIdentifier(arg) && arg.text === 'cancelPending'))) {
          facts.cancelInUnmount = true
        }
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return facts
}
