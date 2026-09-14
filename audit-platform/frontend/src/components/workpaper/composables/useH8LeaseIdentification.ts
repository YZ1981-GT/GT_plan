/**
 * useH8LeaseIdentification — H8-4 租赁的识别（对齐致同 Excel 段落型 90 行）
 *
 * CAS21 第4-13条 / 第32条：
 *   §1 租赁识别：已识别资产 ∩ 主导使用权 ∩ 几乎全部经济利益
 *   §2 租赁分拆：单独获利能力 ∩ 非高度依赖（同时满足）
 *   §3 租赁合并：三条件任一 → 合并为一份合同
 *   §4 短期租赁：≤12月（含续租判断）∩ 无购买选择权
 *   §5 低价值：全新价值较低（如≤4万）∩ 无/不预期转租
 *
 * Excel 关键公式：
 *   F11 = IF(AND(F12="是",F13="否"),"是","否")  // 无实质替换权才构成已识别资产
 *   C21 = IF(AND(F11,F15,F20),"合同为租赁或者包含租赁","不包含租赁")
 *   C27 = IF(AND(F25,F26),"构成合同中的一项单独租赁","无须分拆")
 *   C36 = IF(OR(F33,F34,F35),"应当合并为一份合同进行会计处理","单项租赁")
 *   F41 = IF(AND(F42,F43),"是","否")
 *   C45 = IF(AND(F41,F44),"属于短期租赁","不属于短期租赁")
 *   C54 = IF(AND(F52,F53),"属于低价值资产租赁","不属于低价值资产租赁")
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/ Task 3.4 | Req 4.1, 4.4, 4.5
 */
import { ref, computed, watch, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type YesNo = '是' | '否' | ''
export type ApplicableFlag = '是' | '否' | ''

/** 单份合同的租赁识别记录（对齐 Excel H8-4） */
export interface H8IdentificationRecord {
  recordId: string
  contractNo: string
  /** 合同标的/资产简述 */
  assetDesc: string

  // ── §1 租赁的识别 ──
  /** ①物理可区分（F12） */
  physicallyDistinct: YesNo
  physicallyDistinctInfo: string
  physicallyDistinctIndex: string
  /** ②供应方实质性替换权（F13）— 「是」表示有替换权→削弱已识别资产 */
  supplierSubstantiveSubstitution: YesNo
  substitutionInfo: string
  substitutionIndex: string
  /** 替换权两条件是否同时符合（F14，佐证） */
  substitutionBothConditions: YesNo

  /** （2）①有权主导使用目的和方式（F16） */
  canDirectPurposeManner: YesNo
  directPurposeInfo: string
  /** （2）②使用目的/方式预先确定（F17） */
  usePredetermined: YesNo
  predeterminedInfo: string
  /** 预先确定且：有权运营该资产（F18） */
  canOperateAsset: YesNo
  operateInfo: string
  /** 预先确定且：客户设计了资产（F19） */
  designedAsset: YesNo
  designInfo: string
  directUseIndex: string

  /** （3）几乎全部经济利益（F20） */
  economicBenefits: YesNo
  economicBenefitsInfo: string
  economicBenefitsIndex: string

  /** 手填覆盖「主导使用权」总判断（空则用公式） */
  directUseOverride: YesNo

  // ── §2 租赁的分拆 ──
  splitApplicable: ApplicableFlag
  canBenefitSeparately: YesNo
  canBenefitSeparatelyInfo: string
  canBenefitSeparatelyIndex: string
  notHighlyDependent: YesNo
  notHighlyDependentInfo: string
  notHighlyDependentIndex: string
  /** 是否选择不拆分非租赁部分（实务简化） */
  electNotSplitNonLease: YesNo

  // ── §3 租赁的合并 ──
  combineApplicable: ApplicableFlag
  packageCommercialPurpose: YesNo
  packageInfo: string
  packageIndex: string
  considerationDepends: YesNo
  considerationInfo: string
  considerationIndex: string
  combinedSingleLease: YesNo
  combinedInfo: string
  combinedIndex: string

  // ── §4 短期租赁 ──
  shortTermApplicable: ApplicableFlag
  /** 考虑续租选择权后 ≤12月（F42） */
  termWithRenewalWithin12: YesNo
  termWithRenewalInfo: string
  /** 续签合同后 ≤12月（F43） */
  renewContractWithin12: YesNo
  renewContractInfo: string
  shortTermIndex: string
  /** 不包含购买选择权（F44）— 「是」=无购买选择权 */
  noPurchaseOption: YesNo
  noPurchaseOptionInfo: string

  // ── §5 低价值资产租赁 ──
  lowValueApplicable: ApplicableFlag
  lowValueWhenNew: YesNo
  lowValueInfo: string
  lowValueIndex: string
  /** 全新价值（元），可选填以辅助判断 */
  newAssetValue: number
  noSubleaseExpected: YesNo
  noSubleaseInfo: string
  noSubleaseIndex: string

  explanation: string
  /** 本项总体结论：是=含租赁 / 否=不含 / 不适用 */
  conclusion: '是' | '否' | '不适用' | ''
}

// ─── Tip catalog（Excel 蓝字 H/I 列 → 弹窗）────────────────────────────────

export interface H8LeaseIdTip {
  id: string
  title: string
  paragraphs: string[]
  jumps?: Array<{ label: string; sheet: string }>
}

export const H8_LEASE_ID_TIPS: H8LeaseIdTip[] = [
  {
    id: 'overview',
    title: '租赁识别总览（CAS21）',
    paragraphs: [
      '在合同开始日，企业应当评估合同是否为租赁或者包含租赁。',
      '租赁：在一定期间内，出租人将资产的使用权让与承租人以获取对价的合同。',
      '核心：控制已识别资产使用的权利 = ①存在已识别资产 ＋ ②有权主导使用 ＋ ③有权获得几乎全部经济利益。',
      '除非合同条款或条件发生变化，无需重新评估合同是否为租赁或是否包含租赁。',
      '第三十二条：短期租赁与低价值资产租赁，承租人可选择不确认使用权资产和租赁负债，将付款额按直线法或其他系统合理方法计入成本/损益。',
    ],
    jumps: [
      { label: 'H8-5 租赁期', sheet: 'H8-5' },
      { label: 'H8-6 计量', sheet: 'H8-6' },
      { label: 'H8-13 简化处理', sheet: 'H8-13' },
    ],
  },
  {
    id: 'flowchart',
    title: '识别决策树（对齐模板流程图）',
    paragraphs: [
      '① 是否存在已识别资产？\n　→ 否：合同不是租赁。\n　→ 是：进入②。',
      '② 客户是否有权获得使用期间内几乎全部经济利益？\n　→ 否：不是租赁。\n　→ 是：进入③。',
      '③ 在整个使用期间，主导资产使用目的和方式的是客户、供应方，还是两者皆非（因预先确定）？\n　→ 供应方主导：不是租赁。\n　→ 客户主导：合同为租赁或包含租赁。\n　→ 两者皆非（预先确定）：再判断——客户是否有权运营资产（供应方无权改变指令）？或客户是否设计了资产并预先确定使用目的/方式？\n　　任一对「是」→ 是租赁；均「否」→ 不是租赁。',
      '本表 §1 将上述决策树展开为可勾稽填写项；结论单元格自动按三要素 AND 判定。',
    ],
  },
  {
    id: 's1-asset',
    title: '§1（1）已识别资产',
    paragraphs: [
      '通常由合同明确指定，也可以在资产可供客户使用时隐性指定。',
      '①物理可区分：若资产部分产能在物理上可区分（如建筑物的一层），该部分产能属于已识别资产。产能份额若仅按数量占比、物理上不可区分，通常不构成已识别资产（除非客户实质上获得几乎全部产能）。',
      '②供应方实质性替换权：若供应方在整个使用期间拥有实质性替换权，则该资产不属于已识别资产。',
      'Excel F11 公式：物理可区分=「是」且实质性替换权=「否」→ 已识别资产「是」。（有实质替换权会否定「已识别资产」。）',
      '替换权具有实质性须同时：①拥有在整个使用期间替换的实际能力；②行使替换权将获得经济利益。',
      '反例：仅特定日期/事件后才可替换；资产在客户所在地导致替换成本过高；仅为修理/维护/技术升级而替换——通常不具有实质性。',
    ],
  },
  {
    id: 's1-direct',
    title: '§1（2）主导已识别资产的使用',
    paragraphs: [
      '保护性权利（保护供应方对资产/人员的权益、或确保不违法）本身不足以否定客户主导使用权。',
      '「一定期间」也可表述为已识别资产的使用量（如设备产出量）。客户仅在部分合同期控制使用的，合同包含该部分期间的租赁。',
      '路径①：客户有权在整个使用期间、在合同界定范围内改变资产的使用目的和使用方式。',
      '判断时应关注与改变使用目的/方式最为相关的决策权（影响使用所产生经济利益的决策）。',
      '路径②：使用目的/方式在使用期间前已预先确定，并且满足下列之一：\n　• 客户有权自行或主导他人按确定方式运营该资产；或\n　• 客户设计了已识别资产（或特定方面）并在设计时预先确定了整个使用期间的使用目的和方式。',
      '若客户仅能在使用前指定产出、无其他使用相关决策权，则其权利与普通购货客户并无不同（通常不构成主导使用）。',
      '本表自动：路径①为「是」，或（预先确定为「是」且（运营或设计为「是」））→ 主导使用权「是」。',
    ],
  },
  {
    id: 's1-benefits',
    title: '§1（3）几乎全部经济利益',
    paragraphs: [
      '应在约定的客户权利范围内考虑所产生的经济利益；应有权获得整个使用期间使用该资产所产生的几乎全部经济利益（例如整个期间独家使用）。',
      '经济利益包括主要产出和副产品（含潜在现金流量），以及与第三方交易实现的其他经济利益。',
      '若合同规定客户须向供应方或其他方支付因使用资产产生的部分现金流量作为对价，该现金流量仍视为客户获得的经济利益的一部分。',
    ],
  },
  {
    id: 's1-conclusion',
    title: '§1 结论公式',
    paragraphs: [
      'Excel C21：已识别资产=「是」且主导使用权=「是」且几乎全部经济利益=「是」→「合同为租赁或者包含租赁」；否则「不包含租赁」。',
      '若结论为「不包含租赁」：§2分拆/§3合并通常「无须分析」；§4/§5简化处理亦不适用（因无租赁）。请将证据索引填入各行「索引」列。',
      '含租赁时：继续 H8-5 确定租赁期 → H8-6 计量；若拟简化处理，完成 §4/§5 后跳转 H8-13。',
    ],
    jumps: [
      { label: 'H8-5 租赁期', sheet: 'H8-5' },
      { label: 'H8-6 计量', sheet: 'H8-6' },
      { label: 'H8-13 简化处理', sheet: 'H8-13' },
    ],
  },
  {
    id: 's2-split',
    title: '§2 租赁的分拆',
    paragraphs: [
      '同时满足方可构成合同中的一项单独租赁：',
      '（1）承租人可从单独使用该资产或将其与易于获得的其他资源一起使用中获利。易于获得的资源：出租人/其他供应方单独销售或出租的商品服务，或承租人已从出租人或其他交易中获得的资源。',
      '（2）该资产与合同中其他资产不存在高度依赖或高度关联。若租入决定不会对使用合同中其他资产的权利产生重大影响，则通常不存在高度依赖/关联。',
      'Excel C27：两条件均为「是」→「构成合同中的一项单独租赁」；否则「无须分拆」。',
      '注1：合同含多项单独租赁的，应分拆并分别会计处理。',
      '注2：为简化处理，承租人可按租赁资产类别选择是否分拆租赁与非租赁部分。',
      '分拆时：按各项租赁部分单独价格及非租赁部分单独价格之和的相对比例分摊合同对价。',
    ],
  },
  {
    id: 's3-combine',
    title: '§3 租赁的合并',
    paragraphs: [
      '两份或多份包含租赁的合同，同时或近乎同时订立时，满足下列任一条件应合并为一份合同会计处理：',
      '（1）基于总体商业目的订立并构成一揽子交易，不作为整体则无法理解总体商业目的（独立处理可能无法忠实反映整个交易）。',
      '（2）某份合同对价取决于其他合同的定价或履行情况。',
      '（3）让渡的资产使用权合起来构成一项单独租赁。',
      'Excel C36：任一条件「是」→「应当合并为一份合同进行会计处理」；否则「单项租赁」。',
      '注：合并后仍需区分该份合同中的租赁部分与非租赁部分。',
    ],
  },
  {
    id: 's4-short',
    title: '§4 短期租赁',
    paragraphs: [
      '短期租赁：在租赁期开始日，租赁期不超过12个月的租赁。包含购买选择权的租赁不属于短期租赁。',
      'Excel F41：考虑续租选择权后≤12月 且 续签合同后≤12月 → 租赁期条件「是」。',
      'Excel C45：租赁期条件「是」且不包含购买选择权「是」→「属于短期租赁」。',
      '注1：短期租赁可按资产类别选择第三十二条简化处理（如房屋建筑物、机器设备、车辆等）。',
      '注2：已按简化处理的短期租赁发生变更或其他原因导致租赁期变化的，应视为一项新租赁，重新判断是否可简化。',
      '选择简化处理后，应在 H8-13 登记费用确认，并与损益科目勾稽。',
    ],
    jumps: [
      { label: 'H8-5 核验租赁期', sheet: 'H8-5' },
      { label: 'H8-13 简化处理检查', sheet: 'H8-13' },
    ],
  },
  {
    id: 's5-low',
    title: '§5 低价值资产租赁',
    paragraphs: [
      '应基于租赁资产全新状态下的价值评估，不考虑资产已被使用的年限。',
      '低价值标准应为绝对金额（实务参考如低于人民币 40,000 元），不受承租人规模、性质影响，也不考虑该资产对承租人或交易的重要性。',
      '若已经或预期转租赁，则不能按低价值资产租赁简化处理。',
      'Excel C54：全新价值较低「是」且未/不预期转租「是」→「属于低价值资产租赁」。',
      '承租人可按每项租赁的具体情况作出第三十二条选择；选择后跳转 H8-13 登记。',
    ],
    jumps: [{ label: 'H8-13 简化处理检查', sheet: 'H8-13' }],
  },
]

// ─── Pure formula helpers（对齐 Excel）──────────────────────────────────────

/** F11：物理可区分=是 且 实质替换权=否 → 已识别资产=是 */
export function calcIdentifiedAsset(physicallyDistinct: YesNo, supplierSubstantiveSubstitution: YesNo): YesNo {
  if (!physicallyDistinct || !supplierSubstantiveSubstitution) return ''
  return physicallyDistinct === '是' && supplierSubstantiveSubstitution === '否' ? '是' : '否'
}

/**
 * F15 增强自动：主导使用权
 * 路径① F16=是；或 路径② F17=是 且 (F18=是 或 F19=是)
 */
export function calcDirectUseRight(
  canDirectPurposeManner: YesNo,
  usePredetermined: YesNo,
  canOperateAsset: YesNo,
  designedAsset: YesNo,
): YesNo {
  if (canDirectPurposeManner === '是') return '是'
  if (usePredetermined === '是' && (canOperateAsset === '是' || designedAsset === '是')) return '是'
  // 已填齐且均未命中 → 否
  const touched =
    canDirectPurposeManner !== ''
    || usePredetermined !== ''
    || canOperateAsset !== ''
    || designedAsset !== ''
  if (!touched) return ''
  // 路径①明确否，且路径②未成立
  if (canDirectPurposeManner === '否' || canDirectPurposeManner === '') {
    if (usePredetermined === '否') return '否'
    if (usePredetermined === '是' && canOperateAsset === '否' && designedAsset === '否') return '否'
    if (
      canDirectPurposeManner === '否'
      && usePredetermined === ''
      && canOperateAsset === ''
      && designedAsset === ''
    ) {
      return '否'
    }
  }
  return ''
}

export function resolveDirectUse(r: Pick<
  H8IdentificationRecord,
  'directUseOverride' | 'canDirectPurposeManner' | 'usePredetermined' | 'canOperateAsset' | 'designedAsset'
>): YesNo {
  if (r.directUseOverride === '是' || r.directUseOverride === '否') return r.directUseOverride
  return calcDirectUseRight(
    r.canDirectPurposeManner,
    r.usePredetermined,
    r.canOperateAsset,
    r.designedAsset,
  )
}

/** C21 */
export function calcLeaseIdentificationConclusion(
  identifiedAsset: YesNo,
  directUse: YesNo,
  economicBenefits: YesNo,
): string {
  if (!identifiedAsset || !directUse || !economicBenefits) {
    return '待填写三要素后自动判定'
  }
  if (identifiedAsset === '是' && directUse === '是' && economicBenefits === '是') {
    return '合同为租赁或者包含租赁'
  }
  return '不包含租赁'
}

/** C27 */
export function calcSplitConclusion(canBenefitSeparately: YesNo, notHighlyDependent: YesNo): string {
  if (!canBenefitSeparately || !notHighlyDependent) return '待填写分拆条件后自动判定'
  if (canBenefitSeparately === '是' && notHighlyDependent === '是') {
    return '构成合同中的一项单独租赁'
  }
  return '无须分拆'
}

/** C36 */
export function calcCombineConclusion(
  packageCommercialPurpose: YesNo,
  considerationDepends: YesNo,
  combinedSingleLease: YesNo,
): string {
  if (!packageCommercialPurpose && !considerationDepends && !combinedSingleLease) {
    return '待填写合并条件后自动判定'
  }
  if (
    packageCommercialPurpose === '是'
    || considerationDepends === '是'
    || combinedSingleLease === '是'
  ) {
    return '应当合并为一份合同进行会计处理'
  }
  if (
    packageCommercialPurpose === '否'
    && considerationDepends === '否'
    && combinedSingleLease === '否'
  ) {
    return '单项租赁'
  }
  return '待填写合并条件后自动判定'
}

/** F41 */
export function calcTermWithin12(termWithRenewalWithin12: YesNo, renewContractWithin12: YesNo): YesNo {
  if (!termWithRenewalWithin12 || !renewContractWithin12) return ''
  return termWithRenewalWithin12 === '是' && renewContractWithin12 === '是' ? '是' : '否'
}

/** C45 */
export function calcShortTermConclusion(termWithin12: YesNo, noPurchaseOption: YesNo): string {
  if (!termWithin12 || !noPurchaseOption) return '待填写短期租赁条件后自动判定'
  if (termWithin12 === '是' && noPurchaseOption === '是') return '属于短期租赁'
  return '不属于短期租赁'
}

/** C54 */
export function calcLowValueConclusion(lowValueWhenNew: YesNo, noSubleaseExpected: YesNo): string {
  if (!lowValueWhenNew || !noSubleaseExpected) return '待填写低价值条件后自动判定'
  if (lowValueWhenNew === '是' && noSubleaseExpected === '是') return '属于低价值资产租赁'
  return '不属于低价值资产租赁'
}

export function isContainsLease(conclusion: string): boolean {
  return conclusion === '合同为租赁或者包含租赁'
}

export const LOW_VALUE_THRESHOLD = 40_000

// ─── Constants / factory ─────────────────────────────────────────────────────

const RECORDS_KEY = 'H8-4-records'
const H82_ROWS_KEY = 'H8-2-rows'
const H85_RECORDS_KEY = 'H8-5-records'
const H813_ROWS_KEY = 'H8-13-rows'

/** H8-2 合同摘要（带入用） */
export interface H82ContractSeed {
  contractNo: string
  assetName: string
  lessor: string
  startDate: string
  endDate: string
}

/** 否定/关键判断时建议打开的提示 id（弹窗联动） */
export function suggestTipForField(field: string, value: string): string | null {
  if (value !== '是' && value !== '否') return null
  if (field === 'physicallyDistinct' && value === '否') return 's1-asset'
  if (field === 'supplierSubstantiveSubstitution' && value === '是') return 's1-asset'
  if (field === 'substitutionBothConditions' && value === '是') return 's1-asset'
  if (field === 'canDirectPurposeManner' && value === '否') return 's1-direct'
  if (field === 'economicBenefits' && value === '否') return 's1-benefits'
  if (field === 'noPurchaseOption' && value === '否') return 's4-short'
  if (field === 'noSubleaseExpected' && value === '否') return 's5-low'
  if (field === 'lowValueWhenNew' && value === '否') return 's5-low'
  return null
}

/** 单份合同编制缺口（完整性检查） */
export function calcCompletenessGaps(r: H8IdentificationRecord): string[] {
  const gaps: string[] = []
  const idAsset = calcIdentifiedAsset(r.physicallyDistinct, r.supplierSubstantiveSubstitution)
  const direct = resolveDirectUse(r)
  const lease = calcLeaseIdentificationConclusion(idAsset, direct, r.economicBenefits)

  if (!r.physicallyDistinct) gaps.push('§1 物理可区分未填')
  if (!r.supplierSubstantiveSubstitution) gaps.push('§1 实质替换权未填')
  if (!direct) gaps.push('§1 主导使用权未判定')
  if (!r.economicBenefits) gaps.push('§1 经济利益未填')
  if (lease === '待填写三要素后自动判定') gaps.push('§1 三要素未齐')

  if (isContainsLease(lease)) {
    if (!r.splitApplicable) gaps.push('§2 分拆是否适用未标')
    if (!r.combineApplicable) gaps.push('§3 合并是否适用未标')
    if (!r.shortTermApplicable) gaps.push('§4 短期是否适用未标')
    if (!r.lowValueApplicable) gaps.push('§5 低价值是否适用未标')
  }
  if (!r.conclusion) gaps.push('本项结论未勾选')
  return gaps
}

export function resolveLeaseText(r: H8IdentificationRecord): string {
  return calcLeaseIdentificationConclusion(
    calcIdentifiedAsset(r.physicallyDistinct, r.supplierSubstantiveSubstitution),
    resolveDirectUse(r),
    r.economicBenefits,
  )
}

function emptyRecord(contractNo: string, id: string): H8IdentificationRecord {
  return {
    recordId: id,
    contractNo,
    assetDesc: '',
    physicallyDistinct: '',
    physicallyDistinctInfo: '',
    physicallyDistinctIndex: '',
    supplierSubstantiveSubstitution: '',
    substitutionInfo: '',
    substitutionIndex: '',
    substitutionBothConditions: '',
    canDirectPurposeManner: '',
    directPurposeInfo: '',
    usePredetermined: '',
    predeterminedInfo: '',
    canOperateAsset: '',
    operateInfo: '',
    designedAsset: '',
    designInfo: '',
    directUseIndex: '',
    economicBenefits: '',
    economicBenefitsInfo: '',
    economicBenefitsIndex: '',
    directUseOverride: '',
    splitApplicable: '',
    canBenefitSeparately: '',
    canBenefitSeparatelyInfo: '',
    canBenefitSeparatelyIndex: '',
    notHighlyDependent: '',
    notHighlyDependentInfo: '',
    notHighlyDependentIndex: '',
    electNotSplitNonLease: '',
    combineApplicable: '',
    packageCommercialPurpose: '',
    packageInfo: '',
    packageIndex: '',
    considerationDepends: '',
    considerationInfo: '',
    considerationIndex: '',
    combinedSingleLease: '',
    combinedInfo: '',
    combinedIndex: '',
    shortTermApplicable: '',
    termWithRenewalWithin12: '',
    termWithRenewalInfo: '',
    renewContractWithin12: '',
    renewContractInfo: '',
    shortTermIndex: '',
    noPurchaseOption: '',
    noPurchaseOptionInfo: '',
    lowValueApplicable: '',
    lowValueWhenNew: '',
    lowValueInfo: '',
    lowValueIndex: '',
    newAssetValue: 0,
    noSubleaseExpected: '',
    noSubleaseInfo: '',
    noSubleaseIndex: '',
    explanation: '',
    conclusion: '',
  }
}

/** 兼容旧版「items[] 三要素」结构 */
function migrateLegacy(raw: any, id: string): H8IdentificationRecord {
  const base = emptyRecord(String(raw.contractNo ?? ''), id)
  const items: any[] = Array.isArray(raw.items) ? raw.items : []
  const byLabel = (kw: string) => items.find(i => String(i.label ?? '').includes(kw))

  const assetItem = byLabel('已识别') || byLabel('明确指定') || byLabel('依赖')
  const substItem = byLabel('替换')
  const directItem = byLabel('主导')
  const benefitItem = byLabel('经济利益') || byLabel('获益')

  if (assetItem?.conclusion === '是' || assetItem?.conclusion === '否') {
    base.physicallyDistinct = assetItem.conclusion
    // 旧版「是」=有已识别资产 → 新版需替换权为否
    if (assetItem.conclusion === '是') base.supplierSubstantiveSubstitution = '否'
    if (assetItem.conclusion === '否') base.supplierSubstantiveSubstitution = '是'
    base.physicallyDistinctInfo = String(assetItem.explanation ?? '')
  }
  if (substItem?.conclusion === '是' || substItem?.conclusion === '否') {
    base.supplierSubstantiveSubstitution = substItem.conclusion
    base.substitutionInfo = String(substItem.explanation ?? '')
  }
  if (directItem?.conclusion === '是' || directItem?.conclusion === '否') {
    base.canDirectPurposeManner = directItem.conclusion
    base.directPurposeInfo = String(directItem.explanation ?? '')
  }
  if (benefitItem?.conclusion === '是' || benefitItem?.conclusion === '否') {
    base.economicBenefits = benefitItem.conclusion
    base.economicBenefitsInfo = String(benefitItem.explanation ?? '')
  }

  base.explanation = String(raw.auditNote ?? raw.explanation ?? '')
  const fc = raw.finalConclusion ?? raw.conclusion ?? ''
  if (fc === '是' || fc === '否' || fc === '不适用') base.conclusion = fc
  return base
}

function normalizeRecord(raw: any): H8IdentificationRecord {
  const id = raw.recordId ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
  if (Array.isArray(raw.items)) {
    return migrateLegacy(raw, id)
  }
  const blank = emptyRecord(String(raw.contractNo ?? ''), id)
  const rec: H8IdentificationRecord = { ...blank }
  for (const key of Object.keys(blank) as (keyof H8IdentificationRecord)[]) {
    if (raw[key] === undefined || raw[key] === null) continue
    ;(rec as any)[key] = raw[key]
  }
  rec.recordId = id
  rec.contractNo = String(raw.contractNo ?? '')
  rec.newAssetValue = Number(rec.newAssetValue) || 0
  return rec
}

function syncDerivedConclusion(record: H8IdentificationRecord): void {
  const idAsset = calcIdentifiedAsset(record.physicallyDistinct, record.supplierSubstantiveSubstitution)
  const direct = resolveDirectUse(record)
  const leaseText = calcLeaseIdentificationConclusion(idAsset, direct, record.economicBenefits)
  if (isContainsLease(leaseText)) {
    if (record.conclusion !== '否' && record.conclusion !== '不适用') {
      record.conclusion = '是'
    }
  } else if (leaseText === '不包含租赁') {
    if (record.conclusion !== '是' && record.conclusion !== '不适用') {
      record.conclusion = '否'
    }
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8LeaseIdentification(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const records = ref<H8IdentificationRecord[]>([])

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _generateId(): string {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
  }

  function load(): void {
    const data = _getJson(RECORDS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      records.value = data.map(normalizeRecord)
    } else {
      records.value = []
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  const completedCount = computed(() =>
    records.value.filter(r => r.conclusion !== '').length,
  )

  const leaseCount = computed(() =>
    records.value.filter(r => {
      const text = calcLeaseIdentificationConclusion(
        calcIdentifiedAsset(r.physicallyDistinct, r.supplierSubstantiveSubstitution),
        resolveDirectUse(r),
        r.economicBenefits,
      )
      return isContainsLease(text) || r.conclusion === '是'
    }).length,
  )

  const shortTermCount = computed(() =>
    records.value.filter(r =>
      calcShortTermConclusion(
        calcTermWithin12(r.termWithRenewalWithin12, r.renewContractWithin12),
        r.noPurchaseOption,
      ) === '属于短期租赁',
    ).length,
  )

  const lowValueCount = computed(() =>
    records.value.filter(r =>
      calcLowValueConclusion(r.lowValueWhenNew, r.noSubleaseExpected) === '属于低价值资产租赁',
    ).length,
  )

  /** H8-2 全部合同 */
  const h82Contracts = computed<H82ContractSeed[]>(() => {
    const data = _getJson(H82_ROWS_KEY)
    if (!Array.isArray(data)) return []
    const map = new Map<string, H82ContractSeed>()
    for (const row of data) {
      const no = String(row?.contractNo ?? '').trim()
      if (!no || map.has(no)) continue
      map.set(no, {
        contractNo: no,
        assetName: String(row.assetName ?? ''),
        lessor: String(row.lessor ?? ''),
        startDate: String(row.startDate ?? ''),
        endDate: String(row.endDate ?? ''),
      })
    }
    return [...map.values()]
  })

  /** H8-2 有、H8-4 尚无识别记录的合同 */
  const missingH82Contracts = computed(() => {
    const existing = new Set(records.value.map(r => r.contractNo.trim()).filter(Boolean))
    return h82Contracts.value.filter(c => !existing.has(c.contractNo))
  })

  /** 含租赁但 H8-5 尚无记录 */
  const pendingPushH85 = computed(() => {
    const h85 = _getJson(H85_RECORDS_KEY)
    const existing = new Set(
      Array.isArray(h85) ? h85.map((r: any) => String(r?.contractNo ?? '').trim()).filter(Boolean) : [],
    )
    return records.value.filter(r => isContainsLease(resolveLeaseText(r)) && r.contractNo && !existing.has(r.contractNo))
  })

  /** 短期/低价值但 H8-13 尚无行 */
  const pendingPushH813 = computed(() => {
    const h813 = _getJson(H813_ROWS_KEY)
    const existing = new Set(
      Array.isArray(h813) ? h813.map((r: any) => String(r?.contractNo ?? '').trim()).filter(Boolean) : [],
    )
    return records.value.filter(r => {
      if (!r.contractNo || existing.has(r.contractNo)) return false
      const short = calcShortTermConclusion(
        calcTermWithin12(r.termWithRenewalWithin12, r.renewContractWithin12),
        r.noPurchaseOption,
      ) === '属于短期租赁'
      const low = calcLowValueConclusion(r.lowValueWhenNew, r.noSubleaseExpected) === '属于低价值资产租赁'
      return short || low
    })
  })

  function addRecord(contractNo: string, seed?: Partial<H8IdentificationRecord>): void {
    if (!contractNo?.trim()) return
    const no = contractNo.trim()
    if (records.value.some(r => r.contractNo === no)) return
    const rec = emptyRecord(no, _generateId())
    if (seed) {
      if (seed.assetDesc) rec.assetDesc = seed.assetDesc
      if (seed.explanation) rec.explanation = seed.explanation
      if (seed.newAssetValue) rec.newAssetValue = Number(seed.newAssetValue) || 0
    }
    records.value.push(rec)
    _persist()
  }

  function deleteRecord(recordId: string): void {
    const idx = records.value.findIndex(r => r.recordId === recordId)
    if (idx === -1) return
    records.value.splice(idx, 1)
    _persist()
  }

  /** 从 H8-2 批量带入缺失合同（不覆盖已有） */
  function pullFromH82(): { added: number; message: string } {
    const missing = missingH82Contracts.value
    if (!missing.length) {
      return { added: 0, message: h82Contracts.value.length ? 'H8-2 合同均已在本表' : 'H8-2 暂无明细行可带入' }
    }
    for (const c of missing) {
      addRecord(c.contractNo, {
        assetDesc: [c.assetName, c.lessor].filter(Boolean).join(' / '),
        explanation: c.startDate || c.endDate
          ? `自H8-2带入；期间 ${c.startDate || '?'} ~ ${c.endDate || '?'}`
          : '自H8-2带入',
      })
    }
    return { added: missing.length, message: `已从 H8-2 带入 ${missing.length} 份合同` }
  }

  /** 含租赁合同推送至 H8-5（仅新增缺失合同号） */
  function pushToH85(): { added: number; message: string } {
    const pending = pendingPushH85.value
    if (!pending.length) {
      return { added: 0, message: '无待推送合同（需§1结论为含租赁且 H8-5 尚无该合同）' }
    }
    const existingRaw = _getJson(H85_RECORDS_KEY)
    const existing = Array.isArray(existingRaw) ? [...existingRaw] : []
    const existingSet = new Set(existing.map((r: any) => String(r?.contractNo ?? '').trim()).filter(Boolean))
    let added = 0
    for (const r of pending) {
      if (existingSet.has(r.contractNo)) continue
      existing.push({
        recordId: _generateId(),
        contractNo: r.contractNo,
        explanation: `自H8-4识别推送（${resolveLeaseText(r)}）`,
        conclusion: '',
      })
      existingSet.add(r.contractNo)
      added++
    }
    if (added > 0) {
      if (onSave) onSave(H85_RECORDS_KEY, existing)
      allResponses.value.set(H85_RECORDS_KEY, { remark: JSON.stringify(existing) })
    }
    return { added, message: added ? `已向 H8-5 推送 ${added} 份合同，请继续确定租赁期` : '无新增' }
  }

  /** 短期/低价值推送至 H8-13 */
  function pushToH813(): { added: number; message: string } {
    const pending = pendingPushH813.value
    if (!pending.length) {
      return { added: 0, message: '无待推送合同（需§4/§5结论为属于…且 H8-13 尚无该合同）' }
    }
    const existingRaw = _getJson(H813_ROWS_KEY)
    const existing = Array.isArray(existingRaw) ? [...existingRaw] : []
    const existingSet = new Set(existing.map((r: any) => String(r?.contractNo ?? '').trim()).filter(Boolean))
    let added = 0
    for (const r of pending) {
      if (existingSet.has(r.contractNo)) continue
      const isShort = calcShortTermConclusion(
        calcTermWithin12(r.termWithRenewalWithin12, r.renewContractWithin12),
        r.noPurchaseOption,
      ) === '属于短期租赁'
      const isLow = calcLowValueConclusion(r.lowValueWhenNew, r.noSubleaseExpected) === '属于低价值资产租赁'
      existing.push({
        rowId: _generateId(),
        contractNo: r.contractNo,
        assetName: r.assetDesc,
        newAssetValue: r.newAssetValue || 0,
        leaseTermMonths: isShort ? 12 : 0,
        remark: `自H8-4推送：${[isShort && '短期', isLow && '低价值'].filter(Boolean).join('+')}`,
        conclusion: '待核实',
      })
      existingSet.add(r.contractNo)
      added++
    }
    if (added > 0) {
      if (onSave) onSave(H813_ROWS_KEY, existing)
      allResponses.value.set(H813_ROWS_KEY, { remark: JSON.stringify(existing) })
    }
    return { added, message: added ? `已向 H8-13 推送 ${added} 份，请完善费用重算` : '无新增' }
  }

  function updateField(recordId: string, field: string, value: any): string | null {
    const record = records.value.find(r => r.recordId === recordId)
    if (!record) return null

    if (field === 'newAssetValue') {
      record.newAssetValue = Number(value) || 0
      // 全新价值辅助：有金额时提示低价值判断
      if (record.newAssetValue > 0 && record.lowValueWhenNew === '') {
        record.lowValueWhenNew = record.newAssetValue <= LOW_VALUE_THRESHOLD ? '是' : '否'
      }
    } else {
      ;(record as any)[field] = value == null ? '' : String(value)
    }

    // F14 → F13 联动：两条件同时符合 → 有实质替换权
    if (field === 'substitutionBothConditions') {
      if (record.substitutionBothConditions === '是') {
        record.supplierSubstantiveSubstitution = '是'
      } else if (record.substitutionBothConditions === '否' && record.supplierSubstantiveSubstitution === '') {
        record.supplierSubstantiveSubstitution = '否'
      }
    }

    // 不含租赁时，后续节默认不适用提示（不强制清空已填）
    const leaseText = resolveLeaseText(record)
    if (leaseText === '不包含租赁') {
      if (!record.splitApplicable) record.splitApplicable = '否'
      if (!record.combineApplicable) record.combineApplicable = '否'
      if (!record.shortTermApplicable) record.shortTermApplicable = '否'
      if (!record.lowValueApplicable) record.lowValueApplicable = '否'
    }

    // 含租赁时，若未标简化适用，默认提示关注短期/低价值
    if (isContainsLease(leaseText)) {
      if (!record.shortTermApplicable) record.shortTermApplicable = ''
    }

    syncDerivedConclusion(record)
    _persist()
    return suggestTipForField(field, String(value ?? ''))
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    onSave(RECORDS_KEY, records.value.map(r => ({ ...r })))
  }

  return {
    records,
    completedCount,
    leaseCount,
    shortTermCount,
    lowValueCount,
    h82Contracts,
    missingH82Contracts,
    pendingPushH85,
    pendingPushH813,
    addRecord,
    deleteRecord,
    updateField,
    pullFromH82,
    pushToH85,
    pushToH813,
    save,
    load,
    // formula exports for UI
    calcIdentifiedAsset,
    calcDirectUseRight,
    resolveDirectUse,
    calcLeaseIdentificationConclusion,
    calcSplitConclusion,
    calcCombineConclusion,
    calcTermWithin12,
    calcShortTermConclusion,
    calcLowValueConclusion,
    isContainsLease,
    calcCompletenessGaps,
    resolveLeaseText,
    suggestTipForField,
    LOW_VALUE_THRESHOLD,
  }
}

export default useH8LeaseIdentification
