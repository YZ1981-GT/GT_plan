/**
 * D1 披露同步载荷 —— 比率列口径守卫
 *
 * Spec: .kiro/specs/d1-extraction-chain-completion/ (Property 8 / Requirement 6.1, 6.2)
 *
 * 附注列头是「比例(%)」「预期信用损失率(%)」，故同步载荷里所有比率字段必须是
 * **百分数**（分数 × 100），且**合计行按合计金额现算**（比率不可加）。
 *
 * 改造前两处违反：
 *   * 国企「按组合计提坏账准备的应收票据」表 `loss_rate` 漏乘 100 → 附注显示 0.06 而非 5.75；
 *   * 上市组合表 / 单项计提表**合计行**损失率硬编码 0 → 附注恒 0.00%（源模板
 *     `D68/D74/D82/G82/D89/G89` 都是有公式的）。
 */
import { describe, expect, it } from 'vitest'
import * as fc from 'fast-check'
import {
  D1_LISTED_SUBTABLE,
  D1_SOE_SUBTABLE,
  buildD1SyncPayload,
  type D1DisclosureSnapshot,
} from '../d1NoteSectionMap'

/** 比率字段名（附注列头带 (%) 的那些）。 */
const RATE_KEYS = ['ratio', 'loss_rate', 'end_loss_rate', 'prior_loss_rate']

function emptySnapshot(): D1DisclosureSnapshot {
  const zeroSummary = {
    category: '',
    endBalance: 0,
    endProvision: 0,
    endBookValue: 0,
    priorBalance: 0,
    priorProvision: 0,
    priorBookValue: 0,
  }
  return {
    summaryRows: [],
    summaryTotal: zeroSummary,
    pledgedRows: [],
    pledgedTotal: { category: '合计', pledgedAmount: 0 },
    endorsedRows: [],
    endorsedTotal: { category: '合计', derecognizedAmount: 0, notDerecognizedAmount: 0 },
    transferRows: [],
    transferTotal: { category: '合计', transferAmount: 0 },
    classEndRows: [],
    classPriorRows: [],
    writeOffAmount: 0,
    writeOffDetailRows: [],
    notes: {},
  }
}

describe('Property 8: 比率列口径统一为百分数', () => {
  it('国企组合计提表 loss_rate 必须是百分数（×100）', () => {
    const snap = emptySnapshot()
    snap.soePortfolioRows = [
      { name: '1年以内', balance: 1000, provision: 57.5, lossRate: 0.0575 },
      { name: '合计', balance: 1000, provision: 57.5, lossRate: 0.0575, isTotal: true },
    ]
    const payload = buildD1SyncPayload('soe', 'wp-1', ['soe_standalone'], snap)
    const rows = payload.sub_table_data[D1_SOE_SUBTABLE.portfolio] as Array<Record<string, unknown>>
    expect(rows[0].loss_rate).toBeCloseTo(5.75, 6)
    expect(rows[1].loss_rate).toBeCloseTo(5.75, 6)
  })

  it('上市组合计提表合计行损失率 = 合计坏账 ÷ 合计余额 ×100（不得为 0）', () => {
    const snap = emptySnapshot()
    snap.bankPortfolioEndRows = [
      { drawerTypeOrAging: '1年以内', balance: 800, provision: 40, lossRate: 0.05 },
      { drawerTypeOrAging: '1至2年', balance: 200, provision: 20, lossRate: 0.1 },
    ]
    snap.bankPortfolioPriorRows = [
      { drawerTypeOrAging: '1年以内', balance: 500, provision: 25, lossRate: 0.05 },
    ]
    const payload = buildD1SyncPayload('listed', 'wp-1', ['listed_standalone'], snap)
    const rows = payload.sub_table_data[D1_LISTED_SUBTABLE.portfolioBank] as Array<
      Record<string, unknown>
    >
    const total = rows.find((r) => r.is_total)!
    expect(total.end_balance).toBe(1000)
    expect(total.end_provision).toBe(60)
    expect(total.end_loss_rate).toBeCloseTo(6, 6) // 60/1000*100
    expect(total.prior_loss_rate).toBeCloseTo(5, 6) // 25/500*100
  })

  it('单项计提表合计行损失率同样现算（源模板 D68/D74）', () => {
    const snap = emptySnapshot()
    snap.individualEndRows = [
      { name: 'A 公司', balance: 600, provision: 60, lossRate: 0.1 },
      { name: 'B 公司', balance: 400, provision: 20, lossRate: 0.05 },
    ]
    const payload = buildD1SyncPayload('listed', 'wp-1', ['listed_standalone'], snap)
    const rows = payload.sub_table_data[D1_LISTED_SUBTABLE.individualEnd] as Array<
      Record<string, unknown>
    >
    const total = rows.find((r) => r.is_total)!
    expect(total.balance).toBe(1000)
    expect(total.provision).toBe(80)
    expect(total.loss_rate).toBeCloseTo(8, 6)
  })

  it('分母为 0 时比率返回 0（源模板 IFERROR 语义），不产生 NaN/Infinity', () => {
    const snap = emptySnapshot()
    snap.individualEndRows = [{ name: '空行', balance: 0, provision: 0, lossRate: 0 }]
    snap.bankPortfolioEndRows = [
      { drawerTypeOrAging: '空段', balance: 0, provision: 0, lossRate: 0 },
    ]
    const payload = buildD1SyncPayload('listed', 'wp-1', ['listed_standalone'], snap)
    for (const rows of Object.values(payload.sub_table_data)) {
      if (!Array.isArray(rows)) continue
      for (const row of rows as Array<Record<string, unknown>>) {
        for (const k of RATE_KEYS) {
          if (row[k] === undefined) continue
          expect(Number.isFinite(row[k] as number), `${k} 非有限值`).toBe(true)
        }
      }
    }
  })

  it('🔴 全量扫描：两个变体载荷里没有任何比率字段是非有限值', () => {
    const amount = () => fc.float({ min: 0, max: 1e7, noNaN: true })
    fc.assert(
      fc.property(
        fc.record({ bal: amount(), prov: amount() }),
        fc.constantFrom('listed' as const, 'soe' as const),
        (v, variant) => {
          const snap = emptySnapshot()
          snap.individualEndRows = [
            { name: 'X', balance: v.bal, provision: v.prov, lossRate: 0 },
          ]
          snap.soePortfolioRows = [
            { name: '1年以内', balance: v.bal, provision: v.prov, lossRate: 0 },
          ]
          snap.bankPortfolioEndRows = [
            { drawerTypeOrAging: '1年以内', balance: v.bal, provision: v.prov, lossRate: 0 },
          ]
          const payload = buildD1SyncPayload(variant, 'wp-1', null, snap)
          for (const rows of Object.values(payload.sub_table_data)) {
            if (!Array.isArray(rows)) continue
            for (const row of rows as Array<Record<string, unknown>>) {
              for (const k of RATE_KEYS) {
                if (row[k] === undefined) continue
                expect(Number.isFinite(row[k] as number)).toBe(true)
              }
            }
          }
        },
      ),
      { numRuns: 50 },
    )
  })
})
