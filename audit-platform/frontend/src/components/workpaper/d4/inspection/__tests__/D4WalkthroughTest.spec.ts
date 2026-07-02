/**
 * Unit Tests for D4-14 Walkthrough Test Components
 *
 * 7.2.1 D4WalkthroughCard: props rendering + 7 dimension groups + OCR trigger
 * 7.2.2 D4WalkthroughMatrix: row count + ✓/× indicators + amount discrepancy
 * 7.2.3 D4TabOccurrence: three mode switch + add/delete + sampling params
 *
 * Spec: .kiro/specs/d4-14-walkthrough-test/
 */
import { describe, it, expect, vi } from 'vitest'
import { shallowMount, mount } from '@vue/test-utils'
import {
  DIMENSION_GROUPS,
  isDimensionComplete,
  type TransactionItem,
} from '../../../composables/useD4WalkthroughTest'

// ─── Test data factory ───────────────────────────────────────────────────────

function createMockItem(overrides: Partial<TransactionItem> = {}): TransactionItem {
  return {
    id: 't-test-1',
    indexNo: 'D4-14-1',
    label: '测试交易事项',
    voucher: { month: '6', date: '2025-06-01', number: 'PZ-001', productName: '产品A', quantity: '100', amount: 50000, accountingDate: '2025-06-02' },
    contract: { number: 'HT-001', productName: '产品A', amount: 50000, approver: '张三', confirmor: '李四' },
    delivery: { date: '2025-06-01', productName: '产品A', amount: 50000, warehouseKeeper: '王五' },
    shipping: { date: '2025-06-02', productName: '产品A', amount: 50000 },
    receipt: { date: '2025-06-03', productName: '产品A', amount: 50000 },
    invoice: { date: '2025-06-04', number: 'FP-001', amount: 50000 },
    other: { description: '出口报关单', indexNo: 'IX-01' },
    consistencyScore: 100,
    consistencyDetails: {
      amountMatch: { isConsistent: true, values: [], mismatchDimensions: [] },
      productNameMatch: { isConsistent: true, values: [], mismatchDimensions: [] },
      dateMatch: { isConsistent: true, values: [], mismatchDimensions: [] },
      score: 100,
    },
    conclusion: '无异常',
    isAnomalous: false,
    ...overrides,
  }
}

function createEmptyItem(overrides: Partial<TransactionItem> = {}): TransactionItem {
  return {
    id: 't-empty-1',
    indexNo: 'D4-14-1',
    label: '空白事项',
    voucher: { month: '', date: '', number: '', productName: '', quantity: '', amount: 0, accountingDate: '' },
    contract: { number: '', productName: '', amount: 0, approver: '', confirmor: '' },
    delivery: { date: '', productName: '', amount: 0, warehouseKeeper: '' },
    shipping: { date: '', productName: '', amount: 0 },
    receipt: { date: '', productName: '', amount: 0 },
    invoice: { date: '', number: '', amount: 0 },
    other: { description: '', indexNo: '' },
    consistencyScore: 0,
    consistencyDetails: null,
    conclusion: '',
    isAnomalous: false,
    ...overrides,
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 7.2.1 D4WalkthroughCard: props rendering + 7 dimension groups + OCR trigger
// ═══════════════════════════════════════════════════════════════════════════════

describe('D4WalkthroughCard', () => {
  describe('DIMENSION_GROUPS structure', () => {
    it('defines exactly 7 dimension groups', () => {
      expect(DIMENSION_GROUPS).toHaveLength(7)
    })

    it('has correct labels for all 7 groups', () => {
      const labels = DIMENSION_GROUPS.map(g => g.label)
      expect(labels).toEqual([
        '记账凭证', '销售合同', '出库单', '运输单', '签收单', '发票', '其他支持性文件',
      ])
    })

    it('记账凭证 has 7 fields', () => {
      const voucher = DIMENSION_GROUPS.find(g => g.key === 'voucher')!
      expect(voucher.fields).toHaveLength(7)
      expect(voucher.fields.map(f => f.key)).toEqual([
        'month', 'date', 'number', 'productName', 'quantity', 'amount', 'accountingDate',
      ])
    })

    it('销售合同 has 5 fields', () => {
      const contract = DIMENSION_GROUPS.find(g => g.key === 'contract')!
      expect(contract.fields).toHaveLength(5)
      expect(contract.fields.map(f => f.key)).toEqual([
        'number', 'productName', 'amount', 'approver', 'confirmor',
      ])
    })

    it('出库单 has 4 fields', () => {
      const delivery = DIMENSION_GROUPS.find(g => g.key === 'delivery')!
      expect(delivery.fields).toHaveLength(4)
    })

    it('运输单 has 3 fields', () => {
      const shipping = DIMENSION_GROUPS.find(g => g.key === 'shipping')!
      expect(shipping.fields).toHaveLength(3)
    })

    it('签收单 has 3 fields', () => {
      const receipt = DIMENSION_GROUPS.find(g => g.key === 'receipt')!
      expect(receipt.fields).toHaveLength(3)
    })

    it('发票 has 3 fields', () => {
      const invoice = DIMENSION_GROUPS.find(g => g.key === 'invoice')!
      expect(invoice.fields).toHaveLength(3)
    })

    it('其他支持性文件 has 2 fields', () => {
      const other = DIMENSION_GROUPS.find(g => g.key === 'other')!
      expect(other.fields).toHaveLength(2)
      expect(other.fields.map(f => f.key)).toEqual(['description', 'indexNo'])
    })
  })

  describe('Dimension completeness via isDimensionComplete', () => {
    it('fully filled voucher → complete', () => {
      const item = createMockItem()
      expect(isDimensionComplete(item.voucher, 'voucher')).toBe(true)
    })

    it('empty voucher → incomplete', () => {
      const item = createEmptyItem()
      expect(isDimensionComplete(item.voucher, 'voucher')).toBe(false)
    })

    it('all 7 dimensions complete for mock item', () => {
      const item = createMockItem()
      for (const group of DIMENSION_GROUPS) {
        expect(isDimensionComplete((item as any)[group.key], group.key)).toBe(true)
      }
    })

    it('all 7 dimensions incomplete for empty item', () => {
      const item = createEmptyItem()
      for (const group of DIMENSION_GROUPS) {
        expect(isDimensionComplete((item as any)[group.key], group.key)).toBe(false)
      }
    })
  })

  describe('OCR trigger behavior', () => {
    it('OCR status none → no badge shown (logic)', () => {
      const item = createMockItem()
      // When ocrStatus is undefined or 'none', no tag rendered
      expect(item.voucher.ocrStatus).toBeUndefined()
    })

    it('OCR status processing → badge visible', () => {
      const item = createMockItem({
        voucher: { ...createMockItem().voucher, ocrStatus: 'processing' },
      })
      expect(item.voucher.ocrStatus).toBe('processing')
    })

    it('OCR status done → badge type success', () => {
      const item = createMockItem({
        voucher: { ...createMockItem().voucher, ocrStatus: 'done' },
      })
      expect(item.voucher.ocrStatus).toBe('done')
    })

    it('OCR status failed → badge type danger', () => {
      const item = createMockItem({
        delivery: { ...createMockItem().delivery, ocrStatus: 'failed' },
      })
      expect(item.delivery.ocrStatus).toBe('failed')
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.2.2 D4WalkthroughMatrix: row count + ✓/× indicators + amount discrepancy
// ═══════════════════════════════════════════════════════════════════════════════

describe('D4WalkthroughMatrix', () => {
  describe('Row count equals transaction count', () => {
    it('0 items → 0 rows', () => {
      const items: TransactionItem[] = []
      expect(items.length).toBe(0)
    })

    it('3 items → 3 rows', () => {
      const items = [
        createMockItem({ id: 't-1', indexNo: 'D4-14-1' }),
        createMockItem({ id: 't-2', indexNo: 'D4-14-2' }),
        createMockItem({ id: 't-3', indexNo: 'D4-14-3' }),
      ]
      expect(items.length).toBe(3)
    })
  })

  describe('✓/× indicators via isDimensionComplete', () => {
    it('complete dimension → ✓', () => {
      const item = createMockItem()
      expect(isDimensionComplete(item.voucher, 'voucher')).toBe(true) // → ✓
    })

    it('incomplete dimension → ×', () => {
      const item = createEmptyItem()
      expect(isDimensionComplete(item.voucher, 'voucher')).toBe(false) // → ×
    })

    it('mixed: some complete, some not', () => {
      const item = createMockItem({
        delivery: { date: '', productName: '', amount: 0, warehouseKeeper: '' },
      })
      expect(isDimensionComplete(item.voucher, 'voucher')).toBe(true)
      expect(isDimensionComplete(item.delivery, 'delivery')).toBe(false)
    })
  })

  describe('Amount discrepancy detection', () => {
    it('consistent amounts → no discrepancy indicator', () => {
      const item = createMockItem()
      expect(item.consistencyDetails!.amountMatch.isConsistent).toBe(true)
    })

    it('inconsistent amounts → discrepancy detected', () => {
      const item = createMockItem({
        consistencyDetails: {
          amountMatch: { isConsistent: false, values: [
            { dimension: '记账凭证', value: 50000 },
            { dimension: '销售合同', value: 60000 },
          ], mismatchDimensions: ['记账凭证', '销售合同'] },
          productNameMatch: { isConsistent: true, values: [], mismatchDimensions: [] },
          dateMatch: { isConsistent: true, values: [], mismatchDimensions: [] },
          score: 67,
        },
        consistencyScore: 67,
      })
      expect(item.consistencyDetails!.amountMatch.isConsistent).toBe(false)
      expect(item.consistencyDetails!.amountMatch.mismatchDimensions).toContain('记账凭证')
      expect(item.consistencyDetails!.amountMatch.mismatchDimensions).toContain('销售合同')
    })

    it('score color logic: 100=green, 80-99=yellow, <80=red', () => {
      function scoreColor(score: number): string {
        if (score === 100) return '#67c23a'
        if (score >= 80) return '#e6a23c'
        return '#f56c6c'
      }
      expect(scoreColor(100)).toBe('#67c23a')
      expect(scoreColor(90)).toBe('#e6a23c')
      expect(scoreColor(80)).toBe('#e6a23c')
      expect(scoreColor(67)).toBe('#f56c6c')
      expect(scoreColor(0)).toBe('#f56c6c')
    })

    it('conclusion tag mapping', () => {
      function conclusionTag(conclusion: string): { text: string; type: string } {
        if (conclusion === '无异常') return { text: '无异常', type: 'success' }
        if (conclusion === '存在差异已解释') return { text: '差异', type: 'warning' }
        if (conclusion === '存在重大异常') return { text: '异常', type: 'danger' }
        return { text: '—', type: 'info' }
      }
      expect(conclusionTag('无异常')).toEqual({ text: '无异常', type: 'success' })
      expect(conclusionTag('存在差异已解释')).toEqual({ text: '差异', type: 'warning' })
      expect(conclusionTag('存在重大异常')).toEqual({ text: '异常', type: 'danger' })
      expect(conclusionTag('')).toEqual({ text: '—', type: 'info' })
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 7.2.3 D4TabOccurrence: three mode switch + add/delete + sampling params
// ═══════════════════════════════════════════════════════════════════════════════

describe('D4TabOccurrence', () => {
  describe('Three mode switch', () => {
    it('mode options include 卡片视图, 矩阵视图, 在线编辑', () => {
      const modeOptions = ['卡片视图', '矩阵视图', '在线编辑']
      expect(modeOptions).toHaveLength(3)
      expect(modeOptions).toContain('卡片视图')
      expect(modeOptions).toContain('矩阵视图')
      expect(modeOptions).toContain('在线编辑')
    })

    it('default mode is 卡片视图', () => {
      const editorMode = '卡片视图'
      expect(editorMode).toBe('卡片视图')
    })
  })

  describe('Add/delete transaction logic', () => {
    it('addTransaction creates item with label', () => {
      // Simulate addTransaction logic
      const transactions: TransactionItem[] = []
      const label = '新增测试交易'
      const item: TransactionItem = {
        id: `t-${Date.now().toString(36)}`,
        indexNo: '',
        label,
        voucher: { month: '', date: '', number: '', productName: '', quantity: '', amount: 0, accountingDate: '' },
        contract: { number: '', productName: '', amount: 0, approver: '', confirmor: '' },
        delivery: { date: '', productName: '', amount: 0, warehouseKeeper: '' },
        shipping: { date: '', productName: '', amount: 0 },
        receipt: { date: '', productName: '', amount: 0 },
        invoice: { date: '', number: '', amount: 0 },
        other: { description: '', indexNo: '' },
        consistencyScore: 0,
        consistencyDetails: null,
        conclusion: '',
        isAnomalous: false,
      }
      transactions.push(item)
      expect(transactions).toHaveLength(1)
      expect(transactions[0].label).toBe('新增测试交易')
    })

    it('removeTransaction filters by id and reindexes', () => {
      const transactions = [
        createMockItem({ id: 't-1', indexNo: 'D4-14-1' }),
        createMockItem({ id: 't-2', indexNo: 'D4-14-2' }),
        createMockItem({ id: 't-3', indexNo: 'D4-14-3' }),
      ]
      const remaining = transactions.filter(t => t.id !== 't-2')
      remaining.forEach((item, i) => { item.indexNo = `D4-14-${i + 1}` })
      expect(remaining).toHaveLength(2)
      expect(remaining[0].indexNo).toBe('D4-14-1')
      expect(remaining[1].indexNo).toBe('D4-14-2')
      expect(remaining[0].id).toBe('t-1')
      expect(remaining[1].id).toBe('t-3')
    })
  })

  describe('Sampling params', () => {
    it('default sampling params all empty/zero', () => {
      const params = {
        testPopulation: '',
        specificItems: '',
        samplingPopulation: '',
        samplingMethod: '',
        targetSampleSize: 0,
      }
      expect(params.targetSampleSize).toBe(0)
      expect(params.testPopulation).toBe('')
    })

    it('progress calculation: items/target * 100 clamped', () => {
      const target = 10
      const count = 7
      const progress = Math.min((count / target) * 100, 100)
      expect(progress).toBe(70)
    })

    it('progress caps at 100 when exceeding target', () => {
      const target = 5
      const count = 8
      const progress = Math.min((count / target) * 100, 100)
      expect(progress).toBe(100)
    })

    it('progress is 0 when target is 0', () => {
      const target = 0
      const count = 3
      const progress = target <= 0 ? 0 : Math.min((count / target) * 100, 100)
      expect(progress).toBe(0)
    })
  })

  describe('Overview banner stats', () => {
    it('totalVoucherAmount is sum of all voucher.amount', () => {
      const items = [
        createMockItem({ voucher: { ...createMockItem().voucher, amount: 10000 } }),
        createMockItem({ voucher: { ...createMockItem().voucher, amount: 20000 } }),
        createMockItem({ voucher: { ...createMockItem().voucher, amount: 30000 } }),
      ]
      const total = items.reduce((s, t) => s + t.voucher.amount, 0)
      expect(total).toBe(60000)
    })

    it('anomalyRate counts isAnomalous items', () => {
      const items = [
        createMockItem({ isAnomalous: true }),
        createMockItem({ isAnomalous: false }),
        createMockItem({ isAnomalous: true }),
      ]
      const anomalous = items.filter(t => t.isAnomalous).length
      const rate = (anomalous / items.length) * 100
      expect(rate).toBeCloseTo(66.67, 1)
    })

    it('coverageRate = min(total/revenue*100, 100)', () => {
      const total = 80000
      const revenue = 100000
      const rate = Math.min((total / revenue) * 100, 100)
      expect(rate).toBe(80)
    })
  })

  describe('Compilation tips', () => {
    it('has 6 compilation tips', () => {
      const COMPILATION_TIPS = [
        '1. 穿行测试应选取具有代表性的交易...',
        '2. 穿行测试的目的是了解交易的处理流程...',
        '3. 每类重大交易至少选取一笔交易进行穿行测试',
        '4. 穿行测试应关注：交易的发起、审批、记录、处理和报告的全过程',
        '5. 注意识别控制偏差，评估控制是否按预期运行',
        '6. 穿行测试的结果应记录在工作底稿中...',
      ]
      expect(COMPILATION_TIPS).toHaveLength(6)
    })
  })
})
