import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  extractF4LongOutstandingCandidates,
  migrateF4LongOutstandingRows,
  useF4LongOutstanding,
} from '../composables/useF4LongOutstanding'
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

describe('F4-5 从F4-2提取1年以上实际债权人', () => {
  const detailRows = [
    {
      rowId: 'a1',
      creditor: '甲公司',
      paymentNature: '货款',
      openingUnadjusted: 100,
      currentCredit: 200,
      unadjustedAging1to2: 80,
      auditedAging1to2: 80,
    },
    {
      rowId: 'a2',
      creditor: '甲公司',
      paymentNature: '服务费',
      openingUnadjusted: 50,
      unadjustedAgingGt3: 50,
      auditedAgingGt3: 50,
    },
    {
      rowId: 'b1',
      creditor: '乙公司',
      openingUnadjusted: 500,
      unadjustedAgingLt1: 500,
      auditedAgingLt1: 500,
    },
  ]

  it('仅提取含1年以上账龄的债权人，重复名称自动归集', () => {
    const candidates = extractF4LongOutstandingCandidates(JSON.stringify(detailRows))
    expect(candidates).toHaveLength(1)
    expect(candidates[0]).toMatchObject({
      creditor: '甲公司',
      closingBalance: 350,
      auditedAmount: 350,
      aging: '1～2年、3年以上',
      businessDescription: '货款、服务费',
    })
    expect(candidates[0].sourceRowId).toBe('a1|a2')
  })
})

describe('F4-5旧数据迁移', () => {
  it('旧挂账字段迁移到源表11字段并保留处理建议', () => {
    const rows = migrateF4LongOutstandingRows(JSON.stringify([{
      id: 'old1',
      creditor: '丙公司',
      amount: 900,
      outstandingDays: 1200,
      paymentNature: '工程款',
      reason: '决算未完成',
      hasDispute: '是',
      shouldTransferIncome: '否',
      suggestion: '取得律师函',
    }]))
    expect(rows[0]).toMatchObject({
      rowId: 'old1',
      creditor: '丙公司',
      closingBalance: 900,
      aging: '3年以上',
      businessDescription: '工程款',
      unsettledReason: '决算未完成',
      litigation: '是',
      unableToPay: '否',
      auditedAmount: 900,
    })
    expect(rows[0].remark).toContain('原处理建议：取得律师函')
  })
})

describe('useF4LongOutstanding — 同步、风险及OCR回填', () => {
  const detailRows = [{
    rowId: 'd1',
    creditor: '甲供应商',
    paymentNature: '设备款',
    openingUnadjusted: 1000,
    unadjustedAgingGt3: 1000,
    auditedAgingGt3: 950,
    closingAje: -50,
  }]

  it('从F4-2同步并实时联动余额，检查字段在F4-5补充', () => {
    const opts = options([['F4-2-rows', detailRows]])
    const composable = useF4LongOutstanding(opts)
    expect(composable.pendingSyncCount.value).toBe(1)
    expect(composable.syncFromDetail()).toBe(1)
    expect(composable.rows.value).toHaveLength(1)
    expect(composable.rows.value[0]).toMatchObject({
      creditor: '甲供应商',
      closingBalance: 1000,
      auditedAmount: 950,
      aging: '3年以上',
      linked: true,
    })

    composable.updateCell(composable.rows.value[0].rowId, 'unsettledReason', '设备质保期未结束')
    expect(composable.rows.value[0].unsettledReason).toBe('设备质保期未结束')
    expect(composable.rows.value[0].riskFlags).toContain('含3年以上账龄')
    expect(composable.rows.value[0].riskFlags).toContain('支持性证据待补')
  })

  it('OCR确认回填只填空字段，默认不覆盖人工内容', () => {
    const composable = useF4LongOutstanding(options([['F4-5-rows', [{
      rowId: 'r1',
      attSlot: 7,
      creditor: '人工确认名称',
      closingBalance: 500,
      aging: '2～3年',
      auditedAmount: 500,
    }]]]))
    composable.mergeOcrFields('r1', {
      creditor: 'OCR名称',
      closingBalance: 600,
      unsettledReason: '合同约定尚未到付款节点',
      paymentPlan: '2026年12月支付',
      supportingEvidence: '采购合同HT-001、双方对账单',
    })
    const row = composable.rows.value[0]
    expect(row.creditor).toBe('人工确认名称')
    expect(row.closingBalance).toBe(500)
    expect(row.unsettledReason).toBe('合同约定尚未到付款节点')
    expect(row.paymentPlan).toBe('2026年12月支付')
    expect(row.supportingEvidence).toContain('HT-001')
    expect(row.attSlot).toBe(7)
  })

  it('无法支付或诉讼标记为高风险并汇总金额', () => {
    const composable = useF4LongOutstanding(options([['F4-5-rows', [{
      rowId: 'r1',
      creditor: '风险供应商',
      closingBalance: 300,
      aging: '3年以上',
      unableToPay: '是',
      litigation: '是',
      auditedAmount: 280,
    }]]]))
    expect(composable.rows.value[0].highlightLevel).toBe('danger')
    expect(composable.summary.value.unableToPayAmount).toBe(280)
    expect(composable.summary.value.litigationAmount).toBe(280)
    expect(composable.summary.value.adjustmentTotal).toBe(-20)
  })
})
