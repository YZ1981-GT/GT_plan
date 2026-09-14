/**
 * D5 应收款项融资披露子表 ↔ 附注模板契约（共享 helper 5+1 条 Property）
 *
 * 重点守：上市「期末本公司已背书或贴现但尚未到期的应收票据」两个数据列共前缀「期末」，
 * 未显式 `flat` 时 seed 路径会被 `_infer_groups_from_headers` 猜出凭空「期末」父表头。
 *
 * spec: .kiro/specs/d-cycle-remaining-disclosure-alignment/ Task 4.4
 */
import { describe, expect, it } from 'vitest'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  D5_NOTE_SECTION,
  D5_LISTED_SUBTABLE,
  D5_SOE_SUBTABLE,
  buildD5ListedColumns,
  buildD5SoeColumns,
} from '../d5NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'D5',
  variants: [
    {
      variant: 'listed',
      section: D5_NOTE_SECTION.listed,
      subtables: D5_LISTED_SUBTABLE,
      columns: buildD5ListedColumns(),
    },
    {
      variant: 'soe',
      section: D5_NOTE_SECTION.soe,
      subtables: D5_SOE_SUBTABLE,
      columns: buildD5SoeColumns(),
    },
  ],
})

describe('D5 专属：共前缀列必须显式 flat', () => {
  it('背书或贴现表两列共前缀「期末」→ 必须 flat 且不得带 group', () => {
    const cols = buildD5ListedColumns()[D5_LISTED_SUBTABLE.endorsed]
    expect(cols.map((c) => c.label)).toEqual([
      '种  类', '期末终止确认金额', '期末未终止确认金额',
    ])
    expect(cols.some((c) => c.flat)).toBe(true)
    expect(cols.some((c) => c.group)).toBe(false)
  })

  it('四张表全部显式 flat（源模板均为单行表头）', () => {
    for (const [name, cols] of Object.entries(buildD5ListedColumns())) {
      expect(cols.some((c) => c.flat), `${name} 未标 flat`).toBe(true)
    }
    for (const [name, cols] of Object.entries(buildD5SoeColumns())) {
      expect(cols.some((c) => c.flat), `${name} 未标 flat`).toBe(true)
    }
  })

  it('减值准备情况表保留标签列（模板曾只剩「减值准备金额」一列）', () => {
    const cols = buildD5ListedColumns()[D5_LISTED_SUBTABLE.impairment]
    expect(cols.map((c) => c.label)).toEqual(['项目', '减值准备金额'])
    expect(cols[0].is_label).toBe(true)
  })
})
