/**
 * M9 其他综合收益 披露子表 ↔ note_template 契约
 *
 * 章节：五、57（上市 2 表 8 列两级）/ 八、79（国企 1 表 7 列两级）
 */
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  M9_NOTE_SECTION,
  M9_LISTED_SUBTABLE,
  M9_SOE_SUBTABLE,
  buildM9ListedAllColumns,
  buildM9SoeAllColumns,
} from '../m9NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'M9',
  variants: [
    {
      variant: 'listed',
      section: M9_NOTE_SECTION.listed,
      subtables: M9_LISTED_SUBTABLE,
      columns: buildM9ListedAllColumns(),
    },
    {
      variant: 'soe',
      section: M9_NOTE_SECTION.soe,
      subtables: M9_SOE_SUBTABLE,
      columns: buildM9SoeAllColumns(),
    },
  ],
})
