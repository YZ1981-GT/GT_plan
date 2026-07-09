/**
 * useJ2Detail — J2-2 明细表逻辑（DBO + 计划资产 + 净负债三区段）
 *
 * 明细表含90行×14列：
 * - 区段1：设定受益计划（离职后福利）
 * - 区段2：其他长期职工福利
 * - 区段3：辞退福利
 *
 * 每区段行结构：期初/增加(服务成本+利息+精算损失)/减少(已支付+精算利得)/期末
 * 公式：期末 = 期初 + 增加 - 减少（负债类贷方！）
 *
 * Spec: .kiro/specs/j2-defined-benefit-plan/
 * Requirements: 3.1-3.3, 4.1-4.3
 */
import { ref, computed, type Ref } from 'vue'
import { calcLiabilityEndBalance, calcSubtotal } from './useJ2FormulaEngine'
import { calcEndDBO, calcInterestCost, calcNetLiability } from './useJ2ActuarialEngine'

export interface DetailItem {
  id: string
  label: string
  beginBalance: number
  serviceCost: number         // 当期服务成本
  interestCost: number        // 利息费用
  actuarialLoss: number       // 精算损失
  benefitsPaid: number        // 已支付福利
  actuarialGain: number       // 精算利得
  otherIncrease: number       // 其他增加
  otherDecrease: number       // 其他减少
  endBalance: number          // 期末（自动计算）
  planAssetFV: number         // 计划资产公允价值
  netLiability: number        // 净负债（自动计算）
  note: string
}

export function useJ2Detail() {
  const items: Ref<DetailItem[]> = ref([])

  // ── 公式重算 ──────────────────────────────────────────────────────────────

  function recalcItem(item: DetailItem): DetailItem {
    // DBO期末 = 期初 + 服务成本 + 利息 + 损失 - 利得 - 已支付 + 其他增 - 其他减
    const totalIncrease = item.serviceCost + item.interestCost + item.actuarialLoss + item.otherIncrease
    const totalDecrease = item.benefitsPaid + item.actuarialGain + item.otherDecrease
    item.endBalance = calcLiabilityEndBalance(item.beginBalance, totalIncrease, totalDecrease)
    // 净负债 = DBO期末 - 计划资产
    item.netLiability = calcNetLiability(item.endBalance, item.planAssetFV)
    return item
  }

  function recalcAll() {
    items.value.forEach(recalcItem)
  }

  // ── 合计 ──────────────────────────────────────────────────────────────────

  const totalBeginBalance = computed(() => calcSubtotal(items.value.map(i => i.beginBalance)))
  const totalEndBalance = computed(() => calcSubtotal(items.value.map(i => i.endBalance)))
  const totalNetLiability = computed(() => calcSubtotal(items.value.map(i => i.netLiability)))
  const totalIncrease = computed(() =>
    calcSubtotal(items.value.map(i =>
      i.serviceCost + i.interestCost + i.actuarialLoss + i.otherIncrease,
    )),
  )
  const totalDecrease = computed(() =>
    calcSubtotal(items.value.map(i =>
      i.benefitsPaid + i.actuarialGain + i.otherDecrease,
    )),
  )

  // ── 从htmlData加载 ─────────────────────────────────────────────────────

  function loadFromHtmlData(data: Record<string, unknown>) {
    if (data.detail && Array.isArray(data.detail)) {
      items.value = (data.detail as DetailItem[]).map(recalcItem)
    }
  }

  function createDefaultItems(): DetailItem[] {
    return [
      createEmptyItem('db-retirement', '离职后福利-设定受益计划'),
      createEmptyItem('db-other-long', '其他长期职工福利'),
      createEmptyItem('db-termination', '辞退福利'),
    ]
  }

  function createEmptyItem(id: string, label: string): DetailItem {
    return {
      id, label,
      beginBalance: 0, serviceCost: 0, interestCost: 0,
      actuarialLoss: 0, benefitsPaid: 0, actuarialGain: 0,
      otherIncrease: 0, otherDecrease: 0, endBalance: 0,
      planAssetFV: 0, netLiability: 0, note: '',
    }
  }

  return {
    items,
    recalcItem,
    recalcAll,
    totalBeginBalance,
    totalEndBalance,
    totalNetLiability,
    totalIncrease,
    totalDecrease,
    loadFromHtmlData,
    createDefaultItems,
  }
}
