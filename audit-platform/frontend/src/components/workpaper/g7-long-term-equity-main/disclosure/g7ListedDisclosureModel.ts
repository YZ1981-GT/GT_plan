/**
 * G7 上市公司附注披露模型。
 *
 * 结构逐段来自源模板：
 * backend/wp_templates/G/G7 长期股权投资.xlsx
 * Sheet「附注披露信息（上市公司）」A1:M243。
 *
 * 这里按业务区块建模，而不是把 243 行误当作一张同构 13 列表。
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
  /** 合计：minuend − subtrahend */
  diffRows?: [string, string]
  source?: string
}

export interface G7DisclosureTable {
  id: string
  title: string
  /** 与 note_template_listed.json 中 tables[].name 对齐的同步键；缺省回退 title */
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

export interface G7DisclosureSection {
  id: string
  title: string
  sourceRows: string
  guidance?: string[]
  tables?: G7DisclosureTable[]
  narratives?: G7DisclosureNarrative[]
}

export interface G7ListedDisclosureState {
  version: 2
  tables: Record<string, G7DisclosureRow[]>
  texts: Record<string, string>
  updatedAt?: string
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
  '其中：商誉',
  '未实现内部交易损益',
  '减值准备',
  '其他',
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

const movementColumns = cols([
  ['openingBook', '期初余额（账面价值）', 'number', 150],
  ['openingImpairment', '减值准备期初余额', 'number', 140],
  ['addition', '追加/新增投资', 'number', 130],
  ['reduction', '减少投资', 'number', 120],
  ['equityProfit', '权益法下确认的投资损益', 'number', 155],
  ['oci', '其他综合收益调整', 'number', 135],
  ['otherEquity', '其他权益变动', 'number', 125],
  ['dividend', '宣告发放现金股利或利润', 'number', 165],
  ['impairment', '计提减值准备', 'number', 125],
  ['other', '其他', 'number', 100],
  ['closingBook', '期末余额（账面价值）', 'number', 150],
  ['closingImpairment', '减值准备期末余额', 'number', 145],
])

const subsidiaryBasicColumns = cols([
  ['principalPlace', '主要经营地'],
  ['registeredPlace', '注册地'],
  ['businessNature', '业务性质'],
  ['directHolding', '持股比例-直接', 'percent'],
  ['indirectHolding', '持股比例-间接', 'percent'],
  ['acquisitionMethod', '取得方式'],
])

const minorityColumns = cols([
  ['holdingRatio', '少数股东持股比例', 'percent'],
  ['currentProfit', '本期归属于少数股东的损益', 'number'],
  ['dividend', '本期向少数股东宣告分派的股利', 'number'],
  ['closingEquity', '期末少数股东权益余额', 'number'],
])

const balanceColumns = cols([
  ['currentAssets', '流动资产', 'number'],
  ['nonCurrentAssets', '非流动资产', 'number'],
  ['totalAssets', '资产合计', 'number'],
  ['currentLiabilities', '流动负债', 'number'],
  ['nonCurrentLiabilities', '非流动负债', 'number'],
  ['totalLiabilities', '负债合计', 'number'],
])

const resultColumns = cols([
  ['currentRevenue', '本期营业收入', 'number'],
  ['currentProfit', '本期净利润', 'number'],
  ['currentComprehensive', '本期综合收益总额', 'number'],
  ['currentCashFlow', '本期经营活动现金流量', 'number'],
  ['priorRevenue', '上期营业收入', 'number'],
  ['priorProfit', '上期净利润', 'number'],
  ['priorComprehensive', '上期综合收益总额', 'number'],
  ['priorCashFlow', '上期经营活动现金流量', 'number'],
])

const companyColumns = cols(
  Array.from({ length: 6 }, (_, index) => [
    `company${index + 1}`,
    `公司${index + 1}`,
    'number' as G7DisclosureColumnType,
  ]),
)

const investeeBasicColumns = cols([
  ['principalPlace', '主要经营地'],
  ['registeredPlace', '注册地'],
  ['businessNature', '业务性质'],
  ['directHolding', '持股比例-直接', 'percent'],
  ['indirectHolding', '持股比例-间接', 'percent'],
  ['accountingMethod', '会计处理方法'],
])

const currentPriorColumns = cols([
  ['current', '期末数/本期发生额', 'number'],
  ['prior', '期初数/上期发生额', 'number'],
])

const associateMatrixColumns = cols([
  ['company1Current', '公司1-期末/本期', 'number'],
  ['company1Prior', '公司1-期初/上期', 'number'],
  ['company2Current', '公司2-期末/本期', 'number'],
  ['company2Prior', '公司2-期初/上期', 'number'],
  ['company3Current', '公司3-期末/本期', 'number'],
  ['company3Prior', '公司3-期初/上期', 'number'],
])

export const G7_LISTED_DISCLOSURE_SECTIONS: G7DisclosureSection[] = [
  {
    id: 'investment-movement',
    title: '长期股权投资',
    sourceRows: 'A5:M24',
    tables: [
      {
        id: 'investment-movement',
        title: '长期股权投资本期增减变动',
        templateTableKey: '长期股权投资',
        sourceRows: 'A8:M23',
        columns: movementColumns,
        rows: [
          ...blankRows('joint-venture', 3, movementColumns, () => '合营企业'),
          {
            id: 'joint-venture-subtotal',
            label: '合营企业小计',
            values: valuesFor(movementColumns),
            kind: 'subtotal',
            sumRows: ['joint-venture-1', 'joint-venture-2', 'joint-venture-3'],
          },
          ...blankRows('associate', 5, movementColumns, () => '联营企业'),
          {
            id: 'associate-subtotal',
            label: '联营企业小计',
            values: valuesFor(movementColumns),
            kind: 'subtotal',
            sumRows: ['associate-1', 'associate-2', 'associate-3', 'associate-4', 'associate-5'],
          },
          {
            id: 'investment-total',
            label: '合计',
            values: valuesFor(movementColumns),
            kind: 'total',
            sumRows: ['joint-venture-subtotal', 'associate-subtotal'],
          },
        ],
        dynamic: true,
        maxRows: 30,
      },
    ],
    narratives: [
      {
        id: 'impairment-method',
        title: '长期资产减值测试说明',
        sourceRows: 'A24:M24',
        placeholder: '说明可收回金额的确定方法、关键参数、预测期以及与以前年度信息存在差异的原因。',
        guidance: [
          '可收回金额按公允价值减处置费用后的净额确定时，披露公允价值、处置费用、关键参数及依据。',
          '按预计未来现金流量现值确定时，披露预测期、稳定期关键参数及依据。',
        ],
      },
    ],
  },
  {
    id: 'subsidiary-interests',
    title: '1、在子公司中的权益',
    sourceRows: 'A26:I108',
    guidance: [
      '源模板将“集团构成、重要非全资子公司、主要财务信息、重大限制、结构化主体支持、未丧失控制权交易”分别披露。',
      '蓝色提示及示例仅用于编制判断，不作为附注正文同步。',
    ],
    tables: [
      {
        id: 'subsidiary-composition',
        title: '（1）企业集团的构成',
        sourceRows: 'A28:G39',
        columns: subsidiaryBasicColumns,
        rows: blankRows(
          'subsidiary',
          3,
          subsidiaryBasicColumns,
          index => `被投资单位基本信息G7-4 第${12 + index}行`,
        ),
        description: '公式来源：被投资单位基本信息G7-4（B/F/G/H/M/N/S列）。',
        dynamic: true,
        maxRows: 50,
      },
      {
        id: 'important-minority-subsidiaries',
        title: '（2）重要的非全资子公司',
        sourceRows: 'A47:E55',
        columns: minorityColumns,
        rows: blankRows('minority-subsidiary', 5, minorityColumns),
        dynamic: true,
        maxRows: 30,
      },
      {
        id: 'minority-closing-balance',
        title: '（3）重要非全资子公司主要财务信息—期末数',
        sourceRows: 'A56:G64',
        columns: balanceColumns,
        rows: blankRows('minority-closing', 5, balanceColumns),
        dynamic: true,
        maxRows: 30,
      },
      {
        id: 'minority-opening-balance',
        title: '续（1）—期初数',
        sourceRows: 'A65:G72',
        columns: balanceColumns,
        rows: blankRows('minority-opening', 5, balanceColumns),
        dynamic: true,
        maxRows: 30,
      },
      {
        id: 'minority-results',
        title: '续（2）—本期及上期发生额',
        sourceRows: 'A73:I81',
        columns: resultColumns,
        rows: blankRows('minority-results', 5, resultColumns),
        dynamic: true,
        maxRows: 30,
      },
      {
        id: 'ownership-change-impact',
        title: '（6）未丧失控制权的所有者权益份额变动影响',
        sourceRows: 'A95:G108',
        columns: companyColumns,
        rows: metricRows(
          'ownership-change',
          [
            '购买成本/处置对价',
            '现金',
            '非现金资产的公允价值',
            '发行或承担的债务的账面价值',
            '发行的权益性证券的面值',
            '或有对价',
            '购买成本/处置对价合计',
            '减：按取得/处置股权比例计算的子公司净资产份额',
            '差额',
            '其中：调整资本公积',
            '调整盈余公积',
            '调整未分配利润',
          ],
          companyColumns,
          '子公司后续计量测试表G7-10',
        ),
      },
    ],
    narratives: [
      {
        id: 'subsidiary-control-judgement',
        title: '集团构成及控制判断说明',
        sourceRows: 'A40:G46',
        placeholder: '说明持股比例与表决权比例差异、半数以下表决权仍控制或半数以上不控制、代理人/委托人判断、结构化主体控制依据等。',
      },
      {
        id: 'asset-securitisation',
        title: '资产证券化及结构化主体说明',
        sourceRows: 'A45:G46',
        placeholder: '如适用，说明主要交易安排、破产隔离条款及会计处理；不适用时标记不适用。',
        guidance: ['模板中的[X]及示例年份为编制示例，不能直接进入正式披露正文。'],
      },
      {
        id: 'asset-use-restrictions',
        title: '（4）使用资产和清偿负债存在的重大限制',
        sourceRows: 'A82:I85',
        placeholder: '说明限制的性质、程度以及涉及资产负债在合并财务报表中的金额。',
      },
      {
        id: 'structured-entity-support',
        title: '（5）向纳入合并范围的结构化主体提供支持',
        sourceRows: 'A86:I90',
        placeholder: '说明合同约定、已提供支持的类型/金额/原因以及未来提供支持的意图。',
      },
      {
        id: 'ownership-change-description',
        title: '（6）所有者权益份额发生变化但仍控制子公司的交易说明',
        sourceRows: 'A91:I94',
        placeholder: '说明交易背景、股权比例变化、交易对价、少数股东权益及归属于母公司权益的影响。',
        guidance: ['源模板A94为示例文字，应替换为本项目实际交易情况。'],
      },
    ],
  },
  {
    id: 'joint-associate-interests',
    title: '2、在合营安排或联营企业中的权益',
    sourceRows: 'A109:G233',
    tables: [
      {
        id: 'important-jv-associate',
        title: '（1）重要的合营企业或联营企业',
        sourceRows: 'A111:G124',
        columns: investeeBasicColumns,
        rows: blankRows(
          'important-jv-associate',
          10,
          investeeBasicColumns,
          index => `被投资单位基本信息G7-4 第${index < 5 ? 23 + index : 24 + index}行`,
        ),
        dynamic: true,
        maxRows: 50,
      },
      {
        id: 'important-jv-balance',
        title: '（2）重要合营企业主要财务信息—资产负债及权益法调节',
        sourceRows: 'A132:C151',
        columns: currentPriorColumns,
        rows: annotateEquityBridgeSources(metricRows(
          'important-jv-balance',
          [
            '流动资产',
            '其中：现金和现金等价物',
            '非流动资产',
            '资产合计',
            '流动负债',
            '非流动负债',
            '负债合计',
            '净资产',
            '其中：少数股东权益',
            '归属于母公司的所有者权益',
            '按持股比例计算的净资产份额',
            '调整事项',
            '其中：商誉',
            '未实现内部交易损益',
            '减值准备',
            '其他',
            '对合营企业权益投资的账面价值',
            '存在公开报价的权益投资的公允价值',
          ],
          currentPriorColumns,
          '被投资单位财务信息（合营、联营）G7-5',
        )),
      },
      {
        id: 'important-jv-results',
        title: '续：重要合营企业本期及上期经营成果',
        sourceRows: 'A152:C163',
        columns: currentPriorColumns,
        rows: metricRows(
          'important-jv-results',
          ['营业收入', '财务费用', '所得税费用', '净利润', '终止经营的净利润', '其他综合收益', '综合收益总额', '本期收到的股利'],
          currentPriorColumns,
          '被投资单位财务信息（合营、联营）G7-5',
        ),
      },
      {
        id: 'important-associate-balance',
        title: '（3）重要联营企业主要财务信息—资产负债及权益法调节',
        sourceRows: 'A165:G187',
        columns: associateMatrixColumns,
        rows: annotateEquityBridgeSources(metricRows(
          'important-associate-balance',
          [
            '流动资产',
            '其中：现金和现金等价物',
            '非流动资产',
            '资产合计',
            '流动负债',
            '非流动负债',
            '负债合计',
            '净资产',
            '其中：少数股东权益',
            '归属于母公司的所有者权益',
            '按持股比例计算的净资产份额',
            '调整事项',
            '其中：商誉',
            '未实现内部交易损益',
            '减值准备',
            '其他',
            '对联营企业权益投资的账面价值',
            '存在公开报价的权益投资的公允价值',
          ],
          associateMatrixColumns,
          '被投资单位财务信息（合营、联营）G7-5',
        )),
      },
      {
        id: 'important-associate-results',
        title: '续：重要联营企业本期及上期经营成果',
        sourceRows: 'A188:G197',
        columns: associateMatrixColumns,
        rows: metricRows(
          'important-associate-results',
          ['营业收入', '净利润', '终止经营的净利润', '其他综合收益', '综合收益总额', '本期收到的股利'],
          associateMatrixColumns,
          '被投资单位财务信息（合营、联营）G7-5',
        ),
      },
      {
        id: 'unimportant-aggregate',
        title: '（4）其他不重要合营企业和联营企业的汇总财务信息',
        sourceRows: 'A199:C213',
        columns: currentPriorColumns,
        rows: [
          groupRow('ua-jv-group', '合营企业：', currentPriorColumns),
          {
            id: 'ua-jv-carrying',
            label: '投资账面价值合计',
            values: valuesFor(currentPriorColumns),
            kind: 'data',
            source: '明细表G7-2',
          },
          groupRow('ua-jv-share-header', '下列各项按持股比例计算的合计数', currentPriorColumns),
          {
            id: 'ua-jv-profit',
            label: '净利润',
            values: valuesFor(currentPriorColumns),
            kind: 'data',
            source: '明细表G7-2 / 财务信息G7-5×持股比例',
          },
          {
            id: 'ua-jv-oci',
            label: '其他综合收益',
            values: valuesFor(currentPriorColumns),
            kind: 'data',
            source: '明细表G7-2 / 财务信息G7-5×持股比例',
          },
          {
            id: 'ua-jv-comprehensive',
            label: '综合收益总额',
            values: valuesFor(currentPriorColumns),
            kind: 'data',
            source: '明细表G7-2 / 财务信息G7-5×持股比例',
          },
          groupRow('ua-assoc-group', '联营企业：', currentPriorColumns),
          {
            id: 'ua-assoc-carrying',
            label: '投资账面价值合计',
            values: valuesFor(currentPriorColumns),
            kind: 'data',
            source: '明细表G7-2',
          },
          groupRow('ua-assoc-share-header', '下列各项按持股比例计算的合计数', currentPriorColumns),
          {
            id: 'ua-assoc-profit',
            label: '净利润',
            values: valuesFor(currentPriorColumns),
            kind: 'data',
            source: '明细表G7-2 / 财务信息G7-5×持股比例',
          },
          {
            id: 'ua-assoc-oci',
            label: '其他综合收益',
            values: valuesFor(currentPriorColumns),
            kind: 'data',
            source: '明细表G7-2 / 财务信息G7-5×持股比例',
          },
          {
            id: 'ua-assoc-comprehensive',
            label: '综合收益总额',
            values: valuesFor(currentPriorColumns),
            kind: 'data',
            source: '明细表G7-2 / 财务信息G7-5×持股比例',
          },
        ],
      },
      {
        id: 'excess-losses',
        title: '（6）对合营企业或联营企业发生超额亏损的分担额',
        sourceRows: 'A220:D232',
        columns: cols([
          ['priorUnrecognised', '前期累积未确认的损失份额', 'number'],
          ['currentUnrecognised', '本期未确认损失份额/净利润分享额', 'number'],
          ['closingUnrecognised', '期末累积未确认的损失份额', 'number'],
        ]),
        rows: (() => {
          const excessColumns = cols([
            ['priorUnrecognised', '前期累积未确认的损失份额', 'number'],
            ['currentUnrecognised', '本期未确认损失份额/净利润分享额', 'number'],
            ['closingUnrecognised', '期末累积未确认的损失份额', 'number'],
          ])
          return [
            groupRow('el-jv-group', '合营企业', excessColumns),
            ...blankRows('el-jv', 3, excessColumns, index => `未确认投资损失测试表G7-16 第${12 + index}行`),
            {
              id: 'el-jv-subtotal',
              label: '小计',
              values: valuesFor(excessColumns),
              kind: 'subtotal',
              sumRows: ['el-jv-1', 'el-jv-2', 'el-jv-3'],
            },
            groupRow('el-assoc-group', '联营企业', excessColumns),
            ...blankRows('el-assoc', 3, excessColumns, index => `未确认投资损失测试表G7-16 第${17 + index}行`),
            {
              id: 'el-assoc-subtotal',
              label: '小计',
              values: valuesFor(excessColumns),
              kind: 'subtotal',
              sumRows: ['el-assoc-1', 'el-assoc-2', 'el-assoc-3'],
            },
            {
              id: 'el-total',
              label: '合计',
              values: valuesFor(excessColumns),
              kind: 'total',
              sumRows: ['el-jv-subtotal', 'el-assoc-subtotal'],
            },
          ]
        })(),
        dynamic: true,
        maxRows: 30,
      },
    ],
    narratives: [
      {
        id: 'jv-associate-judgement',
        title: '持股比例、重大影响及共同控制判断',
        sourceRows: 'A125:G127、A214:F217',
        placeholder: '说明持股比例与表决权比例差异、20%阈值例外、重大影响及共同控制判断依据。',
      },
      {
        id: 'policy-differences',
        title: '重要会计政策和会计估计差异',
        sourceRows: 'A214:F216',
        placeholder: '说明合营/联营企业的重要会计政策、会计估计与本公司的重大差异及调整。',
      },
      {
        id: 'fund-transfer-restrictions',
        title: '（5）转移资金能力存在的重大限制',
        sourceRows: 'A218:F219',
        placeholder: '说明合营企业或联营企业向本公司转移资金能力存在的重大限制。',
      },
      {
        id: 'commitments-contingencies',
        title: '（7）未确认承诺及或有负债',
        sourceRows: 'A233:F233',
        placeholder: '披露与合营企业投资相关的未确认承诺，以及与合营/联营企业投资相关的或有负债。',
      },
    ],
  },
  {
    id: 'joint-operations',
    title: '（8）重要的共同经营',
    sourceRows: 'A234:F243',
    tables: [
      {
        id: 'joint-operations',
        title: '重要共同经营基本情况',
        sourceRows: 'A235:F240',
        columns: cols([
          ['principalPlace', '主要经营地'],
          ['registeredPlace', '注册地'],
          ['businessNature', '业务性质'],
          ['directShare', '持股比例/享有份额-直接', 'percent'],
          ['indirectShare', '持股比例/享有份额-间接', 'percent'],
        ]),
        rows: blankRows(
          'joint-operation',
          4,
          cols([
            ['principalPlace', '主要经营地'],
            ['registeredPlace', '注册地'],
            ['businessNature', '业务性质'],
            ['directShare', '持股比例/享有份额-直接', 'percent'],
            ['indirectShare', '持股比例/享有份额-间接', 'percent'],
          ]),
          index => `被投资单位基本信息G7-4 第${35 + index}行`,
        ),
        dynamic: true,
        maxRows: 30,
      },
    ],
    narratives: [
      {
        id: 'joint-operation-basis',
        title: '共同经营判断依据',
        sourceRows: 'A241:F243',
        placeholder: '说明持股比例/享有份额与表决权比例差异；共同经营为单独主体时，说明判断为共同经营的依据。',
      },
    ],
  },
]

export function createG7ListedDisclosureState(): G7ListedDisclosureState {
  const tables: Record<string, G7DisclosureRow[]> = {}
  const texts: Record<string, string> = {}
  for (const section of G7_LISTED_DISCLOSURE_SECTIONS) {
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

/** 物化 sumRows / diffRows，供同步与单测使用。 */
export function materializeG7ListedRows(
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

/**
 * 列头元数据（disclosure-table-sync-convergence）：与 buildG7ListedSyncData 同键，
 * 从各表 columns 配置派生 ColumnDef（label 逐字取自源配置，标签列承载 row.label → '项目'）。
 */
export function buildG7ListedColumns(): Record<string, import('../../composables/disclosureColumnDefs').ColumnDef[]> {
  const result: Record<string, import('../../composables/disclosureColumnDefs').ColumnDef[]> = {}
  for (const section of G7_LISTED_DISCLOSURE_SECTIONS) {
    for (const table of section.tables ?? []) {
      const key = table.templateTableKey ?? table.title
      result[key] = [
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

export function buildG7ListedSyncData(
  state: G7ListedDisclosureState,
): Record<string, Record<string, unknown>[]> {
  const result: Record<string, Record<string, unknown>[]> = {}
  for (const section of G7_LISTED_DISCLOSURE_SECTIONS) {
    for (const table of section.tables ?? []) {
      const key = table.templateTableKey ?? table.title
      result[key] = materializeG7ListedRows(state.tables[table.id] ?? [], table.columns)
    }
  }
  result._note_texts = Object.entries(state.texts)
    .filter(([, text]) => text.trim())
    .map(([section, text]) => {
      const narrative = G7_LISTED_DISCLOSURE_SECTIONS
        .flatMap(item => item.narratives ?? [])
        .find(item => item.id === section)
      return {
        section,
        title: narrative?.title ?? section,
        text,
      }
    })
  return result
}
