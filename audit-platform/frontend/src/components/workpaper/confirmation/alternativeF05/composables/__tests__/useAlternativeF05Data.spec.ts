/**
 * useAlternativeF05Data.spec.ts — F0-5 预付及采购替代程序数据层 characterization 测试（G4 安全网）
 *
 * 背景（2026-07-17 G4）：alternative* 八套近重复 composable 中 F05 无测试。
 * 本文件锁定 F05 **当前行为**（characterization），作为后续收敛为工厂前的回归安全网——
 * 收敛后同一套断言应对工厂产出的 F05 composable 全绿，证明行为不变。
 *
 * F05 相对 D05 的差异（本测试重点）：
 * - _format: alternative-f05-v1
 * - 默认 balance.item_name = '预付账款'
 * - getCheckRatio('payment') 用 block3 payment_amount；('inbound') 用 block4 voucher_amount
 * - 基数 = balance.purchase_amount ?? sales_amount
 * - payload 比例字段 payment_check_ratio / inbound_check_ratio
 */
import { describe, it, expect } from 'vitest'
import { useAlternativeF05Data } from '../useAlternativeF05Data'

function createInstance(initialData?: any) {
  const htmlData = initialData ?? { _format: 'alternative-f05-v1', companies: [] }
  return useAlternativeF05Data({ htmlData: () => htmlData, readonly: false })
}

describe('useAlternativeF05Data', () => {
  describe('初始化', () => {
    it('空 / 格式不匹配 → 空数组', () => {
      expect(createInstance(null).companies.value).toEqual([])
      expect(createInstance({ _format: 'wrong' }).companies.value).toEqual([])
    })

    it('alternative-f05-v1 正确初始化并补 _company_id', () => {
      const data = createInstance({
        _format: 'alternative-f05-v1',
        companies: [{ entity_name: '供应商A', confirm_index: 'F0-1-001' }],
      })
      expect(data.companies.value.length).toBe(1)
      expect(data.companies.value[0]._company_id).toBeTruthy()
    })
  })

  describe('CRUD + 默认 balance', () => {
    it('addCompany 默认 balance.item_name=预付账款', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      expect(c.balance?.item_name).toBe('预付账款')
      expect(data.isDirty.value).toBe(true)
    })

    it('importCompanies 按 confirm_index 去重 + 默认预付账款', () => {
      const data = createInstance()
      data.addCompany({ entity_name: '已有', confirm_index: 'IDX-1' })
      data.importCompanies([
        { entity_name: '重复', confirm_index: 'IDX-1' },
        { entity_name: '新', confirm_index: 'IDX-2' },
      ])
      expect(data.companies.value.length).toBe(2)
      expect(data.companies.value[1].balance?.item_name).toBe('预付账款')
      expect(data.companies.value[1]._source).toBe('auto')
    })
  })

  describe('检查比例（F05 语义）', () => {
    it('无采购额（purchase/sales 均缺）→ null', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      expect(data.getCheckRatio(data.companies.value[0], 'payment')).toBeNull()
      expect(data.getCheckRatio(data.companies.value[0], 'inbound')).toBeNull()
    })

    it('payment 比例 = block3 payment_amount / purchase_amount * 100', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '预付账款', purchase_amount: 1000 })
      const row = data.addBlockRow(c._company_id!, 'block3')!
      data.updateBlockField(c._company_id!, 'block3', row._row_id!, 'payment_amount', 250)
      expect(data.getCheckRatio(data.companies.value[0], 'payment')).toBe(25)
    })

    it('基数回退到 sales_amount（无 purchase_amount）', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { sales_amount: 2000 })
      const row = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', row._row_id!, 'voucher_amount', 500)
      expect(data.getCheckRatio(data.companies.value[0], 'inbound')).toBe(25)
    })
  })

  describe('completionStatus / hasAbnormal / metrics', () => {
    it('4 区块有行 → completed=4', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      ;(['block1', 'block2', 'block3', 'block4'] as const).forEach((b) => data.addBlockRow(c._company_id!, b))
      expect(data.getCompletionStatus(data.companies.value[0]).completed).toBe(4)
    })

    it('metrics 统计 total/completed/abnormal', () => {
      const data = createInstance()
      const c1 = data.addCompany({ entity_name: 'A' })
      ;(['block1', 'block2', 'block3', 'block4'] as const).forEach((b) => data.addBlockRow(c1._company_id!, b))
      const c2 = data.addCompany({ entity_name: 'B' })
      const row = data.addBlockRow(c2._company_id!, 'block1')!
      data.updateBlockField(c2._company_id!, 'block1', row._row_id!, 'is_abnormal', '是')
      expect(data.metrics.value.total_companies).toBe(2)
      expect(data.metrics.value.completed_companies).toBe(1)
      expect(data.metrics.value.abnormal_companies).toBe(1)
    })
  })

  describe('buildPayload', () => {
    it('_format=alternative-f05-v1 + 固化 payment/inbound 比例', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '预付账款', purchase_amount: 1000 })
      const row = data.addBlockRow(c._company_id!, 'block3')!
      data.updateBlockField(c._company_id!, 'block3', row._row_id!, 'payment_amount', 400)
      const payload = data.buildPayload()
      expect(payload._format).toBe('alternative-f05-v1')
      expect(payload.companies[0].balance?.payment_check_ratio).toBe(40)
      expect(payload.companies[0].balance).toHaveProperty('inbound_check_ratio')
    })
  })
})
