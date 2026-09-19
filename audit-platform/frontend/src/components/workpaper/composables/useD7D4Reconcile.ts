/**
 * useD7D4Reconcile — D7 合同负债 ↔ D4 收入跨底稿勾稽
 *
 * 核心审计逻辑：合同负债借方减少 ≈ 收入确认（D4审定数）
 * CAS14：合同负债减少 = 履约义务完成 → 确认收入
 *
 * 勾稽维度：
 *   D7 本期借方发生额合计（从D7-2明细 debitAmount SUM）
 *   vs D4 本期收入审定数（从crossWpEventBridge订阅 substantive:adjudicated wpCode=D4）
 *
 * 差异原因提示：
 *   差异 > 0：D7减少 > D4收入 → 可能存在合同取消/退款未冲减收入
 *   差异 < 0：D4收入 > D7减少 → 可能存在直接收入确认未经合同负债过渡
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useD7FormulaEngine'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useD7FormData'

export interface D7D4ReconcileResult {
  d7DebitTotal: number        // D7本期借方发生额合计（合同负债减少）
  d4RevenueAudited: number   // D4收入审定数（从事件获取或手工填入）
  difference: number          // D7借方 - D4收入
  isConsistent: boolean       // |差异| ≤ 容差
  warningMessage: string      // 差异提示文本
}

export interface UseD7D4ReconcileOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  projectId: Ref<string>
}

const D4_REVENUE_KEY = 'D7-d4-revenue-audited'

export function useD7D4Reconcile(options: UseD7D4ReconcileOptions) {
  const { allResponses } = options

  // D4 收入审定数（从事件自动获取或手工录入）
  const d4RevenueAudited = ref<number>(0)

  // 从 allResponses 加载已保存的 D4 金额
  const savedD4Amount = computed(() =>
    parseNum(allResponses.value.get(D4_REVENUE_KEY)?.remark),
  )

  // 初始化
  if (savedD4Amount.value > 0) {
    d4RevenueAudited.value = savedD4Amount.value
  }

  // 订阅 D4 审定事件自动更新
  function _onD4Adjudicated(payload: any): void {
    if (!payload) return
    if (payload.wpCode === 'D4' || payload.accountCode === '6001') {
      const amount = payload.auditedAmount ?? payload.adjudicatedAmount ?? 0
      if (amount > 0) {
        d4RevenueAudited.value = amount
      }
    }
  }

  eventBus.on('substantive:adjudicated', _onD4Adjudicated)

  // D7 本期借方发生额合计
  const d7DebitTotal: ComputedRef<number> = computed(() => {
    const jsonStr = allResponses.value.get('D7-2-rows')?.remark
    if (!jsonStr) return 0
    try {
      const rows = JSON.parse(jsonStr)
      if (!Array.isArray(rows)) return 0
      return calcSubtotal(rows.map((r: any) => parseNum(r.debitAmount)))
    } catch {
      return 0
    }
  })

  // 勾稽结果
  const reconcileResult: ComputedRef<D7D4ReconcileResult> = computed(() => {
    const d7 = d7DebitTotal.value
    const d4 = d4RevenueAudited.value
    const diff = d7 - d4
    const tolerance = Math.max(Math.abs(d7), Math.abs(d4)) * 0.01 // 1%容差
    const isConsistent = Math.abs(diff) <= Math.max(tolerance, 1)

    let warningMessage = ''
    if (!isConsistent) {
      if (diff > 0) {
        warningMessage = `D7合同负债本期减少(${d7.toLocaleString()})大于D4收入确认(${d4.toLocaleString()})，差额${diff.toLocaleString()}元。关注是否存在合同取消/退款未冲减收入或非经营性冲减。`
      } else {
        warningMessage = `D4收入确认(${d4.toLocaleString()})大于D7合同负债本期减少(${d7.toLocaleString()})，差额${Math.abs(diff).toLocaleString()}元。关注是否存在直接收入确认（未经合同负债过渡的交易）。`
      }
    }

    return { d7DebitTotal: d7, d4RevenueAudited: d4, difference: diff, isConsistent, warningMessage }
  })

  // 手动设置D4金额
  function setD4RevenueAudited(amount: number): void {
    d4RevenueAudited.value = amount
  }

  // Cleanup
  function dispose(): void {
    eventBus.off('substantive:adjudicated', _onD4Adjudicated)
  }

  return {
    d7DebitTotal,
    d4RevenueAudited,
    reconcileResult,
    setD4RevenueAudited,
    dispose,
  }
}

export default useD7D4Reconcile
