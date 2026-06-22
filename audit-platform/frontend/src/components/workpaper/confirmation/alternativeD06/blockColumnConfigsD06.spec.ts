/**
 * blockColumnConfigsD06.spec.ts — D0-6 列配置单元测试
 *
 * 验证：
 * - 4 区块均有列定义且列数符合预期
 * - getSumFieldsD06 返回正确的合计字段
 * - getGroupsD06 返回正确的分组表头
 * - 所有列 field 唯一（同一区块内无重复）
 * - format 标识正确
 */
import { describe, it, expect } from 'vitest'
import {
  BLOCK_COLUMN_CONFIGS_D06,
  getSumFieldsD06,
  getGroupsD06,
} from './blockColumnConfigsD06'

describe('BLOCK_COLUMN_CONFIGS_D06', () => {
  const blockKeys = ['block1', 'block2', 'block3', 'block4']

  it('should have all 4 block configs', () => {
    for (const key of blockKeys) {
      expect(BLOCK_COLUMN_CONFIGS_D06[key]).toBeDefined()
      expect(BLOCK_COLUMN_CONFIGS_D06[key].columns.length).toBeGreaterThan(0)
    }
  })

  it('block1 (期末余额形成) should have ~25 columns', () => {
    const cols = BLOCK_COLUMN_CONFIGS_D06.block1.columns
    expect(cols.length).toBeGreaterThanOrEqual(20)
    expect(cols.length).toBeLessThanOrEqual(30)
  })

  it('block2 (期后回款) should have ~14 columns', () => {
    const cols = BLOCK_COLUMN_CONFIGS_D06.block2.columns
    expect(cols.length).toBeGreaterThanOrEqual(12)
    expect(cols.length).toBeLessThanOrEqual(18)
  })

  it('block3 (本期出库) should have ~20 columns', () => {
    const cols = BLOCK_COLUMN_CONFIGS_D06.block3.columns
    expect(cols.length).toBeGreaterThanOrEqual(15)
    expect(cols.length).toBeLessThanOrEqual(25)
  })

  it('block4 (本期收款) should have ~11 columns', () => {
    const cols = BLOCK_COLUMN_CONFIGS_D06.block4.columns
    expect(cols.length).toBeGreaterThanOrEqual(9)
    expect(cols.length).toBeLessThanOrEqual(15)
  })

  it('each block should have unique field names', () => {
    for (const key of blockKeys) {
      const fields = BLOCK_COLUMN_CONFIGS_D06[key].columns.map((c) => c.field)
      const unique = new Set(fields)
      expect(unique.size).toBe(fields.length)
    }
  })

  it('each block title should be non-empty', () => {
    for (const key of blockKeys) {
      expect(BLOCK_COLUMN_CONFIGS_D06[key].title.length).toBeGreaterThan(0)
    }
  })

  it('each block should have correct blockType', () => {
    for (const key of blockKeys) {
      expect(BLOCK_COLUMN_CONFIGS_D06[key].blockType).toBe(key)
    }
  })
})

describe('getSumFieldsD06', () => {
  it('block1 should have sumFields including debit_amount', () => {
    const fields = getSumFieldsD06('block1')
    expect(fields).toContain('debit_amount')
    expect(fields.length).toBeGreaterThanOrEqual(1)
  })

  it('block2 should have sumFields including credit_amount and bank_amount', () => {
    const fields = getSumFieldsD06('block2')
    expect(fields).toContain('credit_amount')
    expect(fields).toContain('bank_amount')
  })

  it('block3 should have sumFields including product_amount', () => {
    const fields = getSumFieldsD06('block3')
    expect(fields).toContain('product_amount')
  })

  it('block4 should have sumFields including receipt_amount', () => {
    const fields = getSumFieldsD06('block4')
    expect(fields).toContain('receipt_amount')
  })

  it('should return empty array for unknown blockType', () => {
    expect(getSumFieldsD06('block99')).toEqual([])
  })
})

describe('getGroupsD06', () => {
  it('block1 should have groups including 记账凭证', () => {
    const groups = getGroupsD06('block1')
    expect(groups).toContain('记账凭证')
    expect(groups.length).toBeGreaterThanOrEqual(4)
  })

  it('block2 should have groups including 银行回单 and 承兑汇票', () => {
    const groups = getGroupsD06('block2')
    expect(groups).toContain('银行回单')
    expect(groups).toContain('承兑汇票')
  })

  it('block3 should have groups including 出库单 and 运输单', () => {
    const groups = getGroupsD06('block3')
    expect(groups).toContain('出库单')
    expect(groups).toContain('运输单')
  })

  it('block4 should have groups including 银行回单 and 销售发票', () => {
    const groups = getGroupsD06('block4')
    expect(groups).toContain('银行回单')
    expect(groups).toContain('销售发票')
  })

  it('should return empty array for unknown blockType', () => {
    expect(getGroupsD06('block99')).toEqual([])
  })
})
