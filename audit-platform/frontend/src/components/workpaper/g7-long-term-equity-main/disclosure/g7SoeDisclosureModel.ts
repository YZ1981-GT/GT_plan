/**
 * G7 国企附注披露模型。
 *
 * 结构逐段来自源模板：
 * backend/wp_templates/G/G7 长期股权投资.xlsx
 * Sheet「附注披露信息（国企）」A1:Q355（有效业务列止于 M）。
 *
 * 本表是跨章节编排器：
 * - A6:M199 → 附注「七、合并范围的变化」多个子节
 * - A200:M355 → 附注「八、18 长期股权投资」
 *
 * 禁止再按虚构的「上市5节 + 国企3节 / 统一17列」建模。
 */
export type G7DisclosureValue = string | number | null
export type G7DisclosureColumnType = 'text' | 'number' | 'percent'

export interface G7DisclosureColumn {
  key: string
  label: string
  type?: G7DisclosureColumnType
  width?: number
}

export interface G7DisclosureRow {
  id: string
  label: string
  values: Record<string, G7DisclosureValue>
  kind?: 'data' | 'subtotal' | 'total' | 'group'
  /** 小计/合计：对各子行求和 */
  sumRows?: string[]
  /** 合计：minuend − subtrahend（如 小计 − 减值准备） */
  diffRows?: [string, string]
  source?: string
}

export interface G7DisclosureTable {
  id: string
  title: string
  /** 与 note_template_soe.json 中 tables[].name 对齐的同步键；缺省回退 title */
  templateTableKey?: string
  sourceRows: string
  columns: G7DisclosureColumn[]
  rows: G7DisclosureRow[]
  description?: string
  dynamic?: boolean
  maxRows?: number
}

export interface G7DisclosureNarrative {
  id: string
  title: string
  sourceRows: string
  placeholder: string
  guidance?: string[]
}

export interface G7SoeDisclosureSection {
  id: string
  chapter: 'consolidation-scope' | 'long-term-equity'
  title: string
  sourceRows: string
  /** 同步到附注模块的目标章节编号 */
  noteSectionId: string
  noteSectionTitle: string
  guidance?: string[]
  tables?: G7DisclosureTable[]
  narratives?: G7DisclosureNarrative[]
}

export interface G7SoeDisclosureState {
  version: 2
  tables: Record<string, G7DisclosureRow[]>
  texts: Record<string, string>
  updatedAt?: string
}

export interface G7SoeSyncPayload {
  noteSectionId: string
  noteSectionTitle: string
  sheetName: string
  subTableData: Record<string, Record<string, unknown>[]>
}

function cols(items: Array<[string, string, G7DisclosureColumnType?, number?]>): G7DisclosureColumn[] {
  return items.map(([key, label, type = 'text', width]) => ({ key, label, type, width }))
}

function valuesFor(columns: G7DisclosureColumn[]): Record<string, G7DisclosureValue> {
  return Object.fromEntries(columns.map(col => [col.key, col.type === 'text' ? '' : null]))
}

function blankRows(
  prefix: string,
  count: number,
  columns: G7DisclosureColumn[],
  source?: (index: number) => string,
): G7DisclosureRow[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `${prefix}-${index + 1}`,
    label: '',
    values: valuesFor(columns),
    kind: 'data',
    source: source?.(index),
  }))
}

function metricRows(
  prefix: string,
  labels: string[],
  columns: G7DisclosureColumn[],
  sourceSheet?: string,
): G7DisclosureRow[] {
  return labels.map((label, index) => ({
    id: `${prefix}-${index + 1}`,
    label,
    values: valuesFor(columns),
    kind: 'data' as const,
    source: sourceSheet ? `${sourceSheet}（源表第${index + 1}项）` : undefined,
  }))
}

const EQUITY_BRIDGE_LABELS = new Set([
  '按持股比例计算的净资产份额',
  '调整事项',
  '对合营企业权益投资的账面价值',
  '对联营企业权益投资的账面价值',
])

function annotateEquityBridgeSources(rows: G7DisclosureRow[]): G7DisclosureRow[] {
  for (const row of rows) {
    if (EQUITY_BRIDGE_LABELS.has(row.label)) {
      row.source = '权益法测算G7-14'
    }
  }
  return rows
}

function groupRow(id: string, label: string, columns: G7DisclosureColumn[]): G7DisclosureRow {
  return { id, label, values: valuesFor(columns), kind: 'group' }
}

const subsidiaryBasicColumns = cols([
  ['level', '级次', 'text', 80],
  ['enterpriseType', '企业类型', 'text', 100],
  ['registeredPlace', '注册地', 'text', 110],
  ['principalPlace', '主要经营地', 'text', 110],
  ['businessNature', '业务性质', 'text', 110],
  ['paidInCapital', '实收资本', 'number', 120],
  ['subscribedRatio', '认缴持股比例(%)', 'percent', 130],
  ['paidInRatio', '实缴持股比例(%)', 'percent', 130],
  ['votingRights', '享有的表决权(%)', 'percent', 130],
  ['investmentAmount', '投资额', 'number', 120],
  ['acquisitionMethod', '取得方式', 'text', 120],
])

const controlExceptionColumns = cols([
  ['subscribedRatio', '认缴持股比例(%)', 'percent', 130],
  ['votingRights', '享有的表决权(%)', 'percent', 120],
  ['registeredCapital', '注册资本', 'number', 120],
  ['investmentAmount', '投资额', 'number', 120],
  ['level', '级次', 'text', 80],
  ['reason', '原因说明', 'text', 220],
])

const minorityColumns = cols([
  ['holdingRatio', '少数股东持股比例', 'percent', 130],
  ['currentProfit', '当期归属于少数股东的损益', 'number', 160],
  ['dividend', '当期向少数股东支付的股利', 'number', 160],
  ['closingEquity', '期末累计少数股东权益', 'number', 150],
])

const currentPriorColumns = cols([
  ['current', '期末数/本期发生额', 'number', 140],
  ['prior', '期初数/上期发生额', 'number', 140],
])

const multiCompanyCurrentPriorColumns = cols([
  ['c1Current', '公司1-期末/本期', 'number', 130],
  ['c1Prior', '公司1-期初/上期', 'number', 130],
  ['c2Current', '公司2-期末/本期', 'number', 130],
  ['c2Prior', '公司2-期初/上期', 'number', 130],
  ['c3Current', '公司3-期末/本期', 'number', 130],
  ['c3Prior', '公司3-期初/上期', 'number', 130],
  ['c4Current', '公司4-期末/本期', 'number', 130],
  ['c4Prior', '公司4-期初/上期', 'number', 130],
  ['c5Current', '公司5-期末/本期', 'number', 130],
  ['c5Prior', '公司5-期初/上期', 'number', 130],
])

const formerSubsidiaryColumns = cols([
  ['registeredPlace', '注册地', 'text', 110],
  ['businessNature', '业务性质', 'text', 110],
  ['holdingRatio', '持股比例(%)', 'percent', 110],
  ['votingRights', '表决权比例(%)', 'percent', 120],
  ['reason', '本期不再成为子公司的原因', 'text', 220],
])

const soldFsPositionColumns = cols([
  ['c1SaleDate', '公司1-出售日', 'number', 120],
  ['c1Opening', '公司1-期初余额', 'number', 120],
  ['c2SaleDate', '公司2-出售日', 'number', 120],
  ['c2Opening', '公司2-期初余额', 'number', 120],
])

const soldFsResultColumns = cols([
  ['aCurrent', 'A公司-本年年初至出售日', 'number', 150],
  ['aPrior', 'A公司-上年发生额', 'number', 130],
  ['bCurrent', 'B公司-本年年初至出售日', 'number', 150],
  ['bPrior', 'B公司-上年发生额', 'number', 130],
  ['cCurrent', 'C公司-本年年初至出售日', 'number', 150],
  ['cPrior', 'C公司-上年发生额', 'number', 130],
  ['dCurrent', 'D公司-本年年初至出售日', 'number', 150],
  ['dPrior', 'D公司-上年发生额', 'number', 130],
  ['eCurrent', 'E公司-本年年初至出售日', 'number', 150],
  ['ePrior', 'E公司-上年发生额', 'number', 130],
])

const newEntityColumns = cols([
  ['closingNetAssets', '期末净资产', 'number', 130],
  ['currentNetProfit', '本期净利润', 'number', 130],
])

const commonControlColumns = cols([
  ['consolidationDate', '合并日', 'text', 110],
  ['bookNetAssets', '账面净资产', 'number', 120],
  ['consideration', '交易对价', 'number', 120],
  ['ultimateController', '实际控制人', 'text', 120],
  ['revenue', '本年初至合并日-收入', 'number', 140],
  ['netProfit', '本年初至合并日-净利润', 'number', 140],
  ['cashIncrease', '现金净增加额', 'number', 120],
  ['operatingCashFlow', '经营活动现金流量净额', 'number', 160],
])

const nonCommonControlColumns = cols([
  ['purchaseDate', '购买日', 'text', 110],
  ['purchaseDateBasis', '购买日的确定依据', 'text', 150],
  ['preHolding', '购买日前持有权益比例(%)', 'percent', 150],
  ['atCombinationHolding', '形成合并时持有权益比例(%)', 'percent', 160],
  ['bookNetAssets', '账面净资产总额', 'number', 130],
  ['fvIdentifiable', '可辨认净资产公允价值总额', 'number', 160],
  ['fvMethod', '公允价值确定方法', 'text', 140],
  ['consideration', '交易对价', 'number', 120],
  ['goodwill', '形成商誉', 'number', 120],
  ['postRevenue', '购买日至期末收入', 'number', 140],
  ['postProfit', '购买日至期末净利润', 'number', 140],
  ['postCashFlow', '购买日至期末现金流量', 'number', 150],
])

const absorptionColumns = cols([
  ['assetItem', '并入主要资产-项目', 'text', 140],
  ['assetAmount', '并入主要资产-金额', 'number', 140],
  ['liabilityItem', '并入主要负债-项目', 'text', 140],
  ['liabilityAmount', '并入主要负债-金额', 'number', 140],
])

const ownershipChangeImpactColumns = cols([
  ['company1', '公司1', 'number', 120],
  ['company2', '公司2', 'number', 120],
  ['company3', '公司3', 'number', 120],
])

const classificationColumns = cols([
  ['opening', '年初余额', 'number', 120],
  ['increase', '本期增加', 'number', 120],
  ['decrease', '本期减少', 'number', 120],
  ['closing', '期末余额', 'number', 120],
])

const movementColumns = cols([
  ['investmentCost', '投资成本', 'number', 120],
  ['opening', '期初余额', 'number', 120],
  ['addition', '追加投资', 'number', 110],
  ['reduction', '减少投资', 'number', 110],
  ['equityProfit', '权益法下确认的投资损益', 'number', 155],
  ['oci', '其他综合收益调整', 'number', 135],
  ['otherEquity', '其他权益变动', 'number', 120],
  ['dividend', '宣告发放现金股利或利润', 'number', 165],
  ['impairment', '计提减值准备', 'number', 120],
  ['other', '其他', 'number', 100],
  ['closing', '期末余额', 'number', 120],
  ['closingImpairment', '减值准备期末余额', 'number', 145],
])

const jvFsColumns = cols([
  ['current', '期末数', 'number', 120],
  ['prior', '期初数', 'number', 120],
])

const jvPlColumns = cols([
  ['current', '本期发生额', 'number', 120],
  ['prior', '上期发生额', 'number', 120],
])

const associateFsMatrixColumns = cols([
  ['jv2Current', '合营企业2-期末', 'number', 130],
  ['jv2Prior', '合营企业2-期初', 'number', 130],
  ['a1Current', '联营企业1-期末', 'number', 130],
  ['a1Prior', '联营企业1-期初', 'number', 130],
  ['a2Current', '联营企业2-期末', 'number', 130],
  ['a2Prior', '联营企业2-期初', 'number', 130],
])

const associatePlMatrixColumns = cols([
  ['jv2Current', '合营企业2-本期', 'number', 130],
  ['jv2Prior', '合营企业2-上期', 'number', 130],
  ['a1Current', '联营企业1-本期', 'number', 130],
  ['a1Prior', '联营企业1-上期', 'number', 130],
  ['a2Current', '联营企业2-本期', 'number', 130],
  ['a2Prior', '联营企业2-上期', 'number', 130],
])

const aggregateColumns = cols([
  ['current', '本期数', 'number', 120],
  ['prior', '上期数', 'number', 120],
])

const unrecognizedLossColumns = cols([
  ['priorCumulative', '前期累积未确认的损失份额', 'number', 170],
  ['currentUnrecognized', '本期未确认的损失份额（或本期实现净利润的分享额）', 'number', 220],
  ['closingCumulative', '本期末累积未确认的损失份额', 'number', 170],
])

const structuredExposureColumns = cols([
  ['sponsorScale', '发起规模', 'text', 110],
  ['closingCarrying', '期末账面价值', 'number', 130],
  ['closingMaxLoss', '期末最大损失敞口', 'number', 140],
  ['openingCarrying', '期初账面价值', 'number', 130],
  ['openingMaxLoss', '期初最大损失敞口', 'number', 140],
  ['presentationItem', '列报项目', 'text', 120],
])

const sponsorIncomeColumns = cols([
  ['serviceFee', '服务收费', 'number', 120],
  ['assetSaleGain', '向结构化主体出售资产的利得(损失)', 'number', 200],
  ['total', '合计', 'number', 110],
  ['transferredAssets', '当期向结构化主体转移资产账面价值', 'number', 200],
])

const minorityFsLabels = [
  '流动资产', '非流动资产', '资产合计', '流动负债', '非流动负债', '负债合计',
  '营业收入', '净利润', '综合收益总额', '经营活动现金流量',
]

const soldPositionLabels = [
  '流动资产', '长期股权投资', '固定资产', '无形资产', '其他非流动资产',
  '流动负债', '非流动负债', '所有者权益',
]

const soldResultLabels = [
  '营业收入', '营业成本', '期间费用', '营业利润', '利润总额', '所得税费用', '净利润',
]

const jvFsLabels = [
  '流动资产', '非流动资产', '资产合计', '流动负债', '非流动负债', '负债合计', '净资产',
  '按持股比例计算的净资产份额', '调整事项', '对合营企业权益投资的账面价值',
  '存在公开报价的权益投资的公允价值',
]

const jvPlLabels = [
  '营业收入', '财务费用', '所得税费用', '净利润', '其他综合收益', '综合收益总额',
  '企业本期收到的来自合营企业的股利',
]

const associateFsLabels = [
  '流动资产', '非流动资产', '资产合计', '流动负债', '非流动负债', '负债合计', '净资产',
  '按持股比例计算的净资产份额', '调整事项', '对联营企业权益投资的账面价值',
  '存在公开报价的权益投资的公允价值',
]

const associatePlLabels = [
  '营业收入', '净利润', '其他综合收益', '综合收益总额',
  '企业本期收到的来自联营企业的股利',
]

const ownershipImpactLabels = [
  '购买成本/处置对价：',
  '现金',
  '非现金资产的公允价值',
  '发行或承担的债务的账面价值',
  '发行的权益性证券的面值',
  '或有对价',
  '购买成本/处置对价合计',
  '减：按取得/处置的股权比例计算的子公司净资产份额',
  '差额',
  '其中：调整资本公积',
  '调整盈余公积',
  '调整未分配利润',
]

export const G7_SOE_DISCLOSURE_SECTIONS: G7SoeDisclosureSection[] = [
  // ─── 七、合并范围的变化 ───
  {
    id: 'subsidiary-basic',
    chapter: 'consolidation-scope',
    title: '（一）本期纳入合并报表范围的子公司基本情况',
    sourceRows: 'A7:M23',
    noteSectionId: '七、本期纳入合并报表',
    noteSectionTitle: '本期纳入合并报表范围的子公司基本情况',
    guidance: [
      '企业应按照下列格式披露纳入报表合并范围的全部子公司主要情况；大型企业集团可披露到二级子公司，重要子公司不分级次全部披露。',
      '企业类型：1.境内非金融 2.境内金融 3.境外 4.事业单位 5.基建单位；取得方式：1.投资设立 2.同一控制下合并 3.非同一控制下合并 4.其他。',
      '级次为在整个中央企业集团内的法人级次；持股比例不同于表决权比例的应说明原因。',
    ],
    tables: [
      {
        id: 'subsidiary-basic',
        title: '纳入合并范围的子公司基本情况',
        templateTableKey: '本期纳入合并报表范围的子公司基本情况',
        sourceRows: 'A9:M19',
        columns: subsidiaryBasicColumns,
        rows: blankRows(
          'subsidiary-basic',
          3,
          subsidiaryBasicColumns,
          index => `被投资单位基本信息G7-4 第${12 + index}行；投资额←明细表G7-2`,
        ),
        dynamic: true,
        maxRows: 40,
      },
    ],
    narratives: [
      {
        id: 'holding-voting-diff',
        title: '持股比例与表决权比例差异说明',
        sourceRows: 'A22',
        placeholder: '子公司持股比例不同于表决权比例的，说明表决权比例及差异原因。',
      },
    ],
  },
  {
    id: 'control-below-half',
    chapter: 'consolidation-scope',
    title: '（二）表决权不足半数但形成控制的原因',
    sourceRows: 'A24:H35',
    noteSectionId: '七、母公司拥有被投资',
    noteSectionTitle: '母公司拥有被投资单位表决权不足半数但能对被投资单位形成控制的原因',
    guidance: ['源表按 G7-4 表决权≤50% 条件筛选；原因列需人工补录。'],
    tables: [
      {
        id: 'control-below-half',
        title: '表决权不足半数但形成控制',
        templateTableKey: '序号',
        sourceRows: 'A25:H35',
        columns: controlExceptionColumns,
        rows: blankRows(
          'control-below-half',
          5,
          controlExceptionColumns,
          index => `G7-4 条件筛选（表决权≤50%）第${12 + index}行`,
        ),
        dynamic: true,
        maxRows: 30,
      },
    ],
  },
  {
    id: 'no-control-above-half',
    chapter: 'consolidation-scope',
    title: '（三）表决权过半但未形成控制的原因',
    sourceRows: 'A36:H52',
    noteSectionId: '七、母公司直接或通过',
    noteSectionTitle: '母公司直接或通过其他子公司间接拥有被投资单位半数以上的表决权但未能对其形成控制的原因',
    guidance: ['按合营企业、联营企业分组；源表“其他”行存在 #REF!，平台改为可增删动态行。'],
    tables: [
      {
        id: 'no-control-above-half',
        title: '表决权过半但未纳入合并范围',
        templateTableKey: '序号',
        sourceRows: 'A37:H52',
        columns: controlExceptionColumns,
        rows: [
          groupRow('nc-jv-group', '合营企业', controlExceptionColumns),
          ...blankRows('nc-jv', 3, controlExceptionColumns, index => `G7-4 合营条件筛选 第${23 + index}行`),
          groupRow('nc-assoc-group', '联营企业', controlExceptionColumns),
          ...blankRows('nc-assoc', 3, controlExceptionColumns, index => `G7-4 联营条件筛选 第${29 + index}行`),
          groupRow('nc-other-group', '其他', controlExceptionColumns),
          ...blankRows('nc-other', 2, controlExceptionColumns),
        ],
        dynamic: true,
        maxRows: 40,
      },
    ],
  },
  {
    id: 'non-wholly-owned',
    chapter: 'consolidation-scope',
    title: '（四）重要非全资子公司情况',
    sourceRows: 'A53:L74',
    noteSectionId: '七、重要非全资子公司',
    noteSectionTitle: '重要非全资子公司情况',
    guidance: [
      '上述财务数据以合并日子公司可辨认资产和负债的公允价值为基础进行调整；被划分为持有待售资产的，不需要披露该子公司的上述财务信息。',
    ],
    tables: [
      {
        id: 'minority-shareholders',
        title: '1、少数股东',
        templateTableKey: '少数股东',
        sourceRows: 'A54:F60',
        columns: minorityColumns,
        rows: blankRows('minority', 5, minorityColumns),
        dynamic: true,
        maxRows: 30,
      },
      {
        id: 'minority-financials',
        title: '2、主要财务信息',
        templateTableKey: '主要财务信息',
        sourceRows: 'A61:L73',
        columns: multiCompanyCurrentPriorColumns,
        rows: metricRows('minority-fs', minorityFsLabels, multiCompanyCurrentPriorColumns),
        description: '横向按重要非全资子公司展开期末/期初（或本期/上期）对照。',
      },
    ],
  },
  {
    id: 'accounting-period-mismatch',
    chapter: 'consolidation-scope',
    title: '（五）子公司与母公司会计期间不一致的处理方法',
    sourceRows: 'A75',
    noteSectionId: '七',
    noteSectionTitle: '合并范围的变化',
    narratives: [
      {
        id: 'accounting-period-mismatch',
        title: '会计期间不一致的处理方法',
        sourceRows: 'A75',
        placeholder: '说明子公司与母公司会计期间不一致时，母公司编制合并财务报表的处理方法。',
      },
    ],
  },
  {
    id: 'former-subsidiaries',
    chapter: 'consolidation-scope',
    title: '（六）本期不再纳入合并范围的原子公司',
    sourceRows: 'A76:L107',
    noteSectionId: '七、本期不再纳入合并',
    noteSectionTitle: '本期不再纳入合并范围的原子公司',
    guidance: [
      '本期因处置部分股权投资或其他原因丧失控制权的，还应按《企业会计准则解释第4号》披露剩余股权在丧失控制权日的公允价值及重新计量损益。',
    ],
    tables: [
      {
        id: 'former-subsidiary-basic',
        title: '（1）原子公司的基本情况',
        templateTableKey: '原子公司的基本情况',
        sourceRows: 'A77:G83',
        columns: formerSubsidiaryColumns,
        rows: blankRows(
          'former-sub',
          5,
          formerSubsidiaryColumns,
          index => `处置子公司测试表G7-11 第${9 + index}行`,
        ),
        dynamic: true,
        maxRows: 30,
      },
      {
        id: 'former-subsidiary-position',
        title: '（2）本期出售的子公司出售日的财务状况',
        templateTableKey: '本期出售的子公司出售日的财务状况',
        sourceRows: 'A85:F96',
        columns: soldFsPositionColumns,
        rows: metricRows('sold-position', soldPositionLabels, soldFsPositionColumns),
      },
      {
        id: 'former-subsidiary-results',
        title: '（3）本期出售的子公司出售日的经营成果',
        templateTableKey: '本期出售的子公司处置日的经营成果',
        sourceRows: 'A97:L106',
        columns: soldFsResultColumns,
        rows: metricRows('sold-result', soldResultLabels, soldFsResultColumns),
      },
    ],
    narratives: [
      {
        id: 'sale-date-method',
        title: '出售日的确定方法',
        sourceRows: 'A86',
        placeholder: '说明出售日的确定方法。',
      },
      {
        id: 'remaining-equity-remeasurement',
        title: '丧失控制权日剩余股权公允价值及重新计量损益',
        sourceRows: 'A107',
        placeholder: '披露处置后剩余股权在丧失控制权日的公允价值、按公允价值重新计量产生的利得或损失。',
        guidance: ['具体格式可参考股份公司年审报告模板。'],
      },
    ],
  },
  {
    id: 'newly-consolidated',
    chapter: 'consolidation-scope',
    title: '（七）本期新纳入合并范围的主体',
    sourceRows: 'A108:D119',
    noteSectionId: '七、本期新纳入合并范',
    noteSectionTitle: '本期新纳入合并范围的主体',
    guidance: ['说明新纳入合并范围的子公司、特殊目的主体、受托经营或承租等方式形成控制权的经营实体。'],
    tables: [
      {
        id: 'newly-consolidated',
        title: '本期新纳入合并范围的主体',
        templateTableKey: '公司名称',
        sourceRows: 'A109:D119',
        columns: newEntityColumns,
        rows: blankRows(
          'new-entity',
          10,
          newEntityColumns,
          index => `G7-4「本期新增=是」筛选 第${12 + index}行`,
        ),
        dynamic: true,
        maxRows: 40,
      },
    ],
  },
  {
    id: 'common-control-combination',
    chapter: 'consolidation-scope',
    title: '（八）本期发生的同一控制下企业合并情况',
    sourceRows: 'A120:J126',
    noteSectionId: '七、本期发生的同一控',
    noteSectionTitle: '本期发生的同一控制下企业合并情况',
    guidance: [
      '说明合并日的确定依据、支付的对价及被合并方的账面净资产，并披露被合并方自合并当年期初至合并日的收入、净利润、现金流量等情况。',
    ],
    tables: [
      {
        id: 'common-control-combination',
        title: '同一控制下企业合并',
        templateTableKey: '公司名称',
        sourceRows: 'A122:J126',
        columns: commonControlColumns,
        rows: blankRows('common-control', 3, commonControlColumns),
        dynamic: true,
        maxRows: 20,
      },
    ],
    narratives: [
      {
        id: 'common-control-basis',
        title: '合并日确定依据及其他说明',
        sourceRows: 'A121',
        placeholder: '说明合并日的确定依据、支付对价及被合并方账面净资产等。',
      },
    ],
  },
  {
    id: 'non-common-control-combination',
    chapter: 'consolidation-scope',
    title: '（九）本期发生的非同一控制下企业合并情况',
    sourceRows: 'A127:M136',
    noteSectionId: '七、本期发生的非同一',
    noteSectionTitle: '本期发生的非同一控制下企业合并情况',
    guidance: [
      '说明购买日确定方法、相关交易公允价值确定方法、商誉金额及计算方法；分步实现企业合并的应分别说明前期和本期取得股权的时点、成本、比例及方式。',
    ],
    tables: [
      {
        id: 'non-common-control-combination',
        title: '非同一控制下企业合并',
        templateTableKey: '本期发生的非同一控制下企业合并情况',
        sourceRows: 'A129:M134',
        columns: nonCommonControlColumns,
        rows: blankRows('non-common-control', 3, nonCommonControlColumns),
        dynamic: true,
        maxRows: 20,
      },
    ],
    narratives: [
      {
        id: 'non-common-control-notes',
        title: '购买日、或有对价及商誉相关说明',
        sourceRows: 'A128、A135',
        placeholder: '说明购买日确定依据、或有对价安排及变动、业绩承诺对商誉减值测试的影响、分步合并详情等。',
      },
    ],
  },
  {
    id: 'absorption-merger',
    chapter: 'consolidation-scope',
    title: '（十）本期发生的吸收合并',
    sourceRows: 'A137:F172',
    noteSectionId: '七、本期发生的吸收合',
    noteSectionTitle: '本期发生的吸收合并',
    guidance: ['应分别同一控制下和非同一控制下的吸收合并，披露并入的主要资产、负债项目及其金额。'],
    tables: [
      {
        id: 'absorption-common-control',
        title: '同一控制下吸收合并',
        templateTableKey: '吸收合并的类型',
        sourceRows: 'A141:F156',
        columns: absorptionColumns,
        rows: blankRows('abs-cc', 5, absorptionColumns),
        dynamic: true,
        maxRows: 20,
      },
      {
        id: 'absorption-non-common-control',
        title: '非同一控制下吸收合并',
        sourceRows: 'A157:F172',
        columns: absorptionColumns,
        rows: blankRows('abs-ncc', 5, absorptionColumns),
        dynamic: true,
        maxRows: 20,
      },
    ],
  },
  {
    id: 'group-asset-restrictions',
    chapter: 'consolidation-scope',
    title: '（十一）子公司使用企业集团资产和清偿企业集团债务的重大限制',
    sourceRows: 'A173:F176',
    noteSectionId: '七、子公司使用企业集',
    noteSectionTitle: '子公司使用企业集团资产和清偿企业集团债务的重大限制',
    narratives: [
      {
        id: 'group-asset-restrictions',
        title: '重大限制说明',
        sourceRows: 'A174:A176',
        placeholder: '说明限制内容、少数股东保护性权利的性质和程度，以及限制涉及的资产和负债在合并财务报表中的金额。',
        guidance: [
          '包括对母公司或子公司与集团内其他主体相互转移现金或其他资产的限制，以及对股利分配、贷款或垫款的限制。',
        ],
      },
    ],
  },
  {
    id: 'consolidated-structured-entities',
    chapter: 'consolidation-scope',
    title: '（十二）纳入合并财务报表范围的结构化主体的相关信息',
    sourceRows: 'A177:A182',
    noteSectionId: '七、纳入合并财务报表',
    noteSectionTitle: '纳入合并财务报表范围的结构化主体的相关信息',
    narratives: [
      {
        id: 'consolidated-structured-entities',
        title: '已纳入合并范围的结构化主体风险与支持',
        sourceRows: 'A178:A182',
        placeholder: '披露与结构化主体相关的风险信息，以及合同约定/无合同约定的财务支持类型、金额、原因或意图。',
      },
    ],
  },
  {
    id: 'ownership-interest-changes',
    chapter: 'consolidation-scope',
    title: '（十三）母公司在子公司的所有者权益份额发生变化的情况',
    sourceRows: 'A183:E199',
    noteSectionId: '七、母公司在子公司的',
    noteSectionTitle: '母公司在子公司的所有者权益份额发生变化的情况',
    tables: [
      {
        id: 'ownership-change-impact',
        title: '（2）交易对于少数股东权益及归属于母公司所有者权益的影响',
        templateTableKey: '母公司在子公司的所有者权益份额发生变化的情况',
        sourceRows: 'A186:E199',
        columns: ownershipChangeImpactColumns,
        rows: metricRows('ownership-impact', ownershipImpactLabels, ownershipChangeImpactColumns),
      },
    ],
    narratives: [
      {
        id: 'ownership-change-description',
        title: '（1）在子公司所有者权益份额发生变化的情况说明',
        sourceRows: 'A184:A185',
        placeholder: '说明未丧失控制权的股权变动交易背景、对价及对少数股东权益、资本公积的影响。',
        guidance: ['源表 A185 为示例文字，正式披露请改写为项目实际内容。'],
      },
    ],
  },

  // ─── 八、18 长期股权投资 ───
  {
    id: 'long-term-equity-investment',
    chapter: 'long-term-equity',
    title: '16、长期股权投资',
    sourceRows: 'A200:M355',
    noteSectionId: '八、18',
    noteSectionTitle: '长期股权投资',
    guidance: [
      '分类余额勾稽长期股权投资审定表G7-1；重要合营/联营财务信息来自G7-5；超额亏损来自G7-16。',
      '若对被投资单位持股比例与表决权比例不一致，应说明原因，可索引至附注十一、3。',
      '如果母公司为投资性主体，无需披露下列重要合营/联营企业财务信息。',
    ],
    tables: [
      {
        id: 'lte-classification',
        title: '长期股权投资分类',
        templateTableKey: '长期股权投资分类',
        sourceRows: 'A201:F208',
        columns: classificationColumns,
        rows: [
          {
            id: 'lte-sub',
            label: '对子公司投资',
            values: valuesFor(classificationColumns),
            kind: 'data',
            source: '长期股权投资审定表G7-1!C23:E23',
          },
          {
            id: 'lte-jv',
            label: '对合营企业投资',
            values: valuesFor(classificationColumns),
            kind: 'data',
            source: '长期股权投资审定表G7-1!C24:E24',
          },
          {
            id: 'lte-assoc',
            label: '对联营企业投资',
            values: valuesFor(classificationColumns),
            kind: 'data',
            source: '长期股权投资审定表G7-1!C25:E25',
          },
          {
            id: 'lte-subtotal',
            label: '小计',
            values: valuesFor(classificationColumns),
            kind: 'subtotal',
            sumRows: ['lte-sub', 'lte-jv', 'lte-assoc'],
          },
          {
            id: 'lte-impairment',
            label: '减：长期股权投资减值准备',
            values: valuesFor(classificationColumns),
            kind: 'data',
            source: '长期股权投资审定表G7-1!C43:E43',
          },
          {
            id: 'lte-total',
            label: '合计',
            values: valuesFor(classificationColumns),
            kind: 'total',
            diffRows: ['lte-subtotal', 'lte-impairment'],
            source: 'G7-1 勾稽：小计 − 长期股权投资减值准备',
          },
        ],
      },
      {
        id: 'lte-movement',
        title: '（1）长期股权投资明细',
        templateTableKey: '长期股权投资明细',
        sourceRows: 'A209:M222',
        columns: movementColumns,
        rows: [
          groupRow('mv-jv-group', '一、合营企业', movementColumns),
          ...blankRows('mv-jv', 3, movementColumns, () => '合营企业'),
          groupRow('mv-assoc-group', '二、联营企业', movementColumns),
          ...blankRows('mv-assoc', 3, movementColumns, () => '联营企业'),
          {
            id: 'mv-total',
            label: '合计',
            values: valuesFor(movementColumns),
            kind: 'total',
            sumRows: ['mv-jv-1', 'mv-jv-2', 'mv-jv-3', 'mv-assoc-1', 'mv-assoc-2', 'mv-assoc-3'],
          },
        ],
        dynamic: true,
        maxRows: 40,
      },
      {
        id: 'important-jv-fs',
        title: '（3）重要合营企业的主要财务信息（划分为持有待售的除外）',
        templateTableKey: '重要合营企业的主要财务信息（划分为持有待售的除外）',
        sourceRows: 'A225:D241',
        columns: jvFsColumns,
        rows: annotateEquityBridgeSources(metricRows('jv-fs', jvFsLabels, jvFsColumns, '被投资单位财务信息（合营、联营）G7-5')),
        description: '“调整事项”包括正商誉、抵消的未实现内部交易损益、减值准备等。',
      },
      {
        id: 'important-jv-pl',
        title: '续：重要合营企业经营成果',
        templateTableKey: '续：',
        sourceRows: 'A242:D251',
        columns: jvPlColumns,
        rows: metricRows('jv-pl', jvPlLabels, jvPlColumns, '被投资单位财务信息（合营、联营）G7-5'),
      },
      {
        id: 'important-associate-fs',
        title: '（4）重要联营企业的主要财务信息',
        templateTableKey: '重要联营企业的主要财务信息',
        sourceRows: 'A253:H269',
        columns: associateFsMatrixColumns,
        rows: annotateEquityBridgeSources(metricRows('assoc-fs', associateFsLabels, associateFsMatrixColumns, '被投资单位财务信息（合营、联营）G7-5')),
      },
      {
        id: 'important-associate-pl',
        title: '续：重要联营企业经营成果',
        templateTableKey: '续：重要联营企业经营成果',
        sourceRows: 'A270:H277',
        columns: associatePlMatrixColumns,
        rows: metricRows('assoc-pl', associatePlLabels, associatePlMatrixColumns, '被投资单位财务信息（合营、联营）G7-5'),
      },
      {
        id: 'insignificant-aggregate',
        title: '（5）不重要合营企业和联营企业的汇总信息',
        templateTableKey: '不重要合营企业和联营企业的汇总信息',
        sourceRows: 'A279:D292',
        columns: aggregateColumns,
        rows: [
          groupRow('agg-jv-group', '合营企业：', aggregateColumns),
          { id: 'agg-jv-carrying', label: '投资账面价值合计', values: valuesFor(aggregateColumns), kind: 'data', source: '明细表G7-2' },
          { id: 'agg-jv-share-header', label: '下列各项按持股比例计算的合计数', values: valuesFor(aggregateColumns), kind: 'group' },
          { id: 'agg-jv-profit', label: '净利润', values: valuesFor(aggregateColumns), kind: 'data', source: '明细表G7-2 / 财务信息G7-5×持股比例' },
          { id: 'agg-jv-oci', label: '其他综合收益', values: valuesFor(aggregateColumns), kind: 'data', source: '明细表G7-2 / 财务信息G7-5×持股比例' },
          { id: 'agg-jv-comprehensive', label: '综合收益总额', values: valuesFor(aggregateColumns), kind: 'data', source: '明细表G7-2 / 财务信息G7-5×持股比例' },
          groupRow('agg-assoc-group', '联营企业：', aggregateColumns),
          { id: 'agg-assoc-carrying', label: '投资账面价值合计', values: valuesFor(aggregateColumns), kind: 'data', source: '明细表G7-2' },
          { id: 'agg-assoc-share-header', label: '下列各项按持股比例计算的合计数', values: valuesFor(aggregateColumns), kind: 'group' },
          { id: 'agg-assoc-profit', label: '净利润', values: valuesFor(aggregateColumns), kind: 'data', source: '明细表G7-2 / 财务信息G7-5×持股比例' },
          { id: 'agg-assoc-oci', label: '其他综合收益', values: valuesFor(aggregateColumns), kind: 'data', source: '明细表G7-2 / 财务信息G7-5×持股比例' },
          { id: 'agg-assoc-comprehensive', label: '综合收益总额', values: valuesFor(aggregateColumns), kind: 'data', source: '明细表G7-2 / 财务信息G7-5×持股比例' },
        ],
      },
      {
        id: 'unrecognized-losses',
        title: '超额亏损未确认损失份额',
        templateTableKey: '②对合营企业或联营企业发生超额亏损的分担额',
        sourceRows: 'A301:E312',
        columns: unrecognizedLossColumns,
        rows: [
          groupRow('ul-jv-group', '合营企业', unrecognizedLossColumns),
          ...blankRows('ul-jv', 3, unrecognizedLossColumns, index => `未确认投资损失测试表G7-16 第${12 + index}行`),
          {
            id: 'ul-jv-subtotal',
            label: '小计',
            values: valuesFor(unrecognizedLossColumns),
            kind: 'subtotal',
            sumRows: ['ul-jv-1', 'ul-jv-2', 'ul-jv-3'],
          },
          groupRow('ul-assoc-group', '联营企业', unrecognizedLossColumns),
          ...blankRows('ul-assoc', 3, unrecognizedLossColumns, index => `未确认投资损失测试表G7-16 第${17 + index}行`),
          {
            id: 'ul-assoc-subtotal',
            label: '小计',
            values: valuesFor(unrecognizedLossColumns),
            kind: 'subtotal',
            sumRows: ['ul-assoc-1', 'ul-assoc-2', 'ul-assoc-3'],
          },
          {
            id: 'ul-total',
            label: '合计',
            values: valuesFor(unrecognizedLossColumns),
            kind: 'total',
            sumRows: ['ul-jv-subtotal', 'ul-assoc-subtotal'],
          },
        ],
        dynamic: true,
        maxRows: 40,
      },
      {
        id: 'unconsolidated-structured-exposure',
        title: '未纳入合并范围结构化主体的账面价值与最大损失敞口',
        templateTableKey: 'C.在财务报表中确认的与企业在未纳入合并财务报表范围的结构化主体中权益相关的资产和负债的账面价值与其最大损失敞口的比较。',
        sourceRows: 'A323:G328',
        columns: structuredExposureColumns,
        rows: [
          { id: 'se-senior', label: '优先级债券', values: valuesFor(structuredExposureColumns), kind: 'data' },
          { id: 'se-sub', label: '次级债券', values: valuesFor(structuredExposureColumns), kind: 'data' },
          { id: 'se-cds', label: '信用违约互换（负债）', values: valuesFor(structuredExposureColumns), kind: 'data' },
          ...blankRows('se-other', 2, structuredExposureColumns),
        ],
        dynamic: true,
        maxRows: 20,
      },
      {
        id: 'sponsor-income',
        title: '发起人从结构化主体获得的收益及转移资产',
        templateTableKey: '本公司发起多个结构化主体，但在结构化中均不持有权益。2023年，本公司从发起的结构化主体获得收益的情况以及当期向结构化主体转移资产的情况如下表所示：',
        sourceRows: 'A340:E345',
        columns: sponsorIncomeColumns,
        rows: [
          { id: 'si-abs', label: '信用资产证券化', values: valuesFor(sponsorIncomeColumns), kind: 'data' },
          { id: 'si-fund', label: '投资基金', values: valuesFor(sponsorIncomeColumns), kind: 'data' },
          ...blankRows('si-other', 2, sponsorIncomeColumns),
          {
            id: 'si-total',
            label: '合计',
            values: valuesFor(sponsorIncomeColumns),
            kind: 'total',
            sumRows: ['si-abs', 'si-fund', 'si-other-1', 'si-other-2'],
          },
        ],
        dynamic: true,
        maxRows: 20,
      },
    ],
    narratives: [
      {
        id: 'lte-holding-voting-diff',
        title: '持股比例与表决权比例差异说明',
        sourceRows: 'A223:A224',
        placeholder: '若对被投资单位持股比例与其在被投资单位表决权比例不一致，应说明原因。',
      },
      {
        id: 'policy-estimate-differences',
        title: '重要会计政策、会计估计差异',
        sourceRows: 'A293:A294',
        placeholder: '说明合营企业、联营企业的重要会计政策、会计估计与本公司的重大差异。',
      },
      {
        id: 'joint-control-basis',
        title: '共同控制依据',
        sourceRows: 'A295',
        placeholder: '说明对合营企业具有共同控制的依据。',
      },
      {
        id: 'fund-transfer-restrictions',
        title: '（6）在合营企业和联营企业中权益的相关风险',
        sourceRows: 'A297:A299',
        placeholder: '包括对转移资金能力的重大限制、超额亏损、未确认承诺或或有负债等。',
      },
      {
        id: 'unrecognized-commitments',
        title: '未确认承诺及或有负债',
        sourceRows: 'A313',
        placeholder: '披露与对合营企业投资相关的未确认承诺，以及与对合营或联营企业投资相关的或有负债。',
      },
      {
        id: 'unconsolidated-structured-basic',
        title: '（7）未纳入合并范围的结构化主体基础信息',
        sourceRows: 'A314:A318',
        placeholder: '披露未纳入合并范围结构化主体的性质、目的、规模、活动及融资方式。',
      },
      {
        id: 'sponsor-determination',
        title: '发起人认定依据',
        sourceRows: 'A329:A337',
        placeholder: '企业作为该结构化主体发起人但在其中没有权益时，说明认定依据。',
        guidance: [
          '可能表明企业是发起人的情形包括：单独创建、参与创建与设计、作为最主要服务对象、名称出现在结构化主体名称或证券名称中等。',
        ],
      },
      {
        id: 'unconsolidated-support',
        title: '向未纳入合并范围结构化主体提供支持的情况',
        sourceRows: 'A346:A347',
        placeholder: '披露提供财务支持或其他支持的意图、类型、金额及原因。',
      },
      {
        id: 'unconsolidated-extra',
        title: '未纳入合并范围结构化主体的额外信息披露',
        sourceRows: 'A348:A355',
        placeholder: '按需披露合同支持条款、当期损失、收益类型、承担损失上限与顺序、第三方支持、融资困难及资产负债期限结构等。',
      },
    ],
  },
]

export function createG7SoeDisclosureState(): G7SoeDisclosureState {
  const tables: Record<string, G7DisclosureRow[]> = {}
  const texts: Record<string, string> = {}
  for (const section of G7_SOE_DISCLOSURE_SECTIONS) {
    for (const table of section.tables ?? []) {
      tables[table.id] = table.rows.map(row => ({
        ...row,
        values: { ...row.values },
        sumRows: row.sumRows ? [...row.sumRows] : undefined,
        diffRows: row.diffRows ? [...row.diffRows] as [string, string] : undefined,
      }))
    }
    for (const narrative of section.narratives ?? []) texts[narrative.id] = ''
  }
  return { version: 2, tables, texts }
}

/** 物化 sumRows / diffRows，供同步与单测使用（与 UI computedCell 口径一致）。 */
export function materializeG7DisclosureRows(
  rows: G7DisclosureRow[],
  columns: G7DisclosureColumn[],
): Record<string, unknown>[] {
  const byId = new Map(rows.map(row => [row.id, row]))

  function cell(row: G7DisclosureRow, columnKey: string, visited = new Set<string>()): G7DisclosureValue {
    if (row.diffRows?.length === 2) {
      if (visited.has(row.id)) return null
      visited.add(row.id)
      const [minuendId, subtrahendId] = row.diffRows
      const minuend = byId.get(minuendId)
      const subtrahend = byId.get(subtrahendId)
      const left = minuend ? Number(cell(minuend, columnKey, visited)) || 0 : 0
      const right = subtrahend ? Number(cell(subtrahend, columnKey, visited)) || 0 : 0
      return left - right
    }
    if (!row.sumRows?.length) return row.values[columnKey] ?? null
    if (visited.has(row.id)) return null
    visited.add(row.id)
    return row.sumRows.reduce((sum, rowId) => {
      const child = byId.get(rowId)
      if (!child) return sum
      return sum + (Number(cell(child, columnKey, visited)) || 0)
    }, 0)
  }

  return rows.map(row => {
    const values: Record<string, G7DisclosureValue> = { ...row.values }
    if (row.sumRows?.length || row.diffRows?.length) {
      for (const column of columns) {
        if (column.type === 'number' || column.type === 'percent') {
          values[column.key] = cell(row, column.key)
        }
      }
    }
    return {
      项目: row.label,
      ...values,
      _row_id: row.id,
      _kind: row.kind ?? 'data',
      _source: row.source ?? '',
    }
  })
}

function syncTableKey(table: G7DisclosureTable): string {
  return table.templateTableKey ?? table.title
}

export function buildG7SoeSectionSyncData(
  state: G7SoeDisclosureState,
  section: G7SoeDisclosureSection,
): Record<string, Record<string, unknown>[]> {
  const result: Record<string, Record<string, unknown>[]> = {}
  for (const table of section.tables ?? []) {
    result[syncTableKey(table)] = materializeG7DisclosureRows(
      state.tables[table.id] ?? [],
      table.columns,
    )
  }
  const noteTexts = (section.narratives ?? [])
    .map(item => ({
      section: item.id,
      title: item.title,
      text: state.texts[item.id]?.trim() ?? '',
    }))
    .filter(item => item.text)
  if (noteTexts.length) result._note_texts = noteTexts
  return result
}

/**
 * 列头元数据（disclosure-table-sync-convergence）：全部子表键 → ColumnDef 扁平映射，
 * 键与 syncTableKey 一致；投影器仅按各 payload 实含键查找，多余键自动忽略。
 * label 逐字取自各表 columns 配置，标签列承载 row.label → '项目'。
 */
export function buildG7SoeColumns(): Record<string, import('../../composables/disclosureColumnDefs').ColumnDef[]> {
  const result: Record<string, import('../../composables/disclosureColumnDefs').ColumnDef[]> = {}
  for (const section of G7_SOE_DISCLOSURE_SECTIONS) {
    for (const table of section.tables ?? []) {
      result[syncTableKey(table)] = [
        { key: '项目', label: '项目', is_label: true },
        ...table.columns.map((c) => ({
          key: c.key,
          label: c.label,
          format: (c.type === 'number' ? 'amount' : c.type === 'percent' ? 'percent' : 'text') as
            'amount' | 'percent' | 'text',
        })),
      ]
    }
  }
  return result
}

/** 按附注目标章节聚合；七章各子节分别同步，八、18 合并为一份。 */
export function buildG7SoeSyncPayloads(state: G7SoeDisclosureState): G7SoeSyncPayload[] {
  const byNote = new Map<string, G7SoeSyncPayload>()
  for (const section of G7_SOE_DISCLOSURE_SECTIONS) {
    const existing = byNote.get(section.noteSectionId)
    const sectionData = buildG7SoeSectionSyncData(state, section)
    if (!existing) {
      byNote.set(section.noteSectionId, {
        noteSectionId: section.noteSectionId,
        noteSectionTitle: section.noteSectionTitle,
        sheetName: '附注披露信息（国企）',
        subTableData: sectionData,
      })
      continue
    }
    for (const [key, rows] of Object.entries(sectionData)) {
      if (key === '_note_texts') {
        existing.subTableData._note_texts = [
          ...(existing.subTableData._note_texts ?? []),
          ...rows,
        ]
      } else {
        existing.subTableData[key] = rows
      }
    }
  }
  return [...byNote.values()]
}

export function g7SoeChapterSections(chapter: G7SoeDisclosureSection['chapter']): G7SoeDisclosureSection[] {
  return G7_SOE_DISCLOSURE_SECTIONS.filter(section => section.chapter === chapter)
}
