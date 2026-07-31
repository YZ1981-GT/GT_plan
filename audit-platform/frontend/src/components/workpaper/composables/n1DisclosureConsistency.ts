/**
 * N1 递延所得税资产披露内部勾稽校验（纯函数引擎）
 *
 * 规则全部取自源模板 `backend/wp_templates/N/N1 递延所得税资产.xlsx` 的公式，
 * **不自造校验**：
 *
 * | 规则 | 源模板依据 |
 * |---|---|
 * | 表 1 资产段小计 = 段内各项之和 | 上市 `B21=SUM(B13:B20)` / 国企 `B21=SUM(B13:B19)` |
 * | 表 1 负债段小计 = 段内各项之和 | 上市 `B29=SUM(B23:B28)` / 国企同 |
 * | 表 2 资产段小计 = 段内各项之和（国企） | 国企 `B44=SUM(B36:B43)` |
 * | 表 2 负债段小计 = 段内各项之和（国企） | 国企 `B52=SUM(B46:B51)` |
 * | 未确认明细合计 = 可抵扣暂时性差异 + 可抵扣亏损 | 上市 `B42=B39+B40` / 国企 `B63=B61+B62` |
 * | 亏损到期合计 = 各年度之和 | 上市 `B52=SUM(B46:B51)` / 国企 `B72=SUM(B66:B71)` |
 * | 亏损到期合计 = 未确认明细「可抵扣亏损」行（期末 / 上期各一条） | 上市 `B40=B52`、`C40=C52`；国企 `B72=B62`、`C72=C62` |
 *
 * 设计约束（与 `h1DisclosureConsistency` 同范式）：
 * - 容差 **0.01 元**（源模板金额保留 2 位小数）
 * - 任一侧为 `null`（未取到）→ `level='skip'`，**不误报**
 * - 纯函数：不依赖 Vue / DOM，可单测与 PBT
 *
 * spec: .kiro/specs/n1-deferred-tax-disclosure-template-alignment/ R3
 */
import type { N1DisclosureVariant, NullableAmount } from './n1NoteSectionMap'
import {
  WP_CHECK_TOLERANCE,
  eqCheck as sharedEqCheck,
  segmentSumCheck,
  sumNullable,
  summarizeChecks,
  type WpCheckLevel,
  type WpCheckResult,
} from './shared/disclosureConsistency'

/**
 * 金额比较容差（元）。
 * 共用原语在 `shared/disclosureConsistency.ts`；此处保留 N1 名以免既有引用 churn。
 */
export const N1_CHECK_TOLERANCE = WP_CHECK_TOLERANCE

export type N1CheckLevel = WpCheckLevel
export type N1CheckResult = WpCheckResult

// ─── 输入 ────────────────────────────────────────────────────────────────────

/** 表 1 / 表 2 的段（明细 + 小计）——小计由 UI 公式行给出，用于校验而非重算替代 */
export interface N1CheckSegment {
  /** 段内明细金额（按被校验的那一列取值） */
  details: readonly NullableAmount[]
  /** 段小计（UI 展示值） */
  subtotal: NullableAmount
}

export interface N1ConsistencyInput {
  /** 表 1 资产段（按「递延所得税资产/负债」期末列校验） */
  unoffsetAsset?: N1CheckSegment
  /** 表 1 负债段 */
  unoffsetLiability?: N1CheckSegment
  /** 表 2 资产段（国企逐项形态，按「互抵后的递延所得税资产或负债」期末列） */
  netOffsetAsset?: N1CheckSegment
  /** 表 2 负债段（国企） */
  netOffsetLiability?: N1CheckSegment
  /** 未确认明细：可抵扣暂时性差异 / 可抵扣亏损 / 合计（期末列） */
  unrecognized?: {
    temporaryDiff: NullableAmount
    deductibleLoss: NullableAmount
    total: NullableAmount
    /** 上期列（上市=上年年末，国企=年初） */
    priorTemporaryDiff?: NullableAmount
    priorDeductibleLoss?: NullableAmount
    priorTotal?: NullableAmount
  }
  /** 亏损到期：各年度金额 + 合计（期末列与上期列） */
  lossExpiry?: {
    yearAmounts: readonly NullableAmount[]
    total: NullableAmount
    priorYearAmounts?: readonly NullableAmount[]
    priorTotal?: NullableAmount
  }
}

// ─── 内部工具（委托共用原语，保留 N1 名以免既有引用 churn）───────────────────

/** 相等类校验（容差 0.01 元；任一侧 null → skip） */
export const eqCheck = sharedEqCheck

function segmentCheck(
  label: string,
  rule: string,
  seg: N1CheckSegment | undefined,
  refs?: string[],
): N1CheckResult | null {
  if (!seg) return null
  return segmentSumCheck(label, rule, seg.details, seg.subtotal, refs)
}

// ─── 主入口 ──────────────────────────────────────────────────────────────────

/**
 * 跑完整套勾稽。返回顺序稳定（便于快照测试与 UI 稳定渲染）。
 *
 * `variant` 决定第 3 列口径文案（上市「上年年末余额」/ 国企「年初余额」）与
 * 是否包含表 2 的双段小计校验（上市表 2 是 2 行形态，无段小计）。
 */
export function runN1DisclosureChecks(
  variant: N1DisclosureVariant,
  input: N1ConsistencyInput,
): N1CheckResult[] {
  const priorLabel = variant === 'listed' ? '上年年末' : '年初'
  const out: Array<N1CheckResult | null> = []

  out.push(
    segmentCheck(
      '表(1)递延所得税资产段小计',
      '小计 = 资产段各明细项之和（源模板 =SUM(B13:B20)）',
      input.unoffsetAsset,
      ['N1-2', 'N1-4'],
    ),
  )
  out.push(
    segmentCheck(
      '表(1)递延所得税负债段小计',
      '小计 = 负债段各明细项之和（源模板 =SUM(B23:B28)）；负债段数据来源于递延所得税负债底稿',
      input.unoffsetLiability,
      ['N3'],
    ),
  )

  if (variant === 'soe') {
    out.push(
      segmentCheck(
        '表(2)互抵后资产段小计',
        '小计 = 段内各明细项之和（源模板 =SUM(B36:B43)）',
        input.netOffsetAsset,
      ),
    )
    out.push(
      segmentCheck(
        '表(2)互抵后负债段小计',
        '小计 = 段内各明细项之和（源模板 =SUM(B46:B51)）',
        input.netOffsetLiability,
      ),
    )
  }

  const u = input.unrecognized
  if (u) {
    out.push(
      eqCheck(
        '未确认明细合计（期末）',
        '合计 = 可抵扣暂时性差异 + 可抵扣亏损（源模板 =B39+B40）',
        u.total,
        sumNullable([u.temporaryDiff, u.deductibleLoss]),
      ),
    )
    if (u.priorTotal !== undefined) {
      out.push(
        eqCheck(
          `未确认明细合计（${priorLabel}）`,
          `合计 = 可抵扣暂时性差异 + 可抵扣亏损（源模板 =C39+C40）`,
          u.priorTotal,
          sumNullable([u.priorTemporaryDiff ?? null, u.priorDeductibleLoss ?? null]),
        ),
      )
    }
  }

  const l = input.lossExpiry
  if (l) {
    out.push(
      eqCheck(
        '亏损到期合计（期末）',
        '合计 = 各到期年度金额之和（源模板 =SUM(B46:B51)）',
        l.total,
        sumNullable(l.yearAmounts),
      ),
    )
    if (l.priorTotal !== undefined) {
      out.push(
        eqCheck(
          `亏损到期合计（${priorLabel}）`,
          '合计 = 各到期年度金额之和（源模板 =SUM(C46:C51)）',
          l.priorTotal,
          sumNullable(l.priorYearAmounts ?? []),
        ),
      )
    }
    if (u) {
      out.push(
        eqCheck(
          '亏损到期合计 = 未确认可抵扣亏损（期末）',
          '源模板 B40=B52：未确认明细「可抵扣亏损」行必须等于亏损到期表合计',
          l.total,
          u.deductibleLoss,
          ['N1-5'],
        ),
      )
      if (l.priorTotal !== undefined && u.priorDeductibleLoss !== undefined) {
        out.push(
          eqCheck(
            `亏损到期合计 = 未确认可抵扣亏损（${priorLabel}）`,
            '源模板 C40=C52：上期列同口径校验',
            l.priorTotal,
            u.priorDeductibleLoss,
            ['N1-5'],
          ),
        )
      }
    }
  }

  return out.filter((r): r is N1CheckResult => r !== null)
}

/** 汇总：用于紧凑 bar 展示（委托共用原语） */
export type { WpCheckSummary as N1CheckSummary } from './shared/disclosureConsistency'

export const summarizeN1Checks = summarizeChecks
