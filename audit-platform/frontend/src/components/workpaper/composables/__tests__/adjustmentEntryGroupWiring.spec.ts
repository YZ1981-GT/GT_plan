/**
 * 调整分录页跳来源底稿的接线守卫（spec wp-deeplink-locate-residual-closure 需求 1.3）。
 *
 * 1. 全部 `useAdjustmentCentralSync({...})` 调用点：item_id 是函数（随 AJE / RJE 切换）的必须传 `entryType`，且就是
 *    模板串里 `${X.value}` 的那个 ref；item_id 是固定值的不传。
 * 2. 这些底稿在 ACNR 目录里都恰有一张名称含「调整分录」的表（`?sheet=@adjustment` 解析得到）。
 * 3. 调整分录页跳转带别名与 source_ref；渲染器把 `?highlight=` 解析成本底稿分录组并交给调度。
 * 口径：src 下非测试源码（.ts / .vue；跳过 __tests__ / test / tests 与 *.spec / *.test / *.stories）。
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ADJUSTMENT_SHEET_ALIAS, resolveSheetNameByDeepLink } from '@/utils/normalizeSheetName'

const SRC = resolve(__dirname, '../../../..')
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

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    if (existsSync(join(dir, 'backend', 'data', 'acnr', 'global_catalog.json'))) return dir
    dir = dirname(dir)
  }
  throw new Error('未找到仓库根（哨兵 backend/data/acnr/global_catalog.json）')
}

function balanced(text: string, open: number): string {
  let depth = 0
  for (let i = open; i < text.length; i++) {
    if (text[i] === '{') depth++
    else if (text[i] === '}' && --depth === 0) return text.slice(open, i + 1)
  }
  return text.slice(open)
}

export interface SyncCallSite { wpCode: string | null; itemId: string; entryType: string | null; problem: string | null }

/** 一段源码里的汇聚调用点与接线问题（判据本身另有双向样例） */
export function syncCallSites(text: string): SyncCallSite[] {
  const out: SyncCallSite[] = []
  for (const m of text.matchAll(/useAdjustmentCentralSync\(\s*\{/g)) {
    const body = balanced(text, m.index! + m[0].length - 1)
    const wpCode = /\bwpCode:\s*'([^']+)'/.exec(body)?.[1] ?? null
    const itemId = /\bitemId:\s*([^\n]+?),?\s*\n/.exec(body)?.[1]?.trim() ?? ''
    const entryType = /\bentryType:\s*([\w.]+)\s*,?/.exec(body)?.[1] ?? null
    const getter = /^\(\)\s*=>\s*`[^`]*\$\{([\w.]+)\.value\}[^`]*`$/.exec(itemId)
    let problem: string | null = null
    if (/^\(\)\s*=>/.test(itemId) && !getter) problem = `item_id 函数不是「模板串 + \${ref.value}」写法：${itemId}`
    else if (getter && entryType !== getter[1]) problem = `item_id 随 ${getter[1]} 切换，entryType 应传 ${getter[1]}（现为 ${entryType ?? '未传'}）`
    else if (!getter && entryType) problem = `item_id 是固定值却传了 entryType ${entryType}`
    out.push({ wpCode, itemId, entryType, problem })
  }
  return out
}

describe('调整分录组定位接线（wp-deeplink-locate-residual-closure 需求 1.3）', () => {
  const files = walk(SRC)
  const sites = files.flatMap((f) => syncCallSites(readFileSync(f, 'utf-8')).map((s) => ({ ...s, file: relative(SRC, f).split('\\').join('/') })))

  it('判据自身有效：漏传 / 传错 entryType 命中，正确写法不命中（双向）', () => {
    const call = (rest: string) => `useAdjustmentCentralSync({\n  wpCode: 'L1',\n  ${rest}\n  buildLineItems: () => [],\n})\n`
    expect(syncCallSites(call('itemId: () => `L1-adj-${activeType.value}`,'))[0].problem).toMatch(/entryType 应传 activeType/)
    expect(syncCallSites(call('itemId: () => `L1-adj-${activeType.value}`,\n  entryType: other,'))[0].problem).toMatch(/现为 other/)
    expect(syncCallSites(call("itemId: 'D4-4-rows',\n  entryType: activeType,"))[0].problem).toMatch(/固定值/)
    expect(syncCallSites(call('itemId: () => `L1-adj-${activeType.value}`,\n  entryType: activeType,'))[0].problem).toBeNull()
    expect(syncCallSites(call('itemId: () => `M4-adj-${adjustment.activeType.value}`,\n  entryType: adjustment.activeType,'))[0].problem).toBeNull()
    expect(syncCallSites(call("itemId: 'D4-4-rows',"))[0].problem).toBeNull()
  })

  it('全部调用点接线成立（防空转：≥ 81 处，其中按类型取 item_id 的 ≥ 24 处）', () => {
    expect(files.length).toBeGreaterThan(1000)
    expect(sites.length).toBeGreaterThanOrEqual(81)
    expect(sites.filter((s) => s.entryType).length).toBeGreaterThanOrEqual(24)
    expect(sites.filter((s) => s.problem).map((s) => `${s.file}: ${s.problem}`)).toEqual([])
    expect(sites.filter((s) => !s.wpCode).map((s) => s.file)).toEqual([])
  })

  it('这些底稿在目录里都恰有一张「调整分录」表，别名能解析到它', () => {
    const catalog = JSON.parse(readFileSync(join(repoRoot(), 'backend', 'data', 'acnr', 'global_catalog.json'), 'utf-8'))
    const names = new Map<string, string[]>()
    for (const s of catalog.sheets as Array<{ parent_wp_code?: string; sheet_name?: string; deprecated?: boolean }>) {
      if (s.deprecated || !s.parent_wp_code) continue
      names.set(s.parent_wp_code, [...(names.get(s.parent_wp_code) ?? []), s.sheet_name ?? ''])
    }
    const bad = [...new Set(sites.map((s) => s.wpCode!))].filter((code) => {
      const hit = resolveSheetNameByDeepLink(names.get(code) ?? [], ADJUSTMENT_SHEET_ALIAS)
      return !hit || !hit.includes('调整分录')
    })
    expect(bad).toEqual([])
  })

  it('调整分录页跳转带别名与 source_ref；渲染器解析 ?highlight= 并交给调度', () => {
    const adj = readFileSync(join(SRC, 'views', 'Adjustments.vue'), 'utf-8')
    const fn = balanced(adj, adj.indexOf('{', adj.indexOf('function jumpToSourceWorkpaper(')))
    expect(fn).toMatch(/query:\s*\{\s*sheet:\s*ADJUSTMENT_SHEET_ALIAS,\s*highlight:\s*ref\s*\}/)
    const renderer = readFileSync(join(SRC, 'components', 'workpaper', 'GtWpRenderer.vue'), 'utf-8')
    const deps = balanced(renderer, renderer.indexOf('{', renderer.indexOf('useRendererCellLocate({')))
    expect(deps).toMatch(/\bentryGroup:\s*locateAdjustmentEntryGroup\b/)
    expect(renderer).toMatch(/entryGroupOfHighlight\(route\?\.query\?\.highlight,\s*props\.wpId\)/)
    // 只有分录组（没有 ?cell=）也要发请求
    expect(renderer).toMatch(/if \(cellRef \|\| entryGroup\) rendererLocate\.request\(\{[^}]*\bentryGroup\b[^}]*\}\)/)
  })
})
