/**
 * useJ1DisclosureSections — J1 附注披露表 持久化 + 合计 回归测试
 *
 * 锁定 2026-07-26 修复的 P0：
 *  1. 两张披露表 onMounted 只有 TODO 注释 → 录入刷新即丢（现 hydrate + 落库）
 *  2. 汇总表「合计」行是 ref 里的静态 0 行 → 恒为 0（现 computed 聚合）
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import {
  useJ1DisclosureSections,
  recalcDisclosureRow,
  buildDisclosureSubtotal,
  categoryForSummaryLabel,
  aggregateAdjudicationByCategory,
  aggregateDetailAuditedByCategory,
  applySummaryPull,
  type J1DisclosureRow,
  type ChecklistItem,
} from '../useJ1DisclosureSections'

function row(p: Partial<J1DisclosureRow>): J1DisclosureRow {
  return {
    id: 'x', label: 'L', category: 'summary',
    beginBalance: 0, increase: 0, decrease: 0, endBalance: 0,
    ...p,
  }
}

const DEFAULTS = {
  summary: [
    row({ id: 's-1', label: '短期薪酬' }),
    row({ id: 's-2', label: '辞退福利' }),
  ],
  shortTerm: [
    row({ id: 'st-1', label: '工资', category: 'short_term' }),
    row({ id: 'st-2', label: '社会保险费', category: 'short_term' }),
    row({ id: 'st-3', label: '其中：医疗保险费', category: 'short_term', indent: 1 }),
  ],
  postEmployment: [row({ id: 'pe-1', label: '离职后福利', category: 'post_employment' })],
}

describe('recalcDisclosureRow / buildDisclosureSubtotal', () => {
  it('期末 = 期初 + 增加 − 减少（负债贷方）', () => {
    const r = recalcDisclosureRow(row({ beginBalance: 100, increase: 500, decrease: 480 }))
    expect(r.endBalance).toBe(120)
  })

  it('小计只累加非缩进行（「其中：」明细不重复计入）', () => {
    const rows = [
      recalcDisclosureRow(row({ beginBalance: 10, increase: 100, decrease: 90 })),
      recalcDisclosureRow(row({ indent: 1, beginBalance: 5, increase: 50, decrease: 45 })),
    ]
    const st = buildDisclosureSubtotal('t', '合 计', 'short_term', rows)
    expect(st.beginBalance).toBe(10)
    expect(st.endBalance).toBe(20)
    expect(st.isSubtotal).toBe(true)
  })
})

describe('useJ1DisclosureSections — 合计行', () => {
  it('汇总表合计随数据行聚合（历史实现恒为 0）', () => {
    const s = useJ1DisclosureSections({ variant: 'listed', defaults: DEFAULTS, noteKeys: ['shortTerm'] })
    s.summaryData.value[0].increase = 1000
    s.summaryData.value[0].decrease = 400
    recalcDisclosureRow(s.summaryData.value[0])
    const total = s.summaryRows.value.at(-1)!
    expect(total.isSubtotal).toBe(true)
    expect(total.endBalance).toBe(600)
  })

  it('summaryRows = 数据行 + 合计行', () => {
    const s = useJ1DisclosureSections({ variant: 'soe', defaults: DEFAULTS, noteKeys: ['soe'] })
    expect(s.summaryRows.value).toHaveLength(DEFAULTS.summary.length + 1)
  })
})

describe('useJ1DisclosureSections — 持久化', () => {
  it('persist 写四个分区键（variant 前缀隔离上市/国企）', () => {
    const map = ref(new Map<string, ChecklistItem>())
    const saveImmediate = vi.fn().mockResolvedValue(undefined)
    const s = useJ1DisclosureSections({
      variant: 'listed', defaults: DEFAULTS, allResponses: map, saveImmediate,
      noteKeys: ['shortTerm', 'postEmployment', 'severance'],
    })
    s.notes.value.severance = '本期无辞退计划'
    s.persist()

    const items: ChecklistItem[] = saveImmediate.mock.calls[0][0]
    expect(items.map(i => i.item_id).sort()).toEqual([
      'J1-disc-listed-notes',
      'J1-disc-listed-post-employment',
      'J1-disc-listed-short-term',
      'J1-disc-listed-summary',
    ])
    const notes = JSON.parse(items.find(i => i.item_id === 'J1-disc-listed-notes')!.remark as string)
    expect(notes.severance).toBe('本期无辞退计划')
    expect(map.value.size).toBe(4)
  })

  it('soe variant 用独立键（两版本互不覆盖）', () => {
    const saveImmediate = vi.fn().mockResolvedValue(undefined)
    const s = useJ1DisclosureSections({ variant: 'soe', defaults: DEFAULTS, saveImmediate, noteKeys: ['soe'] })
    s.persist()
    const items: ChecklistItem[] = saveImmediate.mock.calls[0][0]
    expect(items.every(i => i.item_id.startsWith('J1-disc-soe-'))).toBe(true)
  })

  it('hydrate 从 allResponses 恢复行与说明，并重算期末', () => {
    const map = ref(new Map<string, ChecklistItem>([
      ['J1-disc-listed-summary', {
        item_id: 'J1-disc-listed-summary', conclusion: null,
        remark: JSON.stringify([{ id: 's-1', label: '短期薪酬', category: 'summary', beginBalance: 100, increase: 900, decrease: 800 }]),
      }],
      ['J1-disc-listed-notes', {
        item_id: 'J1-disc-listed-notes', conclusion: null,
        remark: JSON.stringify({ shortTerm: '含非货币性福利' }),
      }],
    ]))
    const s = useJ1DisclosureSections({
      variant: 'listed', defaults: DEFAULTS, allResponses: map,
      noteKeys: ['shortTerm', 'postEmployment', 'severance'],
    })
    s.hydrate()
    expect(s.summaryData.value).toHaveLength(1)
    expect(s.summaryData.value[0].endBalance).toBe(200)
    expect(s.notes.value.shortTerm).toBe('含非货币性福利')
    // 未持久化的分区保留默认骨架行
    expect(s.shortTermData.value).toHaveLength(3)
  })

  it('hydrate 不触发回写（避免加载即 PUT）', async () => {
    const map = ref(new Map<string, ChecklistItem>([
      ['J1-disc-soe-summary', {
        item_id: 'J1-disc-soe-summary', conclusion: null,
        remark: JSON.stringify([{ id: 's-1', label: '短期薪酬', category: 'summary', beginBalance: 1, increase: 0, decrease: 0 }]),
      }],
    ]))
    const saveImmediate = vi.fn().mockResolvedValue(undefined)
    const s = useJ1DisclosureSections({
      variant: 'soe', defaults: DEFAULTS, allResponses: map, saveImmediate, noteKeys: ['soe'],
    })
    s.hydrate()
    await nextTick()
    expect(saveImmediate).not.toHaveBeenCalled()
  })

  it('只读态不落库', () => {
    const saveImmediate = vi.fn().mockResolvedValue(undefined)
    const s = useJ1DisclosureSections({
      variant: 'listed', defaults: DEFAULTS, saveImmediate,
      isReadonly: ref(true), noteKeys: ['shortTerm'],
    })
    s.persist()
    expect(saveImmediate).not.toHaveBeenCalled()
  })

  it('序列化只存基础字段（期末为派生列，hydrate 时重算）', () => {
    const saveImmediate = vi.fn().mockResolvedValue(undefined)
    const s = useJ1DisclosureSections({ variant: 'listed', defaults: DEFAULTS, saveImmediate, noteKeys: ['shortTerm'] })
    s.persist()
    const items: ChecklistItem[] = saveImmediate.mock.calls[0][0]
    const stored = JSON.parse(items.find(i => i.item_id === 'J1-disc-listed-summary')!.remark as string)
    expect(stored[0]).not.toHaveProperty('endBalance')
    expect(stored[0]).toHaveProperty('beginBalance')
  })
})

// ─── P1：从 J1-1 审定表 / J1-2 明细表带入 + 差异告警 ────────────────────────

describe('categoryForSummaryLabel — 汇总行名→审定分类', () => {
  it('四大分类按关键词识别，未知行名返回 null（不覆盖手工行）', () => {
    expect(categoryForSummaryLabel('短期薪酬')).toBe('short_term')
    expect(categoryForSummaryLabel('离职后福利-设定提存计划')).toBe('post_employment')
    expect(categoryForSummaryLabel('（2）设定提存计划')).toBe('post_employment')
    expect(categoryForSummaryLabel('辞退福利')).toBe('severance')
    expect(categoryForSummaryLabel('一年内到期的其他福利')).toBe('other_long_term')
    expect(categoryForSummaryLabel('其他')).toBeNull()
    expect(categoryForSummaryLabel('')).toBeNull()
  })
})

describe('aggregateAdjudicationByCategory / aggregateDetailAuditedByCategory', () => {
  it('审定表按分类汇总期初/期末审定（审定=未审+调整）', () => {
    const agg = aggregateAdjudicationByCategory([
      { category: 'short_term', beginUnadj: 100, beginAje: 5, endUnadj: 200, endAje: 10 },
      { category: 'short_term', beginUnadj: 50, beginAje: 0, endUnadj: 60, endAje: 0 },
      { category: 'severance', beginUnadj: 0, beginAje: 0, endUnadj: 30, endAje: 0 },
    ])
    expect(agg.short_term).toEqual({ begin: 155, end: 270, has: true })
    expect(agg.severance).toEqual({ begin: 0, end: 30, has: true })
    expect(agg.post_employment.has).toBe(false)
  })

  it('明细表只累加非「其中」子项，审定 = 未审 + 调整', () => {
    const agg = aggregateDetailAuditedByCategory({
      shortTerm: [
        { label: '工资', unadjBegin: 100, openingAdj: 5, unadjIncrease: 900, ajeIncrease: 10, unadjDecrease: 800, ajeDecrease: 0 },
        { label: '其中：1.工资', isSubItem: true, unadjBegin: 80, unadjIncrease: 700, unadjDecrease: 620 },
      ],
      postEmployment: [
        { label: '离职后福利', unadjBegin: 20, unadjIncrease: 100, unadjDecrease: 90 },
        { label: '其他长期职工福利', unadjBegin: 5, unadjIncrease: 10, unadjDecrease: 3 },
      ],
    })
    expect(agg.short_term).toEqual({ begin: 105, increase: 910, decrease: 800, has: true })
    expect(agg.post_employment).toEqual({ begin: 20, increase: 100, decrease: 90, has: true })
    expect(agg.other_long_term).toEqual({ begin: 5, increase: 10, decrease: 3, has: true })
    expect(agg.severance.has).toBe(false)
  })
})

describe('applySummaryPull — 期初取审定表、增减取明细表', () => {
  it('覆盖来源侧存在的分类，未出现的分类保持手工值', () => {
    const rows = [
      row({ id: 's-1', label: '短期薪酬', beginBalance: 1, increase: 2, decrease: 3 }),
      row({ id: 's-2', label: '辞退福利', beginBalance: 11, increase: 22, decrease: 33 }),
      row({ id: 's-3', label: '其他', beginBalance: 7 }),
    ]
    const matched = applySummaryPull(
      rows,
      aggregateAdjudicationByCategory([
        { category: 'short_term', beginUnadj: 100, beginAje: 0, endUnadj: 200, endAje: 0 },
      ]),
      aggregateDetailAuditedByCategory({
        shortTerm: [{ label: '工资', unadjBegin: 100, unadjIncrease: 900, unadjDecrease: 800 }],
      }),
    )
    expect(matched).toBe(1)
    expect(rows[0]).toMatchObject({ beginBalance: 100, increase: 900, decrease: 800, endBalance: 200 })
    // 来源侧无辞退福利/未知行名 → 手工值不动
    expect(rows[1]).toMatchObject({ beginBalance: 11, increase: 22, decrease: 33 })
    expect(rows[2].beginBalance).toBe(7)
  })

  it('仅有审定表（无明细增减）时按净变动拆分到增加/减少', () => {
    const rows = [
      row({ id: 's-1', label: '短期薪酬' }),
      row({ id: 's-2', label: '辞退福利' }),
    ]
    applySummaryPull(
      rows,
      aggregateAdjudicationByCategory([
        { category: 'short_term', beginUnadj: 100, beginAje: 0, endUnadj: 150, endAje: 0 },
        { category: 'severance', beginUnadj: 80, beginAje: 0, endUnadj: 30, endAje: 0 },
      ]),
      aggregateDetailAuditedByCategory({}),
    )
    expect(rows[0]).toMatchObject({ beginBalance: 100, increase: 50, decrease: 0, endBalance: 150 })
    expect(rows[1]).toMatchObject({ beginBalance: 80, increase: 0, decrease: 50, endBalance: 30 })
  })
})

describe('useJ1DisclosureSections — pullFromSources + 审定勾稽', () => {
  it('读 J1-1-rows / J1-2 分区键带入并落库；差异 computed 反映与审定合计的差额', () => {
    const map = ref(new Map<string, ChecklistItem>([
      ['J1-1-rows', {
        item_id: 'J1-1-rows', conclusion: null,
        remark: JSON.stringify([
          { category: 'short_term', beginUnadj: 100, beginAje: 0, endUnadj: 200, endAje: 0 },
        ]),
      }],
      ['J1-1-audited-total', { item_id: 'J1-1-audited-total', conclusion: null, remark: '200' }],
      ['J1-2-detail-shortTerm', {
        item_id: 'J1-2-detail-shortTerm', conclusion: null,
        remark: JSON.stringify([{ label: '工资', unadjBegin: 100, unadjIncrease: 900, unadjDecrease: 800 }]),
      }],
    ]))
    const saveImmediate = vi.fn().mockResolvedValue(undefined)
    const s = useJ1DisclosureSections({
      variant: 'listed',
      defaults: DEFAULTS,
      allResponses: map,
      saveImmediate,
      noteKeys: ['shortTerm'],
    })
    expect(s.adjudicationEndTotal.value).toBe(200)
    expect(s.pullFromSources()).toBe(1)
    expect(s.summaryData.value[0]).toMatchObject({ beginBalance: 100, increase: 900, decrease: 800, endBalance: 200 })
    // 汇总期末合计 200 与审定合计 200 一致
    expect(s.summaryVsAdjudicationDiff.value).toBe(0)
    expect(saveImmediate).toHaveBeenCalled()
  })

  it('审定表/明细表均未编制时返回 0 且不落库', () => {
    const map = ref(new Map<string, ChecklistItem>())
    const saveImmediate = vi.fn().mockResolvedValue(undefined)
    const s = useJ1DisclosureSections({
      variant: 'soe',
      defaults: DEFAULTS,
      allResponses: map,
      saveImmediate,
      noteKeys: ['soe'],
    })
    expect(s.pullFromSources()).toBe(0)
    expect(saveImmediate).not.toHaveBeenCalled()
    expect(s.adjudicationEndTotal.value).toBe(0)
  })
})
