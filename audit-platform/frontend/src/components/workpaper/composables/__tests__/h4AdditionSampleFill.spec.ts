/**
 * H4-4 抽凭回填补丁 / OCR 映射单测（抽凭样本映射改走共享回填函数，用例在 h4VoucherFill.spec.ts）
 */
import { describe, it, expect } from 'vitest'
import {
  mergeSupportingDocs,
  applyAdditionSamplePatch,
  mapOcrToAdditionPatch,
  extractOcrFields,
  applyOcrPatchToAdditionRow,
} from '../h4AdditionSampleFill'
import { normalizeAdditionRow } from '../h4AdditionCheckModel'

describe('h4AdditionSampleFill', () => {
  describe('applyAdditionSamplePatch', () => {
    it('已有名称时不覆盖；强制回填业务内容', () => {
      const row = normalizeAdditionRow({ name: '已有物资', amount: 1 })
      applyAdditionSamplePatch(row, {
        name: '抽凭摘要',
        businessContent: '购入钢管',
        oppositeAccount: '应付账款',
        amount: 5000,
      })
      expect(row.name).toBe('已有物资')
      expect(row.businessContent).toBe('购入钢管')
      expect(row.amount).toBe(5000)
    })
  })

  describe('OCR → 支持性文件', () => {
    it('拼接合同/发票/单据到 supportingDocs，并映射供应商与金额', () => {
      const { patch, previewLines } = mapOcrToAdditionPatch({
        contractNo: 'HT-2025-1',
        invoiceNo: 'FP998',
        counterparty: '丙供应商',
        contractAmount: 80000,
        serviceContent: '变压器',
        acceptanceRef: 'YS-01',
      })
      expect(patch.supportingDocs).toContain('合同:HT-2025-1')
      expect(patch.supportingDocs).toContain('发票:FP998')
      expect(patch.supportingDocs).toContain('验收单:YS-01')
      expect(patch.supplier).toBe('丙供应商')
      expect(patch.invoiceAmount).toBe(80000)
      expect(patch.contractNo).toBe('HT-2025-1')
      expect(previewLines.length).toBeGreaterThan(0)
    })

    it('extractOcrFields 兼容嵌套 data.extracted_fields', () => {
      const { fields, confidence } = extractOcrFields({
        data: {
          extracted_fields: { contractNo: 'C1', counterparty: '丁' },
          confidence: 0.88,
        },
      })
      expect(fields.contractNo).toBe('C1')
      expect(confidence).toBe(0.88)
    })

    it('mergeSupportingDocs 去重合并；OCR 仅填空字段', () => {
      const row = normalizeAdditionRow({
        name: '原名',
        supplier: '已有供应商',
        supportingDocs: '合同:HT-1',
        amount: 100,
      })
      applyOcrPatchToAdditionRow(row, {
        supportingDocs: '合同:HT-1 / 发票:FP1',
        supplier: 'OCR供应商',
        invoiceAmount: 99,
        name: 'OCR名',
      })
      expect(row.supportingDocs).toBe('合同:HT-1 / 发票:FP1')
      expect(row.supplier).toBe('已有供应商')
      expect(row.invoiceAmount).toBe(99)
      expect(row.name).toBe('原名')
    })

    it('mergeSupportingDocs 工具函数', () => {
      expect(mergeSupportingDocs('合同:A', '发票:B')).toBe('合同:A / 发票:B')
      expect(mergeSupportingDocs('合同:A', '合同:A')).toBe('合同:A')
    })
  })
})
