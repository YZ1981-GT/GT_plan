/**
 * useAlternativeD06Data.spec.ts — D0-6 composable 单元测试
 *
 * 验证：
 * - format 为 alternative-d06-v1 时正确初始化
 * - 非 D06 format 时 companies 为空
 * - buildPayload 返回正确的 _format
 * - getSumFields 使用 D06 列配置（区块④用 receipt_amount）
 */
import { describe, it, expect } from 'vitest'
import { useAlternativeD06Data } from './useAlternativeD06Data'

describe('useAlternativeD06Data', () => {
  it('should initialize empty companies when format is not alternative-d06-v1', () => {
    const data = useAlternativeD06Data({
      htmlData: () => ({ _format: 'alternative-d05-v1', companies: [{ entity_name: 'X' }] }),
      readonly: false,
    })
    expect(data.companies.value).toEqual([])
  })

  it('should initialize companies when format is alternative-d06-v1', () => {
    const data = useAlternativeD06Data({
      htmlData: () => ({
        _format: 'alternative-d06-v1',
        companies: [
          { entity_name: 'Company A', block1_rows: [], block2_rows: [], block3_rows: [], block4_rows: [] },
        ],
      }),
      readonly: false,
    })
    expect(data.companies.value.length).toBe(1)
    expect(data.companies.value[0].entity_name).toBe('Company A')
  })

  it('buildPayload should have _format = alternative-d06-v1', () => {
    const data = useAlternativeD06Data({
      htmlData: () => ({ _format: 'alternative-d06-v1', companies: [] }),
      readonly: false,
    })
    data.addCompany({ entity_name: 'Test Co' })
    const payload = data.buildPayload()
    expect(payload._format).toBe('alternative-d06-v1')
    expect(payload.companies.length).toBe(1)
  })

  it('getBlockTotal for block4 should sum receipt_amount', () => {
    const data = useAlternativeD06Data({
      htmlData: () => ({
        _format: 'alternative-d06-v1',
        companies: [{
          entity_name: 'X',
          _company_id: 'c1',
          block1_rows: [],
          block2_rows: [],
          block3_rows: [],
          block4_rows: [
            { _row_id: 'r1', receipt_amount: 100 },
            { _row_id: 'r2', receipt_amount: 200.5 },
          ],
        }],
      }),
      readonly: false,
    })
    const totals = data.getBlockTotal(data.companies.value[0], 'block4')
    expect(totals['receipt_amount']).toBe(300.5)
  })

  it('getCheckRatio receipt should use block4 receipt_amount', () => {
    const data = useAlternativeD06Data({
      htmlData: () => ({
        _format: 'alternative-d06-v1',
        companies: [{
          entity_name: 'X',
          _company_id: 'c1',
          balance: { sales_amount: 1000 },
          block1_rows: [],
          block2_rows: [],
          block3_rows: [],
          block4_rows: [
            { _row_id: 'r1', receipt_amount: 300 },
          ],
        }],
      }),
      readonly: false,
    })
    const ratio = data.getCheckRatio(data.companies.value[0], 'receipt')
    expect(ratio).toBe(30) // 300/1000 * 100 = 30%
  })

  it('getCheckRatio shipment should use block3 product_amount', () => {
    const data = useAlternativeD06Data({
      htmlData: () => ({
        _format: 'alternative-d06-v1',
        companies: [{
          entity_name: 'X',
          _company_id: 'c1',
          balance: { sales_amount: 2000 },
          block1_rows: [],
          block2_rows: [],
          block3_rows: [
            { _row_id: 'r1', product_amount: 500 },
            { _row_id: 'r2', product_amount: 300 },
          ],
          block4_rows: [],
        }],
      }),
      readonly: false,
    })
    const ratio = data.getCheckRatio(data.companies.value[0], 'shipment')
    expect(ratio).toBe(40) // 800/2000 * 100 = 40%
  })

  it('getCheckRatio should return null when sales_amount is 0', () => {
    const data = useAlternativeD06Data({
      htmlData: () => ({
        _format: 'alternative-d06-v1',
        companies: [{
          entity_name: 'X',
          _company_id: 'c1',
          balance: { sales_amount: 0 },
          block1_rows: [],
          block2_rows: [],
          block3_rows: [],
          block4_rows: [],
        }],
      }),
      readonly: false,
    })
    expect(data.getCheckRatio(data.companies.value[0], 'receipt')).toBeNull()
  })
})
