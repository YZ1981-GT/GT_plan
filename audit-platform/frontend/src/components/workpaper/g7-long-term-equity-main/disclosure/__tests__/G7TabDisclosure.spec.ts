/**
 * G7 附注披露联动测试（重构后）。
 *
 * 验证国企模型多目标同步载荷、审定勾稽口径，以及 EventBus 文本更新结构。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  G7_SOE_DISCLOSURE_SECTIONS,
  buildG7SoeSyncPayloads,
  createG7SoeDisclosureState,
} from '../g7SoeDisclosureModel'

const G7_ACCOUNT_CODE = '1511'

describe('G7 SOE disclosure sync routing', () => {
  it('builds one payload per note section id', () => {
    const payloads = buildG7SoeSyncPayloads(createG7SoeDisclosureState())
    const ids = payloads.map(item => item.noteSectionId)
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids.some(id => id.startsWith('七、'))).toBe(true)
    expect(ids).toContain('八、18')
  })

  it('keeps consolidation and long-term equity in separate sync targets', () => {
    const consolidationIds = new Set(
      G7_SOE_DISCLOSURE_SECTIONS
        .filter(section => section.chapter === 'consolidation-scope')
        .map(section => section.noteSectionId),
    )
    const lteIds = new Set(
      G7_SOE_DISCLOSURE_SECTIONS
        .filter(section => section.chapter === 'long-term-equity')
        .map(section => section.noteSectionId),
    )
    for (const id of consolidationIds) expect(lteIds.has(id)).toBe(false)
    expect(lteIds).toEqual(new Set(['八、18']))
  })
})

describe('G7 disclosure EventBus payload shape', () => {
  let dispatchedEvents: CustomEvent[]

  beforeEach(() => {
    dispatchedEvents = []
    vi.spyOn(window, 'dispatchEvent').mockImplementation((event: Event) => {
      if (event instanceof CustomEvent) dispatchedEvents.push(event)
      return true
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('publishes soe multi-payload note update', () => {
    const state = createG7SoeDisclosureState()
    state.texts['group-asset-restrictions'] = '存在资金转移限制。'
    const payloads = buildG7SoeSyncPayloads(state)

    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: {
        accountCode: G7_ACCOUNT_CODE,
        section: 'soe',
        payloads,
        text: '【七、子公司使用企业集 · 重大限制说明】\n存在资金转移限制。',
      },
    }))

    expect(dispatchedEvents).toHaveLength(1)
    expect(dispatchedEvents[0].type).toBe('disclosure:note-text-updated')
    expect(dispatchedEvents[0].detail.accountCode).toBe(G7_ACCOUNT_CODE)
    expect(dispatchedEvents[0].detail.section).toBe('soe')
    expect(dispatchedEvents[0].detail.payloads.length).toBeGreaterThan(5)
    expect(dispatchedEvents[0].detail.text).toContain('资金转移限制')
  })

  it('filters adjudicated events by account code 1511', () => {
    const matched: number[] = []
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail
      if (detail?.accountCode !== G7_ACCOUNT_CODE) return
      matched.push(detail.adjudicatedAmount)
    }

    // 不使用全局 dispatchEvent mock，直接验证过滤逻辑
    vi.mocked(window.dispatchEvent).mockRestore()
    window.addEventListener('substantive:adjudicated', handler)
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: { accountCode: '1122', adjudicatedAmount: 100 },
    }))
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: { accountCode: '1511', adjudicatedAmount: 200 },
    }))
    window.removeEventListener('substantive:adjudicated', handler)

    expect(matched).toEqual([200])
  })
})
