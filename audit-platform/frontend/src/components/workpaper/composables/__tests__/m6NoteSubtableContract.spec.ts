/**
 * M6 未分配利润 披露子表 ↔ note_template 契约
 *
 * 章节：五、61（上市 4 列 flat）/ 八、63（国企 3 列 flat）
 */
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  M6_NOTE_SECTION,
  M6_SUBTABLE,
  buildM6ListedColumns,
  buildM6SoeColumns,
} from '../m6NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'M6',
  variants: [
    {
      variant: 'listed',
      section: M6_NOTE_SECTION.listed,
      subtables: M6_SUBTABLE,
      columns: buildM6ListedColumns(),
    },
    {
      variant: 'soe',
      section: M6_NOTE_SECTION.soe,
      subtables: M6_SUBTABLE,
      columns: buildM6SoeColumns(),
    },
  ],
})
