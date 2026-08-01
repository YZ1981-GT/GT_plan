/**
 * H5 油气资产披露内部勾稽校验（纯函数，仅国企有独立 sheet）
 *
 * 唯一可判定关系（源模板「四、账面价值合计 = 一、原价合计 − 二、累计折耗合计 −
 * 三、减值准备累计金额合计」，见 `h5NoteSectionMap.buildH5SoeRows`）：
 * 层间派生 —— 账面净值 = 原值 − 折耗 − 减值。
 *
 * H5 上市侧无独立附注章节（`H5_NOTE_SECTION.listed` 为 null），故只服务国企 Tab。
 *
 * spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R5
 */
import { eqCheck, type NullableAmount, type WpCheckResult } from './shared/disclosureConsistency'

export interface H5ConsistencyInput {
  cost: NullableAmount
  depletion: NullableAmount
  impairment: NullableAmount
  /** 底稿/组件算出的净值（同步载荷实际推送值，用于比对是否与派生公式一致） */
  netValue: NullableAmount
}

export function buildH5Checks(input: H5ConsistencyInput): WpCheckResult[] {
  const { cost, depletion, impairment, netValue } = input
  if (cost === null && depletion === null && impairment === null && netValue === null) {
    return []
  }
  const derivedNet =
    cost === null || depletion === null || impairment === null
      ? null
      : Math.round((cost - depletion - impairment) * 100) / 100

  return [
    eqCheck(
      '四、账面价值合计',
      '账面价值 = 一、原价合计 − 二、累计折耗合计 − 三、减值准备累计金额合计（源模板层间派生公式）',
      netValue,
      derivedNet,
      ['Note:八、25'],
    ),
  ]
}
