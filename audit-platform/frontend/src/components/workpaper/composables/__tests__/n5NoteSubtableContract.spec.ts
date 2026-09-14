/**
 * N5 披露子表 ↔ note_template 契约
 *
 * 共享 helper 6 条 Property + N5 专属：
 * - P7 双向键集
 * - P8 全表 guidance
 * - P9 **同章节表名唯一**（本 spec 的核心修复：两版原各自重名会丢整表）
 * - P10 同步 columns ↔ 模板 columns 同形
 * - P11 旧键锁在 `N5_LEGACY_OBSOLETE_TABLES`（不得当成现役表名）
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
  N5_LEGACY_OBSOLETE_TABLES,
  N5_NOTE_SECTION,
  N5_SUB_TABLE_KEYS,
  buildN5ListedColumns,
  buildN5SoeColumns,
  type N5DisclosureVariant,
} from '../n5NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'N5',
  variants: [
    {
      variant: 'listed',
      section: N5_NOTE_SECTION.listed,
      subtables: N5_SUB_TABLE_KEYS.listed,
      columns: buildN5ListedColumns(),
    },
    {
      variant: 'soe',
      section: N5_NOTE_SECTION.soe,
      subtables: N5_SUB_TABLE_KEYS.soe,
      columns: buildN5SoeColumns(),
    },
  ],
})

const ROOT = resolve(__dirname, '../../../../../../../backend/data')
const VARIANTS: N5DisclosureVariant[] = ['listed', 'soe']
const COLUMNS = { listed: buildN5ListedColumns(), soe: buildN5SoeColumns() } as const

function loadSection(variant: N5DisclosureVariant): any {
  const file = variant === 'listed' ? 'note_template_listed.json' : 'note_template_soe.json'
  const raw = JSON.parse(readFileSync(resolve(ROOT, file), 'utf-8'))
  const sec = (raw.sections || []).find(
    (s: any) => s.section_number === N5_NOTE_SECTION[variant],
  )
  expect(sec, `${variant} 缺章节 ${N5_NOTE_SECTION[variant]}`).toBeTruthy()
  return sec
}

describe('N5 披露子表专属契约', () => {
  it.each(VARIANTS)('P7 %s 模板表名与映射值双向覆盖', (variant) => {
    const templateNames = new Set(loadSection(variant).tables.map((t: any) => t.name))
    const mapped = new Set(Object.values(N5_SUB_TABLE_KEYS[variant]) as string[])
    expect([...templateNames].filter((n) => !mapped.has(n as string))).toEqual([])
    expect([...mapped].filter((n) => !templateNames.has(n))).toEqual([])
  })

  it.each(VARIANTS)('P8 %s 全部表有 guidance', (variant) => {
    const missing = loadSection(variant)
      .tables.filter((t: any) => !String(t.guidance ?? '').trim())
      .map((t: any) => t.name)
    expect(missing).toEqual([])
  })

  it.each(VARIANTS)('P9 %s 同章节表名唯一（本 spec 核心修复）', (variant) => {
    const names = loadSection(variant).tables.map((t: any) => t.name)
    expect(new Set(names).size, `重名表：${names.join(' | ')}`).toBe(names.length)
    expect(names).toHaveLength(2)
  })

  it.each(VARIANTS)('P10 %s 同步 columns 与模板 columns 的 label/key 一致', (variant) => {
    for (const t of loadSection(variant).tables) {
      const defs = COLUMNS[variant][t.name]
      expect(defs, `缺 ${t.name} 的列定义`).toBeTruthy()
      expect(defs.map((d) => d.label), `${t.name} label`).toEqual(
        t.columns.map((c: any) => c.label),
      )
      expect(defs.map((d) => d.key), `${t.name} key`).toEqual(t.columns.map((c: any) => c.key))
      expect(columnDeclState(defs), `${t.name} 表态`).toBe(columnDeclState(t.columns))
    }
  })

  it('P11 旧键只能出现在 legacyObsolete，不得成为现役表名', () => {
    for (const variant of VARIANTS) {
      const live = new Set(Object.values(N5_SUB_TABLE_KEYS[variant]) as string[])
      for (const legacy of N5_LEGACY_OBSOLETE_TABLES[variant]) {
        expect(live.has(legacy), `${legacy} 既是旧键又是现役表名`).toBe(false)
        // 模板里也不得残留
        const names = loadSection(variant).tables.map((t: any) => t.name)
        expect(names).not.toContain(legacy)
      }
    }
    expect(N5_LEGACY_OBSOLETE_TABLES.listed).toContain('项  目')
  })

  it('P11 表（2）名不是章节名泄漏值（soe 原为 `所得税费用`）', () => {
    expect(N5_SUB_TABLE_KEYS.soe.reconcile).not.toBe(N5_SUB_TABLE_KEYS.soe.detail)
    expect(N5_SUB_TABLE_KEYS.listed.reconcile).not.toBe(N5_SUB_TABLE_KEYS.listed.detail)
  })
})
