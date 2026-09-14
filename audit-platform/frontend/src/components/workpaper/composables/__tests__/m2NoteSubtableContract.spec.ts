/**
 * M2 实收资本/股本 披露子表 ↔ note_template 契约
 *
 * 章节：五、53（上市 `股本（单位：万股）` 8 列两级）/ 八、58（国企 `实收资本` 7 列两级）
 */
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  M2_NOTE_SECTION,
  M2_SUBTABLE,
  buildM2ListedColumns,
  buildM2SoeColumns,
} from '../m2NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'M2',
  variants: [
    {
      variant: 'listed',
      section: M2_NOTE_SECTION.listed,
      subtables: { main: M2_SUBTABLE.listed },
      columns: buildM2ListedColumns(),
    },
    {
      variant: 'soe',
      section: M2_NOTE_SECTION.soe,
      subtables: { main: M2_SUBTABLE.soe },
      columns: buildM2SoeColumns(),
    },
  ],
})
