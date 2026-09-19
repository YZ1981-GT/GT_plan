/**
 * D1 应收票据披露子表 ↔ note_template 契约
 *
 * 接入共享 helper 的 5 条 Property（表名逐字 / 章节存在 / group·flat 表态 /
 * 标签纯文本 / 标签列头对齐 headers[0]），另加 D1 专属断言：
 *  - `group` 不得含 `/`（前端 activeTableColumns 只认扁平 {group,start,span}，树形会崩）
 *  - 双向键集：模板 `tables[].name` 全集 == 子表名映射全集（防漏推 / 防孤儿表）
 *  - 列头与模板 `headers` 逐位一致（seed 路径与同步路径必须同形）
 *
 * spec: .kiro/specs/d1-notes-receivable-disclosure-alignment/ Task 6.1
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import {
  D1_NOTE_SECTION,
  D1_LISTED_SUBTABLE,
  D1_SOE_SUBTABLE,
  buildD1ListedColumns,
  buildD1SoeColumns,
} from '../d1NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'D1',
  variants: [
    {
      variant: 'listed',
      section: D1_NOTE_SECTION.listed,
      subtables: D1_LISTED_SUBTABLE,
      columns: buildD1ListedColumns(),
    },
    {
      variant: 'soe',
      section: D1_NOTE_SECTION.soe,
      subtables: D1_SOE_SUBTABLE,
      columns: buildD1SoeColumns(),
    },
  ],
})

// ─── D1 专属断言 ─────────────────────────────────────────────────────────────

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

interface NoteTable { name?: string; headers?: string[] }

function loadTables(file: string, section: string): NoteTable[] {
  const path = resolve(REPO_ROOT, 'backend/data', file)
  const raw = JSON.parse(readFileSync(path, 'utf-8')) as {
    sections?: Array<{ section_number?: string; tables?: NoteTable[] }>
  }
  const sec = (raw.sections ?? []).find((s) => String(s.section_number ?? '') === section)
  return sec?.tables ?? []
}

const CASES = [
  {
    variant: 'listed' as const,
    file: 'note_template_listed.json',
    section: D1_NOTE_SECTION.listed,
    subtables: D1_LISTED_SUBTABLE as Readonly<Record<string, string>>,
    columns: buildD1ListedColumns(),
    tableCount: 14,
  },
  {
    variant: 'soe' as const,
    file: 'note_template_soe.json',
    section: D1_NOTE_SECTION.soe,
    subtables: D1_SOE_SUBTABLE as Readonly<Record<string, string>>,
    columns: buildD1SoeColumns(),
    tableCount: 12,
  },
]

describe('D1 披露子表 — D1 专属契约', () => {
  it.each(CASES)('$variant group 不含 "/"（多级会让前端 activeTableColumns 崩）', (c) => {
    const bad: string[] = []
    for (const [name, defs] of Object.entries(c.columns)) {
      for (const d of defs) {
        if (String(d.group ?? '').includes('/')) bad.push(`${name}.${d.key}=${d.group}`)
      }
    }
    expect(bad).toEqual([])
  })

  it.each(CASES)('$variant 模板表名全集 == 子表名映射全集（双向）', (c) => {
    const templateNames = loadTables(c.file, c.section).map((t) => String(t.name ?? ''))
    const mapped = Object.values(c.subtables)
    expect(templateNames).toHaveLength(c.tableCount)
    expect([...mapped].sort()).toEqual([...templateNames].sort())
  })

  it.each(CASES)('$variant 同步列头与模板 headers 逐位一致', (c) => {
    const byName = new Map(
      loadTables(c.file, c.section).map((t) => [String(t.name ?? ''), t.headers ?? []]),
    )
    const mismatches: string[] = []
    for (const name of Object.values(c.subtables)) {
      const defs = c.columns[name] ?? []
      const got = defs.map((d) => String(d.label ?? ''))
      const want = byName.get(name) ?? []
      if (JSON.stringify(got) !== JSON.stringify(want)) {
        mismatches.push(`${name}\n  同步=${JSON.stringify(got)}\n  模板=${JSON.stringify(want)}`)
      }
    }
    expect(
      mismatches,
      'seed 路径用模板 headers、同步路径用 columns.label 产出 headers，两者不一致会让'
        + '同一张附注表在「新建项目」与「同步后」显示不同表头',
    ).toEqual([])
  })

  it.each(CASES)('$variant 每张表的 group 分段与模板 _column_groups 同口径', (c) => {
    // 与后端 _extract_column_groups 单级分支 / 修订脚本 _derive_column_groups 同算法
    const derive = (defs: Array<{ group?: string }>) => {
      const out: Array<{ group: string; start: number; span: number }> = []
      let idx = 1
      for (const d of defs.slice(1)) {
        const g = d.group
        if (!g) { idx += 1; continue }
        const last = out[out.length - 1]
        if (last && last.group === g && last.start + last.span === idx) last.span += 1
        else out.push({ group: g, start: idx, span: 1 })
        idx += 1
      }
      return out
    }
    const path = resolve(REPO_ROOT, 'backend/data', c.file)
    const raw = JSON.parse(readFileSync(path, 'utf-8')) as {
      sections?: Array<{ section_number?: string; tables?: Array<Record<string, unknown>> }>
    }
    const tables = (raw.sections ?? []).find(
      (s) => String(s.section_number ?? '') === c.section,
    )?.tables ?? []
    const mismatches: string[] = []
    for (const t of tables) {
      const name = String(t.name ?? '')
      const defs = c.columns[name]
      if (!defs) continue
      const want = derive(defs)
      const got = (t._column_groups ?? null) as unknown
      const normalized = want.length > 0 ? want : null
      if (JSON.stringify(got ?? null) !== JSON.stringify(normalized)) {
        mismatches.push(`${name}: 模板=${JSON.stringify(got)} 同步派生=${JSON.stringify(normalized)}`)
      }
    }
    expect(mismatches).toEqual([])
  })
})
