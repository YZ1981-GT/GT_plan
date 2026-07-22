/**
 * useH2TransferCheck — 双表逻辑 + 期后凭证/折旧AJE/H2-13回写
 */
import { describe, it, expect, vi } from 'vitest'
import { ref as vueRef } from 'vue'
import {
  useH2TransferCheck,
  calcMissedDepreciation,
  matchPostPeriodEntry,
  formatPostPeriodHits,
  mergeH213ReadyIntoCipRows,
  buildDelayDepAjePair,
  H25_AJE_MARKER,
  postPeriodDateRange,
} from '../useH2TransferCheck'

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

import http from '@/utils/http'

function setup(allResponses?: Map<string, any>, year = 2024) {
  const map = vueRef(allResponses ?? new Map())
  const saved: Record<string, any> = {}
  const api = useH2TransferCheck({
    wpId: vueRef('wp-1'),
    projectId: vueRef('p-1'),
    allResponses: map,
    isReadonly: vueRef(false),
    year: vueRef(year),
    onSave: (id, val) => {
      saved[id] = val
      map.value.set(id, { remark: typeof val === 'string' ? val : JSON.stringify(val) })
    },
  })
  return { api, saved, map }
}

describe('纯函数', () => {
  it('期后日期窗口：截止日次日起3个月', () => {
    const r = postPeriodDateRange('2024-12-31', 3)
    expect(r.dateFrom).toBe('2025-01-01')
    expect(r.dateTo).toBe('2025-04-01')
    expect(r.year).toBe(2025)
  })

  it('少计折旧：达可用次月起至 asOf', () => {
    // 成本100万，残值5%，10年 → 月折旧 = 100万*0.95/10/12 = 7916.666...
    const dep = calcMissedDepreciation({
      cost: 1000000,
      salvageRatePct: 5,
      usefulLifeYears: 10,
      readyDate: '2024-03-01',
      asOfDate: '2024-06-15',
    })
    expect(dep.months).toBe(3) // 4、5、6月
    expect(dep.amount).toBeCloseTo(7916.6667 * 3, 0)
  })

  it('期后凭证匹配：工程名或转固关键词', () => {
    expect(matchPostPeriodEntry({ summary: '厂房A转固' }, '厂房A')).toBe(true)
    expect(matchPostPeriodEntry({ summary: '转入固定资产' }, '无关工程')).toBe(true)
    expect(matchPostPeriodEntry({ summary: '材料采购' }, '厂房A')).toBe(false)
  })

  it('formatPostPeriodHits 拼接文本与凭证号', () => {
    const { text, voucherNos } = formatPostPeriodHits([
      { voucherDate: '2025-01-10', voucherNo: '记-1', summary: '转固', amount: 100, accountCode: '1601' },
    ])
    expect(text).toContain('记-1')
    expect(voucherNos).toBe('记-1')
  })

  it('mergeH213ReadyIntoCipRows 新增达可用挂账', () => {
    const { rows, added, updated } = mergeH213ReadyIntoCipRows([], [
      { name: '产线X', readyForUse: '是', bookAmount: 500000 },
    ])
    expect(added).toBe(1)
    expect(updated).toBe(0)
    expect(rows[0].readyForUse).toBe(true)
    expect(rows[0].isAbnormal).toBe(true)
    expect(rows[0].cipOriginal).toBe(500000)
  })

  it('buildDelayDepAjePair 借贷平衡且带 marker', () => {
    const pair = buildDelayDepAjePair({
      projectName: '厂房',
      amount: 10000,
      seqStart: 1,
      months: 3,
    })
    expect(pair).toHaveLength(2)
    expect(pair[0].debit).toBe(10000)
    expect(pair[1].credit).toBe(10000)
    expect(pair[0].remark).toBe(H25_AJE_MARKER)
    expect(pair[0].accountCode).toBe('6602')
    expect(pair[1].accountCode).toBe('1602')
  })
})

describe('useH2TransferCheck 双表逻辑', () => {
  it('表一：已达可用且无原因 → 异常', () => {
    const { api } = setup()
    api.addCipRow('厂房A')
    const id = api.cipRows.value[0].rowId
    api.updateCipCell(id, 'cipOriginal', 1000000)
    api.updateCipCell(id, 'readyForUse', true)
    expect(api.cipRows.value[0].isAbnormal).toBe(true)
    expect(api.cipAbnormalCount.value).toBe(1)
  })

  it('表一：已达可用但填写未转固原因 → 不异常', () => {
    const { api } = setup()
    api.addCipRow('厂房B')
    const id = api.cipRows.value[0].rowId
    api.updateCipCell(id, 'readyForUse', true)
    api.updateCipCell(id, 'notTransferReason', '竣工决算未办完，已暂估转固计划')
    expect(api.cipRows.value[0].isAbnormal).toBe(false)
  })

  it('表二：实质可用日优先正式投产，延迟按日计算', () => {
    const { api } = setup()
    api.addRow('产线C')
    const id = api.rows.value[0].rowId
    api.updateCell(id, 'officialProductionDate', '2024-03-01')
    api.updateCell(id, 'transferDate', '2024-06-15')
    api.updateCell(id, 'condition1', true)
    api.updateCell(id, 'condition2', true)
    api.updateCell(id, 'condition3', true)
    api.updateCell(id, 'condition4', true)
    api.updateCell(id, 'condition5', true)
    expect(api.rows.value[0].conditionsMetDate).toBe('2024-03-01')
    expect(api.rows.value[0].delayDays).toBe(106)
    expect(api.rows.value[0].allConditionsMet).toBe(true)
    expect(api.rows.value[0].timelyTransfer).toBe(false)
  })

  it('从 H2-2 带入挂账与转固', () => {
    const h22 = [
      { name: '仓库', cipEnd: 500000, budget: 800000, transferAmount: 0 },
      { name: '办公楼', cipEnd: 0, transferAmount: 2000000, transferDate: '2024-05-01', transferToH1: '房屋建筑物' },
    ]
    const map = new Map([['H2-2-rows', { remark: JSON.stringify(h22) }]])
    const { api } = setup(map)
    const r = api.syncFromH2Detail()
    expect(r.cipAdded).toBe(1)
    expect(r.transferAdded).toBe(1)
    expect(api.cipRows.value[0].name).toBe('仓库')
    expect(api.rows.value[0].name).toBe('办公楼')
    expect(api.rows.value[0].transferAmount).toBe(2000000)
  })

  it('syncReadyFromH213 回写挂账表', () => {
    const h213 = [
      { name: '新产线', readyForUse: '是', bookAmount: 800000 },
      { name: '在建中', readyForUse: '否', bookAmount: 100000 },
    ]
    const map = new Map([['H2-13-rows', { remark: JSON.stringify(h213) }]])
    const { api, saved } = setup(map)
    const res = api.syncReadyFromH213()
    expect(res.ok).toBe(true)
    expect(res.added).toBe(1)
    expect(api.cipRows.value[0].name).toBe('新产线')
    expect(api.cipRows.value[0].readyForUse).toBe(true)
    expect(saved['H2-5-cip-rows']).toBeTruthy()
  })

  it('pushDelayDepAjeToH23 写入 H2-3', () => {
    const { api, saved } = setup()
    api.addCipRow('延迟工程')
    const id = api.cipRows.value[0].rowId
    api.updateCipCell(id, 'cipOriginal', 1200000)
    api.updateCipCell(id, 'readyForUse', true)
    api.updateCipCell(id, 'readyDate', '2024-01-15')
    api.updateCipCell(id, 'usefulLifeYears', 10)
    api.updateCipCell(id, 'salvageRatePct', 5)
    expect(api.cipRows.value[0].missedDepAmount).toBeGreaterThan(0)

    const res = api.pushDelayDepAjeToH23()
    expect(res.ok).toBe(true)
    expect(res.added).toBe(2)
    const h23 = saved['H2-3-rows']
    expect(Array.isArray(h23)).toBe(true)
    expect(h23.every((r: any) => r.remark === H25_AJE_MARKER)).toBe(true)
    expect(h23[0].debit + h23[1].debit).toBeCloseTo(h23[0].credit + h23[1].credit, 2)
  })

  it('pullPostPeriodTransfers 按工程名回填', async () => {
    ;(http.get as any).mockResolvedValue({
      data: {
        items: [
          {
            voucher_date: '2025-02-01',
            voucher_no: '记-88',
            summary: '仓库改扩建转固',
            debit_amount: 500000,
            account_code: '1601',
          },
        ],
      },
    })
    const { api } = setup()
    api.addCipRow('仓库改扩建')
    const res = await api.pullPostPeriodTransfers()
    expect(res.ok).toBe(true)
    expect(api.cipRows.value[0].postPeriodTransfer).toContain('记-88')
    expect(api.cipRows.value[0].postPeriodVoucherNos).toContain('记-88')
    // 有期后说明后异常应消除（若 ready）
    api.updateCipCell(api.cipRows.value[0].rowId, 'readyForUse', true)
    expect(api.cipRows.value[0].isAbnormal).toBe(false)
  })
})
