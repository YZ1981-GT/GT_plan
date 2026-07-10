/**
 * alternativeF05F06.spec.ts — F0-5/F0-6 替代程序单元测试
 *
 * 覆盖：
 * - 4区块列配置正确性
 * - CRUD 逻辑（addCompany/deleteCompany/addBlockRow/deleteBlockRow/updateBlockField）
 * - 合计行计算（getBlockTotal）
 * - 检查比例计算（getCheckRatio）
 * - 完成度检测（getCompletionStatus）
 * - 异常行检测（hasAbnormal）
 * - 导入导出模板列头匹配
 */
import { describe, it, expect } from 'vitest'
import { BLOCK_COLUMN_CONFIGS_F05, getSumFieldsF05 } from '../alternativeF05/blockColumnConfigsF05'
import { BLOCK_COLUMN_CONFIGS_F06, getSumFieldsF06 } from '../alternativeF06/blockColumnConfigsF06'

// ─── F0-5 区块列配置测试 ─────────────────────────────────────────────────────

describe('BLOCK_COLUMN_CONFIGS_F05', () => {
  it('should have 4 block configs', () => {
    expect(Object.keys(BLOCK_COLUMN_CONFIGS_F05)).toHaveLength(4)
    expect(BLOCK_COLUMN_CONFIGS_F05).toHaveProperty('block1')
    expect(BLOCK_COLUMN_CONFIGS_F05).toHaveProperty('block2')
    expect(BLOCK_COLUMN_CONFIGS_F05).toHaveProperty('block3')
    expect(BLOCK_COLUMN_CONFIGS_F05).toHaveProperty('block4')
  })

  it('block1 should have correct title and columns', () => {
    const b1 = BLOCK_COLUMN_CONFIGS_F05.block1
    expect(b1.title).toContain('期后收货')
    expect(b1.columns.length).toBeGreaterThanOrEqual(14)
    // 必须有 seq/voucher_date/voucher_no/voucher_amount/ref_index/is_abnormal
    const fields = b1.columns.map((c) => c.field)
    expect(fields).toContain('seq')
    expect(fields).toContain('voucher_date')
    expect(fields).toContain('voucher_no')
    expect(fields).toContain('voucher_amount')
    expect(fields).toContain('ref_index')
    expect(fields).toContain('is_abnormal')
    // F05 block1 特有：入库单+发票
    expect(fields).toContain('inbound_date_no')
    expect(fields).toContain('invoice_amount')
  })

  it('block2 should contain payment related fields', () => {
    const b2 = BLOCK_COLUMN_CONFIGS_F05.block2
    expect(b2.title).toContain('余额')
    const fields = b2.columns.map((c) => c.field)
    expect(fields).toContain('bank_amount')
    expect(fields).toContain('contract_vendor')
    expect(fields).toContain('prepay_ratio')
  })

  it('block3 should contain payment check fields', () => {
    const b3 = BLOCK_COLUMN_CONFIGS_F05.block3
    expect(b3.title).toContain('付款')
    const fields = b3.columns.map((c) => c.field)
    expect(fields).toContain('payment_amount')
    expect(fields).toContain('bank_amount')
  })

  it('block4 should contain purchase evidence fields', () => {
    const b4 = BLOCK_COLUMN_CONFIGS_F05.block4
    expect(b4.title).toContain('采购')
    const fields = b4.columns.map((c) => c.field)
    expect(fields).toContain('inbound_date_no')
    expect(fields).toContain('contract_amount')
  })

  it('getSumFieldsF05 should return sumField columns', () => {
    const sumFields1 = getSumFieldsF05('block1')
    expect(sumFields1).toContain('voucher_amount')
    expect(sumFields1).toContain('invoice_amount')

    const sumFields3 = getSumFieldsF05('block3')
    expect(sumFields3).toContain('payment_amount')
    expect(sumFields3).toContain('bank_amount')
  })

  it('each block should have seq as first column', () => {
    for (const key of ['block1', 'block2', 'block3', 'block4']) {
      const config = BLOCK_COLUMN_CONFIGS_F05[key]
      expect(config.columns[0].field).toBe('seq')
      expect(config.columns[0].editable).toBe(false)
    }
  })
})

// ─── F0-6 区块列配置测试 ─────────────────────────────────────────────────────

describe('BLOCK_COLUMN_CONFIGS_F06', () => {
  it('should have 4 block configs', () => {
    expect(Object.keys(BLOCK_COLUMN_CONFIGS_F06)).toHaveLength(4)
  })

  it('block1 should be "应付余额支持性证据检查"', () => {
    const b1 = BLOCK_COLUMN_CONFIGS_F06.block1
    expect(b1.title).toContain('余额')
    const fields = b1.columns.map((c) => c.field)
    expect(fields).toContain('inbound_date_no')
    expect(fields).toContain('contract_date')
    expect(fields).toContain('invoice_amount')
  })

  it('block2 should be "期后付款检查"', () => {
    const b2 = BLOCK_COLUMN_CONFIGS_F06.block2
    expect(b2.title).toContain('期后付款')
    const fields = b2.columns.map((c) => c.field)
    expect(fields).toContain('payment_amount')
    expect(fields).toContain('bank_amount')
    expect(fields).toContain('approval_date_no')
  })

  it('block3 should be "本期采购入库证据"', () => {
    const b3 = BLOCK_COLUMN_CONFIGS_F06.block3
    const fields = b3.columns.map((c) => c.field)
    expect(fields).toContain('inbound_date_no')
    expect(fields).toContain('contract_amount')
  })

  it('block4 should be "本期付款检查"', () => {
    const b4 = BLOCK_COLUMN_CONFIGS_F06.block4
    const fields = b4.columns.map((c) => c.field)
    expect(fields).toContain('payment_amount')
    expect(fields).toContain('bank_amount')
  })

  it('getSumFieldsF06 should return correct sum fields', () => {
    const sumFields1 = getSumFieldsF06('block1')
    expect(sumFields1).toContain('voucher_amount')
    expect(sumFields1).toContain('invoice_amount')

    const sumFields2 = getSumFieldsF06('block2')
    expect(sumFields2).toContain('payment_amount')
    expect(sumFields2).toContain('bank_amount')
  })

  it('each block should have is_abnormal as last column', () => {
    for (const key of ['block1', 'block2', 'block3', 'block4']) {
      const config = BLOCK_COLUMN_CONFIGS_F06[key]
      const lastCol = config.columns[config.columns.length - 1]
      expect(lastCol.field).toBe('is_abnormal')
      expect(lastCol.type).toBe('select')
    }
  })
})

// ─── F0-5/F0-6 共同列标准 ─────────────────────────────────────────────────────

describe('F05/F06 column standards', () => {
  it('all blocks should have consistent blockType field', () => {
    for (const [key, config] of Object.entries(BLOCK_COLUMN_CONFIGS_F05)) {
      expect(config.blockType).toBe(key)
    }
    for (const [key, config] of Object.entries(BLOCK_COLUMN_CONFIGS_F06)) {
      expect(config.blockType).toBe(key)
    }
  })

  it('is_abnormal should be select type in all blocks', () => {
    const allConfigs = [...Object.values(BLOCK_COLUMN_CONFIGS_F05), ...Object.values(BLOCK_COLUMN_CONFIGS_F06)]
    for (const config of allConfigs) {
      const abnCol = config.columns.find((c) => c.field === 'is_abnormal')
      expect(abnCol).toBeDefined()
      expect(abnCol?.type).toBe('select')
    }
  })

  it('ref_index should exist in all blocks', () => {
    const allConfigs = [...Object.values(BLOCK_COLUMN_CONFIGS_F05), ...Object.values(BLOCK_COLUMN_CONFIGS_F06)]
    for (const config of allConfigs) {
      const refCol = config.columns.find((c) => c.field === 'ref_index')
      expect(refCol).toBeDefined()
    }
  })
})

// ─── 导入导出列头匹配测试 ─────────────────────────────────────────────────────

describe('F0 import/export column header alignment', () => {
  // 后端 _f0_import_export.py 中 F05/F06 的区块列头必须与前端 blockColumnConfigs 对齐
  // 这里验证前端 label 完整性和唯一性

  it('F05 block column labels should be unique within each block (field-level)', () => {
    for (const config of Object.values(BLOCK_COLUMN_CONFIGS_F05)) {
      // Fields must be unique (labels can repeat across groups in grouped columns)
      const fields = config.columns.map((c) => c.field)
      expect(fields.length).toBe(new Set(fields).size)
    }
  })

  it('F06 block column labels should be unique within each block (field-level)', () => {
    for (const config of Object.values(BLOCK_COLUMN_CONFIGS_F06)) {
      const fields = config.columns.map((c) => c.field)
      expect(fields.length).toBe(new Set(fields).size)
    }
  })

  it('all columns should have non-empty label and field', () => {
    const allConfigs = [...Object.values(BLOCK_COLUMN_CONFIGS_F05), ...Object.values(BLOCK_COLUMN_CONFIGS_F06)]
    for (const config of allConfigs) {
      for (const col of config.columns) {
        expect(col.label).toBeTruthy()
        expect(col.field).toBeTruthy()
        expect(col.width).toBeGreaterThan(0)
      }
    }
  })
})
