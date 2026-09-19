/**
 * g8CrossHelpers — G8-4/G8-5 层次勾稽与导航
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  reconcileG8FvWithDesignation,
  jumpToG8Sheet,
  dispatchG8AdjHighlight,
  dispatchProcedureFocus,
  G8_NAV_HIGHLIGHT_ADJ_EVENT,
  PROCEDURE_FOCUS_PROGRAM_EVENT,
  G8A_FV_PROGRAM_NOS,
  G8A_DESIGNATION_PROGRAM_NOS,
  G8A_VOUCHER_PROGRAM_NOS,
  buildG8VoucherProcedureSummary,
  selectG8FvDiffTargets,
} from '../g8CrossHelpers'

describe('reconcileG8FvWithDesignation', () => {
  it('层次不一致', () => {
    const r = reconcileG8FvWithDesignation(
      [{ investeeName: '甲', fairValueLevel: 'Level1' }],
      [{ investeeName: '甲', fairValueLevel: 'Level2', fvReliable: 'yes' }],
    )
    expect(r.mismatches).toHaveLength(1)
    expect(r.mismatches[0].issue).toContain('Level1')
  })

  it('Level3 + FV可靠但未标注 Level3', () => {
    const r = reconcileG8FvWithDesignation(
      [{ investeeName: '甲', fairValueLevel: 'Level3' }],
      [{ investeeName: '甲', fairValueLevel: '', fvReliable: 'yes' }],
    )
    expect(r.mismatches.some((m) => m.issue.includes('未标注 Level3'))).toBe(true)
  })

  it('双向缺失名单', () => {
    const r = reconcileG8FvWithDesignation(
      [{ investeeName: '甲', fairValueLevel: 'Level2' }],
      [{ investeeName: '乙', fairValueLevel: 'Level2' }],
    )
    expect(r.missingInDesignation).toContain('甲')
    expect(r.missingInFv).toContain('乙')
  })
})

describe('G8 导航辅助', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('jumpToG8Sheet 无 jumpFn 返回 false', () => {
    expect(jumpToG8Sheet('G8-3', null)).toBe(false)
  })

  it('jumpToG8Sheet 调用 jumpFn 并传显示名', () => {
    const jump = vi.fn()
    expect(jumpToG8Sheet('G8A', jump)).toBe(true)
    expect(jump).toHaveBeenCalledTimes(1)
    expect(String(jump.mock.calls[0][0])).toContain('G8A')
  })

  it('dispatchG8AdjHighlight 派发高亮事件', () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    dispatchG8AdjHighlight({ investeeNames: ['甲'], source: 'G8-4' })
    expect(spy).toHaveBeenCalled()
    const evt = spy.mock.calls.find((c) => (c[0] as Event).type === G8_NAV_HIGHLIGHT_ADJ_EVENT)?.[0] as CustomEvent
    expect(evt).toBeTruthy()
    expect(evt.detail.investeeNames).toEqual(['甲'])
    expect(evt.detail.source).toBe('G8-4')
  })

  it('dispatchProcedureFocus 派发程序定位事件', () => {
    const spy = vi.spyOn(window, 'dispatchEvent')
    dispatchProcedureFocus({ programNos: [...G8A_FV_PROGRAM_NOS], sheetCode: 'G8A' })
    const evt = spy.mock.calls.find((c) => (c[0] as Event).type === PROCEDURE_FOCUS_PROGRAM_EVENT)?.[0] as CustomEvent
    expect(evt).toBeTruthy()
    expect(evt.detail.programNos).toEqual([3, 10])
    expect(evt.detail.sheetCode).toBe('G8A')
  })

  it('G8A 程序序号约定', () => {
    expect(G8A_FV_PROGRAM_NOS).toEqual([3, 10])
    expect(G8A_DESIGNATION_PROGRAM_NOS).toEqual([2])
    expect(G8A_VOUCHER_PROGRAM_NOS).toEqual([6, 7, 12])
  })

  it('buildG8VoucherProcedureSummary 含完成度与金额异常', () => {
    const s = buildG8VoucherProcedureSummary({
      rowCount: 10,
      untested: 2,
      abnormal: 3,
      quantitative: 1,
      completionPct: 80,
      samplingMethod: '随机',
    })
    expect(s).toContain('10 笔')
    expect(s).toContain('完成度 80%')
    expect(s).toContain('金额类 1')
    expect(s).toContain('随机')
  })

  it('selectG8FvDiffTargets onlyMaterial=false 推送全部非零差异', () => {
    const { targets, skipped, threshold } = selectG8FvDiffTargets({
      rows: [
        { investeeName: 'A', fairValueDiff: 50, closingAuditedFV: 1050, closingUnadjustedFV: 1000 },
        { investeeName: 'B', fairValueDiff: 0, closingAuditedFV: 1000, closingUnadjustedFV: 1000 },
      ],
      performanceMateriality: 100,
      onlyMaterial: false,
    })
    expect(threshold).toBe(0.01)
    expect(targets.map((t) => t.investeeName)).toEqual(['A'])
    expect(skipped).toHaveLength(0)
  })
})
