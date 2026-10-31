/**
 * 底稿列表页入口参数（spec wp-deeplink-locate-residual-closure 需求 2）：解析规则 + 全仓入口守卫。
 *
 * 守卫：src 下非测试源码里所有指向列表页的路由对象（`name: 'WorkpaperList'` 或 `path: \`/projects/${…}/workpapers\``，
 * 含 router.push 参数与函数返回的路由对象）与 `/projects/${…}/workpapers?…` 字符串，带的参数都须在
 * `WORKPAPER_LIST_QUERY_KEYS` 里（列表页不读的参数 = 入口失效：此前 `tab=lifecycle`、`source_wp` 即此）。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { WORKPAPER_LIST_QUERY_KEYS, entryCode, readListEntryQuery } from '../workpaperListEntryQuery'

describe('readListEntryQuery', () => {
  it('编码取 highlight > wp_code > search 的第一个词', () => {
    expect(readListEntryQuery({ highlight: 'D2-1', wp_code: 'E1', search: 'F1' }).code).toBe('D2-1')
    expect(readListEntryQuery({ wp_code: ' E1 ', search: 'F1' }).code).toBe('E1')
    expect(readListEntryQuery({ search: 'F1' }).code).toBe('F1')
    expect(readListEntryQuery({ highlight: ['G8', 'x'] }).code).toBe('G8')
    expect(entryCode('D2-1 应收账款明细')).toBe('D2-1')
    expect(entryCode('D2-1，D2-2')).toBe('D2-1')
  })

  it('cycle 只认单个字母 A~S（转大写）；assigned 只认 me / unassigned；account、upload 原样', () => {
    expect(readListEntryQuery({ cycle: 'd' }).cycle).toBe('D')
    expect(readListEntryQuery({ cycle: 'A' }).cycle).toBe('A')
    expect(readListEntryQuery({ cycle: 'Z' }).cycle).toBe('')
    expect(readListEntryQuery({ cycle: 'DD' }).cycle).toBe('')
    expect(readListEntryQuery({ assigned: 'me' }).assigned).toBe('me')
    expect(readListEntryQuery({ assigned: 'unassigned' }).assigned).toBe('unassigned')
    expect(readListEntryQuery({ assigned: 'u-1' }).assigned).toBe('')
    expect(readListEntryQuery({ account: ' 1122 ' }).account).toBe('1122')
    expect(readListEntryQuery({ upload: 'wp-1' }).upload).toBe('wp-1')
  })

  it('签名：没有入口参数为空串；任一参数变了签名就变', () => {
    expect(readListEntryQuery({ view: 'list', filter: 'stale' }).signature).toBe('')
    const a = readListEntryQuery({ highlight: 'D2' }).signature
    expect(a).not.toBe('')
    expect(readListEntryQuery({ highlight: 'D2', view: 'kanban' }).signature).toBe(a)
    expect(readListEntryQuery({ highlight: 'D3' }).signature).not.toBe(a)
    expect(readListEntryQuery({ highlight: 'D2', cycle: 'D' }).signature).not.toBe(a)
  })
})

// ─── 全仓入口守卫 ─────────────────────────────────────────────────────────────

const SRC = resolve(__dirname, '../../..')
const SKIP_DIRS = new Set(['__tests__', 'test', 'tests', 'node_modules'])
const TEST_FILE = /\.(?:spec|test|stories)\.[cm]?[jt]sx?$/

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.(?:ts|vue)$/.test(name) && !TEST_FILE.test(name)) out.push(full)
  }
  return out
}

const QUOTES = new Set(["'", '"', '`'])

/** 从 text[open]（'{'）起取到配平的 '}'，跳过字符串 / 模板串内容 */
function balancedObject(text: string, open: number): string {
  let depth = 0
  for (let i = open; i < text.length; i++) {
    const ch = text[i]
    if (QUOTES.has(ch)) {
      const end = skipString(text, i)
      i = end
      continue
    }
    if (ch === '{') depth++
    else if (ch === '}' && --depth === 0) return text.slice(open, i + 1)
  }
  return text.slice(open)
}

function skipString(text: string, start: number): number {
  const q = text[start]
  for (let i = start + 1; i < text.length; i++) {
    if (text[i] === '\\') { i++; continue }
    if (text[i] === q) return i
  }
  return text.length
}

/** 包住 text[at] 的最内层对象字面量 */
function enclosingObject(text: string, at: number): string | null {
  let depth = 0
  for (let i = at; i >= 0; i--) {
    if (text[i] === '}') depth++
    else if (text[i] === '{') {
      if (depth === 0) return balancedObject(text, i)
      depth--
    }
  }
  return null
}

/** 对象字面量的顶层键（展开 ...x 忽略） */
export function topLevelKeys(obj: string): string[] {
  let flat = ''
  let depth = 0
  for (let i = 0; i < obj.length; i++) {
    const ch = obj[i]
    if (QUOTES.has(ch)) {
      const end = skipString(obj, i)
      if (depth === 1) flat += obj.slice(i, end + 1)
      i = end
      continue
    }
    if ('{[('.includes(ch)) { depth++; continue }
    if ('}])'.includes(ch)) { depth--; continue }
    if (depth === 1) flat += ch
  }
  return flat.split(',').map((p) => p.trim()).filter((p) => p && !p.startsWith('...'))
    .map((p) => /^['"]?([\w$]+)['"]?\s*(?::|$)/.exec(p)?.[1] ?? '').filter(Boolean)
}

/** 一个路由对象带的 query 参数键（query 是变量时找它在前文的字面量与赋值） */
function queryKeysOfRoute(text: string, route: string, routeAt: number): string[] {
  // `query: {…}` / `query: 变量` / 简写 `query`
  const m = /\bquery(?:\s*:\s*(\{|[A-Za-z_$][\w$]*)|(?=\s*[,}\n]))/.exec(route)
  if (!m) return []
  if (m[1] === '{') return topLevelKeys(balancedObject(route, m.index + m[0].length - 1))
  const v = m[1] ?? 'query'
  const before = text.slice(Math.max(0, routeAt - 1500), routeAt)
  const keys: string[] = []
  const decl = new RegExp(`(?:const|let)\\s+${v}\\b[^=]*=\\s*\\{`).exec(before)
  if (decl) keys.push(...topLevelKeys(balancedObject(before, decl.index + decl[0].length - 1)))
  for (const a of before.matchAll(new RegExp(`\\b${v}(?:\\.([\\w$]+)|\\[['"]([\\w$]+)['"]\\])\\s*=[^=]`, 'g'))) keys.push(a[1] || a[2])
  return keys
}

export function listEntryKeys(text: string): Array<{ line: number; keys: string[] }> {
  const out: Array<{ line: number; keys: string[] }> = []
  const lineOf = (i: number) => text.slice(0, i).split('\n').length
  for (const m of text.matchAll(/name:\s*'WorkpaperList'|path:\s*`\/projects\/\$\{[^}]+\}\/workpapers`/g)) {
    const at = m.index!
    const route = enclosingObject(text, at)
    if (!route) continue
    out.push({ line: lineOf(at), keys: queryKeysOfRoute(text, route, at) })
  }
  for (const m of text.matchAll(/\/projects\/\$\{[^}]+\}\/workpapers\?([^`'"\s]*)/g)) {
    const keys = m[1].split('&').map((kv) => kv.split('=')[0]).filter(Boolean)
    out.push({ line: lineOf(m.index!), keys })
  }
  return out
}

describe('跳底稿列表页的参数都由列表页读取（wp-deeplink-locate-residual-closure 需求 2.4）', () => {
  const allowed = new Set<string>(WORKPAPER_LIST_QUERY_KEYS)
  const files = walk(SRC)

  it('判据自身有效：列表页不读的参数命中，读的不命中（双向）', () => {
    const bad = "router.push({\n  name: 'WorkpaperList',\n  params: { projectId: props.projectId },\n  query: { tab: 'lifecycle' },\n})"
    expect(listEntryKeys(bad)[0].keys).toEqual(['tab'])
    const extra = "router.push({ name: 'WorkpaperList', params: { projectId }, query: { highlight: layer.template_wp, source_wp: props.wpCode || '' } })"
    expect(listEntryKeys(extra)[0].keys).toEqual(['highlight', 'source_wp'])
    const ret = "return { name: 'WorkpaperList', params: { projectId }, query: { highlight: wpCode } }"
    expect(listEntryKeys(ret)[0].keys).toEqual(['highlight'])
    const path = 'router.push({ path: `/projects/${pid}/workpapers`, query: { search: wpCode } })'
    expect(listEntryKeys(path)[0].keys).toEqual(['search'])
    const str = 'return `/projects/${pid}/workpapers?wp_code=${targetCode}&foo=1`'
    expect(listEntryKeys(str)[0].keys).toEqual(['wp_code', 'foo'])
    const viaVar = "const query: Record<string, string> = { highlight: code }\nquery.cell = ref\nrouter.push({ name: 'WorkpaperList', params: { projectId }, query })"
    expect(listEntryKeys(viaVar)[0].keys.sort()).toEqual(['cell', 'highlight'])
    const spread = "router.push({ name: 'WorkpaperList', params: { projectId }, query: { ...yearQuery(), filter: 'stale' } })"
    expect(listEntryKeys(spread)[0].keys).toEqual(['filter'])
    expect(topLevelKeys("{ a: 1, 'b': { c: 2 }, d, e: `x${f}` }")).toEqual(['a', 'b', 'd', 'e'])
  })

  const sources = new Map(files.map((f) => [relative(SRC, f).split('\\').join('/'), readFileSync(f, 'utf-8')]))
  /** 已知未接的入口（可伪证：理由不再成立即红；接入后从这里删掉） */
  const KNOWN_UNREAD: Array<{ file: string; key: string; reason: string; holds: () => boolean }> = [{
    file: 'composables/usePenetrate.ts', key: 'fromReport',
    reason: 'toWorkpaperFromReport 无调用方，报表行次 → 底稿的映射未实现；有人调用前须让列表页读该参数',
    holds: () => [...sources].every(([rel, text]) => rel === 'composables/usePenetrate.ts' || !/\btoWorkpaperFromReport\b/.test(text)),
  }]

  it('全仓入口的参数都在清单里（防空转：入口 ≥ 15 处）', () => {
    expect(files.length).toBeGreaterThan(1000)
    const entries = [...sources].flatMap(([rel, text]) => listEntryKeys(text).map((e) => ({ ...e, rel })))
    expect(entries.length).toBeGreaterThanOrEqual(15)
    expect(entries.filter((e) => e.keys.includes('highlight')).length).toBeGreaterThanOrEqual(5)
    const unread = entries.flatMap((e) => e.keys.filter((k) => !allowed.has(k)).map((k) => ({ rel: e.rel, line: e.line, key: k })))
    const known = (u: { rel: string; key: string }) => KNOWN_UNREAD.some((k) => k.file === u.rel && k.key === u.key)
    const bad = unread.filter((u) => !known(u)).map((u) => `${u.rel}:${u.line} ${u.key}`)
    expect(bad, `列表页不读的参数：\n${bad.join('\n')}`).toEqual([])
    for (const k of KNOWN_UNREAD) {
      expect(unread.some((u) => u.rel === k.file && u.key === k.key), `已登记的 ${k.file} ${k.key} 已不存在：删掉这条登记`).toBe(true)
      expect(k.holds(), `${k.file} ${k.key} 的登记理由不再成立：${k.reason}`).toBe(true)
    }
  })
})
