/**
 * useK11CrossSheet — K11 资产减值损失跨Sheet交叉验证 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('K11-{sheet}-{field}')?.remark 存数值。
 *
 * 跨Sheet映射（数据流图）：
 * - K11-1 审定表合计 vs K11-2 明细表合计（adjudicationVsDetail）
 * - K11-2 各行来源金额 vs F2/H1/I1/I3 源底稿减值计提金额（sourceReconcile）
 *
 * 科目方向：
 * - 6701 资产减值损失（借方/损益类）：取发生额=借方发生-贷方发生(转回红冲)
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/
 * Task: 3.2
 * Requirements: 2.5, 3.3, 4.2-4.4
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CrossSheetCheckResult {
  /** 差额：左侧(审定表) - 右侧(明细表) */
  diff: number
  /** 是否匹配（|diff| < 0.01） */
  isMatch: boolean
}

export interface SourceReconcileItem {
  /** 资产类别标识 */
  category: string
  /** 差额：K11金额 - 源底稿金额 */
  diff: number
  /** 是否匹配（|diff| < 0.01） */
  isMatch: boolean
}

// ─── 减值来源类别常量 ──────────────────────────────────────────────────────

/** 各资产减值损失来源类别（与K11-2明细行对应） */
export const IMPAIRMENT_SOURCE_CATEGORIES = [
  { key: 'inventory', label: '存货跌价损失', sourceWp: 'F2' },
  { key: 'fixed-asset', label: '固定资产减值损失', sourceWp: 'H1' },
  { key: 'intangible', label: '无形资产减值损失', sourceWp: 'I1' },
  { key: 'goodwill', label: '商誉减值损失', sourceWp: 'I3' },
  { key: 'construction', label: '在建工程减值损失', sourceWp: 'H2' },
  { key: 'equity', label: '长期股权投资减值损失', sourceWp: 'G7' },
  { key: 'other', label: '其他资产减值损失', sourceWp: '' },
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 从 allResponses Map 中获取指定 item_id 的数值（尝试 remark → conclusion）。
 * NaN/null/undefined → 0
 */
function getNumFromMap(map: Map<string, any>, key: string): number {
  const item = map.get(key)
  if (!item) return 0
  const raw = item.remark ?? item.conclusion
  if (raw == null) return 0
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * K11 跨Sheet computed links：
 * - K11-1 审定表审定合计 ↔ K11-2 明细表发生额合计
 * - K11-2 各行来源金额 ↔ 源底稿(F2/H1/I1/I3等)减值计提金额
 *
 * @param allResponses 全部 checklist_responses 的响应式 Map
 */
export function useK11CrossSheet(allResponses: Ref<Map<string, any>>): {
  adjudicationVsDetail: ComputedRef<CrossSheetCheckResult>
  sourceReconcile: ComputedRef<SourceReconcileItem[]>
} {
  // 辅助：从 allResponses 提取数值
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // ═══ adjudicationVsDetail: K11-1 审定表合计 vs K11-2 明细表合计（Req 2.5）═══

  /**
   * K11-1 审定表资产减值损失审定合计 与 K11-2 明细表本期发生额合计交叉验证。
   * diff = K11-1 审定 total - K11-2 明细发生额 total
   * isMatch = |diff| < 0.01（分以内视为一致）
   *
   * 损益类：各类别减值合计（审定表） == 明细表逐项累计
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjTotal = getNum('K11-1-audited-total')
    const detailTotal = getNum('K11-2-total-occurrence')
    const diff = adjTotal - detailTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ sourceReconcile: K11-2 各行 vs 源底稿减值计提（Req 4.2-4.4）═══

  /**
   * K11-2 明细表各类别金额 与对应源底稿(F2/H1/I1/I3等)减值计提金额交叉核对。
   * diff = K11-2 本类别发生额 - 源底稿对应减值计提金额
   * isMatch = |diff| < 0.01
   *
   * 差异非零需关注：可能是①源底稿未编制 ②数据未刷新 ③分类错误
   * 源底稿数据来源：EventBus subscribe + allResponses 存储
   */
  const sourceReconcile: ComputedRef<SourceReconcileItem[]> = computed(() => {
    return IMPAIRMENT_SOURCE_CATEGORIES.map((cat) => {
      // K11-2 中该类别的本期发生额
      const k11Amount = getNum(`K11-2-${cat.key}-occurrence`)
      // 源底稿减值计提金额（通过 EventBus 接收后存入 allResponses）
      const sourceAmount = getNum(`K11-2-${cat.key}-source-amount`)
      const diff = k11Amount - sourceAmount
      return {
        category: cat.key,
        diff,
        isMatch: Math.abs(diff) < 0.01,
      }
    })
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
    sourceReconcile,
  }
}

export default useK11CrossSheet
