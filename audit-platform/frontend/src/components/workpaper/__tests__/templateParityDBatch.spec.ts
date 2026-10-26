/**
 * D 循环前端按权威模板对齐（第二批，spec oo-writeback-template-parity-closure R2.2 / design §3.1）。
 *
 * 每条都同时断言「与模板同式」和「旧口径算出的值不同」：改回旧口径必须打红（变异自检）。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { calculateDifference as d1EclDiff } from '../composables/useD1EclCalc'
import { calculateDifference as d1LegacyDiff } from '../composables/useD1NotesReceivable'
import { calculateDifference as d2Diff } from '../composables/useD2FormulaEngine'
import { calcDifference as d1EngineDiff, normalizeMemoStatus } from '../composables/useD1FormulaEngine'
import { recalcImpairmentRow, type ImpairmentDetailRow } from '../composables/useD6ImpairmentDetail'
import {
  deriveMemoRow,
  emptyMemoRow,
  useD1MemoReconciliation,
  type MemoRow,
} from '../composables/useD1MemoReconciliation'
import type { ChecklistResponse } from '../composables/useD1FormData'

describe('D1-15 / D2-9 差异 = 应计提 − 期末坏账准备账面余额（模板表头 ⑤=③-④）', () => {
  const impls = [
    ['useD1EclCalc', d1EclDiff],
    ['useD1NotesReceivable', d1LegacyDiff],
    ['useD2FormulaEngine', d2Diff],
    ['useD1FormulaEngine', d1EngineDiff],
  ] as const

  it.each(impls)('%s：少提为正、多提为负（参数顺序仍是 实际, 应计）', (_name, diff) => {
    expect(diff(3000, 5000)).toBe(2000)
    expect(diff(6000, 5000)).toBe(-1000)
    // 旧口径「实际 − 应计」会得 -2000 / 1000
    expect(diff(3000, 5000)).not.toBe(3000 - 5000)
  })
})

describe('D6-3 期末未审从期初未审起算（模板 K = B + SUM(F:G) − SUM(H:J)）', () => {
  const base: ImpairmentDetailRow = {
    rowId: 'r1', itemName: '单项', category: 'single',
    priorUnadjusted: 100, priorAje: 20, priorRje: -5, priorAudited: 0,
    provision: 30, otherIncrease: 4, reversal: 6, writeOff: 2, otherDecrease: 1,
    endUnadjusted: 0, endAje: 7, endRje: 3, endAudited: 0,
  }

  it('期初账项 / 重分类调整不带入期末未审；期末审定 = 期末未审 + 账项 + 重分类', () => {
    const row = recalcImpairmentRow(base)
    expect(row.priorAudited).toBe(115)
    expect(row.endUnadjusted).toBe(100 + 30 + 4 - 6 - 2 - 1)
    // 旧口径以期初审定起算会得 140
    expect(row.endUnadjusted).not.toBe(115 + 30 + 4 - 6 - 2 - 1)
    expect(row.endAudited).toBe(row.endUnadjusted + 7 + 3)
  })
})

// ─── D1-7 备查簿：权威模板「审计核对」区 Q~W 是行公式，表单同式只读 ───────────────

const CUTOFF = '2025-12-31'
const memo = (patch: Partial<MemoRow>): MemoRow => ({ ...emptyMemoRow('bank'), ...patch })

describe('D1-7 Q~W 按模板行公式计算', () => {
  it('Q / R：收到日期在截止日期上一年计入年初余额，其余计入本期收到', () => {
    const prior = deriveMemoRow(memo({ amount: 1000, receivedDate: '2024-11-05', status: '未到期' }), CUTOFF)
    expect([prior.beginningBalance, prior.currentReceived]).toEqual([1000, 0])
    const current = deriveMemoRow(memo({ amount: 1000, receivedDate: '2025-03-01', status: '未到期' }), CUTOFF)
    expect([current.beginningBalance, current.currentReceived]).toEqual([0, 1000])
    // 空白收到日期 = Excel 的 0（1900 年），不等于上一年 ⇒ 全进本期收到
    const blank = deriveMemoRow(memo({ amount: 1000, receivedDate: '' }), CUTOFF)
    expect([blank.beginningBalance, blank.currentReceived]).toEqual([0, 1000])
  })

  it('S / T / U 按模板状态值取票据金额，V = Q + R − S − T − U', () => {
    const cases = [['背书', 'currentEndorsed'], ['到期承兑', 'currentMatured'], ['贴现', 'currentDiscounted']] as const
    for (const [status, field] of cases) {
      const row = deriveMemoRow(memo({ amount: 800, receivedDate: '2025-02-01', status }), CUTOFF)
      expect(row[field]).toBe(800)
      expect(row.endingBalance).toBe(0)
    }
    expect(deriveMemoRow(memo({ amount: 800, receivedDate: '2025-02-01', status: '未到期' }), CUTOFF).endingBalance)
      .toBe(800)
    // 表单旧值「已背书」与模板的「背书」不等：不归一就进不了 S（OnlyOffice 一侧恒 0）
    expect(deriveMemoRow(memo({ amount: 800, status: '已背书' }), CUTOFF).currentEndorsed).toBe(0)
    expect(['已背书', '已贴现', '到期', '持有'].map(normalizeMemoStatus)).toEqual(['背书', '贴现', '到期承兑', '未到期'])
  })

  it('W：到期日不早于截止日期、且流转日期早于到期日 → S + U', () => {
    const base = { amount: 500, receivedDate: '2025-05-01', status: '贴现', maturityDate: '2026-03-31' }
    const w = (patch: Partial<MemoRow>) => deriveMemoRow(memo({ ...base, ...patch }), CUTOFF).unexpiredEndorsedDiscounted
    expect(w({ transferDate: '2025-10-08' })).toBe(500)
    // 到期日 = 截止日期：模板 I<$B$10 不成立 ⇒ 计入（旧实现取 0）
    expect(w({ maturityDate: CUTOFF, transferDate: '2025-10-08' })).toBe(500)
    expect(w({ maturityDate: '2025-12-30', transferDate: '2025-10-08' })).toBe(0)
    expect(w({ transferDate: '2026-03-31' })).toBe(0)
    expect(w({ status: '到期承兑', transferDate: '2025-10-08' })).toBe(0)
  })
})

function memoResponses(bankRows: Partial<MemoRow>[], commercialRows: Partial<MemoRow>[]) {
  const map = new Map<string, ChecklistResponse>()
  const put = (key: string, remark: string) => map.set(key, { item_id: key, conclusion: null, remark } as ChecklistResponse)
  put('D1-memo-rows', JSON.stringify({ bankRows, commercialRows }))
  put('D1-memo-cutoff-date', CUTOFF)
  return ref(map)
}

function mountMemo(bankRows: Partial<MemoRow>[], commercialRows: Partial<MemoRow>[]) {
  let api!: ReturnType<typeof useD1MemoReconciliation>
  mount(defineComponent({
    setup() {
      api = useD1MemoReconciliation({
        allResponses: memoResponses(bankRows, commercialRows),
        wpId: ref('wp-1'),
        projectId: ref('proj-1'),
        saveImmediate: vi.fn(async () => {}),
        isReadonly: ref(false),
      })
      return () => null
    },
  }))
  return api
}

describe('D1-7 核对区与「贴现、票据已背书未到期明细」按模板汇总', () => {
  const flow = { receivedDate: '2025-02-01', maturityDate: '2026-02-01', transferDate: '2025-08-01' }
  const build = () => mountMemo(
    [
      { rowId: 'b1', noteType: '银行承兑汇票', amount: 300, status: '背书', isDerecognized: '是', ...flow },
      { rowId: 'b2', noteType: '银行承兑汇票', amount: 200, status: '已贴现', isDerecognized: '否', ...flow },
      { rowId: 'b3', noteType: '银行承兑汇票', amount: 50, status: '背书', isDerecognized: '', ...flow },
    ],
    [
      { rowId: 'c1', noteType: '商业承兑汇票', amount: 70, status: '背书', isDerecognized: '否', ...flow },
      { rowId: 'c2', noteType: '商业承兑汇票', amount: 90, status: '到期承兑', receivedDate: '2024-06-01' },
    ],
  )

  it('备查簿：期初 = 年初余额合计，本期减少 = 背书 + 到期承兑 + 贴现（模板 B29:E29）', () => {
    const [memoTotal] = build().reconciliationRows.value
    expect(memoTotal).toEqual({
      label: '备查簿合计', beginningBalance: 90, currentIncrease: 620, currentDecrease: 710, endingBalance: 0,
    })
  })

  it('明细表按 W 与是否终止确认（是 / 否）分列，勾稽 = W 合计 − 两列合计（模板 G29:I34）', () => {
    const api = build()
    expect(api.unexpiredSummaryRows.value.map((r) => [r.derecognized, r.notDerecognized]))
      .toEqual([[300, 0], [0, 70], [0, 200], [0, 0]])
    expect(api.unexpiredSummaryTotal.value).toMatchObject({ derecognized: 300, notDerecognized: 270 })
    expect(api.unexpiredCheckDiff.value).toBe(50) // b3 未判断是否终止确认
    expect(api.endorsedStats.value).toEqual({ discountedTotal: 200, endorsedTotal: 420 })
  })

  it('公式列不接受手填；改状态后按新状态重算', () => {
    const api = build()
    api.updateCell('b1', 'currentEndorsed', 999)
    expect(api.bankRows.value[0].currentEndorsed).toBe(300)
    api.updateCell('b1', 'status', '已贴现')
    expect(api.bankRows.value[0]).toMatchObject({ status: '贴现', currentEndorsed: 0, currentDiscounted: 300 })
  })
})

describe('D3-1 审定表变动率按模板 IF(AND(E=0,I=0),"",IF(AND(E=0,I>0),1,J/E))', () => {
  it('期初为 0、期末为正 → 100%（原与分析表共用 calcChangeRate 得 N/A）', async () => {
    const { calcAdjudicationChangeRate, calcChangeRate } = await import('../composables/useD3FormulaEngine')
    expect(calcAdjudicationChangeRate(0, 500)).toBe(1)
    expect(calcChangeRate(0, 500)).toBe('N/A') // 分析表 D3-4 是 =D/C 直接相除，不变
    expect(calcAdjudicationChangeRate(0, 0)).toBe('')
    expect(calcAdjudicationChangeRate(0, -500)).toBe('N/A') // 模板 J/E 除零
    expect(calcAdjudicationChangeRate(400, 500)).toBeCloseTo(0.25)
  })
})
