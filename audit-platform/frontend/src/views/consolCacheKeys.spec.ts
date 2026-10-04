/**
 * 合并页缓存键单测（spec consol-node-key-isolation-and-shared-context 任务 5.3，需求 4.5 / 5.4，设计 §七、P9）。
 *
 * 覆盖：
 *  - 四维（project/year/nodeKey/report-or-template）全部进入缓存键
 *  - 同企业不同角色节点（consol vs consol_elim）缓存键不相等、互不串用
 *  - 精确清理只删当前节点，不波及同企业其他角色节点、其他项目/年度、其他 section
 *  - 反向变异：去掉前缀尾冒号会误伤 consol_elim —— 证明尾冒号是必需的身份边界（禁恒绿）
 *  - types 过滤：all_reports / notes / 逐报表类型
 */
import { describe, it, expect } from 'vitest'
import {
  cacheScopeKey,
  reportCacheKey,
  noteCacheKey,
  clearPrefix,
  clearNodeCache,
} from './consolCacheKeys'

describe('consolCacheKeys — 四维缓存键', () => {
  it('scope 含 project/year/nodeKey 三维', () => {
    expect(cacheScopeKey(5, 2025, 'A:consol')).toBe('5:2025:A:consol')
  })

  it('报表键含第四维 reportType + templateType', () => {
    expect(reportCacheKey(5, 2025, 'A:consol', 'balance_sheet', 'soe'))
      .toBe('5:2025:A:consol:balance_sheet:soe')
  })

  it('附注键含 notes + templateType 第四维', () => {
    expect(noteCacheKey(5, 2025, 'A:consol', 'listed'))
      .toBe('5:2025:A:consol:notes:listed')
  })

  it('改变任一维度都产生不同缓存键', () => {
    const base = reportCacheKey(5, 2025, 'A:consol', 'balance_sheet', 'soe')
    expect(reportCacheKey(6, 2025, 'A:consol', 'balance_sheet', 'soe')).not.toBe(base) // project
    expect(reportCacheKey(5, 2024, 'A:consol', 'balance_sheet', 'soe')).not.toBe(base) // year
    expect(reportCacheKey(5, 2025, 'A:parent', 'balance_sheet', 'soe')).not.toBe(base) // nodeKey
    expect(reportCacheKey(5, 2025, 'A:consol', 'income_statement', 'soe')).not.toBe(base) // reportType
    expect(reportCacheKey(5, 2025, 'A:consol', 'balance_sheet', 'listed')).not.toBe(base) // template
  })

  it('同企业不同角色节点（consol vs consol_elim）缓存键不相等', () => {
    const consol = reportCacheKey(5, 2025, 'A:consol', 'balance_sheet', 'soe')
    const elim = reportCacheKey(5, 2025, 'A:consol_elim', 'balance_sheet', 'soe')
    expect(consol).not.toBe(elim)
  })
})

/** 构造一套跨节点/项目/年度的缓存快照，用于验证清理精确性。 */
function seedCaches() {
  const reportCache = new Map<string, unknown>()
  const noteCache = new Map<string, unknown>()
  // 当前节点 A:consol
  reportCache.set(reportCacheKey(5, 2025, 'A:consol', 'balance_sheet', 'soe'), ['consol-bs'])
  reportCache.set(reportCacheKey(5, 2025, 'A:consol', 'income_statement', 'soe'), ['consol-is'])
  noteCache.set(noteCacheKey(5, 2025, 'A:consol', 'soe'), ['consol-note'])
  // 同企业另一角色 A:consol_elim（consol 的前缀族，最易串用）
  reportCache.set(reportCacheKey(5, 2025, 'A:consol_elim', 'balance_sheet', 'soe'), ['elim-bs'])
  noteCache.set(noteCacheKey(5, 2025, 'A:consol_elim', 'soe'), ['elim-note'])
  // 其他项目 / 其他年度 / 其他 section 维度
  reportCache.set(reportCacheKey(6, 2025, 'A:consol', 'balance_sheet', 'soe'), ['other-project'])
  reportCache.set(reportCacheKey(5, 2024, 'A:consol', 'balance_sheet', 'soe'), ['other-year'])
  return { reportCache, noteCache }
}

describe('consolCacheKeys — 精确清理只清当前节点', () => {
  it('清 A:consol 不波及同企业 A:consol_elim、其他项目/年度', () => {
    const { reportCache, noteCache } = seedCaches()
    clearNodeCache(reportCache, noteCache, 5, 2025, 'A:consol')

    // A:consol 的报表与附注被清
    expect(reportCache.has(reportCacheKey(5, 2025, 'A:consol', 'balance_sheet', 'soe'))).toBe(false)
    expect(reportCache.has(reportCacheKey(5, 2025, 'A:consol', 'income_statement', 'soe'))).toBe(false)
    expect(noteCache.has(noteCacheKey(5, 2025, 'A:consol', 'soe'))).toBe(false)

    // A:consol_elim 不受影响（关键：不串用）
    expect(reportCache.has(reportCacheKey(5, 2025, 'A:consol_elim', 'balance_sheet', 'soe'))).toBe(true)
    expect(noteCache.has(noteCacheKey(5, 2025, 'A:consol_elim', 'soe'))).toBe(true)

    // 其他项目/年度不受影响
    expect(reportCache.has(reportCacheKey(6, 2025, 'A:consol', 'balance_sheet', 'soe'))).toBe(true)
    expect(reportCache.has(reportCacheKey(5, 2024, 'A:consol', 'balance_sheet', 'soe'))).toBe(true)
  })

  it('types=[notes] 只清附注，保留报表', () => {
    const { reportCache, noteCache } = seedCaches()
    clearNodeCache(reportCache, noteCache, 5, 2025, 'A:consol', ['notes'])
    expect(noteCache.has(noteCacheKey(5, 2025, 'A:consol', 'soe'))).toBe(false)
    expect(reportCache.has(reportCacheKey(5, 2025, 'A:consol', 'balance_sheet', 'soe'))).toBe(true)
  })

  it('types=[balance_sheet] 只清该报表类型的两套模板口径', () => {
    const reportCache = new Map<string, unknown>()
    const noteCache = new Map<string, unknown>()
    reportCache.set(reportCacheKey(5, 2025, 'A:consol', 'balance_sheet', 'soe'), ['bs-soe'])
    reportCache.set(reportCacheKey(5, 2025, 'A:consol', 'balance_sheet', 'listed'), ['bs-listed'])
    reportCache.set(reportCacheKey(5, 2025, 'A:consol', 'income_statement', 'soe'), ['is-soe'])
    clearNodeCache(reportCache, noteCache, 5, 2025, 'A:consol', ['balance_sheet'])
    expect(reportCache.has(reportCacheKey(5, 2025, 'A:consol', 'balance_sheet', 'soe'))).toBe(false)
    expect(reportCache.has(reportCacheKey(5, 2025, 'A:consol', 'balance_sheet', 'listed'))).toBe(false)
    expect(reportCache.has(reportCacheKey(5, 2025, 'A:consol', 'income_statement', 'soe'))).toBe(true)
  })

  it('all_reports 清该节点所有报表但保留附注', () => {
    const { reportCache, noteCache } = seedCaches()
    clearNodeCache(reportCache, noteCache, 5, 2025, 'A:consol', ['all_reports'])
    expect(reportCache.has(reportCacheKey(5, 2025, 'A:consol', 'balance_sheet', 'soe'))).toBe(false)
    expect(reportCache.has(reportCacheKey(5, 2025, 'A:consol', 'income_statement', 'soe'))).toBe(false)
    expect(noteCache.has(noteCacheKey(5, 2025, 'A:consol', 'soe'))).toBe(true)
  })
})

describe('consolCacheKeys — 尾冒号身份边界（反向变异，禁恒绿）', () => {
  it('清理前缀必带尾冒号', () => {
    expect(clearPrefix(5, 2025, 'A:consol')).toBe('5:2025:A:consol:')
    expect(clearPrefix(5, 2025, 'A:consol').endsWith(':')).toBe(true)
  })

  it('consol_elim 键不以 consol 的带冒号前缀开头（正向：边界成立）', () => {
    const elim = reportCacheKey(5, 2025, 'A:consol_elim', 'balance_sheet', 'soe')
    expect(elim.startsWith(clearPrefix(5, 2025, 'A:consol'))).toBe(false)
  })

  it('反向变异证明：若用无尾冒号前缀，consol_elim 会被误伤', () => {
    const elim = reportCacheKey(5, 2025, 'A:consol_elim', 'balance_sheet', 'soe')
    const prefixNoColon = cacheScopeKey(5, 2025, 'A:consol') // 故意漏尾冒号
    // 这正是去掉尾冒号后 clearNodeCache 会命中的错误情况；断言它确实为 true，
    // 以证明尾冒号是必需边界而非冗余字符（若实现去掉尾冒号，上一条正向用例会转红）。
    expect(elim.startsWith(prefixNoColon)).toBe(true)
  })
})
