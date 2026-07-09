/**
 * useM9CrossSheet — M9 其他综合收益跨sheet校验引擎 + G8/J2联动
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/
 * Task: 3.2
 * Requirements: 2.5, 4.1-4.8
 *
 * 职责：
 * 1. adjudicationVsDetail — M9-1审定表合计 vs M9-2明细表合计 交叉验证
 * 2. ociVsG8 — G8其他权益工具投资公允价值变动来源金额 vs 账面OCI增加 一致性校验
 * 3. ociVsJ2 — J2设定受益计划重计量来源金额 vs 账面OCI增加 一致性校验
 * 4. EventBus订阅 'g8:fair-value-changed' / 'j2:remeasured'
 * 5. cross_wp_references 关联 G8、J2
 *
 * 联动方向：
 *   G8其他权益工具投资 → 'g8:fair-value-changed' → ociVsG8（公允变动核对）
 *   J2设定受益计划 → 'j2:remeasured'           → ociVsJ2（重计量核对）
 *   M9-1 审定表合计 ↔ M9-2 明细表合计 双向勾稽
 *
 * 科目：4103 其他综合收益（**贷方/权益类！期末=期初+贷方-借方**）
 *
 * ADR-2: OCI是多来源汇聚的核对枢纽。
 *   其他综合收益汇聚多个来源：
 *   - G8其他权益工具投资公允价值变动（不可重分类）
 *   - J2设定受益计划重计量（不可重分类）
 *   - 其他债权投资公允变动/现金流量套期/外币折算差额（可重分类）
 *   M9-4核对表接收各来源EventBus订阅，验证OCI完整性与准确性。
 *
 * ADR-3: OCI按税后净额列示，核对差异=来源金额(税后)-账面OCI增加
 */
import { computed, ref, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useM9FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 交叉验证结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = M9-1审定表期末合计 - M9-2明细表合计 */
  diff: number
  /** |diff| < 阈值视为匹配 */
  isMatch: boolean
}

/** OCI来源 vs 账面 一致性校验结果（G8/J2通用） */
export interface OciConsistencyResult {
  /** 差额 = 来源金额(税后) - 账面OCI增加 */
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

/** OCI核对一致性阈值（0.01元，税后净额精度） */
const OCI_DIFF_THRESHOLD = 0.01

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
 * M9 跨sheet校验引擎 + G8/J2 OCI来源联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useM9FormData）
 */
export function useM9CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── EventBus 订阅的联动数据（reactive refs） ──────────────────────────────

  /** G8其他权益工具投资公允价值变动-来源金额(税后)（订阅 'g8:fair-value-changed'） */
  const _g8FairValueAmount = ref(0)

  /** J2设定受益计划重计量-来源金额(税后)（订阅 'j2:remeasured'） */
  const _j2RemeasuredAmount = ref(0)

  // ─── EventBus 订阅 handlers ─────────────────────────────────────────────

  /**
   * G8其他权益工具投资-公允价值变动（不可重分类进损益）
   * 载荷: { wpCode, afterTaxAmount, preTaxAmount, taxEffect, timestamp }
   * 取 afterTaxAmount（税后公允价值变动净额）
   *
   * 接收后自动持久化到 checklist_responses，防止刷新丢失（复盘铁律②）
   */
  function _onG8FairValueChanged(payload: any): void {
    const value = parseNum(payload?.afterTaxAmount ?? payload?.amount ?? payload?.fairValueChange)
    _g8FairValueAmount.value = value
    // 持久化到 checklist_responses（下次 selfLoad 可恢复，不依赖同会话事件）
    const persistItem: ChecklistResponse = {
      item_id: 'M9-cross-g8-fair-value-amount',
      conclusion: null,
      remark: String(value),
    }
    allResponses.value.set(persistItem.item_id, persistItem)
  }

  /**
   * J2设定受益计划-重计量变动额（不可重分类进损益）
   * 载荷: { wpCode, afterTaxAmount, preTaxAmount, taxEffect, timestamp }
   * 取 afterTaxAmount（税后重计量净额）
   *
   * 接收后自动持久化到 checklist_responses，防止刷新丢失（复盘铁律②）
   */
  function _onJ2Remeasured(payload: any): void {
    const value = parseNum(payload?.afterTaxAmount ?? payload?.amount ?? payload?.remeasuredAmount)
    _j2RemeasuredAmount.value = value
    // 持久化到 checklist_responses（下次 selfLoad 可恢复，不依赖同会话事件）
    const persistItem: ChecklistResponse = {
      item_id: 'M9-cross-j2-remeasured-amount',
      conclusion: null,
      remark: String(value),
    }
    allResponses.value.set(persistItem.item_id, persistItem)
  }

  // ─── 订阅 EventBus ─────────────────────────────────────────────────────────

  eventBus.on('g8:fair-value-changed' as any, _onG8FairValueChanged)
  eventBus.on('j2:remeasured' as any, _onJ2Remeasured)

  // ─── 初始化：从 allResponses 读取已持久化的联动数据 ─────────────────────────

  /**
   * 从 checklist_responses 恢复上次保存的联动数据
   * （EventBus 仅同会话有效，需要从持久化数据恢复）
   */
  function _restoreFromResponses(): void {
    const g8Resp = allResponses.value.get('M9-cross-g8-fair-value-amount')
    if (g8Resp?.remark) _g8FairValueAmount.value = parseNum(g8Resp.remark)

    const j2Resp = allResponses.value.get('M9-cross-j2-remeasured-amount')
    if (j2Resp?.remark) _j2RemeasuredAmount.value = parseNum(j2Resp.remark)
  }

  // 初次恢复
  _restoreFromResponses()

  // ─── 1. adjudicationVsDetail — 审定表M9-1合计 vs 明细表M9-2合计 ─────────

  /**
   * M9-1 审定表期末合计 应= M9-2 明细表（不可重分类+可重分类）期末金额合计
   * 差额 = 审定表期末合计 - 明细表合计
   *
   * 权益类贷方：期末=期初+贷方(OCI增加)-借方(OCI减少/重分类)
   *
   * 数据来源：
   * - M9-1 审定表期末合计存于 item_id: "M9-M9-1-total-end-audited"（remark=期末审定余额合计）
   * - M9-2 明细表合计存于 item_id: "M9-M9-2-total-end-amount"（remark=明细表OCI期末合计）
   *   或遍历 "M9-M9-2-row-*-end" 模式累加
   *
   * Req 2.5: M9-1审定表 SHALL 与M9-2明细合计交叉验证
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：M9-1期末审定余额合计
    const adjResp = allResponses.value.get('M9-M9-1-total-end-audited')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：优先取汇总行（M9-2合计行）
    const detailTotalResp = allResponses.value.get('M9-M9-2-total-end-amount')
    let detailTotal = parseNum(detailTotalResp?.remark)

    // 降级：如果汇总行无值，遍历明细行期末累加（不可重分类+可重分类）
    if (detailTotal === 0 && !detailTotalResp?.remark) {
      for (const [key, resp] of allResponses.value) {
        if (key.startsWith('M9-M9-2-row-') && key.endsWith('-end')) {
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

  // ─── 2. ociVsG8 — G8公允价值变动来源 vs 账面OCI增加 ──────────────────────

  /**
   * G8其他权益工具投资公允价值变动（不可重分类进损益）
   * 核对差异 = 来源金额(G8税后公允变动) - 账面OCI增加(M9-2/M9-4对应行)
   *
   * 数据来源：
   * - G8来源金额(税后): EventBus 'g8:fair-value-changed' 或持久化 "M9-cross-g8-fair-value-amount"
   * - 账面OCI增加: item_id "M9-M9-4-g8-booked-oci"（remark=M9-4核对表row15 账面OCI增加）
   *
   * Req 4.2: THE OCI_Engine SHALL 接收G8其他权益工具投资公允价值变动
   * Req 4.5: 核对差异=来源金额-账面OCI增加
   * Req 4.8: THE M9 SHALL 通过cross_wp_references关联G8、J2
   */
  const ociVsG8: ComputedRef<OciConsistencyResult> = computed(() => {
    // G8来源金额(税后公允价值变动)
    const g8Source = _g8FairValueAmount.value

    // M9-4核对表 G8对应行的账面OCI增加
    const bookedResp = allResponses.value.get('M9-M9-4-g8-booked-oci')
    const booked = parseNum(bookedResp?.remark)

    const diff = parseFloat((g8Source - booked).toFixed(2))
    return {
      diff,
      isConsistent: Math.abs(diff) <= OCI_DIFF_THRESHOLD,
    }
  })

  // ─── 3. ociVsJ2 — J2重计量来源 vs 账面OCI增加 ─────────────────────────────

  /**
   * J2设定受益计划重计量变动额（不可重分类进损益）
   * 核对差异 = 来源金额(J2税后重计量) - 账面OCI增加(M9-2/M9-4对应行)
   *
   * 数据来源：
   * - J2来源金额(税后): EventBus 'j2:remeasured' 或持久化 "M9-cross-j2-remeasured-amount"
   * - 账面OCI增加: item_id "M9-M9-4-j2-booked-oci"（remark=M9-4核对表row13 账面OCI增加）
   *
   * Req 4.3: THE OCI_Engine SHALL 接收J2设定受益计划重计量
   * Req 4.5: 核对差异=来源金额-账面OCI增加
   * Req 4.8: THE M9 SHALL 通过cross_wp_references关联G8、J2
   */
  const ociVsJ2: ComputedRef<OciConsistencyResult> = computed(() => {
    // J2来源金额(税后重计量)
    const j2Source = _j2RemeasuredAmount.value

    // M9-4核对表 J2对应行的账面OCI增加
    const bookedResp = allResponses.value.get('M9-M9-4-j2-booked-oci')
    const booked = parseNum(bookedResp?.remark)

    const diff = parseFloat((j2Source - booked).toFixed(2))
    return {
      diff,
      isConsistent: Math.abs(diff) <= OCI_DIFF_THRESHOLD,
    }
  })

  // ─── 4. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** M9 其他综合收益 cross_wp_references（接收G8公允变动 + J2重计量） */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'G8',
      label: 'G8其他权益工具投资公允价值变动→M9 OCI核对(不可重分类)',
      direction: 'from',
    },
    {
      targetWpCode: 'J2',
      label: 'J2设定受益计划重计量→M9 OCI核对(不可重分类)',
      direction: 'from',
    },
  ]

  // ─── 5. Cleanup — 组件卸载时取消 EventBus 订阅 ─────────────────────────────

  onScopeDispose(() => {
    eventBus.off('g8:fair-value-changed' as any, _onG8FairValueChanged)
    eventBus.off('j2:remeasured' as any, _onJ2Remeasured)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    // G8公允变动核对
    ociVsG8,
    // J2重计量核对
    ociVsJ2,
    // 跨底稿引用
    crossWpReferences,
    // 内部状态（供调试/测试）
    _g8FairValueAmount,
    _j2RemeasuredAmount,
  }
}

export default useM9CrossSheet
