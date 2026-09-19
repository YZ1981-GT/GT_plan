/**
 * Unit Tests — S5 债务重组公式引擎
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/
 * Task: 3.2
 *
 * 已知值验证，互补 PBT 测试。
 * 覆盖 Property P4(S5 债务重组损益) 的具体场景。
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcCreditorGainLoss,
  calcDebtorGainLoss,
  type CreditorInput,
  type DebtorInput,
} from '../useS5FormulaEngine'

// ─── parseNum ────────────────────────────────────────────────

describe('useS5FormulaEngine', () => {
  describe('parseNum', () => {
    it('正常数值直接返回', () => {
      expect(parseNum(100)).toBe(100)
      expect(parseNum(-50.5)).toBe(-50.5)
    })

    it('null/undefined/空字符串→0', () => {
      expect(parseNum(null)).toBe(0)
      expect(parseNum(undefined)).toBe(0)
      expect(parseNum('')).toBe(0)
    })

    it('字符串数值解析', () => {
      expect(parseNum('123.45')).toBe(123.45)
      expect(parseNum('-200')).toBe(-200)
    })

    it('NaN/Infinity→0', () => {
      expect(parseNum(NaN)).toBe(0)
      expect(parseNum(Infinity)).toBe(0)
      expect(parseNum(-Infinity)).toBe(0)
    })
  })

  // ─── calcCreditorGainLoss (Property P4) ─────────────────────

  describe('calcCreditorGainLoss', () => {
    it('标准场景：origBook > origFair → 正损益（债权人获益）', () => {
      const input: CreditorInput = {
        origBook: 1_000_000,
        origFair: 800_000,
        recvFair: 750_000,
        otherCost: 10_000,
      }
      // 损益 = 1_000_000 - 800_000 + 750_000 = 950_000
      expect(calcCreditorGainLoss(input)).toBe(950_000)
    })

    it('origBook < origFair 且 recvFair 较小 → 负损益（债权人损失）', () => {
      const input: CreditorInput = {
        origBook: 500_000,
        origFair: 800_000,
        recvFair: 200_000,
        otherCost: 5_000,
      }
      // 损益 = 500_000 - 800_000 + 200_000 = -100_000
      expect(calcCreditorGainLoss(input)).toBe(-100_000)
    })

    it('损益恰好为0', () => {
      const input: CreditorInput = {
        origBook: 1_000_000,
        origFair: 1_200_000,
        recvFair: 200_000,
        otherCost: 0,
      }
      // 损益 = 1_000_000 - 1_200_000 + 200_000 = 0
      expect(calcCreditorGainLoss(input)).toBe(0)
    })

    it('所有值为0', () => {
      const input: CreditorInput = {
        origBook: 0,
        origFair: 0,
        recvFair: 0,
        otherCost: 0,
      }
      expect(calcCreditorGainLoss(input)).toBe(0)
    })

    it('大金额场景（亿级）', () => {
      const input: CreditorInput = {
        origBook: 500_000_000,
        origFair: 400_000_000,
        recvFair: 350_000_000,
        otherCost: 1_000_000,
      }
      // 损益 = 500_000_000 - 400_000_000 + 350_000_000 = 450_000_000
      expect(calcCreditorGainLoss(input)).toBe(450_000_000)
    })

    it('origFair 为0（无公允价值参考）', () => {
      const input: CreditorInput = {
        origBook: 1_000_000,
        origFair: 0,
        recvFair: 600_000,
        otherCost: 0,
      }
      // 损益 = 1_000_000 - 0 + 600_000 = 1_600_000
      expect(calcCreditorGainLoss(input)).toBe(1_600_000)
    })

    it('recvFair 为0（未收到任何资产）', () => {
      const input: CreditorInput = {
        origBook: 1_000_000,
        origFair: 800_000,
        recvFair: 0,
        otherCost: 0,
      }
      // 损益 = 1_000_000 - 800_000 + 0 = 200_000
      expect(calcCreditorGainLoss(input)).toBe(200_000)
    })
  })

  // ─── calcDebtorGainLoss (Property P4) ──────────────────────

  describe('calcDebtorGainLoss', () => {
    it('标准场景：debtBook > assetBook + equityFair → 正损益（债务人获益）', () => {
      const input: DebtorInput = {
        debtBook: 1_000_000,
        assetBook: 600_000,
        equityFair: 200_000,
      }
      // 损益 = 1_000_000 - 600_000 - 200_000 = 200_000
      expect(calcDebtorGainLoss(input)).toBe(200_000)
    })

    it('debtBook < assetBook + equityFair → 负损益（债务人损失）', () => {
      const input: DebtorInput = {
        debtBook: 500_000,
        assetBook: 400_000,
        equityFair: 200_000,
      }
      // 损益 = 500_000 - 400_000 - 200_000 = -100_000
      expect(calcDebtorGainLoss(input)).toBe(-100_000)
    })

    it('损益恰好为0', () => {
      const input: DebtorInput = {
        debtBook: 1_000_000,
        assetBook: 700_000,
        equityFair: 300_000,
      }
      // 损益 = 1_000_000 - 700_000 - 300_000 = 0
      expect(calcDebtorGainLoss(input)).toBe(0)
    })

    it('所有值为0', () => {
      const input: DebtorInput = {
        debtBook: 0,
        assetBook: 0,
        equityFair: 0,
      }
      expect(calcDebtorGainLoss(input)).toBe(0)
    })

    it('仅以资产清偿（无权益工具）', () => {
      const input: DebtorInput = {
        debtBook: 1_000_000,
        assetBook: 800_000,
        equityFair: 0,
      }
      // 损益 = 1_000_000 - 800_000 - 0 = 200_000
      expect(calcDebtorGainLoss(input)).toBe(200_000)
    })

    it('仅以权益工具清偿（无资产转让）', () => {
      const input: DebtorInput = {
        debtBook: 1_000_000,
        assetBook: 0,
        equityFair: 700_000,
      }
      // 损益 = 1_000_000 - 0 - 700_000 = 300_000
      expect(calcDebtorGainLoss(input)).toBe(300_000)
    })

    it('大金额场景（亿级）', () => {
      const input: DebtorInput = {
        debtBook: 800_000_000,
        assetBook: 500_000_000,
        equityFair: 100_000_000,
      }
      // 损益 = 800_000_000 - 500_000_000 - 100_000_000 = 200_000_000
      expect(calcDebtorGainLoss(input)).toBe(200_000_000)
    })

    it('assetBook 含金融+非金融合并值', () => {
      // assetBook = financialAssetBook(300_000) + nonFinancialAssetBook(200_000) = 500_000
      const input: DebtorInput = {
        debtBook: 1_000_000,
        assetBook: 500_000,
        equityFair: 150_000,
      }
      // 损益 = 1_000_000 - 500_000 - 150_000 = 350_000
      expect(calcDebtorGainLoss(input)).toBe(350_000)
    })
  })
})
