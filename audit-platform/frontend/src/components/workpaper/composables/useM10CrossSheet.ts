/**
 * useM10CrossSheet — M10 其他权益工具跨sheet校验引擎 + 负债科目联动
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Task: 3.2
 * Requirements: 2.5, 4.3-4.4
 *
 * 职责：
 * 1. adjudicationVsDetail — M10-1审定表合计 vs M10-2明细表合计 交叉验证
 * 2. classificationConsistency — M10-4分类一致性（权益+负债===总额）
 * 3. liabilityItems — 负债部分提示（判定为负债的工具→提示计入负债科目）
 * 4. cross_wp_references 关联负债科目底稿
 *
 * 联动方向：
 *   M10-1审定表合计 ↔ M10-2明细表合计 双向勾稽
 *   M10-4区分检查 → 负债部分 → 负债科目（cross_wp_ref + GtIndexChip）
 *
 * 科目：4003 其他权益工具（**贷方/权益类！期末=期初+贷方-借方**）
 *
 * ADR-2: 负债与权益区分是核心（CAS37）
 *   永续债/优先股等金融工具需按CAS37判定分类为权益工具或金融负债。
 *   有合同义务→金融负债（计入负债科目）；无合同义务→权益工具（计入M10 4003）。
 *
 * ADR-3: 权益+负债金额守恒
 *   复合金融工具拆分为权益部分与负债部分，两者之和等于工具总额。
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcClassificationConsistency } from './useM10ClassificationEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** checklist_responses 条目（与 useM10FormData 一致） */
export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** 审定表 vs 明细表 交叉验证结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = M10-1审定表期末审定合计 - M10-2明细表期末合计 */
  diff: number
  /** |diff| < 阈值视为匹配 */
  isMatch: boolean
}

/** 分类金额守恒一致性校验结果 */
export interface ClassificationConsistencyResult {
  /** 是否一致（权益+负债===总额） */
  isConsistent: boolean
  /** 权益部分金额 */
  equity: number
  /** 负债部分金额 */
  liability: number
  /** 工具总额 */
  total: number
}

/** 判定为负债的工具项（需转入负债科目） */
export interface LiabilityItem {
  /** 工具名称 */
  name: string
  /** 金额 */
  amount: number
  /** 目标负债科目 */
  targetAccount: string
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
 * M10 跨sheet校验引擎 + 负债科目联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useM10FormData）
 */
export function useM10CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── 1. adjudicationVsDetail — 审定表M10-1合计 vs 明细表M10-2合计 ────────

  /**
   * M10-1 审定表期末审定合计 应= M10-2 明细表各工具期末金额合计
   * 差额 = 审定表期末合计 - 明细表合计
   *
   * 权益类贷方：期末=期初+贷方-借方
   *
   * 数据来源：
   * - M10-1 审定表期末合计存于 item_id: "M10-1-total-audited"（remark=期末审定余额合计）
   * - M10-2 明细表合计存于 item_id: "M10-2-total-end-balance"（remark=所有工具期末合计）
   *   或遍历 "M10-2-*-end-balance" 模式累加
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：M10-1期末审定余额合计
    const adjResp = allResponses.value.get('M10-1-total-audited')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：优先取汇总行
    const detailTotalResp = allResponses.value.get('M10-2-total-end-balance')
    let detailTotal = parseNum(detailTotalResp?.remark)

    // 降级：如果汇总行无值，遍历明细行期末累加
    if (detailTotal === 0 && !detailTotalResp?.remark) {
      for (const [key, resp] of allResponses.value) {
        if (key.startsWith('M10-2-') && key.endsWith('-end-balance') && key !== 'M10-2-total-end-balance') {
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

  // ─── 2. classificationConsistency — M10-4分类金额守恒 ─────────────────────

  /**
   * M10-4 负债与权益区分检查表底部守恒校验：
   * 权益部分金额 + 负债部分金额 === 工具总额
   *
   * 使用 calcClassificationConsistency 纯函数（来自 useM10ClassificationEngine）
   *
   * 数据来源：
   * - 权益部分：item_id "M10-4-equity-total"（remark=归入权益的金额合计）
   * - 负债部分：item_id "M10-4-liability-total"（remark=归入负债的金额合计）
   * - 工具总额：item_id "M10-4-instrument-total"（remark=所有工具总额）
   */
  const classificationConsistency: ComputedRef<ClassificationConsistencyResult> = computed(() => {
    const equityResp = allResponses.value.get('M10-4-equity-total')
    const equity = parseNum(equityResp?.remark)

    const liabilityResp = allResponses.value.get('M10-4-liability-total')
    const liability = parseNum(liabilityResp?.remark)

    const totalResp = allResponses.value.get('M10-4-instrument-total')
    const total = parseNum(totalResp?.remark)

    const isConsistent = calcClassificationConsistency(equity, liability, total)

    return {
      isConsistent,
      equity,
      liability,
      total,
    }
  })

  // ─── 3. liabilityItems — 判定为负债的工具（需转入负债科目） ────────────────

  /**
   * 从 M10-4 检查表中过滤出分类结论为'liability'的工具
   * 提示用户：这些工具应计入负债科目而非权益
   *
   * 数据来源：
   * - 遍历 "M10-4-item-*-classification" → conclusion === 'liability'
   * - 工具名：item_id "M10-4-item-{n}-name"（remark=工具名称）
   * - 金额：item_id "M10-4-item-{n}-amount"（remark=金额）
   * - 目标科目：默认 '应付债券/其他应付款' 等负债科目
   */
  const liabilityItems: ComputedRef<LiabilityItem[]> = computed(() => {
    const items: LiabilityItem[] = []

    for (const [key, resp] of allResponses.value) {
      // 匹配分类结论条目：M10-4-item-{n}-classification
      if (key.startsWith('M10-4-item-') && key.endsWith('-classification')) {
        if (resp.conclusion === 'liability') {
          // 提取序号: M10-4-item-{n}-classification → n
          const match = key.match(/^M10-4-item-(\d+)-classification$/)
          if (!match) continue
          const idx = match[1]

          // 工具名称
          const nameResp = allResponses.value.get(`M10-4-item-${idx}-name`)
          const name = nameResp?.remark || `工具${idx}`

          // 金额
          const amountResp = allResponses.value.get(`M10-4-item-${idx}-amount`)
          const amount = parseNum(amountResp?.remark)

          // 目标科目（从检查表结论区获取，或使用默认负债科目）
          const accountResp = allResponses.value.get(`M10-4-item-${idx}-target-account`)
          const targetAccount = accountResp?.remark || '应付债券/其他应付款'

          items.push({ name, amount, targetAccount })
        }
      }
    }

    return items
  })

  // ─── 4. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** M10 其他权益工具 cross_wp_references（负债部分输出到负债科目） */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'L4',
      label: 'M10负债部分→L4应付债券（永续债分类为负债时）',
      direction: 'to',
    },
    {
      targetWpCode: 'L7',
      label: 'M10负债部分→L7其他非流动负债（优先股分类为负债时）',
      direction: 'to',
    },
    {
      targetWpCode: 'M9',
      label: 'M9其他综合收益→M10权益工具公允价值变动',
      direction: 'from',
    },
  ]

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 审定表 vs 明细表勾稽
    adjudicationVsDetail,
    // 分类金额守恒
    classificationConsistency,
    // 负债部分工具列表（提示转入负债科目）
    liabilityItems,
    // 跨底稿引用
    crossWpReferences,
  }
}

export default useM10CrossSheet
