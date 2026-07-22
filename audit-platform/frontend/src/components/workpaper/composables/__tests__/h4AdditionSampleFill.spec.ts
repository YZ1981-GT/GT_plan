/**
 * H4-4 抽凭回填 / OCR 映射单测
 */
import { describe, it, expect } from 'vitest'
import {
  splitCounterpartAccount,
  mergeSupportingDocs,
  mapVoucherSampleToAdditionPatch,
  normalizeFilledSamples,
  applyAdditionSamplePatch,
  mapOcrToAdditionPatch,
  extractOcrFields,
  applyOcrPatchToAdditionRow,
  resolveAdditionDebitAmount,
} from '../h4AdditionSampleFill'
import { normalizeAdditionRow } from '../h4AdditionCheckModel'

describe('h4AdditionSampleFill', () => {
  describe('splitCounterpartAccount', () => {
    it('拆分 科目/明细', () => {
      expect(splitCounterpartAccount('应付账款/甲供应商')).toEqual({
        account: '应付账款',
        detail: '甲供应商',
      })
    })

    it('无分隔符时全部作为科目', () => {
      expect(splitCounterpartAccount('银行存款')).toEqual({
        account: '银行存款',
        detail: '',
      })
    })
  })

  describe('mapVoucherSampleToAdditionPatch', () => {
    it('业务内容←summary，对方科目←counterpartAccount，不写入支持性文件', () => {
      const patch = mapVoucherSampleToAdditionPatch({
        voucherNo: '记-100',
        voucherDate: '2025-03-01',
        summary: '购入电缆',
        counterpartAccount: '应付账款/乙公司',
        debitAmount: '12000.50',
      })
      expect(patch.businessContent).toBe('购入电缆')
      expect(patch.oppositeAccount).toBe('应付账款')
      expect(patch.oppositeDetail).toBe('乙公司')
      expect(patch.amount).toBe(12000.5)
      expect(patch.voucherNo).toBe('记-100')
      expect(patch.supportingDocs).toBeUndefined()
    })

    it('借方优先于贷方/amount', () => {
      expect(resolveAdditionDebitAmount({
        debitAmount: '100',
        creditAmount: '999',
        amount: '50',
      })).toBe(100)
    })

    it('不用 accountName 冒充对方科目', () => {
      const patch = mapVoucherSampleToAdditionPatch({
        summary: '入库',
        accountName: '工程物资',
        counterpartAccount: null,
      })
      expect(patch.oppositeAccount).toBeUndefined()
      expect(patch.businessContent).toBe('入库')
    })

    it('abnormal 标记是否异常', () => {
      const patch = mapVoucherSampleToAdditionPatch({ summary: 'x', abnormal: true })
      expect(patch.isAbnormal).toBe('是')
    })
  })

  describe('normalizeFilledSamples', () => {
    it('兼容 { samples } / 裸数组 / { rows }', () => {
      expect(normalizeFilledSamples({ samples: [{ summary: 'a' }] })).toHaveLength(1)
      expect(normalizeFilledSamples([{ summary: 'b' }])).toHaveLength(1)
      expect(normalizeFilledSamples({ rows: [{ summary: 'c' }] })).toHaveLength(1)
      expect(normalizeFilledSamples(null)).toHaveLength(0)
    })
  })

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
