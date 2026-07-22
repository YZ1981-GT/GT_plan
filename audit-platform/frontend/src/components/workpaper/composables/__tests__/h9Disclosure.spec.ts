/**
 * H9 披露模型 / sync payload / 取数 / 附注跳转
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  H9_NOTE_SECTION,
  isH9DisclosureApplicable,
  isH9LeaseLiabilityNoteSection,
} from '../h9NoteSectionMap'
import {
  buildListedDisplayRows,
  buildSoeDisplayRows,
  createDefaultListedState,
  createDefaultSoeState,
  formatListedInterestNote,
  mapToListedCategoryItem,
  resolveListedInterestNote,
} from '../h9DisclosureModel'
import {
  buildH9ListedSyncPayloads,
  buildH9SoeSyncPayloads,
} from '../h9DisclosureSyncPayload'
import { useH9ListedDisclosure, useH9SoeDisclosure } from '../useH9Disclosure'
import {
  isH9LeaseLiabilityNoteSection as jumpIsH9,
  resolveNoteDisclosureJumpTarget,
} from '@/views/composables/noteDisclosureJump'

describe('h9NoteSectionMap', () => {
  it('上市/国企映射到五、47 / 八、52', () => {
    expect(H9_NOTE_SECTION.listed).toBe('五、47')
    expect(H9_NOTE_SECTION.soe).toBe('八、52')
    expect(isH9LeaseLiabilityNoteSection('五、47')).toBe(true)
    expect(isH9LeaseLiabilityNoteSection('租赁负债')).toBe(true)
    expect(isH9LeaseLiabilityNoteSection('使用权资产')).toBe(false)
    expect(isH9DisclosureApplicable('listed', ['listed_standalone'])).toBe(true)
    expect(isH9DisclosureApplicable('listed', ['soe_standalone'])).toBe(false)
  })
})

describe('h9DisclosureModel', () => {
  it('上市：小计 − 一年内 = 合计', () => {
    const state = createDefaultListedState()
    state.rows = [
      { item: '房屋及建筑物租赁', endBalance: 100, lastYearEnd: 80 },
      { item: '设备租赁', endBalance: 50, lastYearEnd: 40 },
    ]
    state.withinOneYear = { end: 30, last: 20 }
    const rows = buildListedDisplayRows(state)
    expect(rows.find((r) => r.kind === 'subtotal')).toMatchObject({ endBalance: 150, lastYearEnd: 120 })
    expect(rows.find((r) => r.kind === 'total')).toMatchObject({ endBalance: 120, lastYearEnd: 100 })
  })

  it('国企：净额 = 付款额 − 未确认 − 重分类', () => {
    const state = createDefaultSoeState()
    state.rows[0].endBalance = 200
    state.rows[0].beginBalance = 180
    state.rows[1].endBalance = 40
    state.rows[1].beginBalance = 35
    state.rows[2].endBalance = 20
    state.rows[2].beginBalance = 15
    const net = buildSoeDisplayRows(state).find((r) => r.kind === 'net')!
    expect(net.endBalance).toBe(140)
    expect(net.beginBalance).toBe(130)
  })

  it('利息说明万元口径', () => {
    const text = formatListedInterestNote({
      total: 1_000_000,
      financeExpense: 800_000,
      capitalized: 200_000,
      year: '2025',
    })
    expect(text).toContain('2025年')
    expect(text).toContain('100.00万元')
    expect(text).toContain('80.00万元')
    expect(text).toContain('20.00万元')
    expect(mapToListedCategoryItem('办公楼租赁')).toBe('房屋及建筑物租赁')
  })

  it('有 override 时优先用 override', () => {
    const state = createDefaultListedState()
    state.interest = { total: 100, financeExpense: 100, capitalized: 0, year: '2025' }
    state.interestNoteOverride = '手工说明'
    expect(resolveListedInterestNote(state)).toBe('手工说明')
  })
})

describe('h9DisclosureSyncPayload', () => {
  it('buildH9ListedSyncPayloads 目标五、47', () => {
    const state = createDefaultListedState()
    state.rows = [{ item: '房屋及建筑物租赁', endBalance: 10, lastYearEnd: 8 }]
    state.withinOneYear = { end: 2, last: 1 }
    state.interest = { total: 10000, financeExpense: 10000, capitalized: 0, year: '2025' }
    const payloads = buildH9ListedSyncPayloads('wp-h9', ['listed_standalone'], state)
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe('五、47')
    expect(payloads[0].sub_table_data['租赁负债']?.length).toBeGreaterThan(3)
    expect(payloads[0].sub_table_data._note_texts?.length).toBe(1)
  })

  it('buildH9SoeSyncPayloads 目标八、52', () => {
    const state = createDefaultSoeState()
    state.rows[0].endBalance = 100
    state.rows[1].endBalance = 20
    state.rows[2].endBalance = 10
    const payloads = buildH9SoeSyncPayloads('wp-h9', ['soe_standalone'], state)
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe('八、52')
    expect(payloads[0].sheet_name).toContain('国企')
    const net = payloads[0].sub_table_data['租赁负债']?.find((r) => r.label === '租赁负债净额')
    expect(net?.end_balance).toBe(70)
  })
})

describe('useH9Disclosure pull', () => {
  it('上市：从 H9-1/H9-2 带入分类、一年内到期与利息', () => {
    const allResponses = ref(new Map([
      ['H9-1-rows', {
        remark: JSON.stringify([
          { name: '房屋租赁A', block: 'liability', beginBalance: 80, endBalance: 100, audited: 100, rje: 0 },
          { name: '货车', block: 'liability', beginBalance: 40, endBalance: 50, audited: 50, rje: 0 },
          { name: '未确认', block: 'unearned', beginBalance: 10, endBalance: 12, audited: 12 },
        ]),
      }],
      ['H9-2-rows', {
        remark: JSON.stringify([
          { contractNo: 'C1', interestAccrued: 5000, interestAje: 0, reclassification: 30 },
          { contractNo: 'C2', interestAccrued: 2000, interestAje: 500, reclassification: 10 },
        ]),
      }],
    ]))
    const saved: any[] = []
    const api = useH9ListedDisclosure({
      allResponses,
      onSave: (id, v) => saved.push({ id, v }),
    })
    const res = api.pullFromSources()
    expect(res.message).toContain('带入')
    expect(api.state.value.rows.some((r) => r.item === '房屋及建筑物租赁' && r.endBalance === 100)).toBe(true)
    expect(api.state.value.rows.some((r) => r.item === '车辆租赁' && r.endBalance === 50)).toBe(true)
    expect(api.state.value.withinOneYear.end).toBe(40)
    expect(api.state.value.interest.total).toBe(7500)
    expect(saved.length).toBeGreaterThan(0)
  })

  it('国企：从 H9-1 带入付款额/未确认融资费用', () => {
    const allResponses = ref(new Map([
      ['H9-1-rows', {
        remark: JSON.stringify([
          { name: 'A', block: 'liability', beginBalance: 200, audited: 220 },
          { name: 'B', block: 'unearned', beginBalance: 30, audited: 25 },
        ]),
      }],
      ['H9-2-rows', {
        remark: JSON.stringify([{ reclassification: 15 }]),
      }],
    ]))
    const api = useH9SoeDisclosure({
      allResponses,
      onSave: () => undefined,
    })
    api.pullFromSources()
    expect(api.state.value.rows.find((r) => r.key === 'payment')).toMatchObject({
      endBalance: 220,
      beginBalance: 200,
    })
    expect(api.state.value.rows.find((r) => r.key === 'unearned')).toMatchObject({
      endBalance: 25,
      beginBalance: 30,
    })
    expect(api.state.value.rows.find((r) => r.key === 'reclass')?.endBalance).toBe(15)
  })
})

describe('noteDisclosureJump H9', () => {
  it('detects H9 lease liability sections', () => {
    expect(jumpIsH9('五、47')).toBe(true)
    expect(jumpIsH9('八、52 租赁负债')).toBe(true)
    expect(jumpIsH9('五、25')).toBe(false)
  })

  it('infers H9 listed disclosure from 五、47', () => {
    const target = resolveNoteDisclosureJumpTarget({
      note_section: '五、47',
      last_sync_wp_id: 'wp-h9',
    })
    expect(target?.wpCode).toBe('H9')
    expect(target?.variant).toBe('listed')
    expect(target?.sheet).toContain('上市公司')
  })

  it('infers H9 SOE disclosure from 八、52', () => {
    expect(resolveNoteDisclosureJumpTarget({
      note_section: '八、52',
      source_template: 'soe',
    })?.wpCode).toBe('H9')
  })
})
