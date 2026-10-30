/**
 * queryIndicatorCache.spec.ts — 指标树缓存（advanced-query-linkage-closure 任务 27；ADR-AQL-16，R10.4）
 *
 * 键含 schema、项目、年度与附注版本：附注重新生成 / 对齐（附注版本变化）或切换年度后旧缓存不命中。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import {
  INDICATOR_CACHE_PREFIX,
  indicatorCacheKey,
  purgeStaleIndicatorCache,
  readIndicatorCache,
  writeIndicatorCache,
} from '../queryIndicatorCache'

const PID = '005a6f2d-cecd-4e30-bcbd-9fb01236c194'
const OTHER = '5942c12e-65fb-4187-ace3-79d45a90cb53'
const TREE = [{ key: 'tb', label: '试算平衡表', children: [{ key: 'tb_detail', label: '试算平衡表（科目）' }] }]

beforeEach(() => {
  sessionStorage.clear()
})

describe('indicatorCacheKey', () => {
  it('四段：schema / 项目 / 年度 / 附注版本', () => {
    expect(indicatorCacheKey({ schema: 12, projectId: PID, year: 2025, notesVersion: '3f2a9c01be44' }))
      .toBe(`gt:custom-query:indicators:12:${PID}:2025:3f2a9c01be44`)
  })

  it('缺省段：unknown / no-project / no-year / none；非法年度当作没有', () => {
    expect(indicatorCacheKey({})).toBe(`${INDICATOR_CACHE_PREFIX}unknown:no-project:no-year:none`)
    expect(indicatorCacheKey({ schema: '12', projectId: PID, year: 1999 })).toBe(`${INDICATOR_CACHE_PREFIX}12:${PID}:no-year:none`)
  })

  it('年度或附注版本变化即换键（旧缓存不命中）', () => {
    const base = { schema: 12, projectId: PID, year: 2025, notesVersion: 'v1' }
    writeIndicatorCache(indicatorCacheKey(base), TREE)
    expect(readIndicatorCache(indicatorCacheKey(base))).toEqual(TREE)
    expect(readIndicatorCache(indicatorCacheKey({ ...base, notesVersion: 'v2' }))).toBeNull()
    expect(readIndicatorCache(indicatorCacheKey({ ...base, year: 2024 }))).toBeNull()
  })
})

describe('purgeStaleIndicatorCache / writeIndicatorCache', () => {
  it('写入时清掉：schema 不同的、同项目同年度附注版本不同的、改造前的旧格式键；保留别的项目与年度', () => {
    const keep1 = indicatorCacheKey({ schema: 12, projectId: OTHER, year: 2025, notesVersion: 'x' })
    const keep2 = indicatorCacheKey({ schema: 12, projectId: PID, year: 2024, notesVersion: 'y' })
    const staleSchema = indicatorCacheKey({ schema: 11, projectId: OTHER, year: 2025, notesVersion: 'x' })
    const staleVersion = indicatorCacheKey({ schema: 12, projectId: PID, year: 2025, notesVersion: 'v1' })
    const legacy = `${INDICATOR_CACHE_PREFIX}11:${PID}`
    for (const k of [keep1, keep2, staleSchema, staleVersion, legacy]) sessionStorage.setItem(k, '[]')
    sessionStorage.setItem('gt:query-builder:schema-v2', '{}')

    const current = indicatorCacheKey({ schema: 12, projectId: PID, year: 2025, notesVersion: 'v2' })
    writeIndicatorCache(current, TREE)

    expect(readIndicatorCache(current)).toEqual(TREE)
    for (const k of [keep1, keep2]) expect(sessionStorage.getItem(k)).toBe('[]')
    for (const k of [staleSchema, staleVersion, legacy]) expect(sessionStorage.getItem(k)).toBeNull()
    expect(sessionStorage.getItem('gt:query-builder:schema-v2')).toBe('{}')
    expect(purgeStaleIndicatorCache(current)).toBe(0)
  })

  it('树形（任务 29）：页面版「骨架 + 附注分支」与弹窗全量树互不命中、写入互不清除；同一树形的旧附注版本照样清掉', () => {
    const full = { schema: 14, projectId: PID, year: 2025, notesVersion: 'v1' }
    const page = { ...full, variant: 'page' }
    expect(indicatorCacheKey(page)).toBe(`${INDICATOR_CACHE_PREFIX}14:${PID}~page:2025:v1`)
    writeIndicatorCache(indicatorCacheKey(full), TREE)
    expect(readIndicatorCache(indicatorCacheKey(page)), '页面版不能读到弹窗的全量树').toBeNull()
    writeIndicatorCache(indicatorCacheKey(page), [{ key: 'page-only' }])
    expect(readIndicatorCache(indicatorCacheKey(full)), '写页面版不清掉弹窗的全量树').toEqual(TREE)
    writeIndicatorCache(indicatorCacheKey({ ...page, notesVersion: 'v2' }), [])
    expect(sessionStorage.getItem(indicatorCacheKey(page)), '同一树形旧附注版本清掉').toBeNull()
    expect(readIndicatorCache(indicatorCacheKey(full))).toEqual(TREE)
  })

  it('损坏条目读回 null 并被删掉', () => {
    const k = indicatorCacheKey({ schema: 12, projectId: PID, year: 2025 })
    sessionStorage.setItem(k, '{broken')
    expect(readIndicatorCache(k)).toBeNull()
    expect(sessionStorage.getItem(k)).toBeNull()
  })
})
