import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  computeF4DetailRow,
  F4_AGING_BUCKET_OPTIONS,
  F4_DETAIL_ALL_COLUMNS,
  F4_PAYMENT_NATURE_OPTIONS,
  F4_RELATED_PARTY_OPTIONS,
  migrateF4DetailRows,
  useF4Detail,
} from '../composables/useF4Detail'
import type { ChecklistResponse } from '../composables/useF4FormData'

function options(rows: unknown[] = []) {
  const remark = JSON.stringify(rows)
  return {
    wpId: ref('wp-1'),
    projectId: ref('p-1'),
    allResponses: ref(new Map<string, ChecklistResponse>([
      ['F4-2-rows', {
        item_id: 'F4-2-rows',
        conclusion: null,
        remark,
      }],
    ])),
    isReadonly: ref(false),
  }
}

describe('F4-2 源表结构与公式', () => {
  it('27列严格对应Excel A:AA顺序', () => {
    expect(F4_DETAIL_ALL_COLUMNS).toHaveLength(27)
    expect(F4_DETAIL_ALL_COLUMNS.map((column) => column.prop)).toEqual([
      'creditor', 'companyCode', 'relatedPartyType', 'paymentNature',
      'openingUnadjusted', 'openingAje', 'openingRje', 'openingAdjusted',
      'currentDebit', 'currentCredit', 'closingBalance',
      'entityReclassification', 'closingUnadjusted',
      'unadjustedAgingLt1', 'unadjustedAging1to2', 'unadjustedAging2to3', 'unadjustedAgingGt3',
      'closingAje', 'closingRje', 'closingAdjusted',
      'auditedAgingLt1', 'auditedAging1to2', 'auditedAging2to3', 'auditedAgingGt3',
      'isConfirmed', 'subsequentPayment', 'remark',
    ])
  })

  it('枚举与Excel数据验证一致', () => {
    expect(F4_RELATED_PARTY_OPTIONS).toEqual([
      '合并范围内关联方', '合并范围外关联方', '非关联方',
    ])
    expect(F4_PAYMENT_NATURE_OPTIONS).toEqual(['货款', '工程款', '设备款', '服务费', '其他'])
    expect(F4_AGING_BUCKET_OPTIONS.map((item) => item.label)).toEqual([
      '1年以下', '1～2年', '2～3年', '3年以上',
    ])
  })

  it('按源表公式依次计算H/K/M/T及双层账龄校验', () => {
    const stored = migrateF4DetailRows(JSON.stringify([{
      creditor: '甲公司',
      openingUnadjusted: 1000,
      openingAje: 30,
      openingRje: -10,
      currentDebit: 200,
      currentCredit: 500,
      entityReclassification: 50,
      unadjustedAgingLt1: 900,
      unadjustedAging1to2: 450,
      closingAje: -20,
      closingRje: 10,
      auditedAgingLt1: 890,
      auditedAging1to2: 450,
    }]))[0]
    const row = computeF4DetailRow(stored)
    expect(row.openingAdjusted).toBe(1020) // H=E+F+G
    expect(row.closingBalance).toBe(1300) // K=E+J-I（不是H+J-I）
    expect(row.closingUnadjusted).toBe(1350) // M=K+L
    expect(row.closingAdjusted).toBe(1340) // T=M+R+S
    expect(row.unadjustedAgingTotal).toBe(1350)
    expect(row.auditedAgingTotal).toBe(1340)
    expect(row.unadjustedAgingMismatch).toBe(false)
    expect(row.auditedAgingMismatch).toBe(false)
  })
})

describe('F4-2 旧数据迁移与账龄快捷分配', () => {
  it('旧27列实现字段无损迁移到源表字段', () => {
    const row = migrateF4DetailRows(JSON.stringify([{
      id: 'old-1',
      creditor: '乙公司',
      openingAdjusted: 800,
      aging1Year: 700,
      aging1to2Year: 100,
      ajeAdjustment: -50,
      rjeReclassification: 20,
      adjustedAging1: 670,
      adjustedAging2: 100,
      confirmationResult: '回函相符',
      subsequentPaymentDate: '2026-02-01',
      indexRef: 'F4-8-1',
    }]))[0]
    expect(row.rowId).toBe('old-1')
    expect(row.openingUnadjusted).toBe(800)
    // 账龄权威已迁到 nested（agingCurrent/agingAudited），序列化不再写扁平字段
    expect(row.agingCurrent.within1).toBe(700)
    expect(row.agingCurrent.y1to2).toBe(100)
    expect(row.closingAje).toBe(-50)
    expect(row.closingRje).toBe(20)
    expect(row.agingAudited.within1).toBe(670)
    // 3 年段零回归对照：兼容派生的扁平字段与迁移前期望值逐项相同
    const computedRow = computeF4DetailRow(row)
    expect(computedRow.unadjustedAgingLt1).toBe(700)
    expect(computedRow.unadjustedAging1to2).toBe(100)
    expect(computedRow.auditedAgingLt1).toBe(670)
    expect(computedRow.auditedAging1to2).toBe(100)
    expect(row.remark).toContain('函证结果：回函相符')
    expect(row.remark).toContain('期后付款日期：2026-02-01')
    expect(row.remark).toContain('原索引：F4-8-1')
  })

  it('按枚举档位将未审余额和审定数分别快捷分配', () => {
    const composable = useF4Detail(options([{
      rowId: 'r1',
      creditor: '丙公司',
      openingUnadjusted: 1000,
      currentCredit: 200,
      closingAje: -50,
    }]))
    composable.allocateAging('r1', 'unadjusted', '2to3')
    expect(composable.rows.value[0].unadjustedAging2to3).toBe(1200)
    expect(composable.rows.value[0].unadjustedAgingMismatch).toBe(false)

    composable.allocateAging('r1', 'audited', 'gt3')
    expect(composable.rows.value[0].auditedAgingGt3).toBe(1150)
    expect(composable.rows.value[0].auditedAgingMismatch).toBe(false)
  })

  it('期后付款超过审定余额时标记异常', () => {
    const stored = migrateF4DetailRows(JSON.stringify([{
      creditor: '丁公司',
      openingUnadjusted: 100,
      subsequentPayment: 120,
    }]))[0]
    expect(computeF4DetailRow(stored).subsequentPaymentExceedsBalance).toBe(true)
  })
})
