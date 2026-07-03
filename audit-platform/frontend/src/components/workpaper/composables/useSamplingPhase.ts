/**
 * useSamplingPhase — 阶段隔离逻辑 composable
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Task: 4.2
 *
 * 职责：
 * - 三种视图模式切换（preliminary / final / all）
 * - 按视图模式过滤 samples
 * - 行编辑权限判定（年审阶段禁止编辑预审行）
 * - 年审阶段强制 append 填充模式
 * - 获取预审已抽凭证号（用于年审排除）
 *
 * Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 9.4
 */

import { ref, computed } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import type { Phase, SampledVoucher } from './useSamplingAlgorithms'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface PhaseOptions {
  phase: Ref<Phase>
  samples: Ref<SampledVoucher[]>
}

export type ViewMode = 'preliminary' | 'final' | 'all'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * 阶段隔离逻辑 composable
 *
 * 核心规则：
 * - 年审阶段（phase='final'）时，预审行（row.phase='preliminary'）不可编辑
 * - 年审阶段填充策略强制为 append，不允许 replace/merge 覆盖预审数据
 * - 视图模式过滤正确分区显示
 *
 * @param options.phase 当前审计阶段 ref
 * @param options.samples 所有已填充的凭证样本 ref
 */
export function useSamplingPhase(options: PhaseOptions) {
  const { phase, samples } = options

  // ─── 视图模式 ────────────────────────────────────────────────────────────────

  /** 当前视图模式，默认显示全部 */
  const viewMode = ref<ViewMode>('all')

  // ─── 计算属性 ────────────────────────────────────────────────────────────────

  /** 预审阶段的样本 */
  const preliminarySamples: ComputedRef<SampledVoucher[]> = computed(() =>
    samples.value.filter(s => s.phase === 'preliminary'),
  )

  /** 年审阶段的样本 */
  const finalSamples: ComputedRef<SampledVoucher[]> = computed(() =>
    samples.value.filter(s => s.phase === 'final'),
  )

  /**
   * 按 viewMode 过滤后的可见样本
   *
   * - 'preliminary': 仅显示 phase='preliminary' 的行
   * - 'final': 仅显示 phase='final' 的行
   * - 'all': 显示全部行
   */
  const visibleSamples: ComputedRef<SampledVoucher[]> = computed(() => {
    switch (viewMode.value) {
      case 'preliminary':
        return preliminarySamples.value
      case 'final':
        return finalSamples.value
      case 'all':
        return samples.value
    }
  })

  /**
   * 年审阶段强制 append 填充模式
   *
   * 当 phase='final' 时返回 true，表示禁用 replace/merge 选项
   * Requirement 5.5: 年审阶段执行填充时强制使用 append 模式
   */
  const isFillModeRestricted: ComputedRef<boolean> = computed(() =>
    phase.value === 'final',
  )

  // ─── 方法 ────────────────────────────────────────────────────────────────────

  /**
   * 判断行是否可编辑
   *
   * 规则：
   * - 当前 phase='final' 且 row.phase='preliminary' → 不可编辑（返回 false）
   * - 其他情况 → 可编辑（返回 true）
   *
   * Requirement 5.2: 年审阶段对预审行设为只读
   * Requirement 9.4: 年审+预审行禁止编辑
   *
   * @param row 目标行
   */
  function isRowEditable(row: SampledVoucher): boolean {
    if (phase.value === 'final' && row.phase === 'preliminary') {
      return false
    }
    return true
  }

  /**
   * 获取预审阶段全部凭证号
   *
   * 用途：年审阶段排除预审已抽凭证号，防止重复抽取
   * Requirement 5.1: 每行标记 phase 字段
   * Requirement 2.5: 年审自动排除预审已抽凭证号
   *
   * @returns 预审阶段全部 voucher_no 数组
   */
  function getPreliminaryVoucherNos(): string[] {
    return preliminarySamples.value.map(s => s.voucherNo)
  }

  // ─── 返回 ────────────────────────────────────────────────────────────────────

  return {
    viewMode,
    visibleSamples,
    preliminarySamples,
    finalSamples,
    isRowEditable,
    isFillModeRestricted,
    getPreliminaryVoucherNos,
  }
}
