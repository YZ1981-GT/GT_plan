/**
 * useDisclosureAdjudicationReconcile — 审定表↔披露表一致性差异告警（纯计算，跨科目共享）
 *
 * 背景：D1/D2 已有「审定合计 vs 披露合计 差异告警 + 从审定表刷新」范式，本 composable
 * 把该告警口径收敛为单一真源，供 D3/D5/D6/D7 披露 tab 复用（各科目审定/披露合计
 * getter 各不相同，留在各 tab 提供；此处只做分级与文案）。
 *
 * 审定合计 = 审定表 X-1 各分类行期末审定数之和（各 tab 从跨 sheet 键聚合传入）。
 * 披露合计 = 披露表主表合计行期末金额（各 tab 从本地 computed 传入）。
 *
 * 不含任何科目特定键，纯计算：diff / level / message。
 */
import { computed, type ComputedRef } from 'vue'

export type ReconcileLevel = 'ok' | 'warn' | 'no-data'

export interface DisclosureAdjudicationReconcileOptions {
  /** 审定表各分类行期末审定数之和 */
  auditedTotal: () => number
  /** 披露表主表合计行期末金额 */
  disclosureTotal: () => number
  /** 审定合计是否已取到（无值时不误报差异，仅提示未取数） */
  hasAudited?: () => boolean
  /** 允许容差（元），默认 1 元 */
  tolerance?: number
}

export interface DisclosureAdjudicationReconcileResult {
  diff: ComputedRef<number>
  level: ComputedRef<ReconcileLevel>
  message: ComputedRef<string>
}

function fmtAmt(v: number): string {
  return (Number.isFinite(v) ? v : 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function useDisclosureAdjudicationReconcile(
  opts: DisclosureAdjudicationReconcileOptions,
): DisclosureAdjudicationReconcileResult {
  const tolerance = opts.tolerance ?? 1

  const auditedVal = computed(() => {
    const n = Number(opts.auditedTotal())
    return Number.isFinite(n) ? n : 0
  })
  const disclosureVal = computed(() => {
    const n = Number(opts.disclosureTotal())
    return Number.isFinite(n) ? n : 0
  })

  // 无审定合计（未取到）：以 opts.hasAudited 为准；未提供则用「审定合计为 0」近似判定
  const audAvailable = computed(() => {
    if (opts.hasAudited) return !!opts.hasAudited()
    return auditedVal.value !== 0
  })

  const diff = computed(() => auditedVal.value - disclosureVal.value)

  const level = computed<ReconcileLevel>(() => {
    if (!audAvailable.value) return 'no-data'
    return Math.abs(diff.value) > tolerance ? 'warn' : 'ok'
  })

  const message = computed(() => {
    if (level.value === 'no-data') {
      return '未取到审定表合计（审定表尚未编制或未取数），暂不校对'
    }
    const base = `审定表合计 ${fmtAmt(auditedVal.value)} / 披露表合计 ${fmtAmt(disclosureVal.value)}`
    if (level.value === 'ok') {
      return `${base}，核对一致`
    }
    return `${base}，差异 ${fmtAmt(diff.value)}（超过 ${tolerance} 元）`
  })

  return { diff, level, message }
}
