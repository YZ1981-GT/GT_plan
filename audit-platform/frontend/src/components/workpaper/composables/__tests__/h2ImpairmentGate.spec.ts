/**
 * H2 减值门禁单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  countImpairmentSignYes,
  needsH216RecoverableTest,
  isH216RecoverableComplete,
  isImpairmentGateBlocked,
  isCleanImpairmentConclusion,
  buildBlockedImpairmentConclusion,
  H215_SIGNS_KEY,
  H215_CALC_KEY,
  H216_GROUPS_KEY,
  H216_CONCLUSION_KEY,
} from '../h2ImpairmentGate'
import { resolveH2SheetStatus } from '../h2IndexCompletion'

function makeMap(entries: Record<string, unknown> = {}) {
  const m = new Map<string, any>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, {
      item_id: k,
      conclusion: null,
      remark: typeof v === 'string' ? v : JSON.stringify(v),
    })
  }
  return m
}

describe('h2ImpairmentGate', () => {
  it('迹象计数与 needsH216', () => {
    const map = makeMap({
      [H215_SIGNS_KEY]: [
        { exists: '是' },
        { exists: '是' },
        { exists: '否' },
      ],
    })
    expect(countImpairmentSignYes(map)).toBe(2)
    expect(needsH216RecoverableTest(map)).toBe(true)
    expect(isImpairmentGateBlocked(map)).toBe(true)
  })

  it('H2-16 结论解除门禁', () => {
    const map = makeMap({
      [H215_SIGNS_KEY]: [{ exists: '是' }, { exists: '是' }],
      [H216_CONCLUSION_KEY]: '可收回金额测算完成',
    })
    expect(isH216RecoverableComplete(map)).toBe(true)
    expect(isImpairmentGateBlocked(map)).toBe(false)
  })

  it('H2-16 工程组测算解除门禁', () => {
    const map = makeMap({
      [H215_SIGNS_KEY]: [{ exists: '是' }, { exists: '是' }],
      [H216_GROUPS_KEY]: [{ name: 'A', fairValueNet: 100, pvCashFlows: 80, recoverableAmount: 100 }],
    })
    expect(isH216RecoverableComplete(map)).toBe(true)
  })

  it('H2-15 回写行可解除门禁', () => {
    const map = makeMap({
      [H215_SIGNS_KEY]: [{ exists: '是' }, { exists: '是' }],
      [H215_CALC_KEY]: [
        { hasSign: '是', fairValueNet: 10, pvCashFlows: 0, recoverableAmount: 10 },
        { hasSign: '是', fairValueNet: 0, pvCashFlows: 20, recoverableAmount: 20 },
      ],
    })
    expect(isH216RecoverableComplete(map)).toBe(true)
    expect(isImpairmentGateBlocked(map)).toBe(false)
  })

  it('清洁结论识别与受限草稿', () => {
    expect(isCleanImpairmentConclusion('未见异常，减值准备计提充分。')).toBe(true)
    expect(isCleanImpairmentConclusion('须完成 H2-16，范围受限，不可确认。')).toBe(false)
    expect(buildBlockedImpairmentConclusion(3)).toContain('3 项')
    expect(buildBlockedImpairmentConclusion(3)).toContain('H2-16')
  })
})

describe('h2IndexCompletion × impairment gate', () => {
  it('门禁阻断时 H2-15/H2-16 均为 pending', () => {
    const map = makeMap({
      [H215_SIGNS_KEY]: [{ exists: '是' }, { exists: '是' }],
      'H2-15-audit-conclusion': '未见异常',
    })
    expect(resolveH2SheetStatus('H2-15', map).status).toBe('pending')
    expect(resolveH2SheetStatus('H2-16', map).status).toBe('pending')
    expect(resolveH2SheetStatus('H2-16', map).reason).toMatch(/H2-16/)
  })

  it('迹象<2 且无数据时 H2-16 为 N/A', () => {
    const map = makeMap({
      [H215_SIGNS_KEY]: [{ exists: '是' }],
    })
    expect(resolveH2SheetStatus('H2-16', map).status).toBe('na')
  })
})
