/**
 * d1AdjudicationModel 守卫 —— D1 审定表锚点与分类合计单一真源
 *
 * Spec: .kiro/specs/d1-extraction-chain-completion/
 *       (Property 4 锚点单一真源 / 5 审定数派生一致 / 6 净值恒等 / 7 动态票据种类不丢金额)
 *
 * 本文件同时做**跨语言契约**：把模块导出的锚点形状与后端
 * `backend/data/d_cycle_extraction/d_cycle_anchor_registry.json` 的 D1 模式锚点交叉校验。
 * 二者漂移时后端 `is_known_anchor` 会静默丢弃 seed —— vue-tsc / mypy / 其它 vitest 全查不出。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import * as fc from 'fast-check'
import {
  D1_ADJ_FIELDS,
  D1_ADJ_PREFIX,
  D1_BD_NOTETYPE_KEY,
  D1_CAT_ROWS_KEY,
  D1_FIXED_CATEGORIES,
  d1AdjAnchor,
  d1AdjAnchorByRowKey,
  d1AdjRowKey,
  d1Audited,
  d1CategorySlug,
  d1NetAmounts,
  d1SumAmounts,
  d1WithAudited,
  readD1AdjudicationTotals,
  readD1BadDebtByNoteType,
  readD1Categories,
  readD1CategoryAmounts,
  type D1AdjSection,
  type D1AnchorResponse,
} from '../d1AdjudicationModel'

const REGISTRY_PATH = resolve(
  __dirname,
  '../../../../../../../backend/data/d_cycle_extraction/d_cycle_anchor_registry.json',
)

function mapOf(entries: Record<string, string>): Map<string, D1AnchorResponse> {
  const m = new Map<string, D1AnchorResponse>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, conclusion: null, remark: v })
  }
  return m
}

const SECTIONS: D1AdjSection[] = ['gross', 'bd', 'net']

// ─── Property 4: 锚点单一真源 ────────────────────────────────────────────────

describe('Property 4: 锚点单一真源（与后端登记表交叉校验）', () => {
  const registry = JSON.parse(readFileSync(REGISTRY_PATH, 'utf-8')) as Record<string, string[]>
  const d1Entries = registry.D1 ?? []
  const patterns = d1Entries
    .filter((e) => e.startsWith('re:'))
    .map((e) => new RegExp(e.slice(3)))
  const exact = new Set(d1Entries.filter((e) => !e.startsWith('re:')))

  it('登记表非空且含 D1 模式锚点（防正则失效导致断言空转）', () => {
    expect(d1Entries.length).toBeGreaterThan(0)
    expect(patterns.length).toBeGreaterThan(0)
  })

  it('d1AdjAnchor 产出的锚点全部被后端登记表接纳（固定 + 动态 slug）', () => {
    const slugs = [...D1_FIXED_CATEGORIES.map((c) => c.slug), 'c-tb-1', 'c-abc123']
    for (const section of SECTIONS) {
      for (const slug of slugs) {
        for (const field of D1_ADJ_FIELDS) {
          const anchor = d1AdjAnchor(section, slug, field)
          const ok = exact.has(anchor) || patterns.some((re) => re.test(anchor))
          expect(ok, `锚点未被后端登记表接纳: ${anchor}`).toBe(true)
        }
      }
    }
  })

  it('D1-4 按票据种类小计锚点已登记（否则后端 seed 会丢弃）', () => {
    expect(exact.has(D1_BD_NOTETYPE_KEY)).toBe(true)
    expect(exact.has(D1_CAT_ROWS_KEY)).toBe(true)
  })

  it('d1AdjAnchorByRowKey 与 d1AdjAnchor 对同一 (section,slug,field) 逐字相等', () => {
    for (const section of SECTIONS) {
      for (const field of D1_ADJ_FIELDS) {
        expect(d1AdjAnchorByRowKey(d1AdjRowKey(section, 'bank'), field)).toBe(
          d1AdjAnchor(section, 'bank', field),
        )
      }
    }
  })

  it('锚点前缀固定为 D1-adj-（改前缀会让全部历史数据变孤儿）', () => {
    expect(D1_ADJ_PREFIX).toBe('D1-adj-')
    expect(d1AdjAnchor('gross', 'bank', 'current-unadj')).toBe('D1-adj-gross-bank-current-unadj')
  })

  it('🔴 派生列不得出现在可持久化字段集（审定数/变动额/变动率是 computed）', () => {
    for (const f of D1_ADJ_FIELDS) {
      expect(f).not.toContain('audited')
      expect(f).not.toContain('change')
    }
  })
})

// ─── slug 稳定性 ─────────────────────────────────────────────────────────────

describe('d1CategorySlug', () => {
  it('固定行映射到与历史锚点兼容的 bank / commercial', () => {
    expect(d1CategorySlug('fixed-bank')).toBe('bank')
    expect(d1CategorySlug('fixed-commercial')).toBe('commercial')
  })

  it('动态行取 rowId（ASCII 稳定），改中文种类名不影响 slug', () => {
    expect(d1CategorySlug('dynamic-tb-1', '信用证')).toBe('c-tb-1')
    expect(d1CategorySlug('dynamic-tb-1', '银行承兑汇票（改名后）')).toBe('c-tb-1')
  })

  it('无 rowId 时按名称关键字兜底归到固定行（历史数据兼容）', () => {
    expect(d1CategorySlug('', '应收票据_银行承兑汇票')).toBe('bank')
    expect(d1CategorySlug('', '商业承兑汇票')).toBe('commercial')
    expect(d1CategorySlug('', '信用证')).toBe('')
  })

  it('slug 恒为锚点安全字符（否则登记表正则不接纳）', () => {
    fc.assert(
      fc.property(fc.string(), (raw) => {
        const slug = d1CategorySlug(`dynamic-${raw}`, '')
        if (!slug) return
        expect(slug).toMatch(/^[A-Za-z0-9_-]+$/)
      }),
      { numRuns: 80 },
    )
  })
})

// ─── Property 5: 审定数派生一致 ──────────────────────────────────────────────

describe('Property 5: 审定数 = 未审 + 账项调整 + 重分类调整（源模板 E8/I8）', () => {
  const amount = () => fc.float({ min: -1e9, max: 1e9, noNaN: true })

  it('d1WithAudited 恒满足公式', () => {
    fc.assert(
      fc.property(
        fc.record({ u: amount(), a: amount(), r: amount(), cu: amount(), ca: amount(), cr: amount() }),
        (v) => {
          const out = d1WithAudited({
            priorUnadjusted: v.u,
            priorAje: v.a,
            priorRje: v.r,
            currentUnadjusted: v.cu,
            currentAje: v.ca,
            currentRje: v.cr,
          })
          expect(out.priorAudited).toBeCloseTo(v.u + v.a + v.r, 4)
          expect(out.currentAudited).toBeCloseTo(v.cu + v.ca + v.cr, 4)
        },
      ),
      { numRuns: 80 },
    )
  })

  it('从锚点读出的审定数与 d1Audited 一致', () => {
    const m = mapOf({
      [d1AdjAnchor('gross', 'bank', 'current-unadj')]: '1000',
      [d1AdjAnchor('gross', 'bank', 'current-aje')]: '50',
      [d1AdjAnchor('gross', 'bank', 'current-rje')]: '-20',
    })
    const t = readD1AdjudicationTotals(m)
    expect(t.gross.bank.currentAudited).toBe(d1Audited(1000, 50, -20))
    expect(t.gross.bank.currentAudited).toBe(1030)
  })
})

// ─── Property 6: 净值恒等 ────────────────────────────────────────────────────

describe('Property 6: 净值 = 原值 − 坏账（源模板 B16=B8-B12 逐列独立）', () => {
  it('d1NetAmounts 逐列相减', () => {
    const g = d1WithAudited({
      priorUnadjusted: 100, priorAje: 1, priorRje: 2,
      currentUnadjusted: 200, currentAje: 3, currentRje: 4,
    })
    const p = d1WithAudited({
      priorUnadjusted: 10, priorAje: 0, priorRje: 1,
      currentUnadjusted: 20, currentAje: 1, currentRje: 0,
    })
    const net = d1NetAmounts(g, p)
    expect(net.priorUnadjusted).toBe(90)
    expect(net.currentUnadjusted).toBe(180)
    expect(net.priorAudited).toBe(g.priorAudited - p.priorAudited)
    expect(net.currentAudited).toBe(g.currentAudited - p.currentAudited)
  })

  it('readD1AdjudicationTotals 的 netTotal 恒 = grossTotal − provisionTotal', () => {
    const m = mapOf({
      [D1_CAT_ROWS_KEY]: JSON.stringify([
        { rowId: 'fixed-bank', category: '银行承兑汇票', priorUnadjusted: 300, currentIncrease: 100, currentDecrease: 40 },
        { rowId: 'fixed-commercial', category: '商业承兑汇票', priorUnadjusted: 200, currentIncrease: 0, currentDecrease: 50 },
      ]),
      [D1_BD_NOTETYPE_KEY]: JSON.stringify([
        { rowId: 'fixed-bank', noteType: '银行承兑汇票小计', isFixed: true, priorUnadjusted: 30, currentUnadjusted: 20 },
        { rowId: 'fixed-commercial', noteType: '商业承兑汇票小计', isFixed: true, priorUnadjusted: 10, currentUnadjusted: 5 },
      ]),
    })
    const t = readD1AdjudicationTotals(m)
    expect(t.netTotal.currentAudited).toBeCloseTo(
      t.grossTotal.currentAudited - t.provisionTotal.currentAudited,
      6,
    )
    expect(t.netTotal.priorAudited).toBeCloseTo(
      t.grossTotal.priorAudited - t.provisionTotal.priorAudited,
      6,
    )
  })
})

// ─── Property 7: 动态票据种类不丢金额 ────────────────────────────────────────

describe('Property 7: 动态票据种类不丢金额', () => {
  it('D1-2 的「信用证」等动态类别必须出现在审定表行集', () => {
    const m = mapOf({
      [D1_CAT_ROWS_KEY]: JSON.stringify([
        { rowId: 'fixed-bank', category: '银行承兑汇票', priorUnadjusted: 37550925.38, currentIncrease: 138564072.55, currentDecrease: 163654386.64 },
        { rowId: 'fixed-commercial', category: '商业承兑汇票', priorUnadjusted: 38977698.35, currentIncrease: 13110869.14, currentDecrease: 44339980.6 },
        { rowId: 'dynamic-tb-1', category: '信用证', priorUnadjusted: 55021577.23, currentIncrease: 10490692.64, currentDecrease: 65512269.87 },
      ]),
    })
    const cats = readD1Categories(m)
    expect(cats.map((c) => c.label)).toEqual(['银行承兑汇票', '商业承兑汇票', '信用证'])
    // 固定行恒排在前
    expect(cats[0].isFixed && cats[1].isFixed).toBe(true)
    expect(cats[2].isFixed).toBe(false)

    const t = readD1AdjudicationTotals(m)
    // 实证数据（项目 0ec33ac9 / 2025）：期末合计 = tb_balance 1121 期末 20,209,198.18
    expect(t.grossTotal.currentUnadjusted).toBeCloseTo(20209198.18, 2)
    // 期初合计含信用证 55,021,577.23，写死两行时会丢掉它
    expect(t.grossTotal.priorUnadjusted).toBeCloseTo(131550200.96, 2)
  })

  it('原值小计恒 = D1-2 各类别期末未审之和（任意类别集）', () => {
    const rowGen = fc.record({
      prior: fc.float({ min: 0, max: 1e6, noNaN: true }),
      inc: fc.float({ min: 0, max: 1e6, noNaN: true }),
      dec: fc.float({ min: 0, max: 1e6, noNaN: true }),
    })
    fc.assert(
      fc.property(fc.array(rowGen, { minLength: 1, maxLength: 6 }), (rows) => {
        const m = mapOf({
          [D1_CAT_ROWS_KEY]: JSON.stringify(
            rows.map((r, i) => ({
              rowId: `dynamic-tb-${i}`,
              category: `种类${i}`,
              priorUnadjusted: r.prior,
              currentIncrease: r.inc,
              currentDecrease: r.dec,
            })),
          ),
        })
        const expected = rows.reduce((s, r) => s + r.prior + r.inc - r.dec, 0)
        const t = readD1AdjudicationTotals(m)
        expect(t.grossTotal.currentUnadjusted).toBeCloseTo(expected, 3)
      }),
      { numRuns: 60 },
    )
  })

  it('🔴 派生列不落库：D1-2 行不含 currentUnadjusted 时仍必须现算出期末未审', () => {
    // 这正是改造前审定表期末恒 0 的根因（serializeRows 有意不存派生列）
    const raw = [{ rowId: 'fixed-bank', category: '银行承兑汇票', priorUnadjusted: 100, currentIncrease: 60, currentDecrease: 20 }]
    expect(Object.keys(raw[0])).not.toContain('currentUnadjusted')
    const amounts = readD1CategoryAmounts(mapOf({ [D1_CAT_ROWS_KEY]: JSON.stringify(raw) }))
    expect(amounts.bank.currentUnadjusted).toBe(140)
  })
})

// ─── 坏账按票据种类小计 ──────────────────────────────────────────────────────

describe('readD1BadDebtByNoteType（源模板 D1-4 R23/R24 → D1-1 坏账区块）', () => {
  it('按 rowId 映射到与原值同一 slug，使净值可逐类别相减', () => {
    const m = mapOf({
      [D1_BD_NOTETYPE_KEY]: JSON.stringify([
        { rowId: 'fixed-bank', noteType: '银行承兑汇票小计', priorUnadjusted: 30, currentUnadjusted: 20 },
      ]),
    })
    const out = readD1BadDebtByNoteType(m)
    expect(Object.keys(out)).toEqual(['bank'])
    expect(out.bank.currentUnadjusted).toBe(20)
  })

  it('未填该块时坏账行不标为「已取数」（改造前恒标 true 却是 0）', () => {
    const m = mapOf({
      [D1_CAT_ROWS_KEY]: JSON.stringify([
        { rowId: 'fixed-bank', category: '银行承兑汇票', priorUnadjusted: 100, currentIncrease: 0, currentDecrease: 0 },
      ]),
    })
    const t = readD1AdjudicationTotals(m)
    expect(t.grossFromCrossSheet.bank).toBe(true)
    expect(t.provisionFromCrossSheet.bank).toBe(false)
  })
})

// ─── 汇总工具 ────────────────────────────────────────────────────────────────

describe('d1SumAmounts', () => {
  it('空数组返回全 0', () => {
    const s = d1SumAmounts([])
    expect(s.priorAudited).toBe(0)
    expect(s.currentAudited).toBe(0)
  })
})
