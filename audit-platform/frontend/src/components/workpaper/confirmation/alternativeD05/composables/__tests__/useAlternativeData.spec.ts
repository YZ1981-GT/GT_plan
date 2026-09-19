/**
 * useAlternativeData.spec.ts — D0-5 数据层单元测试
 *
 * 覆盖：CRUD + 4区块合计 + 检查比例 + completionStatus/hasAbnormal + 带入去重 + buildPayload
 */
import { describe, it, expect } from 'vitest'
import { useAlternativeData } from '../useAlternativeData'
import type { AlternativeCompany, AlternativeD05Payload } from '../../alternativeD05Types'

/** 创建 composable 实例 */
function createInstance(initialData?: any) {
  const htmlData = initialData || { _format: 'alternative-d05-v1', companies: [] }
  return useAlternativeData({
    htmlData: () => htmlData,
    readonly: false,
  })
}

describe('useAlternativeData', () => {
  describe('初始化', () => {
    it('空 htmlData 初始化为空数组', () => {
      const data = createInstance(null)
      expect(data.companies.value).toEqual([])
    })

    it('格式不匹配时初始化为空', () => {
      const data = createInstance({ _format: 'wrong-format' })
      expect(data.companies.value).toEqual([])
    })

    it('正确格式初始化 companies', () => {
      const data = createInstance({
        _format: 'alternative-d05-v1',
        companies: [{ entity_name: 'ABC公司', confirm_index: 'D0-1-001' }],
      })
      expect(data.companies.value.length).toBe(1)
      expect(data.companies.value[0].entity_name).toBe('ABC公司')
      expect(data.companies.value[0]._company_id).toBeTruthy()
    })
  })

  describe('Companies CRUD', () => {
    it('addCompany 新增公司', () => {
      const data = createInstance()
      const company = data.addCompany({ entity_name: '测试公司' })
      expect(data.companies.value.length).toBe(1)
      expect(company.entity_name).toBe('测试公司')
      expect(company.seq).toBe(1)
      expect(data.isDirty.value).toBe(true)
    })

    it('deleteCompany 删除公司', () => {
      const data = createInstance()
      const c1 = data.addCompany({ entity_name: '公司A' })
      const c2 = data.addCompany({ entity_name: '公司B' })
      data.deleteCompany(c1._company_id!)
      expect(data.companies.value.length).toBe(1)
      expect(data.companies.value[0].entity_name).toBe('公司B')
    })

    it('updateCompany 更新字段', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: '旧名' })
      data.updateCompany(c._company_id!, 'entity_name', '新名')
      expect(data.companies.value[0].entity_name).toBe('新名')
    })

    it('importCompanies 按 confirm_index 去重', () => {
      const data = createInstance()
      data.addCompany({ entity_name: '已有', confirm_index: 'IDX-001' })
      data.importCompanies([
        { entity_name: '重复', confirm_index: 'IDX-001' },
        { entity_name: '新公司', confirm_index: 'IDX-002' },
      ])
      expect(data.companies.value.length).toBe(2) // 去重后只增1个
      expect(data.companies.value[1].entity_name).toBe('新公司')
      expect(data.companies.value[1]._source).toBe('auto')
    })
  })

  describe('区块行操作', () => {
    it('addBlockRow 新增行', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      const row = data.addBlockRow(c._company_id!, 'block1')
      expect(row).toBeTruthy()
      expect(row!.seq).toBe(1)
      expect(data.companies.value[0].block1_rows!.length).toBe(1)
    })

    it('deleteBlockRow 删除行', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      const row = data.addBlockRow(c._company_id!, 'block2')!
      data.deleteBlockRow(c._company_id!, 'block2', row._row_id!)
      expect(data.companies.value[0].block2_rows!.length).toBe(0)
    })

    it('updateBlockField 更新行字段', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      const row = data.addBlockRow(c._company_id!, 'block3')!
      data.updateBlockField(c._company_id!, 'block3', row._row_id!, 'receipt_amount', 1000)
      expect(data.companies.value[0].block3_rows![0].receipt_amount).toBe(1000)
    })
  })

  describe('区块合计', () => {
    it('block1 debit_amount 合计', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      const r1 = data.addBlockRow(c._company_id!, 'block1')!
      const r2 = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', r1._row_id!, 'debit_amount', 100.55)
      data.updateBlockField(c._company_id!, 'block1', r2._row_id!, 'debit_amount', 200.45)
      const totals = data.getBlockTotal(data.companies.value[0], 'block1')
      expect(totals.debit_amount).toBe(301)
    })

    it('block3 receipt_amount 合计（精确小数）', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      const r1 = data.addBlockRow(c._company_id!, 'block3')!
      const r2 = data.addBlockRow(c._company_id!, 'block3')!
      data.updateBlockField(c._company_id!, 'block3', r1._row_id!, 'receipt_amount', 0.1)
      data.updateBlockField(c._company_id!, 'block3', r2._row_id!, 'receipt_amount', 0.2)
      const totals = data.getBlockTotal(data.companies.value[0], 'block3')
      expect(totals.receipt_amount).toBe(0.3)
    })
  })

  describe('检查比例', () => {
    it('sales_amount 为 0 时返回 null (N/A)', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { sales_amount: 0 })
      expect(data.getCheckRatio(data.companies.value[0], 'receipt')).toBeNull()
      expect(data.getCheckRatio(data.companies.value[0], 'shipment')).toBeNull()
    })

    it('sales_amount 未填时返回 null', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      expect(data.getCheckRatio(data.companies.value[0], 'receipt')).toBeNull()
    })

    it('receipt 比例 = block3 合计 / sales_amount * 100', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { sales_amount: 1000 })
      const row = data.addBlockRow(c._company_id!, 'block3')!
      data.updateBlockField(c._company_id!, 'block3', row._row_id!, 'receipt_amount', 300)
      expect(data.getCheckRatio(data.companies.value[0], 'receipt')).toBe(30)
    })

    it('shipment 比例 = block4 合计 / sales_amount * 100', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { sales_amount: 2000 })
      const row = data.addBlockRow(c._company_id!, 'block4')!
      data.updateBlockField(c._company_id!, 'block4', row._row_id!, 'product_amount', 500)
      expect(data.getCheckRatio(data.companies.value[0], 'shipment')).toBe(25)
    })
  })

  describe('completionStatus / hasAbnormal', () => {
    it('4 区块均无行 → completed=0', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      const status = data.getCompletionStatus(data.companies.value[0])
      expect(status.completed).toBe(0)
      expect(status.rate).toBe(0)
    })

    it('4 区块均有行 → completed=4', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.addBlockRow(c._company_id!, 'block1')
      data.addBlockRow(c._company_id!, 'block2')
      data.addBlockRow(c._company_id!, 'block3')
      data.addBlockRow(c._company_id!, 'block4')
      const status = data.getCompletionStatus(data.companies.value[0])
      expect(status.completed).toBe(4)
      expect(status.rate).toBe(100)
    })

    it('hasAbnormal 检测异常行', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      expect(data.hasAbnormal(data.companies.value[0])).toBe(false)
      const row = data.addBlockRow(c._company_id!, 'block1')!
      data.updateBlockField(c._company_id!, 'block1', row._row_id!, 'is_abnormal', '是')
      expect(data.hasAbnormal(data.companies.value[0])).toBe(true)
    })
  })

  describe('metrics', () => {
    it('空数据看板指标', () => {
      const data = createInstance()
      expect(data.metrics.value.total_companies).toBe(0)
      expect(data.metrics.value.completion_rate).toBe(0)
    })

    it('有公司时看板统计正确', () => {
      const data = createInstance()
      const c1 = data.addCompany({ entity_name: 'A' })
      data.addBlockRow(c1._company_id!, 'block1')
      data.addBlockRow(c1._company_id!, 'block2')
      data.addBlockRow(c1._company_id!, 'block3')
      data.addBlockRow(c1._company_id!, 'block4')

      const c2 = data.addCompany({ entity_name: 'B' })
      const row = data.addBlockRow(c2._company_id!, 'block1')!
      data.updateBlockField(c2._company_id!, 'block1', row._row_id!, 'is_abnormal', '是')

      expect(data.metrics.value.total_companies).toBe(2)
      expect(data.metrics.value.completed_companies).toBe(1)
      expect(data.metrics.value.abnormal_companies).toBe(1)
    })
  })

  describe('buildPayload', () => {
    it('生成 _format: alternative-d05-v1', () => {
      const data = createInstance()
      data.addCompany({ entity_name: '公司A' })
      const payload = data.buildPayload()
      expect(payload._format).toBe('alternative-d05-v1')
      expect(payload.companies.length).toBe(1)
      expect(payload.companies[0].entity_name).toBe('公司A')
    })

    it('payload 包含余额比例', () => {
      const data = createInstance()
      const c = data.addCompany({ entity_name: 'X' })
      data.updateCompany(c._company_id!, 'balance', { sales_amount: 1000 })
      const row = data.addBlockRow(c._company_id!, 'block3')!
      data.updateBlockField(c._company_id!, 'block3', row._row_id!, 'receipt_amount', 500)
      const payload = data.buildPayload()
      expect(payload.companies[0].balance?.receipt_check_ratio).toBe(50)
    })
  })
})
