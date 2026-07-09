/**
 * useM2CrossSheet — M2 实收资本（股本）跨sheet校验引擎 + M4资本公积联动
 *
 * Spec: .kiro/specs/m2-paid-in-capital/
 * Task: 3.2
 * Requirements: 2.5, 3.1, 4.4
 *
 * 职责：
 * 1. adjudicationVsDetail — M2-1审定表合计 vs M2-2明细表合计 交叉验证
 * 2. detailBranch — 上市/非上市版本分支状态（el-segmented 驱动）
 * 3. fxDiffToM4 — M2-4外币折算差异超阈值→M4资本公积跨底稿联动提示
 *
 * 联动方向：
 *   M2-4外币折算差异 → M4资本公积（cross_wp_ref + EventBus 'm2:fx-diff-to-m4'）
 *   M2-1审定表合计 ↔ M2-2明细表合计 双向勾稽
 *
 * 科目：4001 实收资本/股本（贷方/权益类！期末=期初+贷方-借方）
 *
 * ADR-4: 外币出资按出资日汇率折算，与账面差异计入资本公积（M4）。
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useM2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 交叉验证结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = M2-1审定表期末合计 - M2-2明细表期末合计 */
  diff: number
  /** |diff| < 阈值视为匹配 */
  isMatch: boolean
}

/** 外币折算差异 → M4 联动结果 */
export interface FxDiffToM4Result {
  /** M2-4 外币折算差异合计 */
  totalFxDiff: number
  /** |totalFxDiff| > 阈值，需要提示计入M4 */
  exceedsThreshold: boolean
  /** 按出资人明细 */
  byInvestor: Array<{ investor: string; fxDiff: number }>
}

/** EventBus 'm2:fx-diff-to-m4' 载荷 */
export interface M2FxDiffToM4Payload {
  wpCode: string
  totalFxDiff: number
  byInvestor: Array<{ investor: string; fxDiff: number }>
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

/** 外币折算差异→M4提示阈值（100元，允许汇率小数误差） */
const FX_DIFF_THRESHOLD = 100

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
 * M2 跨sheet校验引擎 + M4资本公积联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useM2FormData）
 */
export function useM2CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── 上次发布的FX差异值（用于变化检测，仅变化时发布） ─────────────────────────
  const _lastPublishedFxDiff = ref<number | null>(null)

  // ─── 1. detailBranch — 上市/非上市分支选择器状态 ──────────────────────────

  /**
   * M2-2 明细表分支选择器：
   * - 'listed' → 上市公司版（38×36 股份）
   * - 'unlisted' → 非上市公司版（37×24 出资）
   *
   * 初始值从 checklist_responses 恢复（item_id: "M2-M2-2-detail-branch"）
   * 默认 'unlisted'（非上市公司更常见）
   */
  const detailBranch: Ref<'listed' | 'unlisted'> = ref(_restoreBranch())

  function _restoreBranch(): 'listed' | 'unlisted' {
    const resp = allResponses.value.get('M2-M2-2-detail-branch')
    if (resp?.conclusion === 'listed') return 'listed'
    return 'unlisted'
  }

  // ─── 2. adjudicationVsDetail — 审定表M2-1合计 vs 明细表M2-2合计 ──────────

  /**
   * M2-1 审定表期末余额合计 应= M2-2 明细表各出资人/股东期末余额之和
   * 差额 = 审定表期末合计 - 明细表期末合计
   *
   * 权益类期末=期初+贷方(增资)-借方(减资)
   *
   * 数据来源：
   * - M2-1 审定表合计存于 item_id: "M2-M2-1-total-end-balance"（remark=期末余额合计）
   * - M2-2 明细表合计存于 item_id: "M2-M2-2-total-end"（remark=各出资人期末合计）
   *   或遍历 "M2-M2-2-row*-end" 模式累加
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：M2-1期末余额合计
    const adjResp = allResponses.value.get('M2-M2-1-total-end-balance')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：优先取汇总行（M2-2合计行）
    const detailTotalResp = allResponses.value.get('M2-M2-2-total-end')
    let detailTotal = parseNum(detailTotalResp?.remark)

    // 降级：如果汇总行无值，遍历明细行期末累加
    if (detailTotal === 0 && !detailTotalResp?.remark) {
      for (const [key, resp] of allResponses.value) {
        if (key.startsWith('M2-M2-2-row') && key.endsWith('-end')) {
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

  // ─── 3. fxDiffToM4 — M2-4外币折算差异合计 + M4联动 ────────────────────────

  /**
   * 汇总 M2-4 外币投资汇率测算表各行的折算差异：
   * - totalFxDiff: Σ fxDiff
   * - exceedsThreshold: |totalFxDiff| > FX_DIFF_THRESHOLD 时需提示用户计入M4
   * - byInvestor: 按出资人明细
   *
   * 数据来源：
   * - M2-4 行数据存于 item_id: "M2-M2-4-rows"（remark=JSON数组）
   *   每行: { investor, originalAmount, currency, rate, converted, booked, fxDiff }
   */
  const fxDiffToM4: ComputedRef<FxDiffToM4Result> = computed(() => {
    const fxResp = allResponses.value.get('M2-M2-4-rows')
    const fxRows = safeParseRows<{
      investor?: string
      fxDiff?: number
    }>(fxResp?.remark)

    let totalFxDiff = 0
    const byInvestor: Array<{ investor: string; fxDiff: number }> = []

    for (const row of fxRows) {
      const diff = parseNum(row.fxDiff)
      totalFxDiff += diff
      if (row.investor) {
        byInvestor.push({
          investor: row.investor,
          fxDiff: diff,
        })
      }
    }

    totalFxDiff = parseFloat(totalFxDiff.toFixed(2))

    return {
      totalFxDiff,
      exceedsThreshold: Math.abs(totalFxDiff) > FX_DIFF_THRESHOLD,
      byInvestor,
    }
  })

  // ─── 4. publishFxDiffToM4 — EventBus 发布 ──────────────────────────────

  /**
   * 发布 'm2:fx-diff-to-m4' 事件到 EventBus。
   * 仅在值变化时发布（避免重复广播）。
   *
   * M4资本公积订阅此事件，用于外币出资折算差异的资本公积入账核对。
   * ADR-4: 外币出资按出资日汇率折算，与账面差异计入资本公积。
   */
  function publishFxDiffToM4(): void {
    const result = fxDiffToM4.value
    const currentTotal = result.totalFxDiff

    // 仅在值变化时发布
    if (_lastPublishedFxDiff.value === currentTotal) return
    _lastPublishedFxDiff.value = currentTotal

    // 仅超阈值时才发布（避免微小汇率误差触发联动）
    if (!result.exceedsThreshold) return

    const payload: M2FxDiffToM4Payload = {
      wpCode: 'M2',
      totalFxDiff: result.totalFxDiff,
      byInvestor: result.byInvestor,
      timestamp: Date.now(),
    }

    eventBus.emit('m2:fx-diff-to-m4', payload)
  }

  // ─── 5. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** M2 实收资本 cross_wp_references（外币折算差异→M4资本公积） */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'M4',
      label: 'M4资本公积-外币出资折算差异',
      direction: 'to',
    },
  ]

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 分支选择器状态
    detailBranch,
    // 核心勾稽
    adjudicationVsDetail,
    // 外币折算差异→M4联动
    fxDiffToM4,
    publishFxDiffToM4,
    // 跨底稿引用
    crossWpReferences,
  }
}

export default useM2CrossSheet
