/**
 * `_disclosureSubtableContract.helper` 自检
 *
 * 用 **K1**（已有完整链路且模板已对齐）反向验证 helper：若 helper 本身有 bug，
 * 这里会红；各循环接入时才能信任它。同时验证 `columnDeclState` 三态判定。
 *
 * Spec: .kiro/specs/disclosure-sync-path-buildout/ Task 1.2
 */
import { describe, expect, it } from 'vitest'
import {
  columnDeclState,
  runDisclosureSubtableContract,
  type ContractColumnDef,
} from './_disclosureSubtableContract.helper'
import { K1_LISTED_SUBTABLE, K1_NOTE_SECTION, K1_SOE_SUBTABLE } from '../k1NoteSectionMap'
import { K1_LISTED_COLUMNS, K1_SOE_COLUMNS } from '../k1DisclosureSyncPayload'

describe('columnDeclState 三态判定', () => {
  const label: ContractColumnDef = { key: 'label', label: '项目', is_label: true }

  it('无列 → none', () => {
    expect(columnDeclState([])).toBe('none')
    expect(columnDeclState(undefined)).toBe('none')
  })

  it('只有列无 group/flat → none（会落入前缀推断）', () => {
    expect(columnDeclState([label, { key: 'a', label: 'A' }])).toBe('none')
  })

  it('任一列标 flat → flat', () => {
    expect(columnDeclState([{ ...label, flat: true }, { key: 'a', label: 'A' }])).toBe('flat')
  })

  it('任一列有 group → group', () => {
    expect(columnDeclState([label, { key: 'a', label: 'A', group: '期末' }])).toBe('group')
  })

  it('两者并存 → conflict', () => {
    expect(
      columnDeclState([{ ...label, flat: true }, { key: 'a', label: 'A', group: '期末' }]),
    ).toBe('conflict')
  })
})

// ── 用 K1 真实数据跑一遍完整契约（helper 自检）─────────────────
//
// 2026-07-31（`k-cycle-disclosure-alignment` 批 3）起 K1 的 27 张同步表**全部显式表态**
// （单级标 `flat`、两级用 `group` + 叶子列名），`columnsPending` 逃逸阀已按设计清空 ——
// helper 的「columnsPending 不得残留已补齐的表」正是靠这条把逃逸阀逼回零的。
// → 本自检现在跑的是 P1~P6 **全量真断言**，不再有任何豁免项。
runDisclosureSubtableContract({
  cycle: 'K1（helper 自检）',
  variants: [
    {
      variant: 'listed',
      section: K1_NOTE_SECTION.listed,
      subtables: K1_LISTED_SUBTABLE,
      columns: K1_LISTED_COLUMNS as Record<string, ContractColumnDef[]>,
    },
    {
      variant: 'soe',
      section: K1_NOTE_SECTION.soe,
      subtables: K1_SOE_SUBTABLE,
      columns: K1_SOE_COLUMNS as Record<string, ContractColumnDef[]>,
    },
  ],
})
