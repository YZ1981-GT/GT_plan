/**
 * H1 固定资产披露子表名 ↔ 附注模板契约
 *
 * 防回归：`H1_LISTED_SUBTABLE` / `H1_SOE_SUBTABLE` 的每个值必须能在
 * `note_template_listed.json` §五、22 / `note_template_soe.json` §八、22
 * 的 `tables[].name` 中找到，否则 sync-from-workpaper 会写出孤儿子表
 * （附注 TAB 永空 + 底稿数据丢失）。
 *
 * 同时锁定：同步 `columns` 的**全部列头**与附注 `headers` 逐字一致——
 * 上市「固定资产情况」的 `……` 占位列曾导致底稿推送的「办公设备 / 其他设备」
 * 两列在附注侧无落点。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  H1_LISTED_SUBTABLE,
  H1_NOTE_SECTION,
  H1_SOE_SUBTABLE,
} from '../h1NoteSectionMap'
import { H1_SOE_COLUMNS, buildH1ListedColumns } from '../h1DisclosureSyncPayload'
import {
  H1_LISTED_DEFAULT_CATEGORIES,
  createDefaultSummary,
  createDefaultIdleRows,
  createDefaultLeaseRows,
  createDefaultGovSubsidy,
} from '../h1ListedDisclosureModel'
import type { H1ListedSyncSnapshot } from '../h1DisclosureSyncPayload'

interface NoteTable { name?: string; headers?: string[]; guidance?: string; rows?: Array<{ label?: string }> }
interface NoteSection { section_number?: string; tables?: NoteTable[]; text_sections?: string[] }

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

function loadSection(file: string, sectionNumber: string): NoteSection {
  const path = resolve(REPO_ROOT, 'backend/data', file)
  const raw = JSON.parse(readFileSync(path, 'utf-8')) as { sections: NoteSection[] }
  const hit = raw.sections.find((s) => String(s.section_number ?? '').trim() === sectionNumber)
  if (!hit) throw new Error(`${file} 缺少章节 ${sectionNumber}`)
  return hit
}

const listedSection = loadSection('note_template_listed.json', H1_NOTE_SECTION.listed)
const soeSection = loadSection('note_template_soe.json', H1_NOTE_SECTION.soe)

const listedNames = new Set((listedSection.tables ?? []).map((t) => t.name))
const soeNames = new Set((soeSection.tables ?? []).map((t) => t.name))

function headersOf(section: NoteSection, name: string): string[] {
  return (section.tables ?? []).find((t) => t.name === name)?.headers ?? []
}

/** 默认快照：类别取 H1_LISTED_DEFAULT_CATEGORIES，与附注 headers 对齐口径一致 */
function defaultListedSnapshot(): H1ListedSyncSnapshot {
  return {
    summary: createDefaultSummary(),
    categories: H1_LISTED_DEFAULT_CATEGORIES.map((c) => ({ ...c })),
    movement: {},
    idle: createDefaultIdleRows(),
    leaseOut: createDefaultLeaseRows(),
    titleCert: [],
    clearing: [],
    govSubsidy: createDefaultGovSubsidy(),
    noteImpairment: '',
    noteMortgage: '',
    noteSale: '',
    noteClearing: '',
  }
}

describe('H1 子表名 ↔ note_template 契约', () => {
  it.each(Object.entries(H1_LISTED_SUBTABLE))(
    '上市 %s → 「%s」存在于 §五、22',
    (_key, name) => {
      expect(listedNames.has(name)).toBe(true)
    },
  )

  it.each(Object.entries(H1_SOE_SUBTABLE))(
    '国企 %s → 「%s」存在于 §八、22',
    (_key, name) => {
      expect(soeNames.has(name)).toBe(true)
    },
  )

  it('国企不含「通过经营租赁租出的固定资产」（源模板国企 sheet 无此段）', () => {
    expect(soeNames.has('通过经营租赁租出的固定资产')).toBe(false)
    expect(Object.values(H1_SOE_SUBTABLE)).not.toContain('通过经营租赁租出的固定资产')
  })
})

describe('附注 §五、22 / §八、22 结构要求', () => {
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

  it('无「可无限量添加行」占位假数据行', () => {
    const offenders: string[] = []
    for (const section of [listedSection, soeSection]) {
      for (const t of section.tables ?? []) {
        if ((t.rows ?? []).some((r) => String(r.label ?? '').trim() === '可无限量添加行')) {
          offenders.push(String(t.name))
        }
      }
    }
    expect(offenders, offenders.join(' / ')).toHaveLength(0)
  })
})

describe('同步 columns ↔ 附注 headers 逐字一致', () => {
  it('国企 5 张表全部列头对齐', () => {
    const mismatches: string[] = []
    for (const [name, cols] of Object.entries(H1_SOE_COLUMNS)) {
      const expected = headersOf(soeSection, name)
      const actual = cols.map((c) => c.label)
      if (JSON.stringify(expected) !== JSON.stringify(actual)) {
        mismatches.push(`${name}: 附注 ${JSON.stringify(expected)} vs 同步 ${JSON.stringify(actual)}`)
      }
    }
    expect(mismatches, mismatches.join(' / ')).toHaveLength(0)
  })

  it('上市 6 张表全部列头对齐（含固定资产情况的动态类别列）', () => {
    const columns = buildH1ListedColumns(defaultListedSnapshot())
    const mismatches: string[] = []
    for (const [name, cols] of Object.entries(columns)) {
      const expected = headersOf(listedSection, name)
      const actual = cols.map((c) => c.label)
      if (JSON.stringify(expected) !== JSON.stringify(actual)) {
        mismatches.push(`${name}: 附注 ${JSON.stringify(expected)} vs 同步 ${JSON.stringify(actual)}`)
      }
    }
    expect(mismatches, mismatches.join(' / ')).toHaveLength(0)
  })

  it('标签列 is_label 且 label = 附注 headers[0]', () => {
    const all: Array<[NoteSection, Record<string, Array<{ label: string; is_label?: boolean }>>]> = [
      [soeSection, H1_SOE_COLUMNS],
      [listedSection, buildH1ListedColumns(defaultListedSnapshot())],
    ]
    for (const [section, columns] of all) {
      for (const [name, cols] of Object.entries(columns)) {
        const labelCol = cols.find((c) => c.is_label)
        expect(labelCol, `${name} 缺 is_label 列`).toBeTruthy()
        expect(labelCol!.label).toBe(headersOf(section, name)[0])
      }
    }
  })
})
