/**
 * useM3CrossSheet — M3 库存股跨sheet校验引擎 + 注销冲减M2/M4联动
 *
 * Spec: .kiro/specs/m3-treasury-stock/
 * Task: 3.2
 * Requirements: 2.5, 5.3
 *
 * 职责：
 * 1. adjudicationVsDetail — M3-1审定表期末合计 vs M3-2明细表期末金额合计 勾稽校验
 * 2. cancellationToM2M4 — 注销冲减联动：注销金额拆分冲减实收资本(M2)+资本公积(M4)
 * 3. publishCancellationDeduction — EventBus 发布 'm3:cancellation-deduction' 到M2/M4
 *
 * 联动方向：
 *   M3-1审定表期末合计 ↔ M3-2明细表期末金额合计 双向勾稽
 *   M3-5注销冲减 → M2实收资本（冲减面值） + M4资本公积（冲减差额）
 *
 * 科目：4002 库存股（**借方/权益备抵类！期末=期初+借方-贷方**）
 * 回购在借方增加库存股，注销在贷方减少库存股（与其他M权益类方向相反！）
 *
 * ADR-2: 注销时冲减实收资本（按面值）和资本公积（差额），差额不足冲减盈余公积/未分配利润。
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useM3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 交叉验证结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = M3-1审定表期末合计 - M3-2明细表期末金额合计 */
  diff: number
  /** |diff| < 阈值视为匹配 */
  isMatch: boolean
}

/** 注销冲减 → M2/M4 联动结果 */
export interface CancellationToM2M4Result {
  /** 注销金额合计（库存股注销贷方减少） */
  totalCancellationAmount: number
  /** 冲减实收资本(M2)合计（按面值） */
  deductCapitalTotal: number
  /** 冲减资本公积(M4)合计（差额部分） */
  deductReserveTotal: number
  /** 未平差额（需冲减盈余公积/未分配利润的部分，=注销金额-冲减M2-冲减M4） */
  remainingDiff: number
  /** 是否存在未平差额 */
  hasRemainingDiff: boolean
  /** 按批次明细 */
  byBatch: Array<{
    batchName: string
    cancelAmount: number
    deductCapital: number
    deductReserve: number
    diff: number
  }>
}

/** EventBus 'm3:cancellation-deduction' 载荷 */
export interface M3CancellationDeductionPayload {
  wpCode: string
  totalCancellationAmount: number
  deductCapitalTotal: number
  deductReserveTotal: number
  remainingDiff: number
  byBatch: Array<{
    batchName: string
    cancelAmount: number
    deductCapital: number
    deductReserve: number
  }>
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

/** 审定-明细勾稽匹配阈值（1元内） */
const MATCH_THRESHOLD = 1

/** 未平差额提示阈值（0.01元，会计精度） */
const REMAINING_DIFF_THRESHOLD = 0.01

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析数字，NaN/null/undefined → 0
 */
function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
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
 * M3 跨sheet校验引擎 + 注销冲减M2/M4联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useM3FormData）
 */
export function useM3CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── 上次发布的注销冲减值（用于变化检测，仅变化时发布） ──────────────────────
  const _lastPublishedCancellation = ref<number | null>(null)

  // ─── 1. adjudicationVsDetail — 审定表M3-1合计 vs 明细表M3-2合计 ─────────

  /**
   * M3-1 审定表期末审定合计 应= M3-2 明细表各批次期末金额合计
   * 差额 = 审定表期末合计 - 明细表期末合计
   *
   * 权益备抵类期末=期初+借方(回购)-贷方(注销/再售)
   *
   * 数据来源：
   * - M3-1 审定表期末审定合计存于 item_id: "M3-M3-1-total-end-audited"（remark=期末审定余额合计）
   * - M3-2 明细表合计存于 item_id: "M3-M3-2-total-end-amount"（remark=各批次期末金额合计）
   *   或遍历 "M3-M3-2-batch-*-end-amount" 模式累加
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：M3-1期末审定余额合计
    const adjResp = allResponses.value.get('M3-M3-1-total-end-audited')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：优先取汇总行（M3-2合计行）
    const detailTotalResp = allResponses.value.get('M3-M3-2-total-end-amount')
    let detailTotal = parseNum(detailTotalResp?.remark)

    // 降级：如果汇总行无值，遍历明细行期末累加
    if (detailTotal === 0 && !detailTotalResp?.remark) {
      for (const [key, resp] of allResponses.value) {
        if (key.startsWith('M3-M3-2-batch-') && key.endsWith('-end-amount')) {
          detailTotal += parseNum(resp.remark)
        }
      }
    }

    const diff = parseFloat((adjTotal - detailTotal).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) < MATCH_THRESHOLD,
    }
  })

  // ─── 2. cancellationToM2M4 — 注销冲减联动(M2实收资本 + M4资本公积) ──────

  /**
   * 汇总 M3-5 检查表中各注销批次的冲减分配：
   * - totalCancellationAmount: 注销总金额（从M3-2注销金额/M3-5核对行）
   * - deductCapitalTotal: 冲减实收资本(M2)合计 —— 按面值×注销股数
   * - deductReserveTotal: 冲减资本公积(M4)合计 —— 注销差额部分
   * - remainingDiff: 未平差额（需冲减盈余公积/未分配利润）
   * - byBatch: 按批次明细
   *
   * ADR-2: 注销库存股流程：
   *   借：实收资本（面值×股数）
   *   借：资本公积—股本溢价（差额）
   *   贷：库存股（回购成本×股数）
   *   差额不足冲减资本公积时，冲减盈余公积/未分配利润
   *
   * 数据来源：
   * - M3-5 注销核对行存于 item_id: "M3-M3-5-cancel-rows"（remark=JSON数组）
   *   每行: { batchName, cancelAmount, deductCapital, deductReserve }
   */
  const cancellationToM2M4: ComputedRef<CancellationToM2M4Result> = computed(() => {
    const cancelResp = allResponses.value.get('M3-M3-5-cancel-rows')
    const cancelRows = safeParseRows<{
      batchName?: string
      cancelAmount?: number
      deductCapital?: number
      deductReserve?: number
    }>(cancelResp?.remark)

    let totalCancellationAmount = 0
    let deductCapitalTotal = 0
    let deductReserveTotal = 0
    const byBatch: CancellationToM2M4Result['byBatch'] = []

    for (const row of cancelRows) {
      const cancelAmount = parseNum(row.cancelAmount)
      const deductCapital = parseNum(row.deductCapital)
      const deductReserve = parseNum(row.deductReserve)
      const diff = parseFloat((cancelAmount - deductCapital - deductReserve).toFixed(2))

      totalCancellationAmount += cancelAmount
      deductCapitalTotal += deductCapital
      deductReserveTotal += deductReserve

      byBatch.push({
        batchName: row.batchName || '未命名批次',
        cancelAmount,
        deductCapital,
        deductReserve,
        diff,
      })
    }

    const remainingDiff = parseFloat(
      (totalCancellationAmount - deductCapitalTotal - deductReserveTotal).toFixed(2),
    )

    return {
      totalCancellationAmount: parseFloat(totalCancellationAmount.toFixed(2)),
      deductCapitalTotal: parseFloat(deductCapitalTotal.toFixed(2)),
      deductReserveTotal: parseFloat(deductReserveTotal.toFixed(2)),
      remainingDiff,
      hasRemainingDiff: Math.abs(remainingDiff) > REMAINING_DIFF_THRESHOLD,
      byBatch,
    }
  })

  // ─── 3. publishCancellationDeduction — EventBus 发布 ───────────────────

  /**
   * 发布 'm3:cancellation-deduction' 事件到 EventBus。
   * 仅在值变化时发布（避免重复广播）。
   *
   * M2实收资本 订阅此事件：核对注销冲减面值部分是否与减资一致。
   * M4资本公积 订阅此事件：核对注销冲减差额部分是否入账。
   *
   * ADR-2: 注销冲减顺序——实收资本（面值）→资本公积→盈余公积→未分配利润
   */
  function publishCancellationDeduction(): void {
    const result = cancellationToM2M4.value
    const currentTotal = result.totalCancellationAmount

    // 仅在值变化时发布
    if (_lastPublishedCancellation.value === currentTotal) return
    _lastPublishedCancellation.value = currentTotal

    // 无注销业务时不发布
    if (currentTotal === 0) return

    const payload: M3CancellationDeductionPayload = {
      wpCode: 'M3',
      totalCancellationAmount: result.totalCancellationAmount,
      deductCapitalTotal: result.deductCapitalTotal,
      deductReserveTotal: result.deductReserveTotal,
      remainingDiff: result.remainingDiff,
      byBatch: result.byBatch.map((b) => ({
        batchName: b.batchName,
        cancelAmount: b.cancelAmount,
        deductCapital: b.deductCapital,
        deductReserve: b.deductReserve,
      })),
      timestamp: Date.now(),
    }

    eventBus.emit('m3:cancellation-deduction', payload)
  }

  // ─── 4. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** M3 库存股 cross_wp_references（注销冲减→M2/M4） */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'M2',
      label: 'M2实收资本-注销冲减面值',
      direction: 'to',
    },
    {
      targetWpCode: 'M4',
      label: 'M4资本公积-注销冲减差额',
      direction: 'to',
    },
  ]

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    // 注销冲减→M2/M4联动
    cancellationToM2M4,
    publishCancellationDeduction,
    // 跨底稿引用
    crossWpReferences,
  }
}

export default useM3CrossSheet
