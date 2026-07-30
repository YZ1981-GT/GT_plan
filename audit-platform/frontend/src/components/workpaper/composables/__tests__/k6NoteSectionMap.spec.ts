import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  buildK6ListedColumns,
  buildK6SoeColumns,
  buildK6SyncPayload,
  K6_DISCLOSURE_SHEET_NAME,
  K6_NOTE_SECTION,
  K6_SUBTABLE,
  type K6DisclosureRow,
  type K6DisclosureVariant,
} from '../k6NoteSectionMap'
import type { ColumnDef } from '../disclosureColumnDefs'

/**
 * K6 持有待售资产披露 columns 契约
 *
 * spec `disclosure-columns-coverage-rollout` design §批 2 列头清查 §6（上市）/§7（国企）
 * 口径证据：源 `K 管理循环/K6 持有待售资产和负债.xlsx` 两张披露 sheet 的表头行合并区
 *   （上市 `A6:A7` + `B6:D6` + `E6:G6`；国企 `A9:A10` + `B9:D9` + `E9:G9`）+
 *   `附注模版/上市报表附注.md` L2726/L2728、`国企报表附注.md` L2319/L2321 +
 *   `note_template_{listed,soe}.json` 五、11 / 八、12 + 校验预设 F11-1/1a/3/4。
 *
 * **本批唯一两行表头 + 唯一需 `group` 的表** → 断言方向与其余 6 张表相反：
 *   无一列 `flat`、恰好 2 个 group、同 group 列索引相邻（Property 3）。
 * 决策 A1：上年年末（期初）`账面余额`/`减值准备` 无录入来源 → 推 `null`（禁造 `0`）。
 */

const SNAKE_CASE = /^[a-z_][a-z0-9_]*$/
const VARIANTS = ['listed', 'soe'] as const

const rows: K6DisclosureRow[] = [
  { project: '（一）持有待售的固定资产', bookValue: 900, impairment: 100, openingBalance: 1200 },
  { project: '其中：生产厂房', bookValue: 400, impairment: 50, openingBalance: 600 },
]

function payloadOf(variant: K6DisclosureVariant, narrative = '拟出售厂房已签订不可撤销转让协议。') {
  return buildK6SyncPayload(variant, 'wp-k6', rows, narrative)
}

function dataKeys(sub: Record<string, unknown>): string[] {
  return Object.keys(sub).filter(k => !k.startsWith('_')).sort()
}

/** 同 group 值的列索引是否连续（Property 3） */
function groupRanges(defs: ColumnDef[]): Array<{ group: string; start: number; span: number }> {
  const out: Array<{ group: string; start: number; span: number }> = []
  defs.forEach((d, i) => {
    if (!d.group) return
    const last = out[out.length - 1]
    if (last && last.group === d.group && last.start + last.span === i) last.span += 1
    else out.push({ group: d.group, start: i, span: 1 })
  })
  return out
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

describe('K6 持有待售资产披露 columns 契约', () => {
  it('上市：7 列两级表头，父表头「期末余额」/「上年年末余额」各 span=3', () => {
    const cols = buildK6ListedColumns()[K6_SUBTABLE.listed]
    expect(cols.map(c => c.label)).toEqual([
      '项目', '账面余额', '减值准备', '账面价值', '账面余额', '减值准备', '账面价值',
    ])
    expect(cols.map(c => c.key)).toEqual([
      'label', 'end_gross', 'end_impairment', 'end_book', 'prior_gross', 'prior_impairment', 'prior_book',
    ])
    expect(cols.map(c => c.group)).toEqual([
      undefined, '期末余额', '期末余额', '期末余额', '上年年末余额', '上年年末余额', '上年年末余额',
    ])
    expect(groupRanges(cols)).toEqual([
      { group: '期末余额', start: 1, span: 3 },
      { group: '上年年末余额', start: 4, span: 3 },
    ])
    // 负向：父表头不得取源 xlsx 的「期末数/上年年末数」（上市按附注模版 L2726）
    expect(cols.map(c => c.group)).not.toContain('期末数')
    expect(cols.map(c => c.group)).not.toContain('上年年末数')
  })

  it('国企：7 列两级表头，父表头「期末数」/「期初数」（三源一致，不用「余额」）', () => {
    const cols = buildK6SoeColumns()[K6_SUBTABLE.soe]
    expect(cols.map(c => c.label)).toEqual([
      '项目', '账面余额', '减值准备', '账面价值', '账面余额', '减值准备', '账面价值',
    ])
    expect(cols.map(c => c.group)).toEqual([
      undefined, '期末数', '期末数', '期末数', '期初数', '期初数', '期初数',
    ])
    expect(groupRanges(cols)).toEqual([
      { group: '期末数', start: 1, span: 3 },
      { group: '期初数', start: 4, span: 3 },
    ])
    // 负向：父表头两版不同，禁抽共享常量（照抄上市即错）
    expect(cols.map(c => c.group)).not.toContain('期末余额')
    expect(cols.map(c => c.group)).not.toContain('上年年末余额')
  })

  it('同名子列不去重、不加期别前缀（靠 end_*/prior_* 两组 key 区分）', () => {
    for (const variant of VARIANTS) {
      const cols = payloadOf(variant).columns[K6_SUBTABLE[variant]]
      expect(cols[1].label, variant).toBe(cols[4].label)
      expect(cols[2].label, variant).toBe(cols[5].label)
      expect(cols[3].label, variant).toBe(cols[6].label)
      expect(cols[1].key, variant).not.toBe(cols[4].key)
      // 负向：加前缀＝压平＋杜撰
      for (const bad of ['期末账面余额', '期末减值准备', '期末账面价值', '期初账面余额', '上年年末账面价值']) {
        expect(cols.map(c => c.label), `${variant} 不得出现压平串 ${bad}`).not.toContain(bad)
      }
    }
  })

  it('Property 3（反向断言）：无一列 flat、恰好 2 个 group、同 group 列索引相邻', () => {
    for (const variant of VARIANTS) {
      const { columns } = payloadOf(variant)
      for (const [name, defs] of Object.entries(columns)) {
        // 两行表头的表**不能**标 flat（会被显式抑制成单级）
        expect(defs.filter(d => d.flat === true), `${variant}.${name} 误标 flat`).toHaveLength(0)
        const distinct = [...new Set(defs.filter(d => d.group).map(d => d.group as string))]
        expect(distinct, `${variant}.${name}`).toHaveLength(2)
        // 相邻性：分组区间数必须等于 distinct group 数，否则区间被拆碎
        const ranges = groupRanges(defs)
        expect(ranges, `${variant}.${name} 同 group 列不相邻`).toHaveLength(2)
        for (const r of ranges) {
          expect(r.start, `${variant}.${name}.${r.group}`).toBeGreaterThanOrEqual(1)
          expect(r.start + r.span, `${variant}.${name}.${r.group}`).toBeLessThanOrEqual(defs.length)
        }
      }
    }
  })

  it('Property 1：两版 columns 键与 sub_table_data 数据键集合相等（表名按变体不同）', () => {
    for (const variant of VARIANTS) {
      const { sub_table_data, columns } = payloadOf(variant)
      expect(dataKeys(sub_table_data), variant).toEqual([K6_SUBTABLE[variant]])
      expect(Object.keys(columns).sort(), variant).toEqual(dataKeys(sub_table_data))
    }
    // 上市/国企表名确实不同源（五、11 vs 八、12），不是同一串
    expect(K6_SUBTABLE.listed).not.toBe(K6_SUBTABLE.soe)
  })

  it('Property 2：每张表恰好 1 个 is_label 且位于索引 0', () => {
    for (const variant of VARIANTS) {
      const { columns } = payloadOf(variant)
      for (const [name, defs] of Object.entries(columns)) {
        expect(defs.filter(d => d.is_label === true), `${variant}.${name}`).toHaveLength(1)
        expect(defs[0].is_label, `${variant}.${name}`).toBe(true)
        // 标签列不带 group（否则 _column_groups 会覆盖标签列）
        expect(defs[0].group, `${variant}.${name}`).toBeUndefined()
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

  it('位置对齐：每行 values 长度 = 6（该表非标签列数）', () => {
    for (const variant of VARIANTS) {
      const { sub_table_data, columns } = payloadOf(variant)
      for (const key of dataKeys(sub_table_data)) {
        const defs = columns[key] as ColumnDef[]
        const valueColCount = defs.filter(d => !d.is_label).length
        expect(valueColCount, `${variant}.${key}`).toBe(6)
        const tableRows = sub_table_data[key] as Array<{ label: unknown; values: unknown[] }>
        expect(tableRows.length, `${variant}.${key}`).toBeGreaterThan(0)
        for (const r of tableRows) {
          expect(r.values.length, `${variant}.${key} 行「${String(r.label)}」`).toBe(valueColCount)
        }
      }
    }
  })

  it('位置对齐（值映射守卫）：values = [账面余额, 减值准备, 账面价值, null, null, 期初账面价值]', () => {
    for (const variant of VARIANTS) {
      const { sub_table_data } = payloadOf(variant)
      const tableRows = sub_table_data[K6_SUBTABLE[variant]] as Array<{ label: string; values: unknown[] }>
      expect(tableRows[0].label, variant).toBe('（一）持有待售的固定资产')
      // F11-4：账面余额 − 减值准备 = 账面价值（1000 − 100 = 900）
      expect(tableRows[0].values, variant).toEqual([1000, 100, 900, null, null, 1200])
      const total = tableRows[tableRows.length - 1] as { label: string; values: unknown[]; is_total?: boolean }
      expect(total.label, variant).toBe('合计')
      expect(total.is_total, variant).toBe(true)
      expect(total.values, variant).toEqual([1450, 150, 1300, null, null, 1800])
    }
  })

  it('决策 A1：上期账面余额/减值准备为**恰好 null**，不得被写成 0（0 = 杜撰数字）', () => {
    for (const variant of VARIANTS) {
      const { sub_table_data } = payloadOf(variant)
      const tableRows = sub_table_data[K6_SUBTABLE[variant]] as Array<{ label: string; values: unknown[] }>
      for (const r of tableRows) {
        expect(r.values[3], `${variant} 行「${r.label}」prior_gross`).toBeNull()
        expect(r.values[4], `${variant} 行「${r.label}」prior_impairment`).toBeNull()
        expect(r.values[3], `${variant} 行「${r.label}」prior_gross 不得为 0`).not.toBe(0)
        expect(r.values[4], `${variant} 行「${r.label}」prior_impairment 不得为 0`).not.toBe(0)
      }
    }
  })

  it('表名 / sheet 名 / section_id 全部引用常量（禁字面量，R8/T7-6）', () => {
    for (const variant of VARIANTS) {
      const payload = payloadOf(variant)
      expect(payload.sheet_name, variant).toBe(K6_DISCLOSURE_SHEET_NAME[variant])
      expect(payload.section_id, variant).toBe(K6_NOTE_SECTION[variant])
      expect(dataKeys(payload.sub_table_data), variant).toEqual([K6_SUBTABLE[variant]])
    }
  })

  it('`_note_texts` 落在 sub_table_data 内，叙述为空时缺席', () => {
    for (const variant of VARIANTS) {
      const withText = payloadOf(variant)
      expect(Array.isArray(withText.sub_table_data._note_texts), variant).toBe(true)
      expect((withText as unknown as Record<string, unknown>)._note_texts, variant).toBeUndefined()

      const blank = payloadOf(variant, '\t ')
      expect(blank.sub_table_data._note_texts, variant).toBeUndefined()
    }
  })
})

describe('K6 子表名 ↔ note_template 逐字契约（T7-3 孤儿 TAB 守卫）', () => {
  const listedNames = templateTableNames('note_template_listed.json', K6_NOTE_SECTION.listed)
  const soeNames = templateTableNames('note_template_soe.json', K6_NOTE_SECTION.soe)

  it('上市「持有待售资产和持有待售负债」逐字存在于 note_template_listed 五、11', () => {
    expect(listedNames.has(K6_SUBTABLE.listed)).toBe(true)
  })

  it('国企「持有待售资产」逐字存在于 note_template_soe 八、12', () => {
    expect(soeNames.has(K6_SUBTABLE.soe)).toBe(true)
  })

  it('负向：不推「持有待售资产减值准备」（决策 B1：模板 name↔rows 错位，推了会把负债塞进减值表）', () => {
    // 该表名在模板里确实存在，正是为什么必须显式不推
    expect(listedNames.has('持有待售资产减值准备')).toBe(true)
    for (const variant of VARIANTS) {
      expect(Object.values(K6_SUBTABLE), variant).not.toContain('持有待售资产减值准备')
      expect(dataKeys(buildK6SyncPayload(variant, 'wp-k6', rows, '').sub_table_data), variant)
        .not.toContain('持有待售资产减值准备')
    }
  })

  it('负向：旧实现推的英文键 `rows` 不是任何模板表名', () => {
    expect(listedNames.has('rows')).toBe(false)
    expect(soeNames.has('rows')).toBe(false)
  })
})
