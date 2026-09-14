/**
 * useAlternativeF06Data.spec.ts — F0-6 应付及采购替代程序数据层 characterization 测试（G4 安全网）
 *
 * 背景（2026-07-17 G4）：alternative* 八套近重复中 F06 无测试。锁定 F06 **当前行为**，
 * 作为收敛为工厂前的回归安全网。
 *
 * F06 相对 F05 的差异（本测试重点，注意 block 映射相反）：
 * - _format: alternative-f06-v1
 * - 默认 balance.item_name = '应付账款'
 * - getCheckRatio('inbound') 用 block3 voucher_amount；('payment') 用 block4 payment_amount
 * - payload 比例字段 inbound_check_ratio / payment_check_ratio
 */
import { describe, it, expect } from 'vitest'
import { useAlternativeF06Data } from '../useAlternativeF06Data'

function createInstance(initialData?: any) {
  const htmlData = initialData ?? { _format: 'alternative-f06-v1', companies: [] }
  return useAlternativeF06Data({ htmlData: () => htmlData, readonly: false })
}

describe('useAlternativeF06Data', () => {
  describe('初始化', () => {
    it('空 / 格式不匹配 → 空数组', () => {
      expect(createInstance(null).companies.value).toEqual([])
      expect(createInstance({ _format: 'alternative-f05-v1' }).companies.value).toEqual([])
    })

    it('alternative-f06-v1 正确初始化', () => {
      const data = createInstance({
        _format: 'alternative-f06-v1',
        companies: [{ entity_name: '供应商A' }],
      })
      expect(data.companies.value.length).toBe(1)
      expect(data.companies.value[0]._company_id).toBeTruthy()
    })
  })

  describe('CRUD + 默认 balance', () => {
    it('addCompany 默认 balance.item_name=应付账款', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      expect(c.balance?.item_name).toBe('应付账款')
    })

    it('importCompanies 去重 + 默认应付账款', () => {
      const data = createInstance()
      data.addCompany({ entity_name: '已有', confirm_index: 'IDX-1' })
      data.importCompanies([
        { entity_name: '重复', confirm_index: 'IDX-1' },
        { entity_name: '新', confirm_index: 'IDX-2' },
      ])
      expect(data.companies.value.length).toBe(2)
      expect(data.companies.value[1].balance?.item_name).toBe('应付账款')
    })
  })

  describe('检查比例（F06 语义：block 映射与 F05 相反）', () => {
    it('inbound 比例 = block3 voucher_amount / purchase_amount * 100', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '应付账款', purchase_amount: 1000 })
      const row = data.addBlockRow(c._company_id!, 'block3')!
      data.updateBlockField(c._company_id!, 'block3', row._row_id!, 'voucher_amount', 300)
      expect(data.getCheckRatio(data.companies.value[0], 'inbound')).toBe(30)
    })

    it('payment 比例 = block4 payment_amount / purchase_amount * 100', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '应付账款', purchase_amount: 2000 })
      const row = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', row._row_id!, 'payment_amount', 500)
      expect(data.getCheckRatio(data.companies.value[0], 'payment')).toBe(25)
    })

    it('无采购额 → null', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      expect(data.getCheckRatio(data.companies.value[0], 'inbound')).toBeNull()
      expect(data.getCheckRatio(data.companies.value[0], 'payment')).toBeNull()
    })
  })

  describe('metrics / buildPayload', () => {
    it('metrics 统计正确', () => {
      const data = createInstance()
      const c1 = data.addCompany({ entity_name: 'A' })
      ;(['block1', 'block2', 'block3', 'block4'] as const).forEach((b) => data.addBlockRow(c1._company_id!, b))
      expect(data.metrics.value.total_companies).toBe(1)
      expect(data.metrics.value.completed_companies).toBe(1)
    })

    it('buildPayload _format=alternative-f06-v1 + 固化比例', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { item_name: '应付账款', purchase_amount: 1000 })
      const row = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', row._row_id!, 'payment_amount', 600)
      const payload = data.buildPayload()
      expect(payload._format).toBe('alternative-f06-v1')
      expect(payload.companies[0].balance?.payment_check_ratio).toBe(60)
      expect(payload.companies[0].balance).toHaveProperty('inbound_check_ratio')
    })
  })
})
