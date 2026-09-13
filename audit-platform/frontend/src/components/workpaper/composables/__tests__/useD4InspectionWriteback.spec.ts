/**
 * useD4InspectionWriteback — 发现→人工确认门→A13 守卫
 *
 * spec: d4-cutoff-return-writeback-formula-io（Task 4/5，Property 3）
 * 铁律：风险发现≠错报；未经人工确认方向/金额/证据不产生 A13 写入；amount<=0 / 证据缺失 /
 *       方向未定 不可确认；幂等（同 sourceId 不重复推送）。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'

// mock eventBus 以捕获 emit
const emitted: Array<{ type: string; payload: any }> = []
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (type: string, payload: any) => { emitted.push({ type, payload }) },
    on: () => {}, off: () => {},
  },
}))

import { useD4InspectionWriteback, type D4Discovery } from '../useD4InspectionWriteback'

function makeWb(wpCode = 'D4-17') {
  return useD4InspectionWriteback({
    wpCode,
    projectId: ref('proj-1'),
    defaultAccountCode: '6001',
    defaultAccountName: '主营业务收入',
  })
}

function draft(over: Partial<D4Discovery> = {}): D4Discovery {
  return {
    sourceId: 'r-1',
    description: '截止跨期（凭证2025-12-28/发货2026-01-05）',
    direction: 'credit',
    amount: 1000,
    evidence: 'D4-17-01',
    accountCode: '6001',
    accountName: '主营业务收入',
    ...over,
  }
}

describe('useD4InspectionWriteback', () => {
  beforeEach(() => { emitted.length = 0 })

  describe('canConfirm — 确认门判据', () => {
    it('齐全（方向+金额>0+证据）可确认', () => {
      const { canConfirm } = makeWb()
      expect(canConfirm(draft())).toBe(true)
    })
    it('金额<=0 不可确认（错报必须有金额）', () => {
      const { canConfirm } = makeWb()
      expect(canConfirm(draft({ amount: 0 }))).toBe(false)
      expect(canConfirm(draft({ amount: -5 }))).toBe(false)
    })
    it('证据缺失不可确认（reason/"否"非空不算证据）', () => {
      const { canConfirm } = makeWb()
      expect(canConfirm(draft({ evidence: '' }))).toBe(false)
      expect(canConfirm(draft({ evidence: '   ' }))).toBe(false)
    })
    it('方向未定不可确认', () => {
      const { canConfirm } = makeWb()
      expect(canConfirm(draft({ direction: null }))).toBe(false)
      expect(canConfirm(draft({ direction: undefined }))).toBe(false)
    })
  })

  describe('pushConfirmed — 只推已确认的候选', () => {
    it('不发送不可确认的候选（风险发现≠错报）', () => {
      const { pushConfirmed } = makeWb()
      const n = pushConfirmed([draft({ amount: 0 }), draft({ sourceId: 'r-2', evidence: '' })])
      expect(n).toBe(0)
      expect(emitted.length).toBe(0)
    })

    it('发送已确认候选并归一为 a13:push-misstatement', () => {
      const { pushConfirmed } = makeWb()
      const n = pushConfirmed([draft()])
      expect(n).toBe(1)
      expect(emitted).toHaveLength(1)
      expect(emitted[0].type).toBe('a13:push-misstatement')
      const p = emitted[0].payload
      expect(p.wpCode).toBe('D4-17')
      expect(p.misstatementType).toBe('factual')
      expect(p.items).toHaveLength(1)
      expect(p.items[0].amount).toBe(1000)
      expect(p.items[0].indexRef).toBe('r-1')          // sourceId 作幂等 identity
      expect(p.items[0].description).toContain('确认方向:贷')
      expect(p.items[0].description).toContain('证据:D4-17-01')
    })

    it('混合：只发可确认的，跳过不可确认的', () => {
      const { pushConfirmed } = makeWb()
      const n = pushConfirmed([
        draft({ sourceId: 'ok-1' }),
        draft({ sourceId: 'bad-1', amount: 0 }),
        draft({ sourceId: 'ok-2' }),
      ])
      expect(n).toBe(2)
      expect(emitted[0].payload.items.map((i: any) => i.indexRef)).toEqual(['ok-1', 'ok-2'])
    })
  })

  describe('幂等 — 同 sourceId 不重复推送', () => {
    it('二次推送同一 sourceId 被跳过', () => {
      const { pushConfirmed, isPushed } = makeWb()
      expect(pushConfirmed([draft({ sourceId: 'dup-1' })])).toBe(1)
      expect(isPushed('dup-1')).toBe(true)
      emitted.length = 0
      expect(pushConfirmed([draft({ sourceId: 'dup-1' })])).toBe(0)
      expect(emitted.length).toBe(0)
    })
  })
})
