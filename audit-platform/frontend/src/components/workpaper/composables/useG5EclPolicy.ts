/** useG5EclPolicy — G5-8 信用减值损失会计政策检查
 *
 * 对齐源模板结构：
 *   一、审计目标
 *   二、审计过程
 *     (一) 具体减值政策说明（含组合划分表，名称同步附注）
 *     (二) 被审计单位历史坏账损失情况
 *     (三) 前瞻性信息的来源及其影响
 *     (四) 同行业公司的会计政策
 *   三、审计说明 / 四、审计结论
 *
 * section2 组合名称供 G5-3 / 上市·国企附注一致性校验，序列化字段保持兼容。
 */
import { ref } from 'vue'
import { ElMessageBox } from 'element-plus'

export interface PolicyCheckRow {
  id: string
  checkItem: string
  requirement: string
  companyPolicy: string
  compliance: '合规' | '不合规' | '待核实'
  explanation: string
}

/** 兼容旧版「政策变更」行（UI 已收敛，仍可读旧存档） */
export interface PolicyChangeRow {
  id: string
  item: string
  priorYear: string
  currentYear: string
  changed: '是' | '否'
  reason: string
  rationality: string
}

export interface PolicyParagraphs {
  /** (一) 具体减值政策说明正文 */
  policy: string
  /** (二) 历史坏账损失 */
  historical: string
  /** (三) 前瞻性信息 */
  forwardLooking: string
  /** (四) 同行业对比 */
  peer: string
}

export interface PolicyEvalItem {
  id: keyof PolicyParagraphs
  title: string
  guidance: string
  placeholder: string
  aiSection: string
}

export interface IndustryPolicyRef {
  company: string
  policy: string
}

export interface ConclusionTemplate {
  label: string
  value: string
}

export interface G5EclPolicyPayload {
  section1: PolicyCheckRow[]
  section2: PolicyCheckRow[]
  section3: PolicyCheckRow[]
  section4: PolicyChangeRow[]
  paragraphs?: PolicyParagraphs
  conclusion: string
}

/** 源模板审计目标 */
export const G5_8_AUDIT_OBJECTIVES = [
  '长期应收款坏账准备以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录。',
  '评价被审计单位信用减值损失会计政策及会计估计是否符合企业会计准则（CAS 22），与同行业及本期业务实质是否一致，计提政策是否得到一贯执行。',
]

/** 四段审计过程（方法论提示对齐 Excel 红/蓝字） */
export const G5_8_EVAL_ITEMS: PolicyEvalItem[] = [
  {
    id: 'policy',
    title: '（一）具体减值政策说明',
    guidance:
      '应说明被审计单位长期应收款坏账准备的信用风险组合划分依据、预期信用损失计量方法等。共同信用风险特征可参考：金融工具类型、信用风险评级、担保物类型、账龄、债务人所处行业/地理位置等。项目组应按被审计单位实际信用风险特征选择组合划分方式，并与会计政策披露及附注组合名称保持一致。',
    placeholder:
      '描述被审计单位长期应收款减值政策：组合划分依据、单项/组合计提判断、简化法或一般法（三阶段）选用、损失率确定方法…',
    aiSection: 'ecl-policy-eval-1',
  },
  {
    id: 'historical',
    title: '（二）被审计单位历史坏账损失情况',
    guidance:
      '【②应列明被审计单位历史损失率的数据来源，以及项目组核实该等数据所执行的程序；需考虑货币时间价值，评价历史数据与当前敞口的相关性。】关注：历史数据年限是否充分；是否剔除非经常性损失事件；迁徙率/核销与账面是否可验证。',
    placeholder:
      '说明历史坏账损失率数据来源、观察期、核实程序、是否考虑货币时间价值、与当前组合的相关性…',
    aiSection: 'ecl-policy-eval-2',
  },
  {
    id: 'forwardLooking',
    title: '（三）前瞻性信息的来源及其影响',
    guidance:
      '【③说明被审计单位确定预期损失率的前瞻性信息来源（包括内部模型、第三方服务机构或利用外部专家工作等），以及项目组对前瞻性信息可靠性执行的程序。】关注：宏观经济/行业指标与长期应收款信用风险的相关性；情景权重与调整幅度是否有量化依据。',
    placeholder:
      '说明前瞻性信息来源（内部模型/第三方/外部专家）、选用宏观指标、情景设置与权重、对损失率的调整幅度及审计核实程序…',
    aiSection: 'ecl-policy-eval-3',
  },
  {
    id: 'peer',
    title: '（四）同行业公司的会计政策',
    guidance:
      '对比同行业（或业务相近）上市公司长期应收款/应收款项减值准备会计政策，评价被审计单位政策合理性与一贯性。需考虑行业特点、租赁/分期销售等业务模式差异对组合划分及损失率的影响；关注是否利用政策或估计变更操纵利润。',
    placeholder:
      '列示同行业公司减值组合及损失率确定方法，对比分析与被审计单位政策的异同及是否存在重大差异…',
    aiSection: 'ecl-policy-eval-4',
  },
]

/** 默认组合（对齐源模板长期应收款常见划分示例） */
export const DEFAULT_G5_POLICY_GROUPS: Array<{ name: string; basis: string }> = [
  { name: '长期应收款组合1', basis: '融资租赁应收款' },
  { name: '长期应收款组合2', basis: '分期收款销售商品' },
  { name: '长期应收款组合3', basis: '应收质保金/保证金' },
  { name: '长期应收款组合4', basis: '应收关联公司款项' },
]

/** 源模板 / 同业披露示例（可一键套用到第（四）节） */
export const G5_8_INDUSTRY_REFS: IndustryPolicyRef[] = [
  {
    company: '中国中铁',
    policy:
      '依据信用风险特征将应收款项划分为若干组合。组合1：应收账款和应收质保金；对组合采用账龄分析法，参考历史信用损失经验，结合当前状况及对未来经济状况的预测，通过违约风险敞口和整个存续期预期信用损失率计算预期信用损失。',
  },
  {
    company: '上海电气',
    policy:
      '对存在客观减值证据的长期应收款及其他应收款单独进行减值测试并计提单项减值准备。其余按信用风险特征组合：组合1 押金和保证金；组合2 员工备用金；组合3 其他。参考历史信用损失经验，结合当前状况及前瞻性信息计算预期信用损失。',
  },
  {
    company: '北辰实业',
    policy:
      '组合1 应收押金、保证金及备用金；组合2 应收关联公司款项；组合3 应收少数股东款项；组合4 应收代垫款项；组合5 应收其他款项。通过违约风险敞口和未来12个月内或整个存续期预期信用损失率计算预期信用损失。',
  },
  {
    company: '美凯龙',
    policy:
      '基于单项和组合评估金融工具预期信用损失。考虑不同客户信用风险特征，以账龄组合为基础评估应收账款、其他应收款、合同资产和长期应收款等金融工具的预期信用损失。确定组合的依据包括：建筑施工与设计、项目前期品牌咨询委托管理费服务等。',
  },
]

export const G5_8_CONCLUSION_TEMPLATES: ConclusionTemplate[] = [
  {
    label: 'A-与同业一致且一贯执行',
    value:
      '被审计单位预期信用损失计提相关的会计政策和会计估计与企业会计准则及同行业企业的计提标准大体一致，反映了被审计单位经营业务的实际情况，与同行业公司相比不存在显著差异，且计提准备政策得到一贯执行。',
  },
  {
    label: 'B-基本合理但需关注',
    value:
      '经检查，被审计单位长期应收款信用减值会计政策整体符合企业会计准则规定，但存在以下需关注事项：（1）_____。上述事项对减值准备计提金额的影响约____万元，经与管理层沟通后认为该差异在可接受范围内/已建议管理层调整。',
  },
  {
    label: 'C-政策需调整',
    value:
      '经检查，被审计单位长期应收款信用减值会计政策存在以下不当之处：（1）_____。上述事项导致减值准备计提不足/多计____万元，已提请管理层进行调整（详见审计调整分录 G5-4）。',
  },
]

function emptyParagraphs(): PolicyParagraphs {
  return { policy: '', historical: '', forwardLooking: '', peer: '' }
}

function defaultSection2(): PolicyCheckRow[] {
  return DEFAULT_G5_POLICY_GROUPS.map((g, i) => ({
    id: `s2-${i + 1}`,
    checkItem: g.name,
    requirement: g.basis,
    companyPolicy: g.name,
    compliance: '待核实' as const,
    explanation: '',
  }))
}

function defaultSection1(): PolicyCheckRow[] {
  return [
    {
      id: 's1-1',
      checkItem: '预期信用损失模型',
      requirement: '按 CAS 22 采用一般法（三阶段）或适用简化法，判断标准可验证',
      companyPolicy: '',
      compliance: '待核实',
      explanation: '',
    },
    {
      id: 's1-2',
      checkItem: '损失率确定方法',
      requirement: '历史损失经验 + 当前状况 + 前瞻性信息，依据充分',
      companyPolicy: '',
      compliance: '待核实',
      explanation: '',
    },
    {
      id: 's1-3',
      checkItem: '组合与披露一致性',
      requirement: '组合名称与会计政策披露、G5-3/附注一致',
      companyPolicy: '',
      compliance: '待核实',
      explanation: '',
    },
  ]
}

export function useG5EclPolicy() {
  const section1 = ref<PolicyCheckRow[]>(defaultSection1())
  /** 组合划分：checkItem=组合名称，供附注披露一致性校验 */
  const section2 = ref<PolicyCheckRow[]>(defaultSection2())
  /** 兼容旧存档 */
  const section3 = ref<PolicyCheckRow[]>([])
  const section4 = ref<PolicyChangeRow[]>([])
  const paragraphs = ref<PolicyParagraphs>(emptyParagraphs())
  const conclusion = ref('')

  async function addSection2Row() {
    const { value } = await ElMessageBox.prompt('请输入组合名称（须与附注/会计政策披露一致）', '新增组合', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (!value?.trim()) return
    section2.value.push({
      id: crypto.randomUUID(),
      checkItem: value.trim(),
      requirement: '与附注披露组合名称一致',
      companyPolicy: value.trim(),
      compliance: '待核实',
      explanation: '',
    })
  }

  function removeSection2Row(id: string) {
    if (section2.value.length <= 1) return
    section2.value = section2.value.filter((r) => r.id !== id)
  }

  async function addSection3Row() {
    const { value } = await ElMessageBox.prompt('请输入检查项', '新增检查项', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (!value?.trim()) return
    section3.value.push({
      id: crypto.randomUUID(),
      checkItem: value.trim(),
      requirement: '',
      companyPolicy: '',
      compliance: '待核实',
      explanation: '',
    })
  }

  function applyIndustryRef(ref: IndustryPolicyRef) {
    const current = paragraphs.value.peer || ''
    const text = `【${ref.company}】\n${ref.policy}`
    paragraphs.value = {
      ...paragraphs.value,
      peer: current ? `${current}\n\n${text}` : text,
    }
  }

  function applyConclusionTemplate(templateValue: string) {
    conclusion.value = templateValue
  }

  function setParagraph(key: keyof PolicyParagraphs, value: string) {
    paragraphs.value = { ...paragraphs.value, [key]: value }
  }

  function serialize(): string {
    const payload: G5EclPolicyPayload = {
      section1: section1.value,
      section2: section2.value,
      section3: section3.value,
      section4: section4.value,
      paragraphs: paragraphs.value,
      conclusion: conclusion.value,
    }
    return JSON.stringify(payload)
  }

  function loadFromRaw(raw: string | null | undefined) {
    if (!raw?.trim()) return
    try {
      const parsed = JSON.parse(raw) as Partial<G5EclPolicyPayload>
      if (Array.isArray(parsed.section1) && parsed.section1.length) section1.value = parsed.section1
      if (Array.isArray(parsed.section2) && parsed.section2.length) section2.value = parsed.section2
      if (Array.isArray(parsed.section3)) section3.value = parsed.section3
      if (Array.isArray(parsed.section4)) section4.value = parsed.section4
      if (parsed.paragraphs && typeof parsed.paragraphs === 'object') {
        paragraphs.value = { ...emptyParagraphs(), ...parsed.paragraphs }
      }
      if (typeof parsed.conclusion === 'string') conclusion.value = parsed.conclusion
    } catch {
      /* ignore */
    }
  }

  /** 附注披露用的组合名称清单 */
  function groupNames(): string[] {
    return section2.value
      .map((r) => String(r.companyPolicy || r.checkItem || '').trim())
      .filter(Boolean)
  }

  return {
    section1,
    section2,
    section3,
    section4,
    paragraphs,
    conclusion,
    evalItems: G5_8_EVAL_ITEMS,
    industryRefs: G5_8_INDUSTRY_REFS,
    conclusionTemplates: G5_8_CONCLUSION_TEMPLATES,
    auditObjectives: G5_8_AUDIT_OBJECTIVES,
    addSection2Row,
    removeSection2Row,
    addSection3Row,
    applyIndustryRef,
    applyConclusionTemplate,
    setParagraph,
    serialize,
    loadFromRaw,
    groupNames,
  }
}
