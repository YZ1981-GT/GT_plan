/**
 * 控制测试样本量与偏差评价 — 双方法学接线（统计抽样 / 实务快捷表）
 *
 * spec: sampling-evaluation-and-governance-closure R9
 * Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5
 *
 * ## 为什么需要它
 *
 * 2026-08-05 实证：`computeAttributeSampleSize` / `evaluateDeviationRate` /
 * `DEFAULT_TOLERABLE_DEVIATION_RATE`（CAS 1314 附录的属性抽样：泊松可信赖度系数推样本量 +
 * 偏差率上限评价）**零生产消费方** —— 只被自己的两个测试文件引用。控制测试底稿
 * （`CControlTestSubPage.vue` / `CControlTestSummaryTable.vue`）用的是
 * `useSampleSizeEngine.suggestSampleSize`（控制频率 × 测试次数区间**快捷表**）。
 *
 * 结果是准则附录的统计评价能力写好了但用户不可达：审计师无法在控制测试里说明
 * 「样本量 25 是按 95% 置信度、可容忍偏差率 5%、预期偏差率 0% 推出的」，
 * 也拿不到「偏差率上限 11.3% > 可容忍 5% ⇒ 该控制不可依赖」这个结论。
 *
 * ## 两套并存是有意的，禁止合并
 *
 * | 方法 | 依据 | 适用 |
 * |---|---|---|
 * | 快捷表 `suggestSampleSize` | 事务所实务经验值（按控制执行频率给固定样本量/比例） | 常规控制测试，快速定量 |
 * | 统计抽样 `computeAttributeSampleSize` | CAS 1314 附录泊松系数 | 需要量化抽样风险、或偏差率上限要进结论时 |
 *
 * 两者的**输入维度完全不同**（频率×次数 vs 置信度×可容忍偏差率×预期偏差率），
 * 输出也不可互相校验。后来者若"顺手统一"会同时破坏两侧：快捷表失去实务便利，
 * 统计法失去准则依据。`SAMPLING_METHOD_BOUNDARY` 常量 + 守卫把这条边界钉死。
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'

import {
  DEFAULT_TOLERABLE_DEVIATION_RATE,
  computeAttributeSampleSize,
  evaluateDeviationRate,
} from '@/components/workpaper/composables/useSamplingAlgorithms'
import { suggestSampleSize } from '@/composables/useSampleSizeEngine'

/** 样本量确定方法 */
export type ControlSampleSizeMode = 'shortcut_table' | 'statistical'

export const CONTROL_SAMPLE_SIZE_MODES: readonly ControlSampleSizeMode[] = Object.freeze([
  'shortcut_table',
  'statistical',
])

export const CONTROL_SAMPLE_SIZE_MODE_LABELS: Readonly<
  Record<ControlSampleSizeMode, string>
> = Object.freeze({
  shortcut_table: '实务快捷表',
  statistical: '统计抽样（CAS 1314）',
})

export const CONTROL_SAMPLE_SIZE_MODE_HINTS: Readonly<
  Record<ControlSampleSizeMode, string>
> = Object.freeze({
  shortcut_table:
    '按控制执行频率与本期执行次数查表取样本量（事务所实务经验值），适用于常规控制测试',
  statistical:
    '按 CAS 1314 附录泊松可信赖度系数推导：样本量 = R(置信度, 预期偏差数) ÷ (可容忍偏差率 − 预期偏差率)，'
    + '并据实际偏差笔数评价偏差率上限是否超过可容忍偏差率',
})

/**
 * 两套方法学的边界声明（供守卫钉死，禁止后来者合并）。
 *
 * 每条写明「服务什么」与「为什么不能合并」—— 只写清单不写理由的登记表，
 * 下一个会话仍会提议统一。
 */
export const SAMPLING_METHOD_BOUNDARY = Object.freeze([
  Object.freeze({
    fn: 'suggestSampleSize',
    module: '@/composables/useSampleSizeEngine',
    serves: '控制测试实务快捷表（控制执行频率 × 本期执行次数 → 固定样本量或比例）',
    reason:
      '入参是频率与次数，输出是事务所经验值；不含置信度与可容忍偏差率，无法产出偏差率上限。'
      + '与统计抽样输入维度不同，两者不可互相替代或校验。',
  }),
  Object.freeze({
    fn: 'computeAttributeSampleSize',
    module: '@/components/workpaper/composables/useSamplingAlgorithms',
    serves: 'CAS 1314 附录属性抽样样本量推导（置信度 × 可容忍偏差率 × 预期偏差率）',
    reason:
      '准则口径，可量化抽样风险；与 evaluateDeviationRate 配套用于「该控制是否可依赖」的统计结论。',
  }),
  Object.freeze({
    fn: 'evaluateDeviationRate',
    module: '@/components/workpaper/composables/useSamplingAlgorithms',
    serves: 'CAS 1314 附录偏差率上限评价（样本量 + 实际偏差笔数 → 上限偏差率与是否有效）',
    reason: '快捷表侧没有对应能力；控制测试结论若要引用偏差率上限只能走这里。',
  }),
])

export interface StatisticalSampleSizeInput {
  /** 置信度（0,1)，如 0.95 */
  confidenceLevel: number
  /** 可容忍偏差率（0,1] */
  tolerableDevRate: number
  /** 预期偏差率 [0,1) */
  expectedDevRate: number
}

export interface DeviationRateEvaluation {
  /** 上限偏差率（小数） */
  upperDevRate: number
  /** 上限 ≤ 可容忍偏差率 ⇒ 控制可依赖 */
  effective: boolean
  /** 中文结论 */
  conclusion: string
}

/** 默认统计参数：95% 置信度、可容忍偏差率取平台默认、预期偏差率 0。 */
export function defaultStatisticalInput(): StatisticalSampleSizeInput {
  return {
    confidenceLevel: 0.95,
    tolerableDevRate: DEFAULT_TOLERABLE_DEVIATION_RATE,
    expectedDevRate: 0,
  }
}

/**
 * 统计口径样本量。返回 `null` 表示参数不足或不可推导（预期 ≥ 可容忍时精度余量 ≤ 0）
 * —— **不返回 0**：0 会被下游当成「样本量为零」而不是「推不出来」。
 */
export function statisticalSampleSize(input: StatisticalSampleSizeInput): number | null {
  const n = computeAttributeSampleSize(
    input.expectedDevRate,
    input.tolerableDevRate,
    input.confidenceLevel,
  )
  return n > 0 ? n : null
}

/**
 * 偏差率上限评价 + 中文结论（R9.2）。
 *
 * 样本量不合法时 `evaluateDeviationRate` 返回 `{upperDevRate: 1, effective: false}`，
 * 此处把它翻成「无法评价」而不是「控制无效」—— 两者审计含义不同。
 */
export function evaluateControlDeviation(
  sampleSize: number,
  deviations: number,
  input: StatisticalSampleSizeInput,
): DeviationRateEvaluation {
  const { upperDevRate, effective } = evaluateDeviationRate(
    sampleSize,
    deviations,
    input.confidenceLevel,
    input.tolerableDevRate,
  )
  const pct = (v: number) => `${(v * 100).toFixed(2)}%`

  if (!Number.isFinite(sampleSize) || sampleSize <= 0) {
    return {
      upperDevRate,
      effective: false,
      conclusion: '样本量未确定，无法评价偏差率上限（不等于控制无效）',
    }
  }
  return {
    upperDevRate,
    effective,
    conclusion: effective
      ? `偏差率上限 ${pct(upperDevRate)} 未超过可容忍偏差率 ${pct(input.tolerableDevRate)}，该控制可予依赖`
      : `偏差率上限 ${pct(upperDevRate)} 超过可容忍偏差率 ${pct(input.tolerableDevRate)}，`
        + '该控制不可依赖：应扩大样本、执行替代程序或改为实质性程序应对',
  }
}

export interface AttributeSamplingModeOptions {
  /** 控制执行频率（快捷表入参） */
  frequency: Ref<string> | ComputedRef<string>
  /** 本期执行次数（快捷表入参） */
  occurrences: Ref<number | null> | ComputedRef<number | null>
  /** 实际样本量（用于偏差评价） */
  actualSampleSize: Ref<number> | ComputedRef<number>
  /** 实际偏差笔数 */
  deviationCount: Ref<number> | ComputedRef<number>
  /** 初始模式，缺省快捷表（零回归） */
  initialMode?: ControlSampleSizeMode
}

/**
 * 控制测试样本量双模式 composable。
 *
 * 默认 `shortcut_table` ⇒ 与改造前逐位一致（R9.3 零回归）。
 */
export function useAttributeSamplingMode(options: AttributeSamplingModeOptions) {
  const mode = ref<ControlSampleSizeMode>(options.initialMode ?? 'shortcut_table')
  const statInput = ref<StatisticalSampleSizeInput>(defaultStatisticalInput())

  /** 快捷表建议（保持既有行为） */
  const shortcutSuggestion = computed(() =>
    suggestSampleSize(options.frequency.value, options.occurrences.value ?? undefined),
  )

  /** 统计口径建议样本量（null = 参数不足/不可推导） */
  const statisticalSuggestion = computed(() => statisticalSampleSize(statInput.value))

  /** 当前模式下的建议样本量文本（供 tooltip / 展示） */
  const suggestionText = computed(() => {
    if (mode.value === 'statistical') {
      const n = statisticalSuggestion.value
      return n == null
        ? '统计口径无法推导：请检查置信度、可容忍偏差率是否大于预期偏差率'
        : `统计口径建议样本量 ${n} 项（置信度 ${(statInput.value.confidenceLevel * 100).toFixed(0)}%，`
          + `可容忍偏差率 ${(statInput.value.tolerableDevRate * 100).toFixed(2)}%，`
          + `预期偏差率 ${(statInput.value.expectedDevRate * 100).toFixed(2)}%）`
    }
    return shortcutSuggestion.value.hint
  })

  /** 偏差率上限评价（仅统计模式有意义） */
  const deviationEvaluation = computed<DeviationRateEvaluation | null>(() => {
    if (mode.value !== 'statistical') return null
    return evaluateControlDeviation(
      options.actualSampleSize.value,
      options.deviationCount.value,
      statInput.value,
    )
  })

  return {
    mode,
    statInput,
    shortcutSuggestion,
    statisticalSuggestion,
    suggestionText,
    deviationEvaluation,
  }
}
