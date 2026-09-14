import { describe, it, expect } from 'vitest'
import {
  deriveA17_5Status,
  deriveConsultationPairing,
  deriveDisagreementClosure,
  parsePresetWpRefs,
} from '../useA17BundleState'

describe('deriveA17_5Status', () => {
  it('returns not_started for empty', () => {
    expect(deriveA17_5Status([])).toBe('not_started')
  })

  it('requires remark when conclusion is 否', () => {
    expect(deriveA17_5Status([
      { item_id: 'a175-1', conclusion: '是' },
      { item_id: 'a175-2', conclusion: '否' },
    ])).toBe('in_progress')

    expect(deriveA17_5Status([
      { item_id: 'a175-1', conclusion: '是' },
      { item_id: 'a175-2', conclusion: '否', remark: '已沟通并处理' },
    ])).toBe('completed')
  })

  it('accepts 不适用 as filled', () => {
    expect(deriveA17_5Status([
      { item_id: 'a175-1', conclusion: '是' },
      { item_id: 'a175-2', conclusion: '不适用' },
    ])).toBe('completed')
  })

  it('ignores header rows', () => {
    expect(deriveA17_5Status([
      { item_id: 'a175-header', conclusion: '是' },
      { item_id: 'a175-1', conclusion: '是' },
    ])).toBe('completed')
  })
})

describe('deriveConsultationPairing', () => {
  it('closes when no consult content', () => {
    expect(deriveConsultationPairing([], []).closed).toBe(true)
  })

  it('matches consultation_id pairs', () => {
    const open = deriveConsultationPairing(
      [
        { item_id: 'a173-meta-consultation_id', conclusion: 'C-001' },
        { item_id: 'a173-sec1-overview', remark: '事项A' },
      ],
      [{ item_id: 'a1731-meta-consultation_id', conclusion: 'C-002' }],
    )
    expect(open.closed).toBe(false)

    const closed = deriveConsultationPairing(
      [
        { item_id: 'a173-meta-consultation_id', conclusion: 'C-001' },
        { item_id: 'a173-sec1-overview', remark: '事项A' },
      ],
      [
        { item_id: 'a1731-meta-consultation_id', conclusion: 'C-001' },
        { item_id: 'a1731-sec2-execution_details', remark: '已执行' },
      ],
    )
    expect(closed.closed).toBe(true)
  })

  it('supports a173-matter-* multi slots', () => {
    const r = deriveConsultationPairing(
      [
        { item_id: 'a173-matter-m1-overview', remark: '一' },
        { item_id: 'a173-matter-m2-overview', remark: '二' },
      ],
      [{ item_id: 'a1731-matter-m1-exec', remark: 'done' }],
    )
    expect(r.hasConsult).toBe(true)
    expect(r.closed).toBe(false)
    expect(r.warning).toContain('m2')
  })

  it('treats not_applicable as closed with no consult', () => {
    const r = deriveConsultationPairing(
      [
        { item_id: 'a173-meta-not_applicable', conclusion: '是' },
        { item_id: 'a173-sec1-overview', remark: '残留内容也应被 NA 覆盖' },
      ],
      [],
    )
    expect(r.hasConsult).toBe(false)
    expect(r.closed).toBe(true)
  })
})

describe('deriveDisagreementClosure', () => {
  it('closes when empty', () => {
    expect(deriveDisagreementClosure([]).closed).toBe(true)
  })

  it('opens when content without sec6 conclusion', () => {
    const r = deriveDisagreementClosure([
      { item_id: 'a174-sec1-parties', remark: '分歧描述' },
    ])
    expect(r.hasDisagreement).toBe(true)
    expect(r.closed).toBe(false)
  })

  it('closes when sec6 conclusion present', () => {
    const r = deriveDisagreementClosure([
      { item_id: 'a174-sec1-parties', remark: '双方' },
      { item_id: 'a174-sec6-conclusion', remark: '已解决' },
    ])
    expect(r.closed).toBe(true)
  })

  it('treats not_applicable as closed', () => {
    const r = deriveDisagreementClosure([
      { item_id: 'a174-meta-not_applicable', conclusion: '是' },
      { item_id: 'a174-sec1-parties', remark: '残留' },
    ])
    expect(r.hasDisagreement).toBe(false)
    expect(r.closed).toBe(true)
  })
})

describe('parsePresetWpRefs', () => {
  it('extracts codes from mixed text', () => {
    expect(parsePresetWpRefs('B60')).toEqual(['B60'])
    expect(parsePresetWpRefs('A1-13、A1-14')).toEqual(['A1-13', 'A1-14'])
    expect(parsePresetWpRefs('A12以及对应实质性底稿函证程序')).toContain('A12')
  })
})
