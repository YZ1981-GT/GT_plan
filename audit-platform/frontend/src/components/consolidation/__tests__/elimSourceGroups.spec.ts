/**
 * 工作底稿 → 草稿分录来源分组（spec consol-elimination-single-source-push 任务 10.2 / 需求 2）
 *
 * - 模拟权益法：三步各家子企业一组，来源键 `equity_sim:step{n}:{企业代码}`，零金额行 / 全零企业不成组；
 * - 内部往来：每对科目抵销（借负债方、贷资产方）+ 本方 / 对方坏账冲回；差异只提示不生成；
 * - 内部交易：收入成本抵销 + 未实现利润（显式 unrealized_profit 类型）；
 * - 金额 Decimal 精确（0.1 + 0.2 = 0.3），每组借贷平衡；
 * - 声明负责的来源：有已保存数据或本次算出分组的来源；
 * - 已保存行恢复：缺字段补齐、账龄数组按段数补空。
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import Decimal from 'decimal.js'
import {
  arapGroups,
  arapPairs,
  arapPreviewLines,
  arapSides,
  buildSourceGroups,
  companyCodeResolver,
  declaredOrigins,
  equitySimGroups,
  restoreArApRows,
  restoreTradeRows,
  savedAgingLength,
  sourceGroupsByOrigin,
  tradeGroups,
  tradePreviewLines,
  tradeTotals,
} from '../composables/elimSourceGroups'
import type { WorksheetSourceGroup } from '@/services/consolidationApi'

const COMPANIES = [
  { name: '甲公司', code: 'A' },
  { name: '乙公司', code: 'B' },
]

function simRows(values: Record<string, (number | string | null)[]>) {
  const step = (title: string) => ({ step: title, isStep: true, direction: '', subject: '' })
  const row = (direction: string, subject: string, detail = '', key = '') => ({
    step: '', direction, subject, detail, values: values[key || `${subject}${detail}`] || [],
  })
  return [
    step('期初长投模拟'),
    row('借', '长期股权投资', '损益调整', 's1-ltei'),
    row('贷', '年初未分配利润', '', 's1-ret'),
    step('模拟当期长期股权投资'),
    row('借', '长期股权投资', '损益调整', 's2-ltei'),
    row('贷', '投资收益', '', 's2-inc'),
    step('还原分红影响'),
    row('借', '投资收益', '', 's3-inc'),
    row('贷', '长期股权投资', '损益调整', 's3-ltei'),
    step('股比发生变动对享有净资产的影响'),
    row('借', '长期股权投资', '损益调整', 's4-ltei'),
  ]
}

function balanced(g: WorksheetSourceGroup): boolean {
  const sum = (dir: string) => g.lines.filter((l) => l.direction === dir)
    .reduce((s, l) => s.plus(new Decimal(String(l.amount))), new Decimal(0))
  return sum('借').equals(sum('贷'))
}

describe('模拟权益法', () => {
  it('三步各家一组：来源键带步骤与企业代码，零金额行与全零企业不成组，第 4 步不生成', () => {
    const groups = equitySimGroups(simRows({
      's1-ltei': [100, 0], 's1-ret': [100, null],
      's2-ltei': [30, 20], 's2-inc': [30, '20'],
      's3-inc': [0, 8], 's3-ltei': [null, '8'],
      's4-ltei': [999, 999],
    }), COMPANIES, 'G')
    expect(groups.map((g) => g.origin_key)).toEqual([
      'equity_sim:step1:A', 'equity_sim:step2:A', 'equity_sim:step2:B', 'equity_sim:step3:B',
    ])
    expect(groups[3].description).toBe('模拟权益法·还原分红：乙公司')
    expect(groups[3].lines.map((l) => [l.subject, l.direction, l.amount])).toEqual([
      ['投资收益', '借', '8'], ['长期股权投资', '贷', '8'],
    ])
    expect(groups.every((g) => g.origin === 'ws_equity_sim')).toBe(true)
    const s1 = groups[0]
    expect(s1.lines).toEqual([
      { subject: '长期股权投资', detail: '损益调整', direction: '借', amount: '100' },
      { subject: '年初未分配利润', detail: null, direction: '贷', amount: '100' },
    ])
    expect(s1.related_company_codes).toEqual(['A', 'G'])
    expect(s1.description).toBe('模拟权益法·期初模拟：甲公司')
  })

  it('企业没有代码时来源键用名称（基本信息表未填代码），交易方不含空代码', () => {
    const [g] = equitySimGroups(simRows({ 's2-ltei': [5], 's2-inc': [5] }), [{ name: '丙公司', code: '' }], 'G')
    expect(g.origin_key).toBe('equity_sim:step2:名称:丙公司')
    expect(g.related_company_codes).toEqual(['G'])
  })

  it('Decimal 精确：0.1 + 0.2 的列直接按值成行，不出现浮点尾数', () => {
    const [g] = equitySimGroups(simRows({ 's2-ltei': ['0.30'], 's2-inc': ['0.1'] }), COMPANIES.slice(0, 1), 'G')
    expect(g.lines.map((l) => l.amount)).toEqual(['0.3', '0.1'])
  })
})

describe('内部往来', () => {
  const ROWS = [
    { localCompany: '甲公司', localSubject: '应收账款', localAmounts: [60, 40], localImpairments: [3, 0],
      remoteCompany: '乙公司', remoteSubject: '应付账款', remoteAmounts: [90, 0], remoteImpairments: [] },
    { localCompany: '甲公司', localSubject: '应收账款', localAmounts: [5], localImpairments: [],
      remoteCompany: '母公司', remoteSubject: '应付账款', remoteAmounts: [5], remoteImpairments: [1] },
  ]

  it('同一对科目跨行汇总；抵销取两边较小值，借负债方贷资产方（与本方 / 对方填哪边无关）', () => {
    const pairs = arapPairs(ROWS)
    expect(pairs).toHaveLength(1)
    const p = pairs[0]
    expect([p.local.toString(), p.remote.toString(), p.localImp.toString(), p.remoteImp.toString()])
      .toEqual(['105', '95', '3', '1'])
    expect(p.companies).toEqual(['甲公司', '乙公司', '母公司'])
    expect(arapSides(p)).toEqual({ debit: '应付账款', credit: '应收账款' })
    expect(arapSides({ localSubject: '应付账款', remoteSubject: '应收账款' })).toEqual({ debit: '应付账款', credit: '应收账款' })
    expect(arapSides({ localSubject: '其他', remoteSubject: '某科目' })).toEqual({ debit: '其他', credit: '某科目' })
  })

  it('分组：往来抵销 + 本方 / 对方坏账冲回各一组；交易方按名称解析（母公司 = 本合并企业，认不出的不猜）', () => {
    const codeOf = companyCodeResolver(COMPANIES, 'G')
    const groups = arapGroups(arapPairs(ROWS), (n) => codeOf(n))
    expect(groups.map((g) => g.origin_key)).toEqual([
      'internal_arap:pair:应收账款|应付账款',
      'internal_arap:bad_debt_local:应收账款|应付账款',
      'internal_arap:bad_debt_remote:应收账款|应付账款',
    ])
    expect(groups[0].lines).toEqual([
      { subject: '应付账款', detail: null, direction: '借', amount: '95' },
      { subject: '应收账款', detail: null, direction: '贷', amount: '95' },
    ])
    expect(groups[1].lines.map((l) => [l.subject, l.direction, l.amount])).toEqual([
      ['坏账准备', '借', '3'], ['信用减值损失', '贷', '3'],
    ])
    expect(groups.every((g) => g.related_company_codes.join() === 'A,B,G')).toBe(true)
    expect(companyCodeResolver(COMPANIES, 'G')('不认识的公司')).toBeNull()
  })

  it('预览：抵销与坏账冲回之后列出未抵销差异（本方 − 对方），差异不进生成分组', () => {
    const lines = arapPreviewLines(ROWS)
    expect(lines.map((l) => [l.direction, l.subject, l.amount])).toEqual([
      ['借', '应付账款', '95'], ['贷', '应收账款', '95'],
      ['借', '坏账准备', '3'], ['贷', '信用减值损失', '3'],
      ['借', '坏账准备', '1'], ['贷', '信用减值损失', '1'],
      ['—', '⚠️ 差异', '10'],
    ])
    expect(arapGroups(arapPairs(ROWS), () => null).flatMap((g) => g.lines).some((l) => l.direction === '—')).toBe(false)
  })
})

describe('内部交易', () => {
  const ROWS = [
    { sellerCompany: '甲公司', buyerCompany: '乙公司', sellerAmount: 100, buyerAmount: 80, unrealizedProfit: 20, inventoryRatio: 50 },
    { sellerCompany: '乙公司', buyerCompany: '', sellerAmount: 999, buyerAmount: 999, unrealizedProfit: 9, inventoryRatio: 100 },
    { sellerCompany: '乙公司', buyerCompany: '甲公司', sellerAmount: '0.1', buyerAmount: '0.2', unrealizedProfit: '0.3', inventoryRatio: '10' },
  ]

  it('浮点会出尾数的金额（0.1 + 0.2）按 Decimal 精确累加', () => {
    const t = tradeTotals([
      { sellerCompany: '甲公司', buyerCompany: '乙公司', sellerAmount: '0.1', buyerAmount: '0.1' },
      { sellerCompany: '乙公司', buyerCompany: '甲公司', sellerAmount: '0.2', buyerAmount: '0.2' },
    ])
    expect([t.revenue.toString(), t.cost.toString()]).toEqual(['0.3', '0.3'])
    expect(tradePreviewLines([
      { sellerCompany: '甲公司', buyerCompany: '乙公司', sellerAmount: '0.1', buyerAmount: '0.1' },
      { sellerCompany: '乙公司', buyerCompany: '甲公司', sellerAmount: '0.2', buyerAmount: '0.2' },
    ])[0].amount).toBe('0.3')
  })

  it('只计卖方买方都填的行；收入成本抵销取较小值；未实现利润 = Σ 未实现 × 留存率%（Decimal 精确）', () => {
    const t = tradeTotals(ROWS)
    expect([t.revenue.toString(), t.cost.toString(), t.unrealized.toString()]).toEqual(['100.1', '80.2', '10.03'])
    const groups = tradeGroups(t, companyCodeResolver(COMPANIES, 'G'))
    expect(groups.map((g) => [g.origin_key, g.entry_type ?? null])).toEqual([
      ['internal_trade:revenue', null], ['internal_trade:unrealized', 'unrealized_profit'],
    ])
    expect(groups[0].lines.map((l) => [l.subject, l.direction, l.amount])).toEqual([['营业收入', '借', '80.2'], ['营业成本', '贷', '80.2']])
    expect(groups[1].lines.map((l) => [l.subject, l.direction, l.amount])).toEqual([['营业成本', '借', '10.03'], ['存货', '贷', '10.03']])
    expect(groups[0].related_company_codes).toEqual(['A', 'B'])
    expect(tradePreviewLines(ROWS).map((l) => l.amount)).toEqual(['80.2', '80.2', '10.03', '10.03'])
  })

  it('没有金额 ⇒ 不成组', () => {
    expect(tradeGroups(tradeTotals([{ sellerCompany: '甲公司', buyerCompany: '乙公司' }]), () => null)).toEqual([])
  })
})

describe('汇总与声明负责的来源', () => {
  it('按来源分开，buildSourceGroups 顺序为模拟权益法 → 内部往来 → 内部交易', () => {
    const src = {
      equitySimRows: simRows({ 's2-ltei': [5], 's2-inc': [5] }),
      arapRows: [{ localSubject: '应收账款', localAmounts: [1], remoteSubject: '应付账款', remoteAmounts: [1] }],
      tradeRows: [{ sellerCompany: '甲公司', buyerCompany: '乙公司', sellerAmount: 2, buyerAmount: 2 }],
      companies: COMPANIES.slice(0, 1),
      rootCode: 'G',
    }
    const by = sourceGroupsByOrigin(src)
    expect([by.ws_equity_sim.length, by.ws_internal_arap.length, by.ws_internal_trade.length]).toEqual([1, 1, 1])
    expect(buildSourceGroups(src).map((g) => g.origin)).toEqual(['ws_equity_sim', 'ws_internal_arap', 'ws_internal_trade'])
  })

  it('有已保存数据或本次算出分组的来源才声明负责（未加载的表不能当成「算出来是空的」去删草稿）', () => {
    const empty = { ws_equity_sim: [], ws_internal_arap: [], ws_internal_trade: [] }
    expect(declaredOrigins(empty, new Set())).toEqual([])
    expect(declaredOrigins(empty, new Set(['internal_trade', 'info']))).toEqual(['ws_internal_trade'])
    const g = { origin: 'ws_internal_arap', origin_key: 'k', lines: [], related_company_codes: [] } as WorksheetSourceGroup
    expect(declaredOrigins({ ...empty, ws_internal_arap: [g] }, new Set(['equity_sim'])))
      .toEqual(['ws_equity_sim', 'ws_internal_arap'])
  })

  it('PBT：任意金额下每组借贷平衡、来源键在来源内唯一（max_examples=5 同口径 numRuns=5）', () => {
    const amount = fc.oneof(
      fc.constant(null), fc.constant(''),
      fc.integer({ min: -100000, max: 100000 }).map((c) => new Decimal(c).dividedBy(100).toString()),
    )
    fc.assert(fc.property(
      fc.array(amount, { minLength: 4, maxLength: 4 }),
      fc.array(fc.record({
        localSubject: fc.constantFrom('应收账款', '应付账款', '其他应收款'),
        remoteSubject: fc.constantFrom('应付账款', '预收款项', '应收账款'),
        localAmounts: fc.array(amount, { maxLength: 4 }),
        remoteAmounts: fc.array(amount, { maxLength: 4 }),
        localImpairments: fc.array(amount, { maxLength: 4 }),
        remoteImpairments: fc.array(amount, { maxLength: 4 }),
      }), { maxLength: 5 }),
      (sim, arap) => {
        const groups = buildSourceGroups({
          equitySimRows: simRows({ 's2-ltei': [sim[0], sim[1]], 's2-inc': [sim[0], sim[1]] }),
          arapRows: arap,
          tradeRows: [{ sellerCompany: '甲公司', buyerCompany: '乙公司', sellerAmount: sim[2], buyerAmount: sim[3] }],
          companies: COMPANIES,
          rootCode: 'G',
        })
        const keys = groups.map((g) => `${g.origin}|${g.origin_key}`)
        expect(new Set(keys).size).toBe(keys.length)
        for (const g of groups) {
          if (g.origin !== 'ws_equity_sim') expect(balanced(g)).toBe(true)
          expect(g.lines.every((l) => !new Decimal(String(l.amount)).isZero())).toBe(true)
        }
      },
    ), { numRuns: 5 })
  })
})

describe('已保存行恢复', () => {
  it('内部往来：缺字段补空、账龄数组按段数补齐；非对象行丢弃；账龄段数取最长数组', () => {
    const raw = [{ localSubject: '应收账款', localAmounts: [1, '2'] }, null, 'x', { remoteAmounts: [1, 2, 3, 4, 5, 6] }]
    expect(savedAgingLength(raw)).toBe(6)
    const rows = restoreArApRows(raw, 4)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toMatchObject({
      localSubject: '应收账款', localCompany: '', localAmounts: [1, 2, null, null], remoteAmounts: [null, null, null, null],
    })
    expect(rows[1].remoteAmounts).toEqual([1, 2, 3, 4, 5, 6])
    expect(restoreArApRows(undefined, 4)).toEqual([])
  })

  it('内部交易：数字字段转数字，空 / 非数为 null', () => {
    expect(restoreTradeRows([{ sellerCompany: ' 甲公司 ', sellerAmount: '12.5', buyerAmount: 'abc' }])).toEqual([{
      sellerCompany: '甲公司', buyerCompany: '', tradeType: '', sellerSubject: '', sellerAmount: 12.5,
      buyerSubject: '', buyerAmount: null, unrealizedProfit: null, inventoryRatio: null,
    }])
  })
})
