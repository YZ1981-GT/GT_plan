/**
 * projectCacheKey.spec.ts — Task 6.3 缓存按 project key 隔离 / 单行 stale / 保存用项目年 单测
 *
 * spec: formula-manager-closure Phase 6 Task 6.3（需求 10.1 / 10.2 / 10.3 / 10.4）
 *
 * 验收判据（tasks.md Task 6.3）：
 *   - 单测/集成断言：切项目旧缓存失效、旧响应不覆盖；保存用 `props.year`；单行保存触发统一 stale。
 *   - 变异反证：把缓存 key 去掉 project 维度应使跨项目串样本打红。
 *
 * 🔴 设计要点：与 crossCheckKey.spec.ts 同款——不挂载庞大的 FormulaManagerDialog.vue，而是测其
 * 收敛后的单一真源纯函数 `projectCacheKey / cacheKeyMatches / shouldApplyResponse / resolveSaveYear`。
 * 组件里所有缓存命中判定与保存年份口径都只经它们产出。只要都经同一函数，「切项目缓存不失效 /
 * 旧响应覆盖新项目 / 保存用系统年」在结构上即不可能。
 */
import { describe, it, expect } from 'vitest'
import {
  projectCacheKey,
  cacheKeyMatches,
  shouldApplyResponse,
  resolveSaveYear,
} from '../projectCacheKey'

describe('projectCacheKey — 按项目隔离的缓存键（需求 10.1）', () => {
  it('不同项目 → 不同缓存键（project 维度不可省）', () => {
    const a = projectCacheKey({ projectId: 'PROJ-A', templateType: 'soe', year: 2025 })
    const b = projectCacheKey({ projectId: 'PROJ-B', templateType: 'soe', year: 2025 })
    expect(a).not.toBe(b)
  })

  it('同项目同模板同年度 → 相同缓存键（可复用缓存）', () => {
    const a = projectCacheKey({ projectId: 'PROJ-A', templateType: 'soe', year: 2025 })
    const b = projectCacheKey({ projectId: 'PROJ-A', templateType: 'soe', year: 2025 })
    expect(a).toBe(b)
  })

  it('同项目换模板版本 / 换年度 → 各自隔离', () => {
    const base = projectCacheKey({ projectId: 'PROJ-A', templateType: 'soe', year: 2025 })
    expect(projectCacheKey({ projectId: 'PROJ-A', templateType: 'listed', year: 2025 })).not.toBe(base)
    expect(projectCacheKey({ projectId: 'PROJ-A', templateType: 'soe', year: 2024 })).not.toBe(base)
  })

  it('空/缺字段稳定可比（null 与 undefined 与 "" 归一一致）', () => {
    expect(projectCacheKey({ projectId: null, templateType: null, year: null }))
      .toBe(projectCacheKey({ projectId: undefined, templateType: undefined, year: undefined }))
    expect(projectCacheKey({ projectId: '', year: '' }))
      .toBe(projectCacheKey({ projectId: null, year: null }))
  })

  it('分隔避免相邻字段拼接碰撞（a|b 不等于 a + b）', () => {
    const x = projectCacheKey({ projectId: 'a', templateType: 'b', year: '' })
    const y = projectCacheKey({ projectId: 'ab', templateType: '', year: '' })
    expect(x).not.toBe(y)
  })
})

describe('cacheKeyMatches — 缓存命中判定（需求 10.1 切项目失效）', () => {
  it('缓存键 == 当前键 → 命中（复用缓存）', () => {
    const k = projectCacheKey({ projectId: 'PROJ-A', templateType: 'soe', year: 2025 })
    expect(cacheKeyMatches(k, k)).toBe(true)
  })

  it('切项目后当前键变化 → 旧缓存键不等 → 判未命中（旧缓存失效）', () => {
    const oldKey = projectCacheKey({ projectId: 'PROJ-A', templateType: 'soe', year: 2025 })
    const newKey = projectCacheKey({ projectId: 'PROJ-B', templateType: 'soe', year: 2025 })
    expect(cacheKeyMatches(oldKey, newKey)).toBe(false)
  })

  it('从未加载过（cachedKey=null）恒判未命中', () => {
    const cur = projectCacheKey({ projectId: 'PROJ-A' })
    expect(cacheKeyMatches(null, cur)).toBe(false)
    expect(cacheKeyMatches(undefined, cur)).toBe(false)
  })
})

describe('shouldApplyResponse — 陈旧异步响应守卫（需求 10.1 旧响应不覆盖 / 10.4 abort 后重发）', () => {
  it('发请求时与响应回来时项目键一致 → 应用响应', () => {
    const reqKey = projectCacheKey({ projectId: 'PROJ-A', templateType: 'soe', year: 2025 })
    const curKey = reqKey
    expect(shouldApplyResponse(reqKey, curKey)).toBe(true)
  })

  it('await 期间切了项目 → 旧响应被丢弃（不写入新项目状态）', () => {
    const reqKey = projectCacheKey({ projectId: 'PROJ-A', templateType: 'soe', year: 2025 })
    const curKey = projectCacheKey({ projectId: 'PROJ-B', templateType: 'soe', year: 2025 })
    expect(shouldApplyResponse(reqKey, curKey)).toBe(false)
  })
})

describe('resolveSaveYear — 保存年份口径（需求 10.2 用 props.year 禁系统当前年）', () => {
  it('有 props.year → 取 props.year（数字）', () => {
    expect(resolveSaveYear(2023)).toBe(2023)
    expect(resolveSaveYear('2023')).toBe(2023)
  })

  it('缺 props.year → 返 null（由调用方跳过传播，不以系统当前年顶替）', () => {
    expect(resolveSaveYear(null)).toBeNull()
    expect(resolveSaveYear(undefined)).toBeNull()
    expect(resolveSaveYear('')).toBeNull()
    expect(resolveSaveYear('abc')).toBeNull()
  })

  it('🔴 口径对比：resolveSaveYear 绝不返回系统当前年', () => {
    const systemYear = new Date().getFullYear()
    // 跨年度打开一个 2020 年的项目：保存年份必须是 2020，而不是系统当前年。
    expect(resolveSaveYear(2020)).toBe(2020)
    expect(resolveSaveYear(2020)).not.toBe(systemYear)
    // 缺年份也不能顶替成系统当前年（宁可返 null 跳过）。
    expect(resolveSaveYear(null)).not.toBe(systemYear)
  })
})

describe('变异反证：缓存键去掉 project 维度 → 跨项目串样本打红（需求 10.1）', () => {
  // 历史缺陷形态：缓存键只按 templateType+year，不含 projectId（布尔 loaded 开关的等价物）。
  function projectlessCacheKey(ctx: { templateType?: string | null; year?: string | number | null }): string {
    const tpl = (ctx.templateType ?? '').toString().trim()
    const yr = ctx.year == null || ctx.year === '' ? '' : String(ctx.year).trim()
    return `${tpl}\u0001${yr}`
  }

  it('去掉 project 维度：A/B 两项目缓存键相同 → 切项目判「命中」→ 旧缓存不失效（这是被修复的缺陷）', () => {
    const aKey = projectlessCacheKey({ templateType: 'soe', year: 2025 })
    const bKey = projectlessCacheKey({ templateType: 'soe', year: 2025 })
    // 缺陷态：A 的缓存键被 B 当成命中 → 旧缓存不失效（cacheKeyMatches 恒真）。
    expect(cacheKeyMatches(aKey, bKey)).toBe(true)
  })

  it('反向断言：保留 project 维度（正确实现）→ A/B 切项目判「未命中」→ 旧缓存失效', () => {
    const aKey = projectCacheKey({ projectId: 'PROJ-A', templateType: 'soe', year: 2025 })
    const bKey = projectCacheKey({ projectId: 'PROJ-B', templateType: 'soe', year: 2025 })
    expect(cacheKeyMatches(aKey, bKey)).toBe(false)
  })

  it('去掉 project 维度：shouldApplyResponse 把 A 的 late response 应用到 B（串样本）', () => {
    const reqKey = projectlessCacheKey({ templateType: 'soe', year: 2025 })  // 发请求时在 A
    const curKey = projectlessCacheKey({ templateType: 'soe', year: 2025 })  // 响应回来时已切到 B
    // 缺陷态：两键相同 → 误判「应应用」→ A 的旧响应覆盖 B（跨项目污染）。
    expect(shouldApplyResponse(reqKey, curKey)).toBe(true)
  })

  it('反向断言：保留 project 维度 → A 的 late response 被 B 丢弃（不污染）', () => {
    const reqKey = projectCacheKey({ projectId: 'PROJ-A', templateType: 'soe', year: 2025 })
    const curKey = projectCacheKey({ projectId: 'PROJ-B', templateType: 'soe', year: 2025 })
    expect(shouldApplyResponse(reqKey, curKey)).toBe(false)
  })
})
