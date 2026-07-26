/**
 * n1NoteSectionMap 载荷构造守卫（spec n1-disclosure-note-linkage）
 *
 * Property 1  章节号 = 权威矩阵（从 note_template_variant_matrix.json 读取比对）
 * Property 2  sub_table_data 键集合 === columns 键集合
 * Property 3  columns label 逐字对齐附注模板 tables[].headers
 * Property 4  year / current_standard 显式传递
 * Property 5  空文本不写 _note_texts
 * Property 9  只含 owner=N1 的四张子表键（不清空 N3 假想键 → 由浅合并语义保证）
 * Property 10 负债段缺失写 null 不写 0
 * Property 11 纯函数（同输入深相等）
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  N1_DISCLOSURE_SHEET_NAME,
  N1_NOTE_SECTION,
  N1_SUB_TABLE_KEYS,
  buildN1NoteTexts,
  buildN1SyncPayload,
  resolveN1CurrentStandard,
  type N1DisclosureSnapshot,
  type N1DisclosureVariant,
} from '../n1NoteSectionMap'

// ─── 权威数据加载（模板 / 矩阵）───────────────────────────────────────────────

const ROOT = resolve(__dirname, '../../../../../../../backend/data')

function readJson(name: string): any {
  return JSON.parse(readFileSync(resolve(ROOT, name), 'utf-8'))
}

const MATRIX = readJson('note_template_variant_matrix.json')
const TEMPLATES: Record<N1DisclosureVariant, any> = {
  listed: readJson('note_template_listed.json'),
  soe: readJson('note_template_soe.json'),
}

function sectionOf(variant: N1DisclosureVariant): any {
  const num = N1_NOTE_SECTION[variant]
  const s = (TEMPLATES[variant].sections || []).find((x: any) => x.section_number === num)
  expect(s, `${variant} 模板缺章节 ${num}`).toBeTruthy()
  return s
}

function tableOf(variant: N1DisclosureVariant, name: string): any {
  const t = (sectionOf(variant).tables || []).find((x: any) => x.name === name)
  expect(t, `${variant} 模板缺表 ${name}`).toBeTruthy()
  return t
}

// ─── fixtures ────────────────────────────────────────────────────────────────

function snapshot(over: Partial<N1DisclosureSnapshot> = {}): N1DisclosureSnapshot {
  return {
    assetRows: [
      { item: '资产减值准备', endBalance: 150_000, priorBalance: 100_000 },
      { item: '可抵扣亏损', endBalance: 50_000, priorBalance: 0 },
    ],
    unrecognizedRows: [
      { item: '可抵扣暂时性差异', amount: 200_000, priorAmount: 100_000 },
      { item: '可抵扣亏损', amount: 300_000, priorAmount: 0 },
    ],
    lossExpiryRows: [
      { expiryYear: '2027', unrecovered: 400_000 },
      { expiryYear: '2027', unrecovered: 100_000, remark: '分支机构' },
      { expiryYear: '2028', unrecovered: 250_000 },
    ],
    ...over,
  }
}

const CTX = { wpId: 'wp-n1', year: 2025 }

// ─── Property 1 ──────────────────────────────────────────────────────────────

describe('Property 1 — 章节号单一真源（权威矩阵）', () => {
  it('N1_NOTE_SECTION 与 note_template_variant_matrix 一致', () => {
    const entry = (MATRIX.accounts || []).find(
      (a: any) => a.account_key === 'di_yan_suo_de_shui_zi_chan_he_di_yan_suo_de',
    )
    expect(entry).toBeTruthy()
    expect(N1_NOTE_SECTION.listed).toBe(entry.variants.listed_standalone)
    expect(N1_NOTE_SECTION.soe).toBe(entry.variants.soe_standalone)
  })

  it('payload section_id 取自同一常量', () => {
    expect(buildN1SyncPayload('listed', snapshot(), CTX).section_id).toBe(N1_NOTE_SECTION.listed)
    expect(buildN1SyncPayload('soe', snapshot(), CTX).section_id).toBe(N1_NOTE_SECTION.soe)
  })

  it('sheet 名为底稿真实 tab 名（全角括号）', () => {
    expect(N1_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
    expect(N1_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企）')
    expect(buildN1SyncPayload('soe', snapshot(), CTX).sheet_name).toBe(N1_DISCLOSURE_SHEET_NAME.soe)
  })
})

// ─── Property 2 / 9 ──────────────────────────────────────────────────────────

describe('Property 2/9 — 键集合一致 + 仅推 owner=N1 的四张子表', () => {
  it.each<[N1DisclosureVariant]>([['listed'], ['soe']])('%s 变体键一致', (variant) => {
    const p = buildN1SyncPayload(variant, snapshot(), CTX)
    const dataKeys = Object.keys(p.sub_table_data).filter((k) => !k.startsWith('_'))
    expect(new Set(dataKeys)).toEqual(new Set(Object.keys(p.columns)))
    const K = N1_SUB_TABLE_KEYS[variant]
    expect(new Set(dataKeys)).toEqual(new Set([K.unoffset, K.netOffset, K.unrecognized, K.lossExpiry]))
  })

  it('四张子表名均存在于附注模板（不自造表名）', () => {
    for (const variant of ['listed', 'soe'] as N1DisclosureVariant[]) {
      const names = (sectionOf(variant).tables || []).map((t: any) => t.name)
      for (const key of Object.values(N1_SUB_TABLE_KEYS[variant])) {
        expect(names, `${variant} ${key}`).toContain(key)
      }
    }
  })

  it('每行值列键均在该表 columns 内声明（投影器不忽略数据）', () => {
    for (const variant of ['listed', 'soe'] as N1DisclosureVariant[]) {
      const p = buildN1SyncPayload(variant, snapshot(), CTX)
      for (const [key, defs] of Object.entries(p.columns)) {
        const allowed = new Set([...defs.map((d) => d.key), 'label', 'is_total'])
        for (const row of p.sub_table_data[key] as Array<Record<string, unknown>>) {
          for (const k of Object.keys(row)) expect(allowed, `${variant}/${key}/${k}`).toContain(k)
        }
      }
    }
  })
})

// ─── Property 3 ──────────────────────────────────────────────────────────────

describe('Property 3 — 列头逐字对齐模板 headers', () => {
  it.each<[N1DisclosureVariant]>([['listed'], ['soe']])('%s 变体列头对齐', (variant) => {
    const p = buildN1SyncPayload(variant, snapshot(), CTX)
    for (const [key, defs] of Object.entries(p.columns)) {
      expect(defs.map((d) => d.label), `${variant}/${key}`).toEqual(tableOf(variant, key).headers)
    }
  })

  it('soe 抵销后净额表只有 3 列（与 listed 5 列结构本质不同）', () => {
    expect(buildN1SyncPayload('soe', snapshot(), CTX).columns[N1_SUB_TABLE_KEYS.soe.netOffset]).toHaveLength(3)
    expect(buildN1SyncPayload('listed', snapshot(), CTX).columns[N1_SUB_TABLE_KEYS.listed.netOffset]).toHaveLength(5)
  })

  it('每张表恰有一个标签列', () => {
    for (const variant of ['listed', 'soe'] as N1DisclosureVariant[]) {
      const p = buildN1SyncPayload(variant, snapshot(), CTX)
      for (const defs of Object.values(p.columns)) {
        expect(defs.filter((d) => d.is_label)).toHaveLength(1)
      }
    }
  })
})

// ─── Property 4 ──────────────────────────────────────────────────────────────

describe('Property 4 — year / current_standard 显式传递', () => {
  it('year 恒等于 ctx.year（不回退当前自然年）', () => {
    expect(buildN1SyncPayload('listed', snapshot(), { wpId: 'w', year: 2021 }).year).toBe(2021)
  })

  it('current_standard 按变体与适用准则解析', () => {
    expect(resolveN1CurrentStandard('listed')).toBe('listed_standalone')
    expect(resolveN1CurrentStandard('soe')).toBe('soe_standalone')
    expect(resolveN1CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveN1CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
    expect(buildN1SyncPayload('soe', snapshot(), CTX).current_standard).toBe('soe_standalone')
  })
})

// ─── Property 5 ──────────────────────────────────────────────────────────────

describe('Property 5 — 空文本不写 _note_texts', () => {
  it('无 notes / 全空串 → 不含 _note_texts 键', () => {
    expect(buildN1SyncPayload('listed', snapshot(), CTX).sub_table_data).not.toHaveProperty('_note_texts')
    const blank = buildN1SyncPayload('listed', snapshot({ notes: { conclusion: '  ', sufficiency: '' } }), CTX)
    expect(blank.sub_table_data).not.toHaveProperty('_note_texts')
  })

  it('有文本 → 按子节产出 {section,title,text}，跳过空串', () => {
    const p = buildN1SyncPayload('soe', snapshot({ notes: { conclusion: '结论X', sufficiency: '' } }), CTX)
    expect(p.sub_table_data._note_texts).toEqual([
      { section: 'n1-disclosure-conclusion', title: '披露说明与结论', text: '结论X' },
    ])
  })

  it('buildN1NoteTexts 无输入返回空数组', () => {
    expect(buildN1NoteTexts()).toEqual([])
    expect(buildN1NoteTexts({})).toEqual([])
  })
})

// ─── Property 10 ─────────────────────────────────────────────────────────────

describe('Property 10 — 缺失写 null 不写 0', () => {
  it('负债段无数据 → 负债小计为 null（不是 0）', () => {
    const p = buildN1SyncPayload('listed', snapshot(), CTX)
    const rows = p.sub_table_data[N1_SUB_TABLE_KEYS.listed.unoffset] as any[]
    const liabSubtotal = rows[rows.length - 1]
    expect(liabSubtotal.is_total).toBe(true)
    expect(liabSubtotal.end).toBeNull()
    expect(liabSubtotal.prior).toBeNull()
  })

  it('负债小计有跨底稿取数 → 写入该值', () => {
    const p = buildN1SyncPayload(
      'listed',
      snapshot({ liabilitySubtotal: { endBalance: 88_000, priorBalance: null } }),
      CTX,
    )
    const rows = p.sub_table_data[N1_SUB_TABLE_KEYS.listed.unoffset] as any[]
    expect(rows[rows.length - 1].end).toBe(88_000)
    expect(rows[rows.length - 1].prior).toBeNull()
  })

  it('互抵金额未取到 → 抵销后净额表全 null', () => {
    const rows = buildN1SyncPayload('listed', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.listed.netOffset] as any[]
    expect(rows.map((r) => r.offsetEnd)).toEqual([null, null])
    expect(rows.map((r) => r.netEnd)).toEqual([null, null])
  })

  it('资产段小计为逐项求和；全 null 时小计为 null', () => {
    const rows = buildN1SyncPayload('listed', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.listed.unoffset] as any[]
    const assetSubtotal = rows.find((r) => r.is_total)
    expect(assetSubtotal.end).toBe(200_000)
    expect(assetSubtotal.prior).toBe(100_000)

    const empty = buildN1SyncPayload(
      'listed',
      snapshot({ assetRows: [{ item: 'X', endBalance: null, priorBalance: null }] }),
      CTX,
    ).sub_table_data[N1_SUB_TABLE_KEYS.listed.unoffset] as any[]
    expect(empty.find((r) => r.is_total).end).toBeNull()
  })
})

// ─── 行结构 / 聚合 ───────────────────────────────────────────────────────────

describe('行结构与聚合', () => {
  it('未经抵销表含资产/负债分组标题行（逐字取模板）', () => {
    const listed = buildN1SyncPayload('listed', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.listed.unoffset] as any[]
    expect(listed[0].item).toBe('递延所得税资产：')
    expect(listed.some((r) => r.item === '递延所得税负债：')).toBe(true)

    const soe = buildN1SyncPayload('soe', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.soe.unoffset] as any[]
    expect(soe[0].item).toBe('一、递延所得税资产')
    expect(soe.some((r) => r.item === '二、递延所得税负债')).toBe(true)
  })

  it('亏损到期表按到期年度聚合 + 合计 + 备注合并', () => {
    const rows = buildN1SyncPayload('listed', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.listed.lossExpiry] as any[]
    expect(rows.map((r) => r.year)).toEqual(['2027年', '2028年', '合计'])
    expect(rows[0].end).toBe(500_000) // 400000 + 100000 同年聚合
    expect(rows[0].remark).toBe('分支机构')
    expect(rows[2].end).toBe(750_000)
    expect(rows[2].is_total).toBe(true)
  })

  it('亏损到期表忽略无效年度（"—" / 空）', () => {
    const rows = buildN1SyncPayload(
      'listed',
      snapshot({ lossExpiryRows: [{ expiryYear: '—', unrecovered: 1 }, { expiryYear: '', unrecovered: 2 }] }),
      CTX,
    ).sub_table_data[N1_SUB_TABLE_KEYS.listed.lossExpiry] as any[]
    expect(rows).toHaveLength(1)
    expect(rows[0].year).toBe('合计')
    expect(rows[0].end).toBeNull()
  })

  it('未确认明细表末行为合计', () => {
    const rows = buildN1SyncPayload('soe', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.soe.unrecognized] as any[]
    expect(rows[rows.length - 1]).toMatchObject({ item: '合计', end: 500_000, is_total: true })
  })
})

// ─── Property 11 ─────────────────────────────────────────────────────────────

describe('Property 11 — 纯函数', () => {
  it('同输入多次调用深相等', () => {
    const a = buildN1SyncPayload('listed', snapshot(), CTX)
    const b = buildN1SyncPayload('listed', snapshot(), CTX)
    expect(a).toEqual(b)
  })

  it('不修改入参 snapshot', () => {
    const snap = snapshot()
    const frozen = JSON.parse(JSON.stringify(snap))
    buildN1SyncPayload('soe', snap, CTX)
    expect(snap).toEqual(frozen)
  })
})
