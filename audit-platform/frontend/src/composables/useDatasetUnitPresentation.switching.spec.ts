/**
 * 数据集单位展示层切换夹具测试。
 *
 * 验证：
 * - 数据集切换（normalized → legacy_declared → legacy_unknown）
 * - 页面切换（模拟 Ledger → TrialBalance → 回到 Ledger，各自独立）
 * - 账号切换后，元数据标签和显示单位彼此独立
 */

import { describe, it, expect } from 'vitest'
import { ref, nextTick, computed } from 'vue'
import {
  useDatasetUnitPresentation,
  type DatasetUnitClass,
} from './useDatasetUnitPresentation'
import { classifyDatasetUnit } from './classifyDatasetUnit'

// ── 辅助构造器 ──────────────────────────────────────────────────────

function makeNormalizedSummary(factor: number = 10000): Record<string, unknown> {
  return {
    amount_unit: '万元',
    unit_normalization: {
      contract: {
        source_unit: 'wan',
        storage_unit: 'yuan',
        factor,
        contract_digest: 'a'.repeat(64),
      },
    },
  }
}

function makeLegacySummary(unit: string = '万元'): Record<string, unknown> {
  return { amount_unit: unit }
}

function makeUnknownSummary(): Record<string, unknown> {
  return { files: ['a.xlsx'] }
}

describe('数据集单位展示切换夹具', () => {
  // ── 数据集切换 ─────────────────────────────────────────────────────

  describe('数据集切换（normalized → legacy_declared → legacy_unknown）', () => {
    it('三类依次切换后 label 正确跟随', async () => {
      const summary = ref<Record<string, unknown> | null>(makeNormalizedSummary())
      const cls = computed<DatasetUnitClass>(() => classifyDatasetUnit(summary.value))
      const { label, storageUnit, factor } = useDatasetUnitPresentation(cls, summary)

      // 初始：normalized_v1
      expect(label.value).toBe('存储单位：元')
      expect(storageUnit.value).toBe('yuan')
      expect(factor.value).toBe(10000)

      // 切到 legacy_declared
      summary.value = makeLegacySummary('千元')
      await nextTick()
      expect(label.value).toBe('历史声明：千元')
      expect(storageUnit.value).toBeNull()
      expect(factor.value).toBeNull()

      // 切到 legacy_unknown
      summary.value = makeUnknownSummary()
      await nextTick()
      expect(label.value).toBe('单位未确认')
      expect(storageUnit.value).toBeNull()
      expect(factor.value).toBeNull()
    })

    it('从 unknown 切回 normalized 恢复因子', async () => {
      const summary = ref<Record<string, unknown> | null>(makeUnknownSummary())
      const cls = computed<DatasetUnitClass>(() => classifyDatasetUnit(summary.value))
      const { label, factor } = useDatasetUnitPresentation(cls, summary)

      expect(label.value).toBe('单位未确认')

      summary.value = makeNormalizedSummary(1000)
      await nextTick()
      expect(label.value).toBe('存储单位：元')
      expect(factor.value).toBe(1000)
    })
  })

  // ── 页面切换（各 composable 实例独立）──────────────────────────────

  describe('页面切换模拟（Ledger 与 TrialBalance 独立实例）', () => {
    it('两个 composable 实例互不影响', async () => {
      // 模拟 Ledger 页有 normalized 数据集
      const ledgerSummary = ref<Record<string, unknown> | null>(makeNormalizedSummary())
      const ledgerCls = computed<DatasetUnitClass>(() => classifyDatasetUnit(ledgerSummary.value))
      const ledger = useDatasetUnitPresentation(ledgerCls, ledgerSummary)

      // 模拟 TrialBalance 页有 legacy 数据集
      const tbSummary = ref<Record<string, unknown> | null>(makeLegacySummary('元'))
      const tbCls = computed<DatasetUnitClass>(() => classifyDatasetUnit(tbSummary.value))
      const tb = useDatasetUnitPresentation(tbCls, tbSummary)

      // 各自独立
      expect(ledger.label.value).toBe('存储单位：元')
      expect(ledger.factor.value).toBe(10000)
      expect(tb.label.value).toBe('历史声明：元')
      expect(tb.factor.value).toBeNull()

      // 改变 Ledger 不影响 TB
      ledgerSummary.value = makeUnknownSummary()
      await nextTick()
      expect(ledger.label.value).toBe('单位未确认')
      expect(tb.label.value).toBe('历史声明：元') // 不变
    })

    it('切回同一页面保持上次分类', async () => {
      // 模拟离开页面再回来：ref 保持原值
      const summary = ref<Record<string, unknown> | null>(makeNormalizedSummary(1000))
      const cls = computed<DatasetUnitClass>(() => classifyDatasetUnit(summary.value))
      const { label, factor } = useDatasetUnitPresentation(cls, summary)

      expect(label.value).toBe('存储单位：元')
      expect(factor.value).toBe(1000)

      // 模拟离开（不清 ref）再创建新 composable 实例
      const cls2 = computed<DatasetUnitClass>(() => classifyDatasetUnit(summary.value))
      const second = useDatasetUnitPresentation(cls2, summary)
      expect(second.label.value).toBe('存储单位：元')
      expect(second.factor.value).toBe(1000)
    })
  })

  // ── 账号切换后独立性 ──────────────────────────────────────────────

  describe('账号切换后元数据标签独立', () => {
    it('切换账号后数据集状态不残留', async () => {
      // 账号 A 看到 normalized 数据集
      const summary = ref<Record<string, unknown> | null>(makeNormalizedSummary())
      const cls = computed<DatasetUnitClass>(() => classifyDatasetUnit(summary.value))
      const { label, storageUnit, factor } = useDatasetUnitPresentation(cls, summary)

      expect(label.value).toBe('存储单位：元')
      expect(storageUnit.value).toBe('yuan')

      // 切换账号：清空数据集 summary（模拟组件 unmount/清空）
      summary.value = null
      await nextTick()

      // 账号 B 没有数据集 → label 降级
      expect(label.value).toBe('单位未确认')
      expect(storageUnit.value).toBeNull()
      expect(factor.value).toBeNull()

      // 账号 B 加载了一个 legacy 数据集
      summary.value = makeLegacySummary('元')
      await nextTick()
      expect(label.value).toBe('历史声明：元')
      expect(storageUnit.value).toBeNull()
    })

    it('数据集元数据标签与显示单位偏好彼此独立', () => {
      // 数据集元数据状态
      const summary = ref<Record<string, unknown> | null>(makeLegacySummary('万元'))
      const cls = computed<DatasetUnitClass>(() => classifyDatasetUnit(summary.value))
      const { label, storageUnit } = useDatasetUnitPresentation(cls, summary)

      // 显示单位（模拟由 displayPrefs store 驱动）
      const userDisplayUnit = ref<string>('qian') // 用户选千元

      // 两者互不影响
      expect(label.value).toBe('历史声明：万元') // 数据集元数据
      expect(userDisplayUnit.value).toBe('qian') // 用户偏好
      expect(storageUnit.value).toBeNull() // legacy 无存储单位

      // 切用户偏好不影响数据集 label
      userDisplayUnit.value = 'wan'
      expect(label.value).toBe('历史声明：万元') // 不变
    })
  })

  // ── classifyDatasetUnit 前端分类器 ─────────────────────────────────

  describe('classifyDatasetUnit 前端分类器', () => {
    it('与后端同口径：normalized_v1', () => {
      expect(classifyDatasetUnit(makeNormalizedSummary())).toBe('normalized_v1')
    })

    it('与后端同口径：legacy_declared', () => {
      expect(classifyDatasetUnit(makeLegacySummary())).toBe('legacy_declared')
    })

    it('与后端同口径：legacy_unknown', () => {
      expect(classifyDatasetUnit(null)).toBe('legacy_unknown')
      expect(classifyDatasetUnit({})).toBe('legacy_unknown')
      expect(classifyDatasetUnit(makeUnknownSummary())).toBe('legacy_unknown')
    })

    it('unit_normalization 无效但有 amount_unit → fail-closed legacy_unknown', () => {
      const summary = {
        amount_unit: '万元',
        unit_normalization: { contract: {} },
      }
      expect(classifyDatasetUnit(summary)).toBe('legacy_unknown')
    })
  })
})
