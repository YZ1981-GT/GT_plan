/**
 * 偏差性质结构化 — 守卫
 *
 * spec: sampling-evaluation-and-governance-closure
 * Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 11.2, 11.3
 * Properties: Property 11, Property 12
 *
 * 核心是 Property 11 的**交叉锁死**：中文标签在运行时从 C 类
 * `useDeviationDecisionTree.getStepOptions(2)` 取，本模块不做硬编码副本。
 * C 类改口径 → 这里立刻打红，而不是两侧长期漂移。
 */
import fs from 'node:fs'
import path from 'node:path'

import { describe, expect, it } from 'vitest'

import { getStepOptions } from '@/composables/useDeviationDecisionTree'

import {
  DEVIATION_NATURES,
  NATURE_REQUIRING_EXPLANATION,
  NO_SIMPLE_PROJECTION_HINT,
  buildDeviationNatureSummaryPayload,
  deviationNatureLabels,
  isDeviation,
  summarizeDeviationNature,
  type DeviationAnnotationMap,
} from '../composables/samplingDeviationNature'
import type { SampledVoucher } from '../composables/useSamplingAlgorithms'

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

const sample = (over: Partial<SampledVoucher> = {}): SampledVoucher => ({
  voucherNo: 'V-1',
  voucherDate: '2025-06-01',
  summary: null,
  debitAmount: '1000.00',
  creditAmount: null,
  accountCode: '1122',
  accountName: null,
  counterpartAccount: null,
  voucherType: null,
  accountingPeriod: 6,
  checkResult: 'N',
  abnormal: false,
  remark: '',
  selected: true,
  phase: 'final',
  editTrail: [],
  ...over,
})

// ─── Property 11：口径与 C 类交叉锁死 ────────────────────────────────────────

describe('Property 11：偏差性质口径复用 C 类控制测试', () => {
  it('三个 key 与 C 类 getStepOptions(2) 的选项数一致', () => {
    expect(DEVIATION_NATURES).toHaveLength(getStepOptions(2).length)
  })

  it('中文标签逐字取自 C 类，不做硬编码副本', () => {
    const labels = deviationNatureLabels()
    const cLabels = getStepOptions(2).map(o => o.label)
    expect(Object.values(labels)).toEqual(cLabels)
    // 实证：C 类三值是「系统性偏差 / 人为偏差 / 随机性偏差」
    expect(cLabels).toEqual(['系统性偏差', '人为偏差', '随机性偏差'])
  })

  it('key → 标签映射方向正确（不是顺序巧合）', () => {
    const labels = deviationNatureLabels()
    expect(labels.systematic).toContain('系统性')
    expect(labels.human).toContain('人为')
    expect(labels.random).toContain('随机')
  })

  it('源码不得硬编码这三个中文标签（防双真源）', () => {
    const src = fs.readFileSync(
      path.join(
        repoRoot(),
        'audit-platform/frontend/src/components/workpaper/composables/samplingDeviationNature.ts',
      ),
      'utf-8',
    )
    // 剥注释后才判 —— 注释里会如实写出这三个标签作为说明
    const code = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
    for (const label of ['系统性偏差', '人为偏差', '随机性偏差']) {
      expect(code).not.toContain(`'${label}'`)
      expect(code).not.toContain(`"${label}"`)
    }
  })

  it('「待判断」不是枚举值（与 C 类的 null 语义一致）', () => {
    expect(DEVIATION_NATURES).not.toContain('undetermined' as never)
    expect(DEVIATION_NATURES).not.toContain('isolated' as never)
  })

  it('需说明性质恰为系统性与人为（随机性可常规外推）', () => {
    expect([...NATURE_REQUIRING_EXPLANATION]).toEqual(['systematic', 'human'])
  })
})

// ─── Property 12：门控输入 ───────────────────────────────────────────────────

describe('Property 12：待判断与缺说明均产生阻断输入', () => {
  it('无偏差 → 全空，不产生任何阻断输入（零回归）', () => {
    const r = summarizeDeviationNature(
      [sample({ checkResult: 'Y' }), sample({ voucherNo: 'V-2', checkResult: 'Y' })],
      {},
    )
    expect(r).toMatchObject({
      total: 0,
      unannotated: [],
      missingExplanation: [],
      hasNonProjectable: false,
    })
    expect(r.summary).toEqual({})
  })

  it('偏差未标注性质 → 进 unannotated', () => {
    const r = summarizeDeviationNature([sample({ checkResult: 'N' })], {})
    expect(r.unannotated).toEqual(['V-1'])
    expect(r.total).toBe(1)
  })

  it('异常也算偏差', () => {
    const r = summarizeDeviationNature([sample({ checkResult: '异常' })], {})
    expect(r.total).toBe(1)
  })

  it('系统性偏差缺原因 → 进 missingExplanation', () => {
    const ann: DeviationAnnotationMap = {
      'V-1': { nature: 'systematic', cause: '', impact: '影响应收账款计价' },
    }
    const r = summarizeDeviationNature([sample()], ann)
    expect(r.missingExplanation).toEqual(['V-1'])
    expect(r.hasNonProjectable).toBe(true)
  })

  it('系统性偏差缺影响评估 → 进 missingExplanation', () => {
    const ann: DeviationAnnotationMap = {
      'V-1': { nature: 'systematic', cause: '审批流程未执行', impact: '   ' },
    }
    expect(summarizeDeviationNature([sample()], ann).missingExplanation).toEqual(['V-1'])
  })

  it('人为偏差同样要求说明', () => {
    const ann: DeviationAnnotationMap = { 'V-1': { nature: 'human' } }
    const r = summarizeDeviationNature([sample()], ann)
    expect(r.missingExplanation).toEqual(['V-1'])
    expect(r.hasNonProjectable).toBe(true)
  })

  it('随机性偏差不要求说明且不触发「不宜外推」', () => {
    const ann: DeviationAnnotationMap = { 'V-1': { nature: 'random' } }
    const r = summarizeDeviationNature([sample()], ann)
    expect(r.missingExplanation).toEqual([])
    expect(r.hasNonProjectable).toBe(false)
  })

  it('系统性偏差齐备说明 → 不阻断但仍标记不宜外推', () => {
    const ann: DeviationAnnotationMap = {
      'V-1': { nature: 'systematic', cause: '审批流程未执行', impact: '扩大至全年' },
    }
    const r = summarizeDeviationNature([sample()], ann)
    expect(r.missingExplanation).toEqual([])
    expect(r.hasNonProjectable).toBe(true)
  })

  it('非法性质值按未标注处理（不猜）', () => {
    const ann = { 'V-1': { nature: 'bogus' } } as unknown as DeviationAnnotationMap
    expect(summarizeDeviationNature([sample()], ann).unannotated).toEqual(['V-1'])
  })

  it('提示语含准则处置方向', () => {
    expect(NO_SIMPLE_PROJECTION_HINT).toContain('不宜简单外推')
    expect(NO_SIMPLE_PROJECTION_HINT).toContain('扩大')
  })
})

// ─── 摘要与载荷 ──────────────────────────────────────────────────────────────

describe('偏差性质摘要', () => {
  it('按性质分组累计笔数与金额（金额取借贷绝对值较大者）', () => {
    const samples = [
      sample({ voucherNo: 'V-1', debitAmount: '1000.00', creditAmount: null }),
      sample({ voucherNo: 'V-2', debitAmount: null, creditAmount: '2500.50' }),
      sample({ voucherNo: 'V-3', debitAmount: '300.00', creditAmount: null }),
    ]
    const ann: DeviationAnnotationMap = {
      'V-1': { nature: 'systematic', cause: 'a', impact: 'b' },
      'V-2': { nature: 'systematic', cause: 'a', impact: 'b' },
      'V-3': { nature: 'random' },
    }
    const r = summarizeDeviationNature(samples, ann)
    expect(r.summary.systematic).toEqual({ count: 2, amount: '3500.50' })
    expect(r.summary.random).toEqual({ count: 1, amount: '300.00' })
  })

  it('未出现的性质不补零（「无系统性偏差」与「未评价」必须可区分）', () => {
    const r = summarizeDeviationNature([sample()], {
      'V-1': { nature: 'random' },
    })
    expect(Object.keys(r.summary)).toEqual(['random'])
    expect(r.summary.systematic).toBeUndefined()
  })

  it('载荷全空时返回 null（与后端「缺省即 None」对齐）', () => {
    expect(buildDeviationNatureSummaryPayload([sample({ checkResult: 'Y' })], {})).toBeNull()
    expect(buildDeviationNatureSummaryPayload([sample()], {})).toBeNull()
  })

  it('载荷非空时结构与摘要一致', () => {
    const ann: DeviationAnnotationMap = { 'V-1': { nature: 'random' } }
    expect(buildDeviationNatureSummaryPayload([sample()], ann)).toEqual({
      random: { count: 1, amount: '1000.00' },
    })
  })

  it('isDeviation 只认 N / 异常', () => {
    expect(isDeviation(sample({ checkResult: 'N' }))).toBe(true)
    expect(isDeviation(sample({ checkResult: '异常' }))).toBe(true)
    expect(isDeviation(sample({ checkResult: 'Y' }))).toBe(false)
    expect(isDeviation(sample({ checkResult: '' }))).toBe(false)
  })
})

// ─── 后端取值域交叉锁死 ──────────────────────────────────────────────────────

describe('前后端取值域交叉锁死', () => {
  it('后端 _EVAL_DEVIATION_NATURES 与前端 key 集合逐字相等', () => {
    const src = fs.readFileSync(
      path.join(repoRoot(), 'backend/app/routers/voucher_sampling.py'),
      'utf-8',
    )
    const m = src.match(/_EVAL_DEVIATION_NATURES\s*=\s*\(([^)]*)\)/)
    expect(m, '后端未找到 _EVAL_DEVIATION_NATURES（常量被改名会让本守卫空转）').toBeTruthy()
    const backend = [...m![1].matchAll(/"([a-z_]+)"/g)].map(x => x[1])
    expect(backend.sort()).toEqual([...DEVIATION_NATURES].sort())
  })

  it('后端投影标签与前端 C 类标签一致', () => {
    const src = fs.readFileSync(
      path.join(repoRoot(), 'backend/app/services/sampling_registry_service.py'),
      'utf-8',
    )
    const labels = deviationNatureLabels()
    for (const [key, label] of Object.entries(labels)) {
      expect(src, `后端 _DEVIATION_NATURE_LABELS 缺 ${key} → ${label}`).toContain(
        `"${key}": "${label}"`,
      )
    }
  })
})
