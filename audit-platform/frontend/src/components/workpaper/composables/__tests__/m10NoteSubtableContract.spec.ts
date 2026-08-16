/**
 * M10 其他权益工具 披露子表 ↔ note_template 契约
 *
 * 章节：五、54（上市 3 表：basic 10 列 flat / movement 9 列两级 / holders 3 列 flat）
 *       八、59（国企 1 表：9 列两级 movement）
 */
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  M10_NOTE_SECTION,
  M10_LISTED_SUBTABLE,
  M10_SOE_SUBTABLE,
  buildM10ListedColumns,
  buildM10SoeColumns,
} from '../m10NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'M10',
  variants: [
    {
      variant: 'listed',
      section: M10_NOTE_SECTION.listed,
      subtables: M10_LISTED_SUBTABLE,
      columns: buildM10ListedColumns(),
    },
    {
      variant: 'soe',
      section: M10_NOTE_SECTION.soe,
      subtables: M10_SOE_SUBTABLE,
      columns: buildM10SoeColumns(),
    },
  ],
})
