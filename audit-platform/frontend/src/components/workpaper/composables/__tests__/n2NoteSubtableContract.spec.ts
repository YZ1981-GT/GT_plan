/**
 * N2 披露子表 ↔ note_template 契约
 *
 * 接共享 helper 的 6 条 Property（子表名逐字 / 章节号存在 / group·flat 表态 /
 * 标签纯文本 / 标签列头对齐 headers[0] / 模板 headers 纯文本），并补 N2 专属断言：
 *
 * - P7 双向键集：模板表名 ≡ 映射值（无孤儿、无遗漏）
 * - P8 全表有 `guidance`（TAB 页签编制提示）
 * - P9 同章节表名唯一（重名会让 `sub_table_data` 键互相覆盖丢表）
 * - P10 同步 `columns` 与模板 `columns` 的 label/key 序列逐字一致（同步 ↔ seed 双路径同形）
 * - P11 **两版列结构本质不同**：上市 3 列双期 / 国企 5 列变动（防复制粘贴复发）
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
  N2_NOTE_SECTION,
  N2_SUB_TABLE_KEYS,
  buildN2ListedColumns,
  buildN2SoeColumns,
  type N2DisclosureVariant,
} from '../n2NoteSectionMap'

runDisclosureSubtableContract({
  cycle: 'N2',
  variants: [
    {
      variant: 'listed',
      section: N2_NOTE_SECTION.listed,
      subtables: N2_SUB_TABLE_KEYS.listed,
      columns: buildN2ListedColumns(),
    },
    {
      variant: 'soe',
      section: N2_NOTE_SECTION.soe,
      subtables: N2_SUB_TABLE_KEYS.soe,
      columns: buildN2SoeColumns(),
    },
  ],
})

// ─── N2 专属断言 ─────────────────────────────────────────────────────────────

const ROOT = resolve(__dirname, '../../../../../../../backend/data')
const VARIANTS: N2DisclosureVariant[] = ['listed', 'soe']
const COLUMNS = { listed: buildN2ListedColumns(), soe: buildN2SoeColumns() } as const

function loadSection(variant: N2DisclosureVariant): any {
  const file = variant === 'listed' ? 'note_template_listed.json' : 'note_template_soe.json'
  const raw = JSON.parse(readFileSync(resolve(ROOT, file), 'utf-8'))
  const sec = (raw.sections || []).find(
    (s: any) => s.section_number === N2_NOTE_SECTION[variant],
  )
  expect(sec, `${variant} 缺章节 ${N2_NOTE_SECTION[variant]}`).toBeTruthy()
  return sec
}

describe('N2 披露子表专属契约', () => {
  it.each(VARIANTS)('P7 %s 模板表名与映射值双向覆盖', (variant) => {
    const templateNames = new Set(loadSection(variant).tables.map((t: any) => t.name))
    const mapped = new Set(Object.values(N2_SUB_TABLE_KEYS[variant]) as string[])
    expect(
      [...templateNames].filter((n) => !mapped.has(n as string)),
      '模板有表但无映射 → 附注该 TAB 永远没人推送',
    ).toEqual([])
    expect(
      [...mapped].filter((n) => !templateNames.has(n)),
      '映射有表但模板无 → 同步产出孤儿子表',
    ).toEqual([])
  })

  it.each(VARIANTS)('P8 %s 全部表有 guidance', (variant) => {
    const missing = loadSection(variant)
      .tables.filter((t: any) => !String(t.guidance ?? '').trim())
      .map((t: any) => t.name)
    expect(missing).toEqual([])
  })

  it.each(VARIANTS)('P9 %s 同章节表名唯一', (variant) => {
    const names = loadSection(variant).tables.map((t: any) => t.name)
    expect(new Set(names).size, `重名表：${names.join(' | ')}`).toBe(names.length)
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

  it('P11 两版列结构本质不同（上市 3 列双期 / 国企 5 列变动）', () => {
    const l = COLUMNS.listed[N2_SUB_TABLE_KEYS.listed.taxes]
    const s = COLUMNS.soe[N2_SUB_TABLE_KEYS.soe.taxes]
    expect(l).toHaveLength(3)
    expect(s).toHaveLength(5)
    expect(l.map((d) => d.key)).not.toEqual(s.map((d) => d.key))
    // 模板侧也必须分化 —— 若模板被"统一"回 3 列，同步会产出孤儿列
    expect(loadSection('listed').tables[0].headers).toHaveLength(3)
    expect(loadSection('soe').tables[0].headers).toHaveLength(5)
  })
})
