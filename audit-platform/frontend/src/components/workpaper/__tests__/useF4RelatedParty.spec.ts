import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  extractF4RelatedPartyCandidates,
  migrateF4RelatedPartyRows,
  useF4RelatedParty,
} from '../composables/useF4RelatedParty'
import type { ChecklistResponse } from '../composables/useF4FormData'

function options(entries: Array<[string, unknown]>) {
  const allResponses = ref(new Map<string, ChecklistResponse>(
    entries.map(([key, value]) => [key, {
      item_id: key,
      conclusion: null,
      remark: typeof value === 'string' ? value : JSON.stringify(value),
    }]),
  ))
  return {
    wpId: ref('wp1'),
    projectId: ref('p1'),
    allResponses,
    isReadonly: ref(false),
  }
}

describe('F4-6 从F4-2提取关联方', () => {
  const detailRows = [
    {
      rowId: 'a1',
      creditor: '甲集团',
      relatedPartyType: '合并范围内关联方',
      paymentNature: '货款',
      openingUnadjusted: 100,
      currentDebit: 20,
      currentCredit: 50,
      auditedAgingLt1: 130,
      subsequentPayment: 30,
    },
    {
      rowId: 'a2',
      creditor: '甲集团',
      relatedPartyType: '合并范围内关联方',
      paymentNature: '服务费',
      openingUnadjusted: 40,
      currentCredit: 10,
      auditedAging1to2: 50,
      subsequentPayment: 5,
    },
    {
      rowId: 'b1',
      creditor: '普通供应商',
      relatedPartyType: '非关联方',
      openingUnadjusted: 500,
      auditedAgingLt1: 500,
    },
  ]

  it('排除非关联方，并按实际债权人归集余额、账龄和交易性质', () => {
    const candidates = extractF4RelatedPartyCandidates(JSON.stringify(detailRows))
    expect(candidates).toHaveLength(1)
    expect(candidates[0]).toMatchObject({
      sourceRowId: 'a1|a2',
      partyName: '甲集团',
      relationship: '合并范围内关联方',
      openingBalance: 140,
      currentDebit: 20,
      currentCredit: 60,
      sourceClosingBalance: 180,
      aging: '1年以内、1～2年',
      transactionNature: '货款、服务费',
      postPaymentAmount: 35,
    })
  })
})

describe('F4-6旧数据迁移', () => {
  it('旧“增加/减少”等字段迁移为贷方/借方并保留旧评价', () => {
    const rows = migrateF4RelatedPartyRows(JSON.stringify([{
      id: 'old1',
      partyName: '乙公司',
      relationship: '联营企业',
      paymentNature: '设备款',
      openingBalance: 100,
      currentIncrease: 80,
      currentDecrease: 30,
      fairness: '基本公允',
      settlementCycle: '90天',
      isOverdue: '是',
      auditEvaluation: '需持续关注',
    }]))
    expect(rows[0]).toMatchObject({
      rowId: 'old1',
      partyName: '乙公司',
      relationship: '联营企业',
      transactionNature: '设备款',
      openingBalance: 100,
      currentDebit: 30,
      currentCredit: 80,
      sourceClosingBalance: 150,
    })
    expect(rows[0].remark).toContain('原定价公允性：基本公允')
    expect(rows[0].remark).toContain('原审计评价：需持续关注')
  })
})

describe('useF4RelatedParty — 公式、联动和风险', () => {
  it('手工行按期初+贷方-借方计算期末并汇总', () => {
    const opts = options([['F4-6-rows', [{
      rowId: 'r1',
      partyName: '丙公司',
      relationship: '合营企业',
      openingBalance: 200,
      currentDebit: 70,
      currentCredit: 120,
      aging: '1年以内',
      pricingPolicy: '市场定价',
      transactionNature: '货款',
      postPaymentAmount: 100,
      indexNo: 'F4-6-1',
    }]]])
    const composable = useF4RelatedParty(opts)
    expect(composable.rows.value[0].closingBalance).toBe(250)
    expect(composable.summary.value.closingTotal).toBe(250)
    expect(composable.summary.value.reconciliationDifference).toBe(0)
    composable.updateCell('r1', 'remark', '已核对')
    const persisted = JSON.parse(opts.allResponses.value.get('F4-6-rows')?.remark || '[]')
    expect(persisted[0].closingBalance).toBe(250)
  })

  it('同步F4-2关联方并提示关系细化、定价和索引缺失', () => {
    const opts = options([['F4-2-rows', [{
      rowId: 'd1',
      creditor: '关联供应商',
      relatedPartyType: '合并范围外关联方',
      paymentNature: '工程款',
      openingUnadjusted: 300,
      currentDebit: 100,
      currentCredit: 200,
      auditedAging2to3: 400,
    }]]])
    const composable = useF4RelatedParty(opts)
    expect(composable.pendingSyncCount.value).toBe(1)
    expect(composable.syncFromDetail()).toBe(1)
    expect(composable.rows.value[0]).toMatchObject({
      partyName: '关联供应商',
      closingBalance: 400,
      aging: '2～3年',
      linked: true,
    })
    expect(composable.rows.value[0].riskFlags).toContain('关联关系需细化')
    expect(composable.rows.value[0].riskFlags).toContain('定价政策未说明')
    expect(composable.rows.value[0].riskFlags).toContain('长期账龄且无期后付款')
  })

  it('联动行以F4-2审定期末为准，AJE不误报不一致', () => {
    const opts = options([['F4-2-rows', [{
      rowId: 'd1',
      creditor: '调整关联方',
      relatedPartyType: '联营企业',
      openingUnadjusted: 100,
      currentCredit: 50,
      closingAje: 20,
      auditedAgingLt1: 170,
    }]]])
    const composable = useF4RelatedParty(opts)
    composable.syncFromDetail()
    const row = composable.rows.value[0]
    expect(row.closingBalance).toBe(170)
    expect(row.sourceClosingBalance).toBe(170)
    expect(row.reconciliationDifference).toBe(0)
    expect(row.riskFlags).not.toContain('与F4-2审定数不一致')
    expect(row.riskLevel).not.toBe('danger')
  })
})
