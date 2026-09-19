/**
 * H 循环勾稽引擎守卫（Property 11 / 12 + 逐循环规则）
 *
 * spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R5
 */
import { describe, expect, it } from 'vitest'
import fc from 'fast-check'

import { eqCheck, summarizeChecks, WP_CHECK_TOLERANCE } from '../shared/disclosureConsistency'
import { buildH2ListedChecks, buildH2SoeChecks } from '../h2DisclosureConsistency'
import { buildH5Checks } from '../h5DisclosureConsistency'
import { buildH8SoeChecks } from '../h8DisclosureConsistency'
import { buildH9SoeChecks } from '../h9DisclosureConsistency'
import { buildH10RowChecks } from '../h10DisclosureConsistency'
import { createDefaultListedSummary, type ListedDetailRow } from '../h2ListedDisclosureModel'
import { H8_SOE_LAYER_META, type H8SoeLayerBlock } from '../h8SoeDisclosureModel'
import type { H9SoeDisclosureState } from '../h9DisclosureModel'
import type { H10DisclosureRow } from '../useH10Disclosure'

describe('平台共用勾稽原语 Property 11/12', () => {
  it('Property 11: 任一侧 null → skip，diff 为 null', () => {
    const r1 = eqCheck('x', 'y', null, 5)
    const r2 = eqCheck('x', 'y', 5, null)
    const r3 = eqCheck('x', 'y', null, null)
    for (const r of [r1, r2, r3]) {
      expect(r.level).toBe('skip')
      expect(r.diff).toBeNull()
    }
  })

  it('Property 12: |diff| <= 容差 → ok，否则 error（PBT）', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e6, max: 1e6, noNaN: true }),
        fc.float({ min: -1e6, max: 1e6, noNaN: true }),
        (a, b) => {
          const r = eqCheck('x', 'y', a, b)
          const diff = Math.round((a - b) * 100) / 100
          if (Math.abs(diff) <= WP_CHECK_TOLERANCE) expect(r.level).toBe('ok')
          else expect(r.level).toBe('error')
        },
      ),
      { numRuns: 50 },
    )
  })

  it('summarizeChecks 统计正确', () => {
    const results = [
      eqCheck('a', 'r', 1, 1),
      eqCheck('b', 'r', 1, 2),
      eqCheck('c', 'r', null, 1),
    ]
    const s = summarizeChecks(results)
    expect(s).toEqual({ total: 3, ok: 1, error: 1, skip: 1, allPassed: false })
  })
})

describe('H2 在建工程勾稽', () => {
  it('上市：汇总表期末 = 明细表账面净值合计 → ok', () => {
    const summary = createDefaultListedSummary().map((r) =>
      r.key === 'cip' ? { ...r, endBalance: 100, priorBalance: 50 } : r,
    )
    const detailRows: ListedDetailRow[] = [
      {
        rowId: 'd1',
        name: '项目A',
        endBook: 120,
        endImpairment: 20,
        priorBook: 60,
        priorImpairment: 10,
      } as ListedDetailRow,
    ]
    const checks = buildH2ListedChecks({
      summary,
      detailRows,
      projectRows: [],
      impairmentRows: [],
    })
    const main = checks.find((c) => c.label.includes('汇总表「在建工程」'))
    expect(main).toBeTruthy()
    expect(main!.level).toBe('ok')
  })

  it('上市：项目表期末超出明细表 → error（子集越界）', () => {
    const detailRows: ListedDetailRow[] = [
      { rowId: 'd1', name: 'A', endBook: 100, endImpairment: 0, priorBook: 0, priorImpairment: 0 } as ListedDetailRow,
    ]
    const projectRows = [
      { rowId: 'p1', name: 'A', beginBalance: 200 } as any,
    ]
    const checks = buildH2ListedChecks({
      summary: createDefaultListedSummary(),
      detailRows,
      projectRows,
      impairmentRows: [],
    })
    const sub = checks.find((c) => c.label.includes('重要项目表期末余额合计'))
    expect(sub).toBeTruthy()
    expect(sub!.level).toBe('error')
  })

  it('国企：无数据返回空数组（不误报）', () => {
    expect(buildH2SoeChecks({ detailRows: [], projectRows: [], impairmentRows: [] })).toEqual([])
  })
})

describe('H5 油气资产层间派生', () => {
  it('原值−折耗−减值=净值 → ok', () => {
    const checks = buildH5Checks({ cost: 1000, depletion: 300, impairment: 100, netValue: 600 })
    expect(checks).toHaveLength(1)
    expect(checks[0].level).toBe('ok')
  })

  it('净值不符公式 → error', () => {
    const checks = buildH5Checks({ cost: 1000, depletion: 300, impairment: 100, netValue: 999 })
    expect(checks[0].level).toBe('error')
  })

  it('全部为 null → 空数组（不刷屏）', () => {
    expect(buildH5Checks({ cost: null, depletion: null, impairment: null, netValue: null })).toEqual([])
  })
})

describe('H8 使用权资产五层派生（国企）', () => {
  function block(layer: keyof typeof H8_SOE_LAYER_META, begin: number, increase: number, decrease: number, end: number): H8SoeLayerBlock {
    return {
      layer,
      categories: [{ key: 'other', begin, increase, decrease, end } as any],
    } as H8SoeLayerBlock
  }

  it('净值=原值−折旧 且 价值=净值−减值 → 全部 ok', () => {
    const layers: H8SoeLayerBlock[] = [
      block('cost', 100, 50, 20, 130),
      block('dep', 20, 10, 5, 25),
      block('net', 0, 0, 0, 105),
      block('impair', 5, 2, 0, 7),
      block('carrying', 0, 0, 0, 98),
    ]
    const checks = buildH8SoeChecks(layers)
    expect(checks.length).toBeGreaterThan(0)
    expect(checks.every((c) => c.level === 'ok')).toBe(true)
  })

  it('净值公式不符 → error', () => {
    const layers: H8SoeLayerBlock[] = [
      block('cost', 100, 0, 0, 100),
      block('dep', 20, 0, 0, 20),
      block('net', 0, 0, 0, 999),
      block('impair', 0, 0, 0, 0),
      block('carrying', 0, 0, 0, 999),
    ]
    const checks = buildH8SoeChecks(layers)
    const netCheck = checks.find((c) => c.label.includes('账面净值'))
    expect(netCheck?.level).toBe('error')
  })

  it('缺层时返回空数组', () => {
    expect(buildH8SoeChecks([])).toEqual([])
  })
})

describe('H9 租赁负债净额子集（国企）', () => {
  function state(payment: number, unearned: number, reclass: number): H9SoeDisclosureState {
    return {
      rows: [
        { key: 'payment', item: '租赁付款额', endBalance: payment, beginBalance: null },
        { key: 'unearned', item: '未确认融资费用', endBalance: unearned, beginBalance: null },
        { key: 'reclass', item: '重分类至一年内到期', endBalance: reclass, beginBalance: null },
      ],
      supplementNote: '',
      auditNote: '',
      auditConclusion: '',
    }
  }

  it('重分类未超净额 → ok', () => {
    const checks = buildH9SoeChecks(state(1000, 100, 500))
    expect(checks[0].level).toBe('ok')
  })

  it('重分类超出净额 → error', () => {
    const checks = buildH9SoeChecks(state(1000, 100, 950))
    expect(checks[0].level).toBe('error')
  })

  it('缺数据时返回空数组', () => {
    expect(buildH9SoeChecks(state(null as any, null as any, null as any))).toEqual([])
  })
})

describe('H10 资产处置损益逐行公式', () => {
  function row(current: number, prior: number, change: number): H10DisclosureRow {
    return {
      rowKey: 'r1',
      label: '处置固定资产',
      currentAmount: current,
      priorAmount: prior,
      changeAmount: change,
      changeRate: null,
      remark: '',
    }
  }

  it('变动金额符合公式 → ok', () => {
    const checks = buildH10RowChecks([row(150, 100, 50)])
    expect(checks[0].level).toBe('ok')
  })

  it('变动金额不符公式 → error', () => {
    const checks = buildH10RowChecks([row(150, 100, 999)])
    expect(checks[0].level).toBe('error')
  })

  it('跳过内部标记行（__ 前缀）', () => {
    const checks = buildH10RowChecks([{ ...row(1, 1, 0), rowKey: '__total__' }])
    expect(checks).toEqual([])
  })
})
