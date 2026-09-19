/**
 * K1 披露子表名 ↔ 附注模板契约
 *
 * 防回归：`K1_LISTED_SUBTABLE` / `K1_SOE_SUBTABLE` 的每个值必须能在
 * `note_template_listed.json` §五、8 / `note_template_soe.json` §八、9
 * 的 `tables[].name` 中找到，否则 sync-from-workpaper 会写出孤儿子表
 * （附注 TAB 永空，底稿数据丢失）。
 *
 * spec: k1-other-receivable-disclosure-alignment Task 3.3
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  K1_LISTED_SUBTABLE,
  K1_NOTE_SECTION,
  K1_SOE_SUBTABLE,
} from '../k1NoteSectionMap'
import {
  K1_LISTED_COLUMNS,
  K1_SOE_COLUMNS,
  buildK1ListedSubTableData,
  buildK1SoeSubTableData,
} from '../k1DisclosureSyncPayload'
import { emptyK1ListedPayload, emptyK1SoePayload } from '../k1DisclosureModel'
import type { ColumnDef } from '../disclosureColumnDefs'

interface NoteTable { name?: string; headers?: string[]; guidance?: string; _column_groups?: unknown }
interface NoteSection { section_number?: string; tables?: NoteTable[]; text_sections?: string[] }

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

function loadSection(file: string, sectionNumber: string): NoteSection {
  const path = resolve(REPO_ROOT, 'backend/data', file)
  const raw = JSON.parse(readFileSync(path, 'utf-8')) as { sections: NoteSection[] }
  const hit = raw.sections.find((s) => String(s.section_number ?? '').trim() === sectionNumber)
  if (!hit) throw new Error(`${file} 缺少章节 ${sectionNumber}`)
  return hit
}

const listedSection = loadSection('note_template_listed.json', K1_NOTE_SECTION.listed)
const soeSection = loadSection('note_template_soe.json', K1_NOTE_SECTION.soe)

const listedNames = new Set((listedSection.tables ?? []).map((t) => t.name))
const soeNames = new Set((soeSection.tables ?? []).map((t) => t.name))

function firstHeader(section: NoteSection, name: string): string | undefined {
  return (section.tables ?? []).find((t) => t.name === name)?.headers?.[0]
}

describe('K1 子表名 ↔ note_template 契约', () => {
  it.each(Object.entries(K1_LISTED_SUBTABLE))(
    '上市 %s → 「%s」存在于 §五、8',
    (_key, name) => {
      expect(listedNames.has(name)).toBe(true)
    },
  )

  it.each(Object.entries(K1_SOE_SUBTABLE))(
    '国企 %s → 「%s」存在于 §八、9',
    (_key, name) => {
      expect(soeNames.has(name)).toBe(true)
    },
  )
})

describe('附注 §五、8 / §八、9 结构要求', () => {
  it('两级表头表必须带 _column_groups', () => {
    const needGroups = [
      ...(listedSection.tables ?? []).filter((t) => [
        '按款项性质披露',
        // 🔴 2026-07-31 补：源 xlsx 上市 A91:E92 是两行表头（阶段名 + ECL 释义），
        // 模板与载荷原先都压成单级 5 列 → 第二行释义整行丢失
        K1_LISTED_SUBTABLE.stageMovement,
      ].includes(String(t.name))),
      ...(soeSection.tables ?? []).filter((t) => [
        // 🔴 「按账龄披露其他应收款项」已按源 xlsx A6:C15 还原为**单级 3 列**
        // （原 5 列结构不在源模板里）→ 已移出本清单，改由下方 flat 断言反向锁死
        K1_SOE_SUBTABLE.methodEnd,
        // 🔴 原为裸续表名 `续：`（跨章节撞键 + 附注 TAB 看不出续的是哪张表），
        // 2026-07-31 由 `fix_note_k_complex_structure.py` 正名，引用常量避免再漂移
        K1_SOE_SUBTABLE.methodPrior,
        '单项计提坏账准备的其他应收款项',
        '账龄组合',
        '采用余额百分比法或其他组合方法计提坏账准备的其他应收款项',
      ].includes(String(t.name))),
    ]
    expect(needGroups).toHaveLength(7)
    for (const t of needGroups) {
      expect(Array.isArray(t._column_groups), `${t.name} 缺 _column_groups`).toBe(true)
    }
  })

  it('源模板单级的表必须显式 flat 且无 _column_groups（反向锁死，防被误加两级）', () => {
    const flatTables = [
      K1_SOE_SUBTABLE.aging,          // 源 xlsx A6:C15 = 账 龄 / 期末数 / 期初数
      K1_SOE_SUBTABLE.eclMovement,    // 源 xlsx A63:E63 一行表头（阶段名+释义同格）
      K1_SOE_SUBTABLE.balanceMovement,
    ]
    for (const name of flatTables) {
      const tbl = (soeSection.tables ?? []).find((t) => t.name === name)
      expect(tbl, `模板缺表 ${name}`).toBeDefined()
      expect(tbl!._column_groups, `${name} 不该有 _column_groups`).toBeUndefined()
      expect(K1_SOE_COLUMNS[name][0].flat, `${name} 标签列须打 flat`).toBe(true)
    }
  })

  it('国企账龄表按源模板还原为 3 列（原 5 列结构不在源模板里）', () => {
    const tbl = (soeSection.tables ?? []).find((t) => t.name === K1_SOE_SUBTABLE.aging)
    expect(tbl!.headers).toEqual(['账  龄', '期末数', '期初数'])
    expect(K1_SOE_COLUMNS[K1_SOE_SUBTABLE.aging].map((c) => c.key)).toEqual([
      'label', '期末数', '期初数',
    ])
    // 反向自检：旧的 5 列键不得残留
    expect(K1_SOE_COLUMNS[K1_SOE_SUBTABLE.aging].map((c) => c.key)).not.toContain('期末账面余额')
  })

  it('上市侧补入的 3 张表（源模板 ⑧⑨⑩）子表名与列头对齐模板', () => {
    const added: Array<[string, string[]]> = [
      [K1_LISTED_SUBTABLE.govGrant, [
        '单位名称（注：政府补助的发文单位）', '政府补助项目名称', '期末余额', '账龄',
        '预计收取的时间、金额及依据',
      ]],
      [K1_LISTED_SUBTABLE.transfer, [
        '项  目', '转移方式', '终止确认金额', '与终止确认相关的利得或损失',
      ]],
      [K1_LISTED_SUBTABLE.continuedInvolvement, ['项  目', '期末数']],
    ]
    for (const [name, headers] of added) {
      const tbl = (listedSection.tables ?? []).find((t) => t.name === name)
      expect(tbl, `§五、8 缺表 ${name}`).toBeDefined()
      expect(tbl!.headers, `${name} 模板列头`).toEqual(headers)
      expect(K1_LISTED_COLUMNS[name].map((c) => c.label), `${name} 同步列头`).toEqual(headers)
    }
  })

  it('裸续表名 `续：` 已从模板消失（跨章节撞键 + TAB 上看不出续哪张表）', () => {
    expect((soeSection.tables ?? []).map((t) => String(t.name))).not.toContain('续：')
    expect(K1_SOE_SUBTABLE.methodPrior).toBe('按坏账准备计提方法分类披露其他应收款项（续：期初余额）')
  })

  it('三阶段快照 6 表含第 6 列「理由」（源 xlsx F32/F41/F51/F63/F72/F82，附注模板原缺）', () => {
    const stageTables = [
      K1_LISTED_SUBTABLE.stage1, K1_LISTED_SUBTABLE.stage2, K1_LISTED_SUBTABLE.stage3,
      K1_LISTED_SUBTABLE.priorStage1, K1_LISTED_SUBTABLE.priorStage2, K1_LISTED_SUBTABLE.priorStage3,
    ]
    for (const name of stageTables) {
      const tbl = (listedSection.tables ?? []).find((t) => t.name === name)
      expect(tbl, `模板缺表 ${name}`).toBeDefined()
      expect(tbl!.headers, `${name} 列数`).toHaveLength(6)
      expect(tbl!.headers![5], `${name} 末列`).toBe('理由')
      expect(K1_LISTED_COLUMNS[name].map((c) => c.label), `${name} 同步列头`).toEqual(tbl!.headers)
    }
    // ECL 率表头按阶段不同（第一阶段 = 未来 12 个月内；第二/三阶段 = 整个存续期）
    expect(K1_LISTED_COLUMNS[K1_LISTED_SUBTABLE.stage1][2].label).toContain('未来12个月')
    expect(K1_LISTED_COLUMNS[K1_LISTED_SUBTABLE.stage2][2].label).toContain('整个存续期')
    // `key` 不随表头变（行对象键真源）
    expect(K1_LISTED_COLUMNS[K1_LISTED_SUBTABLE.stage1][2].key).toBe('预期信用损失率')
    expect(K1_LISTED_COLUMNS[K1_LISTED_SUBTABLE.stage2][2].key).toBe('预期信用损失率')
  })

  it('同步 columns 与模板 headers 逐位同形（两侧同一真源，防单边漂移）', () => {
    const pairs: Array<[NoteSection, Record<string, ColumnDef[]>]> = [
      [listedSection, K1_LISTED_COLUMNS],
      [soeSection, K1_SOE_COLUMNS],
    ]
    for (const [section, colMap] of pairs) {
      for (const [name, cols] of Object.entries(colMap)) {
        const tbl = (section.tables ?? []).find((t) => t.name === name)
        expect(tbl, `模板缺表 ${name}`).toBeDefined()
        expect(cols.map((c) => c.label), `${name} 列头漂移`).toEqual(tbl!.headers)
      }
    }
  })

  it('每张同步表在 group / flat 之间明确表态（防前缀推断凭空造父表头）', () => {
    for (const colMap of [K1_LISTED_COLUMNS, K1_SOE_COLUMNS]) {
      for (const [name, cols] of Object.entries(colMap)) {
        const hasFlat = cols.some((c) => c.flat === true)
        const hasGroup = cols.some((c) => c.group)
        expect(hasFlat && hasGroup, `${name} flat 与 group 并存`).toBe(false)
        expect(hasFlat || hasGroup, `${name} 未表态`).toBe(true)
        expect(cols[0].group, `${name} 标签列不得带 group`).toBeUndefined()
      }
    }
  })

  it('headers 无空串（后端 CI 卡点同构校验）', () => {
    for (const section of [listedSection, soeSection]) {
      for (const t of section.tables ?? []) {
        for (const h of t.headers ?? []) {
          expect(String(h ?? '').trim()).not.toBe('')
        }
      }
    }
  })

  it('每张表都有 guidance（TAB 页签编制提示）', () => {
    for (const section of [listedSection, soeSection]) {
      const missing = (section.tables ?? [])
        .filter((t) => !String(t.guidance ?? '').trim())
        .map((t) => t.name)
      expect(missing, `缺 guidance: ${missing.join(' / ')}`).toHaveLength(0)
    }
  })

  it('同步 columns 的标签列头 = 附注 headers[0]（避免 TAB 首列名漂移）', () => {
    const mismatches: string[] = []
    for (const [section, columns] of [
      [listedSection, K1_LISTED_COLUMNS] as const,
      [soeSection, K1_SOE_COLUMNS] as const,
    ]) {
      for (const [name, cols] of Object.entries(columns)) {
        const expected = firstHeader(section, name)
        const actual = cols.find((c) => c.is_label)?.label
        if (expected !== actual) mismatches.push(`${name}: 附注「${expected}」vs 同步「${actual}」`)
      }
    }
    expect(mismatches, mismatches.join(' / ')).toHaveLength(0)
  })

  it('国企 §八、9 含账面余额变动 / 转移 / 继续涉入 / 政府补助四张表', () => {
    for (const name of [
      '其他应收款项账面余额变动',
      '由金融资产转移而终止确认的其他应收款项',
      '其他应收款项转移继续涉入形成的资产、负债的金额',
      '涉及政府补助的应收款项',
    ]) {
      expect(soeNames.has(name), `缺表 ${name}`).toBe(true)
    }
  })

  // ─── k1-extraction-chain-and-note-alignment：openpyxl 直读源 xlsx 逐字比对
  //     （字面钉死，防再次漂移回「账龄」「项目」「类别」等看似合理但错的写法）───
  it('五处标签逐字对齐源 xlsx（Requirement 6.1, 6.3, 6.4, 6.7）', () => {
    // R7：账 龄（单空格）
    expect(firstHeader(listedSection, K1_LISTED_SUBTABLE.aging)).toBe('账 龄')
    // R32/R41/R51/R63/R72/R82：类 别（单空格，国企侧是双空格「类  别」）
    for (const name of [
      K1_LISTED_SUBTABLE.stage1, K1_LISTED_SUBTABLE.stage2, K1_LISTED_SUBTABLE.stage3,
      K1_LISTED_SUBTABLE.priorStage1, K1_LISTED_SUBTABLE.priorStage2, K1_LISTED_SUBTABLE.priorStage3,
    ]) {
      expect(firstHeader(listedSection, name), name).toBe('类 别')
    }
    // R113：项  目（双空格，非「项目」）
    expect(firstHeader(listedSection, K1_LISTED_SUBTABLE.writeoffSummary)).toBe('项  目')
    // F116：款项是否由关联交易产生（比「是否由关联交易产生」多「款项」二字）
    const writeoffDetail = listedSection.tables?.find(
      (t) => t.name === K1_LISTED_SUBTABLE.writeoffDetail,
    )
    expect(writeoffDetail?.headers?.[5]).toBe('款项是否由关联交易产生')
    expect(
      K1_LISTED_COLUMNS[K1_LISTED_SUBTABLE.writeoffDetail].find((c) => c.key === '是否由关联交易产生')
        ?.label,
    ).toBe('款项是否由关联交易产生')
    // A126：单位名称（注：政府补助的发文单位）—— 源换行改括注纯文本
    expect(firstHeader(soeSection, K1_SOE_SUBTABLE.govGrant)).toBe(
      '单位名称（注：政府补助的发文单位）',
    )
  })

  // ─── Property 4：三阶段变动表行标签逐字对齐模板 rows（k1-extraction-chain-and-note-alignment） ───
  // ─── Property 8：_note_texts 全部带中文 title（k1-extraction-chain-and-note-alignment） ───
  it('_note_texts 每条带中文 title，且空文本被过滤（Property 8）', () => {
    const listedPayload = buildK1ListedSubTableData(
      emptyK1ListedPayload(),
      '审计说明文字',
    )
    const listedTexts = listedPayload._note_texts as unknown as Array<{ section: string; title: string; text: string }>
    expect(listedTexts.length).toBeGreaterThan(0)
    for (const t of listedTexts) {
      expect(t.title, t.section).toBeTruthy()
      expect(t.title, t.section).not.toMatch(/^[a-z0-9-]+$/i)
    }
    expect(listedTexts.find((t) => t.section === 'listed-audit-note')?.title).toBe('审计说明')

    const soePayload = buildK1SoeSubTableData(emptyK1SoePayload(), '国企审计说明')
    const soeTexts = soePayload._note_texts as unknown as Array<{ section: string; title: string; text: string }>
    expect(soeTexts.length).toBeGreaterThan(0)
    for (const t of soeTexts) {
      expect(t.title, t.section).toBeTruthy()
      expect(t.title, t.section).not.toMatch(/^[a-z0-9-]+$/i)
    }

    // 全空时不产生 _note_texts 键
    const emptyPayload = buildK1ListedSubTableData(emptyK1ListedPayload())
    expect(emptyPayload._note_texts).toEqual([])
  })

  it('三阶段变动表行标签逐字对齐模板 rows（Property 4）', () => {
    const listedRows = listedSection.tables?.find(
      (t) => t.name === K1_LISTED_SUBTABLE.stageMovement,
    ) as unknown as { rows?: Array<{ label: string }> }
    expect(listedRows?.rows?.map((r) => r.label)).toEqual([
      '上年年末余额', '上年年末余额在本期',
      '--转入第二阶段', '--转入第三阶段', '--转回第二阶段', '--转回第一阶段',
      '本期计提', '本期转回', '本期转销', '本期核销', '其他变动', '期末余额',
    ])

    const soeEclRows = soeSection.tables?.find(
      (t) => t.name === K1_SOE_SUBTABLE.eclMovement,
    ) as unknown as { rows?: Array<{ label: string }> }
    expect(soeEclRows?.rows?.map((r) => r.label)).toEqual([
      '期初余额', '期初余额在本期',
      '—转入第二阶段', '—转入第三阶段', '—转回第二阶段', '—转回第一阶段',
      '本期计提', '本期转回', '本期转销', '本期核销', '其他变动', '期末余额',
    ])

    const soeBalanceRows = soeSection.tables?.find(
      (t) => t.name === K1_SOE_SUBTABLE.balanceMovement,
    ) as unknown as { rows?: Array<{ label: string }> }
    expect(soeBalanceRows?.rows?.map((r) => r.label)).toEqual([
      '期初余额', '期初余额在本期',
      '—转入第二阶段', '—转入第三阶段', '—转回第二阶段', '—转回第一阶段',
      '本期新增', '本期终止确认', '其他变动', '期末余额',
    ])

    // 无重复标签
    for (const rows of [listedRows?.rows, soeEclRows?.rows, soeBalanceRows?.rows]) {
      const labels = (rows ?? []).map((r) => r.label)
      expect(new Set(labels).size).toBe(labels.length)
    }
  })
})
