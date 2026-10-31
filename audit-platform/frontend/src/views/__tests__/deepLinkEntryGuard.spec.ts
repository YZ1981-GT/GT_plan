/**
 * 深链定位入口守卫（spec wp-deeplink-locate-coverage-closure 需求 3）。
 *
 * 2026-10-30 现扫三类缺陷，统一改走 services/openWorkpaperCell（取本项目底稿实例 → 编辑器 ?sheet=&cell=）：
 * 1. 4 个溯源弹窗（试算表 / 未更正错报 / 合并 / 报表）「定位」发 `workpaper:locate-cell` 且把编码当 wpId：
 *    这些页面没有渲染器，事件无人接收，点了没有任何反应；
 * 2. 复核意见列表、附注→底稿穿透跳底稿列表页并带 sheet / cell：列表页不读这两个参数，定位丢失；
 * 3. 溯源面板的跨底稿节点只在当前页面找，找不到却提示「定位到 X」。
 *
 * 口径：src 下非测试源码（.ts / .vue；跳过 __tests__ / test / tests 与 *.spec / *.test / *.stories）。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = resolve(__dirname, '../..')
const SOURCE_EXT = /\.(?:ts|vue)$/
const TEST_FILE = /\.(?:spec|test|stories)\.[cm]?[jt]sx?$/
const SKIP_DIRS = new Set(['__tests__', 'test', 'tests', 'node_modules'])

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (SOURCE_EXT.test(name) && !TEST_FILE.test(name)) out.push(full)
  }
  return out
}

/** 从 text[open]（'(' 或 '{'）起取到配平的闭括号为止 */
function balanced(text: string, open: number): string {
  const pairs: Record<string, string> = { '(': ')', '{': '}' }
  const close = pairs[text[open]]
  let depth = 0
  for (let i = open; i < text.length; i++) {
    if (text[i] === text[open]) depth++
    else if (text[i] === close && --depth === 0) return text.slice(open, i + 1)
  }
  return text.slice(open)
}

const lineOf = (text: string, index: number) => text.slice(0, index).split('\n').length

/** 1. 定位事件把底稿编码当 wpId */
export function codeAsWpIdEmits(text: string): number[] {
  const re = /eventBus\.emit\(\s*'workpaper:locate-cell'\s*,\s*\{\s*wpId:\s*[\w.?]*wp_code/g
  return [...text.matchAll(re)].map((m) => lineOf(text, m.index!))
}

const LIST_TARGET = /name:\s*'WorkpaperList'|path:\s*`\/projects\/\$\{[^}]+\}\/workpapers`/

/** 2. 跳底稿列表页却带 sheet / cell（对象字面量里直接写，或 query 变量在跳转前被塞进 sheet / cell） */
export function listNavigationsWithLocate(text: string): number[] {
  const hits: number[] = []
  for (const m of text.matchAll(/\brouter\.(?:push|replace)\(/g)) {
    const arg = balanced(text, m.index! + m[0].length - 1)
    if (!LIST_TARGET.test(arg)) continue
    let bad = /\b(?:sheet|cell)\s*:/.test(arg)
    const queryVar = /\bquery\s*[,}\n]/.test(arg) ? 'query' : /\bquery:\s*([A-Za-z_$][\w$]*)\s*[,}\n]/.exec(arg)?.[1]
    if (!bad && queryVar) {
      const before = text.slice(Math.max(0, m.index! - 1200), m.index!)
      bad = new RegExp(`\\b${queryVar}(?:\\.(?:sheet|cell)|\\[['"](?:sheet|cell)['"]\\])\\s*=`).test(before)
        || new RegExp(`(?:const|let)\\s+${queryVar}\\b[^=]*=\\s*\\{[^}]*\\b(?:sheet|cell)\\s*:`).test(before)
    }
    if (bad) hits.push(lineOf(text, m.index!))
  }
  return hits
}

/** 3. 溯源弹窗的「定位」处理函数：名字 → 是否调用 openWorkpaperCell */
export function traceLocateHandlers(text: string): Array<[string, boolean]> {
  return [...text.matchAll(/(?:async\s+)?function\s+(on\w*TraceLocate)\s*\(/g)].map((m) => {
    const body = balanced(text, text.indexOf('{', m.index! + m[0].length))
    return [m[1], body.includes('openWorkpaperCell(')]
  })
}

describe('深链定位入口：统一经 openWorkpaperCell 打开编辑器（wp-deeplink-locate-coverage-closure 需求 3）', () => {
  const files = walk(SRC)
  const sources = files.map((f) => ({ rel: relative(SRC, f).split('\\').join('/'), text: readFileSync(f, 'utf-8') }))

  it('扫描范围没失锚（> 1000 个源码文件）', () => {
    expect(files.length).toBeGreaterThan(1000)
  })

  it('判据自身有效：旧写法命中、正确写法不命中（双向）', () => {
    const oldTrace = `function onTbTraceLocate(node: any) {\n  if (node.wp_code) {\n    eventBus.emit('workpaper:locate-cell', {\n      wpId: node.wp_code,\n    })\n  }\n}`
    expect(codeAsWpIdEmits(oldTrace)).toHaveLength(1)
    expect(codeAsWpIdEmits(`eventBus.emit('workpaper:locate-cell', { wpId: currentWpId, cellRef })`)).toEqual([])
    expect(traceLocateHandlers(oldTrace)).toEqual([['onTbTraceLocate', false]])

    const oldReview = `const query: Record<string, string> = { highlight: item.wp_code }\n  if (item.sheet_name) query.sheet = item.sheet_name\n  router.push({\n    name: 'WorkpaperList',\n    params: { projectId },\n    query,\n  })`
    const oldNote = "const query: Record<string, string> = { code: wpCode }\n if (locate?.cell) query.cell = locate.cell\n router.push({\n path: `/projects/${pid()}/workpapers`,\n query,\n })"
    const inline = "router.push({ name: 'WorkpaperList', params: { projectId }, query: { highlight: code, cell: ref } })"
    for (const sample of [oldReview, oldNote, inline]) expect(listNavigationsWithLocate(sample)).toHaveLength(1)

    const editorThenList = "router.push({ path: `/projects/${pid}/workpapers/${id}/edit`, query: { sheet: alias.sheet } })\n} else {\n router.push({ path: `/projects/${pid}/workpapers`, query: { search: wpCode } })"
    expect(listNavigationsWithLocate(editorThenList)).toEqual([])
  })

  it('没有把底稿编码当 wpId 的定位事件', () => {
    const offenders = sources.flatMap(({ rel, text }) => codeAsWpIdEmits(text).map((line) => `${rel}:${line}`))
    expect(offenders).toEqual([])
  })

  it('跳底稿列表页不带 sheet / cell（列表页不读这两个参数，要定位就进编辑器）', () => {
    const offenders = sources.flatMap(({ rel, text }) => listNavigationsWithLocate(text).map((line) => `${rel}:${line}`))
    expect(offenders).toEqual([])
  })

  it('溯源弹窗的「定位」都经 openWorkpaperCell（4 个弹窗，新增的同类处理函数自动纳入）', () => {
    const handlers = sources.flatMap(({ rel, text }) => traceLocateHandlers(text).map(([name, ok]) => ({ at: `${rel}#${name}`, ok })))
    expect(handlers.map((h) => h.at).sort()).toEqual(expect.arrayContaining([
      'views/ConsolidationIndex.vue#onConsolTraceLocate',
      'views/Misstatements.vue#onMsTraceLocate',
      'views/TrialBalance.vue#onTbTraceLocate',
      'views/composables/useReportTrace.ts#onRvTraceLocate',
    ]))
    expect(handlers.filter((h) => !h.ok).map((h) => h.at)).toEqual([])
  })

  it('复核意见列表、附注→底稿穿透、溯源面板的跨底稿节点经 openWorkpaperCell', () => {
    for (const rel of [
      'components/dashboard/ReviewOpinionList.vue',
      'composables/usePenetrate.ts',
      'components/workpaper/LineageGraphPanel.vue',
    ]) {
      const text = sources.find((s) => s.rel === rel)?.text ?? ''
      expect(text, rel).toContain("from '@/services/openWorkpaperCell'")
      expect(text, rel).toMatch(/openWorkpaperCell\(router,/)
    }
  })
})
