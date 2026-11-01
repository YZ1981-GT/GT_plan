/**
 * D2 应收账款披露子表 ↔ note_template 契约（附注权威源对拍守卫）
 *
 * spec: note-table-structure-formula-pull-closure R13（design §6.5）
 *
 * 背景：`d2NoteSectionMap.ts` 把表名与列头硬编码，文件头声明「权威来源 = note_template
 * 五、5 / 八、5」，但 D2 是**唯一没接入共享子表契约 helper 的披露循环**（现算：D1/D3~D7/
 * E1/F2/F3/G4~G12/H2~H4/I1~I6/J1/J2/K2~K13/L1~L8/M2~M10 全部已接）。既有
 * `d2NoteSectionMap.spec.ts` 只对 `individualEnd` / `individualPrior` 两张表做过模板对拍，
 * 其余 15 张的期望值都是写死的字面量 ⇒ 模板按底稿改表头（R8.4 批 9b-1/9b-2）后前端不跟进，
 * 没有任何守卫会打红，附注里就显示成前端自己编的列头。
 *
 * 本守卫两层：
 *  ① 共享 helper 的 P1~P6（表名逐字 / 章节存在 / group·flat 表态 / 标签纯文本 /
 *     标签列头对齐 headers[0] / 模板 headers 纯文本）；
 *  ② D2 专属逐位对拍：每张固定表的 `label` 序列 == 模板 `headers`，由 `group` 推出的
 *     `_column_groups` == 模板 `_column_groups`；组合分表（表名随项目动态）与模板同类
 *     样板表对拍；固定表名双向键集相等（防漏推 / 防孤儿表）。
 *
 * 🔴 判据取自**生产函数** `buildD2SyncPayload` 的真实产物（不是 import 模块私有常量），
 * 推送链路上游改了列头这里就会红。偏差一律登记在 `HEADER_DEVIATIONS`（带可伪证字段，
 * 只许变短），不得放宽断言。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  deriveColumnGroups,
  runDisclosureSubtableContract,
  templateTable,
  type ContractColumnDef,
} from './_disclosureSubtableContract.helper'
import {
  D2_NOTE_SECTION,
  D2_PORTFOLIO_TABLE_PREFIX,
  D2_SOE_PRIOR_SUFFIX,
  D2_TABLE_NAMES,
  buildD2SyncPayload,
  portfolioTableName,
  type D2DisclosureSnapshot,
  type D2DisclosureVariant,
} from '../d2NoteSectionMap'

// ─── 夹具 ────────────────────────────────────────────────────────────────────

/**
 * 组合名取模板里真实存在的样板组合，让组合分表也能与模板逐位对拍。
 * （真实项目的组合名由审计师自定，模板只能存样板 ⇒ 组合分表不进 P1 表名存在性。）
 */
const SAMPLE_PORTFOLIO = '应收中央企业客户'

function snapshot(): D2DisclosureSnapshot {
  return {
    agingRows: [{ label: '1年以内', endAmount: 1000, priorAmount: 800 }],
    classRows: [],
    classWideEndRows: [
      { label: '按单项计提坏账准备', bookAmount: 500, ratio: 100, provision: 50, lossRate: 10, carryingValue: 450 },
    ],
    classWidePriorRows: [
      { label: '按单项计提坏账准备', bookAmount: 400, ratio: 100, provision: 40, lossRate: 10, carryingValue: 360 },
    ],
    individualRows: [
      {
        name: 'A公司', endAmount: 300, priorAmount: 200, provision: 30, priorProvision: 20,
        lossRate: 10, priorLossRate: 10, aging: '1年以内', basis: '预计无法收回',
      },
    ],
    portfolios: [
      {
        name: SAMPLE_PORTFOLIO,
        rows: [
          {
            label: '1年以内', endAmount: 600, priorAmount: 400, provision: 60, priorProvision: 40,
            lossRate: 10, priorLossRate: 10, ratio: 100, priorRatio: 100,
          },
        ],
      },
    ],
    otherPortfolioRows: [{ label: '余额百分比组合', endAmount: 50, priorAmount: 40, provision: 5, priorProvision: 4 }],
    movement: { priorBalance: 100, provision: 40, reversal: 5, writeOff: 3, transfer: 2, other: 0, endBalance: 130 },
    movementByCategory: [
      {
        label: '按单项计提坏账准备', priorAmount: 60, provisionAmount: 14,
        reversalAmount: 3, writeOffAmount: 1, endAmount: 70,
      },
    ],
    reversalRows: [
      {
        companyName: 'C公司', reversalReason: '款项收回', recoveryMethod: '银行转账',
        originalBasis: '账龄组合', cumulativeProvision: 12, amount: 5,
      },
    ],
    writeOffAmount: 3,
    writeOffRows: [
      { companyName: 'D公司', nature: '货款', amount: 3, reason: '破产清算', procedure: '董事会审批', relatedParty: '否' },
    ],
    top5Rows: [{ companyName: 'A公司', arAmount: 300, contractAssetAmount: 20, ratio: 100, provision: 30 }],
    derecognizedRows: [{ companyName: 'E公司', transferMethod: '保理', amount: 100, gainLoss: -2 }],
    continuedInvolvementRows: [
      { item: '附追索权保理', transferMethod: '保理', assetAmount: 60, liabilityAmount: 55 },
    ],
    notes: {},
  }
}

const PAYLOAD: Record<D2DisclosureVariant, ReturnType<typeof buildD2SyncPayload>> = {
  listed: buildD2SyncPayload('listed', 'wp-d2-listed', null, snapshot()),
  soe: buildD2SyncPayload('soe', 'wp-d2-soe', null, snapshot()),
}

/** 本次推送的数据子表名（剔除 `_note_texts` / `_removed_table_keys` 等元数据键）。 */
function pushedTableNames(variant: D2DisclosureVariant): string[] {
  return Object.keys(PAYLOAD[variant].columns).filter((k) => !k.startsWith('_'))
}

const isPortfolio = (name: string): boolean => name.startsWith(D2_PORTFOLIO_TABLE_PREFIX)

/** 固定表（非组合分表）：表名在模板里应当逐字存在。 */
function fixedTableNames(variant: D2DisclosureVariant): string[] {
  return pushedTableNames(variant).filter((n) => !isPortfolio(n))
}

// ─── 共享契约 P1~P6 ──────────────────────────────────────────────────────────

const SUBTABLES: Record<D2DisclosureVariant, Readonly<Record<string, string>>> = {
  listed: Object.fromEntries(fixedTableNames('listed').map((n) => [n, n])),
  soe: Object.fromEntries(fixedTableNames('soe').map((n) => [n, n])),
}

runDisclosureSubtableContract({
  cycle: 'D2',
  variants: [
    {
      variant: 'listed',
      section: D2_NOTE_SECTION.listed,
      subtables: SUBTABLES.listed,
      columns: PAYLOAD.listed.columns as Readonly<Record<string, ContractColumnDef[]>>,
    },
    {
      variant: 'soe',
      section: D2_NOTE_SECTION.soe,
      subtables: SUBTABLES.soe,
      columns: PAYLOAD.soe.columns as Readonly<Record<string, ContractColumnDef[]>>,
    },
  ],
})

// ─── D2 专属：逐位对拍 ───────────────────────────────────────────────────────

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

const TEMPLATE_FILE: Record<D2DisclosureVariant, string> = {
  listed: 'note_template_listed.json',
  soe: 'note_template_soe.json',
}

interface TplTable { name?: string; headers?: string[]; _column_groups?: unknown }

function templateTableNames(variant: D2DisclosureVariant): string[] {
  const path = resolve(REPO_ROOT, 'backend/data', TEMPLATE_FILE[variant])
  const raw = JSON.parse(readFileSync(path, 'utf-8')) as {
    sections?: Array<{ section_number?: string; tables?: TplTable[] }>
  }
  const section = D2_NOTE_SECTION[variant]
  const sec = (raw.sections ?? []).find((s) => String(s.section_number ?? '') === section)
  return (sec?.tables ?? []).map((t) => String(t.name ?? ''))
}

const VARIANTS: D2DisclosureVariant[] = ['listed', 'soe']

describe('D2 披露子表 ↔ note_template 逐位对拍（R13）', () => {
  it.each(VARIANTS)('%s 固定表名双向相等（模板有 ⇔ 推送有）', (variant) => {
    const pushed = new Set(fixedTableNames(variant))
    const tpl = new Set(templateTableNames(variant).filter((n) => !isPortfolio(n)))
    const missingInPush = [...tpl].filter((n) => !pushed.has(n))
    const orphanInPush = [...pushed].filter((n) => !tpl.has(n))
    expect(
      { missingInPush, orphanInPush },
      '模板有而不推 ⇒ 附注 TAB 永空；推而模板没有 ⇒ 孤儿子表',
    ).toEqual({ missingInPush: [], orphanInPush: [] })
  })

  it.each(VARIANTS)('%s 每张固定表列头逐位 == 模板 headers', (variant) => {
    const bad: string[] = []
    for (const name of fixedTableNames(variant)) {
      const tbl = templateTable(variant, D2_NOTE_SECTION[variant], name)
      if (!tbl) {
        bad.push(`${name}: 模板缺表`)
        continue
      }
      const got = (PAYLOAD[variant].columns[name] ?? []).map((c) => String(c.label ?? ''))
      const want = (tbl.headers ?? []).map((h) => String(h))
      if (JSON.stringify(got) !== JSON.stringify(want)) {
        bad.push(`${name}: 推送 ${JSON.stringify(got)} ≠ 模板 ${JSON.stringify(want)}`)
      }
    }
    expect(bad, '推送 columns 的 label 决定附注表头显示，与模板不一致即与 Word 不一致').toEqual([])
  })

  it.each(VARIANTS)('%s 每张固定表 group 结构 == 模板 _column_groups', (variant) => {
    const bad: string[] = []
    for (const name of fixedTableNames(variant)) {
      const tbl = templateTable(variant, D2_NOTE_SECTION[variant], name)
      if (!tbl) continue
      const got = deriveColumnGroups(PAYLOAD[variant].columns[name] ?? [])
      const want = (tbl._column_groups ?? null) as unknown
      if (JSON.stringify(got) !== JSON.stringify(want)) {
        bad.push(`${name}: 推送 ${JSON.stringify(got)} ≠ 模板 ${JSON.stringify(want)}`)
      }
    }
    expect(bad, '多级表头层数/跨度不一致会让附注与 Word 导出的表头错位').toEqual([])
  })

  it.each(VARIANTS)('%s 组合分表与模板同类样板表逐位一致', (variant) => {
    const sample = portfolioTableName(SAMPLE_PORTFOLIO)
    const tbl = templateTable(variant, D2_NOTE_SECTION[variant], sample)
    expect(tbl, `模板缺组合样板表 ${sample}`).toBeDefined()
    const got = (PAYLOAD[variant].columns[sample] ?? []).map((c) => String(c.label ?? ''))
    expect(got, `${sample} 列头`).toEqual((tbl!.headers ?? []).map((h) => String(h)))
    expect(deriveColumnGroups(PAYLOAD[variant].columns[sample] ?? []), `${sample} 分组`).toEqual(
      (tbl!._column_groups ?? null) as never,
    )
  })

  it('soe 组合分表续表（期初数）也与模板逐位一致', () => {
    const name = `${portfolioTableName(SAMPLE_PORTFOLIO)}${D2_SOE_PRIOR_SUFFIX}`
    const tbl = templateTable('soe', D2_NOTE_SECTION.soe, name)
    expect(tbl, `模板缺 ${name}`).toBeDefined()
    expect((PAYLOAD.soe.columns[name] ?? []).map((c) => String(c.label ?? ''))).toEqual(
      (tbl!.headers ?? []).map((h) => String(h)),
    )
  })

  // ── 变异自检：判据真的会红 ──────────────────────────────────────────────
  it('变异自检：改一个列头 label 后逐位对拍必红', () => {
    const name = D2_TABLE_NAMES.listed.aging
    const tbl = templateTable('listed', D2_NOTE_SECTION.listed, name)
    const mutated = (PAYLOAD.listed.columns[name] ?? []).map((c, i) =>
      i === 0 ? { ...c, label: `${c.label}__mutated` } : c,
    )
    expect(mutated.map((c) => String(c.label ?? ''))).not.toEqual((tbl!.headers ?? []).map((h) => String(h)))
  })
})

// ─── 同名表只许推一次（防重复 put 造死代码）──────────────────────────────────

describe('D2 载荷写入唯一性（R13）', () => {
  const SOURCE = readFileSync(
    resolve(__dirname, '../d2NoteSectionMap.ts'),
    'utf-8',
  ).replace(/\r\n/g, '\n')

  /**
   * `put(第一参数, …)` 的表名表达式清册。
   *
   * 🔴 2026-11-01 实证的反模式：国企「继续涉入」曾被 put 两次（第 ⑨ 段一套
   * `is_section` 行结构、第 ⑩ 段另一套 `row_type: 'header_label'`），后者覆盖前者
   * ⇒ 前一套整段是死代码，且两套行结构的小计 label 还不同（「继续涉入形成的资产小计」
   * vs「资产小计」）。产物上看不出重复（覆盖是静默的），只有数源码里的写入点才看得见。
   */
  function putTargets(): string[] {
    return [...SOURCE.matchAll(/\bput\(\s*\n?\s*([A-Za-z0-9_.[\]'`$\u4e00-\u9fff{}]+)\s*,/g)].map((m) =>
      m[1].trim(),
    )
  }

  it('固定表名的 put 目标互不重复（组合分表走动态 name 变量，不在此列）', () => {
    const targets = putTargets().filter((t) => t.startsWith('D2_TABLE_NAMES.'))
    expect(targets.length, 'put 目标清册为空 ⇒ 正则没匹配上，判据会空转').toBeGreaterThan(10)
    const seen = new Map<string, number>()
    for (const t of targets) seen.set(t, (seen.get(t) ?? 0) + 1)
    const dup = [...seen.entries()].filter(([, n]) => n > 1).map(([t, n]) => `${t} × ${n}`)
    expect(dup, '同一表名 put 两次 ⇒ 后者静默覆盖前者，前者成死代码').toEqual([])
  })

  it('国企继续涉入行结构唯一（资产/负债分块 + 各自小计，取自现行唯一实现）', () => {
    const rows = PAYLOAD.soe.sub_table_data[D2_TABLE_NAMES.soe.continuedInvolvement] as Array<
      Record<string, unknown>
    >
    expect(rows.map((r) => r.label)).toEqual([
      '资产：', '附追索权保理', '资产小计', '负债：', '附追索权保理', '负债小计',
    ])
    expect(rows[0]).toMatchObject({ row_type: 'header_label', amount: null })
    expect(rows[2]).toMatchObject({ amount: 60, is_total: true })
    expect(rows[5]).toMatchObject({ amount: 55, is_total: true })
  })
})
