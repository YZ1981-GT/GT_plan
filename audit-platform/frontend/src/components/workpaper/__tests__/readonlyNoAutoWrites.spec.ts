/**
 * 只读窗口不自动发写请求（spec workpaper-multi-window-lock-gaps R3.5）。
 *
 * 编辑锁在别的窗口 / 无编辑权时，这些写请求后端会 423：数据刷新事件触发的模板重建（原先非静默，每次刷新弹一次）、
 * A17 三张底稿切在线编辑时生成 / 回写 Word、自定义底稿切回表格时重投影。组件依赖重，按脚本 AST 判定：
 * 写请求所在函数里，条件含只读判断、分支里 return 的 if 必须出现在这次写请求之前。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import ts from 'typescript'
import { parse } from 'vue/compiler-sfc'
import { describe, expect, it } from 'vitest'

function scriptOf(file: string): ts.SourceFile {
  const { descriptor } = parse(readFileSync(resolve(process.cwd(), file), 'utf-8'))
  const block = descriptor.scriptSetup ?? descriptor.script
  return ts.createSourceFile(`${file}.ts`, block!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
}

function returns(node: ts.Node): boolean {
  if (ts.isReturnStatement(node)) return true
  let found = false
  node.forEachChild((c) => {
    if (!found && !ts.isFunctionLike(c)) found = returns(c)
  })
  return found
}

function enclosingFunction(node: ts.Node): ts.Node {
  let cur: ts.Node | undefined = node.parent
  while (cur && !ts.isFunctionLike(cur)) cur = cur.parent
  return cur ?? node.getSourceFile()
}

/** 写请求（`.post/.put/.patch/.delete(…endpoint…)`）之前，同一函数里有没有「条件匹配 guard、分支里 return」的 if。 */
function guardBeforeWrites(file: string, endpoint: string, guard: RegExp): { writes: number; unguarded: string[] } {
  const sf = scriptOf(file)
  const writes: ts.CallExpression[] = []
  sf.forEachChild(function visit(n) {
    if (ts.isCallExpression(n) && /\.(post|put|patch|delete)$/.test(n.expression.getText(sf))
      && n.arguments.some((a) => a.getText(sf).includes(endpoint))) writes.push(n)
    n.forEachChild(visit)
  })
  const unguarded = writes.filter((call) => {
    let ok = false
    enclosingFunction(call).forEachChild(function visit(n) {
      if (ts.isIfStatement(n) && n.getStart(sf) < call.getStart(sf) && guard.test(n.expression.getText(sf))
        && returns(n.thenStatement)) ok = true
      if (!ok) n.forEachChild(visit)
    })
    return !ok
  }).map((c) => c.getText(sf).slice(0, 80))
  return { writes: writes.length, unguarded }
}

const CASES: Array<[string, string, string, RegExp]> = [
  ['WorkpaperEditor 数据刷新时重建模板', 'src/views/WorkpaperEditor.vue', 'template-file/init', /!effectiveCanEdit\.value/],
  ['A17-1 生成 Word', 'src/components/workpaper/GtA171AuditSummary.vue', 'generate-docx', /props\.readonly/],
  ['A17-1 Word 回写', 'src/components/workpaper/GtA171AuditSummary.vue', 'sync-from-docx', /props\.readonly/],
  ['A17-6 生成 Word', 'src/components/workpaper/GtA176ClosingMeeting.vue', 'generate-docx', /props\.readonly/],
  ['A17-6 Word 回写', 'src/components/workpaper/GtA176ClosingMeeting.vue', 'sync-from-docx', /props\.readonly/],
  ['A17-7 生成 Word', 'src/components/workpaper/GtA177IndependenceDeclaration.vue', 'generate-docx', /props\.readonly/],
  ['A17-7 Word 回写', 'src/components/workpaper/GtA177IndependenceDeclaration.vue', 'sync-from-docx', /props\.readonly/],
  ['自定义底稿重投影', 'src/components/workpaper/GtCustomWpEditor.vue', 'customRefreshProjection', /props\.readonly/],
]

describe('只读不自动写', () => {
  it.each(CASES)('%s：只读判断在写请求之前', (_label, file, endpoint, guard) => {
    const { writes, unguarded } = guardBeforeWrites(file, endpoint, guard)
    expect(writes, `${file} 里找不到 ${endpoint} 的写请求（扫描面变了）`).toBeGreaterThan(0)
    expect(unguarded).toEqual([])
  })

  it('A17-1 声明了 readonly prop（渲染器按它传只读）', () => {
    const { descriptor } = parse(readFileSync(resolve(process.cwd(), 'src/components/workpaper/GtA171AuditSummary.vue'), 'utf-8'))
    const sf = scriptOf('src/components/workpaper/GtA171AuditSummary.vue')
    let props = ''
    sf.forEachChild(function visit(n) {
      if (ts.isCallExpression(n) && n.expression.getText(sf) === 'defineProps') props = n.getText(sf)
      n.forEachChild(visit)
    })
    expect(descriptor.scriptSetup).toBeTruthy()
    expect(props).toMatch(/readonly\?: boolean/)
  })

  it('判据本身：去掉只读判断即报', () => {
    const sf = ts.createSourceFile('x.ts', [
      'async function a() { if (props.readonly) return; await api.post(`/x/generate-docx`) }',
      'async function b() { await api.post(`/x/generate-docx`); if (props.readonly) return }',
      'async function c() { if (props.other) return; await api.post(`/x/generate-docx`) }',
    ].join('\n'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
    const calls: ts.CallExpression[] = []
    sf.forEachChild(function visit(n) {
      if (ts.isCallExpression(n) && n.expression.getText(sf) === 'api.post') calls.push(n)
      n.forEachChild(visit)
    })
    const guarded = calls.map((call) => {
      let ok = false
      enclosingFunction(call).forEachChild(function visit(n) {
        if (ts.isIfStatement(n) && n.getStart(sf) < call.getStart(sf) && /props\.readonly/.test(n.expression.getText(sf))
          && returns(n.thenStatement)) ok = true
        if (!ok) n.forEachChild(visit)
      })
      return ok
    })
    expect(guarded).toEqual([true, false, false])
  })
})
