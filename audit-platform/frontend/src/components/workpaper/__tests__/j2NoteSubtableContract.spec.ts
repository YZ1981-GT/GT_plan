/**
 * J2 长期应付职工薪酬/设定受益计划净资产 — 披露子表契约测试
 *
 * 覆盖 Property 1~4（P5 不适用：两个变体都适用）：
 * - P1 子表名与模板 tables[].name 逐字一致
 * - P2 章节号存在于对应 variant 模板
 * - P3 每张表 flat/group 明确表态
 * - P4 列标签纯文本（无 HTML）
 *
 * Spec: .kiro/specs/disclosure-sync-path-buildout/ (批6 J2)
 */
import { runDisclosureSubtableContract } from '../composables/__tests__/_disclosureSubtableContract.helper'
import {
  J2_NOTE_SECTION,
  J2_DISCLOSURE_SHEET_NAME,
} from '../composables/j2NoteSectionMap'
import {
  J2_LISTED_SUBTABLE,
  J2_SOE_SUBTABLE,
  buildJ2ListedColumns,
  buildJ2SoeColumns,
} from '../composables/j2DisclosureSyncPayload'

runDisclosureSubtableContract({
  cycle: 'J2',
  variants: [
    {
      variant: 'listed',
      section: J2_NOTE_SECTION.listed,
      subtables: J2_LISTED_SUBTABLE,
      columns: buildJ2ListedColumns(),
    },
    {
      variant: 'soe',
      section: J2_NOTE_SECTION.soe,
      subtables: J2_SOE_SUBTABLE,
      columns: buildJ2SoeColumns(),
    },
  ],
})
