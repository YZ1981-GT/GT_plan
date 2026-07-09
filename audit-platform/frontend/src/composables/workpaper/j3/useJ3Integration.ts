/**
 * useJ3Integration — J3 股份支付集成联动模块
 *
 * 集成全部 6 大联动：
 * 1. EventBus: share-payment:expense-recognized → M4/J1/K8K9
 * 2. cross_wp_references: J3→M4 / J3→J1
 * 3. GtIndexChip: J3→M4 / J3→J1 跳转
 * 4. 权益结算→M4 / 现金结算→J1 自动分流
 * 5. 双模式 OO + IPO 适用性判断
 * 6. 版本链 + 复核对话
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 * Requirements: 6.1-6.5
 */
import { computed, type Ref } from 'vue'
import { http } from '@/utils/http'
import type { J3Plan } from './useJ3FormData'

// ═══ 6.1 EventBus 发布 ═══

export interface J3EventPayload {
  equitySettledAmount: number
  cashSettledAmount: number
  totalExpenseAmount: number
  wpId: string
  plans: Array<{ name: string; type: string; amount: number }>
}

export async function publishSharePaymentExpense(
  projectId: string,
  payload: J3EventPayload,
): Promise<boolean> {
  try {
    await http.post(`/api/projects/${projectId}/events/publish`, {
      event_type: 'share-payment:expense-recognized',
      payload,
    })
    return true
  } catch {
    return false
  }
}

// 权益结算 → M4
export async function publishEquitySettled(projectId: string, amount: number, wpId: string): Promise<boolean> {
  try {
    await http.post(`/api/projects/${projectId}/events/publish`, {
      event_type: 'share-payment:equity-settled',
      payload: { amount, wpId, targetAccount: '3002' },
    })
    return true
  } catch {
    return false
  }
}

// 现金结算 → J1
export async function publishCashSettled(projectId: string, amount: number, wpId: string): Promise<boolean> {
  try {
    await http.post(`/api/projects/${projectId}/events/publish`, {
      event_type: 'share-payment:cash-settled',
      payload: { amount, wpId, targetAccount: '2211' },
    })
    return true
  } catch {
    return false
  }
}

// ═══ 6.2 cross_wp_references ═══

export interface CrossWpRef {
  source_wp_id: string
  target_wp_code: string
  ref_type: string
  description: string
}

export async function registerCrossReferences(
  projectId: string,
  wpId: string,
  plans: Array<{ type: string }>,
): Promise<void> {
  const refs: CrossWpRef[] = []

  // J3 → M4 (权益结算)
  if (plans.some(p => p.type === 'equity')) {
    refs.push({
      source_wp_id: wpId,
      target_wp_code: 'M4',
      ref_type: 'share-payment-equity',
      description: 'J3股份支付→M4资本公积（权益结算贷方）',
    })
  }

  // J3 → J1 (现金结算)
  if (plans.some(p => p.type === 'cash')) {
    refs.push({
      source_wp_id: wpId,
      target_wp_code: 'J1',
      ref_type: 'share-payment-cash',
      description: 'J3股份支付→J1应付职工薪酬（现金结算贷方）',
    })
  }

  if (refs.length === 0) return

  try {
    await http.post(`/api/projects/${projectId}/cross-wp-references/batch`, { references: refs })
  } catch {
    // 联动底稿可能未就绪
  }
}

// ═══ 6.3 GtIndexChip 配置 ═══

export function useJ3ChipConfigs(plans: Ref<J3Plan[]>) {
  const chipConfigs = computed(() => {
    const chips: Array<{ label: string; wpCode: string; tooltip: string }> = []

    const hasEquity = plans.value.some(p => p.type === 'equity')
    const hasCash = plans.value.some(p => p.type === 'cash')

    if (hasEquity) {
      chips.push({
        label: 'M4',
        wpCode: 'M4',
        tooltip: 'M4 资本公积（权益结算贷方联动）',
      })
    }
    if (hasCash) {
      chips.push({
        label: 'J1',
        wpCode: 'J1',
        tooltip: 'J1 应付职工薪酬（现金结算贷方联动）',
      })
    }

    // 费用方向始终联动
    chips.push({
      label: 'K8',
      wpCode: 'K8',
      tooltip: 'K8/K9 管理费用（费用借方联动）',
    })

    return chips
  })

  return { chipConfigs }
}

// ═══ 6.4 结算分流逻辑 ═══

export function classifySettlementType(plans: J3Plan[]) {
  const equity = plans.filter(p => p.type === 'equity')
  const cash = plans.filter(p => p.type === 'cash')

  return {
    equityPlans: equity,
    cashPlans: cash,
    equityTotal: equity.reduce((s, p) => s + (p.currentExpense || 0), 0),
    cashTotal: cash.reduce((s, p) => s + (p.currentExpense || 0), 0),
    totalExpense: plans.reduce((s, p) => s + (p.currentExpense || 0), 0),
  }
}

// ═══ 6.5 双模式 + IPO 适用性 ═══

export function checkIPOApplicability(projectType: string): boolean {
  const ipoKeywords = ['ipo', '首发', '首次公开发行', 'IPO']
  return ipoKeywords.some(kw => projectType.toLowerCase().includes(kw.toLowerCase()))
}
