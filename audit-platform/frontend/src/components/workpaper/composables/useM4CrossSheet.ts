/**
 * useM4CrossSheet — M4 资本公积跨sheet校验引擎 + J3/M2联动
 *
 * Spec: .kiro/specs/m4-capital-reserve/
 * Task: 3.2
 * Requirements: 2.5, 4.1-4.6
 *
 * 职责：
 * 1. adjudicationVsDetail — M4-1审定表合计 vs M4-2明细表合计(资本溢价+其他资本公积) 交叉验证
 * 2. shareBasedVsJ3 — J3股份支付权益结算金额 vs M4其他资本公积账面增加 一致性校验
 * 3. fxDiffVsM2 — M2外币出资折算差异 vs M4资本溢价变动 一致性校验
 * 4. EventBus订阅 'j3:equity-settled' / 'm2:fx-diff'
 * 5. cross_wp_references 关联 J3、M2
 *
 * 联动方向：
 *   J3股份支付 → 'j3:equity-settled'  → shareBasedVsJ3（其他资本公积增加）
 *   M2实收资本 → 'm2:fx-diff'         → fxDiffVsM2（资本溢价变动）
 *   M4-1审定表合计 ↔ M4-2明细表合计 双向勾稽
 *
 * 科目：4002 资本公积（**贷方/权益类！期末=期初+贷方-借方**）
 *
 * ADR-2: 资本公积是权益变动的汇聚点：
 *   J3股份支付权益结算（等待期确认计入其他资本公积）
 *   M2外币出资折算差异（计入资本溢价）
 */
import { computed, ref, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcShareBasedDiff } from './useM4ReserveEngine'
import type { ChecklistResponse } from './useM4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 交叉验证结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = M4-1审定表期末合计 - M4-2明细表合计(资本溢价+其他资本公积) */
  diff: number
  /** |diff| < 阈值视为匹配 */
  isMatch: boolean
}

/** J3股份支付 vs M4其他资本公积 一致性校验结果 */
export interface ShareBasedVsJ3Result {
  /** 差额 = J3确认金额 - 账面其他资本公积增加 */
  diff: number
  /** |diff| < 阈值视为一致 */
  isConsistent: boolean
}

/** M2外币折算差异 vs M4资本溢价变动 一致性校验结果 */
export interface FxDiffVsM2Result {
  /** 差额 = M2外币折算差异 - M4资本溢价变动 */
  diff: number
  /** |diff| < 阈值视为一致 */
  isConsistent: boolean
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

/** 股份支付/外币折算差异一致性阈值（0.01元，会计精度） */
export const DIFF_THRESHOLD = 0.01

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析数字，NaN/null/undefined → 0
 */
function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M4 跨sheet校验引擎 + J3股份支付/M2外币折算联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useM4FormData）
 */
export function useM4CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── EventBus 订阅的联动数据（reactive refs） ──────────────────────────────

  /** J3股份支付权益结算金额（订阅 'j3:equity-settled'） */
  const _j3EquitySettled = ref(0)
  /** M2外币出资折算差异（订阅 'm2:fx-diff'） */
  const _m2FxDiff = ref(0)

  // ─── EventBus 订阅 handlers ─────────────────────────────────────────────

  /**
   * J3股份支付权益结算完成
   * 载荷: { wpCode, equitySettledAmount, waitingPeriodAmount, timestamp }
   * 取 equitySettledAmount（等待期确认的权益结算金额，计入其他资本公积）
   */
  function _onJ3EquitySettled(payload: any): void {
    _j3EquitySettled.value = parseNum(payload?.equitySettledAmount ?? payload?.amount)
  }

  /**
   * M2外币出资折算差异完成
   * 载荷: { wpCode, fxDiffAmount, timestamp }
   * 取 fxDiffAmount（外币出资折算差异，计入资本溢价）
   */
  function _onM2FxDiff(payload: any): void {
    _m2FxDiff.value = parseNum(payload?.fxDiffAmount ?? payload?.amount)
  }

  // ─── 订阅 EventBus ─────────────────────────────────────────────────────────

  eventBus.on('j3:equity-settled' as any, _onJ3EquitySettled)
  eventBus.on('m2:fx-diff' as any, _onM2FxDiff)

  // ─── 初始化：从 allResponses 读取已持久化的联动数据 ─────────────────────────

  /**
   * 从 checklist_responses 恢复上次保存的联动数据
   * （EventBus 仅同会话有效，需要从持久化数据恢复）
   */
  function _restoreFromResponses(): void {
    const j3Resp = allResponses.value.get('M4-cross-j3-equity-settled')
    if (j3Resp?.remark) _j3EquitySettled.value = parseNum(j3Resp.remark)

    const m2Resp = allResponses.value.get('M4-cross-m2-fx-diff')
    if (m2Resp?.remark) _m2FxDiff.value = parseNum(m2Resp.remark)
  }

  // 初次恢复
  _restoreFromResponses()

  // ─── 1. adjudicationVsDetail — 审定表M4-1合计 vs 明细表M4-2合计 ─────────

  /**
   * M4-1 审定表期末合计 应= M4-2 明细表（资本溢价+其他资本公积）期末金额合计
   * 差额 = 审定表期末合计 - 明细表合计
   *
   * 权益类贷方：期末=期初+贷方-借方
   *
   * 数据来源：
   * - M4-1 审定表期末合计存于 item_id: "M4-M4-1-total-end-audited"（remark=期末审定余额合计）
   * - M4-2 明细表合计存于 item_id: "M4-M4-2-total-end-amount"（remark=资本溢价+其他资本公积期末合计）
   *   或遍历 "M4-M4-2-premium-*-end" + "M4-M4-2-other-*-end" 模式累加
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：M4-1期末审定余额合计
    const adjResp = allResponses.value.get('M4-M4-1-total-end-audited')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：优先取汇总行（M4-2合计行）
    const detailTotalResp = allResponses.value.get('M4-M4-2-total-end-amount')
    let detailTotal = parseNum(detailTotalResp?.remark)

    // 降级：如果汇总行无值，遍历明细行期末累加（资本溢价+其他资本公积）
    if (detailTotal === 0 && !detailTotalResp?.remark) {
      for (const [key, resp] of allResponses.value) {
        if (
          (key.startsWith('M4-M4-2-premium-') || key.startsWith('M4-M4-2-other-')) &&
          key.endsWith('-end')
        ) {
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

  // ─── 2. shareBasedVsJ3 — J3股份支付确认 vs M4其他资本公积增加 ─────────────

  /**
   * J3股份支付权益结算金额 应= M4其他资本公积中股份支付对应的本期增加金额
   * 差额 = J3确认金额 - 账面其他资本公积增加
   *
   * 复用 calcShareBasedDiff（来自 useM4ReserveEngine）
   *
   * 数据来源：
   * - J3确认金额：EventBus 'j3:equity-settled' 或持久化 "M4-cross-j3-equity-settled"
   * - 账面增加：item_id "M4-M4-2-other-share-based-increase"（remark=股份支付本期增加）
   */
  const shareBasedVsJ3: ComputedRef<ShareBasedVsJ3Result> = computed(() => {
    const j3Amount = _j3EquitySettled.value

    // 账面其他资本公积中股份支付增加
    const bookedResp = allResponses.value.get('M4-M4-2-other-share-based-increase')
    const booked = parseNum(bookedResp?.remark)

    const diff = calcShareBasedDiff(j3Amount, booked)
    return {
      diff,
      isConsistent: Math.abs(diff) <= DIFF_THRESHOLD,
    }
  })

  // ─── 3. fxDiffVsM2 — M2外币折算差异 vs M4资本溢价变动 ────────────────────

  /**
   * M2外币出资折算差异 应= M4资本溢价中外币折算差异对应的本期变动金额
   * 差额 = M2折算差异 - M4资本溢价变动
   *
   * 数据来源：
   * - M2折算差异：EventBus 'm2:fx-diff' 或持久化 "M4-cross-m2-fx-diff"
   * - M4资本溢价变动：item_id "M4-M4-2-premium-fx-diff-change"（remark=外币折算差异计入资本溢价）
   */
  const fxDiffVsM2: ComputedRef<FxDiffVsM2Result> = computed(() => {
    const m2Amount = _m2FxDiff.value

    // M4资本溢价中外币折算差异变动
    const premiumFxResp = allResponses.value.get('M4-M4-2-premium-fx-diff-change')
    const premiumChange = parseNum(premiumFxResp?.remark)

    const diff = parseFloat((m2Amount - premiumChange).toFixed(2))
    return {
      diff,
      isConsistent: Math.abs(diff) <= DIFF_THRESHOLD,
    }
  })

  // ─── 4. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** M4 资本公积 cross_wp_references（接收J3/M2） */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'J3',
      label: 'J3股份支付-权益结算→其他资本公积',
      direction: 'from',
    },
    {
      targetWpCode: 'M2',
      label: 'M2实收资本-外币出资折算差异→资本溢价',
      direction: 'from',
    },
  ]

  // ─── 5. Cleanup — 组件卸载时取消 EventBus 订阅 ─────────────────────────────

  onScopeDispose(() => {
    eventBus.off('j3:equity-settled' as any, _onJ3EquitySettled)
    eventBus.off('m2:fx-diff' as any, _onM2FxDiff)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    // J3股份支付联动
    shareBasedVsJ3,
    // M2外币折算联动
    fxDiffVsM2,
    // 跨底稿引用
    crossWpReferences,
    // 内部状态（供调试/测试）
    _j3EquitySettled,
    _m2FxDiff,
  }
}

export default useM4CrossSheet
