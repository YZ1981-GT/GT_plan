import { describe, it, expect } from 'vitest'
import {
  F1_LISTED_SUBTABLE,
  F1_SOE_SUBTABLE,
  buildF1ListedSubTableData,
  buildF1SoeSubTableData,
  buildF1SyncPayload,
  type F1ListedSyncSnapshot,
  type F1SoeSyncSnapshot,
} from '../f1DisclosureSyncPayload'

const listedSnap: F1ListedSyncSnapshot = {
  agingRows: [], agingTotal: { label: '小计', endAmount: 0, endPct: 0, priorAmount: 0, priorPct: 0 },
  impairmentProvision: 0, impairmentPrior: 0, agingNet: { label: '合计', endAmount: 0, priorAmount: 0 },
  over1YearRows: [], over1YearTotal: { endBalance: 0, proportionPct: 0, impairment: 0 },
  top5Rows: [], top5Total: { endBalance: 0, proportionPct: 0 }, top5SummaryText: '',
  noteAging: '', noteOver1Year: '', noteTop5: '',
}

const soeSnap: F1SoeSyncSnapshot = {
  agingRows: [], agingTotal: {
    label: '小计', endAmount: 0, endPct: 0, endBadDebt: 0, priorAmount: 0, priorPct: 0, priorBadDebt: 0,
  },
  agingNet: { label: '合计', endAmount: 0, priorAmount: 0 },
  over1YearRows: [], over1YearTotal: { endBalance: 0 },
  top5Rows: [], top5Total: { endBalance: 0, proportionPct: 0, badDebt: 0 },
  noteAging: '', noteOver1Year: '', noteTop5: '',
}

// disclosure-table-sync-convergence：F1 预付款项英文键子表须携带源对齐中文列头
describe('F1 预付款项披露 columns 契约', () => {
  it('上市：按账龄表 5 列两级表头（期末余额 / 上年年末余额）', () => {
    const payload = buildF1SyncPayload('listed', 'wp-f1', null, buildF1ListedSubTableData(listedSnap))
    expect(payload).not.toBeNull()
    const cols = payload!.columns![F1_LISTED_SUBTABLE.AGING]
    expect(cols[0].is_label).toBe(true)
    expect(cols.map((c) => c.label)).toEqual(['账龄', '金额', '比例%', '金额', '比例%'])
    // 两级表头唯一机制：group → 后端 _extract_column_groups → _column_groups
    expect(cols.map((c) => c.group ?? '')).toEqual([
      '', '期末余额', '期末余额', '上年年末余额', '上年年末余额',
    ])
    expect(cols[1].key).toBe('end_amount')
    expect(cols[3].key).toBe('prior_amount')
  })

  it('上市：超1年重要表第 4 列为减值准备（无「未结算的原因」列，F7-9 listed）', () => {
    const payload = buildF1SyncPayload('listed', 'wp-f1', null, buildF1ListedSubTableData(listedSnap))
    const cols = payload!.columns![F1_LISTED_SUBTABLE.OVER1]
    expect(cols.map((c) => c.label)).toEqual([
      '债务人名称', '账面余额', '占预付款项合计的比例（%）', '减值准备',
    ])
    expect(cols.map((c) => c.key)).toEqual(['label', 'balance', 'proportion_pct', 'impairment'])
    // 单级表头显式声明，抑制后端前缀反猜父表头
    expect(cols[0].flat).toBe(true)
  })

  it('上市：前五名表 3 列（无减值准备列，F7-13 listed）', () => {
    const payload = buildF1SyncPayload('listed', 'wp-f1', null, buildF1ListedSubTableData(listedSnap))
    const cols = payload!.columns![F1_LISTED_SUBTABLE.TOP5]
    expect(cols.map((c) => c.label)).toEqual([
      '单位名称', '预付款项期末余额', '占预付款项期末余额合计数的比例%',
    ])
  })

  it('上市：账龄表推 各段 + 小计 + 减：减值准备 + 合计，双期均给值', () => {
    const sub = buildF1ListedSubTableData({
      ...listedSnap,
      agingRows: [{ label: '1年以内', endAmount: 900, endPct: 90, priorAmount: 800, priorPct: 80 }],
      agingTotal: { label: '小计', endAmount: 900, endPct: 100, priorAmount: 800, priorPct: 100 },
      impairmentProvision: 30,
      impairmentPrior: 20,
      agingNet: { label: '合计', endAmount: 870, priorAmount: 780 },
    })
    const rows = sub[F1_LISTED_SUBTABLE.AGING] as Array<Record<string, unknown>>
    expect(rows.map((r) => r.label)).toEqual(['1年以内', '小计', '减：减值准备', '合计'])
    expect(rows[2].end_amount).toBe(30)
    expect(rows[2].prior_amount).toBe(20)
    expect(rows[3].end_amount).toBe(870)
    expect(rows[3].prior_amount).toBe(780)
  })

  it('上市：载荷上报旧表名「单位名称」待清理，且不含本次推送的键', () => {
    const sub = buildF1ListedSubTableData(listedSnap)
    expect(sub._removed_table_keys).toEqual(['单位名称'])
    for (const k of sub._removed_table_keys as string[]) {
      expect(sub[k]).toBeUndefined()
    }
  })

  it('国企：按账龄表收敛为 5 列两级表头（期末数 / 期初数）', () => {
    const payload = buildF1SyncPayload('soe', 'wp-f1', null, buildF1SoeSubTableData(soeSnap))
    const cols = payload!.columns![F1_SOE_SUBTABLE.AGING]
    expect(cols.map((c) => c.label)).toEqual(['账龄', '金额', '比例（%）', '金额', '比例（%）'])
    expect(cols.map((c) => c.group ?? '')).toEqual(['', '期末数', '期末数', '期初数', '期初数'])
  })

  it('国企：超1年大额表以债权单位为标签列，五列齐备', () => {
    const payload = buildF1SyncPayload('soe', 'wp-f1', null, buildF1SoeSubTableData(soeSnap))
    const over1 = payload!.columns![F1_SOE_SUBTABLE.OVER1]
    expect(over1[0].is_label).toBe(true)
    expect(over1[0].key).toBe('creditor_unit')
    expect(over1.map((c) => c.label)).toEqual([
      '债权单位', '债务单位', '期末余额', '账龄', '未结算的原因',
    ])
  })

  it('国企：前五名表第 4 列名为减值准备（非坏账准备，F7-13 soe）', () => {
    const payload = buildF1SyncPayload('soe', 'wp-f1', null, buildF1SoeSubTableData(soeSnap))
    const cols = payload!.columns![F1_SOE_SUBTABLE.TOP5]
    expect(cols.map((c) => c.label)).toEqual([
      '债务人名称', '账面余额', '占预付款项合计的比例（%）', '减值准备',
    ])
    expect(cols[3].key).toBe('impairment')
  })

  it('国企：逐段减值准备聚合为「减：减值准备」行，合计 = 小计 − 减值准备', () => {
    const sub = buildF1SoeSubTableData({
      ...soeSnap,
      agingRows: [{
        label: '1年以内（含1年）',
        endAmount: 800, endPct: 80, endBadDebt: 8,
        priorAmount: 700, priorPct: 70, priorBadDebt: 7,
      }],
      agingTotal: {
        label: '小计',
        endAmount: 1000, endPct: 100, endBadDebt: 12,
        priorAmount: 900, priorPct: 100, priorBadDebt: 9,
      },
      agingNet: { label: '合计', endAmount: 988, priorAmount: 891 },
    })
    const rows = sub[F1_SOE_SUBTABLE.AGING] as Array<Record<string, unknown>>
    expect(rows.map((r) => r.label)).toEqual(['1年以内（含1年）', '小计', '减：减值准备', '合计'])
    // 逐段列在附注侧被折成一行（附注为 5 列，无逐段减值准备列）
    expect(rows[0].end_bad_debt).toBeUndefined()
    expect(rows[2].end_amount).toBe(12)
    expect(rows[2].prior_amount).toBe(9)
    expect(rows[3].end_amount).toBe(988)
    expect(rows[3].prior_amount).toBe(891)
    expect(sub._removed_table_keys).toBeUndefined()
  })

  it('每张表 columns[0].label 与该表首列语义一致，且无英文键当列头', () => {
    for (const variant of ['listed', 'soe'] as const) {
      const sub = variant === 'listed'
        ? buildF1ListedSubTableData(listedSnap)
        : buildF1SoeSubTableData(soeSnap)
      const payload = buildF1SyncPayload(variant, 'wp-f1', null, sub)!
      for (const [name, defs] of Object.entries(payload.columns!)) {
        expect(defs.length, name).toBeGreaterThan(0)
        expect(defs.filter((d) => d.is_label), name).toHaveLength(1)
        for (const d of defs) {
          expect(d.label.trim(), `${name}.${d.key}`).not.toBe('')
          expect(/^[a-z_]+$/.test(d.label), `${name}.${d.key} 用了英文键当列头`).toBe(false)
        }
      }
    }
  })
})
