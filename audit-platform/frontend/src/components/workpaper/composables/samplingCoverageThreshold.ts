/**
 * 抽样覆盖率告警阈值 — 单一真源
 *
 * spec: sampling-evaluation-and-governance-closure R2
 * Validates: Requirements 2.5, 2.6, 2.7, 2.8
 *
 * ## 为什么要单独一个模块
 *
 * 改造前 60% 这个数字**写死在 `checkCAS1314Compliance` 函数体内**
 * （`useSamplingAlgorithms.ts` 原 275-283 行），而它是平台唯一的覆盖率告警口径。
 * 两个问题：
 *
 * 1. **CAS 1314 没有规定 60% 这个数字**。准则要求的是「样本量足以将抽样风险降至可接受
 *    的低水平」，具体比例取决于科目性质、风险评估结果与其他程序的证据。把一个平台经验值
 *    以准则规则的名义硬编码，会让审计师误以为它是硬性要求（或反过来，因为常年看到这条
 *    告警而整体忽略合规提示）。
 * 2. 不同科目/风险等级应当不同。货币资金与其他应收款不该用同一个覆盖率门槛。
 *
 * ## 优先级与「宁缺勿造」
 *
 * 解析优先级：底稿级 > 项目级 > 平台默认。
 *
 * **当前平台没有存储覆盖率阈值的配置位**，所以本模块只把接口就位、由调用方按需传入，
 * 不虚构一张配置表也不去猜某个现有字段的语义。两个入参都不传时返回平台默认 0.60，
 * 与改造前逐位一致（零回归支点）。将来若在项目设置或底稿 schema 里增加该配置，
 * 只需在调用点把值传进来，本模块与消费方均无需改动。
 */

/** 平台默认金额覆盖率告警阈值（小数）。**非准则规定**，见模块头说明。 */
export const DEFAULT_COVERAGE_THRESHOLD = 0.6

/** 阈值来源，用于在告警文案中如实标注（避免被误认为准则硬性要求）。 */
export type CoverageThresholdSource = 'workpaper' | 'project' | 'platform_default'

/** 来源中文标签（UI 全中文化）。 */
export const THRESHOLD_SOURCE_LABELS: Readonly<Record<CoverageThresholdSource, string>> =
  Object.freeze({
    workpaper: '本底稿设定',
    project: '项目设定',
    platform_default: '平台默认（非准则规定）',
  })

export interface CoverageThresholdInput {
  /** 底稿级阈值（小数，如 0.75）。当前平台无该配置位，预留接口。 */
  workpaper?: number | null
  /** 项目级阈值（小数）。当前平台无该配置位，预留接口。 */
  project?: number | null
}

export interface ResolvedCoverageThreshold {
  /** 阈值（小数） */
  value: number
  source: CoverageThresholdSource
  /** 中文来源标签 */
  sourceLabel: string
}

/**
 * 阈值是否可用：必须是 (0, 1] 区间内的有限数。
 *
 * 排除 0 与负数：阈值为 0 等于「永不告警」，那应该显式关闭告警而不是把阈值设成 0
 * （否则「配置成 0」与「配置漏填被当成 0」不可区分）。
 * 排除 > 1：覆盖率上限是 100%，> 1 必然是把百分数当小数传错（如传 60 而非 0.6）。
 */
function isUsable(v: number | null | undefined): v is number {
  return typeof v === 'number' && Number.isFinite(v) && v > 0 && v <= 1
}

/**
 * 解析覆盖率阈值：底稿级 > 项目级 > 平台默认。
 *
 * 非法值（NaN / ≤0 / >1）视为未配置，回退下一级 —— 宁可用平台默认也不用一个错的阈值。
 */
export function resolveCoverageThreshold(
  input: CoverageThresholdInput = {},
): ResolvedCoverageThreshold {
  if (isUsable(input.workpaper)) {
    return {
      value: input.workpaper,
      source: 'workpaper',
      sourceLabel: THRESHOLD_SOURCE_LABELS.workpaper,
    }
  }
  if (isUsable(input.project)) {
    return {
      value: input.project,
      source: 'project',
      sourceLabel: THRESHOLD_SOURCE_LABELS.project,
    }
  }
  return {
    value: DEFAULT_COVERAGE_THRESHOLD,
    source: 'platform_default',
    sourceLabel: THRESHOLD_SOURCE_LABELS.platform_default,
  }
}

/** 阈值渲染为百分数文本（用于告警文案，如 `60%`）。 */
export function formatThresholdPercent(value: number): string {
  const pct = value * 100
  // 整数不显示小数位；非整数保留 1 位（0.625 → 62.5%）
  return Number.isInteger(pct) ? `${pct}%` : `${pct.toFixed(1)}%`
}

/**
 * 覆盖率告警文案（R2.8：必须明示阈值取值与来源）。
 *
 * 改造前文案是「覆盖率偏低，建议增大样本量或调整抽样条件」—— 审计师看不出 60% 从哪来，
 * 也无从判断这条告警是准则要求还是平台经验值。
 */
export function buildCoverageWarningMessage(resolved: ResolvedCoverageThreshold): string {
  return (
    `金额覆盖率低于 ${formatThresholdPercent(resolved.value)}` +
    `（阈值来源：${resolved.sourceLabel}），` +
    '建议增大样本量或调整抽样条件'
  )
}
