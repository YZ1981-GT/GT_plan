/**
 * n2NoteSectionMap 载荷构造 + 契约守卫
 *
 * Property 1  键集合三方相等（sub_table_data ≡ columns ≡ 子表名全集）
 * Property 2  子表名逐字取自附注模板，且章节存在
 * Property 3  **两版列结构本质不同不得共用**（上市 3 列双期 / 国企 5 列变动）
 * Property 5  sheet 名逐字取自 `workpaper_sheet_classification`
 * Property 6  每张表显式 `flat`（单级表头）
 * Property 7  行型判定先去空白（源模板写 `合  计`）
 * Property 8  缺失写 null 不写 0
 * Property 11 纯函数
 *
 * spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/` Task 8.1
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  N2_DISCLOSURE_SHEET_NAME,
  N2_NOTE_SECTION,
  N2_SUB_TABLE_KEYS,
  N2_TABLE_NAMESPACE,
  buildN2ListedColumns,
  buildN2NoteTexts,
  buildN2SoeColumns,
  buildN2SyncPayload,
  computeN2SoeEnd,
  isN2TotalLabel,
  normalizeN2RowLabel,
  resolveN2CurrentStandard,
  type N2DisclosureVariant,
  type N2ListedTaxRow,
  type N2SoeTaxRow,
} from '../n2NoteSectionMap'

const ROOT = resolve(__dirname, '../../../../../../../backend/data')

function readJson(name: string): any {
  return JSON.parse(readFileSync(resolve(ROOT, name), 'utf-8'))
}

const TEMPLATES: Record<N2DisclosureVariant, any> = {
  listed: readJson('note_template_listed.json'),
  soe: readJson('note_template_soe.json'),
}
const MATRIX = readJson('note_template_variant_matrix.json')
const VARIANTS: N2DisclosureVariant[] = ['listed', 'soe']

function sectionOf(variant: N2DisclosureVariant): any {
  const num = N2_NOTE_SECTION[variant]
  const s = (TEMPLATES[variant].sections || []).find((x: any) => x.section_number === num)
  expect(s, `${variant} 模板缺章节 ${num}`).toBeTruthy()
  return s
}

const CTX = { wpId: 'wp-n2', year: 2025 }

const listedRows: N2ListedTaxRow[] = [
  { item: '增值税', end: 100, prior: 60 },
  { item: '消费税', end: 50, prior: 40 },
]

const soeRows: N2SoeTaxRow[] = [
  { item: '增值税', opening: 100, payable: 80, paid: 30, end: 150 },
  { item: '消费税', opening: 20, payable: 10, paid: 5, end: 25 },
]

function snap(variant: N2DisclosureVariant, over: Record<string, unknown> = {}) {
  return { taxRows: variant === 'listed' ? listedRows : soeRows, ...over } as any
}

// ─── Property 1 / 2 ──────────────────────────────────────────────────────────

describe('Property 1/2 — 键集合与子表名', () => {
  it.each(VARIANTS)('%s: sub_table_data 键 ≡ columns 键 ≡ 子表名全集', (variant) => {
    const p = buildN2SyncPayload(variant, snap(variant), CTX)
    const dataKeys = Object.keys(p.sub_table_data).filter((k) => !k.startsWith('_'))
    expect(new Set(dataKeys)).toEqual(new Set(Object.keys(p.columns)))
    expect(new Set(dataKeys)).toEqual(new Set(Object.values(N2_SUB_TABLE_KEYS[variant])))
  })

  it.each(VARIANTS)('%s: 章节号与权威矩阵一致', (variant) => {
    const entry = (MATRIX.accounts || []).find((a: any) => a.account_key === 'ying_jiao_shui_fei')
    const key = variant === 'listed' ? 'listed_standalone' : 'soe_standalone'
    expect(N2_NOTE_SECTION[variant]).toBe(entry.variants[key])
  })

  it.each(VARIANTS)('%s: 子表名存在于附注模板且双向覆盖', (variant) => {
    const names = new Set((sectionOf(variant).tables || []).map((t: any) => t.name))
    const mapped = new Set(Object.values(N2_SUB_TABLE_KEYS[variant]) as string[])
    expect(mapped).toEqual(names)
  })

  it.each(VARIANTS)('%s: N2_TABLE_NAMESPACE 覆盖全部子表名', (variant) => {
    expect(new Set(N2_TABLE_NAMESPACE[variant].known)).toEqual(
      new Set(Object.values(N2_SUB_TABLE_KEYS[variant])),
    )
  })

  it.each(VARIANTS)('%s: 每行值列键均在 columns 内声明', (variant) => {
    const p = buildN2SyncPayload(variant, snap(variant), CTX)
    for (const [key, defs] of Object.entries(p.columns)) {
      const allowed = new Set([...defs.map((d) => d.key), 'label', 'is_total'])
      for (const row of p.sub_table_data[key] as Array<Record<string, unknown>>) {
        for (const k of Object.keys(row)) expect(allowed, `${variant}/${key}/${k}`).toContain(k)
      }
    }
  })
})

// ─── Property 3（核心）──────────────────────────────────────────────────────

describe('Property 3 — 两版列结构本质不同，不得共用', () => {
  it('上市 = 3 列双期余额表', () => {
    const defs = buildN2ListedColumns()[N2_SUB_TABLE_KEYS.listed.taxes]
    expect(defs.map((d) => d.label)).toEqual(['税项', '期末余额', '上年年末余额'])
  })

  it('国企 = 5 列变动表', () => {
    const defs = buildN2SoeColumns()[N2_SUB_TABLE_KEYS.soe.taxes]
    expect(defs.map((d) => d.label)).toEqual([
      '项目', '期初余额', '本期应交', '本期已交', '期末余额',
    ])
  })

  it('反向断言：两版列键集不等（防复制粘贴复发）', () => {
    const l = buildN2ListedColumns()[N2_SUB_TABLE_KEYS.listed.taxes].map((d) => d.key)
    const s = buildN2SoeColumns()[N2_SUB_TABLE_KEYS.soe.taxes].map((d) => d.key)
    expect(l).not.toEqual(s)
    expect(l.length).not.toBe(s.length)
    // 国企特有列绝不出现在上市侧
    expect(l).not.toContain('payable')
    expect(l).not.toContain('paid')
    // 上市特有列绝不出现在国企侧
    expect(s).not.toContain('prior')
  })

  it.each(VARIANTS)('%s: columns label 逐字对齐模板 headers', (variant) => {
    const p = buildN2SyncPayload(variant, snap(variant), CTX)
    for (const [key, defs] of Object.entries(p.columns)) {
      const t = (sectionOf(variant).tables || []).find((x: any) => x.name === key)
      expect(defs.map((d) => d.label), `${variant}/${key}`).toEqual(t.headers)
    }
  })
})

// ─── Property 5 / 6 ──────────────────────────────────────────────────────────

describe('Property 5/6 — sheet 名与表头形态', () => {
  it('sheet 名逐字（全角括号）', () => {
    expect(N2_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(N2_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
    expect(buildN2SyncPayload('soe', snap('soe'), CTX).sheet_name)
      .toBe(N2_DISCLOSURE_SHEET_NAME.soe)
  })

  it.each(VARIANTS)('%s: 每张表显式 flat 且无 group', (variant) => {
    const p = buildN2SyncPayload(variant, snap(variant), CTX)
    for (const [key, defs] of Object.entries(p.columns)) {
      expect(defs.some((d) => d.flat), `${key} 未表态 flat`).toBe(true)
      expect(defs.some((d) => d.group), `${key} 不应有 group`).toBe(false)
    }
  })

  it.each(VARIANTS)('%s: 恰有一个标签列', (variant) => {
    const p = buildN2SyncPayload(variant, snap(variant), CTX)
    for (const defs of Object.values(p.columns)) {
      expect(defs.filter((d) => d.is_label)).toHaveLength(1)
    }
  })
})

// ─── Property 7 ──────────────────────────────────────────────────────────────

describe('Property 7 — 行型判定先去空白', () => {
  it('normalizeN2RowLabel / isN2TotalLabel 认带空格的合计', () => {
    expect(normalizeN2RowLabel('合  计')).toBe('合计')
    expect(isN2TotalLabel('合  计')).toBe(true)
    expect(isN2TotalLabel('小  计')).toBe(true)
    expect(isN2TotalLabel('增值税')).toBe(false)
  })

  it.each(VARIANTS)('%s: 末行为合计且带 is_total', (variant) => {
    const rows = buildN2SyncPayload(variant, snap(variant), CTX)
      .sub_table_data[N2_SUB_TABLE_KEYS[variant].taxes] as any[]
    expect(rows[rows.length - 1].label).toBe('合计')
    expect(rows[rows.length - 1].is_total).toBe(true)
  })
})

// ─── Property 8 + 合计 + 国企公式 ────────────────────────────────────────────

describe('Property 8 — 缺失写 null；合计为逐项求和', () => {
  it('上市合计', () => {
    const rows = buildN2SyncPayload('listed', snap('listed'), CTX)
      .sub_table_data[N2_SUB_TABLE_KEYS.listed.taxes] as any[]
    expect(rows[rows.length - 1]).toMatchObject({ end: 150, prior: 100 })
  })

  it('国企四列合计', () => {
    const rows = buildN2SyncPayload('soe', snap('soe'), CTX)
      .sub_table_data[N2_SUB_TABLE_KEYS.soe.taxes] as any[]
    expect(rows[rows.length - 1]).toMatchObject({
      opening: 120, payable: 90, paid: 35, end: 175,
    })
  })

  it('全 null 时合计为 null（不塌 0）', () => {
    const rows = buildN2SyncPayload(
      'listed',
      { taxRows: [{ item: 'X', end: null, prior: null }] } as any,
      CTX,
    ).sub_table_data[N2_SUB_TABLE_KEYS.listed.taxes] as any[]
    expect(rows[rows.length - 1].end).toBeNull()
    expect(rows[rows.length - 1].prior).toBeNull()
  })

  it('computeN2SoeEnd 实现源模板 =B8+C8-D8；全 null → null', () => {
    expect(computeN2SoeEnd({ opening: 100, payable: 80, paid: 30 })).toBe(150)
    expect(computeN2SoeEnd({ opening: null, payable: null, paid: null })).toBeNull()
    // 部分缺失按 0 计（源模板空单元格参与算式），但不能整体塌成 null
    expect(computeN2SoeEnd({ opening: 100, payable: null, paid: null })).toBe(100)
  })
})

// ─── current_standard / notes / 纯函数 ───────────────────────────────────────

describe('current_standard 与文本', () => {
  it('按变体与适用准则解析', () => {
    expect(resolveN2CurrentStandard('listed')).toBe('listed_standalone')
    expect(resolveN2CurrentStandard('soe')).toBe('soe_standalone')
    expect(resolveN2CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveN2CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
  })

  it('year 恒等于 ctx.year', () => {
    expect(buildN2SyncPayload('listed', snap('listed'), { wpId: 'w', year: 2021 }).year).toBe(2021)
  })

  it('空文本不写 _note_texts；抵销说明排在结论前', () => {
    expect(buildN2SyncPayload('listed', snap('listed'), CTX).sub_table_data)
      .not.toHaveProperty('_note_texts')
    const blank = buildN2SyncPayload('listed', snap('listed', { notes: { conclusion: '  ' } }), CTX)
    expect(blank.sub_table_data).not.toHaveProperty('_note_texts')
    expect(buildN2NoteTexts({ conclusion: 'C', offset: 'O' }).map((t) => t.section)).toEqual([
      'n2-disclosure-offset',
      'n2-disclosure-conclusion',
    ])
  })
})

describe('Property 11 — 纯函数', () => {
  it.each(VARIANTS)('%s: 同输入深相等且不改入参', (variant) => {
    const s = snap(variant)
    const frozen = JSON.parse(JSON.stringify(s))
    const a = buildN2SyncPayload(variant, s, CTX)
    const b = buildN2SyncPayload(variant, s, CTX)
    expect(a).toEqual(b)
    expect(s).toEqual(frozen)
  })
})
