/**
 * n1NoteSectionMap 载荷构造守卫
 *
 * spec: `n1-disclosure-note-linkage`（原）+ `n1-deferred-tax-disclosure-template-alignment`（对齐重建）
 *
 * Property 1  章节号 = 权威矩阵（从 note_template_variant_matrix.json 读取比对）
 * Property 2  sub_table_data 键集合 === columns 键集合 === 该变体子表名全集
 * Property 3  columns label 逐字对齐附注模板 tables[].headers（含两级表头子列序）
 * Property 4  year / current_standard 显式传递
 * Property 5  空文本不写 _note_texts
 * Property 9  只含 owner=N1 的子表键（listed 4 张 / soe 5 张）
 * Property 10 负债段 / 互抵金额缺失写 null 不写 0
 * Property 11 纯函数（同输入深相等 + 不改入参）
 * Property 12 表 1 两版子列序相反（源模板 B11:E11 实测）
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  N1_DISCLOSURE_SHEET_NAME,
  N1_NOTE_SECTION,
  N1_SUB_TABLE_KEYS,
  N1_TABLE_NAMESPACE,
  buildN1NoteTexts,
  buildN1SyncPayload,
  isN1TotalLabel,
  n1UnoffsetSubOrder,
  normalizeN1RowLabel,
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

const VARIANTS: N1DisclosureVariant[] = ['listed', 'soe']

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

function assetRow(item: string, endTax: number, priorTax: number) {
  return { item, endDiff: endTax * 4, endTax, priorDiff: priorTax * 4, priorTax }
}

function snapshot(over: Partial<N1DisclosureSnapshot> = {}): N1DisclosureSnapshot {
  return {
    assetRows: [assetRow('资产减值准备', 150_000, 100_000), assetRow('可抵扣亏损', 50_000, 0)],
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

describe('Property 1 — 章节号 / sheet 名单一真源', () => {
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

describe('Property 2/9 — 键集合一致 + 仅推 owner=N1 的子表', () => {
  it.each(VARIANTS)('%s 变体 sub_table_data 键 ≡ columns 键 ≡ 子表名全集', (variant) => {
    const p = buildN1SyncPayload(variant, snapshot(), CTX)
    const dataKeys = Object.keys(p.sub_table_data).filter((k) => !k.startsWith('_'))
    expect(new Set(dataKeys)).toEqual(new Set(Object.keys(p.columns)))
    expect(new Set(dataKeys)).toEqual(new Set(Object.values(N1_SUB_TABLE_KEYS[variant])))
  })

  it('listed 4 张 / soe 5 张（国企多源模板（2）B 互抵明细）', () => {
    expect(Object.keys(N1_SUB_TABLE_KEYS.listed)).toHaveLength(4)
    expect(Object.keys(N1_SUB_TABLE_KEYS.soe)).toHaveLength(5)
    expect(N1_SUB_TABLE_KEYS.soe.offsetDetail).toBe('递延所得税资产和递延所得税负债互抵明细')
    expect(N1_SUB_TABLE_KEYS.listed).not.toHaveProperty('offsetDetail')
  })

  it('子表名均存在于附注模板（不自造表名）', () => {
    for (const variant of VARIANTS) {
      const names = (sectionOf(variant).tables || []).map((t: any) => t.name)
      for (const key of Object.values(N1_SUB_TABLE_KEYS[variant])) {
        expect(names, `${variant} ${key}`).toContain(key)
      }
    }
  })

  it('反向：模板该章节所有表都有映射（无遗漏表 → 附注不会剩没人推的空 TAB）', () => {
    for (const variant of VARIANTS) {
      const names = (sectionOf(variant).tables || []).map((t: any) => t.name)
      expect(new Set(names)).toEqual(new Set(Object.values(N1_SUB_TABLE_KEYS[variant])))
    }
  })

  it('N1_TABLE_NAMESPACE.known 覆盖全部子表名（孤儿清理基线播种用）', () => {
    for (const variant of VARIANTS) {
      expect(new Set(N1_TABLE_NAMESPACE[variant].known)).toEqual(
        new Set(Object.values(N1_SUB_TABLE_KEYS[variant])),
      )
    }
  })

  it('每行值列键均在该表 columns 内声明（投影器不忽略数据）', () => {
    for (const variant of VARIANTS) {
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

// ─── Property 3 / 12 ─────────────────────────────────────────────────────────

describe('Property 3 — 列头逐字对齐模板 headers', () => {
  it.each(VARIANTS)('%s 变体列头对齐', (variant) => {
    const p = buildN1SyncPayload(variant, snapshot(), CTX)
    for (const [key, defs] of Object.entries(p.columns)) {
      expect(defs.map((d) => d.label), `${variant}/${key}`).toEqual(tableOf(variant, key).headers)
    }
  })

  it('表 1 两版均为 5 列两级表头（原被 md 抽取压扁成 3 列）', () => {
    for (const variant of VARIANTS) {
      const defs = buildN1SyncPayload(variant, snapshot(), CTX)
        .columns[N1_SUB_TABLE_KEYS[variant].unoffset]
      expect(defs).toHaveLength(5)
      expect(defs.filter((d) => d.group)).toHaveLength(4)
    }
  })

  it('soe 抵销后净额表为 5 列（原被压扁成 3 列，是本 spec 修的缺陷）', () => {
    expect(
      buildN1SyncPayload('soe', snapshot(), CTX).columns[N1_SUB_TABLE_KEYS.soe.netOffset],
    ).toHaveLength(5)
    expect(
      buildN1SyncPayload('listed', snapshot(), CTX).columns[N1_SUB_TABLE_KEYS.listed.netOffset],
    ).toHaveLength(5)
  })

  it('Property 12 — 表 1 两版子列序相反（源模板 B11:E11）', () => {
    expect(n1UnoffsetSubOrder('listed').map(([, l]) => l)).toEqual([
      '可抵扣/应纳税暂时性差异',
      '递延所得税资产/负债',
    ])
    expect(n1UnoffsetSubOrder('soe').map(([, l]) => l)).toEqual([
      '递延所得税资产/负债',
      '可抵扣/应纳税暂时性差异',
    ])
    // columns 键序必须跟随子列序，否则附注列错位
    const listedKeys = buildN1SyncPayload('listed', snapshot(), CTX)
      .columns[N1_SUB_TABLE_KEYS.listed.unoffset].map((d) => d.key)
    const soeKeys = buildN1SyncPayload('soe', snapshot(), CTX)
      .columns[N1_SUB_TABLE_KEYS.soe.unoffset].map((d) => d.key)
    expect(listedKeys).toEqual(['label', 'end_diff', 'end_tax', 'prior_diff', 'prior_tax'])
    expect(soeKeys).toEqual(['label', 'end_tax', 'end_diff', 'prior_tax', 'prior_diff'])
  })

  it('单级表显式 flat、两级表用 group（后端三态：不得都无、不得并存）', () => {
    for (const variant of VARIANTS) {
      const p = buildN1SyncPayload(variant, snapshot(), CTX)
      for (const [key, defs] of Object.entries(p.columns)) {
        const hasFlat = defs.some((d) => d.flat)
        const hasGroup = defs.some((d) => d.group)
        expect(hasFlat, `${variant}/${key}`).not.toBe(hasGroup)
      }
    }
  })

  it('每张表恰有一个标签列', () => {
    for (const variant of VARIANTS) {
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
    const blank = buildN1SyncPayload('listed', snapshot({ notes: { conclusion: '  ', rollback: '' } }), CTX)
    expect(blank.sub_table_data).not.toHaveProperty('_note_texts')
  })

  it('有文本 → 按子节产出 {section,title,text}，跳过空串', () => {
    const p = buildN1SyncPayload('soe', snapshot({ notes: { conclusion: '结论X', rollback: '' } }), CTX)
    expect(p.sub_table_data._note_texts).toEqual([
      { section: 'n1-disclosure-conclusion', title: '披露说明与结论', text: '结论X' },
    ])
  })

  it('R30 说明（rollback）排在结论之前', () => {
    expect(buildN1NoteTexts({ conclusion: 'C', rollback: 'R' }).map((t) => t.section)).toEqual([
      'n1-disclosure-rollback',
      'n1-disclosure-conclusion',
    ])
  })

  it('buildN1NoteTexts 无输入返回空数组', () => {
    expect(buildN1NoteTexts()).toEqual([])
    expect(buildN1NoteTexts({})).toEqual([])
  })
})

// ─── Property 10 ─────────────────────────────────────────────────────────────

describe('Property 10 — 缺失写 null 不写 0', () => {
  it('负债段无数据 → 负债小计四值全 null（不是 0）', () => {
    const rows = buildN1SyncPayload('listed', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.listed.unoffset] as any[]
    const last = rows[rows.length - 1]
    expect(last.is_total).toBe(true)
    expect([last.end_diff, last.end_tax, last.prior_diff, last.prior_tax]).toEqual([
      null, null, null, null,
    ])
  })

  it('负债小计有跨底稿取数 → 写入该值', () => {
    const rows = buildN1SyncPayload(
      'listed',
      snapshot({ liabilitySubtotal: { endTax: 88_000, priorTax: null } }),
      CTX,
    ).sub_table_data[N1_SUB_TABLE_KEYS.listed.unoffset] as any[]
    const last = rows[rows.length - 1]
    expect(last.end_tax).toBe(88_000)
    expect(last.prior_tax).toBeNull()
  })

  it('互抵金额未取到 → 上市抵销后净额表全 null', () => {
    const rows = buildN1SyncPayload('listed', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.listed.netOffset] as any[]
    expect(rows.map((r) => r.offset_end)).toEqual([null, null])
    expect(rows.map((r) => r.net_end)).toEqual([null, null])
  })

  it('资产段小计为逐项求和；全 null 时小计为 null', () => {
    const rows = buildN1SyncPayload('listed', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.listed.unoffset] as any[]
    const assetSubtotal = rows.find((r) => r.is_total)
    expect(assetSubtotal.end_tax).toBe(200_000)
    expect(assetSubtotal.prior_tax).toBe(100_000)

    const empty = buildN1SyncPayload(
      'listed',
      snapshot({
        assetRows: [{ item: 'X', endDiff: null, endTax: null, priorDiff: null, priorTax: null }],
      }),
      CTX,
    ).sub_table_data[N1_SUB_TABLE_KEYS.listed.unoffset] as any[]
    expect(empty.find((r) => r.is_total).end_tax).toBeNull()
  })
})

// ─── 行结构 / 聚合 ───────────────────────────────────────────────────────────

describe('行结构与聚合', () => {
  it('表 1 含资产/负债分组标题行（逐字取模板）', () => {
    const listed = buildN1SyncPayload('listed', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.listed.unoffset] as any[]
    expect(listed[0].label).toBe('递延所得税资产：')
    expect(listed.some((r) => r.label === '递延所得税负债：')).toBe(true)

    const soe = buildN1SyncPayload('soe', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.soe.unoffset] as any[]
    expect(soe[0].label).toBe('一、递延所得税资产')
    expect(soe.some((r) => r.label === '二、递延所得税负债')).toBe(true)
  })

  it('分组标题行全列 null（结构行不带数据）', () => {
    const rows = buildN1SyncPayload('soe', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.soe.unoffset] as any[]
    const g = rows[0]
    expect([g.end_diff, g.end_tax, g.prior_diff, g.prior_tax]).toEqual([null, null, null, null])
    expect(g.is_total).toBeUndefined()
  })

  it('soe 表 2 为双段结构（资产段小计 + 负债段小计）', () => {
    const rows = buildN1SyncPayload(
      'soe',
      snapshot({
        netOffsetAssetRows: [
          { item: '资产减值准备', netEnd: 10, diffEnd: 40, netPrior: 5, diffPrior: 20 },
        ],
        netOffsetLiabilityRows: [
          { item: '使用权资产', netEnd: 3, diffEnd: 12, netPrior: 1, diffPrior: 4 },
        ],
      }),
      CTX,
    ).sub_table_data[N1_SUB_TABLE_KEYS.soe.netOffset] as any[]
    expect(rows.map((r) => r.label)).toEqual([
      '一、递延所得税资产', '资产减值准备', '小计',
      '二、递延所得税负债', '使用权资产', '小计',
    ])
    expect(rows.filter((r) => r.is_total).map((r) => r.net_end)).toEqual([10, 3])
  })

  it('soe 互抵明细为空时推空数组（键仍在，附注 TAB 不消失）', () => {
    const p = buildN1SyncPayload('soe', snapshot(), CTX)
    expect(p.sub_table_data[N1_SUB_TABLE_KEYS.soe.offsetDetail]).toEqual([])
    expect(p.columns).toHaveProperty(N1_SUB_TABLE_KEYS.soe.offsetDetail)
  })

  it('亏损到期表按到期年度聚合 + 合计 + 备注合并', () => {
    const rows = buildN1SyncPayload('listed', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.listed.lossExpiry] as any[]
    expect(rows.map((r) => r.label)).toEqual(['2027年', '2028年', '合计'])
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
    expect(rows[0].label).toBe('合计')
    expect(rows[0].end).toBeNull()
  })

  it('未确认明细表末行为合计', () => {
    const rows = buildN1SyncPayload('soe', snapshot(), CTX)
      .sub_table_data[N1_SUB_TABLE_KEYS.soe.unrecognized] as any[]
    expect(rows[rows.length - 1]).toMatchObject({ label: '合计', end: 500_000, is_total: true })
  })
})

// ─── 行型判定（源模板写 `小  计` / `合  计`，带空格）────────────────────────

describe('行型判定先去空白', () => {
  it('normalizeN1RowLabel 去掉全部空白', () => {
    expect(normalizeN1RowLabel('小  计')).toBe('小计')
    expect(normalizeN1RowLabel(' 合 计 ')).toBe('合计')
    expect(normalizeN1RowLabel(null)).toBe('')
  })

  it('isN1TotalLabel 认带空格的小计/合计', () => {
    expect(isN1TotalLabel('小  计')).toBe(true)
    expect(isN1TotalLabel('合  计')).toBe(true)
    expect(isN1TotalLabel('小计')).toBe(true)
    expect(isN1TotalLabel('资产减值准备')).toBe(false)
  })
})

// ─── Property 11 ─────────────────────────────────────────────────────────────

describe('Property 11 — 纯函数', () => {
  it('同输入多次调用深相等', () => {
    expect(buildN1SyncPayload('listed', snapshot(), CTX)).toEqual(
      buildN1SyncPayload('listed', snapshot(), CTX),
    )
  })

  it('不修改入参 snapshot', () => {
    const snap = snapshot()
    const frozen = JSON.parse(JSON.stringify(snap))
    buildN1SyncPayload('soe', snap, CTX)
    expect(snap).toEqual(frozen)
  })
})
