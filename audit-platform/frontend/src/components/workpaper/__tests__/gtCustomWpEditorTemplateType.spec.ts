/**
 * 自定义底稿编辑器保存公式不写死准则口径（spec formula-fetch-and-wp-generation-defect-closure R6）。
 *
 * 原先保存请求体写死 `template_type: 'soe'` ⇒ 上市项目的公式按国企附注校验引用。现改为不传，由后端按底稿所属
 * 项目的口径校验；后端仍尊重显式传入的值，所以前端一旦又写回去，问题就会原样回来 —— 本守卫钉住请求体。
 * 判据走 TypeScript AST：请求体对象字面量的键名（注释里提到 template_type 不算）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import * as ts from 'typescript'
import { describe, expect, it } from 'vitest'

const SFC = readFileSync(resolve(__dirname, '../GtCustomWpEditor.vue'), 'utf-8')

function scriptOf(sfc: string): string {
  const m = sfc.match(/<script setup[^>]*>([\s\S]*?)<\/script>/)
  if (!m) throw new Error('GtCustomWpEditor.vue 里找不到 <script setup>')
  return m[1]
}

/** `api.put(apiPaths.workpapers.formulas(...), { ... })` 每处调用的请求体键名。 */
function formulaSaveBodyKeys(code: string): string[][] {
  const sf = ts.createSourceFile('GtCustomWpEditor.ts', code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const found: string[][] = []
  const visit = (node: ts.Node): void => {
    if (
      ts.isCallExpression(node)
      && node.expression.getText(sf) === 'api.put'
      && (node.arguments[0]?.getText(sf) ?? '').startsWith('apiPaths.workpapers.formulas(')
    ) {
      const body = node.arguments[1]
      if (body && ts.isObjectLiteralExpression(body)) {
        found.push(body.properties.map((p) => (p.name ? p.name.getText(sf) : p.getText(sf))))
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return found
}

describe('GtCustomWpEditor 保存公式的请求体', () => {
  it('不带 template_type（后端按底稿所属项目的口径校验引用）', () => {
    const calls = formulaSaveBodyKeys(scriptOf(SFC))
    expect(calls).toHaveLength(1)
    expect(calls[0]).toContain('target_cell')
    expect(calls[0]).not.toContain('template_type')
  })

  it('反向自检：请求体里写回 template_type 必须被抓到', () => {
    const planted = scriptOf(SFC).replace(
      'target_cell: targetCell,',
      "target_cell: targetCell,\n      template_type: 'soe',",
    )
    expect(planted).not.toBe(scriptOf(SFC))
    expect(formulaSaveBodyKeys(planted)[0]).toContain('template_type')
  })
})
