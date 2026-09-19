/**
 * j1DisclosureConsistency — 披露内部勾稽引擎测试（正向全平 + 反向必须报出）
 *
 * 每条规则的源模板证据见被测模块头注释。
 *
 * spec: .kiro/specs/j1-disclosure-template-alignment/ Task 3.2
 */
import { describe, expect, it } from 'vitest'
import {
  buildJ1Consistency,
  buildJ1ConsistencyChecks,
  J1_AMOUNT_TOLERANCE,
  type J1ConsistencyInput,
  type J1ConsistencyVariant,
} from '../j1DisclosureConsistency'
import type { J1DisclosureRow } from '@/composables/workpaper/j1/j1DisclosureRowModel'

function row(
  label: string,
  begin: number,
  increase: number,
  decrease: number,
  indent = 0,
  category = 'x',
): J1DisclosureRow {
  return {
    id: `r-${label}-${indent}`,
    label,
    category,
    ...(indent ? { indent } : {}),
    beginBalance: begin,
    increase,
    decrease,
    endBalance: begin + increase - decrease,
  }
}

/**
 * 全平夹具：
 * - 表2：社保 30/3/1 = Σ 其中（10/1/0 + 20/2/1）；合计 = 社保 + 住房公积金 15/1/1 = 45/4/2
 * - 表3：离职后福利 40/4/2 = Σ 其中（25/2/1 + 15/2/1）；合计 = 40/4/2 + 其他长期 8/1/0 = 48/5/2
 * - 表1：短期薪酬 = 表2 合计；离职后福利-设定提存计划 = 表3 合计
 */
function balanced(variant: J1ConsistencyVariant = 'listed'): J1ConsistencyInput {
  return {
    variant,
    summary: [
      row('短期薪酬', 45, 4, 2),
      row('离职后福利-设定提存计划', 48, 5, 2),
      row('辞退福利', 10, 1, 1),
    ],
    shortTerm: [
      row('社会保险费', 30, 3, 1),
      row('其中：1．医疗保险费', 10, 1, 0, 1),
      row('2．工伤保险费', 20, 2, 1, 1),
      row('住房公积金', 15, 1, 1),
    ],
    postEmployment: [
      row('离职后福利', 40, 4, 2),
      row('其中：基本养老保险费', 25, 2, 1, 1),
      row('失业保险费', 15, 2, 1, 1),
      row('其他长期职工福利（不适用的删除）', 8, 1, 0),
    ],
  }
}

function byId(input: J1ConsistencyInput, id: string) {
  const hit = buildJ1ConsistencyChecks(input).find((c) => c.id === id)
  if (!hit) throw new Error(`未生成校验项：${id}`)
  return hit
}

const VARIANTS: J1ConsistencyVariant[] = ['listed', 'soe']

// ─── 正向：全平 ──────────────────────────────────────────────────────────

describe('正向：勾稽全平时无 error', () => {
  it.each(VARIANTS)('%s 变体 allPass', (variant) => {
    const res = buildJ1Consistency(balanced(variant))
    expect(res.errorCount, JSON.stringify(res.checks.filter((c) => c.level === 'error'))).toBe(0)
    expect(res.allPass).toBe(true)
    expect(res.okCount).toBe(res.checks.length)
  })

  it('跨表两组 × 4 列 + 父子 2 组 + 期末公式 = 11 项（未编制 J1-1 时不含审定勾稽）', () => {
    expect(buildJ1ConsistencyChecks(balanced()).map((c) => c.id)).toEqual([
      'cross-short_term-beginBalance',
      'cross-short_term-increase',
      'cross-short_term-decrease',
      'cross-short_term-endBalance',
      'cross-post_employment-beginBalance',
      'cross-post_employment-increase',
      'cross-post_employment-decrease',
      'cross-post_employment-endBalance',
      'parent-short-term',
      'parent-post-employment',
      'end-formula',
    ])
  })

  it('列头随变体取源模板口径（上市「上年年末数/期末数」vs 国企「期初余额/期末余额」）', () => {
    expect(byId(balanced('listed'), 'cross-short_term-beginBalance').label).toContain('上年年末数')
    expect(byId(balanced('soe'), 'cross-short_term-beginBalance').label).toContain('期初余额')
    expect(byId(balanced('listed'), 'parent-short-term').label).toContain('期末数')
    expect(byId(balanced('soe'), 'parent-short-term').label).toContain('期末余额')
  })

  it('每条规则都写明源模板证据（供审计追溯，不是空话）', () => {
    for (const c of buildJ1ConsistencyChecks(balanced())) {
      expect(c.rule.length, `${c.id} 规则说明过短`).toBeGreaterThanOrEqual(15)
    }
    expect(byId(balanced(), 'cross-short_term-beginBalance').rule).toContain('明细表J1-2')
    expect(byId(balanced(), 'parent-short-term').rule).toContain('SUM')
  })
})

// ─── 反向：制造差异必须报出 ──────────────────────────────────────────────

describe('🔴 反向：制造差异必须报出（否则面板是装饰）', () => {
  it('表1「短期薪酬」≠ 表2 合计 → 对应列报 error', () => {
    const input = balanced()
    const rows = [...input.summary]
    rows[0] = row('短期薪酬', 99, 4, 2)
    const check = byId({ ...input, summary: rows }, 'cross-short_term-beginBalance')
    expect(check.level).toBe('error')
    expect(check.diff).toBe(54) // 99 − 45
    expect(check.detail).toContain('相差')
  })

  it('只报出错的那一列，其余列仍 ok（差异可定位到列）', () => {
    const input = balanced()
    const rows = [...input.summary]
    rows[0] = row('短期薪酬', 45, 999, 2)
    const checks = buildJ1ConsistencyChecks({ ...input, summary: rows })
    const failed = checks.filter((c) => c.level === 'error').map((c) => c.id)
    expect(failed).toEqual(['cross-short_term-increase', 'cross-short_term-endBalance'])
  })

  it('表1「离职后福利-设定提存计划」≠ 表3 合计 → 报 error', () => {
    const input = balanced()
    const rows = [...input.summary]
    rows[1] = row('离职后福利-设定提存计划', 48, 5, 999)
    const check = byId({ ...input, summary: rows }, 'cross-post_employment-decrease')
    expect(check.level).toBe('error')
  })

  it('父行 ≠ Σ 其中项 → 报 error（表2）', () => {
    const input = balanced()
    const rows = [...input.shortTerm]
    rows[0] = row('社会保险费', 999, 3, 1)
    const check = byId({ ...input, shortTerm: rows }, 'parent-short-term')
    expect(check.level).toBe('error')
    expect(check.label).toContain('社会保险费')
  })

  it('父行 ≠ Σ 其中项 → 报 error（表3）', () => {
    const input = balanced()
    const rows = [...input.postEmployment]
    rows[0] = row('离职后福利', 40, 4, 999)
    expect(byId({ ...input, postEmployment: rows }, 'parent-post-employment').level).toBe('error')
  })

  it('某行期末 ≠ 期初+增−减 → 报 error 并点名到表与行', () => {
    const input = balanced()
    const rows = [...input.shortTerm]
    rows[3] = { ...row('住房公积金', 15, 1, 1), endBalance: 777 }
    const check = byId({ ...input, shortTerm: rows }, 'end-formula')
    expect(check.level).toBe('error')
    expect(check.label).toContain('住房公积金')
    expect(check.label).toContain('短期薪酬')
  })

  it('汇总表合计 ≠ J1-1 期末审定合计 → 报 error 且带 J1-1 追溯', () => {
    const check = byId({ ...balanced(), adjudicationEndTotal: 999 }, 'vs-adjudication')
    expect(check.level).toBe('error')
    expect(check.refs).toContain('wp:J1-1')
  })
})

// ─── 容差 ────────────────────────────────────────────────────────────────

describe('容差 1 分', () => {
  it('差 0.01 元判 ok（分位舍入误差不报警）', () => {
    const input = balanced()
    const rows = [...input.summary]
    rows[0] = row('短期薪酬', 45.01, 4, 2)
    expect(byId({ ...input, summary: rows }, 'cross-short_term-beginBalance').level).toBe('ok')
    expect(J1_AMOUNT_TOLERANCE).toBe(0.01)
  })

  it('差 0.02 元判 error', () => {
    const input = balanced()
    const rows = [...input.summary]
    rows[0] = row('短期薪酬', 45.02, 4, 2)
    expect(byId({ ...input, summary: rows }, 'cross-short_term-beginBalance').level).toBe('error')
  })
})

// ─── 边界 ────────────────────────────────────────────────────────────────

describe('边界与降级', () => {
  it('J1-1 未编制（合计为 0）时不产出审定勾稽项（避免恒不平的噪声）', () => {
    expect(buildJ1ConsistencyChecks(balanced()).some((c) => c.id === 'vs-adjudication')).toBe(false)
    expect(
      buildJ1ConsistencyChecks({ ...balanced(), adjudicationEndTotal: 0 }).some(
        (c) => c.id === 'vs-adjudication',
      ),
    ).toBe(false)
  })

  it('汇总表缺对应分类行时跳过该组跨表校验（不臆造 0=0 的假通过）', () => {
    const input = { ...balanced(), summary: [row('辞退福利', 10, 1, 1)] }
    const ids = buildJ1ConsistencyChecks(input).map((c) => c.id)
    expect(ids.some((i) => i.startsWith('cross-'))).toBe(false)
  })

  it('明细表无「其中：」子项时跳过父子校验', () => {
    const input = {
      ...balanced(),
      shortTerm: [row('住房公积金', 15, 1, 1)],
      postEmployment: [row('离职后福利', 40, 4, 2)],
    }
    const ids = buildJ1ConsistencyChecks(input).map((c) => c.id)
    expect(ids).not.toContain('parent-short-term')
    expect(ids).not.toContain('parent-post-employment')
  })

  it('三张表全空时不抛错，只剩期末公式一项且通过', () => {
    const res = buildJ1Consistency({
      variant: 'soe',
      summary: [],
      shortTerm: [],
      postEmployment: [],
    })
    expect(res.checks.map((c) => c.id)).toEqual(['end-formula'])
    expect(res.allPass).toBe(true)
  })

  it('合计行不参与逐行期末公式校验（其值由 computed 产出）', () => {
    const input = balanced()
    const rows: J1DisclosureRow[] = [
      ...input.shortTerm,
      { ...row('合 计', 0, 0, 0), isSubtotal: true, endBalance: 12345 },
    ]
    expect(byId({ ...input, shortTerm: rows }, 'end-formula').level).toBe('ok')
  })

  it('非数值金额按 0 处理，不产生 NaN 结论', () => {
    const input = balanced()
    const rows = [...input.summary]
    rows[0] = { ...row('短期薪酬', 45, 4, 2), beginBalance: NaN }
    const check = byId({ ...input, summary: rows }, 'cross-short_term-beginBalance')
    expect(Number.isNaN(check.left)).toBe(false)
    expect(Number.isNaN(check.diff)).toBe(false)
  })
})
