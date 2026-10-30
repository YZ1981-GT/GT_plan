/**
 * 页面按路径复用（spec platform-perf-hotspots R6）：key 规则、DefaultLayout 接线、只有底稿列表开启。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parse } from 'vue/compiler-sfc'
import { routeViewKey } from '../routeViewKey'
import { indexFirstBy } from '../indexFirstBy'
import { workpapersRoutes } from '@/router/domains/workpapers'

const SRC = resolve(__dirname, '../..')

function route(path: string, query: Record<string, any> = {}, meta: Record<string, any> = {}) {
  const qs = new URLSearchParams(
    Object.entries(query).flatMap(([k, v]) => (Array.isArray(v) ? v.map((x) => [k, x]) : [[k, v]])),
  ).toString()
  return { path, fullPath: qs ? `${path}?${qs}` : path, query, meta } as any
}

describe('routeViewKey', () => {
  it('默认按 fullPath：只改 query 也换 key（多数页面靠重挂读 query）', () => {
    expect(routeViewKey(route('/p/1/editor', { sheet: 'A', cell: 'B2' })))
      .toBe('/p/1/editor?sheet=A&cell=B2')
    expect(routeViewKey(route('/p/1/editor', { sheet: 'A' }, { reuseOnQueryChange: false })))
      .toBe('/p/1/editor?sheet=A')
  })

  it('开启复用：view / filter 等 query 变化 key 不变', () => {
    const meta = { reuseOnQueryChange: true }
    const keys = [
      routeViewKey(route('/projects/p/workpapers', {}, meta)),
      routeViewKey(route('/projects/p/workpapers', { view: 'list' }, meta)),
      routeViewKey(route('/projects/p/workpapers', { view: 'list', filter: 'stale' }, meta)),
    ]
    expect(new Set(keys)).toEqual(new Set(['/projects/p/workpapers']))
  })

  it('开启复用：路径或 ?year= 变化仍换 key（年度变了整页重取）', () => {
    const meta = { reuseOnQueryChange: true }
    expect(routeViewKey(route('/projects/p/workpapers', { year: '2025', view: 'list' }, meta)))
      .toBe('/projects/p/workpapers?year=2025')
    expect(routeViewKey(route('/projects/p/workpapers', { year: ['2024', '2025'] }, meta)))
      .toBe('/projects/p/workpapers?year=2024,2025')
    expect(routeViewKey(route('/projects/q/workpapers', {}, meta))).toBe('/projects/q/workpapers')
  })
})

describe('接线', () => {
  it('DefaultLayout 的页面组件与 ErrorBoundary 都用 routeViewKey(viewRoute)', () => {
    const { descriptor } = parse(readFileSync(join(SRC, 'layouts/DefaultLayout.vue'), 'utf-8'))
    const keys: Record<string, string[]> = {}
    const walk = (node: any) => {
      if (node?.type === 1 && (node.tag === 'ErrorBoundary' || node.tag === 'component')) {
        const key = node.props.find((p: any) => p.type === 7 && p.name === 'bind' && p.arg?.content === 'key')
        ;(keys[node.tag] ||= []).push(key?.exp?.content ?? '')
      }
      for (const child of node?.children ?? []) walk(child)
    }
    walk(descriptor.template!.ast)
    expect(keys).toEqual({ ErrorBoundary: ['routeViewKey(viewRoute)'], component: ['routeViewKey(viewRoute)'] })
  })

  it('只有底稿列表开启复用（其他页仍按 fullPath 重挂）', () => {
    const wpList = workpapersRoutes.find((r) => r.name === 'WorkpaperList')
    expect(wpList?.meta?.reuseOnQueryChange).toBe(true)
    const files: string[] = []
    const collect = (dir: string) => {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name)
        if (statSync(p).isDirectory()) { if (name !== '__tests__') collect(p) } else if (/\.ts$/.test(name)) files.push(p)
      }
    }
    collect(join(SRC, 'router'))
    const hits = files.flatMap((f) => (readFileSync(f, 'utf-8').match(/reuseOnQueryChange\s*:\s*true/g) ?? []).map(() => f))
    expect(hits.map((f) => f.replace(/\\/g, '/').replace(/^.*\/src\//, ''))).toEqual(['router/domains/workpapers.ts'])
  })
})

describe('indexFirstBy', () => {
  it('同键保留第一个，与 find 命中同一项', () => {
    const items = [{ id: 'a', n: 1 }, { id: 'b', n: 2 }, { id: 'a', n: 3 }]
    const byId = indexFirstBy(items, (i) => i.id)
    for (const k of ['a', 'b', 'c']) expect(byId.get(k)).toBe(items.find((i) => i.id === k))
    expect(byId.size).toBe(2)
  })
})
