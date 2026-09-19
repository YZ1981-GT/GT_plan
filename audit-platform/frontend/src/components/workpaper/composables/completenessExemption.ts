/**
 * 完整性豁免判据（纯函数，零 Vue 依赖、零 IO）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 6
 * 守卫: `__tests__/completenessExemption.spec.ts`
 * Requirements: 5.1 / 5.2 / 5.3 / 5.4 / 5.7 / 5.8
 *
 * ## 它解决什么问题
 *
 * 程序裁剪的重要性维度判据（「科目余额低于实际执行重要性 ⇒ 建议裁掉该科目程序」）
 * 在审计上**对完整性风险高的科目必须失效**，三条依据：
 *
 * 1. **低估风险方向**：重要性用于评价错报与确定样本量，不是「科目小就不查」。
 *    账面金额小本身可能就是**完整性认定**出了问题的结果 —— 少记负债、少记费用、
 *    跨期少记收入，账面越小越可能是漏记而不是真的不重要。完整性风险与账面金额
 *    的大小无关，用金额去豁免它等于用「症状」豁免「病因」。
 * 2. **汇总效应**：若干各自低于实际执行重要性的科目，其错报汇总起来可能远超
 *    财务报表整体重要性；准则要求在评价错报时考虑汇总影响，故逐科目豁免会
 *    系统性低估总体错报敞口。
 * 3. **特别风险不受金额豁免**：对识别为特别风险的领域必须实施实质性程序
 *    （CAS 1231），金额小也必须做，不存在「太小所以不做」的例外。
 *
 * ## 为什么认定级必须优先于循环级
 *
 * B50 风险评估矩阵本就是**按六个认定逐格评估**的（存在/完整性/准确性/截止/
 * 分类/列报），`completeness` 那一格的重大错报风险与特别风险标记，是审计师针对
 * **这个具体科目**在**这个具体项目**上做出的判断。循环级默认清单只是平台按
 * 「管理层动机方向」给出的**行业经验值**（负债费用类倾向少记以虚增利润与净资产，
 * 资产类倾向高估），精度远低于逐科目认定。
 *
 * 所以：只要该科目的完整性认定已被评估过（`completenessRmm` 非 null 或
 * `completenessSpecial` 为真），就**完全不看**循环级清单与项目覆盖 —— 否则会出现
 * 「审计师明确评了低风险，却被平台默认清单强行判成完整性敏感」这种用平台经验值
 * 覆盖项目专业判断的倒挂。反之，认定缺失时（B50 未填）才退回循环级默认，
 * 并由 `usingPlatformDefault` 如实标注「使用平台默认，未经本项目确认」，
 * 供裁剪充分性复核视图提示质控与项目质量控制复核人。
 *
 * ## 术语约定
 *
 * 平台既有 `GtB50RiskAssessment.vue` 把 `overall_materiality` 命名为一个两字母
 * 缩写、把 `performance_materiality` 命名为另一个两字母缩写，与审计通用含义**正好
 * 相反**。故本模块及本 spec 新增代码一律使用数据库字段名全称
 * （`performanceMateriality` / `trivialThreshold` / `overallMateriality`），
 * 不使用任何两三字母缩写作标识符。
 */

/** 完整性认定的重大错报风险等级（B50 矩阵 `completeness` 格取值）。 */
export type CompletenessRmm = 'H' | 'M' | 'L'

/** 判据来源：认定级 / 循环级默认 / 循环级项目覆盖 / 本判据不适用。 */
export type CompletenessExemptionSource =
  | 'assertion'
  | 'cycle_default'
  | 'cycle_override'
  | 'none'

export interface CompletenessCycleRule {
  cycle: string
  /** 默认是否视为完整性敏感 */
  sensitiveByDefault: boolean
  /** 审计依据（不得为空，Requirement 5.4） */
  rationale: string
}

/**
 * 平台默认清单（声明式真源，Requirement 5.3）。
 *
 * 覆盖面 = 11 个科目余额驱动循环（与 `ProcedureTrimming.vue` 的
 * `DATA_DRIVEN_CYCLES` 一致）。A（报表与调整）、B（计划）、C（控制测试）、
 * S（专项）不在其中 —— 它们不是按科目余额驱动裁剪的，完整性认定这一判据
 * 对其不适用，故清单里**刻意不登记**这四个循环。
 *
 * 默认取值的总体依据：
 * - 默认**开**（负债与费用类）：管理层的舞弊动机方向是**少记负债、少记费用**
 *   以虚增利润与净资产，故完整性方向的风险系统性偏高，且与账面金额无关。
 * - 默认**关**（资产类与权益类）：主风险方向是**存在与估值（高估）**，
 *   账面金额小则该科目本身的错报敞口也小，用金额判据建议裁剪是成立的。
 */
export const COMPLETENESS_CYCLE_RULES: readonly CompletenessCycleRule[] = Object.freeze([
  Object.freeze({
    cycle: 'L',
    sensitiveByDefault: true,
    rationale:
      '债务循环的完整性风险最高：表外负债与未记录负债（未开票借款、抽屉协议、关联方资金占用、担保与承诺）是最经典的漏记形态，'
      + '账面余额小恰恰是需要重点查证的对象而不是可以豁免的理由，必须实施搜索未记录负债的程序。',
  }),
  Object.freeze({
    cycle: 'J',
    sensitiveByDefault: true,
    rationale:
      '职工薪酬循环的完整性风险高：应付职工薪酬、职工福利、社会保险与住房公积金少记可直接虚增利润，'
      + '且该循环存在独立于账面金额的验证途径（人数与工资标准勾稽、社保缴费基数核对），账面小不构成不做程序的依据。',
  }),
  Object.freeze({
    cycle: 'N',
    sensitiveByDefault: true,
    rationale:
      '税金循环的完整性风险高：应交税费少记（含未申报、少申报、滞纳金与罚款未计提）不仅影响报表，'
      + '还可能引致税务处罚与或有负债，后果与账面金额不成比例，须结合纳税申报表与完税凭证独立验证。',
  }),
  Object.freeze({
    cycle: 'K',
    sensitiveByDefault: true,
    rationale:
      '管理循环的其他应付款、其他流动负债常是未记录负债的藏身处（暂收款、代垫款、往来挂账、押金保证金），'
      + '完整性方向的漏记不会体现在账面余额上，故不因期末余额低于重要性水平而豁免程序。',
  }),
  Object.freeze({
    cycle: 'D',
    sensitiveByDefault: true,
    rationale:
      '收入循环的截止期完整性风险成立：跨期少记收入（本期已发生却记入下期）会低估当期业绩，'
      + '与高估方向的舞弊推定并列存在，故按用户裁决默认开启完整性敏感，项目组可结合客户舞弊动机方向关闭。',
  }),
  Object.freeze({
    cycle: 'E',
    sensitiveByDefault: false,
    rationale:
      '货币资金的主风险方向是存在与估值（虚增账面余额、受限资金未披露），完整性方向另有银行函证与'
      + '已开立账户清单核对两道程序独立覆盖，故不需要在金额判据之外再设完整性豁免。',
  }),
  Object.freeze({
    cycle: 'F',
    sensitiveByDefault: false,
    rationale:
      '存货的主风险方向是存在与估值（虚增数量、跌价准备计提不足），完整性方向的漏记会同时降低资产与利润，'
      + '不符合管理层动机；账面金额低于重要性水平时该科目的错报敞口本身有限。',
  }),
  Object.freeze({
    cycle: 'G',
    sensitiveByDefault: false,
    rationale:
      '投资类科目的主风险方向是存在与计价（虚构投资、公允价值与减值判断），少记投资会低估资产与投资收益，'
      + '与虚增业绩的动机相反；故账面小则敞口小，金额判据可用。',
  }),
  Object.freeze({
    cycle: 'H',
    sensitiveByDefault: false,
    rationale:
      '固定资产等长期资产的主风险方向是存在与估值（虚构资产、折旧与减值计提不足、费用资本化），'
      + '漏记资产会同时减少资产与当期利润，不符合虚增业绩动机，故不设完整性豁免。',
  }),
  Object.freeze({
    cycle: 'I',
    sensitiveByDefault: false,
    rationale:
      '无形资产与商誉的主风险方向是存在与估值（研发支出资本化条件、商誉减值测试），'
      + '少记该类资产会低估净资产而非虚增，故账面金额低于重要性水平时按金额判据处理即可。',
  }),
  Object.freeze({
    cycle: 'M',
    sensitiveByDefault: false,
    rationale:
      '权益类项目由章程、决议、出资凭证与工商登记等外部证据直接印证，其错报形态以列报与分类为主，'
      + '完整性方向的漏记极易被外部证据发现，故不因完整性风险而豁免金额判据。',
  }),
])

const RULE_BY_CYCLE: ReadonlyMap<string, CompletenessCycleRule> = new Map(
  COMPLETENESS_CYCLE_RULES.map((rule) => [rule.cycle, rule]),
)

export interface CompletenessExemptionResult {
  exempt: boolean
  source: CompletenessExemptionSource
  /** 用于复核视图标注"使用平台默认，未经本项目确认" */
  usingPlatformDefault: boolean
  rationale: string
}

/** 循环代码归一：容忍前后空白与小写输入。 */
function normalizeCycle(cycle: string): string {
  return String(cycle ?? '').trim().toUpperCase()
}

/**
 * 在项目覆盖表里查该循环的显式表态。
 *
 * 返回 `undefined` 表示「项目组未对该循环表态」；`false` 与 `true` 都算**已表态**，
 * 故不能用真值判断（`projectOverride = { E: false }` 也必须走 `cycle_override`）。
 */
function lookupOverride(
  projectOverride: Record<string, boolean> | null,
  cycle: string,
): boolean | undefined {
  if (!projectOverride || typeof projectOverride !== 'object') return undefined
  for (const key of Object.keys(projectOverride)) {
    if (normalizeCycle(key) !== cycle) continue
    const raw = projectOverride[key]
    if (typeof raw !== 'boolean') continue
    return raw
  }
  return undefined
}

/**
 * 解析某科目/循环是否豁免重要性金额判据。
 *
 * 判定顺序（前者短路，后者完全不参与）：
 * 1. **认定级**（`completenessRmm` 非 null 或 `completenessSpecial` 为真）
 *    ⇒ `source = 'assertion'`，结论只看认定，与 `cycle`、`projectOverride` 无关。
 *    豁免条件 = 完整性认定为高风险（`H`）或被标记为特别风险；中、低风险不豁免。
 * 2. **本判据不适用**：循环不在默认清单内（A/B/C/S 及任何未登记的循环代码）
 *    ⇒ `source = 'none'`、不豁免。此时即便传入项目覆盖也不采纳 ——
 *    非科目余额驱动的循环压根不走金额判据，覆盖它没有意义。
 * 3. **项目覆盖**：项目组对该循环有显式表态（`true` 或 `false` 都算）
 *    ⇒ `source = 'cycle_override'`，按覆盖值决定是否豁免。
 * 4. **平台默认** ⇒ `source = 'cycle_default'`，按清单 `sensitiveByDefault` 决定，
 *    并且这是**唯一**会把 `usingPlatformDefault` 置真的分支。
 */
export function resolveCompletenessExemption(args: {
  completenessRmm: CompletenessRmm | null
  completenessSpecial: boolean
  cycle: string
  projectOverride: Record<string, boolean> | null
}): CompletenessExemptionResult {
  const { completenessRmm, completenessSpecial, cycle, projectOverride } = args
  const isSpecial = completenessSpecial === true
  const hasAssertion = completenessRmm !== null && completenessRmm !== undefined

  // ── 1. 认定级优先且短路：审计师已在 B50 逐认定评估过这个科目 ──────────────
  if (hasAssertion || isSpecial) {
    if (isSpecial) {
      return {
        exempt: true,
        source: 'assertion',
        usingPlatformDefault: false,
        rationale:
          '本科目的完整性认定被评估为特别风险，按准则须对特别风险实施实质性程序，'
          + '不因账面金额低于实际执行重要性而裁剪。该结论来自审计师在风险评估矩阵中的科目级判断。',
      }
    }
    if (completenessRmm === 'H') {
      return {
        exempt: true,
        source: 'assertion',
        usingPlatformDefault: false,
        rationale:
          '本科目的完整性认定被评估为高重大错报风险，账面金额不构成豁免依据（漏记本身就会压低账面金额），'
          + '故不进入重要性金额判据的裁剪建议。该结论来自审计师在风险评估矩阵中的科目级判断。',
      }
    }
    return {
      exempt: false,
      source: 'assertion',
      usingPlatformDefault: false,
      rationale:
        `本科目的完整性认定被评估为${completenessRmm === 'M' ? '中等' : '低'}重大错报风险，`
        + '不触发完整性豁免，可按重要性金额判据产生裁剪建议。该结论来自审计师在风险评估矩阵中的科目级判断，'
        + '优先于平台默认的循环级清单。',
    }
  }

  // ── 2. 本判据不适用：非科目余额驱动的循环 ─────────────────────────────────
  const normalized = normalizeCycle(cycle)
  const rule = RULE_BY_CYCLE.get(normalized)
  if (!rule) {
    return {
      exempt: false,
      source: 'none',
      usingPlatformDefault: false,
      rationale:
        `循环 ${normalized || '(空)'} 不是按科目余额驱动裁剪的循环（报表与调整、计划、控制测试、专项等），`
        + '完整性认定豁免这一判据对其不适用，故既不豁免也不标注平台默认。',
    }
  }

  // ── 3. 项目覆盖：true / false 都算已表态 ─────────────────────────────────
  const overridden = lookupOverride(projectOverride, normalized)
  if (overridden !== undefined) {
    return {
      exempt: overridden,
      source: 'cycle_override',
      usingPlatformDefault: false,
      rationale:
        `本项目已在风险评估中确认循环 ${normalized} ${overridden ? '属于' : '不属于'}完整性敏感范围，`
        + `${overridden ? '故豁免重要性金额判据，低于实际执行重要性也不产生裁剪建议' : '故可按重要性金额判据产生裁剪建议'}。`
        + `该结论已经本项目组确认，覆盖平台默认值（平台默认为${rule.sensitiveByDefault ? '敏感' : '不敏感'}）。`,
    }
  }

  // ── 4. 平台默认：唯一会标注 usingPlatformDefault 的分支 ───────────────────
  return {
    exempt: rule.sensitiveByDefault,
    source: 'cycle_default',
    usingPlatformDefault: true,
    rationale:
      `使用平台默认，未经本项目确认：循环 ${normalized} 默认${rule.sensitiveByDefault ? '视为' : '不视为'}完整性敏感。`
      + `平台依据 —— ${rule.rationale}`
      + '（本项目尚未填写该科目的完整性认定评估，也未在风险评估中对该循环表态；'
      + '建议补充风险评估矩阵以取得科目级判断。）',
  }
}
