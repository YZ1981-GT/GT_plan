import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  buildK7ListedColumns,
  buildK7SoeColumns,
  buildK7SyncPayload,
  K7_DISCLOSURE_SHEET_NAME,
  K7_NOTE_SECTION,
  K7_SUBTABLE,
  type K7DisclosureRow,
  type K7DisclosureVariant,
} from '../k7NoteSectionMap'
import type { ColumnDef } from '../disclosureColumnDefs'

/**
 * K7 递延收益披露 columns 契约
 *
 * spec `disclosure-columns-coverage-rollout` design §批 2 列头清查 §8
 * 口径证据：源 `K 管理循环/K7 递延收益.xlsx` 两张披露 sheet（上市 A7:F7 / 国企 A7:E7
 *   表头行零跨列合并）+ `附注模版/上市报表附注.md` L4948 / `国企报表附注.md` L3972 +
 *   `note_template_{listed,soe}.json` 五、51 / 八、56 + 校验预设 F51-1/2/3/6。
 *
 * 覆盖 T5 八族断言，重点两条：
 *   · `flat` **必须标**：不标时后端 `_infer_groups_from_headers` 会把 `本期增加`/`本期减少`
 *     归到凭空的「本期」父表头下（§0⑤ 实跑已复现）。F51-3「期初 + 增加 − 减少 = 期末」
 *     证实这 4 个金额列是并列值列。
 *   · **T4 变体列集差异**：上市 5 值列（末列 `形成原因`）/ 国企 4 值列
 *     （国企源 xlsx 只 5 列、附注模版只 5 列、底稿国企行连 `reason` 字段都没有）。
 */

const SNAKE_CASE = /^[a-z_][a-z0-9_]*$/
const VARIANTS = ['listed', 'soe'] as const

const rows: K7DisclosureRow[] = [
  { project: '与资产相关的政府补助', beginBalance: 1000, increase: 500, decrease: 200, reason: '设备购置补助' },
  { project: '与收益相关的政府补助', beginBalance: 300, increase: 100, decrease: 50, reason: '研发费用补助' },
]

function payloadOf(variant: K7DisclosureVariant, narrative = '递延收益系收到的政府补助分期摊销。') {
  return buildK7SyncPayload(variant, 'wp-k7', rows, narrative)
}

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

describe('K7 递延收益披露 columns 契约', () => {
  it('上市：6 列（含末列「形成原因」），四源一致', () => {
    const cols = buildK7ListedColumns()[K7_SUBTABLE.deferredIncome]
    expect(cols.map(c => c.label)).toEqual(['项目', '期初余额', '本期增加', '本期减少', '期末余额', '形成原因'])
    expect(cols.map(c => c.key)).toEqual(['label', 'begin_amount', 'increase', 'decrease', 'end_amount', 'reason'])
    expect(cols[0].is_label).toBe(true)
    expect(cols.slice(1, 5).every(c => c.format === 'amount')).toBe(true)
    expect(cols[5].format).toBe('text')
  })

  it('国企：5 列，**不带**「形成原因」（源 xlsx / 附注模版 / note headers 三家都只 5 列）', () => {
    const cols = buildK7SoeColumns()[K7_SUBTABLE.deferredIncome]
    expect(cols.map(c => c.label)).toEqual(['项目', '期初余额', '本期增加', '本期减少', '期末余额'])
    expect(cols.map(c => c.key)).toEqual(['label', 'begin_amount', 'increase', 'decrease', 'end_amount'])
    expect(cols).toHaveLength(5)
    expect(cols.map(c => c.label)).not.toContain('形成原因')
    expect(cols.map(c => c.key)).not.toContain('reason')
    // 负向：标签列取附注口径「项目」（源 A7 = `项目/类别` 不作准）
    expect(cols[0].label).not.toBe('项目/类别')
  })

  it('单行表头：每表至少一列 flat 且无 group（抑制凭空的「本期」父表头）', () => {
    for (const variant of VARIANTS) {
      const { columns } = payloadOf(variant)
      for (const [name, defs] of Object.entries(columns)) {
        expect(defs.some(d => d.flat === true), `${variant}.${name} 未声明 flat`).toBe(true)
        expect(defs.filter(d => d.group !== undefined), `${variant}.${name}`).toHaveLength(0)
        // 负向：`本期增加`/`本期减少` 是并列值列，不是「本期」下的子列
        expect(defs.map(d => d.group), `${variant}.${name}`).not.toContain('本期')
        expect(defs.map(d => d.label), `${variant}.${name}`).not.toContain('本期')
      }
    }
  })

  it('Property 1：两版 columns 键与 sub_table_data 数据键集合相等', () => {
    for (const variant of VARIANTS) {
      const { sub_table_data, columns } = payloadOf(variant)
      expect(dataKeys(sub_table_data), variant).toEqual([K7_SUBTABLE.deferredIncome])
      expect(Object.keys(columns).sort(), variant).toEqual(dataKeys(sub_table_data))
    }
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

  it('位置对齐：每行 values 长度 = 该表非标签列数（上市 5 / 国企 4）', () => {
    const expectedLen = { listed: 5, soe: 4 } as const
    for (const variant of VARIANTS) {
      const { sub_table_data, columns } = payloadOf(variant)
      for (const key of dataKeys(sub_table_data)) {
        const defs = columns[key] as ColumnDef[]
        const valueColCount = defs.filter(d => !d.is_label).length
        expect(valueColCount, `${variant}.${key}`).toBe(expectedLen[variant])
        const tableRows = sub_table_data[key] as Array<{ label: unknown; values: unknown[] }>
        expect(tableRows.length, `${variant}.${key}`).toBeGreaterThan(0)
        for (const r of tableRows) {
          expect(r.values.length, `${variant}.${key} 行「${String(r.label)}」`).toBe(valueColCount)
        }
      }
    }
  })

  it('位置对齐（上市变体守卫）：values = [期初, 本期增加, 本期减少, 期末, 形成原因]', () => {
    const { sub_table_data } = payloadOf('listed')
    const tableRows = sub_table_data[K7_SUBTABLE.deferredIncome] as Array<{ label: string; values: unknown[] }>
    expect(tableRows[0].label).toBe('与资产相关的政府补助')
    // F51-3：1000 + 500 − 200 = 1300
    expect(tableRows[0].values).toEqual([1000, 500, 200, 1300, '设备购置补助'])
    expect(tableRows[tableRows.length - 1].values).toEqual([1300, 600, 250, 1650, ''])
  })

  it('位置对齐（国企变体守卫）：values = [期初, 本期增加, 本期减少, 期末]，形成原因不得溢出', () => {
    const { sub_table_data } = payloadOf('soe')
    const tableRows = sub_table_data[K7_SUBTABLE.deferredIncome] as Array<{ label: string; values: unknown[] }>
    expect(tableRows[0].label).toBe('与资产相关的政府补助')
    expect(tableRows[0].values).toEqual([1000, 500, 200, 1300])
    expect(tableRows[0].values).not.toContain('设备购置补助')
    expect(tableRows[tableRows.length - 1].values).toEqual([1300, 600, 250, 1650])
  })

  it('合计行带 is_total 且满足 F51-3 勾稽', () => {
    for (const variant of VARIANTS) {
      const { sub_table_data } = payloadOf(variant)
      const tableRows = sub_table_data[K7_SUBTABLE.deferredIncome] as Array<{
        label: string; values: number[]; is_total?: boolean
      }>
      const total = tableRows[tableRows.length - 1]
      expect(total.label, variant).toBe('合计')
      expect(total.is_total, variant).toBe(true)
      expect(total.values[0] + total.values[1] - total.values[2], variant).toBe(total.values[3])
    }
  })

  it('表名 / sheet 名 / section_id 全部引用常量（禁字面量，R8/T7-6）', () => {
    for (const variant of VARIANTS) {
      const payload = payloadOf(variant)
      expect(payload.sheet_name, variant).toBe(K7_DISCLOSURE_SHEET_NAME[variant])
      expect(payload.section_id, variant).toBe(K7_NOTE_SECTION[variant])
      expect(dataKeys(payload.sub_table_data), variant).toEqual([K7_SUBTABLE.deferredIncome])
    }
  })

  it('`_note_texts` 落在 sub_table_data 内，叙述为空时缺席', () => {
    for (const variant of VARIANTS) {
      const withText = payloadOf(variant)
      expect(Array.isArray(withText.sub_table_data._note_texts), variant).toBe(true)
      expect((withText as unknown as Record<string, unknown>)._note_texts, variant).toBeUndefined()

      const blank = payloadOf(variant, ' ')
      expect(blank.sub_table_data._note_texts, variant).toBeUndefined()
    }
  })
})

describe('K7 子表名 ↔ note_template 逐字契约（T7-3 孤儿 TAB 守卫）', () => {
  const listedNames = templateTableNames('note_template_listed.json', K7_NOTE_SECTION.listed)
  const soeNames = templateTableNames('note_template_soe.json', K7_NOTE_SECTION.soe)

  it('上市「递延收益」逐字存在于 note_template_listed 五、51', () => {
    expect(listedNames.has(K7_SUBTABLE.deferredIncome)).toBe(true)
  })

  it('国企「递延收益」逐字存在于 note_template_soe 八、56', () => {
    expect(soeNames.has(K7_SUBTABLE.deferredIncome)).toBe(true)
  })

  it('负向：国企 10 列「其中：递延收益-政府补助情况」底稿无录入表 → 不推、不造列', () => {
    expect(soeNames.has('其中：递延收益-政府补助情况')).toBe(true)
    expect(Object.values(K7_SUBTABLE)).not.toContain('其中：递延收益-政府补助情况')
    expect(dataKeys(payloadOf('soe').sub_table_data)).not.toContain('其中：递延收益-政府补助情况')
  })

  it('负向：旧实现推的英文键 `rows` 不是任何模板表名', () => {
    expect(listedNames.has('rows')).toBe(false)
    expect(soeNames.has('rows')).toBe(false)
  })
})
