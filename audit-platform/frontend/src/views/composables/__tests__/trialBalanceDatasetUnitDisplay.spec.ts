/**
 * R8 / AC-14 前端守卫：数据集单位三态必须在**主页面**可见，不能只藏在导入弹窗里。
 *
 * 背景（真实缺口）：`useTrialBalanceDatasetUnit` 原本只接导入弹窗的
 * `existingDataSummary`，而那个 ref 只在弹窗打开时才填充 ⇒ 用户在主页面
 * 永远看不到「存储单位：元」，`LedgerPenetration.vue` 里 `datasetUnitLabel`
 * 更是**只声明从未渲染**。两处都测不出「页面上看不见」这类缺陷，
 * 所以这里既测 composable 的自加载行为，也用源码形态断言钉住渲染点。
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

const getActiveLedgerDataset = vi.fn()

vi.mock('@/services/ledgerImportApi', () => ({
  getActiveLedgerDataset: (...args: unknown[]) => getActiveLedgerDataset(...args),
}))

import { useTrialBalanceDatasetUnit } from '../useTrialBalanceDatasetUnit'

const NORMALIZED_SUMMARY = {
  unit_normalization: {
    version: 'normalized_v1',
    contract: {
      source_unit: 'wan',
      storage_unit: 'yuan',
      factor: '10000',
      contract_digest: 'a'.repeat(64),
    },
  },
}

describe('useTrialBalanceDatasetUnit 自加载', () => {
  beforeEach(() => {
    getActiveLedgerDataset.mockReset()
  })

  it('无弹窗摘要时自己加载 active 数据集并判成 normalized_v1', async () => {
    getActiveLedgerDataset.mockResolvedValue({ source_summary: NORMALIZED_SUMMARY })

    const summary = ref<{
      year: number
      balance_count: number
      ledger_count: number
      amount_unit: string
      source_summary: Record<string, unknown> | null
    } | null>(null)
    const projectId = ref<string | null>('p1')
    const year = ref<number | null>(2025)

    const { label, storageUnit, factor } = useTrialBalanceDatasetUnit(summary, projectId, year)
    await nextTick()
    await nextTick()

    expect(getActiveLedgerDataset).toHaveBeenCalledWith('p1', 2025)
    expect(label.value).toBe('存储单位：元')
    expect(storageUnit.value).toBe('yuan')
    expect(factor.value).toBe(10000)
  })

  it('弹窗摘要优先于自加载结果', async () => {
    getActiveLedgerDataset.mockResolvedValue({ source_summary: NORMALIZED_SUMMARY })

    const summary = ref({
      year: 2025,
      balance_count: 1,
      ledger_count: 0,
      amount_unit: '元',
      source_summary: { amount_unit: '万元' } as Record<string, unknown>,
    })
    const { label } = useTrialBalanceDatasetUnit(summary, ref('p1'), ref(2025))
    await nextTick()
    await nextTick()

    // 弹窗摘要（legacy_declared）优先，说明优先级没写反
    expect(label.value).toBe('历史声明：万元')
  })

  it('自加载失败不抛错且保持「单位未确认」', async () => {
    getActiveLedgerDataset.mockRejectedValue(new Error('boom'))
    const { label } = useTrialBalanceDatasetUnit(ref(null), ref('p1'), ref(2025))
    await nextTick()
    await nextTick()
    expect(label.value).toBe('单位未确认')
  })

  it('缺项目或年度时不发请求', async () => {
    useTrialBalanceDatasetUnit(ref(null), ref(null), ref(null))
    await nextTick()
    expect(getActiveLedgerDataset).not.toHaveBeenCalled()
  })
})

describe('单位标签真的渲染在页面上（形态判据）', () => {
  const root = resolve(__dirname, '../../..')

  function read(rel: string): string {
    return readFileSync(resolve(root, rel), 'utf-8')
  }

  it('TrialBalance 主页面把 datasetUnitLabel 放进 badges', () => {
    const source = read('views/TrialBalance.vue')
    const badgeBlock = source.slice(0, source.indexOf('</GtInfoBar>'))
    expect(badgeBlock).toContain('datasetUnitLabel')
  })

  it('TrialBalance 把项目与年度传给 composable（否则不会自加载）', () => {
    const source = read('views/TrialBalance.vue')
    expect(source).toMatch(
      /useTrialBalanceDatasetUnit\(\s*existingDataSummary\s*,\s*selectedProjectId\s*,\s*selectedYear\s*\)/,
    )
  })

  it('LedgerPenetration 真的渲染 datasetUnitLabel（不是只声明）', () => {
    const source = read('views/LedgerPenetration.vue')
    // 只声明不渲染时，`{{ datasetUnitLabel }}` 这个插值不会出现
    expect(source).toContain('{{ datasetUnitLabel }}')
    expect(source).toContain('data-testid="ledger-dataset-unit"')
  })
})
