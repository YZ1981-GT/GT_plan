/**
 * useG6SppiInventory + useG6SppiReconciliation 单元测试
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 10.5
 * 验证：
 *   - G6-9 盘点差异计算（盘点数量 - 账面数量）
 *   - G6-10 倒轧公式、差异必填校验逻辑
 * Requirements: 6.1, 6.2, 6.3, 6.4
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { useG6SppiInventory } from '../useG6SppiInventory'
import type { SecuritiesInventoryData, InventoryItem } from '../useG6SppiInventory'
import { useG6SppiReconciliation } from '../useG6SppiReconciliation'
import type { ReconciliationData, ReconciliationItem } from '../useG6SppiReconciliation'

// ═══════════════════════════════════════════════════════════════════════════════
// useG6SppiInventory (G6-9 有价证券盘点表)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useG6SppiInventory', () => {
  // ─── 差异计算 ──────────────────────────────────────────────────────────────

  describe('差异计算: countQuantity - bookQuantity', () => {
    it('盘点数 > 账面数 → 正差异', () => {
      const { items, loadData } = useG6SppiInventory()
      loadData({
        items: [{ id: 'a', seq: 1, securitiesName: '债券A', securitiesCode: 'B001',
          faceValue: 100, countQuantity: 120, bookQuantity: 100, variance: 0 }],
        auditConclusion: '',
      })
      expect(items.value[0].variance).toBe(20)
    })

    it('盘点数 < 账面数 → 负差异', () => {
      const { items, loadData } = useG6SppiInventory()
      loadData({
        items: [{ id: 'b', seq: 1, securitiesName: '债券B', securitiesCode: 'B002',
          faceValue: 100, countQuantity: 80, bookQuantity: 100, variance: 0 }],
        auditConclusion: '',
      })
      expect(items.value[0].variance).toBe(-20)
    })

    it('盘点数 = 账面数 → 差异为0', () => {
      const { items, loadData } = useG6SppiInventory()
      loadData({
        items: [{ id: 'c', seq: 1, securitiesName: '债券C', securitiesCode: 'B003',
          faceValue: 100, countQuantity: 500, bookQuantity: 500, variance: 0 }],
        auditConclusion: '',
      })
      expect(items.value[0].variance).toBe(0)
    })
  })


  // ─── hasVariance ───────────────────────────────────────────────────────────

  describe('hasVariance', () => {
    it('差异≠0 返回 true', () => {
      const { hasVariance, loadData, items } = useG6SppiInventory()
      loadData({
        items: [{ id: 'x', seq: 1, securitiesName: 'X', securitiesCode: '',
          faceValue: 0, countQuantity: 10, bookQuantity: 5, variance: 0 }],
        auditConclusion: '',
      })
      expect(hasVariance(items.value[0])).toBe(true)
    })

    it('差异=0 返回 false', () => {
      const { hasVariance, loadData, items } = useG6SppiInventory()
      loadData({
        items: [{ id: 'y', seq: 1, securitiesName: 'Y', securitiesCode: '',
          faceValue: 0, countQuantity: 100, bookQuantity: 100, variance: 0 }],
        auditConclusion: '',
      })
      expect(hasVariance(items.value[0])).toBe(false)
    })
  })


  // ─── getVarianceCellStyle ─────────────────────────────────────────────────

  describe('getVarianceCellStyle', () => {
    it('差异≠0时返回红色样式', () => {
      const { getVarianceCellStyle, loadData, items } = useG6SppiInventory()
      loadData({
        items: [{ id: 's1', seq: 1, securitiesName: 'S1', securitiesCode: '',
          faceValue: 0, countQuantity: 15, bookQuantity: 10, variance: 0 }],
        auditConclusion: '',
      })
      const style = getVarianceCellStyle(items.value[0])
      expect(style.color).toBe('#dc2626')
      expect(style.backgroundColor).toBe('#fef2f2')
      expect(style.fontWeight).toBe('600')
    })

    it('差异=0时返回空样式', () => {
      const { getVarianceCellStyle, loadData, items } = useG6SppiInventory()
      loadData({
        items: [{ id: 's2', seq: 1, securitiesName: 'S2', securitiesCode: '',
          faceValue: 0, countQuantity: 50, bookQuantity: 50, variance: 0 }],
        auditConclusion: '',
      })
      const style = getVarianceCellStyle(items.value[0])
      expect(style).toEqual({})
    })
  })


  // ─── loadData / toJSON round-trip ─────────────────────────────────────────

  describe('loadData / toJSON round-trip', () => {
    it('加载数据后导出保持一致', () => {
      const { loadData, toJSON } = useG6SppiInventory()
      const input: SecuritiesInventoryData = {
        items: [
          { id: 'rt1', seq: 1, securitiesName: '国债A', securitiesCode: 'GZ001',
            faceValue: 1000000, countQuantity: 200, bookQuantity: 195, variance: 0 },
          { id: 'rt2', seq: 2, securitiesName: '企业债B', securitiesCode: 'QY002',
            faceValue: 500000, countQuantity: 300, bookQuantity: 300, variance: 0 },
        ],
        auditConclusion: '盘点无重大差异',
      }
      loadData(input)
      const output = toJSON()
      expect(output.items).toHaveLength(2)
      expect(output.items[0].securitiesName).toBe('国债A')
      expect(output.items[0].variance).toBe(5) // 200-195
      expect(output.items[1].variance).toBe(0) // 300-300
      expect(output.auditConclusion).toBe('盘点无重大差异')
    })

    it('loadData(null) 重置为空', () => {
      const { loadData, toJSON, items } = useG6SppiInventory()
      loadData({
        items: [{ id: 'z', seq: 1, securitiesName: 'Z', securitiesCode: '',
          faceValue: 0, countQuantity: 10, bookQuantity: 5, variance: 0 }],
        auditConclusion: 'test',
      })
      expect(items.value).toHaveLength(1)
      loadData(null)
      expect(items.value).toHaveLength(0)
    })
  })


  // ─── 序号重排 (add/remove via loadData) ────────────────────────────────────

  describe('item sequencing after add/remove', () => {
    it('loadData后序号从1开始递增', () => {
      const { loadData, items } = useG6SppiInventory()
      loadData({
        items: [
          { id: 'a1', seq: 99, securitiesName: '债券1', securitiesCode: '',
            faceValue: 0, countQuantity: 10, bookQuantity: 10, variance: 0 },
          { id: 'a2', seq: 88, securitiesName: '债券2', securitiesCode: '',
            faceValue: 0, countQuantity: 20, bookQuantity: 20, variance: 0 },
          { id: 'a3', seq: 77, securitiesName: '债券3', securitiesCode: '',
            faceValue: 0, countQuantity: 30, bookQuantity: 30, variance: 0 },
        ],
        auditConclusion: '',
      })
      // loadData重排序号为1,2,3
      expect(items.value[0].seq).toBe(1)
      expect(items.value[1].seq).toBe(2)
      expect(items.value[2].seq).toBe(3)
    })

    it('手动删除后序号连续（通过直接操作items模拟）', () => {
      const { loadData, items } = useG6SppiInventory()
      loadData({
        items: [
          { id: 'd1', seq: 1, securitiesName: 'A', securitiesCode: '',
            faceValue: 0, countQuantity: 0, bookQuantity: 0, variance: 0 },
          { id: 'd2', seq: 2, securitiesName: 'B', securitiesCode: '',
            faceValue: 0, countQuantity: 0, bookQuantity: 0, variance: 0 },
          { id: 'd3', seq: 3, securitiesName: 'C', securitiesCode: '',
            faceValue: 0, countQuantity: 0, bookQuantity: 0, variance: 0 },
        ],
        auditConclusion: '',
      })
      // 模拟删除中间行并重排序号
      items.value = items.value.filter(r => r.id !== 'd2')
      items.value.forEach((r, i) => { r.seq = i + 1 })
      expect(items.value).toHaveLength(2)
      expect(items.value[0].seq).toBe(1)
      expect(items.value[0].securitiesName).toBe('A')
      expect(items.value[1].seq).toBe(2)
      expect(items.value[1].securitiesName).toBe('C')
    })
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// useG6SppiReconciliation (G6-10 盘点倒轧表)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useG6SppiReconciliation', () => {
  // ─── 倒轧公式: reportDateQuantity = countDateQuantity + changeQuantity ────

  describe('reportDateQuantity = calcInventoryRollForward(countDateQuantity, changeQuantity)', () => {
    it('正向增减: 盘点100 + 增减20 = 基准日120', () => {
      const { loadData, items } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'r1', seq: 1, securitiesName: '债券X',
          countDateQuantity: 100, changeQuantity: 20, reportDateQuantity: 0,
          bookQuantity: 110, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
        auditConclusion: '',
      })
      expect(items.value[0].reportDateQuantity).toBe(120)
    })

    it('负向增减: 盘点200 + 增减(-50) = 基准日150', () => {
      const { loadData, items } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'r2', seq: 1, securitiesName: '债券Y',
          countDateQuantity: 200, changeQuantity: -50, reportDateQuantity: 0,
          bookQuantity: 150, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
        auditConclusion: '',
      })
      expect(items.value[0].reportDateQuantity).toBe(150)
    })

    it('增减为0: 盘点日=基准日', () => {
      const { loadData, items } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'r3', seq: 1, securitiesName: '债券Z',
          countDateQuantity: 500, changeQuantity: 0, reportDateQuantity: 0,
          bookQuantity: 500, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
        auditConclusion: '',
      })
      expect(items.value[0].reportDateQuantity).toBe(500)
    })
  })


  // ─── 差异公式: variance = reportDateQuantity - bookQuantity ────────────────

  describe('variance = calcInventoryVariance(reportDateQuantity, bookQuantity)', () => {
    it('基准日 > 账面 → 正差异(多)', () => {
      const { loadData, items } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'v1', seq: 1, securitiesName: 'A',
          countDateQuantity: 100, changeQuantity: 30, reportDateQuantity: 0,
          bookQuantity: 120, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
        auditConclusion: '',
      })
      // reportDateQuantity = 100 + 30 = 130, variance = 130 - 120 = 10
      expect(items.value[0].variance).toBe(10)
    })

    it('基准日 < 账面 → 负差异(少)', () => {
      const { loadData, items } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'v2', seq: 1, securitiesName: 'B',
          countDateQuantity: 80, changeQuantity: 10, reportDateQuantity: 0,
          bookQuantity: 100, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
        auditConclusion: '',
      })
      // reportDateQuantity = 80 + 10 = 90, variance = 90 - 100 = -10
      expect(items.value[0].variance).toBe(-10)
    })

    it('基准日 = 账面 → 差异为0', () => {
      const { loadData, items } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'v3', seq: 1, securitiesName: 'C',
          countDateQuantity: 100, changeQuantity: 0, reportDateQuantity: 0,
          bookQuantity: 100, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
        auditConclusion: '',
      })
      expect(items.value[0].variance).toBe(0)
    })
  })


  // ─── isVarianceReasonMissing ──────────────────────────────────────────────

  describe('isVarianceReasonMissing', () => {
    it('|差异|>0 且 reason为空 → true', () => {
      const { isVarianceReasonMissing, loadData, items } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'm1', seq: 1, securitiesName: 'M1',
          countDateQuantity: 110, changeQuantity: 0, reportDateQuantity: 0,
          bookQuantity: 100, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
        auditConclusion: '',
      })
      // variance = 110 - 100 = 10, reason = ''
      expect(isVarianceReasonMissing(items.value[0])).toBe(true)
    })

    it('|差异|>0 且 reason非空 → false', () => {
      const { isVarianceReasonMissing, loadData, items } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'm2', seq: 1, securitiesName: 'M2',
          countDateQuantity: 110, changeQuantity: 0, reportDateQuantity: 0,
          bookQuantity: 100, variance: 0, varianceReason: '计数误差已确认',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
        auditConclusion: '',
      })
      expect(isVarianceReasonMissing(items.value[0])).toBe(false)
    })

    it('差异=0 且 reason为空 → false (无需填写)', () => {
      const { isVarianceReasonMissing, loadData, items } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'm3', seq: 1, securitiesName: 'M3',
          countDateQuantity: 100, changeQuantity: 0, reportDateQuantity: 0,
          bookQuantity: 100, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
        auditConclusion: '',
      })
      expect(isVarianceReasonMissing(items.value[0])).toBe(false)
    })
  })


  // ─── isVarianceValid ──────────────────────────────────────────────────────

  describe('isVarianceValid', () => {
    it('所有行差异原因均满足 → true', () => {
      const { isVarianceValid, loadData } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [
          { id: 'iv1', seq: 1, securitiesName: 'V1',
            countDateQuantity: 100, changeQuantity: 0, reportDateQuantity: 0,
            bookQuantity: 100, variance: 0, varianceReason: '',
            varianceConclusion: '', indexRef: '', remark: '' },
          { id: 'iv2', seq: 2, securitiesName: 'V2',
            countDateQuantity: 110, changeQuantity: 0, reportDateQuantity: 0,
            bookQuantity: 100, variance: 0, varianceReason: '已核实',
            varianceConclusion: '', indexRef: '', remark: '' },
        ],
        changeDetails: [],
        auditConclusion: '',
      })
      // 行1差异=0不需填; 行2差异=10已填 → valid
      expect(isVarianceValid.value).toBe(true)
    })

    it('任一行有差异但原因未填 → false', () => {
      const { isVarianceValid, loadData } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [
          { id: 'iv3', seq: 1, securitiesName: 'V3',
            countDateQuantity: 100, changeQuantity: 0, reportDateQuantity: 0,
            bookQuantity: 100, variance: 0, varianceReason: '',
            varianceConclusion: '', indexRef: '', remark: '' },
          { id: 'iv4', seq: 2, securitiesName: 'V4',
            countDateQuantity: 120, changeQuantity: 0, reportDateQuantity: 0,
            bookQuantity: 100, variance: 0, varianceReason: '',
            varianceConclusion: '', indexRef: '', remark: '' },
        ],
        changeDetails: [],
        auditConclusion: '',
      })
      // 行2差异=20,reason='' → invalid
      expect(isVarianceValid.value).toBe(false)
    })
  })


  // ─── Tab切换与行同步 ───────────────────────────────────────────────────────

  describe('Tab切换与行同步', () => {
    it('switchTab 切换activeTab', () => {
      const { activeTab, switchTab } = useG6SppiReconciliation()
      expect(activeTab.value).toBe('rollForward')
      switchTab('changeDetail')
      expect(activeTab.value).toBe('changeDetail')
      switchTab('rollForward')
      expect(activeTab.value).toBe('rollForward')
    })

    it('selectRow 更新 selectedRowIndex', () => {
      const { selectedRowIndex, selectRow, loadData } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [
          { id: 'sr1', seq: 1, securitiesName: 'A',
            countDateQuantity: 10, changeQuantity: 0, reportDateQuantity: 0,
            bookQuantity: 10, variance: 0, varianceReason: '',
            varianceConclusion: '', indexRef: '', remark: '' },
          { id: 'sr2', seq: 2, securitiesName: 'B',
            countDateQuantity: 20, changeQuantity: 0, reportDateQuantity: 0,
            bookQuantity: 20, variance: 0, varianceReason: '',
            varianceConclusion: '', indexRef: '', remark: '' },
        ],
        changeDetails: [],
        auditConclusion: '',
      })
      selectRow(1)
      expect(selectedRowIndex.value).toBe(1)
    })

    it('selectRow 越界不生效', () => {
      const { selectedRowIndex, selectRow, loadData } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [
          { id: 'sr3', seq: 1, securitiesName: 'C',
            countDateQuantity: 10, changeQuantity: 0, reportDateQuantity: 0,
            bookQuantity: 10, variance: 0, varianceReason: '',
            varianceConclusion: '', indexRef: '', remark: '' },
        ],
        changeDetails: [],
        auditConclusion: '',
      })
      selectRow(5) // 越界
      expect(selectedRowIndex.value).toBe(0)
    })
  })


  // ─── loadData 初始化 items 和 changeDetails ───────────────────────────────

  describe('loadData initializes both items and changeDetails', () => {
    it('正常加载2个区段的数据', () => {
      const { loadData, items, changeDetails, activeTab, auditConclusion } = useG6SppiReconciliation()
      loadData({
        activeTab: 'changeDetail',
        selectedRowIndex: 1,
        items: [
          { id: 'ld1', seq: 1, securitiesName: '公司债A',
            countDateQuantity: 500, changeQuantity: 20, reportDateQuantity: 0,
            bookQuantity: 520, variance: 0, varianceReason: '',
            varianceConclusion: '', indexRef: '', remark: '' },
        ],
        changeDetails: [
          { id: 'cd1', securitiesName: '公司债A', date: '2024-12-20',
            transactionType: 'buy', quantity: 20, amount: 2000000,
            voucherNo: 'PZ-001', handler: '张三', remark: '' },
        ],
        auditConclusion: '倒轧无异常',
      })
      expect(items.value).toHaveLength(1)
      expect(items.value[0].securitiesName).toBe('公司债A')
      expect(items.value[0].reportDateQuantity).toBe(520)  // 500+20
      expect(items.value[0].variance).toBe(0)  // 520-520
      expect(changeDetails.value).toHaveLength(1)
      expect(changeDetails.value[0].transactionType).toBe('buy')
      expect(changeDetails.value[0].quantity).toBe(20)
      expect(activeTab.value).toBe('changeDetail')
      expect(auditConclusion.value).toBe('倒轧无异常')
    })

    it('loadData(null) 重置所有状态', () => {
      const { loadData, items, changeDetails, activeTab, selectedRowIndex } = useG6SppiReconciliation()
      loadData({
        activeTab: 'changeDetail',
        selectedRowIndex: 2,
        items: [
          { id: 'n1', seq: 1, securitiesName: 'N1',
            countDateQuantity: 10, changeQuantity: 0, reportDateQuantity: 0,
            bookQuantity: 10, variance: 0, varianceReason: '',
            varianceConclusion: '', indexRef: '', remark: '' },
        ],
        changeDetails: [
          { id: 'ncd1', securitiesName: 'N1', date: '',
            transactionType: '', quantity: 0, amount: 0,
            voucherNo: '', handler: '', remark: '' },
        ],
        auditConclusion: 'test',
      })
      loadData(null)
      expect(items.value).toHaveLength(0)
      expect(changeDetails.value).toHaveLength(0)
      expect(activeTab.value).toBe('rollForward')
      expect(selectedRowIndex.value).toBe(0)
    })
  })


  // ─── toJSON serialization ─────────────────────────────────────────────────

  describe('toJSON serialization', () => {
    it('序列化输出包含所有字段', () => {
      const { loadData, toJSON, switchTab } = useG6SppiReconciliation()
      loadData({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [
          { id: 'tj1', seq: 1, securitiesName: '测试债券',
            countDateQuantity: 300, changeQuantity: -10, reportDateQuantity: 0,
            bookQuantity: 280, variance: 0, varianceReason: '到期赎回差异',
            varianceConclusion: '属正常波动', indexRef: 'G6-9', remark: '' },
        ],
        changeDetails: [
          { id: 'tjcd1', securitiesName: '测试债券', date: '2024-12-25',
            transactionType: 'sell', quantity: 10, amount: 1000000,
            voucherNo: 'PZ-102', handler: '李四', remark: '到期赎回' },
        ],
        auditConclusion: '差异已查明',
      })
      switchTab('changeDetail')

      const json = toJSON()
      expect(json.activeTab).toBe('changeDetail')
      expect(json.selectedRowIndex).toBe(0)
      expect(json.items).toHaveLength(1)
      expect(json.items[0].securitiesName).toBe('测试债券')
      expect(json.items[0].reportDateQuantity).toBe(290) // 300-10
      expect(json.items[0].variance).toBe(10) // 290-280
      expect(json.items[0].varianceReason).toBe('到期赎回差异')
      expect(json.changeDetails).toHaveLength(1)
      expect(json.changeDetails[0].transactionType).toBe('sell')
      expect(json.changeDetails[0].handler).toBe('李四')
      expect(json.auditConclusion).toBe('差异已查明')
    })
  })
})
