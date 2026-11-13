/**
 * 同步桥 reloadHtml 接线契约（spec workpaper-html-onlyoffice-bidirectional-writeback-closure，2026-11-04 审计整改）
 *
 * 在线编辑落地（applied）后，桥调 `reloadHtml(revision)` 让表单读回服务端的新值（Property 14）。
 * 两种坏形态曾同时在库、且都没有门禁拦：
 *  ① D4-4 调整分录根本没传 `reloadHtml` ⇒ 桥里 `await options.reloadHtml(revision)` 抛 TypeError，
 *     进 reload 失败态、participant lease 不释放、表单停在 OO 改动之前的旧值。vue-tsc 报过 TS2345，
 *     但全量类型检查不是门禁（基线几千条），这条就一直埋着。
 *  ② D4-5 / D4-13 / D4-16 / D4-35 在 `reloadHtml` 里派发 `d4:reload-responses`，全仓没有一个监听方
 *     ⇒ 静默空操作，切回表单后同样是旧值。
 * 判据：每个 `useD4SyncMode` / `useWorkpaperSyncBridge` 调用的选项对象都传 `reloadHtml`；`reloadHtml`
 * 里派发的 CustomEvent 在 src 里必须有 `addEventListener`。
 */
import { describe, it, expect } from 'vitest'
import { resolve } from 'node:path'
import { isTestFile, readSource, stripJsComments, toSrcRelative, walkSourceFiles } from '@/__tests__/_helpers/frontendSourceScan'

const SRC = resolve(__dirname, '../../../..')
const CALL = /\b(useD4SyncMode|useWorkpaperSyncBridge)\(\s*\{/g

/** 从 `{` 开始按括号配平取出选项对象（只看代码：注释已剥掉）。 */
function optionsObject(code: string, open: number): string {
  let depth = 0
  for (let i = open; i < code.length; i += 1) {
    if (code[i] === '{') depth += 1
    else if (code[i] === '}') {
      depth -= 1
      if (depth === 0) return code.slice(open, i + 1)
    }
  }
  return code.slice(open)
}

interface CallSite { file: string; composable: string; options: string }

export function syncCallSites(file: string, source: string): CallSite[] {
  const code = stripJsComments(source)
  const out: CallSite[] = []
  for (const match of code.matchAll(CALL)) {
    const open = (match.index ?? 0) + match[0].length - 1
    out.push({ file, composable: match[1], options: optionsObject(code, open) })
  }
  return out
}

/** 选项对象没传 reloadHtml（整体透传 `...options` 的包装层不算）。 */
export function lacksReload(site: CallSite): boolean {
  return !/\breloadHtml\s*[:,(]/.test(site.options) && !/\.\.\.\w+/.test(site.options)
}

/** reloadHtml 里派发的 CustomEvent 名。 */
export function reloadEvents(site: CallSite): string[] {
  const body = /\breloadHtml\s*:\s*async\s*\([^)]*\)\s*=>\s*\{([\s\S]*?)\}\s*,/.exec(site.options)?.[1] ?? ''
  return [...body.matchAll(/new CustomEvent\(\s*['"]([^'"]+)['"]/g)].map((m) => m[1])
}

describe('同步桥 reloadHtml 接线契约', () => {
  it('判据识别两种坏形态（变异自检：否则全仓扫描为空也可能是判据失效）', () => {
    const [missing] = syncCallSites('Bad.vue', `const a = useD4SyncMode({ sheetKey: 'x', flushHtml: async () => ({}) })`)
    expect(lacksReload(missing)).toBe(true)
    const [dead] = syncCallSites('Dead.vue', [
      'const b = useD4SyncMode({',
      "  flushHtml: async () => ({}),",
      "  reloadHtml: async () => { window.dispatchEvent(new CustomEvent('x:never-heard')) },",
      '})',
    ].join('\n'))
    expect(lacksReload(dead)).toBe(false)
    expect(reloadEvents(dead)).toEqual(['x:never-heard'])
    // 注释里的写法不算传了
    const [commented] = syncCallSites('C.vue', 'useD4SyncMode({ sheetKey: "x", // reloadHtml: async () => {},\n})')
    expect(lacksReload(commented)).toBe(true)
    // 包装层整体透传不误报
    const [wrapper] = syncCallSites('W.ts', 'return useD4SyncMode({ ...options, entryId: ENTRY })')
    expect(lacksReload(wrapper)).toBe(false)
  })

  const files = walkSourceFiles(SRC).filter((f) => /\.(vue|ts)$/.test(f) && !isTestFile(f))
  const sources = new Map(files.map((f) => [f, readSource(f)]))
  const sites = files.flatMap((f) => syncCallSites(toSrcRelative(f), sources.get(f) ?? ''))

  it('每个同步桥调用都传 reloadHtml', () => {
    expect(sites.length).toBeGreaterThan(30) // 防空转：扫描范围失效时不许恒绿
    expect(sites.filter(lacksReload).map((s) => `${s.file} :: ${s.composable}`)).toEqual([])
  })

  it('reloadHtml 派发的事件都有监听方', () => {
    const listened = (name: string) => [...sources.values()].some((text) =>
      new RegExp(`addEventListener\\(\\s*['"]${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}['"]`).test(stripJsComments(text)))
    const dead = sites.flatMap((s) => reloadEvents(s).filter((name) => !listened(name)).map((name) => `${s.file} :: ${name}`))
    expect(dead).toEqual([])
  })
})
