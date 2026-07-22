/**
 * I2 开发支出 — CAS6五条件资本化判断引擎（纯函数）
 *
 * CAS6第9条：开发阶段支出须**同时**满足下列条件，才能确认为无形资产：
 *   ① 技术可行性 — 完成该无形资产使其能够使用或出售在技术上具有可行性
 *   ② 完成意图 — 具有完成该无形资产并使用或出售的意图
 *   ③ 经济利益方式 — 无形资产产生经济利益的方式，能够证明产品/自身存在市场，或对内部使用有用
 *   ④ 资源支持 — 有足够的技术、财务资源和其他资源支持，以完成开发并有能力使用或出售
 *   ⑤ 可靠计量 — 归属于该无形资产开发阶段的支出能够可靠地计量
 *
 * Spec: .kiro/specs/i2-development-expenditure/ Requirements: 5.1-5.8
 */

export interface CAS6Condition {
  id: 1 | 2 | 3 | 4 | 5
  name: string
  result: 'yes' | 'no' | 'na' | ''
  evidence: string
  /** 条件级附件索引/文件名 */
  attachments?: string[]
}

export interface CapitalizationResult {
  isMet: boolean
  missingConditions: number[]
  conclusion: string
}

export interface ResearchSplitResult {
  isValid: boolean
  difference: number
}

/** CAS6 五条件短名（对齐准则表述；修正旧版④⑤标签错位） */
export const CAS6_CONDITION_NAMES: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: '技术可行性',
  2: '完成意图',
  3: '经济利益方式',
  4: '资源支持',
  5: '可靠计量',
}

/** 准则原文要点 */
export const CAS6_CONDITION_ANALYSIS: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: '完成该无形资产使其能够使用或出售在技术上具有可行性（研究成果已形成可据以开发的基本框架）。',
  2: '具有完成该无形资产并使用或出售的意图（管理层已作出完成开发的明确决策）。',
  3: '无形资产产生经济利益的方式：能够证明运用该无形资产生产的产品存在市场，或无形资产自身存在市场；若自用，应证明对内部有用。',
  4: '有足够的技术、财务资源和其他资源支持，以完成该无形资产的开发，并有能力使用或出售该无形资产。',
  5: '归属于该无形资产开发阶段的支出能够可靠地计量（可按项目单独归集人工、材料等）。',
}

/** 具体情形/证据示例（对齐 Excel 右侧「开发支出资本化判断示例」） */
export const CAS6_CONDITION_EXAMPLES: Record<1 | 2 | 3 | 4 | 5, string> = {
  1: '例：已完成样品/原型设计与测试；技术评审通过；具备量产前技术路径。',
  2: '例：立项批复、项目计划书、里程碑安排；董事会/管理层决议继续开发并拟使用或出售。',
  3: '例：可行性研究报告证明盈利或内部效用；市场调研、意向性订单、内部使用论证。',
  4: '例：配备专业研发人员；已落实开发预算/融资安排；配套设备与协作资源到位。',
  5: '例：按项目核算工时、材料领用、委外合同；明细账可区分研究/开发阶段支出。',
}

export const CAS6_OBJECTIVES = [
  '检查研发支出资本化的会计处理是否符合企业会计准则、业务特点及行业惯例，政策运用是否一贯。',
  '检查研究阶段与开发阶段的划分是否合理，资本化开始时点（完成时点）的确定是否有充分依据。',
] as const

export const CAS6_PROCEDURE_HINTS: string[] = [
  '测试与研发支出相关的内部控制运行有效性。',
  '将企业资本化标准与同行业可比公司对比，关注是否过于激进。',
  '了解同类项目的典型开发流程与行业惯例时点。',
  '询问管理层及研发人员，了解研究/开发阶段划分标准及实际执行。',
  '检查立项文件、工作计划、里程碑报告及管理层复核记录。',
  '检查可行性研究报告、研发预算、董事会决议、外部专家意见及销售合同等，评价技术可行性。',
  '与管理层讨论商业化应用前景，收集市场信息以评价未来经济利益。',
  '评价完成开发所需技术、财务及其他资源是否充足，以及开发完成后的支持能力。',
  '询问是否存在未予资本化的项目，评价是否符合会计政策。',
  '获取研发项目清单及费用归集明细，核对合同、发票、工时等，确认支出真实且与研发相关。',
]

export function createEmptyCAS6Conditions(): CAS6Condition[] {
  return ([1, 2, 3, 4, 5] as const).map((id) => ({
    id,
    name: CAS6_CONDITION_NAMES[id],
    result: '' as const,
    evidence: '',
    attachments: [],
  }))
}

/**
 * 据项目描述/依据关键词启发式建议五条件（无外部 AI 时的本地建议；可再接 LLM）。
 */
export function suggestCas6ConditionsFromText(opts: {
  projectContent?: string
  capBasis?: string
  supportingEvidence?: string
  personnelComposition?: string
}): CAS6Condition[] {
  const blob = [
    opts.projectContent,
    opts.capBasis,
    opts.supportingEvidence,
    opts.personnelComposition,
  ].filter(Boolean).join(' ').toLowerCase()

  const conds = createEmptyCAS6Conditions()
  const hit = (keys: string[]) => keys.some((k) => blob.includes(k.toLowerCase()))

  const rules: Array<{ id: 1 | 2 | 3 | 4 | 5; keys: string[]; evidence: string }> = [
    { id: 1, keys: ['原型', '样品', '技术可行', '测试通过', '评审'], evidence: '文本提及技术验证/原型/评审，建议补充测试记录。' },
    { id: 2, keys: ['立项', '决议', '计划', '董事会', '继续开发'], evidence: '文本提及立项/决议/计划，建议附批复文件。' },
    { id: 3, keys: ['市场', '订单', '可行性研究', '商业化', '内部使用', '自用'], evidence: '文本提及市场/可行性/自用，建议附调研或效用论证。' },
    { id: 4, keys: ['预算', '融资', '人员', '团队', '资金'], evidence: '文本提及预算/人员/资金，建议附预算与人员配备说明。' },
    { id: 5, keys: ['工时', '领料', '单独核算', '项目核算', '明细'], evidence: '文本提及工时/领料/单独核算，建议附成本归集底稿。' },
  ]

  for (const r of rules) {
    if (hit(r.keys)) {
      const c = conds[r.id - 1]
      c.result = 'yes'
      c.evidence = r.evidence
    }
  }
  return conds
}

/**
 * 评估 CAS6 资本化五条件。
 * 规则（对齐准则「同时满足」）：
 * - 五个条件均须为「是」才可资本化
 * - 「否」或未填/空 → 计入缺失
 * - 「不适用」在资本化语境下视为未满足（开发支出五条件通常均适用）
 */
export function evaluateCapitalization(conditions: CAS6Condition[]): CapitalizationResult {
  if (!conditions.length) {
    return {
      isMet: false,
      missingConditions: [],
      conclusion: '未填写任何条件，无法判断资本化',
    }
  }

  const byId = new Map(conditions.map((c) => [c.id, c]))
  const missing: number[] = []
  for (const id of [1, 2, 3, 4, 5] as const) {
    const c = byId.get(id)
    if (!c || c.result !== 'yes') missing.push(id)
  }

  if (missing.length === 0) {
    return {
      isMet: true,
      missingConditions: [],
      conclusion: '五条件同时满足，可资本化',
    }
  }

  const allNa = conditions.length > 0 && conditions.every((c) => c.result === 'na')
  if (allNa) {
    return {
      isMet: false,
      missingConditions: missing,
      conclusion: '所有条件均标记为不适用，无法确认资本化',
    }
  }

  const missingNames = missing.map((id) => CAS6_CONDITION_NAMES[id as 1 | 2 | 3 | 4 | 5])
  return {
    isMet: false,
    missingConditions: missing,
    conclusion: `不满足资本化条件（须五条件同时为「是」），待满足：${missingNames.join('、')}`,
  }
}

export function calcResearchTotal(expenseI6: number, capitalizedI2: number): number {
  return expenseI6 + capitalizedI2
}

export function validateResearchSplit(
  expenseI6: number,
  capitalizedI2: number,
  totalBudget: number,
): ResearchSplitResult {
  const difference = totalBudget - (expenseI6 + capitalizedI2)
  return {
    isValid: Math.abs(difference) < 1e-6,
    difference,
  }
}
