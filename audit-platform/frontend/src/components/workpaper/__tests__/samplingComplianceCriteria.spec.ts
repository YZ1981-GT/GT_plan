/**
 * 合规检查判据接线 — 守卫
 *
 * spec: sampling-evaluation-and-governance-closure
 * Validates: Requirements 2.1, 2.2, 2.3, 2.4, 11.2, 11.3
 * Properties: Property 5, Property 6
 *
 * 背景（2026-08-05 实证 F4）：`useVoucherSampling.checkCompliance` 改造前传的是
 * `(selectedCount, sampledVouchers.length)` 即「勾选数 / 抽出总数」，与两条规则的语义
 * 都不符。函数签名改成 options 对象后，**光靠函数自身的单测抓不到「调用点传错」** ——
 * 因为传错的仍是合法数字。故本文件做源码级接线断言 + 行为级不变式。
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  checkCAS1314Compliance,
  type ComplianceCheckInput,
  type CoverageStats,
} from '../composables/useSamplingAlgorithms'
import {
  DEFAULT_COVERAGE_THRESHOLD,
  THRESHOLD_SOURCE_LABELS,
} from '../composables/samplingCoverageThreshold'

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

const CONSUMER_SRC = path.join(
  repoRoot(),
  'audit-platform/frontend/src/components/workpaper/composables/useVoucherSampling.ts',
)

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function functionBody(src: string, decl: string): string {
  const at = src.indexOf(decl)
  if (at < 0) throw new Error(`未找到声明：${decl}`)
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

const stats = (rate: string): CoverageStats => ({
  populationCount: 1000,
  populationAmount: '1000000.00',
  sampleCount: 30,
  sampleAmount: '300000.00',
  countCoverageRate: '3.00',
  amountCoverageRate: rate,
})

const input = (over: Partial<ComplianceCheckInput> = {}): ComplianceCheckInput => ({
  stats: stats('80.00'),
  method: 'random',
  methodSampleCount: 30,
  totalSampleCount: 100,
  suggestedSampleSize: null,
  coverageThreshold: DEFAULT_COVERAGE_THRESHOLD,
  coverageThresholdLabel: THRESHOLD_SOURCE_LABELS.platform_default,
  ...over,
})

// ─── Property 5：特定项目占比判据与勾选无关 ──────────────────────────────────

describe('Property 5：特定项目占比判据与勾选无关', () => {
  it('同一样本构成下，改变「勾选多少」不改变告警集合', () => {
    // 新签名里根本没有「勾选数」这个入参 —— 这本身就是结构性保证。
    // 此处以「分子固定、分母固定」验证输出稳定，并在下一条用源码断言钉死调用点。
    const base = { method: 'specific_item' as const, methodSampleCount: 60, totalSampleCount: 100 }
    const a = checkCAS1314Compliance(input(base))
    const b = checkCAS1314Compliance(input(base))
    expect(a.map(w => w.type)).toEqual(b.map(w => w.type))
    expect(a.some(w => w.type === 'specific_item_high')).toBe(true)
  })

  it('全部样本都来自特定项目（分母==分子）→ 判据不可用，不告警', () => {
    const w = checkCAS1314Compliance(
      input({ method: 'specific_item', methodSampleCount: 40, totalSampleCount: 40 }),
    )
    expect(w.some(t => t.type === 'specific_item_high')).toBe(false)
  })

  it('存在其它方法样本且特定项目过半 → 告警，文案含实际占比', () => {
    const w = checkCAS1314Compliance(
      input({ method: 'specific_item', methodSampleCount: 60, totalSampleCount: 100 }),
    )
    const hit = w.find(t => t.type === 'specific_item_high')!
    expect(hit.message).toContain('60')
    expect(hit.message).toContain('100')
  })
})

// ─── Property 6：MUS 判据基于建议样本量 ──────────────────────────────────────

describe('Property 6：MUS 样本量判据基于系统建议样本量', () => {
  it.each([
    [5, 10, true],
    [10, 10, false],
    [11, 10, false],
  ])('实际 %i / 建议 %i → 告警=%s', (actual, suggested, expected) => {
    const w = checkCAS1314Compliance(
      input({ method: 'mus', totalSampleCount: actual, suggestedSampleSize: suggested }),
    )
    expect(w.some(t => t.type === 'mus_insufficient')).toBe(expected)
  })

  it.each([[null], [0], [-1]])('建议样本量不可用（%s）→ 不告警', suggested => {
    const w = checkCAS1314Compliance(
      input({ method: 'mus', totalSampleCount: 1, suggestedSampleSize: suggested as number }),
    )
    expect(w.some(t => t.type === 'mus_insufficient')).toBe(false)
  })

  it('非 mus 方法即使样本量不足也不产生 mus_insufficient', () => {
    const w = checkCAS1314Compliance(
      input({ method: 'random', totalSampleCount: 1, suggestedSampleSize: 100 }),
    )
    expect(w.some(t => t.type === 'mus_insufficient')).toBe(false)
  })
})

// ─── 调用点接线（源码级）────────────────────────────────────────────────────

describe('调用点接线：不得再传勾选数', () => {
  const body = stripComments(
    functionBody(fs.readFileSync(CONSUMER_SRC, 'utf-8'), 'function checkCompliance'),
  )

  it('checkCompliance 内不得引用 selectedCount（勾选数与两条规则语义都无关）', () => {
    expect(body).not.toContain('selectedCount')
  })

  it('按 options 对象调用且六个语义入参齐备', () => {
    expect(body).toContain('checkCAS1314Compliance({')
    for (const key of [
      'stats:',
      'method:',
      'methodSampleCount:',
      'totalSampleCount:',
      'suggestedSampleSize:',
      'coverageThreshold:',
      'coverageThresholdLabel:',
    ]) {
      expect(body).toContain(key)
    }
  })

  it('分母纳入底稿现有样本数（占比判据可用性的前提）', () => {
    expect(body).toContain('existingSampleCount')
    expect(body).toMatch(/totalSampleCount:\s*existingCount\s*\+\s*thisRoundCount/)
  })

  it('建议样本量为 0 时传 null（判据不可用而非默认告警）', () => {
    expect(body).toMatch(/suggested\s*!=\s*null\s*&&\s*suggested\s*>\s*0\s*\?/)
    expect(body).toContain('usableSuggested')
  })

  it('阈值走 resolveCoverageThreshold，不在调用点写死', () => {
    expect(body).toContain('resolveCoverageThreshold(')
    expect(body).not.toMatch(/coverageThreshold:\s*0?\.\d/)
  })

  it('反向自检：复现旧调用（传 selectedCount）必被上面第一条打红', () => {
    const legacy = `{
      const warnings = checkCAS1314Compliance(
        coverageStats.value, config.value.samplingMethod,
        selectedCount.value, sampledVouchers.value.length,
      )
    }`
    expect(legacy).toContain('selectedCount')
  })

  it('自检：函数体截取非空且确实是 checkCompliance（防正则失效空转）', () => {
    expect(body.length).toBeGreaterThan(200)
    expect(body).toContain('complianceWarnings.value = warnings')
  })
})

// ─── 阈值留痕进评价载荷 ──────────────────────────────────────────────────────

describe('阈值随评价留痕（R2.6）', () => {
  const body = stripComments(
    functionBody(fs.readFileSync(CONSUMER_SRC, 'utf-8'), 'function buildEvaluationPayload'),
  )

  it('评价载荷含 coverage_threshold 与来源', () => {
    expect(body).toContain('coverage_threshold:')
    expect(body).toContain('coverage_threshold_source:')
  })

  it('取的是本次实际生效值（coverageThreshold ref）而非重新算', () => {
    expect(body).toContain('coverageThreshold.value')
  })
})
