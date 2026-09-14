/**
 * useJ3Disclosure — J3 股份支付披露/附注
 *
 * IPO企业适用性判断 + 披露信息管理
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 * Requirements: 7.1-7.3
 */
import { ref, computed } from 'vue'

export interface J3DisclosureData {
  profitImpact: number         // 对利润的影响金额
  epsImpact: number            // 对每股收益的稀释影响
  isDisclosureSufficient: boolean  // 披露充分性
  notes: string                // 附注说明
}

export function useJ3Disclosure(projectType: string) {
  const disclosure = ref<J3DisclosureData>({
    profitImpact: 0,
    epsImpact: 0,
    isDisclosureSufficient: false,
    notes: '',
  })

  // ── IPO适用性判断 ─────────────────────────────────────────────────────────

  const isIPO = computed(() =>
    projectType.toLowerCase().includes('ipo') || projectType === '首次公开发行',
  )

  const showIPOPanel = computed(() => isIPO.value)

  // ── IPO审计重点提示 ───────────────────────────────────────────────────────

  const ipoHighlights = computed(() => {
    if (!isIPO.value) return []
    return [
      '股份支付费用对报告期利润的影响比例',
      '对每股收益的稀释效应',
      '信息披露的充分性和完整性',
      '股权激励计划合规性（证监会要求）',
      '历史期间股份支付追溯调整',
    ]
  })

  function updateDisclosure(updates: Partial<J3DisclosureData>) {
    Object.assign(disclosure.value, updates)
  }

  return {
    disclosure,
    isIPO,
    showIPOPanel,
    ipoHighlights,
    updateDisclosure,
  }
}
