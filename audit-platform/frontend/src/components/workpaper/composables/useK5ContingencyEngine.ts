/**
 * K5 预计负债 — 或有事项判断引擎（纯函数）
 *
 * CAS13 或有事项三级可能性判断：
 *   很可能 (very_likely, >50%)   → 确认预计负债 (recognize)
 *   可能   (possible, ≤50%非极小) → 披露或有负债 (disclose)
 *   极小可能 (remote)             → 不处理 (ignore)
 *
 * 设计原则：纯函数，无Vue响应式，无副作用，可PBT验证
 * determineRecognition 必须是确定性映射（相同输入永远得到相同输出）
 *
 * Spec: .kiro/specs/k5-provisions/ Requirements 4.1-4.2, 10.3
 */

// ─── Types ──────────────────────────────────────────────────────────────────

/** CAS13 三级可能性级别 */
export type LikelihoodLevel = 'very_likely' | 'possible' | 'remote'

/** 确认/披露/不处理决策 */
export type Recognition = 'recognize' | 'disclose' | 'ignore'

// ─── 判断函数 ───────────────────────────────────────────────────────────────

/**
 * 根据可能性级别判定确认/披露/不处理
 *
 * CAS13 或有事项准则：
 * - 很可能 (very_likely, >50%) → 'recognize' 确认预计负债 + 填最佳估计数
 * - 可能 (possible, ≤50%且非极小) → 'disclose' 披露或有负债（进附注）
 * - 极小可能 (remote) → 'ignore' 不处理
 *
 * 确定性映射：同一输入永远产生相同输出，无随机性
 *
 * @param level 可能性级别
 * @returns 确认决策
 *
 * Requirements 4.1, 4.2, 10.3
 */
export function determineRecognition(level: LikelihoodLevel): Recognition {
  switch (level) {
    case 'very_likely':
      return 'recognize'
    case 'possible':
      return 'disclose'
    case 'remote':
      return 'ignore'
  }
}
