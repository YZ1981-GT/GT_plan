/**
 * K1 披露子表名 ↔ 附注模板契约
 *
 * 防回归：`K1_LISTED_SUBTABLE` / `K1_SOE_SUBTABLE` 的每个值必须能在
 * `note_template_listed.json` §五、8 / `note_template_soe.json` §八、9
 * 的 `tables[].name` 中找到，否则 sync-from-workpaper 会写出孤儿子表
 * （附注 TAB 永空，底稿数据丢失）。
 *
 * spec: k1-other-receivable-disclosure-alignment Task 3.3
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  K1_LISTED_SUBTABLE,
  K1_NOTE_SECTION,
  K1_SOE_SUBTABLE,
} from '../k1NoteSectionMap'
import { K1_LISTED_COLUMNS, K1_SOE_COLUMNS } from '../k1DisclosureSyncPayload'

interface NoteTable { name?: string; headers?: string[]; guidance?: string; _column_groups?: unknown }
interface NoteSection { section_number?: string; tables?: NoteTable[]; text_sections?: string[] }

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

function loadSection(file: string, sectionNumber: string): NoteSection {
  const path = resolve(REPO_ROOT, 'backend/data', file)
  const raw = JSON.parse(readFileSync(path, 'utf-8')) as { sections: NoteSection[] }
  const hit = raw.sections.find((s) => String(s.section_number ?? '').trim() === sectionNumber)
  if (!hit) throw new Error(`${file} 缺少章节 ${sectionNumber}`)
  return hit
}

const listedSection = loadSection('note_template_listed.json', K1_NOTE_SECTION.listed)
const soeSection = loadSection('note_template_soe.json', K1_NOTE_SECTION.soe)

const listedNames = new Set((listedSection.tables ?? []).map((t) => t.name))
const soeNames = new Set((soeSection.tables ?? []).map((t) => t.name))

function firstHeader(section: NoteSection, name: string): string | undefined {
  return (section.tables ?? []).find((t) => t.name === name)?.headers?.[0]
}

describe('K1 子表名 ↔ note_template 契约', () => {
  it.each(Object.entries(K1_LISTED_SUBTABLE))(
    '上市 %s → 「%s」存在于 §五、8',
    (_key, name) => {
      expect(listedNames.has(name)).toBe(true)
    },
  )

  it.each(Object.entries(K1_SOE_SUBTABLE))(
    '国企 %s → 「%s」存在于 §八、9',
    (_key, name) => {
      expect(soeNames.has(name)).toBe(true)
    },
  )
})

describe('附注 §五、8 / §八、9 结构要求', () => {
  it('两级表头表必须带 _column_groups', () => {
    const needGroups = [
      ...(listedSection.tables ?? []).filter((t) => t.name === '按款项性质披露'),
      ...(soeSection.tables ?? []).filter((t) => [
        '按账龄披露其他应收款项',
        '按坏账准备计提方法分类披露其他应收款项',
        '续：',
        '单项计提坏账准备的其他应收款项',
        '账龄组合',
        '采用余额百分比法或其他组合方法计提坏账准备的其他应收款项',
      ].includes(String(t.name))),
    ]
    expect(needGroups).toHaveLength(7)
    for (const t of needGroups) {
      expect(Array.isArray(t._column_groups), `${t.name} 缺 _column_groups`).toBe(true)
    }
  })

  it('headers 无空串（后端 CI 卡点同构校验）', () => {
    for (const section of [listedSection, soeSection]) {
      for (const t of section.tables ?? []) {
        for (const h of t.headers ?? []) {
          expect(String(h ?? '').trim()).not.toBe('')
        }
      }
    }
  })

  it('每张表都有 guidance（TAB 页签编制提示）', () => {
    for (const section of [listedSection, soeSection]) {
      const missing = (section.tables ?? [])
        .filter((t) => !String(t.guidance ?? '').trim())
        .map((t) => t.name)
      expect(missing, `缺 guidance: ${missing.join(' / ')}`).toHaveLength(0)
    }
  })

  it('同步 columns 的标签列头 = 附注 headers[0]（避免 TAB 首列名漂移）', () => {
    const mismatches: string[] = []
    for (const [section, columns] of [
      [listedSection, K1_LISTED_COLUMNS] as const,
      [soeSection, K1_SOE_COLUMNS] as const,
    ]) {
      for (const [name, cols] of Object.entries(columns)) {
        const expected = firstHeader(section, name)
        const actual = cols.find((c) => c.is_label)?.label
        if (expected !== actual) mismatches.push(`${name}: 附注「${expected}」vs 同步「${actual}」`)
      }
    }
    expect(mismatches, mismatches.join(' / ')).toHaveLength(0)
  })

  it('国企 §八、9 含账面余额变动 / 转移 / 继续涉入 / 政府补助四张表', () => {
    for (const name of [
      '其他应收款项账面余额变动',
      '由金融资产转移而终止确认的其他应收款项',
      '其他应收款项转移继续涉入形成的资产、负债的金额',
      '涉及政府补助的应收款项',
    ]) {
      expect(soeNames.has(name), `缺表 ${name}`).toBe(true)
    }
  })
})
