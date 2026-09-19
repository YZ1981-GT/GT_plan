/**
 * M3 库存股 披露子表 ↔ note_template 契约
 *
 * 章节：五、56（上市，单表 5 列 flat）；国企无此章节（应返回 null/跳过）
 */
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  M3_NOTE_SECTION,
  M3_SUBTABLE,
  buildM3Columns,
} from '../m3NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'M3',
  variants: [
    {
      variant: 'listed',
      section: M3_NOTE_SECTION.listed,
      subtables: M3_SUBTABLE,
      columns: buildM3Columns(),
    },
  ],
})
