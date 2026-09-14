/**
 * B19 识别关联方 — 前端预置常量
 *
 * 来源：致同源模板
 * - 关系类型/交易类型枚举对齐后端 VALID_RELATION_TYPES / VALID_TRANSACTION_TYPES
 * - 未披露关联方扫描 33 项固定特征来自「B19-1 识别未披露的关联方关系及异常关联交易」源 sheet
 */

/** 关联方关系类型（对齐后端 VALID_RELATION_TYPES） */
export const RELATION_TYPE_OPTIONS = [
  { value: 'parent', label: '母公司' },
  { value: 'subsidiary', label: '子公司' },
  { value: 'associate', label: '联营企业' },
  { value: 'joint_venture', label: '合营企业' },
  { value: 'key_management', label: '关键管理人员' },
  { value: 'family_member', label: '关系密切的家庭成员' },
  { value: 'other', label: '其他关联方' },
] as const

export const RELATION_TYPE_LABEL: Record<string, string> = Object.fromEntries(
  RELATION_TYPE_OPTIONS.map((o) => [o.value, o.label]),
)

/** 关联方交易类型（对齐后端 VALID_TRANSACTION_TYPES） */
export const TRANSACTION_TYPE_OPTIONS = [
  { value: 'sales', label: '销售商品/提供劳务' },
  { value: 'purchase', label: '采购商品/接受劳务' },
  { value: 'loan', label: '资金拆借' },
  { value: 'guarantee', label: '担保' },
  { value: 'service', label: '关键管理人员报酬/其他服务' },
  { value: 'asset_transfer', label: '资产转让/受让' },
  { value: 'other', label: '其他交易' },
] as const

export const TRANSACTION_TYPE_LABEL: Record<string, string> = Object.fromEntries(
  TRANSACTION_TYPE_OPTIONS.map((o) => [o.value, o.label]),
)

/** 是否存在的三态点选 */
export const EXIST_OPTIONS = [
  { value: '是', label: '是（存在此迹象）', tag: 'danger' },
  { value: '否', label: '否', tag: 'success' },
  { value: '不适用', label: '不适用', tag: 'info' },
] as const

export interface UndisclosedItem {
  key: string
  text: string
}

export interface UndisclosedSection {
  key: string
  title: string
  items: UndisclosedItem[]
}

/**
 * 未披露关联方关系及异常关联交易扫描表（源模板固定 33 项）
 * si = section index, ii = item index → item_id = b19u-{si}-{ii}-{field}
 */
export const UNDISCLOSED_SECTIONS: UndisclosedSection[] = [
  {
    key: 'relation',
    title: '（一）管理层未向注册会计师披露关联方关系的具体特征',
    items: [
      { key: '1', text: '重大或非常规交易的交易对手曾经与被审计单位或其实际控制人、关键管理人员等存在关联关系' },
      { key: '2', text: '重大或非常规交易的交易对手的注册地址或办公地址与被审计单位或其集团成员在同一地点或接近' },
      { key: '3', text: '重大或非常规交易的交易对手的网站地址或其 IP 地址、邮箱域名等与被审计单位或其集团成员相同或接近' },
      { key: '4', text: '重大或非常规交易的交易对手的名称与被审计单位或其集团成员名称相似' },
      { key: '5', text: '重大或非常规交易的交易对手的实际控制人、关键管理人员或购销等关键环节的员工姓名与被审计单位管理层或被审计单位关联方的管理层或员工相近或重合' },
      { key: '6', text: '重大或非常规交易的交易标的与交易对手或被审计单位的经营范围不相关' },
      { key: '7', text: '重大或非常规交易的交易对手与被审计单位的实际控制人、关键管理人员等存在特殊关系，可能使后者对前者施加重大影响，但形式上不构成关联方' },
      { key: '8', text: '重大或非常规交易的交易对手系自然人或由其控制，且交易规模、性质与该交易对手的业务和规模不匹配' },
      { key: '9', text: '被审计单位仅能提供极其有限的与重大或非常规交易的交易对手相关的信息，通过互联网等途径也难以检索到相关信息' },
      { key: '10', text: '交易对手长期拖欠被审计单位的款项，但被审计单位仍继续与其进行交易' },
      { key: '11', text: '交易对手是当年新增或减少的异常重要的客户或供应商，关注其是否为新设公司及交易时间是否接近设立时间' },
      { key: '12', text: '被审计单位与某些交易对手间的交易在价格和条款方面明显与其他交易对手不同，显失公允' },
    ],
  },
  {
    key: 'transaction',
    title: '（二）管理层未向注册会计师披露关联方交易的具体特征',
    items: [
      { key: '1', text: '交易金额重大，或为被审计单位带来大额利润' },
      { key: '2', text: '交易发生频次较少且交易时间接近于资产负债表日，或集中于某一特定期间' },
      { key: '3', text: '交易价格、交付方式及付款条件、结算方式等商业条款与其他客户或供应商明显不同' },
      { key: '4', text: '付款人与销售合同、发票所显示的客户名称不一致，或收款人与采购合同、发票所显示的供应商名称不一致' },
      { key: '5', text: '与同一客户或其关联公司同时发生销售和采购业务' },
      { key: '6', text: '交易规模与交易对手的业务规模明显不符' },
      { key: '7', text: '合同条款明显不符合商业惯例或形式要件不齐备' },
      { key: '8', text: '实际履行情况与合同条款明显不符（如未按约定日期发货或未按结算期付款；商品发运目的地为关联方营业场所）' },
      { key: '9', text: '交易形成的款项长期以债权债务形式存在，购销货款久拖不结或存在金额重大且长期未结算的其他应收款项，且交易理由不明确或不合理' },
      { key: '10', text: '不合常理且对财务指标具有实质性影响的大额政府补助（如用途不明、无条件的补助），真正来源可能是关联方' },
      { key: '11', text: '交易涉及在没有被审计单位帮助的情况下不具备物质基础或财务能力完成交易的第三方' },
      { key: '12', text: '为被审计单位提供担保或被审计单位为之提供担保' },
      { key: '13', text: '实际控制人或控股股东将其持有的被审计单位股份进行质押，将获得的资金用于其自身持有的其他主体' },
      { key: '14', text: '被审计单位收到或对外提供大额捐赠或债务豁免，但相关捐赠或债务豁免没有合理的交易理由' },
      { key: '15', text: '被审计单位银行明细账显示存在定期或有规律的银行存款转入/转出交易，表明可能存在关联方之间的资金安排（如资金集中管理协议或资金池安排）' },
      { key: '16', text: '其他商业理由明显不充分的交易' },
    ],
  },
  {
    key: 'occupation',
    title: '（三）关联方资金占用风险或关联方往来或担保违约风险较高',
    items: [
      { key: '1', text: '上市公司存在违规对外担保，或保证、质押等隐性债务风险' },
      { key: '2', text: '大股东股份较大比例（50% 以上）质押' },
      { key: '3', text: '大股东的持续经营存在重大不确定性' },
      { key: '4', text: '存在通过余额模式形成的关联方资金占用风险（如虚构货币资金余额隐瞒资金占用，或不披露货币资金受限情况隐瞒违规担保）' },
      { key: '5', text: '存在通过发生额模式形成的关联方占用风险（如通过资金拆借、无商业实质的购销业务或票据交换、对外投资、支付工程款等形式占用其资金）' },
    ],
  },
]
