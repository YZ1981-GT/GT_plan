/**
 * I1-5 增加检查模型 — 检查比例防 DIV/0 + 明细带入
 */
import { describe, it, expect } from 'vitest'
import {
  calcI1AdditionCoverage,
  summarizeI1Addition,
  seedI1AdditionFromDetail,
  seedI1AdditionFromI2Transfer,
  seedI1TraceFromCheckRows,
  mapDetailIncreaseMethodToAddition,
  methodToColGroup,
  shouldShowColGroup,
  isI1VatMismatch,
  calcI1TraceAmountDiff,
  emptyI1AdditionRow,
  normalizeI1AdditionRow,
} from '../i1AdditionCheckModel'

describe('i1AdditionCheckModel', () => {
  describe('calcI1AdditionCoverage', () => {
    it('正常比例', () => {
      expect(calcI1AdditionCoverage(25000, 100000)).toBe(25)
    })

    it('总体为 0 → null（防 #DIV/0!）', () => {
      expect(calcI1AdditionCoverage(1000, 0)).toBeNull()
      expect(calcI1AdditionCoverage(0, 0)).toBeNull()
    })

    it('总体为负 → null', () => {
      expect(calcI1AdditionCoverage(1000, -1)).toBeNull()
    })

    it('保留两位小数', () => {
      expect(calcI1AdditionCoverage(1, 3)).toBeCloseTo(33.33, 2)
    })
  })

  describe('summarizeI1Addition', () => {
    it('汇总检查合计与检查比例', () => {
      const rows = [
        emptyI1AdditionRow({ entryAmount: 10000, financeBookAmount: 8000, financeCost: 500, comboAmount: 0 }),
        emptyI1AdditionRow({ entryAmount: 20000, checkConclusion: '有异常', comboAmount: 15000 }),
      ]
      const s = summarizeI1Addition(rows, 100000)
      expect(s.checkedTotal).toBe(30000)
      expect(s.coverageRate).toBe(30)
      expect(s.financeBookTotal).toBe(8000)
      expect(s.financeCostTotal).toBe(500)
      expect(s.comboAmountTotal).toBe(15000)
      expect(s.anomalyCount).toBe(1)
      expect(s.checkedCount).toBe(2)
    })

    it('无总体时 coverageRate 为 null', () => {
      const s = summarizeI1Addition([emptyI1AdditionRow({ entryAmount: 5000 })], 0)
      expect(s.coverageRate).toBeNull()
      expect(s.checkedTotal).toBe(5000)
    })
  })

  describe('mapDetailIncreaseMethodToAddition', () => {
    it('映射 I1-2 标准枚举', () => {
      expect(mapDetailIncreaseMethodToAddition('购置')).toBe('购买')
      expect(mapDetailIncreaseMethodToAddition('内部研发')).toBe('自行开发')
      expect(mapDetailIncreaseMethodToAddition('企业合并增加')).toBe('企业合并')
      expect(mapDetailIncreaseMethodToAddition('其他增加')).toBe('其他')
      expect(mapDetailIncreaseMethodToAddition('股东投入')).toBe('股东投入')
      expect(mapDetailIncreaseMethodToAddition('融资性质购买')).toBe('融资性质购买')
    })
  })

  describe('seedI1AdditionFromDetail', () => {
    it('仅带入 costIncrease>0 的行', () => {
      const seeded = seedI1AdditionFromDetail([
        { rowId: '1', name: '软件A', costIncrease: 50000, acquisitionDate: '2022-03-01', acquisitionMethod: '外购' },
        { rowId: '2', name: '专利B', costIncrease: 0 },
        { rowId: '3', name: '', costIncrease: 10000 },
      ])
      expect(seeded).toHaveLength(1)
      expect(seeded[0].name).toBe('软件A')
      expect(seeded[0].entryAmount).toBe(50000)
      expect(seeded[0].acquisitionMethod).toBe('购买')
      expect(seeded[0].entryDate).toBe('2022-03-01')
    })

    it('优先 costIncreaseMethod，覆盖旧 acquisitionMethod', () => {
      const seeded = seedI1AdditionFromDetail([
        {
          rowId: '1',
          name: '专利C',
          costIncrease: 80000,
          costIncreaseMethod: '内部研发',
          acquisitionMethod: '外购',
        },
      ])
      expect(seeded).toHaveLength(1)
      expect(seeded[0].acquisitionMethod).toBe('自行开发')
    })

    it('企业合并增加 → 企业合并', () => {
      const seeded = seedI1AdditionFromDetail([
        { rowId: '1', name: '客户关系', costIncrease: 120000, costIncreaseMethod: '企业合并增加' },
      ])
      expect(seeded[0].acquisitionMethod).toBe('企业合并')
    })
  })

  describe('normalizeI1AdditionRow', () => {
    it('兼容旧字段 contractInvoiceNo → voucherNo', () => {
      const row = normalizeI1AdditionRow({
        name: '旧数据',
        entryAmount: '1234.5',
        contractInvoiceNo: 'PZ-001',
      })
      expect(row.voucherNo).toBe('PZ-001')
      expect(row.entryAmount).toBe(1234.5)
      expect(row.purchaseContractComplete).toBe('')
    })
  })

  describe('methodToColGroup / shouldShowColGroup', () => {
    it('映射取得方式到列组', () => {
      expect(methodToColGroup('购买')).toBe('purchase')
      expect(methodToColGroup('融资性质购买')).toBe('finance')
      expect(methodToColGroup('自行开发')).toBe('other')
      expect(methodToColGroup('企业合并')).toBe('combo')
    })

    it('精简视图仅显示样本涉及的列组', () => {
      const rows = [
        emptyI1AdditionRow({ name: 'A', acquisitionMethod: '自行开发' }),
        emptyI1AdditionRow({ name: 'B', acquisitionMethod: '购买' }),
      ]
      expect(shouldShowColGroup('purchase', 'compact', rows)).toBe(true)
      expect(shouldShowColGroup('other', 'compact', rows)).toBe(true)
      expect(shouldShowColGroup('invest', 'compact', rows)).toBe(false)
      expect(shouldShowColGroup('invest', 'full', rows)).toBe(true)
    })
  })

  describe('seedI1AdditionFromI2Transfer', () => {
    it('带入转无形项目为自行开发', () => {
      const seeded = seedI1AdditionFromI2Transfer([
        { projectName: '研发项目甲', amount: 88000, transferDate: '2024-06-30', transferAssetName: '软件著作权甲' },
        { projectName: '空金额', amount: 0 },
      ])
      expect(seeded).toHaveLength(1)
      expect(seeded[0].name).toBe('软件著作权甲')
      expect(seeded[0].acquisitionMethod).toBe('自行开发')
      expect(seeded[0].otherMethod).toBe('I2开发支出资本化转入')
      expect(seeded[0].entryAmount).toBe(88000)
      expect(seeded[0].entryDate).toBe('2024-06-30')
    })
  })

  describe('价税分离 / 证→账', () => {
    it('外购入账≠发票不含税 → vat mismatch', () => {
      expect(isI1VatMismatch(emptyI1AdditionRow({
        acquisitionMethod: '购买',
        entryAmount: 100000,
        invoiceAmountExTax: 90000,
      }))).toBe(true)
      expect(isI1VatMismatch(emptyI1AdditionRow({
        acquisitionMethod: '购买',
        entryAmount: 100000,
        invoiceAmountExTax: 100000,
        inputVat: 13000,
      }))).toBe(false)
      expect(isI1VatMismatch(emptyI1AdditionRow({
        acquisitionMethod: '自行开发',
        entryAmount: 100000,
        invoiceAmountExTax: 1,
      }))).toBe(false)
    })

    it('追查差额 = 源 − 账面', () => {
      expect(calcI1TraceAmountDiff(1000, 800)).toBe(200)
    })

    it('从账→证样本生成追查行', () => {
      const traces = seedI1TraceFromCheckRows([
        emptyI1AdditionRow({
          name: '软件A',
          voucherNo: 'PZ-1',
          entryAmount: 50000,
          invoiceAmountExTax: 50000,
          counterparty: '供应商甲',
        }),
      ])
      expect(traces).toHaveLength(1)
      expect(traces[0].bookAssetName).toBe('软件A')
      expect(traces[0].recordedInBooks).toBe('Y')
      expect(traces[0].amountDiff).toBe(0)
    })

    it('汇总含关联方/价税/追查计数', () => {
      const s = summarizeI1Addition(
        [
          emptyI1AdditionRow({
            entryAmount: 10000,
            acquisitionMethod: '购买',
            invoiceAmountExTax: 9000,
            isRelatedParty: 'Y',
            fundOccupationRisk: 'Y',
          }),
        ],
        100000,
        [
          { rowId: 't1', seq: 1, sourceType: '发票', sourceRef: '', sourceDate: '', sourceParty: '',
            sourceAmount: 100, recordedInBooks: 'N', bookVoucherNo: '', bookAssetName: '',
            bookAmount: 0, amountDiff: 100, checkResult: 'ERR', remark: '', indexRef: '' },
        ],
      )
      expect(s.relatedPartyCount).toBe(1)
      expect(s.fundRiskCount).toBe(1)
      expect(s.vatMismatchCount).toBe(1)
      expect(s.traceCount).toBe(1)
      expect(s.traceUnrecordedCount).toBe(1)
    })
  })
})
