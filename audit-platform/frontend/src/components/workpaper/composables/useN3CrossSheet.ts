/**
 * useN3CrossSheet — N3 递延所得税负债跨sheet引擎 + N1对应 + N5递延税费用联动
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/
 * Task: 3.2
 * Requirements: 2.5, 6.1-6.5
 *
 * 职责：
 * 1. adjudicationVsDetail — N3-1审定表合计 vs N3-2明细表合计 勾稽校验
 * 2. n3ToN1Correspondence — N3与N1递延所得税资产的对应关系（同源暂时性差异分列）
 * 3. deferredTaxChange — 递延所得税负债本期变动额（期末-期初）供N5递延所得税费用核对
 * 4. publishDeferredTaxLiabilityUpdated — EventBus 发布 'deferred-tax:liability-updated'
 *
 * 联动方向：N3-1审定 → N3-2明细（合计交叉验证）
 *           N3-2 ↔ N1-4测算表（同源应纳税暂时性差异，N3接收负债部分）
 *           N3-1本期变动额 → N5-8递延税费用核对
 *           同一纳税主体可抵销，不同主体N1/N3分列
 *
 * 科目：2901 递延所得税负债（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useN3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 勾稽结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = 审定表合计 - 明细表合计 */
  diff: number
  /** 差额绝对值 ≤ 阈值 视为匹配 */
  isMatch: boolean
}

/** N3 与 N1 递延所得税资产对应关系 */
export interface N3ToN1CorrespondenceResult {
  /** N1负责的可抵扣暂时性差异对应递延税资产部分（从N1读取） */
  assetPart: number
  /** N3负责的应纳税暂时性差异对应递延税负债部分（本底稿审定） */
  liabilityPart: number
  /** 是否同一纳税主体可抵销（同一主体净额列示，不同主体分列） */
  canOffset: boolean
}

/** 递延所得税负债本期变动额（供N5核对） */
export interface DeferredTaxChangeResult {
  /** 变动额 = 期末审定 - 期初审定 */
  change: number
  /** 期初余额 */
  beginBalance: number
  /** 期末余额（审定数） */
  endBalance: number
}

/** EventBus 'deferred-tax:liability-updated' 载荷 */
export interface DeferredTaxLiabilityUpdatedPayload {
  wpCode: string
  /** 期末审定余额 */
  endBalance: number
  /** 期初余额 */
  beginBalance: number
  /** 本期变动额（期末-期初） */
  change: number
  timestamp: number
}

/** 跨底稿引用定义 */
export interface CrossWpReference {
  /** 目标底稿编码 */
  targetWpCode: string
  /** 引用说明 */
  label: string
  /** 引用方向：from=从目标引入, to=输出到目标 */
  direction: 'from' | 'to'
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 勾稽匹配阈值（0.01元内视为匹配） */
const MATCH_THRESHOLD = 0.01

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析数字，NaN/null/undefined → 0
 */
function parseNum(v: any): number {
  if (v == null) return 0
  if (typeof v === 'string') {
    try {
      v = JSON.parse(v)
    } catch {
      // not JSON, try direct parse
    }
  }
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 从 allResponses 获取指定 item_id 的 conclusion 数值
 */
function getResponseNum(allResponses: Map<string, ChecklistResponse>, itemId: string): number {
  const resp = allResponses.get(itemId)
  return parseNum(resp?.conclusion)
}

/**
 * 安全解析 JSON 数组字符串，失败回退空数组
 */
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * N3 跨sheet引擎 + N1递延税资产对应 + N5递延税费用联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useN3FormData）
 */
export function useN3CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── 上次发布的变动额（用于变化检测，仅变化时发布） ─────────────────────────
  const _lastPublishedChange = ref<number | null>(null)

  // ─── 1. adjudicationVsDetail — N3-1审定表合计 vs N3-2明细表合计 ─────────

  /**
   * N3-1 审定表递延所得税负债期末合计 应= N3-2 明细表各项目期末递延税负债合计
   * 差额 = 审定表合计 - 明细表合计
   *
   * 数据来源：
   * - N3-1 审定表期末合计: item_id "N3-1-end-balance-total"（conclusion=合计金额）
   * - N3-2 明细表行数据: item_id "N3-2-rows"（conclusion=JSON数组，每行含 endDeferredTaxLiability）
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表期末合计
    const adjTotal = getResponseNum(allResponses.value, 'N3-1-end-balance-total')

    // 明细表各行期末递延税负债汇总
    const detailResp = allResponses.value.get('N3-2-rows')
    const detailRows = safeParseRows<{ endDeferredTaxLiability?: number }>(detailResp?.conclusion)
    let detailTotal = 0
    for (const row of detailRows) {
      detailTotal += parseNum(row.endDeferredTaxLiability)
    }

    const diff = parseFloat((adjTotal - detailTotal).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) <= MATCH_THRESHOLD,
    }
  })

  // ─── 2. n3ToN1Correspondence — N3与N1递延所得税资产对应关系 ─────────────

  /**
   * N3递延所得税负债 与 N1递延所得税资产 的对应关系：
   * - assetPart: N1负责的可抵扣暂时性差异→递延税资产部分（从N1存储读取）
   * - liabilityPart: N3负责的应纳税暂时性差异→递延税负债部分（本底稿审定期末）
   * - canOffset: 同一纳税主体可互相抵销后净额列示
   *
   * 准则规定：
   * - 同一纳税主体的递延税资产与负债可以抵销后净额列示
   * - 不同纳税主体不能抵销，需分别在N1/N3列示
   *
   * 数据来源：
   * - N1递延税资产期末: item_id "N3-cross-n1-asset-balance"（N1回写/手工录入）
   * - N3递延税负债期末: item_id "N3-1-end-balance-total"
   * - 是否同一纳税主体: item_id "N3-cross-n1-same-entity"（conclusion="true"/"false"）
   */
  const n3ToN1Correspondence: ComputedRef<N3ToN1CorrespondenceResult> = computed(() => {
    // N1递延税资产期末余额（从N1传入或手工录入）
    const assetPart = getResponseNum(allResponses.value, 'N3-cross-n1-asset-balance')

    // N3递延税负债期末审定额
    const liabilityPart = getResponseNum(allResponses.value, 'N3-1-end-balance-total')

    // 是否同一纳税主体可抵销
    const sameEntityResp = allResponses.value.get('N3-cross-n1-same-entity')
    const canOffset = sameEntityResp?.conclusion === 'true'

    return {
      assetPart,
      liabilityPart,
      canOffset,
    }
  })

  // ─── 3. deferredTaxChange — 递延税负债本期变动额（供N5核对） ────────────

  /**
   * 递延所得税负债本期变动额 = 期末审定 - 期初余额
   * 此值供 N5-8 递延所得税费用核对表接收。
   *
   * 递延所得税费用(N5) = 递延税负债本期增加 - 递延税资产本期增加
   *
   * 数据来源：
   * - 期初余额: item_id "N3-1-begin-balance"（conclusion=期初金额）
   * - 期末审定: item_id "N3-1-end-balance-total"（conclusion=审定期末金额）
   */
  const deferredTaxChange: ComputedRef<DeferredTaxChangeResult> = computed(() => {
    const beginBalance = getResponseNum(allResponses.value, 'N3-1-begin-balance')
    const endBalance = getResponseNum(allResponses.value, 'N3-1-end-balance-total')
    const change = parseFloat((endBalance - beginBalance).toFixed(2))

    return {
      change,
      beginBalance,
      endBalance,
    }
  })

  // ─── 4. publishDeferredTaxLiabilityUpdated — EventBus 发布 ─────────────

  /**
   * 发布 'deferred-tax:liability-updated' 事件到 EventBus。
   * 仅在值变化时发布（避免重复广播）。
   *
   * 载荷：wpCode / 期末余额 / 期初余额 / 变动额 / 时间戳
   * N5递延所得税费用核对表(N5-8) 订阅用于递延税费用计算核对。
   */
  function publishDeferredTaxLiabilityUpdated(): void {
    const { change, beginBalance, endBalance } = deferredTaxChange.value

    // 仅在值变化时发布
    if (_lastPublishedChange.value === change) return
    _lastPublishedChange.value = change

    const payload: DeferredTaxLiabilityUpdatedPayload = {
      wpCode: 'N3',
      endBalance,
      beginBalance,
      change,
      timestamp: Date.now(),
    }

    eventBus.emit('deferred-tax:liability-updated', payload)
  }

  // ─── 5. 跨底稿引用定义 ────────────────────────────────────────────────

  /** N3 递延所得税负债 cross_wp_references（关联 N1, N5） */
  const cross_wp_references: CrossWpReference[] = [
    {
      targetWpCode: 'N1',
      label: 'N1递延所得税资产-同源暂时性差异对应',
      direction: 'from',
    },
    {
      targetWpCode: 'N5',
      label: 'N5所得税费用-递延税费用核对',
      direction: 'to',
    },
  ]

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    // N1对应关系
    n3ToN1Correspondence,
    // N5递延税费用联动
    deferredTaxChange,
    publishDeferredTaxLiabilityUpdated,
    // 跨底稿引用
    cross_wp_references,
  }
}

export default useN3CrossSheet
