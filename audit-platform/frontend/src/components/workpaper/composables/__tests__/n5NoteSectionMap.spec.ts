/**
 * n5NoteSectionMap 载荷构造 + 契约守卫
 *
 * Property 1  键集合三方相等
 * Property 2  子表名逐字取自附注模板、章节存在、**同章节无重名**
 * Property 5  🔴 sheet 名逐字（国企 `附注披露信息（国企` **缺右括号**）
 * Property 6  显式 `flat`
 * Property 7  行型判定先去空白
 * Property 8  缺失写 null 不写 0
 * Property 10 表（2）末行按变体分化（上市 = 勾稽落点行 / 国企 = 合计行）
 * Property 11 纯函数
 * Property 12 孤儿键上报（表名去重后的旧键进 `_removed_table_keys`，推送键绝不进）
 *
 * spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/` Task 8.1
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  N5_DISCLOSURE_SHEET_NAME,
  N5_LEGACY_OBSOLETE_TABLES,
  N5_LISTED_TAIL_LABEL,
  N5_NOTE_SECTION,
  N5_SUB_TABLE_KEYS,
  N5_TABLE_NAMESPACE,
  buildN5ListedColumns,
  buildN5NoteTexts,
  buildN5SoeColumns,
  buildN5SyncPayload,
  isN5TotalLabel,
  normalizeN5RowLabel,
  resolveN5CurrentStandard,
  type N5DisclosureVariant,
} from '../n5NoteSectionMap'

const ROOT = resolve(__dirname, '../../../../../../../backend/data')

function readJson(name: string): any {
  return JSON.parse(readFileSync(resolve(ROOT, name), 'utf-8'))
}

const TEMPLATES: Record<N5DisclosureVariant, any> = {
  listed: readJson('note_template_listed.json'),
  soe: readJson('note_template_soe.json'),
}
const VARIANTS: N5DisclosureVariant[] = ['listed', 'soe']

function sectionOf(variant: N5DisclosureVariant): any {
  const num = N5_NOTE_SECTION[variant]
  const s = (TEMPLATES[variant].sections || []).find((x: any) => x.section_number === num)
  expect(s, `${variant} 模板缺章节 ${num}`).toBeTruthy()
  return s
}

const CTX = { wpId: 'wp-n5', year: 2025 }

const SNAP = {
  detailRows: [
    { item: '当期所得税', current: 300, prior: 200 },
    { item: '递延所得税', current: 100, prior: 50 },
  ],
  reconcileRows: [
    { item: '利润总额', current: 1000, prior: 800 },
    { item: '其他', current: 400, prior: 250 },
  ],
  reconcileTail: { current: 400, prior: 250 },
}

function payload(variant: N5DisclosureVariant, over: Record<string, unknown> = {}) {
  return buildN5SyncPayload(variant, { ...SNAP, ...over } as any, CTX)
}

// ─── Property 1 / 2 ──────────────────────────────────────────────────────────

describe('Property 1/2 — 键集合、子表名、无重名', () => {
  it.each(VARIANTS)('%s: sub_table_data 键 ≡ columns 键 ≡ 子表名全集', (variant) => {
    const p = payload(variant)
    const dataKeys = Object.keys(p.sub_table_data).filter((k) => !k.startsWith('_'))
    expect(new Set(dataKeys)).toEqual(new Set(Object.keys(p.columns)))
    expect(new Set(dataKeys)).toEqual(new Set(Object.values(N5_SUB_TABLE_KEYS[variant])))
  })

  it.each(VARIANTS)('%s: 子表名与模板双向覆盖', (variant) => {
    const names = new Set(sectionOf(variant).tables.map((t: any) => t.name))
    expect(new Set(Object.values(N5_SUB_TABLE_KEYS[variant]) as string[])).toEqual(names)
  })

  it.each(VARIANTS)('%s: 同章节表名唯一（重名会互相覆盖丢整表）', (variant) => {
    const names = sectionOf(variant).tables.map((t: any) => t.name)
    expect(new Set(names).size, `重名：${names.join(' | ')}`).toBe(names.length)
    const mapped = Object.values(N5_SUB_TABLE_KEYS[variant]) as string[]
    expect(new Set(mapped).size).toBe(mapped.length)
  })

  it('去重后不得残留 md 重建泄漏的表名（表头首格 / 章节名）', () => {
    for (const variant of VARIANTS) {
      const names = Object.values(N5_SUB_TABLE_KEYS[variant]) as string[]
      expect(names).not.toContain('项  目')
      expect(names).not.toContain('项目')
    }
    // 国企第 1 表确实叫「所得税费用」（章节同名，但只有 1 张，不构成重名）
    expect(N5_SUB_TABLE_KEYS.soe.detail).toBe('所得税费用')
    expect(N5_SUB_TABLE_KEYS.soe.reconcile).toBe('会计利润与所得税费用调整过程')
  })

  it.each(VARIANTS)('%s: N5_TABLE_NAMESPACE 含子表名与旧键', (variant) => {
    const known = new Set(N5_TABLE_NAMESPACE[variant].known ?? [])
    for (const n of Object.values(N5_SUB_TABLE_KEYS[variant]) as string[]) {
      expect(known).toContain(n)
    }
    for (const n of N5_LEGACY_OBSOLETE_TABLES[variant]) expect(known).toContain(n)
  })

  it.each(VARIANTS)('%s: 每行值列键均在 columns 内声明', (variant) => {
    const p = payload(variant)
    for (const [key, defs] of Object.entries(p.columns)) {
      const allowed = new Set([...defs.map((d) => d.key), 'label', 'is_total'])
      for (const row of p.sub_table_data[key] as Array<Record<string, unknown>>) {
        for (const k of Object.keys(row)) expect(allowed, `${variant}/${key}/${k}`).toContain(k)
      }
    }
  })
})

// ─── Property 5（核心：缺右括号）────────────────────────────────────────────

describe('Property 5 — sheet 名逐字（含缺右括号）', () => {
  it('🔴 国企 sheet 名缺右括号，禁"修正"', () => {
    expect(N5_DISCLOSURE_SHEET_NAME.soe).toBe('附注披露信息（国企')
    expect(N5_DISCLOSURE_SHEET_NAME.soe.endsWith('）')).toBe(false)
    expect(N5_DISCLOSURE_SHEET_NAME.soe).not.toBe('附注披露信息（国企）')
  })

  it('上市 sheet 名全角括号完整', () => {
    expect(N5_DISCLOSURE_SHEET_NAME.listed).toBe('附注披露信息（上市公司）')
  })

  it.each(VARIANTS)('%s: 载荷 sheet_name 取常量', (variant) => {
    expect(payload(variant).sheet_name).toBe(N5_DISCLOSURE_SHEET_NAME[variant])
  })
})

// ─── Property 6 ──────────────────────────────────────────────────────────────

describe('Property 6 — 表头形态', () => {
  it.each(VARIANTS)('%s: 每张表显式 flat 且无 group，恰一个标签列', (variant) => {
    const cols = variant === 'listed' ? buildN5ListedColumns() : buildN5SoeColumns()
    for (const [key, defs] of Object.entries(cols)) {
      expect(defs.some((d) => d.flat), `${key} 未表态 flat`).toBe(true)
      expect(defs.some((d) => d.group), `${key} 不应有 group`).toBe(false)
      expect(defs.filter((d) => d.is_label), key).toHaveLength(1)
    }
  })

  it.each(VARIANTS)('%s: columns label 逐字对齐模板 headers', (variant) => {
    const p = payload(variant)
    for (const [key, defs] of Object.entries(p.columns)) {
      const t = sectionOf(variant).tables.find((x: any) => x.name === key)
      expect(defs.map((d) => d.label), `${variant}/${key}`).toEqual(t.headers)
    }
  })
})

// ─── Property 7 / 8 / 10 ─────────────────────────────────────────────────────

describe('Property 7/8/10 — 行型、空值、末行分化', () => {
  it('normalizeN5RowLabel / isN5TotalLabel 认带空格的合计', () => {
    expect(normalizeN5RowLabel('合  计')).toBe('合计')
    expect(isN5TotalLabel('合  计')).toBe(true)
    expect(isN5TotalLabel('利润总额')).toBe(false)
  })

  it.each(VARIANTS)('%s: 表（1）末行为合计（逐项求和 + is_total）', (variant) => {
    const rows = payload(variant).sub_table_data[N5_SUB_TABLE_KEYS[variant].detail] as any[]
    expect(rows[rows.length - 1]).toMatchObject({
      label: '合计', current: 400, prior: 250, is_total: true,
    })
  })

  it('上市表（2）末行 = 「所得税费用」勾稽落点，不打 is_total（源模板注 1）', () => {
    const rows = payload('listed').sub_table_data[N5_SUB_TABLE_KEYS.listed.reconcile] as any[]
    const tail = rows[rows.length - 1]
    expect(tail.label).toBe(N5_LISTED_TAIL_LABEL)
    expect(tail.is_total).toBeUndefined()
    expect(tail).toMatchObject({ current: 400, prior: 250 })
  })

  it('国企表（2）末行 = 合计行（打 is_total）', () => {
    const rows = payload('soe').sub_table_data[N5_SUB_TABLE_KEYS.soe.reconcile] as any[]
    const tail = rows[rows.length - 1]
    expect(tail.label).toBe('合计')
    expect(tail.is_total).toBe(true)
  })

  it('表（2）明细行原样列示（含首行利润总额，求和口径由编制模型决定）', () => {
    const rows = payload('listed').sub_table_data[N5_SUB_TABLE_KEYS.listed.reconcile] as any[]
    expect(rows.slice(0, -1).map((r) => r.label)).toEqual(['利润总额', '其他'])
  })

  it('缺失写 null 不写 0', () => {
    const p = buildN5SyncPayload(
      'listed',
      {
        detailRows: [{ item: 'X', current: null, prior: null }],
        reconcileRows: [],
        reconcileTail: { current: null, prior: null },
      },
      CTX,
    )
    const detail = p.sub_table_data[N5_SUB_TABLE_KEYS.listed.detail] as any[]
    expect(detail[detail.length - 1].current).toBeNull()
    const rec = p.sub_table_data[N5_SUB_TABLE_KEYS.listed.reconcile] as any[]
    expect(rec[rec.length - 1].current).toBeNull()
  })
})

// ─── Property 12 ─────────────────────────────────────────────────────────────

describe('Property 12 — 孤儿键上报', () => {
  it('上市：去重前的旧键 `项  目` 进 _removed_table_keys', () => {
    const removed = payload('listed').sub_table_data._removed_table_keys as string[]
    expect(removed).toContain('项  目')
  })

  it('上次已同步键中不再推送的进 removed；本次推送键绝不进', () => {
    const removed = payload('listed', {
      previouslySyncedTables: ['项  目', N5_SUB_TABLE_KEYS.listed.detail, '历史遗留表'],
    }).sub_table_data._removed_table_keys as string[]
    expect(removed).toContain('历史遗留表')
    expect(removed).not.toContain(N5_SUB_TABLE_KEYS.listed.detail)
    expect(removed).not.toContain(N5_SUB_TABLE_KEYS.listed.reconcile)
  })

  it('国企无额外孤儿键（旧第 2 表与第 1 表同名，塌成一张）', () => {
    expect(N5_LEGACY_OBSOLETE_TABLES.soe).toEqual([])
    expect(payload('soe').sub_table_data._removed_table_keys).toBeUndefined()
  })
})

// ─── current_standard / 文本 / 纯函数 ────────────────────────────────────────

describe('current_standard 与文本', () => {
  it('按变体与适用准则解析', () => {
    expect(resolveN5CurrentStandard('listed')).toBe('listed_standalone')
    expect(resolveN5CurrentStandard('soe')).toBe('soe_standalone')
    expect(resolveN5CurrentStandard('listed', ['listed_consolidated'])).toBe('listed_consolidated')
    expect(resolveN5CurrentStandard('soe', ['soe_consolidated'])).toBe('soe_consolidated')
  })

  it('章节号取模板现存值（listed 章节归属错误属跨 spec 依赖）', () => {
    expect(N5_NOTE_SECTION.listed).toBe('三、所得税费用')
    expect(N5_NOTE_SECTION.soe).toBe('八、78')
    expect(payload('soe').section_id).toBe('八、78')
  })

  it('空文本不写 _note_texts；顺序 detail → reconcile → conclusion；title 为中文', () => {
    expect(payload('listed').sub_table_data).not.toHaveProperty('_note_texts')
    expect(payload('listed', { notes: { conclusion: ' ' } }).sub_table_data)
      .not.toHaveProperty('_note_texts')
    const texts = buildN5NoteTexts({ conclusion: 'C', reconcile: 'R', detail: 'D' })
    expect(texts.map((t) => t.section)).toEqual([
      'n5-disclosure-detail',
      'n5-disclosure-reconcile',
      'n5-disclosure-conclusion',
    ])
    for (const t of texts) expect(/^[a-z-]+$/.test(t.title)).toBe(false)
  })
})

describe('Property 11 — 纯函数', () => {
  it.each(VARIANTS)('%s: 同输入深相等且不改入参', (variant) => {
    const snap = JSON.parse(JSON.stringify(SNAP))
    const frozen = JSON.parse(JSON.stringify(snap))
    expect(buildN5SyncPayload(variant, snap, CTX)).toEqual(buildN5SyncPayload(variant, snap, CTX))
    expect(snap).toEqual(frozen)
  })
})
