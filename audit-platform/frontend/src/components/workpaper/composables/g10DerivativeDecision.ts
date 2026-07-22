/** G10-8 衍生工具识别决策树（A→B→C→D→E，对齐 Excel 编制说明） */

export type G10YesNo = 'yes' | 'no' | ''

export const G10_DERIVATIVE_VARIABLE_CHECKS = [
  { key: 'interestRate', label: '利率' },
  { key: 'financialPrice', label: '金融工具价格' },
  { key: 'commodityPrice', label: '商品价格' },
  { key: 'exchangeRate', label: '汇率' },
  { key: 'index', label: '指数' },
  { key: 'creditRating', label: '信用等级或信用指数' },
  { key: 'otherFinancial', label: '其他变量（仅金融变量）' },
  { key: 'otherNonFinancial', label: '其他非金融变量' },
] as const

export type G10DerivativeVariableKey = (typeof G10_DERIVATIVE_VARIABLE_CHECKS)[number]['key']

export type G10DerivativeMeasurement =
  | 'none'
  | 'host_contract'
  | 'split_fvtpl'
  | 'whole_fvtpl'

export interface G10DerivativeWizardState {
  contractReviewNote: string
  variableAnswers: Partial<Record<G10DerivativeVariableKey, G10YesNo>>
  embeddedSeparateTransfer: G10YesNo
  embeddedSameCounterparty: G10YesNo
  d1NotCloselyRelated: G10YesNo
  d2StandaloneDerivative: G10YesNo
  d3NotFvtpl: G10YesNo
  canMeasureSeparately: G10YesNo
  expertQualificationIndex: string
  expertWorkIndex: string
  wizardConclusion: string
}

export function defaultG10DerivativeWizardState(): G10DerivativeWizardState {
  return {
    contractReviewNote: '',
    variableAnswers: {},
    embeddedSeparateTransfer: '',
    embeddedSameCounterparty: '',
    d1NotCloselyRelated: '',
    d2StandaloneDerivative: '',
    d3NotFvtpl: '',
    canMeasureSeparately: '',
    expertQualificationIndex: '',
    expertWorkIndex: '',
    wizardConclusion: '',
  }
}

export function parseG10DerivativeWizardState(json: string | null | undefined): G10DerivativeWizardState {
  const defaults = defaultG10DerivativeWizardState()
  if (!json) return defaults
  try {
    const raw = JSON.parse(json)
    if (!raw || typeof raw !== 'object') return defaults
    return {
      ...defaults,
      ...raw,
      variableAnswers: { ...defaults.variableAnswers, ...(raw.variableAnswers ?? {}) },
    }
  } catch {
    return defaults
  }
}

function allAnswered(values: G10YesNo[]): boolean {
  return values.every((v) => v === 'yes' || v === 'no')
}

export function evaluateG10DerivativeWizard(state: G10DerivativeWizardState): {
  hasDerivative: boolean | null
  isEmbeddedCandidate: boolean | null
  shouldSplit: boolean | null
  measurement: G10DerivativeMeasurement | null
  summary: string
} {
  const vars = G10_DERIVATIVE_VARIABLE_CHECKS.map((d) => state.variableAnswers[d.key] ?? '')
  if (!allAnswered(vars)) {
    return {
      hasDerivative: null,
      isEmbeddedCandidate: null,
      shouldSplit: null,
      measurement: null,
      summary: '请先完成步骤 B：现金流是否随特定变量变动（8 项均须选择是/否）。',
    }
  }

  const hasDerivative = vars.some((v) => v === 'yes')
  if (!hasDerivative) {
    return {
      hasDerivative: false,
      isEmbeddedCandidate: false,
      shouldSplit: false,
      measurement: 'none',
      summary: '步骤 B 全部为「否」→ 不存在衍生工具，可停止后续嵌入衍生拆分判断。',
    }
  }

  const embeddedQs = [state.embeddedSeparateTransfer, state.embeddedSameCounterparty]
  if (!allAnswered(embeddedQs)) {
    return {
      hasDerivative: true,
      isEmbeddedCandidate: null,
      shouldSplit: null,
      measurement: null,
      summary: '存在现金流随变量变动项目 → 请继续步骤 C 判断是否为嵌入衍生。',
    }
  }

  const isEmbeddedCandidate = state.embeddedSeparateTransfer === 'no' || state.embeddedSameCounterparty === 'yes'
  if (!isEmbeddedCandidate) {
    return {
      hasDerivative: true,
      isEmbeddedCandidate: false,
      shouldSplit: false,
      measurement: 'split_fvtpl',
      summary: '独立衍生工具 → 通常按 FVTPL 单独确认与计量（请与 G10-2/G10-5 勾稽）。',
    }
  }

  const dAnswers = [state.d1NotCloselyRelated, state.d2StandaloneDerivative, state.d3NotFvtpl]
  if (!allAnswered(dAnswers)) {
    return {
      hasDerivative: true,
      isEmbeddedCandidate: true,
      shouldSplit: null,
      measurement: null,
      summary: '嵌入衍生候选 → 请完成步骤 D（D1/D2/D3 须同时为「是」方可拆分）。',
    }
  }

  const shouldSplit = dAnswers.every((v) => v === 'yes')
  if (!shouldSplit) {
    return {
      hasDerivative: true,
      isEmbeddedCandidate: true,
      shouldSplit: false,
      measurement: 'host_contract',
      summary: 'D 条件未同时满足 → 不拆分，按主合同整体处理。',
    }
  }

  if (!allAnswered([state.canMeasureSeparately])) {
    return {
      hasDerivative: true,
      isEmbeddedCandidate: true,
      shouldSplit: true,
      measurement: null,
      summary: '应拆分 → 请完成步骤 E：判断能否单独可靠计量嵌入衍生公允价值。',
    }
  }

  const measurement: G10DerivativeMeasurement = state.canMeasureSeparately === 'yes'
    ? 'split_fvtpl'
    : 'whole_fvtpl'

  return {
    hasDerivative: true,
    isEmbeddedCandidate: true,
    shouldSplit: true,
    measurement,
    summary: measurement === 'split_fvtpl'
      ? '应拆分且可单独计量 → 嵌入衍生与主合同分别按公允价值计量。'
      : '应拆分但无法单独计量 → 整体按交易性（FVTPL）计量。',
  }
}

export function buildG10DerivativeWizardConclusion(state: G10DerivativeWizardState): string {
  const evalResult = evaluateG10DerivativeWizard(state)
  const lines = [
    evalResult.summary,
    state.contractReviewNote.trim() ? `合同审阅：${state.contractReviewNote.trim()}` : '',
    state.expertWorkIndex.trim() ? `专家工作索引：${state.expertWorkIndex.trim()}` : '',
  ].filter(Boolean)
  return lines.join('\n')
}

export type G10DerivativeCompliance = 'compliant' | 'non_compliant' | 'not_applicable'

export interface G10DerivativeQuestionnaireRowLike {
  checkItem: string
  checkArea: string
  sectionNo: string
  compliance: '' | G10DerivativeCompliance
  checkResult: string
  auditConclusion: string
  indexRef: string
  remark: string
}

function wizardTag(state: G10DerivativeWizardState): string {
  return state.expertWorkIndex.trim() || state.expertQualificationIndex.trim() || '向导'
}

/** 向导结论 → 78 行问卷合规勾选（仅填充空白行或带「向导」标记的行） */
export function deriveG10DerivativeRowFromWizard(
  row: G10DerivativeQuestionnaireRowLike,
  state: G10DerivativeWizardState,
): Partial<G10DerivativeQuestionnaireRowLike> | null {
  const evalResult = evaluateG10DerivativeWizard(state)
  if (evalResult.measurement === null) return null

  const item = row.checkItem
  const area = row.checkArea
  const section = row.sectionNo
  const summary = evalResult.summary
  const expertIdx = wizardTag(state)
  const hasDerivative = evalResult.hasDerivative === true
  const embedded = evalResult.isEmbeddedCandidate === true
  const split = evalResult.shouldSplit === true
  const measurement = evalResult.measurement

  const patch = (
    compliance: G10DerivativeCompliance,
    checkResult: string,
    auditConclusion: string,
    remark = '向导自动勾选',
  ): Partial<G10DerivativeQuestionnaireRowLike> => ({
    compliance,
    checkResult,
    auditConclusion,
    indexRef: expertIdx !== '向导' ? expertIdx : (row.indexRef || 'G10-8向导'),
    remark: row.remark?.includes('向导') ? row.remark : remark,
  })

  // (一) 基本信息
  if (section === '(一)') {
    if (/衍生工具定义|价值随变量变动/.test(item)) {
      return patch(
        'compliant',
        hasDerivative ? '存在衍生特征' : '无衍生特征',
        summary,
      )
    }
    if (/初始净投资|未来日期结算|固定或可确定|净额结算/.test(item)) {
      return hasDerivative
        ? patch('compliant', '符合 CAS22 五要素', summary)
        : patch('not_applicable', '无衍生', '不适用')
    }
    if (/合同条款摘要/.test(item)) {
      return state.contractReviewNote.trim()
        ? patch('compliant', state.contractReviewNote.trim(), '主合同已审阅')
        : null
    }
    if (/G10-2/.test(item)) {
      return hasDerivative
        ? patch('compliant', '应与 G10-2 衍生/负债明细勾稽', summary)
        : patch('not_applicable', '无衍生', '不适用')
    }
    if (hasDerivative && /衍生工具类型|对手方|名义金额|起止日期|结算方式|标的/.test(item)) {
      return patch('compliant', '基本信息已记录', summary)
    }
    if (!hasDerivative) {
      return patch('not_applicable', '无衍生', '向导：无衍生工具')
    }
  }

  // (二) 嵌入衍生
  if (section === '(二)') {
    if (!hasDerivative) {
      return patch('not_applicable', '无衍生', '不适用')
    }
    if (!embedded) {
      if (/主合同|交易性负债分类/.test(item)) {
        return patch('compliant', '独立衍生工具', '非嵌入衍生')
      }
      if (/嵌入衍生|拆分|紧密相关|FVTPL计量|复合工具/.test(item)) {
        return patch('not_applicable', '非嵌入衍生', summary)
      }
    }
    if (embedded && !split) {
      if (/紧密相关/.test(item)) {
        return patch('compliant', '经济特征与主合同紧密相关', 'D 条件未满足，不拆分')
      }
      if (/拆分必要性|拆分方法|拆分后计量|拆分结论/.test(item)) {
        return patch('compliant', '评估后不拆分', summary)
      }
      if (/主合同/.test(item)) {
        return patch('compliant', '按主合同整体处理', summary)
      }
    }
    if (embedded && split) {
      if (/拆分必要性|拆分方法|拆分后计量|拆分结论|法律合同/.test(item)) {
        return patch('compliant', '应拆分嵌入衍生', summary)
      }
      if (/紧密相关/.test(item) && state.d1NotCloselyRelated === 'yes') {
        return patch('compliant', '不紧密相关', 'D1 满足')
      }
      if (/FVTPL计量/.test(item) && state.d3NotFvtpl === 'yes') {
        return patch('compliant', '主合同非 FVTPL', 'D3 满足')
      }
      if (/公允价值是否可可靠计量/.test(item)) {
        return measurement === 'split_fvtpl'
          ? patch('compliant', '可单独计量', summary)
          : patch('compliant', '无法单独计量', '整体 FVTPL')
      }
    }
    if (/披露是否包含嵌入衍生/.test(item)) {
      return embedded
        ? patch('compliant', '须披露嵌入衍生', summary)
        : patch('not_applicable', '非嵌入', summary)
    }
  }

  // (三) 公允价值
  if (section === '(三)') {
    if (!hasDerivative) {
      return patch('not_applicable', '无衍生', '不适用')
    }
    if (/G10-5|G10-6/.test(item)) {
      return patch('compliant', '与公允测试/L3 调节勾稽', '见 G10-5/G10-6')
    }
    if (/估值|Level|输入值|敏感性|公允价值变动|模型校验|估值文件/.test(item)) {
      return patch('compliant', '公允价值程序已执行', summary)
    }
  }

  // (四) 套期关系 — 默认不适用（向导未识别套期）
  if (section === '(四)') {
    if (!hasDerivative) {
      return patch('not_applicable', '无衍生', '不适用')
    }
    if (/套期|CAS24|G12/.test(item)) {
      return patch('not_applicable', '向导未识别套期关系', '如有套期请手工补充')
    }
  }

  // (五) 披露
  if (section === '(五)') {
    if (!hasDerivative) {
      if (/衍生工具|嵌入衍生|套期关系|表外衍生/.test(item)) {
        return patch('not_applicable', '无衍生', '无相关披露义务')
      }
      return patch('compliant', '无衍生披露事项', summary)
    }
    if (/嵌入衍生/.test(item)) {
      return embedded
        ? patch('compliant', '须披露嵌入衍生信息', summary)
        : patch('not_applicable', '非嵌入', summary)
    }
    if (/套期关系/.test(item)) {
      return patch('not_applicable', '向导未识别套期', '手工补充')
    }
    if (/G10附注|名义金额|公允价值层次|敏感性|关联方衍生/.test(item)) {
      return patch('compliant', '披露与底稿一致', summary)
    }
  }

  if (area === '基本信息' && hasDerivative) {
    return patch('compliant', '已核实', summary)
  }

  return null
}

export function applyG10DerivativeWizardToRows<T extends G10DerivativeQuestionnaireRowLike>(
  rows: T[],
  state: G10DerivativeWizardState,
  opts?: { overwrite?: boolean },
): { rows: T[]; filled: number } {
  const overwrite = opts?.overwrite ?? false
  let filled = 0
  const next = rows.map((row) => {
    const derived = deriveG10DerivativeRowFromWizard(row, state)
    if (!derived) return row
    const isBlank = !row.compliance
    const isWizardMarked = String(row.remark ?? '').includes('向导')
    if (!overwrite && !isBlank && !isWizardMarked) return row
    filled += 1
    return { ...row, ...derived }
  })
  return { rows: next, filled }
}
