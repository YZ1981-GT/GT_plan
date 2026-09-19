/**
 * H2 在建工程披露内部勾稽校验（纯函数，上市 / 国企双变体）
 *
 * 规则只取源模板可判定的层间派生 / 子集关系（不自造审计判断）：
 * - 上市：汇总表「在建工程」= ①明细表账面净值合计；项目表期末余额是明细表的子集；
 *   减值准备是明细表账面余额的子集（减值不得超过账面余额）。
 * - 国企：项目表「账面价值」= 账面余额 − 减值准备（逐行公式列）。
 *
 * 委托平台共用原语 `shared/disclosureConsistency.ts`（容差 0.01 元 / null → skip）。
 *
 * spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R5
 */
import {
  eqCheck,
  summarizeChecks,
  type NullableAmount,
  type WpCheckResult,
  type WpCheckSummary,
} from './shared/disclosureConsistency'
import {
  type ListedDetailRow,
  type ListedImpairmentRow,
  type ListedProjectRow,
  type ListedSummaryRow,
  listedDetailSubtotal,
  listedImpairmentSubtotal,
  listedProjectSubtotal,
} from './h2ListedDisclosureModel'
import {
  type SoeDetailRow,
  type SoeImpairmentRow,
  type SoeProjectRow,
  soeDetailSubtotal,
  soeImpairmentSubtotal,
  soeProjectSubtotal,
} from './h2SoeDisclosureModel'

export type { WpCheckResult } from './shared/disclosureConsistency'

export interface H2ListedConsistencyInput {
  summary: readonly ListedSummaryRow[]
  detailRows: readonly ListedDetailRow[]
  projectRows: readonly ListedProjectRow[]
  impairmentRows: readonly ListedImpairmentRow[]
}

export function buildH2ListedChecks(input: H2ListedConsistencyInput): WpCheckResult[] {
  const detailSub = listedDetailSubtotal([...input.detailRows])
  const projectSub = listedProjectSubtotal([...input.projectRows])
  const impairSub = listedImpairmentSubtotal([...input.impairmentRows])
  const cipRow = input.summary.find((r) => r.key === 'cip')

  const checks: WpCheckResult[] = [
    eqCheck(
      '汇总表「在建工程」期末余额',
      '汇总表在建工程期末余额 = ①明细表账面净值合计（源模板汇总表引明细表）',
      cipRow?.endBalance ?? null,
      detailSub?.endNet ?? null,
      ['Note:五、23'],
    ),
  ]

  const projectEnd: NullableAmount = projectSub?.endBalance ?? null
  const detailEnd: NullableAmount = detailSub?.endBook ?? null
  if (projectEnd !== null && detailEnd !== null && projectEnd - detailEnd > 0.01) {
    checks.push({
      label: '重要项目表期末余额合计',
      rule: '重要在建工程项目是全部在建工程的子集：项目表期末余额合计 ≤ 明细表账面余额合计',
      left: projectEnd,
      right: detailEnd,
      diff: Math.round((projectEnd - detailEnd) * 100) / 100,
      level: 'error',
      refs: ['wp:H2-2'],
    })
  }

  const impairEnd: NullableAmount = impairSub?.endBalance ?? null
  if (impairEnd !== null && detailEnd !== null && impairEnd - detailEnd > 0.01) {
    checks.push({
      label: '减值准备期末余额合计',
      rule: '减值准备是账面余额的子集：减值准备期末余额合计 ≤ 明细表账面余额期末余额合计',
      left: impairEnd,
      right: detailEnd,
      diff: Math.round((impairEnd - detailEnd) * 100) / 100,
      level: 'error',
      refs: ['wp:H2-3'],
    })
  }

  return checks
}

export interface H2SoeConsistencyInput {
  detailRows: readonly SoeDetailRow[]
  projectRows: readonly SoeProjectRow[]
  impairmentRows: readonly SoeImpairmentRow[]
}

export function buildH2SoeChecks(input: H2SoeConsistencyInput): WpCheckResult[] {
  const detailSub = soeDetailSubtotal([...input.detailRows])
  const projectSub = soeProjectSubtotal([...input.projectRows])
  const impairSub = soeImpairmentSubtotal([...input.impairmentRows])
  const checks: WpCheckResult[] = []

  const projectEnd: NullableAmount = projectSub?.endBalance ?? null
  const detailEnd: NullableAmount = detailSub?.endBook ?? null
  if (projectEnd !== null && detailEnd !== null && projectEnd - detailEnd > 0.01) {
    checks.push({
      label: '重要项目表账面余额合计',
      rule: '重要在建工程项目是全部在建工程的子集：项目表账面余额合计 ≤ 明细表账面余额合计',
      left: projectEnd,
      right: detailEnd,
      diff: Math.round((projectEnd - detailEnd) * 100) / 100,
      level: 'error',
      refs: ['wp:H2-2'],
    })
  }

  const impairEnd: NullableAmount = impairSub ?? null
  if (impairEnd !== null && detailEnd !== null && impairEnd - detailEnd > 0.01) {
    checks.push({
      label: '减值准备期末余额合计',
      rule: '减值准备是账面余额的子集：减值准备期末余额合计 ≤ 明细表账面余额期末余额合计',
      left: impairEnd,
      right: detailEnd,
      diff: Math.round((impairEnd - detailEnd) * 100) / 100,
      level: 'error',
      refs: ['wp:H2-3'],
    })
  }

  return checks
}

export function summarizeH2Consistency(checks: readonly WpCheckResult[]): WpCheckSummary {
  return summarizeChecks(checks)
}
