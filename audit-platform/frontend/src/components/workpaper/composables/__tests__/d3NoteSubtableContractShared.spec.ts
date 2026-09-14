/**
 * D3 预收款项披露子表 ↔ 附注模板契约（共享 helper 5+1 条 Property）
 *
 * 与 `d3NoteSubtableContract.spec.ts` 分工：本文件只跑平台通用 Property
 * （子表名逐字 / 章节存在 / flat·group 表态 / 纯文本 / 标签列头对齐 headers[0]），
 * D3 专属的账龄映射与逐表合计字面留在原文件。
 *
 * spec: .kiro/specs/d-cycle-remaining-disclosure-alignment/ Task 2.3
 */
import { describe, expect, it } from 'vitest'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  D3_NOTE_SECTION,
  D3_LISTED_SUBTABLE,
  D3_SOE_SUBTABLE,
  D3_OBSOLETE_TABLE_NAMES,
  buildD3ListedColumns,
  buildD3SoeColumns,
} from '../d3NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'D3',
  variants: [
    {
      variant: 'listed',
      section: D3_NOTE_SECTION.listed,
      subtables: D3_LISTED_SUBTABLE,
      columns: buildD3ListedColumns(),
    },
    {
      variant: 'soe',
      section: D3_NOTE_SECTION.soe,
      subtables: D3_SOE_SUBTABLE,
      columns: buildD3SoeColumns(),
    },
  ],
})

describe('D3 专属（共享 helper 补充）', () => {
  it('五张表全部显式 flat（源模板均为单行表头）', () => {
    for (const cols of [
      ...Object.values(buildD3ListedColumns()),
      ...Object.values(buildD3SoeColumns()),
    ]) {
      expect(cols.some((c) => c.flat)).toBe(true)
      expect(cols.some((c) => c.group)).toBe(false)
    }
  })

  it('废弃表名登记在册且不与当前表名冲突', () => {
    expect(D3_OBSOLETE_TABLE_NAMES.soe).toContain('账龄超过1年的重要预收款项')
    for (const name of D3_OBSOLETE_TABLE_NAMES.soe) {
      expect(Object.values(D3_SOE_SUBTABLE)).not.toContain(name)
    }
  })
})
