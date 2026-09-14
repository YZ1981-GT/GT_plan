/**
 * g4SppiGuidance — G4-6 源模板表格外提示 / 判断逻辑知识库
 *
 * 内容对齐 Excel《合同现金流量特征分析G4-6》右侧「判断逻辑」列与底部「提示」区，
 * UI 侧以折叠面板/段落旁注呈现，禁止自行臆造准则条文。
 */

export interface JudgmentLogicRow {
  analysisItem: string
  basis: string
}

export interface TipBlock {
  id: string
  title: string
  /** accent: blue=解释性 / red=关键或难点 / amber=操作提示 */
  accent: 'blue' | 'red' | 'amber'
  paragraphs: string[]
}

/** 一、审计目标（源模板） */
export const SPPI_AUDIT_OBJECTIVE =
  '确定债务工具投资合同现金流量是否仅为对本金和以未偿付本金金额为基础的利息的支付（能否通过SPPI测试），并结合业务模式确定金融资产分类。'

/** 二、审计程序（源模板要点） */
export const SPPI_AUDIT_PROCEDURES: string[] = [
  '分析合同约定的本金与利息构成，判断利息对价是否仅反映货币时间价值、信用风险、其他基本借贷风险与成本以及利润率。',
  '识别并评价修正的货币时间价值（利率重置期间与基准期限不匹配）是否需进行基准现金流量比较测试。',
  '分析导致合同现金流量时间或金额变更的条款（提前偿付、展期、杠杆、挂钩权益/商品等）。',
  '评价无追索权约定：必要时穿透至底层资产现金流量特征。',
  '对合同挂钩工具（含分层、瀑布式清偿）执行穿透与信用风险比较分析。',
  '评估微小特征与非真实特征：影响可忽略或不现实时，可不导致SPPI不通过，但须留痕理由与证据。',
]

/** 部分(一) 右侧「判断逻辑」对照表（源模板） */
export const BOND_JUDGMENT_LOGIC_TABLE: JudgmentLogicRow[] = [
  {
    analysisItem: '简单条款直接分析',
    basis:
      '合同现金流量仅为对本金和以未偿付本金金额为基础的利息的支付（即仅包含货币时间价值、信用风险对价和其他基本贷款风险和成本的对价，以及利润率），则通过SPPI测试。',
  },
  {
    analysisItem: '浮动利率',
    basis:
      '若浮动利率仅包含对货币时间价值、信用风险、流动性风险和管理成本的对价，且不含杠杆特征，则浮动利率条款不影响通过SPPI测试。',
  },
  {
    analysisItem: '利率调整 / 修正的货币时间价值',
    basis:
      '若利率重置期间与所参照利率的期限不匹配（如每月重置一年期利率），需进行基准测试：比较合同现金流量与基准工具现金流量差异是否重大；差异不重大时仍可通过SPPI测试。',
  },
  {
    analysisItem: '提前偿付特征',
    basis:
      '提前偿付金额须基本等于未偿付本金及以未偿付本金为基础的利息（可含提前终止的合理补偿），且期限/金额变更与基本借贷安排一致，则不影响SPPI判断。',
  },
  {
    analysisItem: '展期选择权',
    basis:
      '展期期间合同现金流量仍为对本金和利息的支付，且不含杠杆/权益挂钩特征时，展期条款不影响通过SPPI测试。',
  },
  {
    analysisItem: '无追索权',
    basis:
      '无追索权不必然导致不通过。须穿透评估底层资产现金流量是否本身符合SPPI，以及该约定是否引入与基本借贷安排不一致的风险。',
  },
  {
    analysisItem: '合同挂钩工具',
    basis:
      '若现金流量与基本借贷安排不一致（如挂钩权益工具或商品价格），则SPPI测试不通过，应分类为以公允价值计量且其变动计入当期损益的金融资产。',
  },
]

/** 部分(二) 银行理财 / 结构性存款旁注 */
export const FINANCIAL_PRODUCT_TIPS: TipBlock[] = [
  {
    id: 'wmp-non-genuine',
    title: '浮动收益「非真实 / 不现实」特征',
    accent: 'blue',
    paragraphs: [
      '结构性存款等产品常约定固定收益＋条件浮动收益。若触发浮动收益的条件根据历史数据几乎不可能发生（或影响极微小），可将浮动条款视为非真实/不现实特征，不导致SPPI失败，但仍须记录历史区间、发生概率判断与结论。',
      '示例思路：挂钩汇率区间触发浮动时，收集足够长历史样本，证明落在触发区间的概率极低，则可论证浮动条款「不现实」。',
    ],
  },
  {
    id: 'wmp-fail-fvtpl',
    title: '未通过SPPI时的分类后果',
    accent: 'red',
    paragraphs: [
      '合同现金流量特征不满足仅为对本金和利息的支付时，无论业务模式如何，后续计量分类应为以公允价值计量且其变动计入当期损益（FVTPL）。',
    ],
  },
]

/** 部分(三)～(六) 分类旁注（对齐源模板蓝/红字） */
export const SECTION_TIPS: Record<string, TipBlock[]> = {
  preferred_perpetual: [
    {
      id: 'pp-stepup',
      title: '永续债 / 优先股常见条款',
      accent: 'blue',
      paragraphs: [
        '利率跳升（step-up）、递延付息且利息可累积等，若仍反映货币时间价值与信用风险对价、并不引入权益类回报，通常不单独导致SPPI失败。',
        '若可转换为可变数量普通股或以权益工具结算、或回报实质取决于发行人利润/净资产，则通常不满足SPPI。',
      ],
    },
  ],
  convertible: [
    {
      id: 'cb-hybrid',
      title: '可转换债券',
      accent: 'red',
      paragraphs: [
        '含权益转换选择权的可转债一般为混合工具：转换特征使合同现金流量并非仅为对本金和利息的支付，通常通不过SPPI测试，应整体或按准则要求分类为FVTPL（或拆分处理，以适用准则为准）。',
      ],
    },
  ],
  project_trust: [
    {
      id: 'pt-lookthrough',
      title: '项目收益债 / 信托计划',
      accent: 'amber',
      paragraphs: [
        '关注基础资产现金流是否仅为债务工具本息；若依赖再投资、股权投资收益或经营业绩分成，通常不满足SPPI。',
        '存在差额补足、担保时，仍须判断投资人最终现金流量是否仍符合基本借贷安排。',
      ],
    },
  ],
  abs: [
    {
      id: 'abs-tranche',
      title: '资产支持证券（合同挂钩工具）',
      accent: 'red',
      paragraphs: [
        '须同时满足：①底层资产组合本身现金流量符合SPPI；②本层级所暴露的信用风险等于或低于底层资产组合的平均信用风险（优先级常可通过、次级常不通过）。',
        '次级档因优先吸收信用损失，风险特征更接近权益，通常通不过SPPI测试。',
      ],
    },
  ],
}

/** 底部「提示」区 — 六大准则要点（源模板精华，供抽屉/折叠完整呈现） */
export const SPPI_BOTTOM_TIPS: TipBlock[] = [
  {
    id: 'tip-1',
    title: '1. 合同条款与利息构成',
    accent: 'blue',
    paragraphs: [
      '1.1 评估合同现金流量是否仅为对本金和以未偿付本金金额为基础的利息的支付。',
      '1.2 利息对价通常包括：货币时间价值、信用风险、流动性风险、管理成本以及利润率；引入与上述无关的变量（权益价格、商品价格等）通常导致不通过。',
      '1.3 检查是否存在杠杆特征：使合同现金流量变动性增加、与基本借贷安排不一致的条款通常导致不通过。',
    ],
  },
  {
    id: 'tip-2',
    title: '2. 修正的货币时间价值与基准测试',
    accent: 'blue',
    paragraphs: [
      '2.1 当利率重置频率与利率期限不匹配时，存在「修正的货币时间价值」。',
      '2.2 应构造未包含该修正的基准工具，比较未折现合同现金流量与基准现金流量；差异重大则不满足SPPI。',
      '2.3 基准测试须保留计算过程、假设期间与结论说明，作为审计轨迹。',
    ],
  },
  {
    id: 'tip-3',
    title: '3. 改变现金流量时间或金额的条款',
    accent: 'blue',
    paragraphs: [
      '3.1 提前偿付权、展期权、利率重设条款等均须逐项评价对SPPI的影响。',
      '3.2 若条款引入与基本借贷安排无关的或有事件，通常导致不通过。',
    ],
  },
  {
    id: 'tip-4',
    title: '4. 无追索权约定',
    accent: 'amber',
    paragraphs: [
      '无追索权约定本身不自动推翻SPPI；关键在于债权人求偿是否实质上限于特定资产表现，以及该表现是否符合本息支付特征。必要时对底层资产执行穿透分析。',
    ],
  },
  {
    id: 'tip-5',
    title: '5. 合同挂钩工具（难点）',
    accent: 'red',
    paragraphs: [
      '合同挂钩工具（含ABS分层、瀑布清偿）是实操难点：须穿透底层资产池SPPI特征，并比较本档信用风险与底层平均信用风险。',
      '不满足穿透条件或次级档承担不成比例信用损失时，结论一般为不通过SPPI。',
    ],
  },
  {
    id: 'tip-6',
    title: '6. 微小特征与非真实特征',
    accent: 'red',
    paragraphs: [
      '对合同现金流量影响极微（de minimis）或发生可能极低（非真实）的特征，可不导致SPPI不通过，但须在底稿中记录定量/定性依据，不得空泛结论。',
    ],
  },
]

/** 分析项目 → 方法论文本（强化版，供表格「判断逻辑」列） */
export const ENRICHED_METHODOLOGY_MAP: Record<string, string> = Object.fromEntries(
  BOND_JUDGMENT_LOGIC_TABLE.map((r) => {
    const keyMap: Record<string, string> = {
      简单条款直接分析: 'simple',
      浮动利率: 'floating_rate',
      '利率调整 / 修正的货币时间价值': 'rate_adjustment',
      提前偿付特征: 'prepayment',
      展期选择权: 'extension',
      无追索权: 'non_recourse',
      合同挂钩工具: 'linked_instrument',
    }
    return [keyMap[r.analysisItem] ?? r.analysisItem, r.basis]
  }),
)
