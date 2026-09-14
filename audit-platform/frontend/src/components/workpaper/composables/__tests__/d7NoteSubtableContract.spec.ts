/**
 * D7 合同负债披露子表 ↔ 附注模板契约（共享 helper 5+1 条 Property）
 *
 * 重点守：国企第 2 表原为占位名「合同负债（表2）」，已按源模板 A20 校正为
 * 「本期合同负债账面价值的重大变动」——错位即产出孤儿子表。
 *
 * spec: .kiro/specs/d-cycle-remaining-disclosure-alignment/ Task 3.4
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  D7_NOTE_SECTION,
  D7_LISTED_SUBTABLE,
  D7_SOE_SUBTABLE,
  D7_OBSOLETE_TABLE_NAMES,
  D7_NOTE_TEXT_SECTIONS,
  D7_NOTE_TEXT_KEYS,
  D7_QUALITATIVE_TITLES,
  buildD7ListedColumns,
  buildD7SoeColumns,
  buildD7NoteTexts,
} from '../d7NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'D7',
  variants: [
    {
      variant: 'listed',
      section: D7_NOTE_SECTION.listed,
      subtables: D7_LISTED_SUBTABLE,
      columns: buildD7ListedColumns(),
    },
    {
      variant: 'soe',
      section: D7_NOTE_SECTION.soe,
      subtables: D7_SOE_SUBTABLE,
      columns: buildD7SoeColumns(),
    },
  ],
})

describe('D7 专属', () => {
  it('国企第 2 表名不再是占位「合同负债（表2）」', () => {
    expect(D7_SOE_SUBTABLE.change).toBe('本期合同负债账面价值的重大变动')
    expect(Object.values(D7_SOE_SUBTABLE)).not.toContain('合同负债（表2）')
  })

  it('废弃表名登记在册（供 _removed_table_keys 清理附注残留）', () => {
    expect(D7_OBSOLETE_TABLE_NAMES.soe).toContain('合同负债（表2）')
    // 废弃名不得同时出现在当前表名里（否则会把刚推的表删掉）
    for (const name of D7_OBSOLETE_TABLE_NAMES.soe) {
      expect(Object.values(D7_SOE_SUBTABLE)).not.toContain(name)
    }
  })

  it('五张表全部显式 flat（源模板均为单行表头）', () => {
    for (const cols of [
      ...Object.values(buildD7ListedColumns()),
      ...Object.values(buildD7SoeColumns()),
    ]) {
      expect(cols.some((c) => c.flat)).toBe(true)
      expect(cols.some((c) => c.group)).toBe(false)
    }
  })
})

// ─── 文本域键集（R4：源模板定性披露不得无处录入）──────────────────────────

describe('D7 文本域键集单一真源', () => {
  // 直接按相对 __dirname 定位同目录上一级的源码，避免数 `..` 层数出错
  const read = (name: string) => readFileSync(resolve(__dirname, '..', name), 'utf-8')

  it('D7_NOTE_TEXT_KEYS ≡ 两版 sections 键的并集，且无重复', () => {
    const want = [
      ...D7_NOTE_TEXT_SECTIONS.listed.map((s) => s.key),
      ...D7_NOTE_TEXT_SECTIONS.soe.map((s) => s.key),
    ]
    expect(D7_NOTE_TEXT_KEYS).toEqual(want)
    expect(new Set(D7_NOTE_TEXT_KEYS).size).toBe(D7_NOTE_TEXT_KEYS.length)
  })

  it('两版各含源模板要求的 3 段定性披露（上市 A32-A34 / 国企 A15-A17）', () => {
    expect(D7_QUALITATIVE_TITLES).toHaveLength(3)
    for (const variant of ['listed', 'soe'] as const) {
      const keys = D7_NOTE_TEXT_SECTIONS[variant].map((s) => s.key)
      for (let i = 1; i <= 3; i++) expect(keys).toContain(`D7-note-${variant}-qual-${i}`)
    }
  })

  it('每条都有中文 title（缺 title 时后端会渲染成英文键）', () => {
    for (const variant of ['listed', 'soe'] as const) {
      for (const s of D7_NOTE_TEXT_SECTIONS[variant]) {
        expect(String(s.title).trim().length, s.key).toBeGreaterThan(0)
        expect(s.title).not.toMatch(/^[a-zA-Z0-9_-]+$/)
      }
    }
  })

  it('🔴 composable 不得再硬编码键集（防双真源漂移）', () => {
    const src = read('useD7Disclosure.ts')
    expect(src).toContain('D7_NOTE_TEXT_KEYS')
    // 不得出现形如 'D7-note-listed-text-1' 的字面量数组
    expect(src).not.toMatch(/'D7-note-(listed|soe)-text-\d'/)
  })

  it('非空文本才进 _note_texts，且 section/title 成对', () => {
    const texts = buildD7NoteTexts('listed', {
      'D7-note-listed-qual-1': '本期确认收入 100 万元。',
      'D7-note-listed-qual-2': '   ',
    })
    expect(texts).toEqual([
      {
        section: 'D7-note-listed-qual-1',
        title: D7_QUALITATIVE_TITLES[0],
        text: '本期确认收入 100 万元。',
      },
    ])
  })
})
