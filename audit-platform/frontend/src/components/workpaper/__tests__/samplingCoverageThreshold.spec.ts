/**
 * 覆盖率阈值单一真源 — 守卫
 *
 * spec: sampling-evaluation-and-governance-closure
 * Validates: Requirements 2.5, 2.6, 2.7, 2.8, 11.2, 11.3
 * Properties: Property 7
 *
 * 背景（2026-08-05 实证 F5）：60% 这个数字改造前写死在 `checkCAS1314Compliance` 函数体内，
 * 而它是平台唯一的覆盖率告警口径。CAS 1314 并未规定该比例，把平台经验值以准则名义硬编码
 * 会让审计师误判其性质。
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  DEFAULT_COVERAGE_THRESHOLD,
  THRESHOLD_SOURCE_LABELS,
  buildCoverageWarningMessage,
  formatThresholdPercent,
  resolveCoverageThreshold,
} from '../composables/samplingCoverageThreshold'

/** 定位仓库根：双哨兵具体文件向上查找（单哨兵将来遇到同名文件会误停）。 */
function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    const a = path.join(dir, 'backend', 'app', 'routers', 'voucher_sampling.py')
    const b = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('未找到仓库根（双哨兵均未命中）')
}

const ALGO_SRC = path.join(
  repoRoot(),
  'audit-platform/frontend/src/components/workpaper/composables/useSamplingAlgorithms.ts',
)

/** 去注释：判「源码里有没有某写法」前必须剥掉注释，否则说明文字会被数成真实代码。 */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/** 截出某函数体（花括号配对，不用固定字符窗口 —— 会溢出到下一个函数）。 */
function functionBody(src: string, decl: string): string {
  const at = src.indexOf(decl)
  if (at < 0) throw new Error(`未找到声明：${decl}`)
  // 跳过参数列表（圆括号配对），再找函数体起始花括号
  let i = src.indexOf('(', at)
  let paren = 0
  for (; i < src.length; i++) {
    if (src[i] === '(') paren++
    else if (src[i] === ')') {
      paren--
      if (paren === 0) break
    }
  }
  const open = src.indexOf('{', i)
  let depth = 0
  for (let j = open; j < src.length; j++) {
    if (src[j] === '{') depth++
    else if (src[j] === '}') {
      depth--
      if (depth === 0) return src.slice(open, j + 1)
    }
  }
  throw new Error(`函数体未闭合：${decl}`)
}

describe('resolveCoverageThreshold 优先级', () => {
  it('两级都未配置 → 平台默认 0.60 + 来源标签', () => {
    const r = resolveCoverageThreshold()
    expect(r.value).toBe(0.6)
    expect(r.source).toBe('platform_default')
    expect(r.sourceLabel).toBe(THRESHOLD_SOURCE_LABELS.platform_default)
  })

  it('底稿级优先于项目级', () => {
    const r = resolveCoverageThreshold({ workpaper: 0.75, project: 0.5 })
    expect(r.value).toBe(0.75)
    expect(r.source).toBe('workpaper')
  })

  it('仅项目级配置 → 用项目级', () => {
    const r = resolveCoverageThreshold({ project: 0.5 })
    expect(r.value).toBe(0.5)
    expect(r.source).toBe('project')
  })

  it.each([
    ['0（等于永不告警，应显式关闭而非设 0）', 0],
    ['负数', -0.3],
    ['大于 1（把百分数当小数传错，如 60）', 60],
    ['NaN', Number.NaN],
    ['Infinity', Number.POSITIVE_INFINITY],
    ['null', null],
    ['undefined', undefined],
  ])('非法底稿级值（%s）→ 回退项目级', (_label, bad) => {
    const r = resolveCoverageThreshold({ workpaper: bad as number, project: 0.4 })
    expect(r.value).toBe(0.4)
    expect(r.source).toBe('project')
  })

  it('两级都非法 → 平台默认（宁可用默认也不用错阈值）', () => {
    const r = resolveCoverageThreshold({ workpaper: 60, project: -1 })
    expect(r.value).toBe(DEFAULT_COVERAGE_THRESHOLD)
    expect(r.source).toBe('platform_default')
  })

  it('阈值 = 1（100% 覆盖）合法', () => {
    expect(resolveCoverageThreshold({ project: 1 }).source).toBe('project')
  })
})

describe('阈值文案', () => {
  it('整数百分比不带小数位', () => {
    expect(formatThresholdPercent(0.6)).toBe('60%')
    expect(formatThresholdPercent(1)).toBe('100%')
  })

  it('非整数保留 1 位小数', () => {
    expect(formatThresholdPercent(0.625)).toBe('62.5%')
  })

  it('告警文案含阈值与来源标签（R2.8）', () => {
    const msg = buildCoverageWarningMessage(resolveCoverageThreshold())
    expect(msg).toContain('60%')
    expect(msg).toContain('非准则规定')
  })

  it('来源标签全中文，不得出现裸英文枚举值', () => {
    for (const [key, label] of Object.entries(THRESHOLD_SOURCE_LABELS)) {
      expect(label).not.toBe(key)
      expect(/[\u4e00-\u9fa5]/.test(label)).toBe(true)
    }
  })
})

describe('Property 7：checkCAS1314Compliance 函数体内无覆盖率阈值字面量', () => {
  const body = stripComments(
    functionBody(fs.readFileSync(ALGO_SRC, 'utf-8'), 'export function checkCAS1314Compliance'),
  )

  it('函数体不含 60 / 0.6 这类覆盖率阈值字面量', () => {
    expect(body).not.toMatch(/\b0?\.6\b/)
    expect(body).not.toMatch(/amountRate\s*<\s*\d/)
  })

  it('函数体确实使用了入参阈值（防止「删掉判断」也能通过上一条）', () => {
    expect(body).toContain('coverageThreshold')
    expect(body).toContain('coverageThresholdLabel')
  })

  it('特定项目占比上限走模块级常量，不在函数体内写死', () => {
    expect(body).toContain('SPECIFIC_ITEM_RATIO_LIMIT')
    expect(body).not.toMatch(/ratio\s*>\s*0?\.5\b/)
  })

  it('反向自检：判据对「复现旧实现」的函数体必须打红', () => {
    const legacy = `{
      const amountRate = parseFloat(stats.amountCoverageRate) || 0
      if (amountRate < 60) { warnings.push({ type: 'coverage_low' }) }
      if (ratio > 0.5) { warnings.push({ type: 'specific_item_high' }) }
    }`
    // 三条判据里至少有一条要在旧实现上打红，否则守卫是空转的
    const wouldFail =
      /\b0?\.6\b/.test(legacy) ||
      /amountRate\s*<\s*\d/.test(legacy) ||
      /ratio\s*>\s*0?\.5\b/.test(legacy)
    expect(wouldFail).toBe(true)
  })

  it('自检：stripComments 真的剥掉了注释（否则说明文字会被当代码）', () => {
    const withComment = 'const a = 1 // amountRate < 60\n/* ratio > 0.5 */\nconst b = 2'
    const cleaned = stripComments(withComment)
    expect(cleaned).not.toContain('amountRate < 60')
    expect(cleaned).not.toContain('ratio > 0.5')
    expect(cleaned).toContain('const a = 1')
  })

  it('自检：functionBody 用花括号配对而非固定窗口（不会溢出到下一个函数）', () => {
    const src = 'function a(x: number) { return { y: 1 } }\nfunction b() { return 2 }'
    const bodyA = functionBody(src, 'function a')
    expect(bodyA).toContain('y: 1')
    expect(bodyA).not.toContain('return 2')
  })
})
