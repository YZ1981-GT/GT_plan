/**
 * Vue Router 域拆分投影等价：domains/*.ts ↔ index.ts 装配。
 *
 * 验证每个域导出被展开恰好一次、域内 path 全部进入声明集合、
 * 跨域 name 不重复、index 仅一个 beforeEach。
 */
import { describe, it, expect } from 'vitest'
import { readdirSync } from 'fs'
import { basename, resolve } from 'path'
import {
  FRONTEND_SRC,
  readSource,
  stripJsComments,
  parseDeclaredRoutes,
} from '../../__tests__/_helpers/frontendSourceScan'

const ROUTER_DIR = resolve(FRONTEND_SRC, 'router')
const ROUTER_FILE = resolve(ROUTER_DIR, 'index.ts')
const DOMAIN_DIR = resolve(ROUTER_DIR, 'domains')

const DOMAIN_FILES = readdirSync(DOMAIN_DIR)
  .filter((name) => name.endsWith('.ts'))
  .map((name) => resolve(DOMAIN_DIR, name))
  .sort()

/** layout children 域（不含顶层 auth / standalone） */
const LAYOUT_DOMAIN_EXPORTS = [
  'dashboardRoutes',
  'projectsRoutes',
  'workpapersRoutes',
  'reportsRoutes',
  'notesRoutes',
  'confirmationsRoutes',
  'qcRoutes',
  'extensionRoutes',
  'systemRoutes',
] as const

const TOP_LEVEL_DOMAIN_EXPORTS = ['authRoutes', 'standaloneRoutes'] as const

interface DomainRouteEntry {
  file: string
  path: string
  name: string | null
  full: string
}

function parseDomainRouteEntries(file: string, source: string): DomainRouteEntry[] {
  const code = stripJsComments(source)
  const entries: DomainRouteEntry[] = []
  // 每个 route 对象块：path 必有；name 可选（如纯 redirect）
  const blockRe = /\{\s*([\s\S]*?)\n\s*\}/g
  for (const m of code.matchAll(blockRe)) {
    const body = m[1]
    const pathM = body.match(/path:\s*'([^']*)'/)
    if (!pathM) continue
    const raw = pathM[1]
    const nameM = body.match(/name:\s*'([^']+)'/)
    entries.push({
      file: basename(file),
      path: raw,
      name: nameM?.[1] ?? null,
      full: raw.startsWith('/') ? raw : `/${raw}`,
    })
  }
  return entries
}

const ALL_DOMAIN_ENTRIES = DOMAIN_FILES.flatMap((f) => parseDomainRouteEntries(f, readSource(f)))
const DECLARED_FROM_DOMAINS = parseDeclaredRoutes(DOMAIN_FILES.map((f) => readSource(f)).join('\n'))
const DECLARED_FULL_SET = new Set(DECLARED_FROM_DOMAINS.map((r) => r.full))

describe('route domain projection equality', () => {
  it('index.ts 将每个域导出展开恰好一次（layoutChildren + top-level routes）', () => {
    const indexSrc = stripJsComments(readSource(ROUTER_FILE))

    for (const exp of LAYOUT_DOMAIN_EXPORTS) {
      const spreads = indexSrc.match(new RegExp(`\\.\\.\\.${exp}\\b`, 'g')) ?? []
      expect(spreads.length, `${exp} 应在 layoutChildren 中展开恰好一次`).toBe(1)
      expect(indexSrc).toMatch(new RegExp(`from '\\./domains/[^']+'`))
    }

    for (const exp of TOP_LEVEL_DOMAIN_EXPORTS) {
      const spreads = indexSrc.match(new RegExp(`\\.\\.\\.${exp}\\b`, 'g')) ?? []
      expect(spreads.length, `${exp} 应在 routes 中展开恰好一次`).toBe(1)
    }

    // 每个 domains/*.ts 对应一个 import
    for (const file of DOMAIN_FILES) {
      const stem = basename(file, '.ts')
      expect(indexSrc).toContain(`from './domains/${stem}'`)
    }
  })

  it('每个域 route path 都出现在装配后的 DECLARED 集合中', () => {
    expect(ALL_DOMAIN_ENTRIES.length).toBeGreaterThan(50)
    const missing = ALL_DOMAIN_ENTRIES.filter((e) => !DECLARED_FULL_SET.has(e.full)).map(
      (e) => `${e.file} path=${JSON.stringify(e.path)} full=${e.full}`,
    )
    expect(missing, `域 path 未进入 DECLARED:\n${missing.join('\n')}`).toEqual([])
  })

  it('跨域 route name 无重复', () => {
    const names = ALL_DOMAIN_ENTRIES.map((e) => e.name).filter((n): n is string => n != null)
    const counts = new Map<string, number>()
    for (const n of names) counts.set(n, (counts.get(n) ?? 0) + 1)
    const dupes = [...counts.entries()].filter(([, c]) => c > 1).map(([n, c]) => `${n}×${c}`)
    expect(dupes, `重复 name:\n${dupes.join('\n')}`).toEqual([])
  })

  it('index.ts 仅有一个 beforeEach', () => {
    const indexSrc = stripJsComments(readSource(ROUTER_FILE))
    expect((indexSrc.match(/\.beforeEach\(/g) ?? []).length).toBe(1)
  })
})
