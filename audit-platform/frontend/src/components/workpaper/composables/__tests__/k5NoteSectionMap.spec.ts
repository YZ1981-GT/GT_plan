import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  buildK5ListedColumns,
  buildK5SoeColumns,
  buildK5SyncPayload,
  K5_DISCLOSURE_SHEET_NAME,
  K5_NOTE_SECTION,
  K5_SUBTABLE,
  type K5DisclosureRow,
  type K5DisclosureVariant,
} from '../k5NoteSectionMap'
import type { ColumnDef } from '../disclosureColumnDefs'

/**
 * K5 预计负债披露 columns 契约
 *
 * spec `disclosure-columns-coverage-rollout` design §批 2 列头清查 §4（上市）/§5（国企）
 * 口径证据：源 `K 管理循环/K5 预计负债.xlsx` 两张披露 sheet +
 *   `附注模版/上市报表附注.md` L4930 / `国企报表附注.md` L3952 +
 *   `note_template_{listed,soe}.json` 五、50 / 八、55 + consol 五-50-1 / 五-56-1 +
 *   校验预设 F50-1/2/3（2 个数值列 + 合计行，无变动表）。
 *
 * 覆盖 T5 八族断言，重点是 **T4 变体列集差异**：上市 3 值列（末列 `形成原因`）/
 * 国企 2 值列（国企源 xlsx D6 有 `形成原因`，但附注模版 + note_template + consol
 * 三家都只有 3 列，形成原因降级为表下注文字 L3964）。
 */

const SNAKE_CASE = /^[a-z_][a-z0-9_]*$/
const VARIANTS = ['listed', 'soe'] as const

const rows: K5DisclosureRow[] = [
  { project: '未决诉讼', endAmount: 1000, priorAmount: 800, reason: '被诉侵权' },
  { project: '产品质量保证', endAmount: 500, priorAmount: 400, reason: '三包义务' },
]

function payloadOf(variant: K5DisclosureVariant, narrative = '预计负债主要为未决诉讼。') {
  return buildK5SyncPayload(variant, 'wp-k5', rows, narrative)
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

describe('K5 预计负债披露 columns 契约', () => {
  it('上市：4 列（项目 / 期末余额 / 上年年末余额 / 形成原因），金额列取附注模版口径', () => {
    const cols = buildK5ListedColumns()[K5_SUBTABLE.provision]
    expect(cols.map(c => c.label)).toEqual(['项目', '期末余额', '上年年末余额', '形成原因'])
    expect(cols.map(c => c.key)).toEqual(['label', 'end_amount', 'prior_amount', 'reason'])
    expect(cols[0].is_label).toBe(true)
    expect(cols[1].format).toBe('amount')
    expect(cols[2].format).toBe('amount')
    expect(cols[3].format).toBe('text')
    // 负向：源 xlsx B6/C6 的 `期末数`/`期初数` 被裁决掉（上市按附注模版取「上年年末余额」）
    expect(cols.map(c => c.label)).not.toContain('期末数')
    expect(cols.map(c => c.label)).not.toContain('期初数')
    // 负向：预设 F50-3 无变动表 → 底稿 roll-forward 的两列不进附注
    expect(cols.map(c => c.label)).not.toContain('本期增加')
    expect(cols.map(c => c.label)).not.toContain('本期减少')
  })

  it('国企：3 列，**不带**「形成原因」（源 xlsx D6 有但附注三源都只有 3 列）', () => {
    const cols = buildK5SoeColumns()[K5_SUBTABLE.provision]
    expect(cols.map(c => c.label)).toEqual(['项目', '期末余额', '期初余额'])
    expect(cols.map(c => c.key)).toEqual(['label', 'end_amount', 'prior_amount'])
    expect(cols).toHaveLength(3)
    // 负向：照抄上市会多出第 3 值列 → `remark` 溢出（表面仍渲染 3 列，肉眼极难发现）
    expect(cols.map(c => c.label)).not.toContain('形成原因')
    expect(cols.map(c => c.key)).not.toContain('reason')
    // 负向：底稿 UI 的「确认依据」「风险等级」是审计列，附注无落点
    expect(cols.map(c => c.label)).not.toContain('确认依据')
    expect(cols.map(c => c.label)).not.toContain('风险等级')
  })

  it('Property 1：两版 columns 键与 sub_table_data 数据键集合相等', () => {
    for (const variant of VARIANTS) {
      const { sub_table_data, columns } = payloadOf(variant)
      expect(dataKeys(sub_table_data), variant).toEqual([K5_SUBTABLE.provision])
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

  it('单行表头：每表至少一列 flat，且无一列带 group', () => {
    for (const variant of VARIANTS) {
      const { columns } = payloadOf(variant)
      for (const [name, defs] of Object.entries(columns)) {
        expect(defs.some(d => d.flat === true), `${variant}.${name} 未声明 flat`).toBe(true)
        expect(defs.filter(d => d.group !== undefined), `${variant}.${name}`).toHaveLength(0)
      }
    }
  })

  it('位置对齐：每行 values 长度 = 该表非标签列数', () => {
    for (const variant of VARIANTS) {
      const { sub_table_data, columns } = payloadOf(variant)
      for (const key of dataKeys(sub_table_data)) {
        const defs = columns[key] as ColumnDef[]
        const valueColCount = defs.filter(d => !d.is_label).length
        const tableRows = sub_table_data[key] as Array<{ label: unknown; values: unknown[] }>
        expect(tableRows.length, `${variant}.${key}`).toBeGreaterThan(0)
        for (const r of tableRows) {
          expect(r.values.length, `${variant}.${key} 行「${String(r.label)}」`).toBe(valueColCount)
        }
      }
    }
  })

  it('位置对齐（上市变体守卫）：行 values = [期末余额, 上年年末余额, 形成原因]', () => {
    const { sub_table_data } = payloadOf('listed')
    const tableRows = sub_table_data[K5_SUBTABLE.provision] as Array<{ label: string; values: unknown[] }>
    expect(tableRows[0].label).toBe('未决诉讼')
    expect(tableRows[0].values).toEqual([1000, 800, '被诉侵权'])
    expect(tableRows[tableRows.length - 1].values).toEqual([1500, 1200, ''])
  })

  it('位置对齐（国企变体守卫）：行 values = [期末余额, 期初余额]，形成原因不得溢出', () => {
    const { sub_table_data } = payloadOf('soe')
    const tableRows = sub_table_data[K5_SUBTABLE.provision] as Array<{ label: string; values: unknown[] }>
    expect(tableRows[0].label).toBe('未决诉讼')
    expect(tableRows[0].values).toEqual([1000, 800])
    expect(tableRows[0].values).not.toContain('被诉侵权')
    expect(tableRows[tableRows.length - 1].values).toEqual([1500, 1200])
  })

  it('合计行：金额为明细行之和且带 is_total', () => {
    const { sub_table_data } = payloadOf('soe')
    const tableRows = sub_table_data[K5_SUBTABLE.provision] as Array<{ label: string; is_total?: boolean }>
    const total = tableRows[tableRows.length - 1]
    expect(total.label).toBe('合计')
    expect(total.is_total).toBe(true)
  })

  it('表名 / sheet 名 / section_id 全部引用常量（禁字面量，R8/T7-6）', () => {
    for (const variant of VARIANTS) {
      const payload = payloadOf(variant)
      expect(payload.sheet_name, variant).toBe(K5_DISCLOSURE_SHEET_NAME[variant])
      expect(payload.section_id, variant).toBe(K5_NOTE_SECTION[variant])
      expect(dataKeys(payload.sub_table_data), variant).toEqual([K5_SUBTABLE.provision])
    }
  })

  it('`_note_texts` 落在 sub_table_data 内，叙述为空时缺席', () => {
    for (const variant of VARIANTS) {
      const withText = payloadOf(variant)
      expect(Array.isArray(withText.sub_table_data._note_texts), variant).toBe(true)
      expect((withText as unknown as Record<string, unknown>)._note_texts, variant).toBeUndefined()

      const blank = payloadOf(variant, '  \n ')
      expect(blank.sub_table_data._note_texts, variant).toBeUndefined()
    }
  })
})

describe('K5 子表名 ↔ note_template 逐字契约（T7-3 孤儿 TAB 守卫）', () => {
  const listedNames = templateTableNames('note_template_listed.json', K5_NOTE_SECTION.listed)
  const soeNames = templateTableNames('note_template_soe.json', K5_NOTE_SECTION.soe)

  it('上市「预计负债」逐字存在于 note_template_listed 五、50 的 tables[].name', () => {
    expect(listedNames.has(K5_SUBTABLE.provision)).toBe(true)
  })

  it('国企「预计负债」逐字存在于 note_template_soe 八、55 的 tables[].name', () => {
    expect(soeNames.has(K5_SUBTABLE.provision)).toBe(true)
  })

  it('负向：旧实现推的英文键 `rows` 不是任何模板表名', () => {
    expect(listedNames.has('rows')).toBe(false)
    expect(soeNames.has('rows')).toBe(false)
  })
})
