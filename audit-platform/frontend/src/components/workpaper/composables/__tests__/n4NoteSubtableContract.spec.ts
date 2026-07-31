/**
 * N4 披露子表 ↔ note_template 契约
 *
 * 只接上市变体 —— 🔴 国企版源模板此节为「附注披露信息：无」，不披露、无章节、无表，
 * 由 `n4NoteSectionMap.spec.ts` 的 Property 4 反向锁死（`buildN4SyncPayload('soe')` 恒 null）。
 *
 * 共享 helper 6 条 Property + N4 专属：
 * - P7 双向键集
 * - P8 全表 guidance
 * - P9 同章节表名唯一
 * - P10 同步 columns ↔ 模板 columns 同形
 *
 * spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/` Task 8.1
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  columnDeclState,
  runDisclosureSubtableContract,
} from './_disclosureSubtableContract.helper'
import {
  N4_NOTE_SECTION,
  N4_SUB_TABLE_KEYS,
  buildN4ListedColumns,
} from '../n4NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'N4',
  variants: [
    {
      variant: 'listed',
      section: N4_NOTE_SECTION.listed,
      subtables: N4_SUB_TABLE_KEYS.listed,
      columns: buildN4ListedColumns(),
    },
  ],
})

const ROOT = resolve(__dirname, '../../../../../../../backend/data')
const COLUMNS = buildN4ListedColumns()

function loadSection(): any {
  const raw = JSON.parse(readFileSync(resolve(ROOT, 'note_template_listed.json'), 'utf-8'))
  const sec = (raw.sections || []).find((s: any) => s.section_number === N4_NOTE_SECTION.listed)
  expect(sec, `缺章节 ${N4_NOTE_SECTION.listed}`).toBeTruthy()
  return sec
}

describe('N4 披露子表专属契约', () => {
  it('P7 模板表名与映射值双向覆盖', () => {
    const templateNames = new Set(loadSection().tables.map((t: any) => t.name))
    const mapped = new Set(Object.values(N4_SUB_TABLE_KEYS.listed) as string[])
    expect([...templateNames].filter((n) => !mapped.has(n as string))).toEqual([])
    expect([...mapped].filter((n) => !templateNames.has(n))).toEqual([])
  })

  it('P8 全部表有 guidance', () => {
    const missing = loadSection()
      .tables.filter((t: any) => !String(t.guidance ?? '').trim())
      .map((t: any) => t.name)
    expect(missing).toEqual([])
  })

  it('P9 同章节表名唯一', () => {
    const names = loadSection().tables.map((t: any) => t.name)
    expect(new Set(names).size).toBe(names.length)
  })

  it('P10 同步 columns 与模板 columns 的 label/key 一致', () => {
    for (const t of loadSection().tables) {
      const defs = COLUMNS[t.name]
      expect(defs, `缺 ${t.name} 的列定义`).toBeTruthy()
      expect(defs.map((d) => d.label)).toEqual(t.columns.map((c: any) => c.label))
      expect(defs.map((d) => d.key)).toEqual(t.columns.map((c: any) => c.key))
      expect(columnDeclState(defs)).toBe(columnDeclState(t.columns))
    }
  })
})
