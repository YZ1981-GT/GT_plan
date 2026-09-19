import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  buildK6ListedColumns,
  buildK6SoeColumns,
  buildK6SoeLiabilityColumns,
  buildK6SoeLiabilityPayload,
  buildK6SyncPayload,
  impairmentEndAmount,
  K6_DISCLOSURE_SHEET_NAME,
  K6_LEGACY_OBSOLETE_TABLES,
  K6_LISTED_SUBTABLE,
  K6_NOTE_SECTION,
  K6_SOE_LIABILITY_NOTE_SECTION,
  K6_SOE_LIABILITY_SUBTABLE,
  K6_SOE_SUBTABLE,
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

  it('Property 3：每张表在 group / flat 之间明确表态，同 group 列索引相邻', () => {
    for (const variant of VARIANTS) {
      const all = variant === 'listed' ? buildK6ListedColumns() : buildK6SoeColumns()
      for (const [name, defs] of Object.entries(all)) {
        const hasFlat = defs.some(d => d.flat === true)
        const ranges = groupRanges(defs)
        expect(hasFlat && ranges.length > 0, `${variant}.${name} flat 与 group 并存`).toBe(false)
        expect(hasFlat || ranges.length > 0, `${variant}.${name} 未表态`).toBe(true)
        for (const r of ranges) {
          expect(r.start, `${variant}.${name}.${r.group}`).toBeGreaterThanOrEqual(1)
          expect(r.start + r.span, `${variant}.${name}.${r.group}`).toBeLessThanOrEqual(defs.length)
        }
      }
    }
  })

  it('Property 3（主表反向断言）：两行表头的主表不得标 flat，恰好 2 个 group', () => {
    for (const variant of VARIANTS) {
      const defs = payloadOf(variant).columns[K6_SUBTABLE[variant]]
      expect(defs.filter(d => d.flat === true), `${variant} 主表误标 flat`).toHaveLength(0)
      expect(groupRanges(defs), `${variant} 主表分组`).toHaveLength(2)
    }
  })

  it('Property 1：columns 键 ⊇ sub_table_data 数据键（推了的表必有列定义）', () => {
    for (const variant of VARIANTS) {
      const { sub_table_data, columns } = payloadOf(variant)
      expect(dataKeys(sub_table_data), variant).toContain(K6_SUBTABLE[variant])
      expect(Object.keys(columns).sort(), variant).toEqual(dataKeys(sub_table_data))
    }
    // 上市/国企表名确实不同源（五、11 vs 八、12），不是同一串
    expect(K6_SUBTABLE.listed).not.toBe(K6_SUBTABLE.soe)
  })

  it('Property 2：每张表恰好 1 个 is_label 且位于索引 0', () => {
    for (const variant of VARIANTS) {
      const columns = variant === 'listed' ? buildK6ListedColumns() : buildK6SoeColumns()
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
      const columns = {
        ...(variant === 'listed' ? buildK6ListedColumns() : buildK6SoeColumns()),
        ...(variant === 'soe' ? buildK6SoeLiabilityColumns() : {}),
      }
      for (const [name, defs] of Object.entries(columns)) {
        for (const d of defs) {
          expect(d.label.trim(), `${variant}.${name}.${d.key}`).not.toBe('')
          expect(SNAKE_CASE.test(d.label), `${variant}.${name}.${d.key} 用了字段键当列头`).toBe(false)
        }
      }
    }
  })

  it('位置对齐：主表每行 values 长度 = 6（该表非标签列数）', () => {
    for (const variant of VARIANTS) {
      const { sub_table_data, columns } = payloadOf(variant)
      const key = K6_SUBTABLE[variant]
      const defs = columns[key] as ColumnDef[]
      const valueColCount = defs.filter(d => !d.is_label).length
      expect(valueColCount, `${variant}.${key}`).toBe(6)
      const tableRows = sub_table_data[key] as Array<{ label: unknown; values: unknown[] }>
      expect(tableRows.length, `${variant}.${key}`).toBeGreaterThan(0)
      for (const r of tableRows) {
        expect(r.values.length, `${variant}.${key} 行「${String(r.label)}」`).toBe(valueColCount)
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
      expect(dataKeys(payload.sub_table_data), variant).toContain(K6_SUBTABLE[variant])
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

  it('上市 5 张子表名全部逐字存在于 五、11（含 2026-07-31 正名的 4 张）', () => {
    for (const name of Object.values(K6_LISTED_SUBTABLE)) {
      expect(listedNames.has(name), `模板缺表「${name}」`).toBe(true)
    }
    expect(listedNames.size).toBe(Object.keys(K6_LISTED_SUBTABLE).length)
  })

  it('国企 4 张子表名（八、12 资产）+ 1 张（八、43 负债）逐字存在', () => {
    for (const name of Object.values(K6_SOE_SUBTABLE)) {
      expect(soeNames.has(name), `模板缺表「${name}」`).toBe(true)
    }
    expect(soeNames.size).toBe(Object.keys(K6_SOE_SUBTABLE).length)
    const liabNames = templateTableNames('note_template_soe.json', K6_SOE_LIABILITY_NOTE_SECTION)
    expect(liabNames.has(K6_SOE_LIABILITY_SUBTABLE.liability)).toBe(true)
  })

  it('负向：md 重建的垃圾表名已从模板消失，且进 _removed_table_keys 清理历史推送', () => {
    // 上市：段落文本泄漏名 / 示例处置组名 / 表头首格泄漏名
    for (const legacy of K6_LEGACY_OBSOLETE_TABLES.listed) {
      expect(listedNames.has(legacy), `垃圾表名「${legacy}」仍在模板里`).toBe(false)
    }
    for (const legacy of K6_LEGACY_OBSOLETE_TABLES.soe) {
      expect(soeNames.has(legacy), `假名「${legacy}」仍在模板里`).toBe(false)
    }
    for (const variant of VARIANTS) {
      const removed = (payloadOf(variant).sub_table_data._removed_table_keys ?? []) as string[]
      for (const legacy of K6_LEGACY_OBSOLETE_TABLES[variant]) {
        expect(removed, `${variant} 未清理旧表名「${legacy}」`).toContain(legacy)
      }
    }
  })

  it('负向：本次推送的键绝不进 _removed_table_keys（否则刚推就被删）', () => {
    for (const variant of VARIANTS) {
      const p = payloadOf(variant)
      const removed = (p.sub_table_data._removed_table_keys ?? []) as string[]
      for (const pushed of dataKeys(p.sub_table_data)) {
        expect(removed, `${variant} 推送键「${pushed}」误入 removed`).not.toContain(pushed)
      }
    }
  })

  it('🔴 上市 tables[1] 的 name↔rows 错位已修：「持有待售负债」是独立表且 3 列', () => {
    expect(listedNames.has(K6_LISTED_SUBTABLE.liability)).toBe(true)
    const cols = buildK6ListedColumns()[K6_LISTED_SUBTABLE.liability]
    expect(cols.map(c => c.label)).toEqual(['项目', '期末余额', '上年年末余额'])
    // 减值准备表是另一张、6 列含「本期减少」二级拆分
    const imp = buildK6ListedColumns()[K6_LISTED_SUBTABLE.impairment]
    expect(imp.map(c => c.label)).toEqual([
      '项目', '上年年末数', '本期增加', '本期转回', '本期出售', '期末数',
    ])
    expect(groupRanges(imp)).toEqual([{ group: '本期减少', start: 3, span: 2 }])
  })

  it('减值准备派生列：期末 = 期初 + 本期增加 − 本期转回 − 本期出售', () => {
    expect(impairmentEndAmount({
      project: '固定资产', priorAmount: 1000, increase: 500, reverse: 200, disposal: 100,
    })).toBe(1200)
  })

  it('🔴 负债空行时默认发清理载荷（否则附注 §八、43 永久残留过时明细）', () => {
    // 默认 clearWhenEmpty=true → 无条件清理（实测：不发就残留，且 last_sync_at 不前移）
    const clear = buildK6SoeLiabilityPayload('wp-k6', [])
    expect(clear).not.toBeNull()
    // 显式关闭才不动该节（当前无消费方，保留给「明确不想动」的调用方）
    expect(buildK6SoeLiabilityPayload('wp-k6', [], '', { clearWhenEmpty: false })).toBeNull()
    expect(clear!.section_id).toBe(K6_SOE_LIABILITY_NOTE_SECTION)
    expect(clear!.sub_table_data._removed_table_keys).toEqual([
      K6_SOE_LIABILITY_SUBTABLE.liability,
    ])
    expect(dataKeys(clear!.sub_table_data)).toEqual([])
    expect(clear!.columns).toEqual({})
  })

  it('国企负债是独立章节 八、43 —— 必须单独 POST', () => {
    expect(K6_SOE_LIABILITY_NOTE_SECTION).not.toBe(K6_NOTE_SECTION.soe)
    const p = buildK6SoeLiabilityPayload('wp-k6', [
      { project: '应付账款', endBook: 300, endFairValue: 320, disposalFee: 10, timetable: '2026年6月' },
    ])
    expect(p).not.toBeNull()
    expect(p!.section_id).toBe(K6_SOE_LIABILITY_NOTE_SECTION)
    expect(p!.sheet_name).toBe(K6_DISCLOSURE_SHEET_NAME.soe)
    expect(dataKeys(p!.sub_table_data)).toEqual([K6_SOE_LIABILITY_SUBTABLE.liability])
    // 国企「预计处置费用」≠ 上市「预计出售费用」（源模板用语不同）
    expect(p!.columns[K6_SOE_LIABILITY_SUBTABLE.liability].map(c => c.label)).toEqual([
      '项目', '期末账面价值', '期末公允价值', '预计处置费用', '时间安排',
    ])
    expect(buildK6ListedColumns()[K6_LISTED_SUBTABLE.nonCurrent].map(c => c.label)).toContain(
      '预计出售费用',
    )
  })

  it('条件区块无行 → 不推空表（防整表覆盖模板骨架）并进 removed', () => {
    const p = buildK6SyncPayload('soe', 'wp-k6', { assets: rows })
    const T = K6_SOE_SUBTABLE
    const removed = (p.sub_table_data._removed_table_keys ?? []) as string[]
    for (const name of [T.impairment, T.nonCurrent, T.disposalGroup]) {
      expect(p.sub_table_data[name]).toBeUndefined()
      expect(p.columns[name]).toBeUndefined()
      expect(removed).toContain(name)
    }
    expect(p.sub_table_data[T.main]).toBeDefined()
  })

  it('有行时条件区块正常推送（含合计行）', () => {
    const p = buildK6SyncPayload('soe', 'wp-k6', {
      assets: rows,
      impairment: [{ project: '固定资产', priorAmount: 1000, increase: 500, reverse: 200, disposal: 100 }],
      nonCurrent: [{ project: '生产厂房', endBook: 900, endFairValue: 1000, disposalFee: 20, timetable: '2026年6月' }],
    })
    const T = K6_SOE_SUBTABLE
    const imp = p.sub_table_data[T.impairment] as Array<Record<string, unknown>>
    expect(imp).toHaveLength(2)
    expect(imp[0]).toMatchObject({ label: '固定资产', end_amount: 1200 })
    expect(imp[1]).toMatchObject({ label: '合计', is_total: true, end_amount: 1200 })
    const nc = p.sub_table_data[T.nonCurrent] as Array<Record<string, unknown>>
    expect(nc[0]).toMatchObject({ label: '生产厂房', end_book: 900, timetable: '2026年6月' })
    expect(p.columns[T.impairment]).toBeDefined()
  })

  it('旧签名 `(variant, wpId, rows[], narrative)` 仍兼容（组件未改造期间不炸）', () => {
    const p = buildK6SyncPayload('listed', 'wp-k6', rows, '说明文字')
    expect(dataKeys(p.sub_table_data)).toContain(K6_SUBTABLE.listed)
    expect(p.sub_table_data._note_texts).toEqual([
      { section: 'note-held-for-sale', title: '持有待售资产说明', text: '说明文字' },
    ])
  })

  it('负向：旧实现推的英文键 `rows` 不是任何模板表名', () => {
    expect(listedNames.has('rows')).toBe(false)
    expect(soeNames.has('rows')).toBe(false)
  })
})
