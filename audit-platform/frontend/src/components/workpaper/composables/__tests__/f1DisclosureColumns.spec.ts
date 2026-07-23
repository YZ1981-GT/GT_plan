import { describe, it, expect } from 'vitest'
import {
  buildF1ListedSubTableData,
  buildF1SoeSubTableData,
  buildF1SyncPayload,
  type F1ListedSyncSnapshot,
  type F1SoeSyncSnapshot,
} from '../f1DisclosureSyncPayload'

const listedSnap: F1ListedSyncSnapshot = {
  agingRows: [], agingTotal: { label: '小计', endAmount: 0, endPct: 0, priorAmount: 0, priorPct: 0 },
  impairmentProvision: 0, agingNet: { label: '合计', endAmount: 0, priorAmount: 0 },
  over1YearRows: [], over1YearTotal: { endBalance: 0, proportionPct: 0, impairment: 0 },
  top5Rows: [], top5Total: { endBalance: 0, proportionPct: 0 }, top5SummaryText: '',
  noteAging: '', noteOver1Year: '', noteTop5: '',
}

const soeSnap: F1SoeSyncSnapshot = {
  agingRows: [], agingTotal: {
    label: '合计', endAmount: 0, endPct: 0, endBadDebt: 0, priorAmount: 0, priorPct: 0, priorBadDebt: 0,
  },
  over1YearRows: [], over1YearTotal: { endBalance: 0 },
  top5Rows: [], top5Total: { endBalance: 0, proportionPct: 0, badDebt: 0 },
  noteAging: '', noteOver1Year: '', noteTop5: '',
}

// disclosure-table-sync-convergence：F1 预付款项英文键子表须携带源对齐中文列头
describe('F1 预付款项披露 _columns 覆盖', () => {
  it('listed 附带源对齐列头（账龄/期末数/上年年末数）', () => {
    const payload = buildF1SyncPayload('listed', 'wp-f1', null, buildF1ListedSubTableData(listedSnap))
    expect(payload).not.toBeNull()
    const cols = payload!.columns!
    expect(cols['预付款项按账龄披露'][0].is_label).toBe(true)
    expect(cols['预付款项按账龄披露'].map((c) => c.label)).toEqual([
      '账龄', '期末数-金额', '期末数-比例%', '上年年末数-金额', '上年年末数-比例%',
    ])
    // 英文键映射：end_amount → 期末数-金额（不用英文键当 header）
    expect(cols['预付款项按账龄披露'][1].key).toBe('end_amount')
    expect(cols['单位名称'].map((c) => c.label)).toEqual([
      '单位名称', '预付款项期末余额', '占预付款项期末余额合计数的比例%',
    ])
  })

  it('soe 前置多级账龄表 + 债权/债务单位标签列', () => {
    const payload = buildF1SyncPayload('soe', 'wp-f1', null, buildF1SoeSubTableData(soeSnap))
    const cols = payload!.columns!
    expect(cols['预付款项按账龄列示'].map((c) => c.label)).toEqual([
      '账龄', '期末数-账面余额金额', '期末数-账面余额比例%', '期末数-坏账准备',
      '期初数-账面余额金额', '期初数-账面余额比例%', '期初数-坏账准备',
    ])
    // 大额表以债权单位为标签列（无 label 键）
    const over1 = cols['账龄超过1年的大额预付款项']
    expect(over1[0].is_label).toBe(true)
    expect(over1[0].key).toBe('creditor_unit')
    expect(over1.map((c) => c.label)).toEqual([
      '债权单位', '债务单位', '期末余额', '账龄', '未结算的原因',
    ])
  })
})
