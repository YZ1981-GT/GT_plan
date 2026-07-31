/**
 * H2 在建工程披露子表 ↔ note_template 契约（复用共享 helper P1~P6）+ H2 专属守卫。
 *
 * spec: h2-construction-in-progress-disclosure-alignment (Task 5)
 */
import { describe, expect, it } from 'vitest'
import { columnDeclState, runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import { H2_LISTED_SUBTABLE, H2_NOTE_SECTION, H2_SOE_SUBTABLE } from '../h2NoteSectionMap'
import { buildH2ListedColumns, buildH2SoeColumns } from '../h2DisclosureSyncPayload'

// 受限在建工程（restricted）不是 §五、23 模板子表（走 _note_texts 叙述），契约排除。
const H2_LISTED_NOTE_SUBTABLES = {
  summary: H2_LISTED_SUBTABLE.summary,
  detail: H2_LISTED_SUBTABLE.detail,
  projectMovement: H2_LISTED_SUBTABLE.projectMovement,
  projectCont: H2_LISTED_SUBTABLE.projectCont,
  impairment: H2_LISTED_SUBTABLE.impairment,
  materials: H2_LISTED_SUBTABLE.materials,
} as const

runDisclosureSubtableContract({
  cycle: 'H2',
  variants: [
    {
      variant: 'listed',
      section: H2_NOTE_SECTION.listed,
      subtables: H2_LISTED_NOTE_SUBTABLES,
      columns: buildH2ListedColumns(),
    },
    {
      variant: 'soe',
      section: H2_NOTE_SECTION.soe,
      subtables: H2_SOE_SUBTABLE,
      columns: buildH2SoeColumns(),
    },
  ],
})

describe('H2 披露结构专属守卫', () => {
  it('materials 已改名「工程物资」，全映射无「项  目」残留', () => {
    expect(H2_LISTED_SUBTABLE.materials).toBe('工程物资')
    expect(Object.values(H2_LISTED_SUBTABLE)).not.toContain('项  目')
    expect(Object.values(H2_SOE_SUBTABLE)).not.toContain('项  目')
  })

  it('两级表头表 columns 带 group（listed 明细 / soe 汇总+情况）', () => {
    const l = buildH2ListedColumns()
    expect(columnDeclState(l['在建工程明细'])).toBe('group')
    expect(l['在建工程明细'].filter((c) => c.group === '期末余额')).toHaveLength(3)
    expect(l['在建工程明细'].filter((c) => c.group === '上年年末余额')).toHaveLength(3)
    const s = buildH2SoeColumns()
    for (const name of ['在建工程', '（1）在建工程情况'] as const) {
      expect(columnDeclState(s[name])).toBe('group')
      expect(s[name].filter((c) => c.group === '期末余额')).toHaveLength(3)
      expect(s[name].filter((c) => c.group === '期初余额')).toHaveLength(3)
    }
  })

  it('两级表头叶子列 key 与后端模板一致（防 seed/push 漂移）', () => {
    const l = buildH2ListedColumns()['在建工程明细'].map((c) => c.key)
    expect(l).toEqual([
      'label', 'end_book', 'end_impairment', 'end_net',
      'prior_book', 'prior_impairment', 'prior_net',
    ])
    const s = buildH2SoeColumns()['在建工程'].map((c) => c.key)
    expect(s).toEqual([
      'label', 'end_book', 'end_impairment', 'end_carrying',
      'begin_book', 'begin_impairment', 'begin_carrying',
    ])
  })
})
