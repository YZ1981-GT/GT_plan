/**
 * Word 类底稿「导入数据」只读时禁用、并带窗口编号（spec workpaper-multi-window-lock-gaps R2.2 / R2.6）。
 *
 * 组件依赖在线编辑等重模块，这里按 SFC 结构判定（模板 AST + 脚本 AST），不靠源码文本匹配：
 * - 模板里文字为「导入数据」的按钮绑定 `:disabled="readonly"`；
 * - `onImportData` 开头只读即返回；原生 fetch 的请求头带 `X-Client-Instance`。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import ts from 'typescript'
import { parse } from 'vue/compiler-sfc'
import { describe, expect, it } from 'vitest'

const FILE = resolve(process.cwd(), 'src/components/workpaper/WorkpaperWordEditor.vue')
const { descriptor } = parse(readFileSync(FILE, 'utf-8'))
const script = descriptor.scriptSetup?.content ?? ''
const sf = ts.createSourceFile('WorkpaperWordEditor.ts', script, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)

function textOf(node: any): string {
  return (node.children ?? []).map((c: any) => (c.type === 2 ? c.content : textOf(c))).join('').trim()
}

function findButtons(node: any, out: any[] = []): any[] {
  if (node?.type === 1 && node.tag === 'el-button') out.push(node)
  for (const c of node?.children ?? []) findButtons(c, out)
  return out
}

function fn(name: string): ts.FunctionDeclaration {
  let found: ts.FunctionDeclaration | undefined
  sf.forEachChild(function visit(n) {
    if (ts.isFunctionDeclaration(n) && n.name?.text === name) found = n
    else n.forEachChild(visit)
  })
  expect(found, `缺函数 ${name}`).toBeDefined()
  return found!
}

describe('WorkpaperWordEditor 只读导入', () => {
  it('「导入数据」按钮绑定 :disabled="readonly"', () => {
    const button = findButtons(descriptor.template!.ast).find((b) => textOf(b) === '导入数据')
    expect(button, '没找到「导入数据」按钮').toBeDefined()
    const disabled = button.props.find((p: any) => p.type === 7 && p.name === 'bind' && p.arg?.content === 'disabled')
    expect(disabled?.exp?.content).toBe('readonly')
  })

  it('onImportData 只读即返回（在发请求之前），请求头带窗口编号', () => {
    const body = fn('onImportData').body!
    const statements = body.statements.map((s) => s.getText(sf))
    const guard = statements.findIndex((s) => /^if \(props\.readonly\)/.test(s) && /return/.test(s))
    const request = statements.findIndex((s) => s.includes('fetch('))
    expect(guard, '缺只读早退').toBeGreaterThanOrEqual(0)
    expect(request === -1 || guard < request).toBe(true)

    let headersText = ''
    body.forEachChild(function visit(n) {
      if (ts.isPropertyAssignment(n) && n.name.getText(sf) === 'headers') headersText = n.initializer.getText(sf)
      n.forEachChild(visit)
    })
    expect(headersText).toContain('getAuthHeaders()')
    expect(headersText).toContain("'X-Client-Instance': getClientInstanceId()")
  })
})
