/**
 * M8 一般风险准备 披露子表 ↔ note_template 契约
 *
 * 章节：五、60（上市）/ 八、94（国企），两版同结构 5 列 flat
 */
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  M8_NOTE_SECTION,
  M8_SUBTABLE,
  buildM8Columns,
} from '../m8NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'M8',
  variants: [
    {
      variant: 'listed',
      section: M8_NOTE_SECTION.listed,
      subtables: M8_SUBTABLE,
      columns: buildM8Columns(),
    },
    {
      variant: 'soe',
      section: M8_NOTE_SECTION.soe,
      subtables: M8_SUBTABLE,
      columns: buildM8Columns(),
    },
  ],
})
