/**
 * G7 长期股权投资 披露载荷契约守卫（上市 §五、18 / 国企 §八、18）。
 *
 * 复用共享 helper P1~P6：子表名逐字一致 / 章节号存在 / group·flat 必表态 /
 * 标签纯文本 / 标签列头对齐 headers[0] / 模板 headers 纯文本。
 *
 * G7 的披露模型跨多章节（上市 五、18 + 七、1；国企 八、18 + 七、*），
 * 本契约只覆盖**主章节**（五、18 / 八、18）里的表 —— 对应 G7_NOTE_SECTION 声明值。
 * 跨章表（七、1 / 七、*）的子表名验证在后端 `test_note_g7_structure.py` 三向比对中覆盖。
 *
 * 🔴 buildG7ListedColumns / buildG7SoeColumns 必须零入参可调（coverage sweep 空入参调用）。
 *
 * **Validates: Requirements 10.2**
 * **Properties: 8, 9**
 *
 * spec: g7-four-table-extraction-and-disclosure-alignment (Task 6.4)
 */
import { describe, expect, it } from 'vitest'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import { G7_NOTE_SECTION } from '../g7NoteSectionMap'
import {
  G7_LISTED_DISCLOSURE_SECTIONS,
  buildG7ListedColumns,
} from '../../g7-long-term-equity-main/disclosure/g7ListedDisclosureModel'
import {
  G7_SOE_DISCLOSURE_SECTIONS,
  buildG7SoeColumns,
} from '../../g7-long-term-equity-main/disclosure/g7SoeDisclosureModel'

// ─── 从 sections 定义中导出子表名映射，只包含目标章节的表 ────────────────────

interface SectionLike {
  noteSectionId: string
  tables?: readonly { id: string; templateTableKey?: string; title: string }[]
}

function buildSubtableMapForSection(
  sections: readonly SectionLike[],
  targetSectionId: string,
): Record<string, string> {
  const map: Record<string, string> = {}
  for (const section of sections) {
    if (section.noteSectionId !== targetSectionId) continue
    for (const table of section.tables ?? []) {
      const key = table.templateTableKey ?? table.title
      map[table.id] = key
    }
  }
  return map
}

function buildColumnsForSection(
  allColumns: Record<string, unknown[]>,
  subtableMap: Record<string, string>,
): Record<string, unknown[]> {
  const result: Record<string, unknown[]> = {}
  for (const name of Object.values(subtableMap)) {
    if (allColumns[name]) {
      result[name] = allColumns[name]
    }
  }
  return result
}

const G7_LISTED_SUBTABLE = buildSubtableMapForSection(
  G7_LISTED_DISCLOSURE_SECTIONS as unknown as SectionLike[],
  G7_NOTE_SECTION.listed,
)

const G7_SOE_SUBTABLE = buildSubtableMapForSection(
  G7_SOE_DISCLOSURE_SECTIONS as unknown as SectionLike[],
  G7_NOTE_SECTION.soe,
)

const listedAllColumns = buildG7ListedColumns()
const soeAllColumns = buildG7SoeColumns()

const listedColumns = buildColumnsForSection(listedAllColumns as Record<string, unknown[]>, G7_LISTED_SUBTABLE)
const soeColumns = buildColumnsForSection(soeAllColumns as Record<string, unknown[]>, G7_SOE_SUBTABLE)

// ─── 共享 helper P1~P6（只对主章节的表跑） ──────────────────────────────────

runDisclosureSubtableContract({
  cycle: 'G7',
  variants: [
    {
      variant: 'listed',
      section: G7_NOTE_SECTION.listed,
      subtables: G7_LISTED_SUBTABLE,
      columns: listedColumns as any,
    },
    {
      variant: 'soe',
      section: G7_NOTE_SECTION.soe,
      subtables: G7_SOE_SUBTABLE,
      columns: soeColumns as any,
    },
  ],
})

// ─── G7 专属补充断言 ────────────────────────────────────────────────────────

describe('G7 专属契约补充', () => {
  it('buildG7ListedColumns 零入参可调且返回非空', () => {
    const cols = buildG7ListedColumns()
    expect(Object.keys(cols).length).toBeGreaterThan(0)
    // 每张表都有列定义
    for (const [name, defs] of Object.entries(cols)) {
      expect(defs.length, `${name} 列定义为空`).toBeGreaterThan(0)
    }
  })

  it('buildG7SoeColumns 零入参可调且返回非空', () => {
    const cols = buildG7SoeColumns()
    expect(Object.keys(cols).length).toBeGreaterThan(0)
    for (const [name, defs] of Object.entries(cols)) {
      expect(defs.length, `${name} 列定义为空`).toBeGreaterThan(0)
    }
  })

  it('上市主章节 subtable 映射非空', () => {
    expect(Object.keys(G7_LISTED_SUBTABLE).length).toBeGreaterThan(0)
  })

  it('国企主章节 subtable 映射非空', () => {
    expect(Object.keys(G7_SOE_SUBTABLE).length).toBeGreaterThan(0)
  })

  it('列集键集覆盖主章节 subtable 映射（无孤儿列定义）', () => {
    const listedSubNames = new Set(Object.values(G7_LISTED_SUBTABLE))
    const listedColNames = new Set(Object.keys(listedColumns))
    // columns 键应覆盖 subtable 映射值
    const missing = [...listedSubNames].filter(n => !listedColNames.has(n))
    expect(missing, '上市主章节 subtable 在列定义中缺失').toEqual([])

    const soeSubNames = new Set(Object.values(G7_SOE_SUBTABLE))
    const soeColNames = new Set(Object.keys(soeColumns))
    const soeMissing = [...soeSubNames].filter(n => !soeColNames.has(n))
    expect(soeMissing, '国企主章节 subtable 在列定义中缺失').toEqual([])
  })
})
