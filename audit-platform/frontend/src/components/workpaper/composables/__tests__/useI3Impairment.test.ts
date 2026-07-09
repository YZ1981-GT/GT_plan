/**
 * useI3Impairment — 单元测试
 *
 * 验证：
 * 1. CGU行添加/删除
 * 2. cguBookValue = goodwill + Σ(otherAssets)
 * 3. impairmentAmount = MAX(bookValue - recoverable, 0)
 * 4. 先冲商誉逻辑：goodwillImpairment = MIN(impairment, goodwill)
 * 5. 剩余减值按比例分摊
 * 6. 商誉减值不可转回（不允许负数）
 * 7. 合计行正确性
 * 8. I3-7 联动
 *
 * Spec: .kiro/specs/i3-goodwill/
 * Task: 3.5
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed, nextTick } from 'vue'
import { useI3Impairment, type CguRow } from '../useI3Impairment'
import type { ChecklistItem } from '../useI3FormData'

// Helper：创建 allResponses ref
function createAllResponses(data?: Record<string, any>) {
  const map = new Map<string, ChecklistItem>()
  if (data) {
    for (const [key, value] of Object.entries(data)) {
      map.set(key, {
        item_id: key,
        conclusion: null,
        remark: typeof value === 'string' ? value : JSON.stringify(value),
      })
    }
  }
  return ref(map)
}

describe('useI3Impairment', () => {
  let wpId: ReturnType<typeof ref<string>>
  let allResponses: ReturnType<typeof createAllResponses>
  let onSave: ReturnType<typeof vi.fn>

  beforeEach(() => {
    wpId = ref('wp-test-123')
    allResponses = createAllResponses()
    onSave = vi.fn()
  })

  describe('初始化', () => {
    it('空数据时 cguRows 为空数组', () => {
      const { cguRows } = useI3Impairment(wpId, allResponses, { onSave })
      expect(cguRows.value).toEqual([])
    })

    it('从 allResponses 加载已有CGU行', () => {
      const existingRows = [
        {
          rowId: 'cgu-1',
          cguName: 'CGU-A',
          goodwillAmount: 1000000,
          otherAssets: [{ name: '固定资产', bookValue: 2000000 }],
          recoverableAmount: 2500000,
        },
      ]
      allResponses = createAllResponses({ 'I3-6-rows': existingRows })
      const { cguRows } = useI3Impairment(wpId, allResponses, { onSave })

      expect(cguRows.value).toHaveLength(1)
      expect(cguRows.value[0].cguName).toBe('CGU-A')
      expect(cguRows.value[0].goodwillAmount).toBe(1000000)
      // cguBookValue = 1000000 + 2000000 = 3000000
      expect(cguRows.value[0].cguBookValue).toBe(3000000)
      // impairment = MAX(3000000 - 2500000, 0) = 500000
      expect(cguRows.value[0].impairmentAmount).toBe(500000)
      // goodwillImpairment = MIN(500000, 1000000) = 500000
      expect(cguRows.value[0].goodwillImpairment).toBe(500000)
    })
  })

  describe('CGU行管理', () => {
    it('addCguRow 添加并计算', () => {
      const { cguRows, addCguRow } = useI3Impairment(wpId, allResponses, { onSave })

      const row = addCguRow({
        cguName: 'CGU-B',
        goodwillAmount: 500000,
        otherAssets: [
          { name: '固定资产', bookValue: 1000000 },
          { name: '无形资产', bookValue: 500000 },
        ],
        recoverableAmount: 1800000,
      })

      expect(cguRows.value).toHaveLength(1)
      // cguBookValue = 500000 + 1000000 + 500000 = 2000000
      expect(row.cguBookValue).toBe(2000000)
      // impairment = MAX(2000000 - 1800000, 0) = 200000
      expect(row.impairmentAmount).toBe(200000)
      // goodwillImpairment = MIN(200000, 500000) = 200000（全部由商誉承担）
      expect(row.goodwillImpairment).toBe(200000)
      // 其他资产分摊 = 0（商誉已全部吸收）
      expect(row.otherAllocations.every(a => a.amount === 0)).toBe(true)
      expect(onSave).toHaveBeenCalledWith('I3-6-rows', expect.any(Array))
    })

    it('removeCguRow 删除正确', () => {
      const { cguRows, addCguRow, removeCguRow } = useI3Impairment(wpId, allResponses, { onSave })

      addCguRow({ cguName: 'CGU-A', goodwillAmount: 100 })
      addCguRow({ cguName: 'CGU-B', goodwillAmount: 200 })
      expect(cguRows.value).toHaveLength(2)

      removeCguRow(0)
      expect(cguRows.value).toHaveLength(1)
      expect(cguRows.value[0].cguName).toBe('CGU-B')
    })

    it('removeCguRow 越界不报错', () => {
      const { cguRows, removeCguRow } = useI3Impairment(wpId, allResponses, { onSave })
      removeCguRow(-1)
      removeCguRow(999)
      expect(cguRows.value).toHaveLength(0)
    })
  })

  describe('先冲商誉再分摊 (CAS8两步法)', () => {
    it('减值 ≤ 商誉时：全部由商誉承担，其他资产不分摊', () => {
      const { addCguRow } = useI3Impairment(wpId, allResponses, { onSave })

      const row = addCguRow({
        cguName: 'CGU-A',
        goodwillAmount: 1000000,
        otherAssets: [
          { name: '固定资产', bookValue: 3000000 },
          { name: '无形资产', bookValue: 2000000 },
        ],
        recoverableAmount: 5500000, // bookValue=6000000, impairment=500000
      })

      expect(row.impairmentAmount).toBe(500000)
      expect(row.goodwillImpairment).toBe(500000) // 全部由商誉承担
      expect(row.otherAllocations).toEqual([
        { name: '固定资产', amount: 0 },
        { name: '无形资产', amount: 0 },
      ])
    })

    it('减值 > 商誉时：商誉冲零，剩余按比例分摊', () => {
      const { addCguRow } = useI3Impairment(wpId, allResponses, { onSave })

      const row = addCguRow({
        cguName: 'CGU-B',
        goodwillAmount: 300000,
        otherAssets: [
          { name: '固定资产', bookValue: 600000 },  // 比例 60%
          { name: '无形资产', bookValue: 400000 },  // 比例 40%
        ],
        recoverableAmount: 800000, // bookValue=1300000, impairment=500000
      })

      expect(row.impairmentAmount).toBe(500000)
      // 商誉先冲: MIN(500000, 300000) = 300000
      expect(row.goodwillImpairment).toBe(300000)
      // 剩余: 500000 - 300000 = 200000
      // 固定资产分摊: 200000 * (600000/1000000) = 120000
      // 无形资产分摊: 200000 * (400000/1000000) = 80000
      expect(row.otherAllocations[0].amount).toBeCloseTo(120000, 2)
      expect(row.otherAllocations[1].amount).toBeCloseTo(80000, 2)
    })

    it('可收回金额 ≥ 资产组账面：无减值', () => {
      const { addCguRow } = useI3Impairment(wpId, allResponses, { onSave })

      const row = addCguRow({
        cguName: 'CGU-C',
        goodwillAmount: 500000,
        otherAssets: [{ name: '固定资产', bookValue: 1000000 }],
        recoverableAmount: 2000000, // > bookValue 1500000
      })

      expect(row.impairmentAmount).toBe(0)
      expect(row.goodwillImpairment).toBe(0)
      expect(row.otherAllocations).toEqual([{ name: '固定资产', amount: 0 }])
    })

    it('商誉为0时：全部分摊至其他资产', () => {
      const { addCguRow } = useI3Impairment(wpId, allResponses, { onSave })

      const row = addCguRow({
        cguName: 'CGU-D',
        goodwillAmount: 0,
        otherAssets: [
          { name: '固定资产', bookValue: 800000 },
          { name: '无形资产', bookValue: 200000 },
        ],
        recoverableAmount: 700000, // bookValue=1000000, impairment=300000
      })

      expect(row.impairmentAmount).toBe(300000)
      expect(row.goodwillImpairment).toBe(0)
      // 800000/1000000 * 300000 = 240000
      // 200000/1000000 * 300000 = 60000
      expect(row.otherAllocations[0].amount).toBeCloseTo(240000, 2)
      expect(row.otherAllocations[1].amount).toBeCloseTo(60000, 2)
    })
  })

  describe('字段更新', () => {
    it('updateGoodwillAmount 触发重算', () => {
      const { cguRows, addCguRow, updateGoodwillAmount } = useI3Impairment(wpId, allResponses, { onSave })

      addCguRow({
        cguName: 'CGU-A',
        goodwillAmount: 1000000,
        otherAssets: [{ name: '固定资产', bookValue: 2000000 }],
        recoverableAmount: 2500000,
      })

      // 初始: bookValue=3000000, impairment=500000, gwImpairment=500000
      expect(cguRows.value[0].impairmentAmount).toBe(500000)

      updateGoodwillAmount(0, 2000000)
      // 新: bookValue=4000000, impairment=1500000, gwImpairment=MIN(1500000,2000000)=1500000
      expect(cguRows.value[0].cguBookValue).toBe(4000000)
      expect(cguRows.value[0].impairmentAmount).toBe(1500000)
      expect(cguRows.value[0].goodwillImpairment).toBe(1500000)
    })

    it('updateRecoverableAmount 触发重算', () => {
      const { cguRows, addCguRow, updateRecoverableAmount } = useI3Impairment(wpId, allResponses, { onSave })

      addCguRow({
        cguName: 'CGU-A',
        goodwillAmount: 500000,
        otherAssets: [{ name: '固定资产', bookValue: 1500000 }],
        recoverableAmount: 3000000, // no impairment
      })

      expect(cguRows.value[0].impairmentAmount).toBe(0)

      updateRecoverableAmount(0, 1000000)
      // bookValue=2000000, recoverable=1000000, impairment=1000000
      expect(cguRows.value[0].impairmentAmount).toBe(1000000)
      // goodwillImpairment = MIN(1000000, 500000) = 500000
      expect(cguRows.value[0].goodwillImpairment).toBe(500000)
    })

    it('updateGoodwillAmount 负值被修正为0', () => {
      const { cguRows, addCguRow, updateGoodwillAmount } = useI3Impairment(wpId, allResponses, { onSave })
      addCguRow({ cguName: 'CGU-A', goodwillAmount: 100 })
      updateGoodwillAmount(0, -500)
      expect(cguRows.value[0].goodwillAmount).toBe(0)
    })
  })

  describe('其他资产管理', () => {
    it('addOtherAsset 添加并重算', () => {
      const { cguRows, addCguRow, addOtherAsset } = useI3Impairment(wpId, allResponses, { onSave })

      addCguRow({
        cguName: 'CGU-A',
        goodwillAmount: 100000,
        recoverableAmount: 50000,
      })
      // 初始: bookValue=100000, impairment=50000

      addOtherAsset(0, { name: '存货', bookValue: 200000 })
      // 新: bookValue=300000, impairment=250000
      expect(cguRows.value[0].cguBookValue).toBe(300000)
      expect(cguRows.value[0].impairmentAmount).toBe(250000)
    })

    it('removeOtherAsset 删除并重算', () => {
      const { cguRows, addCguRow, removeOtherAsset } = useI3Impairment(wpId, allResponses, { onSave })

      addCguRow({
        cguName: 'CGU-A',
        goodwillAmount: 100000,
        otherAssets: [
          { name: '固定资产', bookValue: 200000 },
          { name: '无形资产', bookValue: 300000 },
        ],
        recoverableAmount: 400000,
      })
      // bookValue=600000, impairment=200000

      removeOtherAsset(0, 1) // 删除无形资产
      // bookValue=300000, impairment=0 (recoverable 400000 > bookValue 300000)
      expect(cguRows.value[0].cguBookValue).toBe(300000)
      expect(cguRows.value[0].impairmentAmount).toBe(0)
    })

    it('updateOtherAsset 更新并重算', () => {
      const { cguRows, addCguRow, updateOtherAsset } = useI3Impairment(wpId, allResponses, { onSave })

      addCguRow({
        cguName: 'CGU-A',
        goodwillAmount: 100000,
        otherAssets: [{ name: '固定资产', bookValue: 200000 }],
        recoverableAmount: 250000,
      })
      // bookValue=300000, impairment=50000

      updateOtherAsset(0, 0, 'bookValue', 500000)
      // bookValue=600000, impairment=350000
      expect(cguRows.value[0].cguBookValue).toBe(600000)
      expect(cguRows.value[0].impairmentAmount).toBe(350000)
    })
  })

  describe('合计行 (cguSummary)', () => {
    it('多个CGU行正确汇总', () => {
      const { cguSummary, addCguRow } = useI3Impairment(wpId, allResponses, { onSave })

      addCguRow({
        cguName: 'CGU-A',
        goodwillAmount: 1000000,
        otherAssets: [{ name: '固定资产', bookValue: 2000000 }],
        recoverableAmount: 2500000, // impairment=500000, gwImpairment=500000
      })
      addCguRow({
        cguName: 'CGU-B',
        goodwillAmount: 500000,
        otherAssets: [{ name: '无形资产', bookValue: 1500000 }],
        recoverableAmount: 1000000, // impairment=1000000, gwImpairment=500000, other=500000
      })

      expect(cguSummary.value.totalGoodwill).toBe(1500000)
      expect(cguSummary.value.totalOtherAssets).toBe(3500000)
      expect(cguSummary.value.totalCguBookValue).toBe(5000000)
      expect(cguSummary.value.totalRecoverable).toBe(3500000)
      expect(cguSummary.value.totalImpairment).toBe(1500000)
      expect(cguSummary.value.totalGoodwillImpairment).toBe(1000000)
      expect(cguSummary.value.totalOtherImpairment).toBe(500000)
    })
  })

  describe('totalGoodwillImpairment (供审定表)', () => {
    it('返回所有CGU商誉减值之和', () => {
      const { totalGoodwillImpairment, addCguRow } = useI3Impairment(wpId, allResponses, { onSave })

      addCguRow({
        cguName: 'CGU-A',
        goodwillAmount: 1000000,
        otherAssets: [{ name: '固定资产', bookValue: 2000000 }],
        recoverableAmount: 2500000, // gwImpairment=500000
      })
      addCguRow({
        cguName: 'CGU-B',
        goodwillAmount: 300000,
        otherAssets: [],
        recoverableAmount: 100000, // gwImpairment=200000 (=MIN(200000, 300000))
      })

      expect(totalGoodwillImpairment.value).toBe(700000)
    })
  })

  describe('I3-7 联动 (syncRecoverableFromI3_7)', () => {
    it('按CGU名称匹配更新可收回金额', () => {
      const recoverableByCgu = computed(() => ({
        'CGU-A': 2000000,
        'CGU-B': 800000,
      }))

      const existingRows = [
        { cguName: 'CGU-A', goodwillAmount: 500000, otherAssets: [{ name: '固定资产', bookValue: 2000000 }], recoverableAmount: 9999999 },
        { cguName: 'CGU-B', goodwillAmount: 300000, otherAssets: [{ name: '无形资产', bookValue: 1000000 }], recoverableAmount: 9999999 },
      ]
      allResponses = createAllResponses({ 'I3-6-rows': existingRows })

      const { cguRows, syncRecoverableFromI3_7 } = useI3Impairment(
        wpId,
        allResponses,
        { onSave, recoverableByCgu },
      )

      // 初始时 recoverable 来自持久化值
      syncRecoverableFromI3_7()

      // CGU-A: bookValue=2500000, recoverable=2000000, impairment=500000
      expect(cguRows.value[0].recoverableAmount).toBe(2000000)
      expect(cguRows.value[0].impairmentAmount).toBe(500000)
      expect(cguRows.value[0].goodwillImpairment).toBe(500000)

      // CGU-B: bookValue=1300000, recoverable=800000, impairment=500000
      expect(cguRows.value[1].recoverableAmount).toBe(800000)
      expect(cguRows.value[1].impairmentAmount).toBe(500000)
      // goodwillImpairment = MIN(500000, 300000) = 300000
      expect(cguRows.value[1].goodwillImpairment).toBe(300000)
    })
  })

  describe('impairedRowIds (高亮)', () => {
    it('仅减值>0的行被标记', () => {
      const { impairedRowIds, addCguRow } = useI3Impairment(wpId, allResponses, { onSave })

      const rowA = addCguRow({
        cguName: 'CGU-A',
        goodwillAmount: 100000,
        recoverableAmount: 50000, // impairment=50000
      })
      const rowB = addCguRow({
        cguName: 'CGU-B',
        goodwillAmount: 100000,
        recoverableAmount: 200000, // no impairment
      })

      expect(impairedRowIds.value.has(rowA.rowId)).toBe(true)
      expect(impairedRowIds.value.has(rowB.rowId)).toBe(false)
    })
  })

  describe('Import/Export', () => {
    it('exportCguRows 返回当前数据副本', () => {
      const { addCguRow, exportCguRows } = useI3Impairment(wpId, allResponses, { onSave })

      addCguRow({ cguName: 'CGU-A', goodwillAmount: 100 })
      const exported = exportCguRows()
      expect(exported).toHaveLength(1)
      expect(exported[0].cguName).toBe('CGU-A')
    })

    it('importCguRows 覆盖并重算', () => {
      const { cguRows, addCguRow, importCguRows } = useI3Impairment(wpId, allResponses, { onSave })

      addCguRow({ cguName: 'CGU-OLD', goodwillAmount: 100 })

      importCguRows([
        { cguName: 'CGU-NEW', goodwillAmount: 500000, otherAssets: [{ name: '机器', bookValue: 1000000 }], recoverableAmount: 1200000 },
      ])

      expect(cguRows.value).toHaveLength(1)
      expect(cguRows.value[0].cguName).toBe('CGU-NEW')
      expect(cguRows.value[0].cguBookValue).toBe(1500000)
      expect(cguRows.value[0].impairmentAmount).toBe(300000)
    })
  })
})
