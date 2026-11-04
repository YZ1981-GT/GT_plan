/**
 * 税务底稿索引：11 个分组、162 张表。
 *
 * 移植自 CITAR（src/app/workpaper-index.ts），编号与表名已按样表「税审底稿10.16.xlsx」的
 * 索引 sheet 校正（2-01(2)-2/-3 对调、2-15~2-19 顺移、补 2-09-01 / 2-13-01）。
 * 每个编号对应的表格结构由 backend/scripts/gen/gen_tax_workpaper_sheets.py 从样表生成到 sheets/。
 * 目录栏、索引页、单表页的页签都读这一份，增删表只改这里。
 * 底稿页只显示其中一部分（SHOWN_TAX_WORKPAPER_INDEX，见下方 SHOWN_SHEET_CODES）。
 */

export interface TaxWorkpaperSheet {
  /** 索引编号，如 2-01(2)-1 */
  code: string
  name: string
}

export interface TaxWorkpaperGroup {
  title: string
  sheets: TaxWorkpaperSheet[]
}

export const TAX_WORKPAPER_INDEX: TaxWorkpaperGroup[] = [
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
      // 2-01(2)-2 / -3 照样表：-2 证券业、-3 保险业（成本类 2-04(2) 的顺序相反，样表如此）
      { code: '2-01(2)-2', name: '证券业营业收入审核表' },
      { code: '2-01(2)-3', name: '保险业营业收入审核表' },
      { code: '2-01(2)-4', name: '其他金融业营业收入审核表' },
      { code: '2-01(3)-1', name: '事业单位收入总额审核表' },
      { code: '2-01(3)-2', name: '民间非营利组织收入总额审核表' },
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
      { code: '2-04(3)-2', name: '民间非营利组织支出总额审核表' },
      { code: '2-05', name: '其他业务成本审核表' },
      { code: '2-05-01', name: '其他业务成本明细审核表' },
      { code: '2-06', name: '营业外支出审核表' },
      { code: '2-07', name: '税金及附加审核表' },
      { code: '2-08', name: '销售（营业）费用审核表' },
      { code: '2-09', name: '管理费用审核表' },
      { code: '2-09-01', name: '研发费用审核表' },
      { code: '2-10', name: '财务费用审核表' },
      { code: '2-11-1', name: '资产减值损失审核表' },
      { code: '2-11-2', name: '信用减值损失审核表' },
      { code: '2-12', name: '公允价值变动损益审核表' },
      { code: '2-13', name: '投资收益审核表' },
      { code: '2-13-01', name: '投资收益明细表' },
      { code: '2-14', name: '净敞口套期收益审核表' },
      // 样表索引此行名称为空（"     审核表"），取表内标题
      { code: '2-15', name: '审核表（其他损益类科目）' },
      { code: '2-16', name: '制造费用明细审核表' },
      { code: '2-17', name: '生产成本明细审核表' },
      { code: '2-18', name: '在建工程审核表' },
      { code: '2-19', name: '其他成本1明细审核表' },
    ],
  },
  {
    title: '三、纳税调整项目-收入类',
    sheets: [
      { code: '3-01-01-01', name: '视同销售收入审核表' },
      { code: '3-01-01-02', name: '视同销售成本审核表' },
      {
        code: '3-01-01-03',
        name: '房地产企业预售收入计算的预计利润明细审核表',
      },
      {
        code: '3-01-01-04',
        name: '房地产开发企业特定业务计算的纳税调整审核表',
      },
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
      {
        code: '3-02-09',
        name: '与未实现融资收益相关在当期确认的财务费用审核表',
      },
      { code: '3-02-10-1', name: '业务佣金和手续费审核表' },
      // 索引原文编号尾部带空格,此处已去除。
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
      {
        code: '3-03-09-01',
        name: '执行新租赁准则后使用权资产折旧的纳税调整审核表-经营租赁',
      },
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
      {
        code: '3-04-05',
        name: '合伙企业法人合伙方应分得的应纳税所得额审核表',
      },
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
      {
        code: '4-01-02',
        name: '境外分支机构收入与支出纳税调整额（分国）',
      },
      { code: '4-02', name: '境外分支机构弥补亏损审核表' },
      { code: '4-03', name: '跨年度结转抵免境外所得税审核表' },
      {
        code: '4-03-01',
        name: '前五年境外所得已缴税款未抵扣余额审核表（分国）',
      },
      { code: '4-04', name: '境外所得税收抵免审核表' },
    ],
  },
  {
    title: '九、税收优惠类',
    sheets: [
      { code: '5-01-01', name: '免税、减计收入及加计扣除优惠审核表' },
      {
        code: '5-01-02',
        name: '符合条件的居民企业之间的股息、红利等权益性投资收益优惠审核表',
      },
      { code: '5-01-03', name: '研发费用加计扣除优惠审核表' },
      {
        code: '5-01-03-01',
        name: '自主研发、合作研发、集中研发税收优惠审核表-2015版',
      },
      {
        code: '5-01-03-02',
        name: '自主研发、合作研发、集中研发税收优惠审核表-2021版',
      },
      { code: '5-01-04', name: '所得减免优惠审核表' },
      { code: '5-01-05', name: '抵扣应纳税所得额审核表' },
      { code: '5-01-06', name: '企业所得税弥补亏损审核表' },
      { code: '5-02-01', name: '减免所得税额审核表' },
      {
        code: '5-02-01-01',
        name: '符合条件的小型微利企业减免企业所得税审核表',
      },
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
      {
        code: '6-02',
        name: '跨地区经营汇总纳税企业年度分摊企业所得税审核表',
      },
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

/**
 * 底稿页显示的表（用户 2026-11-04）：一类全部 + 下列编号，其余隐藏。
 * 只影响底稿页的目录栏、索引页、页签与底稿映射里的跳转；表结构、取数与公式计算照旧，
 * 隐藏表的值仍参与被保留表的计算。恢复某张表：把编号加进 SHOWN_SHEET_CODES。
 */
const SHOWN_GROUP_PREFIXES = ['1-']
const SHOWN_SHEET_CODES: ReadonlySet<string> = new Set([
  '2-01', '2-02', '2-03', '2-04', '2-06', '2-07', '2-08', '2-09', '2-10',
  '3-02-01-01', '3-02-01-02', '3-02-01-03', '3-02-01-04', '3-02-01-05', '3-02-01-07',
  '3-02-02', '3-02-03', '3-02-13', '3-02-15',
  '3-03-01', '3-03-04', '3-03-08',
  '5-01-06',
])

/** 该表是否在底稿页显示 */
export function isTaxWorkpaperShown(code: string): boolean {
  return SHOWN_SHEET_CODES.has(code) || SHOWN_GROUP_PREFIXES.some(p => code.startsWith(p))
}

/** 底稿页显示的分组（只含显示的表；没有表的分组整组不显示，分组标题保留样表原编号） */
export const SHOWN_TAX_WORKPAPER_INDEX: TaxWorkpaperGroup[] = TAX_WORKPAPER_INDEX
  .map(g => ({ title: g.title, sheets: g.sheets.filter(s => isTaxWorkpaperShown(s.code)) }))
  .filter(g => g.sheets.length > 0)

/** 全部表的扁平清单（含隐藏的表） */
export const ALL_TAX_WORKPAPER_SHEETS: TaxWorkpaperSheet[] = TAX_WORKPAPER_INDEX.flatMap(g => g.sheets)

/** 底稿页显示的表的扁平清单 */
export const SHOWN_TAX_WORKPAPER_SHEETS: TaxWorkpaperSheet[] = SHOWN_TAX_WORKPAPER_INDEX.flatMap(g => g.sheets)

/** 按编号找表；不在索引里返回 undefined（隐藏的表也能找到，供表名显示用） */
export function findTaxWorkpaperSheet(code: string): TaxWorkpaperSheet | undefined {
  return ALL_TAX_WORKPAPER_SHEETS.find(s => s.code === code)
}

/** 按编号找它所属的分组（原分组，含隐藏的表） */
export function findTaxWorkpaperGroup(code: string): TaxWorkpaperGroup | undefined {
  return TAX_WORKPAPER_INDEX.find(g => g.sheets.some(s => s.code === code))
}

/** 索引页的编号：不是真实底稿，借「当前表编号」这一条通道表达「当前在索引页」 */
export const TAX_INDEX_CODE = '__index__'

/**
 * 税审底稿页「上次打开的表」（按项目存 sessionStorage）。
 * 税审底稿页刷新后回到这张表；别的页面（底稿映射）要打开某张底稿时先写这里再跳转。
 */
const ACTIVE_PREFIX = 'gt.tax-workpaper-active.'

export function loadActiveTaxSheet(projectId: string): string {
  try {
    const saved = sessionStorage.getItem(ACTIVE_PREFIX + projectId)
    // 上次打开的表已被隐藏时回到索引页
    if (saved && (saved === TAX_INDEX_CODE || (findTaxWorkpaperSheet(saved) && isTaxWorkpaperShown(saved)))) return saved
  } catch {
    // sessionStorage 不可用时回到索引页
  }
  return TAX_INDEX_CODE
}

export function saveActiveTaxSheet(projectId: string, code: string): void {
  try {
    sessionStorage.setItem(ACTIVE_PREFIX + projectId, code)
  } catch {
    // 记不住上次的表不影响使用
  }
}
