/** 「访谈记录与核对示例」只读示例（XYZ 公司）：数据与 sheet 名检测。 */

export function isInterviewCheckExampleSheet(sheetName?: string): boolean {
  if (!sheetName) return false
  return /访谈记录与核对.*示例|示例.*访谈记录与核对/.test(sheetName)
}

export interface InterviewExampleContractRow {
  item: string
  inquiry: string
  crossCheck: string
}

/** 三、与发行人的主要合同条款核对（询问所得 vs 发行人合同条款） */
export const INTERVIEW_EXAMPLE_CONTRACT_ROWS: InterviewExampleContractRow[] = [
  { item: '交易模式', inquiry: '包销', crossCheck: '与合同条款一致' },
  { item: '交易标的', inquiry: 'AAA材料', crossCheck: '与合同条款一致' },
  { item: '交易规模', inquiry: '500-600吨（含税金额约5000-6000万）', crossCheck: '与合同条款一致' },
  { item: '付款方式', inquiry: '银行承兑汇票或银行转账', crossCheck: '与合同条款一致' },
  { item: '预付款项及质保金', inquiry: '', crossCheck: '' },
  { item: '付款期限', inquiry: '收货验收后3个月内（较同行业优惠，行业平均约为2.5月/75天）', crossCheck: '与合同条款一致' },
  { item: '订货到发货时间', inquiry: '1个月以内，基本在1周之内发货（一般每月发一次订单）', crossCheck: '合同条款为1个月之内' },
  {
    item: '佣金返利',
    inquiry: '5-6%，每季度按5%结算一次；全年若超过6000万采购量，按全年5.5%结算差额部分；若超过7000万，按全年6%结算差额部分；每年4月份进行全年佣金返利',
    crossCheck: '与合同条款一致',
  },
  { item: '佣金水平', inquiry: '略高于同行业的返利水平，行业平均为4.8-5.5%', crossCheck: '与合同条款一致' },
  {
    item: '运输方式及费用承担',
    inquiry: '实际承运单位为物流公司汽运运输，运输时间3-5天，运费由发行人负责；运费中含保险费，保险受益人为发行人',
    crossCheck: '与合同条款一致',
  },
  { item: '交付方式', inquiry: 'XYZ收到材料、验收合格后，在发行人的验收单和物流公司的运单上签字确认收货', crossCheck: '与合同条款一致' },
  { item: '质量保证', inquiry: '收货验收后质保1个月', crossCheck: '与合同条款一致' },
  { item: '验收或检验', inquiry: '出具验收报告/验收单', crossCheck: '与凭证检查情况一致' },
  {
    item: '退货、换货情况',
    inquiry: '合作5年来，仅在3年前发生过一次质保期内的质量问题，换货解决，价值约为20万',
    crossCheck: '与从发行人处获取的信息一致',
  },
  { item: '是否涉及委托加工', inquiry: '', crossCheck: '' },
  { item: '是否存在实物返利', inquiry: '', crossCheck: '' },
  { item: '现金交易情况', inquiry: '', crossCheck: '' },
  { item: '第三方收款/付款', inquiry: '', crossCheck: '' },
  { item: '代收款、代付款情况', inquiry: '', crossCheck: '' },
  { item: '其他资金往来', inquiry: '', crossCheck: '' },
  { item: '是否涉诉', inquiry: '', crossCheck: '' },
]

export interface InterviewExampleSection {
  title: string
  /** 红字编制指引（源表【】内容）。 */
  guide: string
  /** 示例正文段落。 */
  paragraphs: string[]
}

export const INTERVIEW_EXAMPLE_SECTIONS: InterviewExampleSection[] = [
  {
    title: '一、走访的公司基本信息',
    guide: 'XYZ公司的基本情况，包括：法定代表人、注册地、注册资本、成立时间、股权关系等；取得公司营业执照复印件或照片、公司章程等。',
    paragraphs: [
      '工商信息查询结果、天眼查等查询结果：（记录查询结果并与访谈所述核对）',
      '百度地图等查询走访地址的结果：（核对走访地址与注册/经营地址是否一致）',
    ],
  },
  {
    title: '二、交易基本情况',
    guide: 'XYZ公司与发行人的业务关系、发生业务的起始时间、交易金额、交易量及是否异动，若异动应在访谈中确认异常变动原因；XYZ公司经营状况、与发行人的交易占其总交易比重。公司基本情况需通过查取工商资料，并与发行人记录、增值税发票、XYZ公司网站信息等核对。',
    paragraphs: [
      '与发行人合作从2006年至今已超过15年，XYZ公司主要从发行人采购AAA材料；最近两期交易量、交易金额稳步上升，交易比重保持平稳，未见异常变动。发行人的销售人员经常到访维护客户关系，双方均有继续合作意愿。',
      '检查了XYZ公司的营业执照、组织机构代码证、税务登记证、章程等工商资料并取得复印件，与发行人记录情况、增值税发票、XYZ公司网站信息等核对。【若为新增、异动明显客户/供应商或疑似关联方：考虑取得工商登记资料、纳税资料、开户行及资金流水，了解实际控制人、关键经办人并核对分析，包括经营业绩、银行流水与其声称的经营状况、营运能力、现金流量是否相符】',
      'XYZ公司不是ABC的关联方。',
      'XYZ公司今年对AAA材料的采购目标为3亿（含税），其中约有20%采购自发行人。',
      '业务区域主要集中在山西、陕西地区。',
      '所在行业具有季节性：春、夏、秋为旺季，冬为淡季，原材料采购呈现类似特征。',
    ],
  },
  {
    title: '三、与发行人的主要合同条款核对',
    guide: '询问并取得合同样本，核对XYZ公司与发行人的合同条款：交易模式、交易规模、付款方式、付款期限、运输条款、运输保险受益人、销售佣金比例、质保金比例、信用期等。逐项记录询问所得信息，并与发行人合同条款交叉核对。',
    paragraphs: [],
  },
  {
    title: '四、走访经营场所',
    guide: '走访XYZ的生产经营场所等（若适用），关注其生产经营现状与访谈内容相互印证。',
    paragraphs: [
      'XYZ公司位于XXX工业园区，园区面积300亩，主要生产XXXX，主要原材料AAA，年产能XXXX吨。',
      'XYZ公司目前处于生产旺季，现场观察厂房生产正常，开工率约为90%。',
      '走访原料库，见到约20吨发行人生产的AAA材料（与年消耗500-600吨、每月订货的库存量相符）；走访产成品库，见到XXXX产品约30吨，并见到XYZ公司向其客户发运XXXX产品。',
      'XXXX产品销售良好，采用赊销方式直接销售给最终用户，平均收款周期为2个月，与行业状况基本相符。',
      '产品使用场景的照片（显示客户公司名称的铭牌，注明日期）。',
    ],
  },
  {
    title: '五、现场函证',
    guide: '对XYZ公司进行现场函证。函证内容包括但不限于与发行人的：采购量、采购总额、截止日的债权/债务余额、重要合同条款及其他项目组认为必要的信息；关联方关系确认函。',
    paragraphs: [
      '现场获取经XYZ公司盖章确认的函证，XYZ公司对函证信息确认一致（差异为20吨、200万，系XYZ公司尚未对12月份采购的原材料入账所致，经查12月份发票、出库单、运单核对一致），详见索引号____。',
    ],
  },
  {
    title: '六、关联方关系',
    guide: '记录走访公司的控股股东、实际控制人；董监高及关键经办人员（如采购、销售部门负责人、出纳等），与被审计单位人员比对识别关联关系。',
    paragraphs: [
      '走访公司的控股股东、实际控制人：',
      '走访公司的董监高、关键经办人员（如采购、销售部门负责人、出纳等）：',
    ],
  },
  {
    title: '七、其他',
    guide: '记录其他需要说明的事项，并在最后形成走访结论。',
    paragraphs: ['走访结论：'],
  },
]
