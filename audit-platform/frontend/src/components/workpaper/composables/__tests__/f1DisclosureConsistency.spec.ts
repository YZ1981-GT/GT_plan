/**
 * F1 披露勾稽引擎守卫（Property 8 / 9）
 *
 * 规则集完备性以 `backend/data/note_check_preset_formulas.json` 的
 * `note_section='五、7'` 为真源交叉校验 —— 新增/删除校验预设必然打红，
 * 防「引擎规则集与平台校验预设漂移」。
 *
 * spec: .kiro/specs/f1-four-table-extraction-and-disclosure-alignment/ R8
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  F1_AMOUNT_TOLERANCE,
  buildF1ConsistencyChecks,
  summarizeF1Checks,
  type F1ConsistencyInput,
} from '../f1DisclosureConsistency'

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

/**
 * 取该变体「预付款项」章节的校验预设 id 集合。
 *
 * 🔴 必须同时按 `section_title` 过滤：实证 `note_check_preset_formulas.json` 里
 * `note_section='五、7'` 下混入了 `F65-*`（其他收益，应为 五、65）与
 * `F82-*`（筹资活动产生的各项负债的变动，应为 五、82）—— 预设文件的
 * `note_section` 存在陈旧值，属平台级 data-hygiene，本 spec 不修，只在此按标题收敛。
 */
function presetIds(variant: 'listed' | 'soe'): string[] {
  const raw = JSON.parse(
    readFileSync(resolve(REPO_ROOT, 'backend/data/note_check_preset_formulas.json'), 'utf-8'),
  ) as Record<string, Array<{ id?: string; note_section?: string; section_title?: string }>>
  const ids = (raw[variant] ?? [])
    .filter((x) => String(x.note_section ?? '') === '五、7')
    .filter((x) => String(x.section_title ?? '') === '预付款项')
    .map((x) => String(x.id ?? ''))
  return [...new Set(ids)].sort()
}

/** 一个自洽的输入：各段之和 = 小计，合计 = 小计 − 减值准备，比例正确 */
function goodInput(overrides: Partial<F1ConsistencyInput> = {}): F1ConsistencyInput {
  return {
    reportEndAmount: 900,
    reportPriorAmount: null,
    agingRows: [
      { key: 'within1', label: '1年以内', endAmount: 600, endPct: 60, priorAmount: 500, priorPct: 50 },
      { key: 'y1to2', label: '1至2年', endAmount: 300, endPct: 30, priorAmount: 300, priorPct: 30 },
      { key: 'y2to3', label: '2至3年', endAmount: 100, endPct: 10, priorAmount: 200, priorPct: 20 },
    ],
    agingSubtotal: { endAmount: 1000, endPct: 100, priorAmount: 1000, priorPct: 100 },
    agingImpairment: { endAmount: 100, priorAmount: 50 },
    agingNet: { endAmount: 900, priorAmount: 950 },
    overOneYearKeys: ['y1to2', 'y2to3'],
    over1Rows: [
      {
        name: '甲', endBalance: 300,
        creditorUnit: '本公司', agingLabel: '1至2年', reason: '货未到',
      },
    ],
    over1Total: { endBalance: 300 },
    top5Rows: [{ name: '甲', endBalance: 300, proportionPct: 30, impairment: 40 }],
    top5Total: { endBalance: 300, proportionPct: 30, impairment: 40 },
    fourTableImpairmentEnd: 100,
    ...overrides,
  }
}

function byId(results: ReturnType<typeof buildF1ConsistencyChecks>, id: string) {
  const hit = results.find((r) => r.id === id)
  if (!hit) throw new Error(`缺规则 ${id}；实有 ${results.map((r) => r.id).join(',')}`)
  return hit
}

describe('Property 8：规则集完备且与校验预设不漂移', () => {
  it.each(['listed', 'soe'] as const)('%s 覆盖该变体全部 F7-* 预设 id', (variant) => {
    const wanted = presetIds(variant)
    expect(wanted.length, '预设读取失败（反向自检）').toBeGreaterThan(10)
    const results = buildF1ConsistencyChecks(variant, goodInput())
    // 引擎把「期末/期初各独立」的规则拆成 `-end` / `-prior`，故用前缀归一比对
    const covered = new Set(results.map((r) => r.id.replace(/-(end|prior)$/, '')))
    const missing = wanted.filter((id) => !covered.has(id))
    expect(missing, `未覆盖预设：${missing.join(' / ')}`).toHaveLength(0)
  })

  it('国企附加四表库比对规则；上市不含该规则（四表无账龄维度，只在国企逐段列上校验）', () => {
    expect(buildF1ConsistencyChecks('soe', goodInput()).some((r) => r.id === 'F1-TB4')).toBe(true)
    expect(buildF1ConsistencyChecks('listed', goodInput()).some((r) => r.id === 'F1-TB4')).toBe(false)
  })

  it('每条规则都带中文 label / 规则原文 / 追溯 refs', () => {
    for (const variant of ['listed', 'soe'] as const) {
      for (const r of buildF1ConsistencyChecks(variant, goodInput())) {
        expect(r.label.trim(), r.id).not.toBe('')
        expect(r.rule.trim(), r.id).not.toBe('')
        expect(r.refs.length, r.id).toBeGreaterThan(0)
        expect(r.detail.trim(), r.id).not.toBe('')
      }
    }
  })
})

describe('自洽输入下全部通过', () => {
  it('国企：无 error', () => {
    const results = buildF1ConsistencyChecks('soe', goodInput())
    const bad = results.filter((r) => r.level === 'error')
    expect(bad.map((r) => `${r.id}:${r.detail}`), 'unexpected errors').toHaveLength(0)
  })

  it('上市：F7-13 显式跳过（③表无减值准备列）', () => {
    const r = byId(buildF1ConsistencyChecks('listed', goodInput()), 'F7-13')
    expect(r.level).toBe('skipped')
    expect(r.detail).toContain('无「减值准备」列')
  })
})

describe('Property 8：缺数据一律 skipped，不误报 error', () => {
  it('报表数未取到 → F7-1 skipped', () => {
    const r = byId(buildF1ConsistencyChecks('soe', goodInput({ reportEndAmount: 0 })), 'F7-1')
    expect(r.level).toBe('skipped')
    expect(r.detail).toContain('报表数未取到')
  })

  it('四表库无备抵科目 → F1-TB4 skipped', () => {
    const r = byId(
      buildF1ConsistencyChecks('soe', goodInput({ fourTableImpairmentEnd: null })),
      'F1-TB4',
    )
    expect(r.level).toBe('skipped')
    expect(r.detail).toContain('坏账准备-预付账款')
  })

  it('小计为 0 → F7-8 / F7-14 skipped（无比例基数）', () => {
    const input = goodInput({
      agingRows: [],
      agingSubtotal: { endAmount: 0, endPct: 0, priorAmount: 0, priorPct: 0 },
      agingImpairment: { endAmount: 0, priorAmount: 0 },
      agingNet: { endAmount: 0, priorAmount: 0 },
      reportEndAmount: 0,
      top5Rows: [],
      top5Total: { endBalance: 0, proportionPct: 0, impairment: 0 },
      over1Rows: [],
      over1Total: { endBalance: 0 },
      fourTableImpairmentEnd: null,
    })
    const results = buildF1ConsistencyChecks('soe', input)
    expect(byId(results, 'F7-8').level).toBe('skipped')
    expect(byId(results, 'F7-14').level).toBe('skipped')
    expect(results.filter((r) => r.level === 'error')).toHaveLength(0)
  })

  it('上市「汇总披露格式」下 ③ 相关规则 skipped', () => {
    const results = buildF1ConsistencyChecks('listed', goodInput({ top5SummaryOnly: true }))
    for (const id of ['F7-4', 'F7-12', 'F7-14']) {
      expect(byId(results, id).level, id).toBe('skipped')
      expect(byId(results, id).detail, id).toContain('汇总披露格式')
    }
  })
})

describe('异常能被检出', () => {
  it('F7-6：各段之和 ≠ 小计', () => {
    const r = byId(
      buildF1ConsistencyChecks('soe', goodInput({
        agingSubtotal: { endAmount: 1200, endPct: 100, priorAmount: 1000, priorPct: 100 },
      })),
      'F7-6-end',
    )
    expect(r.level).toBe('error')
    expect(r.diff).toBe(-200)
  })

  it('F7-7：合计 ≠ 小计 − 减值准备', () => {
    const r = byId(
      buildF1ConsistencyChecks('soe', goodInput({ agingNet: { endAmount: 950, priorAmount: 950 } })),
      'F7-7-end',
    )
    expect(r.level).toBe('error')
  })

  it('F7-11：②合计超出 ①表 1 年以上各段之和', () => {
    const r = byId(
      buildF1ConsistencyChecks('soe', goodInput({
        over1Rows: [{ name: '甲', endBalance: 900, creditorUnit: '本公司', agingLabel: '1至2年', reason: 'x' }],
        over1Total: { endBalance: 900 },
      })),
      'F7-11',
    )
    expect(r.level).toBe('error')
    expect(r.detail).toContain('超出')
  })

  it('F7-9：国企②表关键列缺失 → warning（非 error）', () => {
    const r = byId(
      buildF1ConsistencyChecks('soe', goodInput({
        over1Rows: [{ name: '甲', endBalance: 300 }],
      })),
      'F7-9',
    )
    expect(r.level).toBe('warning')
    expect(r.detail).toContain('债权单位')
  })

  it('F7-9：上市②表只要求债务人名称', () => {
    const r = byId(
      buildF1ConsistencyChecks('listed', goodInput({
        over1Rows: [{ name: '甲', endBalance: 300 }],
      })),
      'F7-9',
    )
    expect(r.level).toBe('pass')
  })

  it('F7-8：比例算错能定位到具体行与期别', () => {
    const r = byId(
      buildF1ConsistencyChecks('soe', goodInput({
        agingRows: [
          { key: 'within1', label: '1年以内', endAmount: 600, endPct: 99, priorAmount: 500, priorPct: 50 },
          { key: 'y1to2', label: '1至2年', endAmount: 300, endPct: 30, priorAmount: 300, priorPct: 30 },
          { key: 'y2to3', label: '2至3年', endAmount: 100, endPct: 10, priorAmount: 200, priorPct: 20 },
        ],
      })),
      'F7-8',
    )
    expect(r.level).toBe('error')
    expect(r.detail).toContain('1年以内')
  })
})

describe('Property 9：账龄枚举驱动的「1 年以上」段集自适配', () => {
  it('5 年段：超 1 年基数含 3至4/4至5/5年以上', () => {
    const input = goodInput({
      agingRows: [
        { key: 'within1', label: '1年以内', endAmount: 100, endPct: 10, priorAmount: 0, priorPct: 0 },
        { key: 'y1to2', label: '1至2年', endAmount: 200, endPct: 20, priorAmount: 0, priorPct: 0 },
        { key: 'y2to3', label: '2至3年', endAmount: 200, endPct: 20, priorAmount: 0, priorPct: 0 },
        { key: 'y3to4', label: '3至4年', endAmount: 200, endPct: 20, priorAmount: 0, priorPct: 0 },
        { key: 'y4to5', label: '4至5年', endAmount: 200, endPct: 20, priorAmount: 0, priorPct: 0 },
        { key: 'over5', label: '5年以上', endAmount: 100, endPct: 10, priorAmount: 0, priorPct: 0 },
      ],
      agingSubtotal: { endAmount: 1000, endPct: 100, priorAmount: 0, priorPct: 0 },
      agingImpairment: { endAmount: 0, priorAmount: 0 },
      agingNet: { endAmount: 1000, priorAmount: 0 },
      reportEndAmount: 1000,
      overOneYearKeys: ['y1to2', 'y2to3', 'y3to4', 'y4to5', 'over5'],
      over1Rows: [{ name: '甲', endBalance: 900, creditorUnit: 'x', agingLabel: '1至2年', reason: 'y' }],
      over1Total: { endBalance: 900 },
      top5Rows: [{ name: '甲', endBalance: 900, proportionPct: 90, impairment: 0 }],
      top5Total: { endBalance: 900, proportionPct: 90, impairment: 0 },
      fourTableImpairmentEnd: null,
    })
    // 1 年以上合计 = 900 → 恰好等于 ②合计，不应报超出
    expect(byId(buildF1ConsistencyChecks('soe', input), 'F7-11').level).toBe('pass')
  })

  it('自定义段（2~10 段）长度不影响规则数', () => {
    const lens = [2, 5, 10]
    const counts = lens.map((len) => {
      const rows = Array.from({ length: len }, (_, i) => ({
        key: `custom-${i}`,
        label: `自定义${i}`,
        endAmount: 10,
        endPct: Number(((10 / (len * 10)) * 100).toFixed(2)),
        priorAmount: 0,
        priorPct: 0,
      }))
      return buildF1ConsistencyChecks('soe', goodInput({
        agingRows: rows,
        agingSubtotal: { endAmount: len * 10, endPct: 100, priorAmount: 0, priorPct: 0 },
        agingImpairment: { endAmount: 0, priorAmount: 0 },
        agingNet: { endAmount: len * 10, priorAmount: 0 },
        reportEndAmount: len * 10,
        overOneYearKeys: rows.slice(1).map((r) => r.key),
        over1Rows: [],
        over1Total: { endBalance: 0 },
        top5Rows: [],
        top5Total: { endBalance: 0, proportionPct: 0, impairment: 0 },
        fourTableImpairmentEnd: null,
      })).length
    })
    expect(new Set(counts).size, `规则数随段数漂移：${counts.join(',')}`).toBe(1)
  })
})

describe('容差与汇总', () => {
  it('相等类容差 0.01 元', () => {
    expect(F1_AMOUNT_TOLERANCE).toBe(0.01)
    const withinTol = buildF1ConsistencyChecks('soe', goodInput({ agingNet: { endAmount: 900.01, priorAmount: 950 } }))
    expect(byId(withinTol, 'F7-7-end').level).toBe('pass')
    const outOfTol = buildF1ConsistencyChecks('soe', goodInput({ agingNet: { endAmount: 900.05, priorAmount: 950 } }))
    expect(byId(outOfTol, 'F7-7-end').level).toBe('error')
  })

  it('summarizeF1Checks 计数与结果集一致', () => {
    const results = buildF1ConsistencyChecks('soe', goodInput())
    const s = summarizeF1Checks(results)
    expect(s.total).toBe(results.length)
    expect(s.pass + s.warning + s.error + s.skipped).toBe(results.length)
  })
})
