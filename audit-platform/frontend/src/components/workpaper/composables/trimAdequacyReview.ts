/**
 * 裁剪充分性复核视图的统计派生（纯函数，零 Vue 依赖、零 IO、零写入）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 20
 * 守卫: `views/__tests__/trimAdequacyReview.spec.ts`
 * Requirements: 12.1 / 12.2 / 12.3 / 12.4 / 12.5 / 12.6 / 12.7
 *
 * ## 它解决的复核问题
 *
 * EQCR 与质控复核合伙人要回答的是「这个项目裁掉的东西，裁得对不对」。这个问题不能靠
 * 逐循环翻 15 个 Tab 回答 —— 复核者需要一屏看到：哪些循环裁得多、理由分布是什么、
 * 有没有把高风险科目裁掉、有没有裁了却没写理由、因金额裁掉的那批加起来是否已经不小。
 *
 * ## 为什么统计必须由决策真源派生，而不是本模块自己算
 *
 * 「相同输入下与裁剪页统计逐项相等」（R12.7）只有一种可靠落法：**两处调用同一个函数**。
 * 故本模块：
 *
 * - 金额汇总一律走 `evaluateAggregateGate`（与裁剪页批量确认前那道闸门是同一个函数），
 *   由它承担「只计重要性类理由码 / 按科目去重 / `>=` 而非 `>`」三条约束；本模块**不再
 *   自己写一遍求和**。自己写一遍就是第二真源，两边分叉时无从裁决谁对。
 * - 理由码分类走 `isMachineReasonCode` / `reasonCodeLabel`（真源 `trimReasonCodes`，
 *   已与后端 `TrimReasonCode` 交叉锁死）。
 * - 「缺理由」的判据与裁剪页概览逐字一致（已裁剪且理由文本为空）—— 该口径同时也是
 *   `saveTrim` 阻断保存的判据，换成「无理由码」会让存量自由文本裁剪被误判成缺理由。
 *
 * ## 三个不可退化为 0 的未知态
 *
 * 平台反复吃过「未知补成 0」的亏（负载未知显示 0 会被读成"这个人很空闲"）。复核视图上
 * 这类退化更贵，因为复核者据此签字：
 *
 * | 未知 | 正确表现 | 退化成 0 的后果 |
 * |---|---|---|
 * | 某循环未加载 | `loaded = false`，计数一律不参与合计 | 合计虚低，复核者以为该循环没裁过东西 |
 * | 待确认建议数不可派生 | `suggested = null` | 显示 0 会读成「该循环没有待确认建议」 |
 * | 实际执行重要性未确定 | `materialityAvailable = false` | 显示「合计 0 元 < 重要性」= 谎报已做汇总评估 |
 *
 * ## 为什么「待确认」只有部分循环可派生
 *
 * 建议态（`suggest_trim`）是**未落库**的中间状态，只存在于裁剪页跑过 `decideTrim` 之后的
 * 内存行上。跨循环的原始行（`getProcedures` 返回值）上没有它，而重跑 `decideTrim` 需要
 * per-cycle 的三维判据上下文（科目数据态 / 风险 / 重要性）—— 在此另造一套判据就是第二
 * 真源。故本模块要求宿主**如实传 `null`** 表示该循环不可派生，视图渲染成「需打开该循环」。
 *
 * ## 已确认的重要性类裁剪为什么会有「金额未知」
 *
 * 🔴 后端**不持久化判据数值**：`procedure_instances.suggestion_state` 实际只写
 * `reason_code`（确认时）与 `rejected` / `rejected_by` / `rejected_at` / `rejected_reason`
 * （驳回时）。design.md 里写的 `evidence` 键与 `_write_suggestion_reason_code` 的 docstring
 * 都提到 evidence，但代码从未写它。
 *
 * 后果：已确认裁剪的科目余额只能由宿主用**同一个** `resolveAccountName` + 同一份
 * 判据上下文当场重解析，解析不到就是解析不到。故本模块把「金额可解析的合计」与
 * 「金额不可解析的条数」**分开报**：把不可解析的当 0 计入合计会让复核者看到一个偏低的
 * 汇总额并据此认为汇总敞口可接受。
 */

import { evaluateAggregateGate, type AggregateGateResult } from './trimAggregateGate'
import { isMachineReasonCode, reasonCodeLabel } from './trimReasonCodes'

// ═══════════════════════════════════════════════════════════════════════════
// 输入类型
// ═══════════════════════════════════════════════════════════════════════════

export type ReviewRiskLevel = 'H' | 'M' | 'L' | null

/** 复核视图消费的单条程序（**已落地事实** + 宿主用同一真源解析出的判据数值）。 */
export interface ReviewProcedureRow {
  wpCode: string
  procedureCode: string
  procedureName: string
  /** 已落地的适用性：已裁剪（`not_applicable` / `skip`）为 true */
  trimmed: boolean
  /** 裁剪理由自由文本（存量记录只有这个） */
  skipReason: string
  /** 结构化理由码；`null` = 存量记录或人工裁剪未选码 */
  reasonCode: string | null
  /** 建议已被人工驳回 */
  rejected: boolean
  /** 宿主用 `resolveAccountName` 解析出的科目名；`null` = 解析不出 */
  accountName: string | null
  /** 科目余额；`null` = 未知（判据数值未持久化，或该循环判据上下文未加载） */
  accountAmount: number | null
  /**
   * B50 该科目的风险结论。
   *
   * 🔴 `riskKnown = false` 时 `riskLevel` / `riskSpecial` 一律不得用于判断 ——
   * B50 未填时把「未评估」当「非高风险」会让「高风险被裁」这条异常永不触发，
   * 而那正是本视图最要紧的一条。
   */
  riskLevel: ReviewRiskLevel
  riskSpecial: boolean
  riskKnown: boolean
}

export interface ReviewCycleInput {
  cycle: string
  label: string
  /** false = 该循环尚未加载（计数未知，不参与合计） */
  loaded: boolean
  rows: ReviewProcedureRow[]
  /** 待确认建议数；`null` = 不可派生（宿主未在该循环跑过 `decideTrim`） */
  suggested: number | null
}

/** 取平台默认、未经本项目确认的完整性敏感循环（R5.6 / R12.3）。 */
export interface PlatformDefaultCompletenessCycle {
  cycle: string
  label: string
  /** 平台默认的审计依据原文（让复核者看到"凭什么默认这样"） */
  rationale: string
  /** 平台默认的结论：视为完整性敏感 / 不敏感 */
  sensitiveByDefault: boolean
}

export interface TrimAdequacyReviewInput {
  cycles: ReviewCycleInput[]
  /** `null` = 覆盖表读取失败（**未知**，不等于"全部平台默认"） */
  platformDefaultCompleteness: PlatformDefaultCompletenessCycle[] | null
  /** 实际执行重要性；`null` = 本项目未确定（视图须如实说明，不显示 0） */
  performanceMateriality: number | null
  /**
   * 当前仍处建议态的项，直接喂汇总闸。
   *
   * 🔴 由宿主从**裁剪页那一批同样的行**构造，保证与页面上那道闸门同输入同输出。
   */
  suggestedGateItems: Array<{ accountName: string; amount: number; reasonCode: string }>
}

// ═══════════════════════════════════════════════════════════════════════════
// 输出类型
// ═══════════════════════════════════════════════════════════════════════════

export interface ReviewCycleStat {
  cycle: string
  label: string
  loaded: boolean
  total: number
  /** 保留执行 */
  keep: number
  trimmed: number
  /** 已裁剪但理由文本为空（与裁剪页概览同口径，也是 saveTrim 的阻断判据） */
  missingReason: number
  /** `null` = 不可派生 */
  suggested: number | null
  rejected: number
  /** 带机器判据理由码的裁剪（系统建议 → 人工确认） */
  machineTrimmed: number
  /** 带人工理由码的裁剪 */
  manualTrimmed: number
  /** 只有自由文本、无理由码的存量裁剪（R8.4：必须可读，不算缺理由） */
  legacyTextOnly: number
  /** 本循环命中的异常条数（含平台默认完整性清单） */
  anomalyCount: number
}

export type ReviewAnomalyKind =
  | 'risk_protected_trimmed'
  | 'missing_reason'
  | 'platform_default_completeness'

export interface ReviewAnomaly {
  kind: ReviewAnomalyKind
  /** high = 审计红线（可能导致程序缺失）；medium = 需确认但未必错 */
  severity: 'high' | 'medium'
  cycle: string
  /** `null` = 该异常不针对具体程序（如循环级完整性清单） */
  wpCode: string | null
  /** 一行标题 */
  title: string
  /** 🔴 必须写清判据与后果 —— 只给行上色，复核者看不出为什么被标 */
  detail: string
}

export interface ReasonDistributionEntry {
  /** `null` = 该桶不对应任何理由码（缺理由 / 仅自由文本） */
  code: string | null
  label: string
  kind: 'machine' | 'manual' | 'legacy_text' | 'missing'
  count: number
}

export interface MaterialityTrimPanel {
  /** false = 本项目未确定实际执行重要性（视图须说明，不得显示成 0 元对比） */
  materialityAvailable: boolean
  performanceMateriality: number | null
  /** 待确认建议的汇总闸（与裁剪页同一函数、同一批行 ⇒ 逐项相等） */
  suggestedGate: AggregateGateResult
  /** 已确认的重要性类裁剪的汇总闸（同一函数，输入换成已落地那批） */
  confirmedGate: AggregateGateResult
  /** 已确认的重要性类裁剪条数（按程序计，未去重） */
  confirmedCount: number
  /** 其中科目余额解析不到的条数 —— **不计入** confirmedGate 的合计 */
  amountUnknownCount: number
  /** 面向复核者的结论（含判据数值与未知项提示） */
  narrative: string
}

export interface TrimAdequacyReview {
  cycles: ReviewCycleStat[]
  totals: {
    total: number
    keep: number
    trimmed: number
    missingReason: number
    rejected: number
    machineTrimmed: number
    manualTrimmed: number
    legacyTextOnly: number
    /** `null` = 无任何循环可派生待确认数 */
    suggested: number | null
  }
  reasonDistribution: ReasonDistributionEntry[]
  materiality: MaterialityTrimPanel
  anomalies: ReviewAnomaly[]
  /** 未加载的循环代号（其计数不参与合计） */
  unloadedCycles: string[]
  /** 待确认数可派生的循环代号（其余循环该列显示"需打开该循环"） */
  suggestedDerivableCycles: string[]
  /** true = 完整性清单覆盖状态未知（读取失败），非"全部平台默认" */
  completenessOverrideUnknown: boolean
}

// ═══════════════════════════════════════════════════════════════════════════
// 小工具（纯函数）
// ═══════════════════════════════════════════════════════════════════════════

const RISK_LEVEL_LABEL: Readonly<Record<string, string>> = {
  H: '高',
  M: '中',
  L: '低',
}

function text(value: unknown): string {
  return String(value ?? '').trim()
}

/** 金额格式化（千分符 + 两位小数），与汇总闸措辞一致。 */
function formatAmount(value: number): string {
  if (!Number.isFinite(value)) return String(value)
  const negative = value < 0
  const fixed = Math.abs(value).toFixed(2)
  const dot = fixed.indexOf('.')
  const grouped = fixed.slice(0, dot).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${negative ? '-' : ''}${grouped}.${fixed.slice(dot + 1)}`
}

/**
 * 该行是否属「因重要性原因裁剪」。
 *
 * 判据是理由码，而不是「有没有金额」—— 后者会把金额解析不到的那批漏掉，正是要单独
 * 统计的一类。
 */
function isMaterialityTrim(row: ReviewProcedureRow): boolean {
  const code = text(row.reasonCode)
  return code === 'below_trivial' || code === 'below_materiality'
}

/**
 * 该行是否触发风险保护红线。
 *
 * 🔴 `riskKnown` 是前置条件：B50 未填时不得断言任何科目是高风险，也不得断言它不是。
 */
function isRiskProtected(row: ReviewProcedureRow): boolean {
  if (!row.riskKnown) return false
  return row.riskSpecial === true || row.riskLevel === 'H'
}

/** 已裁剪且理由文本为空（与裁剪页概览、`saveTrim` 阻断判据同口径）。 */
function isMissingReason(row: ReviewProcedureRow): boolean {
  return row.trimmed === true && text(row.skipReason) === ''
}

// ═══════════════════════════════════════════════════════════════════════════
// 主派生函数
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 由已落地事实 + 宿主解析出的判据数值派生复核视图统计。
 *
 * 纯函数：同输入同输出，无 IO、无副作用、不改入参。
 */
export function buildTrimAdequacyReview(input: TrimAdequacyReviewInput): TrimAdequacyReview {
  const cycleInputs = Array.isArray(input?.cycles) ? input.cycles : []
  const performanceMateriality = typeof input?.performanceMateriality === 'number'
    && Number.isFinite(input.performanceMateriality)
    ? input.performanceMateriality
    : null

  const anomalies: ReviewAnomaly[] = []
  const anomalyByCycle = new Map<string, number>()
  const bump = (cycle: string) => anomalyByCycle.set(cycle, (anomalyByCycle.get(cycle) ?? 0) + 1)

  // 理由码分布：按码累计（含"仅自由文本"与"缺理由"两个非码桶）
  const byCode = new Map<string, number>()
  let legacyTextOnlyTotal = 0
  let missingReasonTotal = 0

  // 已确认的重要性类裁剪（喂第二道同函数汇总闸）
  const confirmedItems: Array<{ accountName: string; amount: number; reasonCode: string }> = []
  let confirmedCount = 0
  let amountUnknownCount = 0

  const stats: ReviewCycleStat[] = []
  const unloadedCycles: string[] = []
  const suggestedDerivableCycles: string[] = []

  for (const ci of cycleInputs) {
    const cycle = text(ci?.cycle)
    const label = text(ci?.label) || cycle
    const loaded = ci?.loaded === true
    const rows = Array.isArray(ci?.rows) ? ci.rows : []

    if (!loaded) {
      unloadedCycles.push(cycle)
      stats.push({
        cycle,
        label,
        loaded: false,
        total: 0,
        keep: 0,
        trimmed: 0,
        missingReason: 0,
        // 🔴 未加载时待确认恒 null（不是 0）：0 会被读成"该循环没有待确认建议"
        suggested: null,
        rejected: 0,
        machineTrimmed: 0,
        manualTrimmed: 0,
        legacyTextOnly: 0,
        anomalyCount: 0,
      })
      continue
    }

    const suggested = typeof ci?.suggested === 'number' && Number.isFinite(ci.suggested)
      ? ci.suggested
      : null
    if (suggested !== null) suggestedDerivableCycles.push(cycle)

    let keep = 0
    let trimmed = 0
    let missingReason = 0
    let rejected = 0
    let machineTrimmed = 0
    let manualTrimmed = 0
    let legacyTextOnly = 0

    for (const row of rows) {
      if (!row) continue
      if (row.rejected === true) rejected += 1
      if (row.trimmed !== true) {
        keep += 1
        continue
      }
      trimmed += 1

      const code = text(row.reasonCode)
      if (code) {
        byCode.set(code, (byCode.get(code) ?? 0) + 1)
        if (isMachineReasonCode(code)) machineTrimmed += 1
        else manualTrimmed += 1
      }

      if (isMissingReason(row)) {
        missingReason += 1
        missingReasonTotal += 1
        anomalies.push({
          kind: 'missing_reason',
          severity: 'high',
          cycle,
          wpCode: text(row.wpCode) || text(row.procedureCode) || null,
          title: `${label} · ${text(row.wpCode) || text(row.procedureCode)} 已裁剪但未填理由`,
          detail: `程序「${text(row.procedureName) || text(row.procedureCode)}」已被裁剪为不适用，`
            + '但裁剪理由为空。无理由的裁剪在复核时无法评价其适当性，且保存粗裁时会被阻断；'
            + '请补填理由或改回执行。',
        })
        bump(cycle)
      } else if (!code) {
        // 有文本、无理由码 = 存量记录（R8.4：必须可读，不得算缺理由）
        legacyTextOnly += 1
        legacyTextOnlyTotal += 1
      }

      if (isRiskProtected(row)) {
        const riskWord = row.riskSpecial
          ? '特别风险'
          : `重大错报风险等级为${RISK_LEVEL_LABEL[String(row.riskLevel)] ?? String(row.riskLevel)}`
        anomalies.push({
          kind: 'risk_protected_trimmed',
          severity: 'high',
          cycle,
          wpCode: text(row.wpCode) || text(row.procedureCode) || null,
          title: `${label} · ${text(row.accountName) || text(row.wpCode)} 属${row.riskSpecial ? '特别风险' : '高风险'}却被裁剪`,
          detail: `科目「${text(row.accountName) || '（未解析出科目）'}」在 B50 认定层次风险矩阵中${riskWord}，`
            + '准则要求对特别风险与高风险认定实施实质性程序，金额小也不得豁免。'
            + `本程序「${text(row.procedureName) || text(row.procedureCode)}」已被裁剪为不适用，`
            + `理由为「${text(row.skipReason) || reasonCodeLabel(row.reasonCode) || '未填'}」。`
            + '请复核该裁剪是否适当，或说明相关认定已由哪张底稿覆盖。',
        })
        bump(cycle)
      }

      if (isMaterialityTrim(row)) {
        confirmedCount += 1
        const amount = typeof row.accountAmount === 'number' && Number.isFinite(row.accountAmount)
          ? row.accountAmount
          : null
        if (amount === null) {
          // 🔴 解析不到的**不喂**汇总闸：喂进去会被当 0 计入合计，让汇总额偏低
          amountUnknownCount += 1
        } else {
          confirmedItems.push({
            accountName: text(row.accountName) || text(row.wpCode) || text(row.procedureCode),
            amount,
            reasonCode: code,
          })
        }
      }
    }

    stats.push({
      cycle,
      label,
      loaded: true,
      total: rows.length,
      keep,
      trimmed,
      missingReason,
      suggested,
      rejected,
      machineTrimmed,
      manualTrimmed,
      legacyTextOnly,
      anomalyCount: 0, // 循环级异常在下方补齐后统一回填
    })
  }

  // 平台默认完整性清单（循环级异常）
  const platformDefaults = input?.platformDefaultCompleteness
  const completenessOverrideUnknown = platformDefaults === null || platformDefaults === undefined
  if (!completenessOverrideUnknown) {
    for (const pd of platformDefaults) {
      if (!pd) continue
      const cycle = text(pd.cycle)
      anomalies.push({
        kind: 'platform_default_completeness',
        severity: 'medium',
        cycle,
        wpCode: null,
        title: `${text(pd.label) || cycle} 的完整性敏感判据取平台默认，未经本项目确认`,
        detail: `平台默认${pd.sensitiveByDefault ? '视为' : '不视为'}完整性敏感 —— 依据：`
          + `${text(pd.rationale) || '（无依据文字）'}。`
          + '该判据决定「科目余额低于实际执行重要性」这条裁剪建议对本循环是否失效，'
          + '未经本项目确认时其适当性无法评价；请在完整性敏感清单面板逐循环表态并填写理由。',
      })
      bump(cycle)
    }
  }

  // 回填每循环异常数
  for (const s of stats) s.anomalyCount = anomalyByCycle.get(s.cycle) ?? 0

  const loaded = stats.filter(s => s.loaded)
  const derivable = loaded.filter(s => s.suggested !== null)
  const totals = {
    total: loaded.reduce((sum, s) => sum + s.total, 0),
    keep: loaded.reduce((sum, s) => sum + s.keep, 0),
    trimmed: loaded.reduce((sum, s) => sum + s.trimmed, 0),
    missingReason: loaded.reduce((sum, s) => sum + s.missingReason, 0),
    rejected: loaded.reduce((sum, s) => sum + s.rejected, 0),
    machineTrimmed: loaded.reduce((sum, s) => sum + s.machineTrimmed, 0),
    manualTrimmed: loaded.reduce((sum, s) => sum + s.manualTrimmed, 0),
    legacyTextOnly: loaded.reduce((sum, s) => sum + s.legacyTextOnly, 0),
    // 🔴 一个循环都不可派生时为 null —— 报 0 等于宣称"全项目没有待确认建议"
    suggested: derivable.length === 0
      ? null
      : derivable.reduce((sum, s) => sum + (s.suggested as number), 0),
  }

  return {
    cycles: stats,
    totals,
    reasonDistribution: buildReasonDistribution({
      byCode,
      legacyTextOnly: legacyTextOnlyTotal,
      missingReason: missingReasonTotal,
    }),
    materiality: buildMaterialityPanel({
      performanceMateriality,
      suggestedGateItems: Array.isArray(input?.suggestedGateItems) ? input.suggestedGateItems : [],
      confirmedItems,
      confirmedCount,
      amountUnknownCount,
    }),
    anomalies,
    unloadedCycles,
    suggestedDerivableCycles,
    completenessOverrideUnknown,
  }
}

/**
 * 理由码分布（R12.2）。
 *
 * 三类桶的语义必须分开，否则复核者无法区分「系统判据裁的」「人工判断裁的」
 * 「存量没有码的」：前者复核判据数值，中者复核理由是否充分，后者只能看文本。
 */
function buildReasonDistribution(args: {
  byCode: Map<string, number>
  legacyTextOnly: number
  missingReason: number
}): ReasonDistributionEntry[] {
  const out: ReasonDistributionEntry[] = []
  for (const [code, count] of args.byCode) {
    out.push({
      code,
      // 未登记的码原样回显（`reasonCodeLabel` 的既有契约），不显示空白
      label: reasonCodeLabel(code) ?? code,
      kind: isMachineReasonCode(code) ? 'machine' : 'manual',
      count,
    })
  }
  // 机器判据在前（复核关注点不同），同类按数量降序
  const rank = (kind: ReasonDistributionEntry['kind']) => (kind === 'machine' ? 0 : 1)
  out.sort((a, b) => rank(a.kind) - rank(b.kind) || b.count - a.count || a.label.localeCompare(b.label))

  if (args.legacyTextOnly > 0) {
    out.push({
      code: null,
      label: '仅自由文本理由（无结构化理由码）',
      kind: 'legacy_text',
      count: args.legacyTextOnly,
    })
  }
  if (args.missingReason > 0) {
    out.push({
      code: null,
      label: '缺理由（已裁剪但未填理由）',
      kind: 'missing',
      count: args.missingReason,
    })
  }
  return out
}

/**
 * 因重要性原因裁剪的金额合计与重要性水平对比（R12.4）。
 *
 * 两道闸门都走 `evaluateAggregateGate`（同一函数）：
 * - `suggestedGate` = 仍待确认的那批 ⇒ 与裁剪页那道闸门逐项相等
 * - `confirmedGate` = 已落地的那批 ⇒ 回答「已经裁掉的加起来是否已达可容忍水平」
 */
function buildMaterialityPanel(args: {
  performanceMateriality: number | null
  suggestedGateItems: Array<{ accountName: string; amount: number; reasonCode: string }>
  confirmedItems: Array<{ accountName: string; amount: number; reasonCode: string }>
  confirmedCount: number
  amountUnknownCount: number
}): MaterialityTrimPanel {
  const { performanceMateriality, confirmedCount, amountUnknownCount } = args
  const suggestedGate = evaluateAggregateGate({
    items: args.suggestedGateItems,
    performanceMateriality,
  })
  const confirmedGate = evaluateAggregateGate({
    items: args.confirmedItems,
    performanceMateriality,
  })

  return {
    materialityAvailable: performanceMateriality !== null,
    performanceMateriality,
    suggestedGate,
    confirmedGate,
    confirmedCount,
    amountUnknownCount,
    narrative: buildMaterialityNarrative({
      performanceMateriality,
      confirmedGate,
      suggestedGate,
      confirmedCount,
      amountUnknownCount,
    }),
  }
}

function buildMaterialityNarrative(args: {
  performanceMateriality: number | null
  confirmedGate: AggregateGateResult
  suggestedGate: AggregateGateResult
  confirmedCount: number
  amountUnknownCount: number
}): string {
  const { performanceMateriality, confirmedGate, suggestedGate, confirmedCount } = args
  const unknownNote = args.amountUnknownCount > 0
    ? `其中 ${args.amountUnknownCount} 项的科目余额无法定位（判据数值未随裁剪落库，`
      + '需打开对应循环后重新解析），未计入上述合计 —— 实际汇总额高于此数。'
    : ''

  if (performanceMateriality === null) {
    // 🔴 未确定重要性时不得给出"合计低于重要性"的结论
    return `本项目尚未确定实际执行重要性，无法对因金额原因裁剪的科目做汇总评估。`
      + `已按金额类理由码裁剪 ${confirmedCount} 项。`
      + '请先在重要性水平底稿确定实际执行重要性与明显微小错报临界值，再复核这批裁剪的适当性。'
      + (unknownNote ? ` ${unknownNote}` : '')
  }

  const base = `已确认的金额类裁剪涉及 ${confirmedGate.distinctAccountCount} 个科目（已去重），`
    + `余额合计 ${formatAmount(confirmedGate.totalAmount)} 元，`
    + `实际执行重要性 ${formatAmount(performanceMateriality)} 元`
  const verdict = confirmedGate.blocked
    ? '。合计已达到实际执行重要性 —— 这批科目各自金额虽小，汇总错报可能超过可容忍水平，'
      + '请复核裁剪范围是否过宽、以及是否需要对其中部分科目补做实质性程序。'
    : '，合计低于该水平，汇总错报敞口在可容忍范围内。'
  const pending = suggestedGate.distinctAccountCount > 0
    ? ` 另有待确认建议涉及 ${suggestedGate.distinctAccountCount} 个科目、`
      + `合计 ${formatAmount(suggestedGate.totalAmount)} 元`
      + `${suggestedGate.blocked ? '（已触发汇总闸，批量确认被阻断）' : ''}。`
    : ''

  return `${base}${verdict}${pending}${unknownNote ? ` ${unknownNote}` : ''}`
}
