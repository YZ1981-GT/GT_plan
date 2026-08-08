/**
 * 未检查样本的准则处置 — 纯函数
 *
 * spec: sampling-evaluation-and-governance-closure R3
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6
 *
 * ## 准则要求与改造前的缺口
 *
 * CAS 1314 要求：注册会计师无法对选取的项目实施设计的审计程序或替代审计程序时，
 * 应当将该项目**视为偏差**；也可以对该项目**实施替代审计程序**后据以评价。
 *
 * 改造前平台只有 `unchecked_sample_count` 计数，配一句
 * 「有 N 笔样本尚未填写核查结果，未纳入错报推断」的 warning（`GtVoucherSamplingEngine.vue`
 * 原 436 行）。等于两条路都没走：既不计入错报（少算），也没有替代程序证据，
 * 而这个选择本身也没有任何留痕字段。抽样结论因此不成立。
 *
 * ## 为什么按凭证号做键
 *
 * 与 `extraction_criteria.filled_voucher_nos` 同粒度。同一凭证多条分录时，
 * 「无法实施程序」是针对那张凭证（凭证缺失/不可获取），不是针对某一条分录。
 */
import type { SampledVoucher } from './useSamplingAlgorithms'

/** 处置方式。两种审计后果完全不同，缺省不猜。 */
export type UncheckedDispositionMode = 'treated_as_deviation' | 'alternative_performed'

export const UNCHECKED_DISPOSITION_MODES: readonly UncheckedDispositionMode[] = Object.freeze([
  'treated_as_deviation',
  'alternative_performed',
])

/** 中文标签（UI 全中文化） */
export const UNCHECKED_DISPOSITION_LABELS: Readonly<
  Record<UncheckedDispositionMode, string>
> = Object.freeze({
  treated_as_deviation: '视同偏差',
  alternative_performed: '已实施替代程序',
})

/** 选项说明（下拉 tooltip，写明准则口径） */
export const UNCHECKED_DISPOSITION_HINTS: Readonly<
  Record<UncheckedDispositionMode, string>
> = Object.freeze({
  treated_as_deviation:
    '按 CAS 1314：无法实施程序且未执行替代程序的项目视为偏差，其账面金额按 100% 污染率纳入错报推断',
  alternative_performed:
    '已通过替代程序取得该项目的审计证据，须填写替代程序说明；'
    + '该样本按替代程序结论参与推断（「实际错报」留空即替代程序未发现错报）',
})

export interface UncheckedDispositionEntry {
  mode: UncheckedDispositionMode
  /** 替代程序说明。`alternative_performed` 时必填 */
  note?: string | null
}

/** 凭证号 → 处置 */
export type UncheckedDispositionMap = Record<string, UncheckedDispositionEntry>

export interface UncheckedDispositionResolution {
  /** 未检查且尚未选择处置方式的凭证号（阻断结论确认） */
  pending: string[]
  /** 选了「已实施替代程序」但说明为空的凭证号（阻断结论确认） */
  missingNote: string[]
  /** 处置为「视同偏差」的样本（按 100% 污染率参与推断） */
  asDeviation: SampledVoucher[]
  /** 处置为「已实施替代程序」的样本 */
  alternative: SampledVoucher[]
}

/** 该样本是否未检查（`checkResult` 为空串）。 */
export function isUnchecked(v: SampledVoucher): boolean {
  return !v.checkResult
}

/** 取单笔凭证的账面金额（借贷方绝对值较大者），与推断口径一致。 */
function bookAmountOf(v: SampledVoucher): number {
  const d = Math.abs(parseFloat(v.debitAmount ?? '0') || 0)
  const c = Math.abs(parseFloat(v.creditAmount ?? '0') || 0)
  return Math.max(d, c)
}

/**
 * 解析未检查样本的处置状态。
 *
 * 无未检查样本时四个集合全空 → 调用方的门控不产生任何阻断（R3.6 零回归）。
 */
export function resolveUncheckedDisposition(
  samples: SampledVoucher[],
  disposition: UncheckedDispositionMap,
): UncheckedDispositionResolution {
  const list = Array.isArray(samples) ? samples : []
  const map = disposition ?? {}
  const out: UncheckedDispositionResolution = {
    pending: [],
    missingNote: [],
    asDeviation: [],
    alternative: [],
  }

  for (const v of list) {
    if (!isUnchecked(v)) continue
    const entry = map[v.voucherNo]
    const mode = entry?.mode
    if (mode === 'treated_as_deviation') {
      out.asDeviation.push(v)
    } else if (mode === 'alternative_performed') {
      out.alternative.push(v)
      if (!entry?.note || !String(entry.note).trim()) {
        out.missingNote.push(v.voucherNo)
      }
    } else {
      out.pending.push(v.voucherNo)
    }
  }
  return out
}

/**
 * 把「视同偏差」的未检查样本改写为「实际错报 = 账面金额」的样本，供推断使用（R3.2）。
 *
 * 返回**新数组**，不改原样本（原样本的 `actualMisstatement` 是审计师录入值，
 * 视同偏差是评价环节的派生处置，两者不能混为一谈：改口径后必须能回到原值）。
 *
 * `checkResult` 同时置为 `'N'` —— 否则推断函数会按「未检查」再次跳过它。
 */
export function applyDeviationTreatment(
  samples: SampledVoucher[],
  disposition: UncheckedDispositionMap,
): SampledVoucher[] {
  const map = disposition ?? {}
  return (Array.isArray(samples) ? samples : []).map(v => {
    if (!isUnchecked(v)) return v
    if (map[v.voucherNo]?.mode !== 'treated_as_deviation') return v
    return {
      ...v,
      checkResult: 'N' as const,
      actualMisstatement: bookAmountOf(v).toFixed(2),
    }
  })
}

/**
 * 把「已实施替代程序」的未检查样本改写为「已检查」，供推断使用（R3.3）。
 *
 * 🔴 **为什么必须改写**：`useVoucherSampling.inferMisstatement` 的既有过滤
 * `treated.filter(v => v.checkResult !== '')`（来自 `voucher-check-sampling-integration`
 * R18）会把 `checkResult` 为空的样本整体排除。而 `alternative_performed` 的样本
 * `checkResult` 仍为空 ⇒ 它**既不进分子也不进分母**，比率估计的基数被静默缩小、
 * 推断错报被放大（2026-08-08 Task 19 浏览器实测：一笔 37,340.20 的替代程序样本
 * 被排除，使污染率由 0.3111 变成 0.7025、推断错报由 1,511,078 变成 3,412,422 元）。
 * 那既不符合 R3.3「该样本 SHALL 按替代程序结论参与推断」，也不是安全方向 ——
 * 虚高的推断错报会误触发扩大范围/调整，或把总体误判为超可容忍错报。
 *
 * 准则依据：CAS 1314 只把「无法实施设计的程序**且**无法实施适当替代程序」的项目
 * 视为偏差/错报。替代程序已实施 ⇒ 该项目**已取得审计证据**，应当以其结论进入基数。
 *
 * **不动 `actualMisstatement`**：留空时 `toDecimal(undefined)` = 0，即「替代程序
 * 未发现错报」；审计师若在替代程序中发现错报，其录入值原样参与推断（绝不覆盖）。
 *
 * 与 `applyDeviationTreatment` 一样返回**新数组**：处置是评价环节的派生口径，
 * 原样本必须能回到审计师录入的原值；`buildUncheckedDispositionPayload` 读的是原数组，
 * 故留痕里「已实施替代程序」这一处置记录不会因本改写而丢失。
 */
export function applyAlternativeTreatment(
  samples: SampledVoucher[],
  disposition: UncheckedDispositionMap,
): SampledVoucher[] {
  const map = disposition ?? {}
  return (Array.isArray(samples) ? samples : []).map(v => {
    if (!isUnchecked(v)) return v
    if (map[v.voucherNo]?.mode !== 'alternative_performed') return v
    return { ...v, checkResult: 'Y' as const }
  })
}

/**
 * 未检查样本处置的统一改写入口（推断前必须走这一个，R3.2 + R3.3）。
 *
 * 两种处置的集合互斥（`resolveUncheckedDisposition` 按 mode 分流），故先后顺序无关。
 * 未选处置方式的样本一律不改写 —— 它们由 `conclusionBlockedReason` 阻断结论确认，
 * 不该悄悄按任一口径参与推断。
 */
export function applyUncheckedDisposition(
  samples: SampledVoucher[],
  disposition: UncheckedDispositionMap,
): SampledVoucher[] {
  return applyAlternativeTreatment(
    applyDeviationTreatment(samples, disposition),
    disposition,
  )
}

/**
 * 视同偏差的笔数（计入 `deviation_count`，R3.2）。
 */
export function countTreatedAsDeviation(
  samples: SampledVoucher[],
  disposition: UncheckedDispositionMap,
): number {
  return resolveUncheckedDisposition(samples, disposition).asDeviation.length
}

/**
 * 构建持久化载荷（`{凭证号: {mode, note}}`）。
 *
 * 只输出**当前仍未检查**的样本的处置 —— 审计师后来补录了核查结果的样本，其处置记录
 * 已无意义，留着会让归档件显示「既检查过又视同偏差」的自相矛盾状态。
 * 全空时返回 `null`（不产生空 dict，与后端「缺省即 None」对齐）。
 */
export function buildUncheckedDispositionPayload(
  samples: SampledVoucher[],
  disposition: UncheckedDispositionMap,
): UncheckedDispositionMap | null {
  const map = disposition ?? {}
  const out: UncheckedDispositionMap = {}
  for (const v of (Array.isArray(samples) ? samples : [])) {
    if (!isUnchecked(v)) continue
    const entry = map[v.voucherNo]
    if (!entry?.mode) continue
    out[v.voucherNo] = {
      mode: entry.mode,
      note: entry.note && String(entry.note).trim() ? String(entry.note).trim() : null,
    }
  }
  return Object.keys(out).length > 0 ? out : null
}
