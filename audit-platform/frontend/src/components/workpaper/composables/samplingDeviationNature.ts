/**
 * 偏差性质与原因 — 实质性抽凭侧（口径复用 C 类控制测试）
 *
 * spec: sampling-evaluation-and-governance-closure R4
 * Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5
 *
 * ## 准则要求与改造前的缺口
 *
 * CAS 1314 要求：调查偏差的**性质和原因**，并评价其对审计程序目的和审计其他方面的
 * 可能影响；若偏差表明总体中可能存在系统性问题，不宜简单外推。
 *
 * 改造前实质性抽凭侧的评价字段只有 `deviation_count`（一个笔数）+ `conclusion_message`
 * （一段自由文本），而 **C 类控制测试侧早已有结构化的偏差决策树**
 * （`composables/useDeviationDecisionTree.ts`，六步 IF 链复刻致同模板 Cx-2）。
 * 同一条准则要求在两侧不对称。
 *
 * ## 为什么不另写一套枚举
 *
 * R4.4 要求复用 C 类口径。实测 `getStepOptions(2)` 返回的是三值**中文**标签
 * `系统性偏差` / `人为偏差` / `随机性偏差`（立项时以为是 `isolated`/`systematic`/
 * `undetermined`，与 C 类不同构 —— 多出「人为偏差」，且「待判断」在 C 类里是 `null`
 * 而非独立枚举值）。
 *
 * 本模块的处置：**key 用英文（存储层友好），中文标签在运行时从 C 类导出函数取**，
 * 不做硬编码副本。守卫据此交叉锁死：C 类改了文案这里必须同步，否则打红。
 */
import { getStepOptions } from '@/composables/useDeviationDecisionTree'

import type { SampledVoucher } from './useSamplingAlgorithms'

/**
 * 偏差性质 key。与 C 类三个选项一一对应；「待判断」= 未标注（`null`），不是枚举值。
 */
export type DeviationNature = 'systematic' | 'human' | 'random'

export const DEVIATION_NATURES: readonly DeviationNature[] = Object.freeze([
  'systematic',
  'human',
  'random',
])

/**
 * key → C 类中文标签的映射关系（顺序即 `getStepOptions(2)` 的顺序）。
 *
 * 这里只声明「第 N 个选项对应哪个 key」，**标签文本本身不在此硬编码** ——
 * 由 `deviationNatureLabels()` 在运行时从 C 类取，避免双真源。
 */
const NATURE_KEY_ORDER: readonly DeviationNature[] = Object.freeze([
  'systematic', // 系统性偏差
  'human', // 人为偏差
  'random', // 随机性偏差
])

/**
 * 从 C 类决策树取中文标签（单一真源）。
 *
 * C 类选项数与本模块 key 数不一致时**抛错而非静默截断** —— 那说明 C 类改了口径，
 * 必须有人来同步，静默降级会让两侧长期漂移。
 */
export function deviationNatureLabels(): Readonly<Record<DeviationNature, string>> {
  const options = getStepOptions(2)
  if (options.length !== NATURE_KEY_ORDER.length) {
    throw new Error(
      `偏差性质口径漂移：C 类 getStepOptions(2) 返回 ${options.length} 项，` +
        `本模块声明 ${NATURE_KEY_ORDER.length} 项。请同步 samplingDeviationNature.ts`,
    )
  }
  const out = {} as Record<DeviationNature, string>
  NATURE_KEY_ORDER.forEach((key, i) => {
    out[key] = options[i].label
  })
  return Object.freeze(out)
}

/**
 * 需要填写原因与影响评估的性质（R4.2）。
 *
 * 系统性与人为偏差都指向「总体中可能存在同类问题」，准则要求考虑扩大范围或改变审计
 * 方法；随机性偏差可按常规外推处理。
 */
export const NATURE_REQUIRING_EXPLANATION: readonly DeviationNature[] = Object.freeze([
  'systematic',
  'human',
])

/** 结论区提示语（存在需说明性质的偏差时显著展示） */
export const NO_SIMPLE_PROJECTION_HINT =
  '存在系统性或人为偏差，不宜简单外推：应考虑扩大测试范围、改变审计方法或提请管理层扩大检查'

export interface DeviationAnnotation {
  nature: DeviationNature | null
  /** 原因说明 */
  cause?: string | null
  /** 对审计程序目的与其他方面的影响评估 */
  impact?: string | null
}

/** 凭证号 → 偏差标注 */
export type DeviationAnnotationMap = Record<string, DeviationAnnotation>

export interface NatureBucket {
  count: number
  amount: string
}

/** 偏差性质摘要：只含**实际出现**的性质（未出现不补零，见后端同名说明） */
export type DeviationNatureSummary = Partial<Record<DeviationNature, NatureBucket>>

export interface DeviationResolution {
  /** 偏差样本总数（checkResult 为 N / 异常） */
  total: number
  /** 未标注性质的凭证号（阻断结论确认） */
  unannotated: string[]
  /** 已标注为需说明性质但原因或影响为空的凭证号（阻断结论确认） */
  missingExplanation: string[]
  summary: DeviationNatureSummary
  /** 是否存在需说明性质的偏差（驱动结论区提示） */
  hasNonProjectable: boolean
}

/** 该样本是否为偏差（核查结果为 N 或 异常）。 */
export function isDeviation(v: SampledVoucher): boolean {
  return v.checkResult === 'N' || v.checkResult === '异常'
}

function bookAmountOf(v: SampledVoucher): number {
  const d = Math.abs(parseFloat(v.debitAmount ?? '0') || 0)
  const c = Math.abs(parseFloat(v.creditAmount ?? '0') || 0)
  return Math.max(d, c)
}

/**
 * 汇总偏差性质。
 *
 * 无偏差时 `unannotated` / `missingExplanation` 均为空 → 调用方门控不产生阻断（零回归）。
 */
export function summarizeDeviationNature(
  samples: SampledVoucher[],
  annotations: DeviationAnnotationMap,
): DeviationResolution {
  const list = Array.isArray(samples) ? samples : []
  const map = annotations ?? {}
  const summary: DeviationNatureSummary = {}
  const out: DeviationResolution = {
    total: 0,
    unannotated: [],
    missingExplanation: [],
    summary,
    hasNonProjectable: false,
  }

  for (const v of list) {
    if (!isDeviation(v)) continue
    out.total += 1
    const ann = map[v.voucherNo]
    const nature = ann?.nature ?? null
    if (!nature || !DEVIATION_NATURES.includes(nature)) {
      out.unannotated.push(v.voucherNo)
      continue
    }
    const bucket = summary[nature] ?? { count: 0, amount: '0.00' }
    bucket.count += 1
    bucket.amount = (parseFloat(bucket.amount) + bookAmountOf(v)).toFixed(2)
    summary[nature] = bucket

    if (NATURE_REQUIRING_EXPLANATION.includes(nature)) {
      out.hasNonProjectable = true
      const hasCause = !!ann?.cause && String(ann.cause).trim().length > 0
      const hasImpact = !!ann?.impact && String(ann.impact).trim().length > 0
      if (!hasCause || !hasImpact) {
        out.missingExplanation.push(v.voucherNo)
      }
    }
  }
  return out
}

/**
 * 构建持久化载荷。全空返回 `null`（与后端「缺省即 None」对齐）。
 *
 * **不补零**：未出现的性质不写入。「没有系统性偏差」与「没评价过偏差性质」是两件事，
 * 补零会把后者伪装成前者。
 */
export function buildDeviationNatureSummaryPayload(
  samples: SampledVoucher[],
  annotations: DeviationAnnotationMap,
): DeviationNatureSummary | null {
  const { summary } = summarizeDeviationNature(samples, annotations)
  return Object.keys(summary).length > 0 ? summary : null
}
