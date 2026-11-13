/**
 * useDatasetUnitPresentation 的 vitest 测试。
 *
 * 覆盖三种分类的 label / storageUnit / factor，
 * 以及分类动态切换时响应式更新。
 */

import { describe, it, expect } from 'vitest'
import { ref, nextTick } from 'vue'
import {
  useDatasetUnitPresentation,
  type DatasetUnitClass,
} from './useDatasetUnitPresentation'

describe('useDatasetUnitPresentation', () => {
  // ── normalized_v1 ─────────────────────────────────────────────────

  describe('normalized_v1', () => {
    it('返回存储单位标签、yuan 和因子', () => {
      const classification = ref<DatasetUnitClass>('normalized_v1')
      const summary = ref<Record<string, unknown> | null>({
        unit_normalization: {
          contract: {
            source_unit: 'wan',
            storage_unit: 'yuan',
            factor: 10000,
            contract_digest: 'a'.repeat(64),
          },
        },
      })
      const { label, storageUnit, factor } = useDatasetUnitPresentation(classification, summary)

      expect(label.value).toBe('存储单位：元')
      expect(storageUnit.value).toBe('yuan')
      expect(factor.value).toBe(10000)
    })

    it('factor 为字符串数字也能正确解析', () => {
      const classification = ref<DatasetUnitClass>('normalized_v1')
      const summary = ref<Record<string, unknown> | null>({
        unit_normalization: {
          contract: { factor: '1000', contract_digest: 'b'.repeat(64) },
        },
      })
      const { factor } = useDatasetUnitPresentation(classification, summary)
      expect(factor.value).toBe(1000)
    })

    it('contract 缺 factor 时返回 null', () => {
      const classification = ref<DatasetUnitClass>('normalized_v1')
      const summary = ref<Record<string, unknown> | null>({
        unit_normalization: { contract: { contract_digest: 'c'.repeat(64) } },
      })
      const { factor } = useDatasetUnitPresentation(classification, summary)
      expect(factor.value).toBeNull()
    })

    it('summary 为 null 时 factor 为 null', () => {
      const classification = ref<DatasetUnitClass>('normalized_v1')
      const summary = ref<Record<string, unknown> | null>(null)
      const { label, storageUnit, factor } = useDatasetUnitPresentation(classification, summary)

      expect(label.value).toBe('存储单位：元')
      expect(storageUnit.value).toBe('yuan')
      expect(factor.value).toBeNull()
    })
  })

  // ── legacy_declared ───────────────────────────────────────────────

  describe('legacy_declared', () => {
    it('显示历史声明的单位', () => {
      const classification = ref<DatasetUnitClass>('legacy_declared')
      const summary = ref<Record<string, unknown> | null>({ amount_unit: '万元' })
      const { label, storageUnit, factor } = useDatasetUnitPresentation(classification, summary)

      expect(label.value).toBe('历史声明：万元')
      expect(storageUnit.value).toBeNull()
      expect(factor.value).toBeNull()
    })

    it('amount_unit 为元', () => {
      const classification = ref<DatasetUnitClass>('legacy_declared')
      const summary = ref<Record<string, unknown> | null>({ amount_unit: '元' })
      const { label } = useDatasetUnitPresentation(classification, summary)
      expect(label.value).toBe('历史声明：元')
    })

    it('summary 为 null 时降级为单位未确认', () => {
      const classification = ref<DatasetUnitClass>('legacy_declared')
      const summary = ref<Record<string, unknown> | null>(null)
      const { label } = useDatasetUnitPresentation(classification, summary)
      expect(label.value).toBe('单位未确认')
    })

    it('amount_unit 为空字符串时降级', () => {
      const classification = ref<DatasetUnitClass>('legacy_declared')
      const summary = ref<Record<string, unknown> | null>({ amount_unit: '' })
      const { label } = useDatasetUnitPresentation(classification, summary)
      expect(label.value).toBe('单位未确认')
    })
  })

  // ── legacy_unknown ────────────────────────────────────────────────

  describe('legacy_unknown', () => {
    it('显示单位未确认', () => {
      const classification = ref<DatasetUnitClass>('legacy_unknown')
      const summary = ref<Record<string, unknown> | null>({})
      const { label, storageUnit, factor } = useDatasetUnitPresentation(classification, summary)

      expect(label.value).toBe('单位未确认')
      expect(storageUnit.value).toBeNull()
      expect(factor.value).toBeNull()
    })
  })

  // ── 响应式切换 ────────────────────────────────────────────────────

  describe('reactive switching', () => {
    it('分类从 legacy_unknown 切到 normalized_v1 后 label 更新', async () => {
      const classification = ref<DatasetUnitClass>('legacy_unknown')
      const summary = ref<Record<string, unknown> | null>({
        unit_normalization: {
          contract: { factor: 10000, contract_digest: 'd'.repeat(64) },
        },
      })
      const { label, storageUnit, factor } = useDatasetUnitPresentation(classification, summary)

      expect(label.value).toBe('单位未确认')
      expect(storageUnit.value).toBeNull()
      expect(factor.value).toBeNull()

      classification.value = 'normalized_v1'
      await nextTick()

      expect(label.value).toBe('存储单位：元')
      expect(storageUnit.value).toBe('yuan')
      expect(factor.value).toBe(10000)
    })

    it('分类从 normalized_v1 切到 legacy_declared 后 factor 变 null', async () => {
      const classification = ref<DatasetUnitClass>('normalized_v1')
      const summary = ref<Record<string, unknown> | null>({
        amount_unit: '千元',
        unit_normalization: {
          contract: { factor: 1000, contract_digest: 'e'.repeat(64) },
        },
      })
      const { label, factor } = useDatasetUnitPresentation(classification, summary)

      expect(label.value).toBe('存储单位：元')
      expect(factor.value).toBe(1000)

      classification.value = 'legacy_declared'
      await nextTick()

      expect(label.value).toBe('历史声明：千元')
      expect(factor.value).toBeNull()
    })

    it('summary 变化后 label 响应更新', async () => {
      const classification = ref<DatasetUnitClass>('legacy_declared')
      const summary = ref<Record<string, unknown> | null>({ amount_unit: '元' })
      const { label } = useDatasetUnitPresentation(classification, summary)

      expect(label.value).toBe('历史声明：元')

      summary.value = { amount_unit: '万元' }
      await nextTick()

      expect(label.value).toBe('历史声明：万元')
    })
  })
})
