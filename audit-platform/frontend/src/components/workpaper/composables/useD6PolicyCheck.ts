/**
 * useD6PolicyCheck — D6-7 合同资产减值准备会计政策检查（对齐源模板4段式）
 *
 * 源模板结构：
 *   一、审计目标（2条认定）
 *   二、审计过程
 *     (一) 合同资产减值计提会计政策
 *     (二) 被审计单位历史坏账损失情况
 *     (三) 前瞻性信息的来源及其影响
 *     (四) 同行业公司的会计政策
 *   三、审计说明
 *   四、审计结论
 *
 * Item IDs:
 *   D6-7-eval-{1-4}  — 4项审计评价 textarea
 *   D6-7-objective   — 审计目标（自定义补充）
 *   D6-7-note-explanation / D6-7-note-conclusion
 */
import { ref, watch, type Ref } from 'vue'
import type { ChecklistResponse } from './useD6FormData'

export interface PolicyEvalItem {
  id: number
  itemId: string
  aiSection: string
  title: string
  /** 源模板红字方法论提示（琥珀块内容） */
  guidance: string
}

export const POLICY_EVAL_ITEMS: PolicyEvalItem[] = [
  {
    id: 1,
    itemId: 'D6-7-eval-1',
    aiSection: 'policy-eval-1',
    title: '(一) 合同资产减值准备计提会计政策',
    guidance: '应说明被审计单位合同资产坏账准备信用风险组合划分依据、预期信用损失计量方法等。关注：组合划分是否合理反映不同信用风险特征（如按业务类型/客户信用等级/地域）；ECL模型选用（简化法/一般法）是否符合CAS22第63条要求。',
  },
  {
    id: 2,
    itemId: 'D6-7-eval-2',
    aiSection: 'policy-eval-2',
    title: '(二) 被审计单位历史坏账损失情况',
    guidance: '应说明被审计单位合同资产历史损失率的数据来源，以及项目组核实该等数据所执行的程序。需考虑货币的时间价值。关注：历史数据年限是否充分（一般需三年以上）；是否剔除了非经常性损失事件；迁徙率与实际核销是否对应可验证。',
  },
  {
    id: 3,
    itemId: 'D6-7-eval-3',
    aiSection: 'policy-eval-3',
    title: '(三) 前瞻性信息的来源及其影响',
    guidance: '应说明被审计单位确定预期损失率的前瞻性信息来源（包括内部模型、第三方服务机构或利用外部专家工作等），以及项目组对前瞻性信息可靠性所执行的程序。关注：宏观经济指标选取（GDP增速/行业景气度/信用利差等）与合同资产信用风险的相关性；调整幅度是否有合理量化依据。',
  },
  {
    id: 4,
    itemId: 'D6-7-eval-4',
    aiSection: 'policy-eval-4',
    title: '(四) 同行业公司的会计政策',
    guidance: '对比同行业上市公司合同资产减值准备会计政策，评价被审计单位政策的合理性与一贯性。需考虑行业特点、业务模式差异对组合划分及损失率的影响。',
  },
]

/** 上市公司参考政策（源模板第二页蓝字内容） */
export interface IndustryPolicyRef {
  company: string
  policy: string
}

export const INDUSTRY_POLICY_REFS: IndustryPolicyRef[] = [
  {
    company: '中国中铁',
    policy: '合同资产组合1 基础设施建设项目\n合同资产组合2 土地一级开发项目\n合同资产组合3 处于建设期的金融资产模式的PPP项目\n合同资产组合4 未到期的质保金\n对不同组合的应收账款和合同资产，本集团参考历史信用损失经验，结合当前状况以及对未来经济状况的预测，编制应收账款逾期天数与整个存续期预期信用损失率对照表，计算预期信用损失。',
  },
  {
    company: '中国中冶',
    policy: '在预期信用损失法下，本集团对由新收入准则规范的交易而形成的未包含重大融资成分或不考虑不超过一年的合同中的融资成分的合同资产与应收账款按照相当于整个存续期内预期信用损失的金额计量信用损失准备。\n信用损失准备的确认需要运用判断和估计。如果实际结果与现有估计存在差异，该差异将会影响估计改变期间的利润、合同资产和应收账款面值。\n确定组合的依据如下：\n工程承包服务相关的合同资产\n工程质保金相关的合同资产',
  },
  {
    company: '中煤能源',
    policy: '本集团依据信用风险特征将应收票据及应收账款和合同资产划分为若干组合，在组合基础上计算预期信用损失，确定组合的依据如下：\n·应收账款\\合同资产组合A 信用优良。在未来的信用风险极低，自身抗风险能力很强，不确定性因素对其经营与发展的影响很小。\n·应收账款\\合同资产组合B，信用较好。在未来的信用风险较低，自身有一定抗风险能力，但是可能存在一些影响其未来经营与发展的不确定性因素。\n·应收账款\\合同资产组合C，信用一般。在未来存在较大的不确定性因素，自身抗风险能力不够稳定。\n本集团始终按照相当于整个存续期内预期信用损失的金额计量损失准备。',
  },
  {
    company: '长飞光纤',
    policy: '群体1: 集团外关联方；群体2: 中国电信网络运营商及其他信用记录良好的企业；群体3: 除群体1、2以外的其他客户。\n本集团始终按照相当于整个存续期内预期信用损失的金额计量应收账款的减值准备，并以逾期天数与违约损失率对照表为基础计算其预期信用损失准备。根据本集团的历史经验，不同组合客户群体发生损失的情况存在差异，因此本集团根据历史经验区分不同客户群体根据逾期信息计算减值准备。',
  },
  {
    company: '中国中车',
    policy: '本集团除对单项金额重大或已发生信用减值的金融资产、合同资产、租赁应收款、贷款承诺和财务担保合同在单项资产/合同基础上确定其信用损失外，在组合基础上采用减值矩阵确定相关金融工具的信用损失。本集团采用的共同信用风险特征为依据，将金融工具分为不同组别。本集团采用的共同信用风险特征包括：金融工具类型、信用风险评级、担保物类型、剩余合同期限、债务人所处行业、债务人所处地理位置、担保品相对于金融资产的价值信息等。\n确定组合的依据如下：\n销售商品\n建造合同',
  },
  {
    company: '美凯龙',
    policy: '本集团基于单项和组合评估金融工具的预期信用损失。本集团考虑不同客户的信用风险特征，以账龄组合为基础评估应收账款、其他应收款、合同资产和长期应收款等金融工具的预期信用损失。\n确定组合的依据如下：\n建筑施工与设计\n项目前期品牌咨询委托管理费服务',
  },
]

/** D6-7结论模板 */
export const D6_7_CONCLUSION_TEMPLATES = [
  {
    label: 'A-政策合理',
    value: '经检查，被审计单位合同资产减值准备的会计政策与会计估计符合企业会计准则的规定，与同行业公司政策相比属于合理范围，预期信用损失模型的参数选取及前瞻性调整具有充分合理依据，本年度会计政策保持一贯性，未发现重大不当之处。',
  },
  {
    label: 'B-政策基本合理但需关注',
    value: '经检查，被审计单位合同资产减值准备的会计政策整体符合企业会计准则的规定，但存在以下需关注事项：（1）_____。上述事项对减值准备计提金额的影响为____万元，经与管理层沟通后认为该差异在可接受范围内/已建议管理层调整。',
  },
  {
    label: 'C-政策需调整',
    value: '经检查，被审计单位合同资产减值准备的会计政策存在以下不当之处：（1）_____。上述事项导致减值准备计提不足/多计____万元，已提请管理层进行调整（详见审计调整分录D6-4）。',
  },
]

export interface UseD6PolicyCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}

export function useD6PolicyCheck(options: UseD6PolicyCheckOptions) {
  const { allResponses, debouncedSave } = options

  const evaluations = ref<Record<number, string>>({ 1: '', 2: '', 3: '', 4: '' })
  const auditObjective = ref('')
  const auditNotes = ref({ explanation: '', conclusion: '' })

  for (const item of POLICY_EVAL_ITEMS) {
    watch(
      () => allResponses.value.get(item.itemId)?.remark,
      (v) => { evaluations.value[item.id] = v || '' },
      { immediate: true },
    )
    watch(
      () => evaluations.value[item.id],
      (v) => debouncedSave(item.itemId, { remark: v }),
    )
  }

  watch(
    () => allResponses.value.get('D6-7-objective')?.remark,
    (v) => { auditObjective.value = v || '' },
    { immediate: true },
  )
  watch(
    () => auditObjective.value,
    (v) => debouncedSave('D6-7-objective', { remark: v }),
  )

  watch(
    () => allResponses.value.get('D6-7-note-explanation')?.remark,
    (v) => { auditNotes.value.explanation = v || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get('D6-7-note-conclusion')?.remark,
    (v) => { auditNotes.value.conclusion = v || '' },
    { immediate: true },
  )
  watch(
    () => auditNotes.value.explanation,
    (v) => debouncedSave('D6-7-note-explanation', { remark: v }),
  )
  watch(
    () => auditNotes.value.conclusion,
    (v) => debouncedSave('D6-7-note-conclusion', { remark: v }),
  )

  function updateEvaluation(id: number, value: string): void {
    evaluations.value = { ...evaluations.value, [id]: value }
  }

  /** 从结论模板快速填入 */
  function applyConclusion(templateValue: string): void {
    auditNotes.value = { ...auditNotes.value, conclusion: templateValue }
  }

  /** 从参考政策一键套用到第(四)节 */
  function applyIndustryRef(ref: IndustryPolicyRef): void {
    const current = evaluations.value[4] || ''
    const text = `${ref.company}：\n${ref.policy}`
    evaluations.value = { ...evaluations.value, 4: current ? `${current}\n\n${text}` : text }
  }

  return {
    evaluations,
    updateEvaluation,
    auditObjective,
    auditNotes,
    policyEvalItems: POLICY_EVAL_ITEMS,
    industryPolicyRefs: INDUSTRY_POLICY_REFS,
    conclusionTemplates: D6_7_CONCLUSION_TEMPLATES,
    applyConclusion,
    applyIndustryRef,
  }
}

export default useD6PolicyCheck
