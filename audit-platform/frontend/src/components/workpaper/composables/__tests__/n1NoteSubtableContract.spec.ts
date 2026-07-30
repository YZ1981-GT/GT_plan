/**
 * N1 披露子表 ↔ note_template 契约
 *
 * 接共享 helper 的 5 条 Property（子表名逐字 / 章节号存在 / group·flat 表态 /
 * 标签纯文本 / 标签列头对齐 headers[0]），并补 N1 专属断言：
 *
 * - P6 双向键集：模板表名 ⊆ 映射值 且 映射值 ⊆ 模板表名（无孤儿、无遗漏）
 * - P7 全表有 `guidance`（TAB 页签编制提示）
 * - P8 headers 无空串 / 两级表 `_column_groups` 齐备且不越界
 * - P9 表 1 两版子列序相反（源模板 B11:E11），且 `columns` 键序跟随
 * - P10 `columns` 与模板 `columns` 的 label 序列逐字一致（同步 ↔ seed 双路径同形）
 *
 * spec: `.kiro/specs/n1-deferred-tax-disclosure-template-alignment/` R6
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  runDisclosureSubtableContract,
  columnDeclState,
} from './_disclosureSubtableContract.helper'
import {
  N1_NOTE_SECTION,
  N1_SUB_TABLE_KEYS,
  buildN1ListedColumns,
  buildN1SoeColumns,
  n1UnoffsetSubOrder,
  type N1DisclosureVariant,
} from '../n1NoteSectionMap'

// ─── 共享 helper 的 5 条 Property ────────────────────────────────────────────

runDisclosureSubtableContract({
  cycle: 'N1',
  variants: [
    {
      variant: 'listed',
      section: N1_NOTE_SECTION.listed,
      subtables: N1_SUB_TABLE_KEYS.listed,
      columns: buildN1ListedColumns(),
    },
    {
      variant: 'soe',
      section: N1_NOTE_SECTION.soe,
      subtables: N1_SUB_TABLE_KEYS.soe,
      columns: buildN1SoeColumns(),
    },
  ],
})

// ─── N1 专属断言 ─────────────────────────────────────────────────────────────

const ROOT = resolve(__dirname, '../../../../../../../backend/data')

function loadSection(variant: N1DisclosureVariant): any {
  const file = variant === 'listed' ? 'note_template_listed.json' : 'note_template_soe.json'
  const raw = JSON.parse(readFileSync(resolve(ROOT, file), 'utf-8'))
  const sec = (raw.sections || []).find(
    (s: any) => s.section_number === N1_NOTE_SECTION[variant],
  )
  expect(sec, `${variant} 缺章节 ${N1_NOTE_SECTION[variant]}`).toBeTruthy()
  return sec
}

const VARIANTS: N1DisclosureVariant[] = ['listed', 'soe']
const COLUMNS = { listed: buildN1ListedColumns(), soe: buildN1SoeColumns() } as const

describe('N1 披露子表专属契约', () => {
  // ── P6 双向键集 ──────────────────────────────────────────────────────────
  it.each(VARIANTS)('P6 %s 模板表名与映射值双向覆盖', (variant) => {
    const templateNames = new Set(loadSection(variant).tables.map((t: any) => t.name))
    const mapped = new Set(Object.values(N1_SUB_TABLE_KEYS[variant]) as string[])
    expect(
      [...templateNames].filter((n) => !mapped.has(n as string)),
      '模板有表但无映射 → 附注该 TAB 永远没人推送',
    ).toEqual([])
    expect(
      [...mapped].filter((n) => !templateNames.has(n)),
      '映射有表但模板无 → 同步产出孤儿子表',
    ).toEqual([])
  })

  // ── P7 guidance ─────────────────────────────────────────────────────────
  it.each(VARIANTS)('P7 %s 全部表有 guidance（TAB 编制提示）', (variant) => {
    const missing = loadSection(variant)
      .tables.filter((t: any) => !String(t.guidance ?? '').trim())
      .map((t: any) => t.name)
    expect(missing).toEqual([])
  })

  // ── P8 headers / _column_groups ─────────────────────────────────────────
  it.each(VARIANTS)('P8 %s headers 无空串且 _column_groups 合法', (variant) => {
    for (const t of loadSection(variant).tables) {
      expect(t.headers.every((h: string) => String(h).trim()), t.name).toBe(true)
      const groups = t._column_groups
      if (!groups) continue
      const occupied = new Set<number>()
      for (const g of groups) {
        expect(g.start, t.name).toBeGreaterThanOrEqual(1)
        expect(g.start + g.span, t.name).toBeLessThanOrEqual(t.headers.length)
        for (let i = g.start; i < g.start + g.span; i++) {
          expect(occupied.has(i), `${t.name} 分组重叠`).toBe(false)
          occupied.add(i)
        }
      }
    }
  })

  it('P8 表 1 两版都是 5 列两级（原被 md 抽取压扁成 3 列 + header_label 假数据行）', () => {
    for (const variant of VARIANTS) {
      const t = loadSection(variant).tables.find(
        (x: any) => x.name === N1_SUB_TABLE_KEYS[variant].unoffset,
      )
      expect(t.headers).toHaveLength(5)
      expect(t._column_groups).toHaveLength(2)
      expect(columnDeclState(t.columns)).toBe('group')
      expect(t.rows.some((r: any) => r.row_type === 'header_label')).toBe(false)
    }
  })

  it('P8 soe 表 2 是 5 列（原被压扁成 3 列）', () => {
    const t = loadSection('soe').tables.find(
      (x: any) => x.name === N1_SUB_TABLE_KEYS.soe.netOffset,
    )
    expect(t.headers).toHaveLength(5)
    expect(columnDeclState(t.columns)).toBe('flat')
  })

  it('P8 soe 有第 5 张表「互抵明细」（源模板（2）B，原整张缺失）', () => {
    const names = loadSection('soe').tables.map((t: any) => t.name)
    expect(names).toContain(N1_SUB_TABLE_KEYS.soe.offsetDetail)
    expect(loadSection('listed').tables.map((t: any) => t.name)).not.toContain(
      N1_SUB_TABLE_KEYS.soe.offsetDetail,
    )
  })

  // ── P9 子列序 ───────────────────────────────────────────────────────────
  it('P9 表 1 两版子列序相反，且模板 headers 与同步 columns 都跟随', () => {
    for (const variant of VARIANTS) {
      const order = n1UnoffsetSubOrder(variant).map(([, l]) => l)
      const t = loadSection(variant).tables.find(
        (x: any) => x.name === N1_SUB_TABLE_KEYS[variant].unoffset,
      )
      expect(t.headers.slice(1), `${variant} 模板 headers`).toEqual([...order, ...order])
      const defs = COLUMNS[variant][N1_SUB_TABLE_KEYS[variant].unoffset]
      expect(defs.slice(1).map((d) => d.label), `${variant} 同步 columns`).toEqual([
        ...order,
        ...order,
      ])
    }
    expect(n1UnoffsetSubOrder('listed')).not.toEqual(n1UnoffsetSubOrder('soe'))
  })

  // ── P10 同步 columns ↔ 模板 columns 同形 ────────────────────────────────
  it.each(VARIANTS)('P10 %s 同步 columns 与模板 columns 的 label/key 序列一致', (variant) => {
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
})
