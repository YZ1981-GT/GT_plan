/**
 * 税审底稿索引（底稿目录）—— 11 个分组。
 *
 * 内容照录 CITAR `src/app/workpaper-index.ts`（其事实来源为《税务底稿-索引.xlsx》），
 * 编号与表名逐字一致，改动须同步两边。
 *
 * 消费方：`components/layout/TaxWorkpaperSubnav.vue`（二级栏）、`views/TaxWorkpaperPage.vue`（内容区）。
 */
export interface TaxWorkpaperSheet {
  /** 索引编号，如 2-01(2)-1 */
  code: string
  name: string
}

export interface TaxWorkpaperGroup {
  title: string
  sheets: readonly TaxWorkpaperSheet[]
}

export const TAX_WORKPAPER_INDEX: readonly TaxWorkpaperGroup[] = [
  {
    title: '一、综合类',
    sheets: [
      { code: '1-01', name: '正式报告' },
      { code: '1-02', name: '报告签发' },
      { code: '1-03', name: '三级复核记录表' },
      { code: '1-04', name: '送审报告' },
      { code: '1-05', name: '审核项目总结' },
      { code: '1-06', name: '审核业务工作计划' },
      { code: '1-07', name: '预计时间进度表' },
      { code: '1-08', name: '初步业务活动程序及评价表' },
      { code: '1-09', name: '企业内部控制调查表' },
      { code: '1-10', name: '委托方声明书' },
      { code: '1-11', name: '企业提供资料清单' },
      { code: '1-12', name: '企业基础信息表' },
      { code: '1-13', name: '个人所得税明细申报调查表' },
      { code: '1-14', name: '从业人数和资产总额调查表' },
      { code: '1-15', name: '分支机构基本情况调查表' },
      { code: '1-16', name: '长期股权投资情况调查表' },
      { code: '1-17', name: '长期股权投资的投资收益利润分配情况表' },
      { code: '1-18', name: '承接情况表' },
      { code: '1-19', name: '承接条件评价表' },
      { code: '1-20', name: '纳税申报审核业务委托协议书' },
      { code: '1-21', name: '海外单位实际缴纳企业所得税调查表' },
      { code: '1-22', name: '暂时性差异纳税调整备查表' },
      { code: '1-23', name: '交换意见记录表' },
      { code: '1-24', name: '疑点问题记录表' },
      { code: '1-25', name: '其他' },
    ],
  },
  {
    title: '二、业务实施类-利润综合计算类',
    sheets: [
      { code: '2-01', name: '主营业务收入审核表' },
      { code: '2-01(2)-1', name: '银行业营业收入审核表' },
      { code: '2-01(2)-2', name: '保险业营业收入审核表' },
      { code: '2-01(2)-3', name: '证券业营业收入审核表' },
      { code: '2-01(2)-4', name: '其他金融业营业收入审核表' },
      { code: '2-02', name: '其他业务收入审核表' },
      { code: '2-03', name: '营业外收入审核表' },
      { code: '2-03-1', name: '其他收益审核表' },
      { code: '2-03-2', name: '资产处置收益审核表' },
      { code: '2-04', name: '主营业务成本审核表' },
      { code: '2-04-1', name: '主营业务成本明细审核表' },
      { code: '2-04(2)-1', name: '银行业营业成本审核表' },
      { code: '2-04(2)-2', name: '保险业营业成本审核表' },
      { code: '2-04(2)-3', name: '证券业营业成本审核表' },
      { code: '2-04(2)-4', name: '其他金融业营业成本审核表' },
      { code: '2-04(3)-1', name: '事业单位支出总额审核表' },
      { code: '2-05', name: '其他业务成本审核表' },
      { code: '2-05-01', name: '其他业务成本明细审核表' },
      { code: '2-06', name: '营业外支出审核表' },
      { code: '2-07', name: '税金及附加审核表' },
      { code: '2-08', name: '销售（营业）费用审核表' },
      { code: '2-09', name: '管理费用审核表' },
      { code: '2-10', name: '财务费用审核表' },
      { code: '2-11-1', name: '资产减值损失审核表' },
      { code: '2-11-2', name: '信用减值损失审核表' },
      { code: '2-12', name: '公允价值变动损益审核表' },
      { code: '2-13', name: '投资收益审核表' },
      { code: '2-14', name: '净敞口套期收益审核表' },
      { code: '2-15', name: '制造费用明细审核表' },
      { code: '2-16', name: '生产成本明细审核表' },
      { code: '2-17', name: '在建工程审核表' },
      { code: '2-18', name: '其他成本1明细审核表' },
    ],
  },
  {
    title: '三、纳税调整项目-收入类',
    sheets: [
      { code: '3-01-01-01', name: '视同销售收入审核表' },
      { code: '3-01-01-02', name: '视同销售成本审核表' },
      { code: '3-01-02', name: '未按权责发生制原则确认的收入审核表' },
      { code: '3-01-03', name: '投资收益纳税调整审核表' },
      { code: '3-01-04', name: '长期股权投资初始投资成本损益审核表' },
      { code: '3-01-05', name: '交易性金融资产初始投资调整审核表' },
      { code: '3-01-06', name: '以公允价值计量资产纳税调整表审核表' },
      { code: '3-01-07', name: '专项用途财政性资金纳税调整审核表' },
      { code: '3-01-08', name: '不征税收入审核表' },
      { code: '3-01-09', name: '销售折扣、折让和退回审核表' },
      { code: '3-01-10-01', name: '收入类调整项目—其他调整事项审核表' },
      { code: '3-01-10-02', name: '接受捐赠收入审核表' },
    ],
  },
  {
    title: '四、纳税调整项目-支出类',
    sheets: [
      { code: '3-02-01-01', name: '工资薪金支出审核表' },
      { code: '3-02-01-02', name: '职工福利费支出审核表' },
      { code: '3-02-01-03', name: '职工教育经费支出审核表' },
      { code: '3-02-01-04', name: '职工工会经费支出审核表' },
      { code: '3-02-01-05', name: '各类基本社会保障性缴款支出审核表' },
      { code: '3-02-01-06', name: '补充养老保险、补充医疗保险支出审核表' },
      { code: '3-02-01-07', name: '住房公积金支出审核表' },
      { code: '3-02-01-08', name: '职工薪酬-其他调整项目审核表' },
      { code: '3-02-02', name: '业务招待费支出审核表' },
      { code: '3-02-03', name: '广告费和业务宣传费跨年度纳税调整表审核表' },
      { code: '3-02-04', name: '捐赠支出审核表' },
      { code: '3-02-05', name: '利息支出审核表' },
      { code: '3-02-06', name: '罚金、罚款、被没收财物的损失审核表' },
      { code: '3-02-07', name: '税收滞纳金、加收利息审核表' },
      { code: '3-02-08', name: '赞助支出审核表' },
      { code: '3-02-10-1', name: '业务佣金和手续费审核表' },
      { code: '3-02-10-2', name: '保险企业佣金和手续费鉴证表' },
      { code: '3-02-11', name: '不征税收入用于支出所形成的费用审核表' },
      { code: '3-02-12', name: '跨期扣除项目审核表' },
      { code: '3-02-13', name: '与取得收入无关的支出审核表' },
      { code: '3-02-14', name: '党组织工作经费审核表' },
      { code: '3-02-15', name: '扣除类调整项目—其他调整事项审核表' },
    ],
  },
  {
    title: '五、纳税调整项目-资产类',
    sheets: [
      { code: '3-03-01', name: '固定资产折旧审核表' },
      { code: '3-03-02', name: '生产性生物资产折旧审核表' },
      { code: '3-03-03', name: '无形资产摊销审核表' },
      { code: '3-03-04', name: '长期待摊费用审核表' },
      { code: '3-03-05', name: '油气勘探投资审核表' },
      { code: '3-03-06', name: '油气开发投资审核表' },
      { code: '3-03-07', name: '资产减值准备项目调整明细审核表' },
      { code: '3-03-08', name: '资产损失税前扣除及纳税调整审核表' },
      { code: '3-03-09', name: '资产类调整项目—其他调整事项审核表' },
    ],
  },
  {
    title: '六、纳税调整项目-其他类',
    sheets: [
      { code: '3-04-01', name: '特殊重组审核表' },
      { code: '3-04-02', name: '一般重组审核表' },
      { code: '3-04-03', name: '政策性搬迁审核表' },
      { code: '3-04-04', name: '特殊行业准备金纳税调整审核表' },
      { code: '3-04-04-1', name: '贷款损失准备金及纳税调整明细表' },
      { code: '3-04-06', name: '发行永续债利息支出审核表' },
      { code: '3-04-07', name: '特殊类调整项目—其他调整事项审核表' },
      { code: '3-05', name: '特别纳税调整应税所得审核表' },
      { code: '3-06', name: '纳税调整项目—其他调整事项审核表' },
    ],
  },
  {
    title: '七、资产负债类审核表',
    sheets: [
      { code: '3-07-01', name: '存货审核表' },
      { code: '3-07-02', name: '应收账款审核表' },
      { code: '3-07-03', name: '其他应收款审核表' },
      { code: '3-07-04', name: '长期应付款审核表' },
      { code: '3-07-05', name: '预收账款审核表' },
      { code: '3-07-06', name: '应付账款审核表' },
      { code: '3-07-07', name: '其他应付款审核表' },
      { code: '3-07-08', name: '应付股利审核表' },
      { code: '3-07-09', name: '短期借款审核表' },
      { code: '3-07-10', name: '长期借款审核表' },
      { code: '3-07-11', name: '资本公积审核表' },
      { code: '3-07-12', name: '利润分配审核表' },
      { code: '3-07-13', name: '实收资本审核表' },
      { code: '3-07-14', name: '应收股利审核表' },
    ],
  },
  {
    title: '八、境外所得纳税调整类',
    sheets: [
      { code: '4-01', name: '境外所得税纳税调整后所得审核表' },
      { code: '4-01-01', name: '境外所得税纳税调整后所得审核表（分国）' },
      { code: '4-02', name: '境外分支机构弥补亏损审核表' },
      { code: '4-03', name: '跨年度结转抵免境外所得税审核表' },
      { code: '4-04', name: '境外所得税收抵免审核表' },
    ],
  },
  {
    title: '九、税收优惠类',
    sheets: [
      { code: '5-01-01', name: '免税、减计收入及加计扣除优惠审核表' },
      { code: '5-01-03', name: '研发费用加计扣除优惠审核表' },
      { code: '5-01-04', name: '所得减免优惠审核表' },
      { code: '5-01-05', name: '抵扣应纳税所得额审核表' },
      { code: '5-01-06', name: '企业所得税弥补亏损审核表' },
      { code: '5-02-01', name: '减免所得税额审核表' },
      { code: '5-02-01-02', name: '高新技术企业优惠情况审核表' },
      { code: '5-02-01-03', name: '软件、集成电路企业优惠情况审核表' },
      { code: '5-02-02', name: '税额抵免优惠审核表' },
      { code: '5-02-03', name: '民族自治地区企业所得税地方减免审核表' },
    ],
  },
  {
    title: '十、税款计算和跨地区经营汇总业务类',
    sheets: [
      { code: '6-01', name: '企业所得税缴纳情况审核表' },
      { code: '6-03', name: '企业所得税汇总纳税分支机构所得税分配表' },
    ],
  },
  {
    title: '十一、其他',
    sheets: [
      { code: '7-01', name: '企业重大事项披露表' },
      { code: '7-02', name: '企业所得税年度纳税申报重大事项披露表' },
      { code: '7-03', name: '其他事项审核表' },
      { code: '7-03-01', name: '以前年度损益调整审核表' },
    ],
  },
]

/** 全部表的扁平清单 */
export const ALL_TAX_WORKPAPER_SHEETS: readonly TaxWorkpaperSheet[] =
  TAX_WORKPAPER_INDEX.flatMap(g => g.sheets)

/** 按编号找表；不在清单里即为编号有误 */
export function findTaxWorkpaperSheet(code: string): TaxWorkpaperSheet | undefined {
  return ALL_TAX_WORKPAPER_SHEETS.find(s => s.code === code)
}

/** 按编号找所属分组 */
export function findTaxWorkpaperGroup(code: string): TaxWorkpaperGroup | undefined {
  return TAX_WORKPAPER_INDEX.find(g => g.sheets.some(s => s.code === code))
}

/**
 * 索引页的编号。不是真实底稿，借 `?sheet=` 这一条通道表达「当前在索引页」。
 */
export const TAX_WORKPAPER_INDEX_CODE = '__index__'
