/**
 * N 类附注子表契约守卫（N1 + N2 + N4 + N5 共 16 张表）
 *
 * Property 1: 子表名存在于附注模板 _tables[].name
 * Property 2: 每张表列定义 ≥2 列且含 label 列
 * Property 3: flat/group 必须表态（无 flat 也无 group 的列 ≠ label 列即违规）
 * Property 4: 标签列 label 纯文本（无 HTML）
 * Property 5: 列 key 不含空格/特殊字符
 *
 * Requirements: n-cycle-note-template-and-disclosure-completion 4.2
 */
import { resolve } from 'path'
import { readFileSync } from 'fs'
import { describe, it, expect } from 'vitest'

import { buildN1ListedColumns, buildN1SoeColumns } from '../n1NoteSectionMap'
import { buildN2ListedColumns, buildN2SoeColumns } from '../n2NoteSectionMap'
import { buildN4ListedColumns } from '../n4NoteSectionMap'
import { buildN5ListedColumns, buildN5SoeColumns } from '../n5NoteSectionMap'

const ROOT = resolve(__dirname, '../../../../../../../backend/data')

function loadTemplate(variant: 'listed' | 'soe') {
  const fname = variant === 'listed' ? 'note_template_listed.json' : 'note_template_soe.json'
  const raw = JSON.parse(readFileSync(resolve(ROOT, fname), 'utf-8'))
  return (raw.sections || raw) as Array<Record<string, any>>
}

function findSection(sections: Array<Record<string, any>>, sn: string) {
  return sections.find((s) => s.section_number === sn)
}

type ColumnDef = { key: string; label: string; flat?: boolean; group?: string; is_label?: boolean }

// ─── 收集所有 N 类列定义 ────────────────────────────────────────────────────

interface TableSpec {
  variant: 'listed' | 'soe'
  sectionNumber: string
  tableName: string
  columns: ColumnDef[]
}

function collectAllTables(): TableSpec[] {
  const specs: TableSpec[] = []

  // N1
  for (const [tableName, cols] of Object.entries(buildN1ListedColumns())) {
    specs.push({ variant: 'listed', sectionNumber: '五、30', tableName, columns: cols as ColumnDef[] })
  }
  for (const [tableName, cols] of Object.entries(buildN1SoeColumns())) {
    specs.push({ variant: 'soe', sectionNumber: '八、31', tableName, columns: cols as ColumnDef[] })
  }

  // N2
  for (const [tableName, cols] of Object.entries(buildN2ListedColumns())) {
    specs.push({ variant: 'listed', sectionNumber: '五、41', tableName, columns: cols as ColumnDef[] })
  }
  for (const [tableName, cols] of Object.entries(buildN2SoeColumns())) {
    specs.push({ variant: 'soe', sectionNumber: '八、41', tableName, columns: cols as ColumnDef[] })
  }

  // N4 (仅上市)
  for (const [tableName, cols] of Object.entries(buildN4ListedColumns())) {
    specs.push({ variant: 'listed', sectionNumber: '五、63', tableName, columns: cols as ColumnDef[] })
  }

  // N5
  for (const [tableName, cols] of Object.entries(buildN5ListedColumns())) {
    specs.push({ variant: 'listed', sectionNumber: '三、所得税费用', tableName, columns: cols as ColumnDef[] })
  }
  for (const [tableName, cols] of Object.entries(buildN5SoeColumns())) {
    specs.push({ variant: 'soe', sectionNumber: '八、78', tableName, columns: cols as ColumnDef[] })
  }

  return specs
}

const ALL_TABLES = collectAllTables()

// ─── 反向自检 ───────────────────────────────────────────────────────────────

describe('nCycleNoteSubtableContract 反向自检', () => {
  it('收集到 16 张表', () => {
    expect(ALL_TABLES.length).toBe(16)
  })
})

// ─── Property 1: 子表名存在于模板 ──────────────────────────────────────────

describe('P1 子表名存在于附注模板', () => {
  for (const spec of ALL_TABLES) {
    it(`${spec.sectionNumber}/${spec.tableName}`, () => {
      const sections = loadTemplate(spec.variant)
      const sec = findSection(sections, spec.sectionNumber)
      expect(sec).toBeDefined()
      const tables = (sec!._tables || []) as Array<{ name: string }>
      const names = tables.map((t) => t.name)
      expect(names).toContain(spec.tableName)
    })
  }
})

// ─── Property 2: 列定义 ≥2 列且含 label ───────────────────────────────────

describe('P2 列定义完整', () => {
  for (const spec of ALL_TABLES) {
    it(`${spec.sectionNumber}/${spec.tableName} 至少 2 列`, () => {
      expect(spec.columns.length).toBeGreaterThanOrEqual(2)
    })
    it(`${spec.sectionNumber}/${spec.tableName} 含 label 列`, () => {
      const hasLabel = spec.columns.some((c) => c.key === 'label' || c.is_label)
      expect(hasLabel).toBe(true)
    })
  }
})

// ─── Property 3: flat/group 必须表态 ───────────────────────────────────────

describe('P3 flat/group 表态', () => {
  for (const spec of ALL_TABLES) {
    it(`${spec.sectionNumber}/${spec.tableName}`, () => {
      const nonLabel = spec.columns.filter((c) => !c.is_label && c.key !== 'label')
      for (const col of nonLabel) {
        const hasFlat = col.flat === true || spec.columns.some((c) => c.flat)
        const hasGroup = !!col.group
        // 标签列带 flat 即整表 flat；否则非标签列必须有 group
        expect(
          hasFlat || hasGroup,
          `${spec.tableName} 列 ${col.key} 既无 flat 也无 group`,
        ).toBe(true)
      }
    })
  }
})

// ─── Property 4: label 纯文本 ──────────────────────────────────────────────

describe('P4 label 纯文本', () => {
  for (const spec of ALL_TABLES) {
    it(`${spec.sectionNumber}/${spec.tableName}`, () => {
      for (const col of spec.columns) {
        expect(col.label).not.toMatch(/<[^>]+>/)
      }
    })
  }
})

// ─── Property 5: key 合法 ──────────────────────────────────────────────────

describe('P5 key 合法', () => {
  for (const spec of ALL_TABLES) {
    it(`${spec.sectionNumber}/${spec.tableName}`, () => {
      for (const col of spec.columns) {
        expect(col.key).toMatch(/^[a-z_][a-z0-9_]*$/)
      }
    })
  }
})
