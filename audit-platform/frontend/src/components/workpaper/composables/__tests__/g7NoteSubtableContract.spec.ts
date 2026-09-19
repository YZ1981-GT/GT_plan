/**
 * G7 长期股权投资 披露载荷契约守卫 —— **全章节覆盖**（38 张运行时表）
 *
 * 复用共享 helper P1~P6：子表名逐字一致 / 章节号存在 / group·flat 必表态 /
 * 标签纯文本 / 标签列头对齐 headers[0] / 模板 headers 纯文本。
 *
 * ## 🔴 为什么改成全章节（Task 12）
 *
 * 改造前本文件用 `G7_NOTE_SECTION` 过滤，**只覆盖主章节**（listed `五、18` 1 张 +
 * soe `八、18` 10 张 = 11 张），而 G7 运行时实推 **38 张**（listed 15 / soe 23）——
 * 跨章的 **27 张**（listed `七、1` 14 张 + soe 10 个 `七、…` 13 张）落在
 * 「后端 test_note_g7_structure.py（边①）」与「本契约（边②）」的**交集之外**：
 * 边① 只比源 xlsx↔seed、本契约当时不看这些表 ⇒ 它们的表名/表态/标签列头无任何守卫。
 *
 * 现在按 `(章节, 表名)` 二元组把**每个章节各作一个 variant 条目**喂给 helper
 * （helper 本身按 `section + subtables` 成组，天然支持多章节，**无需改它的 P1~P6 语义**）。
 *
 * ## 🔴 soe 的 `七、…` 章节号是 md 截断值（10 字符）
 *
 * 如 `七、本期纳入合并报表` / `七、母公司拥有被投资` —— 属**既有真源形态**
 * （`note_template_soe.json` 里就是这个值），按截断值断言，**不得「补全」**。
 *
 * **Validates: Requirements 9.1, 9.2, 9.5**
 * **Properties: 7, 11, 32, 33, 34**
 *
 * spec: g7-column-alignment-and-extraction-closure (Task 12)
 *       前身 g7-four-table-extraction-and-disclosure-alignment (Task 6.4)
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
import { G7_NOTE_SECTION } from '../g7NoteSectionMap'
import {
  G7_LISTED_DISCLOSURE_SECTIONS,
  buildG7ListedColumns,
} from '../../g7-long-term-equity-main/disclosure/g7ListedDisclosureModel'
import {
  G7_SOE_DISCLOSURE_SECTIONS,
  buildG7SoeColumns,
} from '../../g7-long-term-equity-main/disclosure/g7SoeDisclosureModel'

// ─── 运行时 sections → 按章节分组的 (语义键 → 模板表名) 映射 ──────────────────

interface SectionLike {
  noteSectionId: string
  tables?: readonly { id: string; templateTableKey?: string; title: string }[]
}

interface SectionGroup {
  section: string
  subtables: Record<string, string>
}

/**
 * 按 `noteSectionId` 分组（保持声明顺序），每组产出一个 helper variant 条目。
 *
 * 🔴 **无表章节必须剔除**：`G7_SOE_DISCLOSURE_SECTIONS` 里有 3 个只放 `text_sections`
 * 的纯叙述章节（`七`、`七、子公司使用企业集`、`七、纳入合并财务报表`，`tables` 为空或
 * 只有非载荷表）—— 它们没有子表可推送。若把它们也喂给 helper，`P1 声明了子表` 会因
 * `entries.length === 0` 打红，那是**本文件的判据缺陷**（空转组），不是产品偏差。
 * 剔除的同时把它们记进 `EMPTY_SECTIONS` 由自检断言可见，防「剔除」被滥用成静默漏检。
 */
function groupBySection(sections: readonly SectionLike[]): {
  groups: SectionGroup[]
  emptySections: string[]
} {
  const all: SectionGroup[] = []
  const index = new Map<string, SectionGroup>()
  for (const section of sections) {
    const sid = String(section.noteSectionId ?? '')
    let g = index.get(sid)
    if (!g) {
      g = { section: sid, subtables: {} }
      index.set(sid, g)
      all.push(g)
    }
    for (const table of section.tables ?? []) {
      g.subtables[table.id] = table.templateTableKey ?? table.title
    }
  }
  return {
    groups: all.filter((g) => Object.keys(g.subtables).length > 0),
    emptySections: all.filter((g) => Object.keys(g.subtables).length === 0).map((g) => g.section),
  }
}

function pickColumns(
  all: Record<string, unknown[]>,
  subtables: Record<string, string>,
): Record<string, unknown[]> {
  const result: Record<string, unknown[]> = {}
  for (const name of Object.values(subtables)) {
    if (all[name]) result[name] = all[name]
  }
  return result
}

const LISTED_SPLIT = groupBySection(G7_LISTED_DISCLOSURE_SECTIONS as unknown as SectionLike[])
const SOE_SPLIT = groupBySection(G7_SOE_DISCLOSURE_SECTIONS as unknown as SectionLike[])
const LISTED_GROUPS = LISTED_SPLIT.groups
const SOE_GROUPS = SOE_SPLIT.groups

const listedAllColumns = buildG7ListedColumns() as Record<string, unknown[]>
const soeAllColumns = buildG7SoeColumns() as Record<string, unknown[]>

// ─── 共享 helper P1~P6（对**全部章节**跑，不再只跑主章节）────────────────────

runDisclosureSubtableContract({
  cycle: 'G7',
  variants: [
    ...LISTED_GROUPS.map((g) => ({
      variant: 'listed' as const,
      section: g.section,
      subtables: g.subtables,
      columns: pickColumns(listedAllColumns, g.subtables) as any,
    })),
    ...SOE_GROUPS.map((g) => ({
      variant: 'soe' as const,
      section: g.section,
      subtables: g.subtables,
      columns: pickColumns(soeAllColumns, g.subtables) as any,
    })),
  ],
})

// ─── 扫描面自检（防扩容后又静默缩回主章节）────────────────────────────────────

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

type Variant = 'listed' | 'soe'

interface SeedSection {
  section_number?: string
  tables?: { name?: string }[]
}

function loadTemplate(variant: Variant): SeedSection[] {
  const file = variant === 'listed' ? 'note_template_listed.json' : 'note_template_soe.json'
  const raw = JSON.parse(readFileSync(resolve(REPO_ROOT, 'backend/data', file), 'utf-8')) as {
    sections?: SeedSection[]
  }
  return raw.sections ?? []
}

/** 全部运行时表（含章节），作为覆盖面判据的分母。 */
const RUNTIME_TABLES: { variant: Variant; section: string; table: string }[] = [
  ...LISTED_GROUPS.flatMap((g) =>
    Object.values(g.subtables).map((t) => ({ variant: 'listed' as Variant, section: g.section, table: t })),
  ),
  ...SOE_GROUPS.flatMap((g) =>
    Object.values(g.subtables).map((t) => ({ variant: 'soe' as Variant, section: g.section, table: t })),
  ),
]

describe('G7 契约扫描面自检（覆盖面回退即打红）', () => {
  it('覆盖 38 张全部运行时表（listed 15 + soe 23），不再只覆盖主章节 11 张', () => {
    const listedCount = LISTED_GROUPS.reduce((n, g) => n + Object.keys(g.subtables).length, 0)
    const soeCount = SOE_GROUPS.reduce((n, g) => n + Object.keys(g.subtables).length, 0)
    expect(listedCount, 'listed 运行时表数').toBe(15)
    expect(soeCount, 'soe 运行时表数').toBe(23)
    expect(RUNTIME_TABLES.length, '合计运行时表数').toBeGreaterThanOrEqual(38)

    // 🔴 反面锚定：主章节只占 11 张 ⇒ 若哪天有人把过滤加回来，上面三条必红
    const mainOnly = RUNTIME_TABLES.filter(
      (t) => t.section === G7_NOTE_SECTION[t.variant],
    ).length
    expect(mainOnly, '主章节表数（改造前的全部覆盖面）').toBe(11)
    expect(RUNTIME_TABLES.length - mainOnly, '跨章表数（改造前的盲区）').toBe(27)
  })

  it('有表章节全部进契约，每组都真有表（无空转组）', () => {
    // 🔴 `noteSectionId` 分组后必须**过滤掉无表章节**再喂 helper：
    // 实测 soe 侧有 3 个纯文字披露章节（`七、子公司使用企业集` / `七、纳入合并财务报表`
    // 以及一个截断成 `七` 的），它们只推 `text_sections` 不推表。把它们喂给 helper 会让
    // P1「声明了子表（防空映射空转）」直接失败 —— 那是**判据缺陷**（helper 的空映射闸
    // 本就是为了拦住「忘了填 subtables」），不是产品缺陷。
    expect(LISTED_GROUPS.length, 'listed 有表章节数').toBe(2)
    expect(SOE_GROUPS.length, 'soe 有表章节数').toBe(11)
    for (const g of [...LISTED_GROUPS, ...SOE_GROUPS]) {
      expect(Object.keys(g.subtables).length, `章节 ${g.section} 无表 ⇒ 该组契约空转`).toBeGreaterThan(0)
    }
  })

  it('无表章节登记：确有纯文字披露章节，且它们真的一张表都不推（不是被漏掉）', () => {
    // 反面锚定：证明上一条的过滤不是「把偏差藏起来」——
    // 被过滤的章节必须**确实零表**，且其表数之和为 0（若哪天它们开始推表，本条必红，
    // 提醒把它们纳入契约而不是继续过滤）。
    expect(LISTED_SPLIT.emptySections, 'listed 不应有无表章节').toEqual([])
    expect(SOE_SPLIT.emptySections.length, 'soe 无表章节数').toBe(3)
    for (const s of SOE_SPLIT.emptySections) {
      const decl = (G7_SOE_DISCLOSURE_SECTIONS as unknown as SectionLike[]).filter(
        (x) => String(x.noteSectionId ?? '') === s,
      )
      expect(decl.length, `章节 ${s} 应在运行时 sections 里出现过`).toBeGreaterThan(0)
      const total = decl.reduce((n, x) => n + (x.tables?.length ?? 0), 0)
      expect(total, `章节 ${s} 已开始推表 ⇒ 应纳入契约而非继续过滤`).toBe(0)
    }
  })

  it('每张运行时表都真拿到列定义（拿不到会让 P3/P4/P5 静默跳过）', () => {
    const empty: string[] = []
    for (const t of RUNTIME_TABLES) {
      const all = t.variant === 'listed' ? listedAllColumns : soeAllColumns
      if (!all[t.table] || all[t.table].length === 0) empty.push(`${t.variant}/${t.section}/${t.table}`)
    }
    expect(empty).toEqual([])
  })

  it('soe 的 七、… 章节号按 md 截断值（10 字符）断言，禁「补全」', () => {
    const crossSections = SOE_GROUPS.map((g) => g.section).filter((s) => s.startsWith('七、'))
    expect(crossSections.length, 'soe 跨章章节数').toBeGreaterThanOrEqual(9)
    for (const s of crossSections) {
      // 真源形态：`七、` + 8 个汉字 = 10 字符（md 截断）
      expect(s.length, `章节号 ${s} 长度应为截断值 10`).toBe(10)
    }
    // 交叉锁死：这些截断值必须真存在于模板（补全后的写法在模板里查不到）
    const tplSections = new Set(loadTemplate('soe').map((s) => String(s.section_number ?? '').trim()))
    for (const s of crossSections) {
      expect(tplSections.has(s), `模板缺章节 ${s}（若这里失败，八成是有人把截断值「补全」了）`).toBe(true)
    }
  })

  it('孤儿表 0：每张运行时表都在对应变体的**对应章节**里（不是全局按表名）', () => {
    const orphans: string[] = []
    for (const variant of ['listed', 'soe'] as Variant[]) {
      const byKey = new Set<string>()
      for (const s of loadTemplate(variant)) {
        const sec = String(s.section_number ?? '').trim()
        for (const t of s.tables ?? []) byKey.add(`${sec}\u0000${t.name ?? ''}`)
      }
      for (const t of RUNTIME_TABLES.filter((x) => x.variant === variant)) {
        if (!byKey.has(`${t.section}\u0000${t.table}`)) orphans.push(`${variant}/${t.section}/${t.table}`)
      }
    }
    expect(orphans, '孤儿表 ⇒ 投影器不渲染 ⇒ 底稿数据静默丢失').toEqual([])
  })

  it('运行时 templateTableKey 撞名 0（同变体内）', () => {
    for (const variant of ['listed', 'soe'] as Variant[]) {
      const keys = RUNTIME_TABLES.filter((t) => t.variant === variant).map((t) => t.table)
      const dup = [...new Set(keys.filter((k, i) => keys.indexOf(k) !== i))]
      expect(dup, `${variant} 运行时 templateTableKey 撞名`).toEqual([])
    }
  })

  it('模板同章节内表名唯一 0 撞名（撞名会让 sub_table_data 字典去重丢整张表）', () => {
    for (const variant of ['listed', 'soe'] as Variant[]) {
      const dups: string[] = []
      for (const s of loadTemplate(variant)) {
        const sec = String(s.section_number ?? '').trim()
        const seen = new Set<string>()
        for (const t of s.tables ?? []) {
          const n = t.name ?? ''
          if (seen.has(n)) dups.push(`${sec}/${n}`)
          seen.add(n)
        }
      }
      expect(dups, `${variant} 同章节内表名撞名`).toEqual([])
    }
  })

  it('反向自检：改错一个表名必被孤儿判据抓到', () => {
    const byKey = new Set<string>()
    for (const s of loadTemplate('soe')) {
      const sec = String(s.section_number ?? '').trim()
      for (const t of s.tables ?? []) byKey.add(`${sec}\u0000${t.name ?? ''}`)
    }
    const sample = RUNTIME_TABLES.find((t) => t.variant === 'soe')!
    expect(byKey.has(`${sample.section}\u0000${sample.table}`), '基线应命中').toBe(true)
    expect(
      byKey.has(`${sample.section}\u0000${sample.table}__typo__`),
      '改错表名后应不命中（判据有效）',
    ).toBe(false)
    // 章节错也必须不命中（证明索引真的带章节，不是全局按表名）
    expect(byKey.has(`八、18\u0000${sample.table}`) && sample.section !== '八、18').toBe(false)
  })
})

// ─── G7 专属补充断言（保留原有，零入参可调 + 无孤儿列定义）────────────────────

describe('G7 专属契约补充', () => {
  it('buildG7ListedColumns 零入参可调且每张表都有列', () => {
    const cols = buildG7ListedColumns()
    expect(Object.keys(cols).length).toBe(15)
    for (const [name, defs] of Object.entries(cols)) {
      expect(defs.length, `${name} 列定义为空`).toBeGreaterThan(0)
    }
  })

  it('buildG7SoeColumns 零入参可调且每张表都有列', () => {
    const cols = buildG7SoeColumns()
    expect(Object.keys(cols).length).toBe(23)
    for (const [name, defs] of Object.entries(cols)) {
      expect(defs.length, `${name} 列定义为空`).toBeGreaterThan(0)
    }
  })

  it('列集键集与运行时表名集逐一对应（无孤儿列定义、无缺列表）', () => {
    for (const variant of ['listed', 'soe'] as Variant[]) {
      const all = variant === 'listed' ? listedAllColumns : soeAllColumns
      const declared = new Set(RUNTIME_TABLES.filter((t) => t.variant === variant).map((t) => t.table))
      const built = new Set(Object.keys(all))
      expect([...declared].filter((n) => !built.has(n)), `${variant} 声明了表但没造列`).toEqual([])
      expect([...built].filter((n) => !declared.has(n)), `${variant} 造了列但没有表声明（孤儿）`).toEqual([])
    }
  })
})
