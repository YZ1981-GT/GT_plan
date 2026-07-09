/**
 * useM7CrossSheet — M7 专项储备跨sheet校验引擎 + H1资本化联动
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Task: 3.2
 * Requirements: 2.5, 5.1
 *
 * 职责：
 * 1. adjudicationVsDetail — M7-1审定表合计 vs M7-2明细表合计 交叉验证
 * 2. capitalExpToH1 — M7-2资本化支出 → H1固定资产 cross_wp_reference + GtIndexChip
 * 3. EventBus订阅 'h1:fixed-asset-confirmed' 接收H1确认反馈
 * 4. cross_wp_references 关联 H1
 *
 * 联动方向：
 *   M7-2 资本化支出 → H1固定资产（形成固定资产+全额折旧冲减专项储备）
 *   M7-1 审定表合计 ↔ M7-2 明细表合计 双向勾稽
 *
 * 科目：4201 专项储备（**贷方/权益类！期末=期初+贷方-借方**）
 *
 * ADR-3: 资本性支出形成固定资产（联动H1），同时全额计提折旧冲减专项储备计入累计折旧特殊科目。
 *   借:固定资产 贷:在建工程(或银行存款)
 *   借:专项储备 贷:累计折旧—专项储备折旧
 *   两笔分录同时发生，需与H1固定资产底稿交叉核对。
 */
import { computed, ref, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

/** checklist_responses 基础类型（与 useM7FormData 对齐） */
export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** 审定表 vs 明细表 交叉验证结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = M7-1审定表期末合计 - M7-2明细表合计 */
  diff: number
  /** |diff| < 阈值视为匹配 */
  isMatch: boolean
}

/** 资本化支出 → H1联动状态 */
export interface CapitalExpToH1Result {
  /** M7-2 资本化支出合计金额 */
  capitalExpTotal: number
  /** H1已确认的转固金额（EventBus接收） */
  h1ConfirmedAmount: number
  /** 差额 = M7资本化支出 - H1已确认转固 */
  diff: number
  /** 是否一致 */
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

/** H1联动一致性阈值（1元内，考虑四舍五入） */
const H1_DIFF_THRESHOLD = 1

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
 * M7 跨sheet校验引擎 + H1资本化联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useM7FormData）
 */
export function useM7CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── EventBus 订阅的联动数据（reactive refs） ──────────────────────────────

  /** H1固定资产已确认的专项储备转固金额（订阅 'h1:fixed-asset-confirmed'） */
  const _h1ConfirmedAmount = ref(0)

  // ─── EventBus 订阅 handlers ─────────────────────────────────────────────

  /**
   * H1固定资产-转固确认
   * 载荷: { wpCode, amount, source, timestamp }
   * 取 amount（专项储备转固金额）
   *
   * 接收后自动持久化到 checklist_responses，防止刷新丢失（复盘铁律②）
   */
  function _onH1FixedAssetConfirmed(payload: any): void {
    const value = parseNum(payload?.amount ?? payload?.capitalExpAmount)
    _h1ConfirmedAmount.value = value
    // 持久化到 checklist_responses（下次 selfLoad 可恢复，不依赖同会话事件）
    const persistItem: ChecklistResponse = {
      item_id: 'M7-cross-h1-confirmed-amount',
      conclusion: null,
      remark: String(value),
    }
    allResponses.value.set(persistItem.item_id, persistItem)
  }

  // ─── 订阅 EventBus ─────────────────────────────────────────────────────────

  eventBus.on('h1:fixed-asset-confirmed' as any, _onH1FixedAssetConfirmed)

  // ─── 初始化：从 allResponses 读取已持久化的联动数据 ─────────────────────────

  /**
   * 从 checklist_responses 恢复上次保存的联动数据
   * （EventBus 仅同会话有效，需要从持久化数据恢复）
   */
  function _restoreFromResponses(): void {
    const h1Resp = allResponses.value.get('M7-cross-h1-confirmed-amount')
    if (h1Resp?.remark) _h1ConfirmedAmount.value = parseNum(h1Resp.remark)
  }

  // 初次恢复
  _restoreFromResponses()

  // ─── 1. adjudicationVsDetail — 审定表M7-1合计 vs 明细表M7-2合计 ─────────

  /**
   * M7-1 审定表期末合计 应= M7-2 明细表（计提+使用）期末金额合计
   * 差额 = 审定表期末合计 - 明细表合计
   *
   * 权益类贷方：期末=期初+贷方(计提)-借方(使用)
   *
   * 数据来源：
   * - M7-1 审定表期末合计存于 item_id: "M7-M7-1-total-end-audited"（remark=期末审定余额合计）
   * - M7-2 明细表合计存于 item_id: "M7-M7-2-total-end-amount"（remark=明细表期末合计）
   *   或遍历 "M7-M7-2-row-*-end" 模式累加
   *
   * 对应xlsx: O17 = M7-1审定期末合计 应= M7-2明细汇总行
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：M7-1期末审定余额合计
    const adjResp = allResponses.value.get('M7-M7-1-total-end-audited')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：优先取汇总行（M7-2合计行）
    const detailTotalResp = allResponses.value.get('M7-M7-2-total-end-amount')
    let detailTotal = parseNum(detailTotalResp?.remark)

    // 降级：如果汇总行无值，遍历明细行期末累加
    if (detailTotal === 0 && !detailTotalResp?.remark) {
      for (const [key, resp] of allResponses.value) {
        if (key.startsWith('M7-M7-2-row-') && key.endsWith('-end')) {
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

  // ─── 2. capitalExpToH1 — M7-2资本化支出 → H1固定资产联动 ──────────────────

  /**
   * M7-2 明细表中"本期使用(资本化)"列合计应= H1固定资产中专项储备转入金额
   *
   * ADR-3: 资本性支出形成固定资产：
   *   借:固定资产 贷:在建工程
   *   借:专项储备 贷:累计折旧—专项储备折旧
   * 因此 M7 借方减少(资本化) 应在 H1 固定资产增加中可追溯。
   *
   * 数据来源：
   * - M7-2 资本化支出合计：item_id "M7-M7-2-total-capital-exp"
   *   或遍历 "M7-M7-2-row-*-capital-exp" 模式累加
   * - H1 已确认：EventBus 'h1:fixed-asset-confirmed' 或持久化 "M7-cross-h1-confirmed-amount"
   */
  const capitalExpToH1: ComputedRef<CapitalExpToH1Result> = computed(() => {
    // M7-2 资本化支出合计
    const capitalExpResp = allResponses.value.get('M7-M7-2-total-capital-exp')
    let capitalExpTotal = parseNum(capitalExpResp?.remark)

    // 降级：遍历明细行资本化支出累加
    if (capitalExpTotal === 0 && !capitalExpResp?.remark) {
      for (const [key, resp] of allResponses.value) {
        if (key.startsWith('M7-M7-2-row-') && key.endsWith('-capital-exp')) {
          capitalExpTotal += parseNum(resp.remark)
        }
      }
    }

    // H1已确认的转固金额
    const h1Amount = _h1ConfirmedAmount.value

    const diff = parseFloat((capitalExpTotal - h1Amount).toFixed(2))
    return {
      capitalExpTotal,
      h1ConfirmedAmount: h1Amount,
      diff,
      isConsistent: Math.abs(diff) <= H1_DIFF_THRESHOLD,
    }
  })

  // ─── 3. M7→H1 发布：资本化支出金额通知 ────────────────────────────────────

  /**
   * 发布M7资本化支出金额 → H1固定资产核对
   *
   * ADR-3: 专项储备资本性支出形成固定资产，H1应确认对应金额。
   * 事件名: 'm7:capital-exp-to-h1'
   * 载荷: { wpCode, capitalExpAmount, items, timestamp }
   */
  function publishCapitalExpToH1(capitalExpAmount: number, items?: string[]): void {
    const payload = {
      wpCode: 'M7',
      capitalExpAmount,
      items: items ?? [],
      timestamp: Date.now(),
    }
    eventBus.emit('m7:capital-exp-to-h1', payload)
  }

  // ─── 4. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** M7 专项储备 cross_wp_references（资本化支出→H1固定资产） */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'H1',
      label: 'M7资本化支出→H1固定资产(专项储备转固)',
      direction: 'to',
    },
    {
      targetWpCode: 'H1',
      label: 'H1固定资产确认→M7资本化核对',
      direction: 'from',
    },
  ]

  // ─── 5. Cleanup — 组件卸载时取消 EventBus 订阅 ─────────────────────────────

  onScopeDispose(() => {
    eventBus.off('h1:fixed-asset-confirmed' as any, _onH1FixedAssetConfirmed)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    // H1资本化联动
    capitalExpToH1,
    // M7→H1 发布
    publishCapitalExpToH1,
    // 跨底稿引用
    crossWpReferences,
    // 内部状态（供调试/测试）
    _h1ConfirmedAmount,
  }
}

export default useM7CrossSheet
