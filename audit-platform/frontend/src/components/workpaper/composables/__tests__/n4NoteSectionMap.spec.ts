/**
 * n4NoteSectionMap 载荷构造 + 契约守卫
 *
 * Property 1  键集合三方相等（sub_table_data ≡ columns ≡ 子表名全集）
 * Property 2  子表名逐字取自附注模板，且章节存在
 * Property 4  **国企不产出载荷也不产出章节**（源模板 `附注披露信息：无`）
 * Property 5  sheet 名逐字
 * Property 6  显式 `flat`（单级表头）
 * Property 7  行型判定先去空白
 * Property 8  缺失写 null 不写 0
 * Property 11 纯函数
 *
 * spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/` Task 8.1
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  N4_DISCLOSURE_SHEET_NAME,
  N4_NOTE_SECTION,
  N4_SOE_NOT_APPLICABLE_REASON,
  N4_SUB_TABLE_KEYS,
  N4_TABLE_NAMESPACE,
  buildN4ListedColumns,
  buildN4NoteTexts,
  buildN4SyncPayload,
  isN4TotalLabel,
  n4ColumnsFor,
  normalizeN4RowLabel,
  resolveN4CurrentStandard,
  type N4TaxRow,
} from '../n4NoteSectionMap'

const ROOT = resolve(__dirname, '../../../../../../../backend/data')

function readJson(name: string): any {
  return JSON.parse(readFileSync(resolve(ROOT, name), 'utf-8'))
}

const LISTED = readJson('note_template_listed.json')
const SOE = readJson('note_template_soe.json')
const MATRIX = readJson('note_template_variant_matrix.json')

function listedSection(): any {
  const s = (LISTED.sections || []).find((x: any) => x.section_number === N4_NOTE_SECTION.listed)
  expect(s, `上市模板缺章节 ${N4_NOTE_SECTION.listed}`).toBeTruthy()
  return s
}

const CTX = { wpId: 'wp-n4', year: 2025 }
const ROWS: N4TaxRow[] = [
  { item: '城市维护建设税', current: 120, prior: 100 },
  { item: '印花税', current: 30, prior: 25 },
]
const KEY = N4_SUB_TABLE_KEYS.listed.taxes

function payload(over: Record<string, unknown> = {}) {
  return buildN4SyncPayload('listed', { taxRows: ROWS, ...over } as any, CTX)!
}

describe('Property 1/2 — 键集合与子表名', () => {
  it('sub_table_data 键 ≡ columns 键 ≡ 子表名全集', () => {
    const p = payload()
    const dataKeys = Object.keys(p.sub_table_data).filter((k) => !k.startsWith('_'))
    expect(new Set(dataKeys)).toEqual(new Set(Object.keys(p.columns)))
    expect(new Set(dataKeys)).toEqual(new Set([KEY]))
  })

  it('章节号与权威矩阵一致（上市有 / 国企为空）', () => {
    const entry = (MATRIX.accounts || []).find((a: any) => a.account_key === 'shui_jin_ji_fu_jia')
    expect(entry, '矩阵缺 shui_jin_ji_fu_jia').toBeTruthy()
    expect(N4_NOTE_SECTION.listed).toBe(entry.variants.listed_standalone)
    expect(entry.variants.soe_standalone ?? null).toBeNull()
    expect(entry.variants.soe_consolidated ?? null).toBeNull()
  })

  it('子表名与模板双向覆盖', () => {
    const names = new Set(listedSection().tables.map((t: any) => t.name))
    expect(names).toEqual(new Set([KEY]))
  })

  it('N4_TABLE_NAMESPACE 覆盖全部子表名', () => {
    expect(new Set(N4_TABLE_NAMESPACE.listed.known)).toEqual(new Set([KEY]))
  })

  it('每行值列键均在 columns 内声明', () => {
    const p = payload()
    const allowed = new Set([...p.columns[KEY].map((d) => d.key), 'label', 'is_total'])
    for (const row of p.sub_table_data[KEY] as Array<Record<string, unknown>>) {
      for (const k of Object.keys(row)) expect(allowed, k).toContain(k)
    }
  })
})

// ─── Property 4（核心）──────────────────────────────────────────────────────

describe('Property 4 — 国企不适用', () => {
  it('buildN4SyncPayload(soe) 恒返回 null', () => {
    expect(buildN4SyncPayload('soe', { taxRows: ROWS }, CTX)).toBeNull()
    expect(buildN4SyncPayload('soe', { taxRows: [] }, CTX)).toBeNull()
  })

  it('N4_NOTE_SECTION.soe 为 null', () => {
    expect(N4_NOTE_SECTION.soe).toBeNull()
  })

  it('n4ColumnsFor(soe) 为空（无列定义）', () => {
    expect(n4ColumnsFor('soe')).toEqual({})
    expect(Object.keys(n4ColumnsFor('listed'))).toEqual([KEY])
  })

  it('国企模板不含税金及附加章节（禁"补齐"）', () => {
    const hit = (SOE.sections || []).filter((s: any) =>
      String(s.section_title ?? '').includes('税金及附加'),
    )
    expect(hit.map((s: any) => s.section_number)).toEqual([])
  })

  it('不适用原因写明源模板依据（不得改写成"功能未做"）', () => {
    expect(N4_SOE_NOT_APPLICABLE_REASON).toContain('附注披露信息：无')
    expect(N4_SOE_NOT_APPLICABLE_REASON).toContain('国有企业')
  })
})

// ─── Property 5 / 6 ──────────────────────────────────────────────────────────

describe('Property 5/6 — sheet 名与表头形态', () => {
  it('sheet 名逐字（全角括号）', () => {
    expect(N4_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(N4_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
    expect(payload().sheet_name).toBe(N4_DISCLOSURE_SHEET_NAME.listed)
  })

  it('显式 flat 且无 group；恰一个标签列', () => {
    const defs = buildN4ListedColumns()[KEY]
    expect(defs.some((d) => d.flat)).toBe(true)
    expect(defs.some((d) => d.group)).toBe(false)
    expect(defs.filter((d) => d.is_label)).toHaveLength(1)
  })

  it('columns label 逐字对齐模板 headers（3 列，非自造 6 列）', () => {
    const t = listedSection().tables.find((x: any) => x.name === KEY)
    expect(buildN4ListedColumns()[KEY].map((d) => d.label)).toEqual(t.headers)
    expect(t.headers).toEqual(['项目', '本期发生额', '上期发生额'])
  })

  it('反向断言：不得出现自造的变动分析列', () => {
    const keys = buildN4ListedColumns()[KEY].map((d) => d.key)
    for (const bad of ['change', 'changeAmount', 'changeRate', 'reason']) {
      expect(keys).not.toContain(bad)
    }
    expect(keys).toHaveLength(3)
  })
})

// ─── Property 7 / 8 ──────────────────────────────────────────────────────────

describe('Property 7/8 — 行型与空值', () => {
  it('normalizeN4RowLabel / isN4TotalLabel 认带空格的合计', () => {
    expect(normalizeN4RowLabel('合  计')).toBe('合计')
    expect(isN4TotalLabel('合  计')).toBe(true)
    expect(isN4TotalLabel('小  计')).toBe(true)
    expect(isN4TotalLabel('印花税')).toBe(false)
  })

  it('末行为合计且带 is_total，金额为逐项求和', () => {
    const rows = payload().sub_table_data[KEY] as any[]
    expect(rows[rows.length - 1]).toMatchObject({
      label: '合计', current: 150, prior: 125, is_total: true,
    })
  })

  it('全 null 时合计为 null（不塌 0）', () => {
    const rows = buildN4SyncPayload(
      'listed',
      { taxRows: [{ item: 'X', current: null, prior: null }] },
      CTX,
    )!.sub_table_data[KEY] as any[]
    expect(rows[rows.length - 1].current).toBeNull()
    expect(rows[rows.length - 1].prior).toBeNull()
  })
})

// ─── current_standard / 文本 / 纯函数 ────────────────────────────────────────

describe('current_standard 与文本', () => {
  it('按适用准则解析（只有上市两态）', () => {
    expect(resolveN4CurrentStandard()).toBe('listed_standalone')
    expect(resolveN4CurrentStandard(['listed_consolidated'])).toBe('listed_consolidated')
  })

  it('year 恒等于 ctx.year', () => {
    expect(buildN4SyncPayload('listed', { taxRows: ROWS }, { wpId: 'w', year: 2019 })!.year).toBe(2019)
  })

  it('空文本不写 _note_texts；计缴标准说明排在结论前', () => {
    expect(payload().sub_table_data).not.toHaveProperty('_note_texts')
    expect(payload({ notes: { conclusion: '   ' } }).sub_table_data).not.toHaveProperty('_note_texts')
    expect(buildN4NoteTexts({ conclusion: 'C', standard: 'S' }).map((t) => t.section)).toEqual([
      'n4-disclosure-standard',
      'n4-disclosure-conclusion',
    ])
  })

  it('_note_texts 每条带中文 title（防附注渲染英文键）', () => {
    for (const t of buildN4NoteTexts({ standard: 'S', conclusion: 'C' })) {
      expect(t.title).toBeTruthy()
      expect(/^[a-z-]+$/.test(t.title)).toBe(false)
    }
  })
})

describe('Property 11 — 纯函数', () => {
  it('同输入深相等且不改入参', () => {
    const snap = { taxRows: ROWS }
    const frozen = JSON.parse(JSON.stringify(snap))
    expect(buildN4SyncPayload('listed', snap, CTX)).toEqual(buildN4SyncPayload('listed', snap, CTX))
    expect(snap).toEqual(frozen)
  })
})
