/**
 * queryTemplateCache.spec.ts — 模板列表缓存（advanced-query-linkage-closure 任务 27，design §4.1）
 */
import { describe, it, expect, beforeEach } from 'vitest'
import {
  TEMPLATE_LIST_CACHE_KEY,
  TEMPLATE_LIST_CACHE_TTL_MS,
  invalidateTemplateCache,
  readTemplateCache,
  writeTemplateCache,
} from '../queryTemplateCache'

const T0 = 1_800_000_000_000
const ITEMS = [{ id: 't1', name: '【测试】AQL 公开' }, { id: 't2', name: '【测试】AQL 私有' }]

beforeEach(() => {
  sessionStorage.clear()
})

describe('queryTemplateCache', () => {
  it('沿用 MyTemplatesDialog 的键与 5 分钟有效期；有效期内读回同一列表', () => {
    expect(TEMPLATE_LIST_CACHE_KEY).toBe('gt:cqd:my-templates-cache')
    expect(TEMPLATE_LIST_CACHE_TTL_MS).toBe(5 * 60 * 1000)
    writeTemplateCache(ITEMS, { owner: 'u1', now: T0 })
    expect(readTemplateCache({ owner: 'u1', now: T0 + TEMPLATE_LIST_CACHE_TTL_MS - 1 })).toEqual(ITEMS)
    expect(readTemplateCache({ owner: 'u1', now: T0 + TEMPLATE_LIST_CACHE_TTL_MS })).toBeNull()
  })

  it('换人登录不读到上一个人的列表（模板可见性因人而异）', () => {
    writeTemplateCache(ITEMS, { owner: 'u1', now: T0 })
    expect(readTemplateCache({ owner: 'u2', now: T0 + 1 })).toBeNull()
  })

  it('损坏的条目返回 null 并被删掉；失效后读不到', () => {
    sessionStorage.setItem(TEMPLATE_LIST_CACHE_KEY, '{not json')
    expect(readTemplateCache({ owner: 'u1' })).toBeNull()
    expect(sessionStorage.getItem(TEMPLATE_LIST_CACHE_KEY)).toBeNull()
    writeTemplateCache(ITEMS, { owner: 'u1' })
    invalidateTemplateCache()
    expect(readTemplateCache({ owner: 'u1' })).toBeNull()
  })

  it('独立键互不影响（W3 系统预置列表用另一个键）', () => {
    writeTemplateCache(ITEMS, { owner: 'u1', now: T0 })
    writeTemplateCache([{ id: 'je_weekend' }], { owner: 'u1', key: 'gt:cqd:presets-cache', now: T0 })
    invalidateTemplateCache({ key: 'gt:cqd:presets-cache' })
    expect(readTemplateCache({ owner: 'u1', now: T0 + 1 })).toEqual(ITEMS)
    expect(readTemplateCache({ owner: 'u1', key: 'gt:cqd:presets-cache', now: T0 + 1 })).toBeNull()
  })
})
