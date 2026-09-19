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
import { useG6SppiReconciliation, CURRENT_FORMULA_VERSION, securityMatchKey } from '../useG6SppiReconciliation'
import type { ReconciliationData, ReconciliationItem } from '../useG6SppiReconciliation'
import { mapG62RowsToInventorySeeds } from '../g6CrossHelpers'
import {
  estimateG69VarianceAmount,
  buildG69VarianceAdjustmentDrafts,
  mergeG64EntriesWithG69Drafts,
} from '../g6CrossHelpers'
import type { G6AdjustmentEntry } from '../useG6MainAdjustment'

function withV2(data: Omit<ReconciliationData, 'formulaVersion'> & { formulaVersion?: number }): ReconciliationData {
  return { formulaVersion: CURRENT_FORMULA_VERSION, ...data }
}

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

  // ─── G6-2 同步 / 元数据 / 受限 ─────────────────────────────────────────────

  describe('mergeSeedsFromDetail + meta', () => {
    it('从 G6-2 种子新增并默认盘点数=账面数', () => {
      const { mergeSeedsFromDetail, items } = useG6SppiInventory()
      const { added, updated } = mergeSeedsFromDetail([
        { id: 's1', securitiesName: '国债A', securitiesCode: 'GZ1', faceValue: 1000, bookQuantity: 50, indexRef: 'G6-2' },
        { id: 's2', securitiesName: '企债B', faceValue: 500, bookQuantity: 0 },
      ])
      expect(added).toBe(2)
      expect(updated).toBe(0)
      expect(items.value[0].countQuantity).toBe(50)
      expect(items.value[0].bookQuantity).toBe(50)
      expect(items.value[0].indexRef).toBe('G6-2')
      expect(items.value[0].variance).toBe(0)
    })

    it('代码优先匹配已有行并补全面值/账面', () => {
      const { loadData, mergeSeedsFromDetail, items } = useG6SppiInventory()
      loadData({
        items: [{
          id: 'ex1', seq: 1, securitiesName: '旧名称', securitiesCode: 'CODE1',
          faceValue: 0, countQuantity: 0, bookQuantity: 0, variance: 0,
          varianceReason: '', varianceConclusion: '', indexRef: '',
          ownershipEntity: '', restrictionType: '', restrictionNote: '', evidenceIndex: '',
        }],
        auditConclusion: '',
      })
      const { added, updated } = mergeSeedsFromDetail([
        { securitiesName: '新名称', securitiesCode: 'CODE1', faceValue: 200, bookQuantity: 10 },
      ])
      expect(added).toBe(0)
      expect(updated).toBe(1)
      expect(items.value).toHaveLength(1)
      expect(items.value[0].faceValue).toBe(200)
      expect(items.value[0].bookQuantity).toBe(10)
      expect(items.value[0].countQuantity).toBe(10)
    })

    it('非报表日 needsRollForward=true；受限计数正确', () => {
      const { loadData, updateMeta, needsRollForward, restrictedCount, toJSON } = useG6SppiInventory()
      loadData({
        items: [{
          id: 'r1', seq: 1, securitiesName: '债X', securitiesCode: '',
          faceValue: 0, countQuantity: 1, bookQuantity: 1, variance: 0,
          varianceReason: '', varianceConclusion: '', indexRef: '',
          ownershipEntity: '公司A', restrictionType: 'pledge', restrictionNote: '质押融资',
          evidenceIndex: '对账单-1',
        }],
        auditConclusion: '',
        meta: { inventoryDate: '2025-01-15', isBalanceSheetDate: false, participants: '张三', custodyInstitution: '中债登', coverageNote: '全覆盖' },
      })
      expect(needsRollForward.value).toBe(true)
      expect(restrictedCount.value).toBe(1)
      updateMeta('isBalanceSheetDate', true)
      expect(needsRollForward.value).toBe(false)
      const json = toJSON()
      expect(json.meta?.custodyInstitution).toBe('中债登')
      expect(json.items[0].restrictionType).toBe('pledge')
    })
  })
})

describe('mapG62RowsToInventorySeeds', () => {
  it('映射名称/面值，并按代码优先、名称兜底去重', () => {
    const seeds = mapG62RowsToInventorySeeds([
      { id: '1', investProject: '国债A', faceValue: 1000, bookQuantity: 20, securitiesCode: 'GZ001' },
      { id: '2', investProject: '企债B', face_value: 500, quantity: 8 },
      { id: '3', investProject: '国债A', faceValue: 999, securitiesCode: 'GZ001' }, // 同代码去重
      { id: '4', investProject: '国债A', faceValue: 888 }, // 同名称去重（避免重复盘点行）
    ])
    expect(seeds).toHaveLength(2)
    expect(seeds[0].securitiesName).toBe('国债A')
    expect(seeds[0].securitiesCode).toBe('GZ001')
    expect(seeds[0].bookQuantity).toBe(20)
    expect(seeds[1].bookQuantity).toBe(8)
    expect(seeds[0].indexRef).toBe('G6-2')
  })

  it('读取 G6-2 正式字段 securitiesCode / bookQuantity', () => {
    const seeds = mapG62RowsToInventorySeeds([
      {
        id: 'g62-1',
        investProject: '农发债',
        securitiesCode: 'AF001',
        faceValue: 100,
        bookQuantity: 500,
      },
    ])
    expect(seeds).toEqual([
      {
        id: 'g62-1',
        securitiesName: '农发债',
        securitiesCode: 'AF001',
        faceValue: 100,
        bookQuantity: 500,
        indexRef: 'G6-2',
      },
    ])
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// useG6SppiReconciliation (G6-10 盘点倒轧表)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useG6SppiReconciliation', () => {
  // ─── 倒轧公式: reportDateQuantity = countDateQuantity - changeQuantity ────

  describe('reportDateQuantity = calcInventoryRollForward(countDateQuantity, changeQuantity)', () => {
    it('净增加为正: 盘点100 − 增减20 = 基准日80', () => {
      const { loadData, items } = useG6SppiReconciliation()
      loadData(withV2({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'r1', seq: 1, securitiesName: '债券X',
          countDateQuantity: 100, changeQuantity: 20, reportDateQuantity: 0,
          bookQuantity: 80, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
        auditConclusion: '',
      }))
      expect(items.value[0].reportDateQuantity).toBe(80)
    })

    it('净增加为负(净卖出): 盘点200 − 增减(-50) = 基准日250', () => {
      const { loadData, items } = useG6SppiReconciliation()
      loadData(withV2({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'r2', seq: 1, securitiesName: '债券Y',
          countDateQuantity: 200, changeQuantity: -50, reportDateQuantity: 0,
          bookQuantity: 250, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
        auditConclusion: '',
      }))
      expect(items.value[0].reportDateQuantity).toBe(250)
    })

    it('增减为0: 盘点日=基准日', () => {
      const { loadData, items } = useG6SppiReconciliation()
      loadData(withV2({
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
      }))
      expect(items.value[0].reportDateQuantity).toBe(500)
    })
  })


  // ─── 差异公式: variance = reportDateQuantity - bookQuantity ────────────────

  describe('variance = calcInventoryVariance(reportDateQuantity, bookQuantity)', () => {
    it('基准日 > 账面 → 正差异(多)', () => {
      const { loadData, items } = useG6SppiReconciliation()
      loadData(withV2({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'v1', seq: 1, securitiesName: 'A',
          countDateQuantity: 100, changeQuantity: -30, reportDateQuantity: 0,
          bookQuantity: 120, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
        auditConclusion: '',
      }))
      // reportDateQuantity = 100 - (-30) = 130, variance = 130 - 120 = 10
      expect(items.value[0].reportDateQuantity).toBe(130)
      expect(items.value[0].variance).toBe(10)
    })

    it('基准日 < 账面 → 负差异(少)', () => {
      const { loadData, items } = useG6SppiReconciliation()
      loadData(withV2({
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'v2', seq: 1, securitiesName: 'B',
          countDateQuantity: 80, changeQuantity: -10, reportDateQuantity: 0,
          bookQuantity: 100, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
        auditConclusion: '',
      }))
      // reportDateQuantity = 80 - (-10) = 90, variance = 90 - 100 = -10
      expect(items.value[0].reportDateQuantity).toBe(90)
      expect(items.value[0].variance).toBe(-10)
    })

    it('基准日 = 账面 → 差异为0', () => {
      const { loadData, items } = useG6SppiReconciliation()
      loadData(withV2({
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
      }))
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
            varianceConclusion: '拟调整', indexRef: '', remark: '' },
        ],
        changeDetails: [],
        auditConclusion: '',
      })
      // 行1差异=0不需填; 行2差异=10已填原因与结论 → valid
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
      expect(items.value[0].changeQuantity).toBe(20) // buy 20 自动汇总
      expect(items.value[0].reportDateQuantity).toBe(480)  // 500-20
      expect(items.value[0].variance).toBe(-40)  // 480-520
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
      loadData(withV2({
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
      }))
      switchTab('changeDetail')

      const json = toJSON()
      expect(json.activeTab).toBe('changeDetail')
      expect(json.selectedRowIndex).toBe(0)
      expect(json.items).toHaveLength(1)
      expect(json.items[0].securitiesName).toBe('测试债券')
      expect(json.items[0].changeQuantity).toBe(-10) // sell 10 → 净增加 -10
      expect(json.items[0].reportDateQuantity).toBe(310) // 300-(-10)
      expect(json.items[0].variance).toBe(30) // 310-280
      expect(json.items[0].varianceReason).toBe('到期赎回差异')
      expect(json.changeDetails).toHaveLength(1)
      expect(json.changeDetails[0].transactionType).toBe('sell')
      expect(json.changeDetails[0].handler).toBe('李四')
      expect(json.formulaVersion).toBe(CURRENT_FORMULA_VERSION)
      expect(json).not.toHaveProperty('auditConclusion')
    })
  })


  // ─── Tab2 自动汇总 + G6-9 带入 ─────────────────────────────────────────────

  describe('Tab2 自动汇总与 G6-9 带入', () => {
    it('买入为正、卖出为负，汇总到 changeQuantity 并重算基准日', async () => {
      const { loadData, items, changeDetails } = useG6SppiReconciliation()
      loadData({
        formulaVersion: CURRENT_FORMULA_VERSION,
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'a1', seq: 1, securitiesName: '债A',
          countDateQuantity: 1000, changeQuantity: 0, reportDateQuantity: 0,
          bookQuantity: 900, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
      })
      changeDetails.value.push(
        { id: 'd1', securitiesName: '债A', date: '2025-01-05', transactionType: 'buy', quantity: 200, amount: 0, voucherNo: '', handler: '', remark: '' },
        { id: 'd2', securitiesName: '债A', date: '2025-01-08', transactionType: 'sell', quantity: 100, amount: 0, voucherNo: '', handler: '', remark: '' },
      )
      await nextTick()
      expect(items.value[0].changeQuantity).toBe(100)
      expect(items.value[0].changeSource).toBe('detailDerived')
      expect(items.value[0].reportDateQuantity).toBe(900)
      expect(items.value[0].variance).toBe(0)
    })

    it('删除最后一条明细后自动清零 detailDerived 增减', async () => {
      const { loadData, items, changeDetails } = useG6SppiReconciliation()
      loadData({
        formulaVersion: CURRENT_FORMULA_VERSION,
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'a1', seq: 1, securitiesName: '债A',
          countDateQuantity: 1000, changeQuantity: 50, reportDateQuantity: 0,
          bookQuantity: 1000, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '', changeSource: 'detailDerived',
        }],
        changeDetails: [
          { id: 'd1', securitiesName: '债A', date: '2025-01-05', transactionType: 'buy', quantity: 50, amount: 0, voucherNo: '', handler: '', remark: '' },
        ],
      })
      expect(items.value[0].changeQuantity).toBe(50)
      changeDetails.value = []
      await nextTick()
      expect(items.value[0].changeQuantity).toBe(0)
      expect(items.value[0].changeSource).toBe('manual')
      expect(items.value[0].reportDateQuantity).toBe(1000)
    })

    it('importFromInventory 仅带入盘点日数量，不覆盖账面', () => {
      const { importFromInventory, items, loadData } = useG6SppiReconciliation()
      loadData({
        formulaVersion: CURRENT_FORMULA_VERSION,
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'e1', seq: 1, securitiesName: '国债A',
          countDateQuantity: 10, changeQuantity: 0, reportDateQuantity: 0,
          bookQuantity: 999, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
      })
      importFromInventory([
        { securitiesName: '国债A', securitiesCode: 'GZ1', countQuantity: 120, bookQuantity: 100, indexRef: 'G6-9' },
        { securitiesName: '新券B', securitiesCode: 'B2', countQuantity: 30, bookQuantity: 30, indexRef: 'G6-9' },
      ])
      expect(items.value.find(r => r.securitiesName === '国债A')!.countDateQuantity).toBe(120)
      expect(items.value.find(r => r.securitiesName === '国债A')!.bookQuantity).toBe(999)
      expect(items.value.find(r => r.securitiesName === '新券B')!.countDateQuantity).toBe(30)
      expect(items.value.find(r => r.securitiesName === '新券B')!.bookQuantity).toBe(0)
    })

    it('期前盘点顺推：基准日 = 盘点日 + 净增加', () => {
      const { loadData, items, updateHeader } = useG6SppiReconciliation()
      loadData({
        formulaVersion: CURRENT_FORMULA_VERSION,
        header: { countDate: '2024-12-20', balanceSheetDate: '2024-12-31' },
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'f1', seq: 1, securitiesName: 'F',
          countDateQuantity: 1000, changeQuantity: 100, reportDateQuantity: 0,
          bookQuantity: 1100, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
      })
      expect(items.value[0].reportDateQuantity).toBe(1100)
      updateHeader({ countDate: '2025-01-10', balanceSheetDate: '2024-12-31' })
      expect(items.value[0].reportDateQuantity).toBe(900)
    })

    it('旧口径 formulaVersion=1 手工增减取反迁移', () => {
      const { loadData, items, migratedFromLegacy } = useG6SppiReconciliation()
      loadData({
        formulaVersion: 1,
        changeConvention: 'legacy_count_to_bs_adjust',
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'l1', seq: 1, securitiesName: '旧债',
          countDateQuantity: 100, changeQuantity: -20, reportDateQuantity: 0,
          bookQuantity: 80, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
      })
      expect(migratedFromLegacy.value).toBe(true)
      // 旧 -20（逆向调整）→ 新净增加 +20；基准日 = 100 - 20 = 80
      expect(items.value[0].changeQuantity).toBe(20)
      expect(items.value[0].reportDateQuantity).toBe(80)
    })

    it('assertVarianceValidForSave 在差异未解释时返回 false', () => {
      const { loadData, assertVarianceValidForSave, isVarianceValid } = useG6SppiReconciliation()
      loadData({
        formulaVersion: CURRENT_FORMULA_VERSION,
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'x1', seq: 1, securitiesName: 'X',
          countDateQuantity: 110, changeQuantity: 0, reportDateQuantity: 0,
          bookQuantity: 100, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
      })
      expect(isVarianceValid.value).toBe(false)
      expect(assertVarianceValidForSave('保存审计结论')).toBe(false)
    })

    it('差异有原因但缺结论时仍不可保存', () => {
      const { loadData, isVarianceValid, isVarianceConclusionMissing, items } = useG6SppiReconciliation()
      loadData({
        formulaVersion: CURRENT_FORMULA_VERSION,
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'x2', seq: 1, securitiesName: 'Y',
          countDateQuantity: 110, changeQuantity: 0, reportDateQuantity: 0,
          bookQuantity: 100, variance: 0, varianceReason: '盘点未入账',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
      })
      expect(isVarianceConclusionMissing(items.value[0])).toBe(true)
      expect(isVarianceValid.value).toBe(false)
    })
  })

  // ─── P1: 匹配键汇总 + 明细校验 ─────────────────────────────────────────────

  describe('P1 匹配键与明细校验', () => {
    it('按证券代码汇总增减，名称不同也能匹配', async () => {
      const { loadData, items, changeDetails } = useG6SppiReconciliation()
      loadData({
        formulaVersion: CURRENT_FORMULA_VERSION,
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'c1', seq: 1, securitiesName: '国开债A', securitiesCode: '101001',
          countDateQuantity: 1000, changeQuantity: 0, reportDateQuantity: 0,
          bookQuantity: 1000, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
      })
      changeDetails.value.push({
        id: 'd1',
        securitiesName: '国开债A（别名）',
        securitiesCode: '101001',
        date: '2025-01-10',
        transactionType: 'buy',
        quantity: 80,
        amount: 0,
        voucherNo: 'V001',
        handler: '',
        remark: '',
      })
      await nextTick()
      expect(items.value[0].changeQuantity).toBe(80)
      expect(items.value[0].changeSource).toBe('detailDerived')
      expect(changeDetails.value[0].linkedItemId).toBe('c1')
    })

    it('转入为正、转出为负计入净增加', async () => {
      const { loadData, items, changeDetails } = useG6SppiReconciliation()
      loadData({
        formulaVersion: CURRENT_FORMULA_VERSION,
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 't1', seq: 1, securitiesName: '债T', securitiesCode: 'T001',
          countDateQuantity: 500, changeQuantity: 0, reportDateQuantity: 0,
          bookQuantity: 500, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
      })
      changeDetails.value.push(
        {
          id: 'd1', securitiesName: '债T', securitiesCode: 'T001',
          date: '2025-01-05', transactionType: 'transfer_in', quantity: 30,
          amount: 0, voucherNo: 'V1', handler: '', remark: '',
        },
        {
          id: 'd2', securitiesName: '债T', securitiesCode: 'T001',
          date: '2025-01-06', transactionType: 'transfer_out', quantity: 10,
          amount: 0, voucherNo: 'V2', handler: '', remark: '',
        },
      )
      await nextTick()
      expect(items.value[0].changeQuantity).toBe(20)
    })

    it('明细日期超出盘点日与资产负债表日区间时校验失败', async () => {
      const { loadData, changeDetails, detailValidationErrors, isVarianceValid, updateHeader } = useG6SppiReconciliation()
      loadData({
        formulaVersion: CURRENT_FORMULA_VERSION,
        header: { countDate: '2025-01-15', balanceSheetDate: '2024-12-31' },
        activeTab: 'changeDetail',
        selectedRowIndex: 0,
        items: [{
          id: 'a1', seq: 1, securitiesName: '债A',
          countDateQuantity: 100, changeQuantity: 0, reportDateQuantity: 0,
          bookQuantity: 100, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
      })
      updateHeader({ countDate: '2025-01-15', balanceSheetDate: '2024-12-31' })
      changeDetails.value.push({
        id: 'd1',
        securitiesName: '债A',
        date: '2025-02-01',
        transactionType: 'buy',
        quantity: 10,
        amount: 0,
        voucherNo: 'V1',
        handler: '',
        remark: '',
      })
      await nextTick()
      expect(detailValidationErrors.value.length).toBeGreaterThan(0)
      expect(detailValidationErrors.value[0].reasons.some((r) => r.includes('之间'))).toBe(true)
      expect(isVarianceValid.value).toBe(false)
    })

    it('securityMatchKey 优先代码再来源ID再名称', () => {
      expect(securityMatchKey({ securitiesCode: ' ab 01 ', securitiesName: 'X' })).toBe('code:AB01')
      expect(securityMatchKey({ sourceItemId: 'src-9', securitiesName: 'X' })).toBe('src:src-9')
      expect(securityMatchKey({ securitiesName: ' 国开 债 ' })).toBe('name:国开债')
    })

    it('linkedItemId 优先匹配，加载后自动重绑', async () => {
      const { loadData, items, changeDetails } = useG6SppiReconciliation()
      loadData({
        formulaVersion: CURRENT_FORMULA_VERSION,
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [
          {
            id: 'row-a', seq: 1, securitiesName: '债A', securitiesCode: 'A001',
            countDateQuantity: 100, changeQuantity: 0, reportDateQuantity: 0,
            bookQuantity: 100, variance: 0, varianceReason: '',
            varianceConclusion: '', indexRef: '', remark: '',
          },
          {
            id: 'row-b', seq: 2, securitiesName: '债B', securitiesCode: 'B001',
            countDateQuantity: 200, changeQuantity: 0, reportDateQuantity: 0,
            bookQuantity: 200, variance: 0, varianceReason: '',
            varianceConclusion: '', indexRef: '', remark: '',
          },
        ],
        changeDetails: [{
          id: 'd1',
          securitiesName: '债B', // 名称指向 B
          securitiesCode: '',
          linkedItemId: 'row-a', // 但明确关联 A
          date: '2025-01-05',
          transactionType: 'buy',
          quantity: 15,
          amount: 0,
          voucherNo: 'V1',
          handler: '',
          remark: '',
        }],
      })
      await nextTick()
      expect(items.value[0].changeQuantity).toBe(15)
      expect(items.value[1].changeQuantity).toBe(0)
      expect(changeDetails.value[0].linkedItemId).toBe('row-a')
      expect(changeDetails.value[0].securitiesCode).toBe('A001')
    })

    it('importBookFromSeeds 只更新账面数量，不改盘点日数量', () => {
      const { loadData, importBookFromSeeds, items } = useG6SppiReconciliation()
      loadData({
        formulaVersion: CURRENT_FORMULA_VERSION,
        activeTab: 'rollForward',
        selectedRowIndex: 0,
        items: [{
          id: 'e1', seq: 1, securitiesName: '国债A', securitiesCode: '101001',
          countDateQuantity: 88, changeQuantity: 0, reportDateQuantity: 0,
          bookQuantity: 10, variance: 0, varianceReason: '',
          varianceConclusion: '', indexRef: '', remark: '',
        }],
        changeDetails: [],
      })
      const r = importBookFromSeeds([
        { securitiesName: '国债A', securitiesCode: '101001', bookQuantity: 100 },
      ], 'G6-2')
      expect(r.updated).toBe(1)
      expect(items.value[0].bookQuantity).toBe(100)
      expect(items.value[0].countDateQuantity).toBe(88)
      expect(items.value[0].reportDateQuantity).toBe(88)
      expect(items.value[0].variance).toBe(-12)
    })

    it('空表时 importBookFromSeeds 不新增行', () => {
      const { importBookFromSeeds, items } = useG6SppiReconciliation()
      const r = importBookFromSeeds([
        { securitiesName: '债X', bookQuantity: 50 },
      ], 'G6-2')
      expect(r.updated).toBe(0)
      expect(items.value).toHaveLength(0)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// G6-9 → G6-4 调整草稿
// ═══════════════════════════════════════════════════════════════════════════════

describe('G6-9 → G6-4 调整草稿', () => {
  it('estimateG69VarianceAmount：面值/账面数量估算单位成本', () => {
    const est = estimateG69VarianceAmount({
      variance: 10,
      faceValue: 1000,
      bookQuantity: 100,
    })
    expect(est.amount).toBe(100)
    expect(est.basis).toContain('单位面值')
  })

  it('buildG69VarianceAdjustmentDrafts：盘盈生成借成本贷投资收益', () => {
    const { pairs, skipped } = buildG69VarianceAdjustmentDrafts([
      {
        id: 's1',
        securitiesName: '国债A',
        securitiesCode: 'GZ1',
        variance: 20,
        faceValue: 1000,
        bookQuantity: 100,
        varianceConclusion: '拟调整入账',
      },
    ])
    expect(skipped).toHaveLength(0)
    expect(pairs).toHaveLength(1)
    expect(pairs[0].direction).toBe('surplus')
    expect(pairs[0].amount).toBe(200)
    const [dr, cr] = pairs[0].entries
    expect(dr.accountCode).toBe('150301')
    expect(dr.debitAmount).toBe(200)
    expect(cr.accountCode).toBe('6111')
    expect(cr.creditAmount).toBe(200)
    expect(dr.id).toBe('g69-s1-dr')
    expect(cr.id).toBe('g69-s1-cr')
  })

  it('buildG69VarianceAdjustmentDrafts：盘亏借贷方向相反', () => {
    const { pairs } = buildG69VarianceAdjustmentDrafts([
      {
        id: 's2',
        securitiesName: '企债B',
        variance: -5,
        faceValue: 500,
        bookQuantity: 50,
        varianceConclusion: '拟调整',
      },
    ], { onlyProposedAdjust: true })
    expect(pairs[0].direction).toBe('shortage')
    const [cost, income] = pairs[0].entries
    expect(cost.id).toBe('g69-s2-cr')
    expect(cost.creditAmount).toBe(50)
    expect(income.id).toBe('g69-s2-dr')
    expect(income.debitAmount).toBe(50)
  })

  it('onlyProposedAdjust 默认跳过未标注拟调整的行', () => {
    const { pairs, skipped } = buildG69VarianceAdjustmentDrafts([
      {
        id: 's3',
        securitiesName: '观察项',
        variance: 3,
        faceValue: 300,
        bookQuantity: 30,
        varianceConclusion: '待查',
      },
    ])
    expect(pairs).toHaveLength(0)
    expect(skipped[0].reason).toContain('拟调整')
  })

  it('mergeG64EntriesWithG69Drafts：同 sourceId 旧草稿被替换', () => {
    const existing: G6AdjustmentEntry[] = [
      {
        id: 'keep-1', rowId: 'keep-1', seq: 1, description: '其他', category: '账项调整',
        reportItem: '其他债权投资', accountCode: '1503', accountName: '其他债权投资',
        noteItem: '', debitAmount: 1, creditAmount: 0, indexRef: 'G6-4', remark: '',
        entryType: 'AJE', date: '', summary: '其他', preparedBy: '',
      },
      {
        id: 'g69-s1-dr', rowId: 'g69-s1-dr', seq: 2, description: '旧草稿', category: '账项调整',
        reportItem: '其他债权投资', accountCode: '150301', accountName: '成本',
        noteItem: '', debitAmount: 99, creditAmount: 0, indexRef: 'G6-9',
        remark: 'source=G6-9;sourceId=s1', entryType: 'AJE', date: '', summary: '旧草稿', preparedBy: '',
      },
    ]
    const { pairs } = buildG69VarianceAdjustmentDrafts([
      {
        id: 's1',
        securitiesName: '国债A',
        variance: 10,
        faceValue: 1000,
        bookQuantity: 100,
        varianceConclusion: '拟调整',
      },
    ])
    const merged = mergeG64EntriesWithG69Drafts(existing, pairs)
    expect(merged.find((e) => e.id === 'keep-1')).toBeTruthy()
    expect(merged.filter((e) => e.remark?.includes('sourceId=s1'))).toHaveLength(2)
    expect(merged.find((e) => e.id === 'g69-s1-dr')?.debitAmount).toBe(100)
  })
})
