import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  buildK4ListedColumns,
  buildK4SoeColumns,
  buildK4SyncPayload,
  K4_DISCLOSURE_SHEET_NAME,
  K4_NOTE_SECTION,
  K4_SUBTABLE,
  type K4DisclosureRow,
  type K4DisclosureVariant,
  type K4SyncPayloadExtras,
} from '../k4NoteSectionMap'
import type { ColumnDef } from '../disclosureColumnDefs'

/**
 * K4 其他流动负债披露 columns 契约
 *
 * spec `disclosure-columns-coverage-rollout` design §批 2 列头清查 §2（上市）/§3（国企）
 * 口径证据：源 `K 管理循环/K4 其他流动负债.xlsx` 两张披露 sheet +
 *   `附注模版/上市报表附注.md` L4593/L4614/L4623、`国企报表附注.md` L3665 +
 *   `note_template_{listed,soe}.json` 五、44 / 八、48 + 校验预设 F44-1/2/3。
 *
 * 覆盖 T5 八族断言：Property 1（键一一对应，含债券两张条件表的空分支）/
 *   Property 2（标签列唯一居首）/ Property 6（无 snake_case 列头）/
 *   单行表头 `flat`（0 处 group）/ 逐字 label + 负向断言 /
 *   行结构对齐（K4 用业务键行，非位置化 `values`）/ 表名·sheet 名·section 常量 /
 *   `_note_texts` 落在 `sub_table_data` 内 + 附注模板表名逐字契约（T7-3 孤儿 TAB 守卫）。
 */

const SNAKE_CASE = /^[a-z_][a-z0-9_]*$/
const VARIANTS = ['listed', 'soe'] as const

const rows: K4DisclosureRow[] = [
  { project: '预提费用', endAmount: 1000, priorAmount: 800 },
  { project: '待转销项税额', endAmount: 500, priorAmount: 400 },
]

const extras: K4SyncPayloadExtras = {
  bondRows: [
    { name: '25 甲债01', faceValue: 1000, couponRate: 3.5, issueDate: '2025-01-10', term: '1年', issueAmount: 990 },
  ],
  bondContRows: [
    { name: '25 甲债01', beginBalance: 900, issued: 100, interestAccrued: 30, premiumAmort: 5, repaid: 20, defaulted: '否' },
  ],
}

function payloadOf(variant: K4DisclosureVariant, over: K4SyncPayloadExtras = extras, narrative = '本期其他流动负债主要为预提费用。') {
  return buildK4SyncPayload(variant, 'wp-k4', rows, narrative, over)
}

/** 非元数据（非 `_` 前缀）的数据子表键 */
function dataKeys(sub: Record<string, unknown>): string[] {
  return Object.keys(sub).filter(k => !k.startsWith('_')).sort()
}

// ─── 附注模板表名（T7-3 孤儿 TAB 守卫的证据源） ────────────────────────────────

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

interface NoteTable { name?: string }
interface NoteSection { section_number?: string; tables?: NoteTable[] }

function templateTableNames(file: string, sectionNumber: string): Set<string> {
  const path = resolve(REPO_ROOT, 'backend/data', file)
  const raw = JSON.parse(readFileSync(path, 'utf-8')) as { sections: NoteSection[] }
  const hit = raw.sections.find(s => String(s.section_number ?? '').trim() === sectionNumber)
  if (!hit) throw new Error(`${file} 缺少章节 ${sectionNumber}`)
  return new Set((hit.tables ?? []).map(t => String(t.name ?? '')))
}

describe('K4 其他流动负债披露 columns 契约', () => {
  it('上市：汇总表 3 列，金额列取附注模版口径（非源 xlsx 的「期末数/上年年末数」）', () => {
    const cols = buildK4ListedColumns()[K4_SUBTABLE.summary]
    expect(cols.map(c => c.label)).toEqual(['项目', '期末余额', '上年年末余额'])
    expect(cols.map(c => c.key)).toEqual(['label', 'end_amount', 'prior_amount'])
    expect(cols[0].is_label).toBe(true)
    expect(cols[1].format).toBe('amount')
    expect(cols[2].format).toBe('amount')
    // 负向：源 xlsx B6/C6 的 `期末数`/`上年年末数` 被裁决掉（附注是交付物）
    expect(cols.map(c => c.label)).not.toContain('期末数')
    expect(cols.map(c => c.label)).not.toContain('上年年末数')
    // 负向：预设 F44-1/2/3 只认 2 个金额列，UI 的「形成原因/备注」无附注落点
    expect(cols).toHaveLength(3)
    expect(cols.map(c => c.label)).not.toContain('形成原因')
  })

  it('国企：汇总表第 3 列为「期初余额」（四源一致）', () => {
    const cols = buildK4SoeColumns()[K4_SUBTABLE.summary]
    expect(cols.map(c => c.label)).toEqual(['项目', '期末余额', '期初余额'])
    expect(cols.map(c => c.key)).toEqual(['label', 'end_amount', 'prior_amount'])
    expect(cols.map(c => c.label)).not.toContain('上年年末余额')
    // 负向：UI 的「增减额」是审计列，附注无落点
    expect(cols.map(c => c.label)).not.toContain('增减额')
  })

  it('上市：短期应付债券明细 6 列（源 A19:F19 / 附注模版 L4614）', () => {
    const cols = buildK4ListedColumns({ includeBond: true })[K4_SUBTABLE.bond]
    expect(cols.map(c => c.label)).toEqual(['债券名称', '面值', '票面利率', '发行日期', '债券期限', '发行金额'])
    expect(cols.map(c => c.key)).toEqual(['bond_name', 'face_value', 'coupon_rate', 'issue_date', 'term', 'issue_amount'])
    expect(cols[0].is_label).toBe(true)
    expect(cols[2].format).toBe('percent')
    expect(cols[3].format).toBe('text')
  })

  it('上市：债券续表 8 列，期初列取附注模版口径「期初余额」（非源 xlsx 的「上年年末数」）', () => {
    const cols = buildK4ListedColumns({ includeBondCont: true })[K4_SUBTABLE.bondCont]
    expect(cols.map(c => c.label)).toEqual([
      '债券名称', '期初余额', '本期发行', '按面值计提利息', '溢折价摊销', '本期偿还', '期末余额', '是否违约',
    ])
    expect(cols.map(c => c.key)).toEqual([
      'bond_name', 'begin_amount', 'issued', 'interest_accrued', 'premium_amort', 'repaid', 'end_amount', 'defaulted',
    ])
    expect(cols.map(c => c.label)).not.toContain('上年年末数')
    expect(cols[7].format).toBe('text')
  })

  it('Property 1：columns 键与 sub_table_data 数据键集合相等', () => {
    const listed = payloadOf('listed')
    expect(dataKeys(listed.sub_table_data)).toEqual(
      [K4_SUBTABLE.summary, K4_SUBTABLE.bond, K4_SUBTABLE.bondCont].sort(),
    )
    expect(Object.keys(listed.columns).sort()).toEqual(dataKeys(listed.sub_table_data))

    const soe = payloadOf('soe')
    expect(dataKeys(soe.sub_table_data)).toEqual([K4_SUBTABLE.summary])
    expect(Object.keys(soe.columns).sort()).toEqual(dataKeys(soe.sub_table_data))
  })

  it('Property 1（空条件表分支）：债券两表过滤为空时在两侧同时缺席', () => {
    // 空数组 与 全空行（`name || issueAmount || faceValue` 均为假）两种入参落到同一分支
    const emptyInputs: K4SyncPayloadExtras[] = [
      { bondRows: [], bondContRows: [] },
      {
        bondRows: [{ name: '', faceValue: 0, issueAmount: 0 }],
        bondContRows: [{ name: '', beginBalance: 0, issued: 0 }],
      },
    ]
    for (const over of emptyInputs) {
      const { sub_table_data, columns } = payloadOf('listed', over)
      expect(sub_table_data[K4_SUBTABLE.bond]).toBeUndefined()
      expect(columns[K4_SUBTABLE.bond]).toBeUndefined()
      expect(sub_table_data[K4_SUBTABLE.bondCont]).toBeUndefined()
      expect(columns[K4_SUBTABLE.bondCont]).toBeUndefined()
      expect(Object.keys(columns).sort()).toEqual(dataKeys(sub_table_data))
      expect(dataKeys(sub_table_data)).toEqual([K4_SUBTABLE.summary])
    }
  })

  it('Property 1（国企无债券表）：即便传入债券入参，国企侧两表都不出现', () => {
    const { sub_table_data, columns } = payloadOf('soe')
    expect(sub_table_data[K4_SUBTABLE.bond]).toBeUndefined()
    expect(columns[K4_SUBTABLE.bond]).toBeUndefined()
    expect(sub_table_data[K4_SUBTABLE.bondCont]).toBeUndefined()
    expect(columns[K4_SUBTABLE.bondCont]).toBeUndefined()
  })

  it('Property 2：每张表恰好 1 个 is_label 且位于索引 0', () => {
    for (const variant of VARIANTS) {
      const { columns } = payloadOf(variant)
      for (const [name, defs] of Object.entries(columns)) {
        expect(defs.length, name).toBeGreaterThan(0)
        expect(defs.filter(d => d.is_label === true), `${variant}.${name}`).toHaveLength(1)
        expect(defs[0].is_label, `${variant}.${name}`).toBe(true)
      }
    }
  })

  it('Property 6：无 snake_case 字段键泄漏为列头，且 label 非空', () => {
    for (const variant of VARIANTS) {
      const { columns } = payloadOf(variant)
      for (const [name, defs] of Object.entries(columns)) {
        for (const d of defs) {
          expect(d.label.trim(), `${variant}.${name}.${d.key}`).not.toBe('')
          expect(SNAKE_CASE.test(d.label), `${variant}.${name}.${d.key} 用了字段键当列头`).toBe(false)
        }
      }
    }
  })

  it('K4 三张表全为单行表头：每表至少一列 flat，且无一列带 group', () => {
    for (const variant of VARIANTS) {
      const { columns } = payloadOf(variant)
      for (const [name, defs] of Object.entries(columns)) {
        expect(defs.some(d => d.flat === true), `${variant}.${name} 未声明 flat`).toBe(true)
        expect(defs.filter(d => d.group !== undefined), `${variant}.${name}`).toHaveLength(0)
      }
    }
  })

  it('行结构对齐：K4 用业务键行，每行含全部声明列键且无多余业务键', () => {
    for (const variant of VARIANTS) {
      const { sub_table_data, columns } = payloadOf(variant)
      for (const key of dataKeys(sub_table_data)) {
        const defs = columns[key] as ColumnDef[]
        const declared = new Set(defs.map(d => d.key))
        const tableRows = sub_table_data[key] as Array<Record<string, unknown>>
        expect(tableRows.length, `${variant}.${key}`).toBeGreaterThan(0)
        for (const r of tableRows) {
          for (const d of defs) {
            expect(Object.prototype.hasOwnProperty.call(r, d.key), `${variant}.${key} 行缺列键 ${d.key}`).toBe(true)
          }
          // 允许的非列键只有行标记 `is_total`；其余泄漏说明底稿字段混进了附注行
          const leaked = Object.keys(r).filter(k => !declared.has(k) && k !== 'is_total')
          expect(leaked, `${variant}.${key} 行「${String(r.label ?? r.bond_name)}」多余键`).toEqual([])
        }
        // K4 不用位置化 values
        expect(tableRows.every(r => !('values' in r)), `${variant}.${key}`).toBe(true)
      }
    }
  })

  it('汇总表带合计行，金额为明细行之和', () => {
    const { sub_table_data } = payloadOf('listed')
    const tableRows = sub_table_data[K4_SUBTABLE.summary] as Array<Record<string, unknown>>
    const total = tableRows[tableRows.length - 1]
    expect(total.label).toBe('合计')
    expect(total.is_total).toBe(true)
    expect(total.end_amount).toBe(1500)
    expect(total.prior_amount).toBe(1200)
  })

  it('表名 / sheet 名 / section_id 全部引用常量（禁字面量，R8/T7-6）', () => {
    for (const variant of VARIANTS) {
      const payload = payloadOf(variant)
      expect(payload.sheet_name, variant).toBe(K4_DISCLOSURE_SHEET_NAME[variant])
      expect(payload.section_id, variant).toBe(K4_NOTE_SECTION[variant])
      const expected = variant === 'listed'
        ? [K4_SUBTABLE.summary, K4_SUBTABLE.bond, K4_SUBTABLE.bondCont].sort()
        : [K4_SUBTABLE.summary]
      expect(dataKeys(payload.sub_table_data), variant).toEqual(expected)
    }
  })

  it('`_note_texts` 落在 sub_table_data 内，叙述为空时缺席', () => {
    for (const variant of VARIANTS) {
      const withText = payloadOf(variant)
      expect(Array.isArray(withText.sub_table_data._note_texts), variant).toBe(true)
      expect((withText.sub_table_data as Record<string, Array<{ text: string }>>)._note_texts[0].text, variant)
        .toBe('本期其他流动负债主要为预提费用。')
      // 后端 `_extract_note_texts(sub_table_data)` 只认 sub_table_data 内的键
      expect((withText as unknown as Record<string, unknown>)._note_texts, variant).toBeUndefined()

      const blank = payloadOf(variant, extras, '   ')
      expect(blank.sub_table_data._note_texts, variant).toBeUndefined()
    }
  })
})

describe('K4 子表名 ↔ note_template 逐字契约（T7-3 孤儿 TAB 守卫）', () => {
  const listedNames = templateTableNames('note_template_listed.json', K4_NOTE_SECTION.listed)
  const soeNames = templateTableNames('note_template_soe.json', K4_NOTE_SECTION.soe)

  it.each([K4_SUBTABLE.summary, K4_SUBTABLE.bond, K4_SUBTABLE.bondCont])(
    '上市「%s」逐字存在于 note_template_listed 五、44 的 tables[].name',
    name => {
      expect(listedNames.has(name)).toBe(true)
    },
  )

  it('国企「其他流动负债」逐字存在于 note_template_soe 八、48 的 tables[].name', () => {
    expect(soeNames.has(K4_SUBTABLE.summary)).toBe(true)
  })

  it('负向：旧实现推的英文键 `rows` 不是任何模板表名（6.1 实测的孤儿子表来源）', () => {
    expect(listedNames.has('rows')).toBe(false)
    expect(soeNames.has('rows')).toBe(false)
  })
})
