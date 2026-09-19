/**
 * useLmnTbReconcile — L/M/N 循环审定表 TB 核对 composable
 *
 * 从 htmlData.trial_balance 取 TB 数据，与审定合计对比差异。
 * 供各循环审定表组件接入（一行 import 即用）。
 *
 * 用法示例：
 * ```ts
 * const tbReconcile = useLmnTbReconcile(
 *   computed(() => props.htmlData),
 *   computed(() => total.value.endAudited),
 * )
 * ```
 *
 * 模板：
 * ```html
 * <el-alert v-if="tbReconcile.value.hasTb"
 *   :type="tbReconcile.value.hasWarning ? 'warning' : 'success'"
 *   :title="tbReconcile.value.hasWarning
 *     ? `审定合计与试算平衡表核对不一致（差异 ${fmtAmount(tbReconcile.value.diff)}）`
 *     : '审定合计与试算平衡表核对一致'"
 *   :closable="false" show-icon />
 * ```
 */
import { computed, type Ref, type ComputedRef } from 'vue'

export interface TbReconcileResult {
  /** 试算平衡表数（期末余额或损益类发生额） */
  tbAmount: number
  /** 期初余额 */
  tbBeginAmount: number
  /** 审定合计 vs TB 差异（正=审定>TB） */
  diff: number
  /** 是否有 TB 数据（守卫：全 0 时不渲染核对行，避免 TB 未导入时误报） */
  hasTb: boolean
  /** 差异是否超阈值（绝对值>1元） */
  hasWarning: boolean
}

/**
 * 从 htmlData.trial_balance 解析 TB 核对数据
 *
 * @param htmlData - render-config 返回的 htmlData（含 trial_balance 字段）
 * @param totalAudited - 审定表期末审定合计（Ref 或 ComputedRef）
 * @param options.isIncome - 是否为损益类（end_balance 存的是净发生额=借-贷）
 */
export function useLmnTbReconcile(
  htmlData: Ref<any> | ComputedRef<any>,
  totalAudited: Ref<number> | ComputedRef<number>,
  options?: { isIncome?: boolean },
): ComputedRef<TbReconcileResult> {
  return computed(() => {
    const tb = htmlData.value?.trial_balance
    if (!tb) {
      return { tbAmount: 0, tbBeginAmount: 0, diff: 0, hasTb: false, hasWarning: false }
    }

    const endBalance = Number(tb.end_balance) || 0
    const beginBalance = Number(tb.begin_balance) || 0

    // 损益类 end_balance 已存净发生额（debit-credit），与余额类统一消费
    const tbAmount = endBalance
    const tbBeginAmount = beginBalance

    const hasTb = tbAmount !== 0 || tbBeginAmount !== 0
    const auditedVal = totalAudited.value || 0
    const diff = auditedVal - tbAmount

    return {
      tbAmount,
      tbBeginAmount,
      diff,
      hasTb,
      hasWarning: hasTb && Math.abs(diff) > 1,
    }
  })
}

export default useLmnTbReconcile
