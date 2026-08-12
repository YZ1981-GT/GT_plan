/**
 * 裁剪决策内核（纯函数，零 Vue 依赖、零 IO）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 7
 * 守卫: `__tests__/procedureTrimDecision.spec.ts`（Task 5 打红基线）
 *       `__tests__/procedureTrimDecision.behavior.spec.ts`（本任务新增覆盖面）
 * Requirements: 3.1 / 3.2 / 3.3 / 3.4 / 4.x / 5.x / 6.x / 9.x
 *
 * ## 它决定什么
 *
 * 对**单个程序**给出三态结论：保留（`keep`）、自动裁剪（`auto_trim`）、
 * 建议裁剪（`suggest_trim`）。三个法定判据维度按固定顺序施加，前者命中即短路：
 * 风险评估 → 数据存在性 → 重要性。任何一维数据缺失时**整体跳过该维度**，
 * 既不猜测也不用别的口径替代。
 *
 * ## 为什么「科目余额低于实际执行重要性就裁掉程序」不能自动执行
 *
 * 三条审计上的理由，构成本模块全部判据顺序的由来：
 *
 * 1. **风险方向反了**：重要性用于评价错报与确定样本量，不是「科目小就不查」。
 *    账面金额小本身可能就是完整性认定出问题的**结果** —— 少记负债、少记费用、
 *    跨期少记收入，账面越小越可能是漏记。用金额去豁免完整性风险，等于用症状
 *    豁免病因。故完整性豁免（档 5）必须排在重要性判据（档 7、8）之前。
 * 2. **汇总效应**：若干各自低于实际执行重要性的科目，错报汇总起来可能远超
 *    财务报表层面的可容忍水平。故重要性维度只产生**建议**（`suggest_trim`），
 *    由 `trimAggregateGate` 在批量确认前做汇总闸，本模块永不对它给 `auto_trim`。
 * 3. **特别风险与高风险不受金额豁免**：对识别为特别风险的领域必须实施实质性
 *    程序（CAS 1231），金额小也必须做。故风险保护（档 1）排在最前，且哪怕
 *    科目在试算表里完全没有数据也不裁 —— 「无数据」在特别风险科目上恰恰是
 *    需要查证的异常，不是可以省掉程序的理由。
 *
 * ## 只产生「建议」的那两档为什么不能合并进自动裁
 *
 * `no_data`（科目未在试算表出现）是**事实判断**：没有余额就没有可实施的实质性
 * 程序对象，自动裁剪不引入审计判断风险。而 `below_trivial` / `below_materiality`
 * 是**职业判断**：是否因金额小而不做程序，取决于该科目的风险特征、与其他科目的
 * 汇总影响、以及是否存在完整性方向的漏记可能。故后两者恒为 `suggest_trim`，
 * 必须经审计师逐条或批量确认才能落到不适用状态（Property 2 双向锁死）。
 *
 * ## 术语约定
 *
 * 平台既有 `GtB50RiskAssessment.vue` 用两三字母缩写命名重要性字段，且与审计通用
 * 含义正好相反。故本模块一律使用数据库字段名全称
 * （`performanceMateriality` = 实际执行重要性、`trivialThreshold` = 明显微小
 * 错报临界值）。财务报表整体层面的重要性水平**不作为裁剪判据** —— 它是报表
 * 整体评价基准，不是单科目是否要做程序的门槛，故本模块的输入类型里压根没有它。
 */

import {
  COMPLETENESS_CYCLE_RULES,
  resolveCompletenessExemption,
  type CompletenessExemptionSource,
  type CompletenessRmm,
} from './completenessExemption'

// ═══════════════════════════════════════════════════════════════════════════
// 类型
// ═══════════════════════════════════════════════════════════════════════════

/** 三态结论。 */
export type TrimVerdict = 'keep' | 'auto_trim' | 'suggest_trim'

/**
 * 本决策内核可能产出的结构化理由码。
 *
 * 后端 `TrimReasonCode` 枚举在这三个之外还有既有的四个取值
 * （`no_related_business` / `low_risk_assessment` / `control_test_effective` /
 * `other`）与 `covered_elsewhere` —— 那些由人工选择或别的路径写入，
 * 本内核永不产出，故不纳入本联合类型。
 */
export type TrimReasonCode = 'no_data' | 'below_trivial' | 'below_materiality'

/** 科目级数据可用性（registry 覆盖时优先于循环级）。 */
export type SubjectDataState = 'with_data' | 'no_data' | 'unknown'

/** 命中的档位标识，供复核视图与守卫定位决策来源。 */
export type TrimDecidedBy =
  | 'risk_protection'
  | 'mandatory'
  | 'non_data_driven_cycle_mandatory'
  | 'execution_progress'
  | 'manual_reason'
  | 'workpaper_entry'
  | 'suggestion_rejected'
  | 'non_balance_driven_cycle'
  | 'no_data'
  | 'completeness_exemption'
  | 'materiality_unavailable'
  | 'below_trivial'
  | 'below_materiality'
  | 'default_keep'

export interface TrimProcedureInput {
  wpCode: string
  cycle: string
  /** 准则或平台标记为强制执行，不允许裁剪 */
  isMandatory: boolean
  /** 程序实例执行状态；`in_progress` / `completed` / `reviewed` 视为已投入工作 */
  executionStatus: string | null
  /** 审计师已手工填写过裁剪理由 */
  hasManualReason: boolean
  /** 审计师已驳回过本程序的裁剪建议 */
  suggestionRejected: boolean
  /** 底稿已有实质录入（即便程序状态仍为待执行） */
  hasWorkpaperEntry: boolean
}

export interface TrimRiskInput {
  maxRisk: 'H' | 'M' | 'L' | null
  hasSpecial: boolean
  completenessRmm: CompletenessRmm | null
  completenessSpecial: boolean
  approach: string | null
  /** 是否拟信赖内部控制；B50 实际写入的取值形态多样（`是` / `部分信赖` / 不信赖类文本） */
  reliance: string | null
}

export interface TrimMaterialityInput {
  performanceMateriality: number
  trivialThreshold: number
}

export interface TrimDecisionInput {
  procedure: TrimProcedureInput
  /** 科目余额；`null` = 该科目未在试算表出现 */
  accountAmount: number | null
  subjectDataState: SubjectDataState
  cycleHasData: boolean
  /** 重要性；整体为 `null` 表示该维度不可用 */
  materiality: TrimMaterialityInput | null
  /** B50 该科目结论；`null` = B50 无该科目 */
  risk: TrimRiskInput | null
  /** B50 是否有任何已评估科目（决定风险维度整体可用性） */
  riskDimensionAvailable: boolean
  /** 完整性豁免的循环级判据（调用方已合并项目覆盖） */
  completenessSensitiveCycle: boolean
  completenessSource: CompletenessExemptionSource
}

export interface TrimEvidence {
  wpCode: string
  cycle: string
  /** 本次实际使用的档位 */
  decidedBy: TrimDecidedBy
  // ── 数据存在性判据 ──
  accountAmount: number | null
  subjectDataState: SubjectDataState
  cycleHasData: boolean
  // ── 重要性判据（口径标识 + 实际比较用的金额）──
  materialityBasis: 'performance_materiality' | 'trivial_threshold' | null
  materialityAmount: number | null
  performanceMateriality: number | null
  trivialThreshold: number | null
  materialityAvailable: boolean
  // ── B50 风险判据 ──
  maxRisk: 'H' | 'M' | 'L' | null
  hasSpecial: boolean
  /**
   * B50 无该科目：既不享受风险保护，也不因风险被裁。
   *
   * 「未评估」与「已评估为低风险」是两种状态，混为一谈会让未填风险矩阵的项目
   * 被当成全低风险而批量裁剪。故本标记必须随决策一起留痕。
   */
  risk_unknown: boolean
  riskDimensionAvailable: boolean
  // ── 完整性判据 ──
  completenessSource: CompletenessExemptionSource
  completenessExempt: boolean
  completenessUsingPlatformDefault: boolean
}

export interface TrimDecision {
  verdict: TrimVerdict
  reasonCode: TrimReasonCode | null
  /** 面向审计师的一句话说明，含判据数值 */
  narrative: string
  evidence: TrimEvidence
  /** 附加提示（不改变 verdict） */
  hints: string[]
}

// ═══════════════════════════════════════════════════════════════════════════
// 常量与小工具（全部纯函数）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 按科目余额驱动裁剪的循环集合，由完整性清单**派生**而非另抄一份。
 *
 * `COMPLETENESS_CYCLE_RULES` 的覆盖面就是这 11 个循环（其模块文档明确写了
 * 这一等价关系，并说明 A / B / C / S 刻意不登记）。派生而不是再写一个字面量
 * 集合，是为了避免「改一处另一处不动」—— 若两份清单分叉，会出现某循环
 * 「进得了重要性判据但查不到完整性规则」这种半开状态。守卫钉死派生结果
 * 恰为 D~N 十一个循环。
 */
export const BALANCE_DRIVEN_CYCLES: ReadonlySet<string> = new Set(
  COMPLETENESS_CYCLE_RULES.map((rule) => rule.cycle),
)

/** 视为「已投入工作」的执行状态，不允许裁剪。 */
const IN_PROGRESS_STATUSES: ReadonlySet<string> = new Set([
  'in_progress',
  'completed',
  'reviewed',
])

/**
 * 不适用科目余额判据、且按既有行为恒保留的循环。
 *
 * A（报表与调整）与 S（专项）在改造前的智能裁剪里就是显式保留的，
 * 保持该行为以满足「既有保留判据行为不变」。B（计划）与 C（控制测试）
 * 由更后面的「非科目余额驱动」档统一兜住。
 */
const ALWAYS_KEEP_CYCLES: ReadonlySet<string> = new Set(['A', 'S'])

function normalizeCode(value: unknown): string {
  return String(value ?? '').trim().toUpperCase()
}

function normalizeText(value: unknown): string {
  return String(value ?? '').trim().toLowerCase()
}

/** 金额格式化（千分符 + 两位小数），纯函数、不依赖任何 store 或区域设置。 */
function formatAmount(value: number): string {
  if (!Number.isFinite(value)) return String(value)
  const negative = value < 0
  const fixed = Math.abs(value).toFixed(2)
  const dot = fixed.indexOf('.')
  const intPart = fixed.slice(0, dot)
  const decPart = fixed.slice(dot + 1)
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${negative ? '-' : ''}${grouped}.${decPart}`
}

/** 该金额是否可参与数值比较（`null` 表示科目未在试算表出现，不得当 0 比较）。 */
function isComparableAmount(value: number | null): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

/** 风险等级中文标签，供 narrative 使用。 */
function riskLabel(maxRisk: 'H' | 'M' | 'L' | null): string {
  if (maxRisk === 'H') return '高'
  if (maxRisk === 'M') return '中'
  if (maxRisk === 'L') return '低'
  return '未评估'
}

/**
 * 是否明确「不拟信赖内部控制」。
 *
 * B50 写入的取值形态多样（`是` / `部分信赖` / `否` / `不信赖` / `不拟信赖内部控制`），
 * 故不能只判 `=== '否'`。判定顺序必须是「不适用 → 否定 → 肯定」：
 * `不信赖` 含子串 `信赖`，先判肯定会把否定判成肯定；而 `不适用` 含 `不`，
 * 先判否定又会把「未评估」判成「不信赖」并误发提示。
 */
function isControlNotRelied(reliance: string | null): boolean {
  const text = normalizeText(reliance)
  if (!text) return false
  // 1. 不适用 / 未评估 —— 既非信赖也非不信赖
  if (
    text.includes('不适用')
    || text.includes('未评估')
    || text.includes('未确定')
    || text === 'n/a'
    || text === 'na'
  ) {
    return false
  }
  // 2. 明确否定
  if (
    text.includes('不信赖')
    || text.includes('不拟信赖')
    || text.includes('不予信赖')
    || text.includes('不依赖')
    || text.includes('不信任')
    || text === '否'
    || text === 'no'
    || text === 'false'
    || text === '不'
  ) {
    return true
  }
  // 3. 其余（含 `是` / `信赖` / `部分信赖` / 无法判读）一律不发提示
  return false
}

/** 是否采用实质性程序方案（容忍 `substantive_only` 与中文写法）。 */
function isSubstantiveApproach(approach: string | null): boolean {
  const text = normalizeText(approach)
  if (!text) return false
  return text.includes('substantive') || text.includes('实质性')
}

// ═══════════════════════════════════════════════════════════════════════════
// 决策内核
// ═══════════════════════════════════════════════════════════════════════════

interface EvidenceSeed {
  input: TrimDecisionInput
  cycle: string
  exemption: {
    exempt: boolean
    source: CompletenessExemptionSource
    usingPlatformDefault: boolean
    rationale: string
  }
}

function buildEvidence(
  seed: EvidenceSeed,
  decidedBy: TrimDecidedBy,
  materialityBasis: TrimEvidence['materialityBasis'] = null,
): TrimEvidence {
  const { input, cycle, exemption } = seed
  const materiality = input.materiality
  const materialityAmount = materialityBasis === 'performance_materiality'
    ? materiality?.performanceMateriality ?? null
    : materialityBasis === 'trivial_threshold'
      ? materiality?.trivialThreshold ?? null
      : null
  return {
    wpCode: String(input.procedure?.wpCode ?? ''),
    cycle,
    decidedBy,
    accountAmount: isComparableAmount(input.accountAmount) ? input.accountAmount : null,
    subjectDataState: input.subjectDataState,
    cycleHasData: input.cycleHasData === true,
    materialityBasis,
    materialityAmount,
    performanceMateriality: materiality ? materiality.performanceMateriality : null,
    trivialThreshold: materiality ? materiality.trivialThreshold : null,
    materialityAvailable: materiality !== null && materiality !== undefined,
    maxRisk: input.risk ? (input.risk.maxRisk ?? null) : null,
    hasSpecial: input.risk ? input.risk.hasSpecial === true : false,
    risk_unknown: !input.risk,
    riskDimensionAvailable: input.riskDimensionAvailable === true,
    completenessSource: exemption.source,
    completenessExempt: exemption.exempt,
    completenessUsingPlatformDefault: exemption.usingPlatformDefault,
  }
}

/**
 * 对单个程序给出裁剪结论。
 *
 * 决策顺序（前者命中即短路，后者完全不参与）：
 *
 * | 档 | 判据 | 结论 |
 * |---|---|---|
 * | 1 | 特别风险 或 重大错报风险为高 | `keep` |
 * | 2 | 强制保留：强制程序 / A·S 循环 / 已有执行进度 / 已手工填理由 / 底稿已录入 / 建议已被驳回 | `keep` |
 * | 3 | 非科目余额驱动循环 | `keep` |
 * | 4 | 科目或循环在试算表无数据 | `auto_trim` + `no_data` |
 * | 5 | 完整性豁免命中 | `keep` |
 * | 6 | 重要性维度不可用 | `keep` |
 * | 7 | 余额绝对值低于明显微小错报临界值 | `suggest_trim` + `below_trivial` |
 * | 8 | 余额绝对值低于实际执行重要性 | `suggest_trim` + `below_materiality` |
 * | 9 | 默认 | `keep`（拟不信赖内部控制时附提示） |
 *
 * 档 1 排在最前是设计要点：特别风险科目即便**在试算表里完全没有数据**也不裁 ——
 * 那种情形恰恰是需要查证的异常。档 5 排在档 7/8 之前同理：完整性风险与账面
 * 金额无关，用金额判据豁免它方向就是反的。
 */
export function decideTrim(input: TrimDecisionInput): TrimDecision {
  const procedure = input.procedure ?? ({} as TrimProcedureInput)
  const cycle = normalizeCode(procedure.cycle)
  const risk = input.risk ?? null

  // 完整性豁免：判定委托给共享真源，不在本模块再写一份。
  //
  // 认定级（B50 该科目的完整性认定）优先且短路，循环级只在认定缺失时生效。
  // 循环级取值以调用方已合并好的 `completenessSensitiveCycle` 为准，故一律作为
  // 项目覆盖传入 —— 这样共享函数不会用平台默认清单去覆盖调用方已确认的结论。
  // 而 `source` 与 `usingPlatformDefault` 两个溯源标签仍取调用方给的
  // `completenessSource`（只有它知道那个布尔值是平台默认还是项目已确认）。
  const resolved = resolveCompletenessExemption({
    completenessRmm: risk?.completenessRmm ?? null,
    completenessSpecial: risk?.completenessSpecial === true,
    cycle,
    projectOverride: { [cycle]: input.completenessSensitiveCycle === true },
  })
  const cycleRule = COMPLETENESS_CYCLE_RULES.find((rule) => rule.cycle === cycle) ?? null
  const exemption = resolved.source === 'assertion' || resolved.source === 'none'
    ? {
      exempt: resolved.exempt,
      source: resolved.source,
      usingPlatformDefault: false,
      rationale: resolved.rationale,
    }
    : {
      exempt: resolved.exempt,
      source: input.completenessSource ?? 'cycle_default',
      usingPlatformDefault: input.completenessSource === 'cycle_default',
      rationale: cycleRule ? cycleRule.rationale : resolved.rationale,
    }

  const seed: EvidenceSeed = { input, cycle, exemption }
  const amount = input.accountAmount
  const amountText = isComparableAmount(amount)
    ? `${formatAmount(amount)} 元`
    : '未在试算平衡表中出现'

  // ── 档 1：风险保护 ────────────────────────────────────────────────────────
  if (risk && (risk.hasSpecial === true || risk.maxRisk === 'H')) {
    const which = risk.hasSpecial === true ? '特别风险' : '高重大错报风险'
    return {
      verdict: 'keep',
      reasonCode: null,
      narrative:
        `保留：本科目在风险评估中被识别为${which}（重大错报风险等级 ${riskLabel(risk.maxRisk)}），`
        + `按准则须对其实施实质性程序，不因科目余额（${amountText}）或重要性水平而裁剪。`,
      evidence: buildEvidence(seed, 'risk_protection'),
      hints: [],
    }
  }

  // ── 档 2：强制保留 ────────────────────────────────────────────────────────
  if (procedure.isMandatory === true) {
    return {
      verdict: 'keep',
      reasonCode: null,
      narrative: `保留：本程序被标记为强制执行程序，不允许裁剪（科目余额 ${amountText}）。`,
      evidence: buildEvidence(seed, 'mandatory'),
      hints: [],
    }
  }
  if (ALWAYS_KEEP_CYCLES.has(cycle)) {
    return {
      verdict: 'keep',
      reasonCode: null,
      narrative:
        `保留：${cycle} 循环不按科目余额驱动裁剪（报表与调整、专项事项类程序与单一科目余额无对应关系），`
        + '恒予保留。',
      evidence: buildEvidence(seed, 'non_data_driven_cycle_mandatory'),
      hints: [],
    }
  }
  if (IN_PROGRESS_STATUSES.has(normalizeText(procedure.executionStatus))) {
    return {
      verdict: 'keep',
      reasonCode: null,
      narrative:
        `保留：本程序执行状态为「${String(procedure.executionStatus)}」，已投入审计工作，`
        + '裁剪会丢弃已完成的程序记录与复核痕迹。',
      evidence: buildEvidence(seed, 'execution_progress'),
      hints: [],
    }
  }
  if (procedure.hasManualReason === true) {
    return {
      verdict: 'keep',
      reasonCode: null,
      narrative: '保留：审计师已手工填写本程序的适用性理由，人工判断优先于自动判据。',
      evidence: buildEvidence(seed, 'manual_reason'),
      hints: [],
    }
  }
  if (procedure.hasWorkpaperEntry === true) {
    return {
      verdict: 'keep',
      reasonCode: null,
      narrative:
        '保留：对应底稿已有实质录入内容，即便程序状态仍为待执行也不裁剪 ——'
        + '裁剪会让已录入的审计工作在程序清单上消失。',
      evidence: buildEvidence(seed, 'workpaper_entry'),
      hints: [],
    }
  }
  if (procedure.suggestionRejected === true) {
    return {
      verdict: 'keep',
      reasonCode: null,
      narrative: '保留：审计师已驳回本程序的裁剪建议，不再重复提示。',
      evidence: buildEvidence(seed, 'suggestion_rejected'),
      hints: [],
    }
  }

  // ── 档 3：非科目余额驱动循环 ──────────────────────────────────────────────
  if (!BALANCE_DRIVEN_CYCLES.has(cycle)) {
    return {
      verdict: 'keep',
      reasonCode: null,
      narrative:
        `保留：${cycle || '(未知)'} 循环不属于按科目余额驱动裁剪的范围，`
        + '科目金额与数据存在性判据对其不适用。',
      evidence: buildEvidence(seed, 'non_balance_driven_cycle'),
      hints: [],
    }
  }

  // ── 档 4：数据存在性（科目底稿级优先于循环级）────────────────────────────
  const subjectNoData = input.subjectDataState === 'no_data'
  const cycleNoData = input.subjectDataState === 'unknown' && input.cycleHasData === false
  if (subjectNoData || cycleNoData) {
    const basis = subjectNoData
      ? '该科目在试算平衡表中无数据'
      : `${cycle} 循环相关科目在试算平衡表中均无数据`
    return {
      verdict: 'auto_trim',
      reasonCode: 'no_data',
      narrative:
        `自动裁剪：${basis}（科目余额 ${amountText}），无可实施实质性程序的对象，`
        + '故标记为不适用。',
      evidence: buildEvidence(seed, 'no_data'),
      hints: [],
    }
  }

  // ── 档 5：完整性豁免 ──────────────────────────────────────────────────────
  if (exemption.exempt) {
    const prefix = exemption.source === 'assertion'
      ? '本科目的完整性认定被评估为高风险或特别风险'
      : `${cycle} 循环属完整性敏感范围`
    return {
      verdict: 'keep',
      reasonCode: null,
      narrative:
        `保留：${prefix}，完整性方向的漏记与账面金额大小无关（漏记本身就会压低账面金额），`
        + `故科目余额 ${amountText} 不产生裁剪建议。判据依据 —— ${exemption.rationale}`,
      evidence: buildEvidence(seed, 'completeness_exemption'),
      hints: [],
    }
  }

  // ── 档 6：重要性维度不可用 ────────────────────────────────────────────────
  const materiality = input.materiality
  if (!materiality) {
    return {
      verdict: 'keep',
      reasonCode: null,
      narrative:
        `保留：本项目尚未设置重要性水平，重要性维度不可用，故不产生金额类裁剪建议`
        + `（科目余额 ${amountText}）。`,
      evidence: buildEvidence(seed, 'materiality_unavailable'),
      hints: [],
    }
  }

  // ── 档 7 / 8：重要性判据（只产生建议，永不自动裁）────────────────────────
  //
  // `accountAmount === null` 表示该科目未在试算表出现，不得参与数值比较 ——
  // `Math.abs(null)` 是 0，会让它被误判成「低于阈值」而产生建议，而这种情形
  // 的正确归属是档 4 的数据存在性判据。
  if (isComparableAmount(amount)) {
    const absAmount = Math.abs(amount)
    if (absAmount < materiality.trivialThreshold) {
      return {
        verdict: 'suggest_trim',
        reasonCode: 'below_trivial',
        narrative:
          `建议裁剪（需人工确认）：本期科目余额 ${formatAmount(absAmount)} 元低于明显微小错报临界值 `
          + `${formatAmount(materiality.trivialThreshold)} 元，该科目单独的错报敞口有限；`
          + '是否裁剪仍需结合完整性风险与汇总影响判断，故不自动执行。',
        evidence: buildEvidence(seed, 'below_trivial', 'trivial_threshold'),
        hints: [],
      }
    }
    if (absAmount < materiality.performanceMateriality) {
      return {
        verdict: 'suggest_trim',
        reasonCode: 'below_materiality',
        narrative:
          `建议裁剪（需人工确认）：本期科目余额 ${formatAmount(absAmount)} 元低于实际执行重要性 `
          + `${formatAmount(materiality.performanceMateriality)} 元；`
          + '请注意若干低于该水平的科目汇总错报仍可能超过可容忍水平，批量应用前须通过汇总闸校验。',
        evidence: buildEvidence(seed, 'below_materiality', 'performance_materiality'),
        hints: [],
      }
    }
  }

  // ── 档 9：默认保留（+ 不信赖控制提示）────────────────────────────────────
  const hints: string[] = []
  if (risk && isSubstantiveApproach(risk.approach) && isControlNotRelied(risk.reliance)) {
    hints.push(
      '本科目拟不信赖内部控制且采用实质性程序方案，实质性程序需相应加强'
      + '（扩大样本量、提高测试细节程度或增加期末程序），不宜按常规范围执行。',
    )
  }
  return {
    verdict: 'keep',
    reasonCode: null,
    narrative:
      `保留：科目余额 ${amountText}`
      + (isComparableAmount(amount)
        ? `不低于实际执行重要性 ${formatAmount(materiality.performanceMateriality)} 元`
        : '无法参与重要性金额比较')
      + `，重大错报风险等级为${riskLabel(risk ? risk.maxRisk : null)}，按常规执行本程序。`,
    evidence: buildEvidence(seed, 'default_keep'),
    hints,
  }
}
