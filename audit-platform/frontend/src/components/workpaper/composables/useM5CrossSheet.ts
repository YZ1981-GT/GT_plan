/**
 * useM5CrossSheet — M5 盈余公积跨sheet校验引擎 + M6联动
 *
 * Spec: .kiro/specs/m5-surplus-reserve/
 * Task: 3.2
 * Requirements: 2.5, 4.2
 *
 * 职责：
 * 1. adjudicationVsDetail — M5-1审定表合计(row11) vs M5-2明细表合计(row16) 交叉验证
 * 2. accrualVsM6 — M5-4计提基数(净利润) vs M6净利润实际值 一致性校验
 * 3. EventBus订阅 'm6:net-profit'
 * 4. cross_wp_references 关联 M6
 *
 * 联动方向：
 *   M6未分配利润 → 'm6:net-profit' → accrualVsM6（M5-4计提基数一致性）
 *   M5-1审定表合计 ↔ M5-2明细表合计 双向勾稽
 *
 * 科目：4101 盈余公积（**贷方/权益类！期末=期初+贷方-借方**）
 *
 * ADR-2: 法定盈余公积计提按净利润(弥补以前年度亏损后)的10%计提。
 *   M6未分配利润提供计提基数（净利润），M5计提后影响M6可供分配利润。
 *   M5-M6形成利润分配闭环。
 */
import { computed, ref, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useM5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 交叉验证结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = M5-1审定表期末合计 - M5-2明细表合计(法定+任意盈余公积) */
  diff: number
  /** |diff| < 阈值视为匹配 */
  isMatch: boolean
}

/** M5-4计提基数 vs M6净利润 一致性校验结果 */
export interface AccrualVsM6Result {
  /** 差额 = M5-4使用的计提基数 - M6实际净利润 */
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

/** M6净利润一致性阈值（0.01元，会计精度） */
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
 * M5 跨sheet校验引擎 + M6净利润联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useM5FormData）
 */
export function useM5CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── EventBus 订阅的联动数据（reactive refs） ──────────────────────────────

  /** M6未分配利润的净利润/计提基数（订阅 'm6:net-profit'） */
  const _m6NetProfit = ref(0)

  // ─── EventBus 订阅 handlers ─────────────────────────────────────────────

  /**
   * M6未分配利润-净利润确认
   * 载荷: { wpCode, netProfit, accrualBase, timestamp }
   * 取 netProfit 或 accrualBase（弥补以前年度亏损后的计提基数）
   *
   * 接收后自动持久化到 checklist_responses，防止刷新丢失（复盘铁律②）
   */
  function _onM6NetProfit(payload: {
    wpCode?: string
    netProfit?: number
    accrualBase?: number
    amount?: number
    timestamp?: number
  }): void {
    const value = parseNum(payload?.accrualBase ?? payload?.netProfit ?? payload?.amount)
    _m6NetProfit.value = value
    // 持久化到 checklist_responses（下次 selfLoad 可恢复，不依赖同会话事件）
    const persistItem: ChecklistResponse = {
      item_id: 'M5-cross-m6-net-profit',
      conclusion: null,
      remark: String(value),
    }
    allResponses.value.set(persistItem.item_id, persistItem)
  }

  // ─── 订阅 EventBus ─────────────────────────────────────────────────────────

  eventBus.on('m6:net-profit', _onM6NetProfit)

  // ─── 初始化：从 allResponses 读取已持久化的联动数据 ─────────────────────────

  /**
   * 从 checklist_responses 恢复上次保存的联动数据
   * （EventBus 仅同会话有效，需要从持久化数据恢复）
   */
  function _restoreFromResponses(): void {
    const m6Resp = allResponses.value.get('M5-cross-m6-net-profit')
    if (m6Resp?.remark) _m6NetProfit.value = parseNum(m6Resp.remark)
  }

  // 初次恢复
  _restoreFromResponses()

  // ─── 1. adjudicationVsDetail — 审定表M5-1合计 vs 明细表M5-2合计 ─────────

  /**
   * M5-1 审定表期末合计(row11) 应= M5-2 明细表（法定+任意盈余公积）期末金额合计(row16)
   * 差额 = 审定表期末合计 - 明细表合计
   *
   * 权益类贷方：期末=期初+贷方-借方
   *
   * 数据来源：
   * - M5-1 审定表期末合计存于 item_id: "M5-M5-1-total-end-audited"（remark=期末审定余额合计）
   * - M5-2 明细表合计存于 item_id: "M5-M5-2-total-end-amount"（remark=法定+任意盈余公积期末合计）
   *   或遍历 "M5-M5-2-statutory-*-end" + "M5-M5-2-discretionary-*-end" 模式累加
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：M5-1期末审定余额合计
    const adjResp = allResponses.value.get('M5-M5-1-total-end-audited')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：优先取汇总行（M5-2合计行）
    const detailTotalResp = allResponses.value.get('M5-M5-2-total-end-amount')
    let detailTotal = parseNum(detailTotalResp?.remark)

    // 降级：如果汇总行无值，遍历明细行期末累加（法定+任意盈余公积）
    if (detailTotal === 0 && !detailTotalResp?.remark) {
      for (const [key, resp] of allResponses.value) {
        if (
          (key.startsWith('M5-M5-2-statutory-') || key.startsWith('M5-M5-2-discretionary-')) &&
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

  // ─── 2. accrualVsM6 — M5-4计提基数 vs M6实际净利润 ────────────────────────

  /**
   * M5-4 计提检查表使用的"计提基数（净利润）"应= M6未分配利润中实际确认的净利润
   * 差额 = M5-4使用的计提基数 - M6实际净利润
   *
   * 数据来源：
   * - M5-4计提基数：item_id "M5-M5-4-accrual-base"（remark=净利润-弥补以前年度亏损）
   * - M6实际净利润：EventBus 'm6:net-profit' 或持久化 "M5-cross-m6-net-profit"
   */
  const accrualVsM6: ComputedRef<AccrualVsM6Result> = computed(() => {
    // M5-4使用的计提基数
    const accrualBaseResp = allResponses.value.get('M5-M5-4-accrual-base')
    const accrualBase = parseNum(accrualBaseResp?.remark)

    // M6实际净利润
    const m6Amount = _m6NetProfit.value

    const diff = parseFloat((accrualBase - m6Amount).toFixed(2))
    return {
      diff,
      isConsistent: Math.abs(diff) <= DIFF_THRESHOLD,
    }
  })

  // ─── 3. M5→M6 发布：计提盈余公积金额 → M6可供分配利润 ──────────────────────

  /**
   * 发布M5盈余公积计提金额 → M6可供分配利润
   *
   * ADR-3: M5计提盈余公积后回流影响M6的可供分配利润。M5-M6形成利润分配闭环。
   * 事件名: 'm5:surplus-accrual'
   * 载荷: { statutoryAccrual, discretionaryAccrual, totalAccrual, wpCode, timestamp }
   */
  function publishAccrualToM6(
    statutoryAccrual: number,
    discretionaryAccrual: number,
  ): void {
    const payload = {
      wpCode: 'M5',
      statutoryAccrual,
      discretionaryAccrual,
      totalAccrual: statutoryAccrual + discretionaryAccrual,
      timestamp: Date.now(),
    }
    eventBus.emit('m5:surplus-accrual', payload)
  }

  // ─── 4. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** M5 盈余公积 cross_wp_references（接收M6净利润 + 输出计提金额到M6） */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'M6',
      label: 'M6未分配利润-净利润→M5计提基数',
      direction: 'from',
    },
    {
      targetWpCode: 'M6',
      label: 'M5计提盈余公积→M6可供分配利润',
      direction: 'to',
    },
    {
      targetWpCode: 'M1',
      label: 'M5计提盈余公积→M1利润分配',
      direction: 'to',
    },
  ]

  // ─── 5. Cleanup — 组件卸载时取消 EventBus 订阅 ─────────────────────────────

  onScopeDispose(() => {
    eventBus.off('m6:net-profit', _onM6NetProfit)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    // M6净利润联动
    accrualVsM6,
    // M5→M6 发布
    publishAccrualToM6,
    // 跨底稿引用
    crossWpReferences,
    // 内部状态（供调试/测试）
    _m6NetProfit,
  }
}

export default useM5CrossSheet
