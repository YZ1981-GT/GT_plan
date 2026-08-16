/**
 * G7 上市公司附注披露模型。
 *
 * 结构逐段来自源模板：
 * backend/wp_templates/G/G7 长期股权投资.xlsx
 * Sheet「附注披露信息（上市公司）」A1:M243。
 *
 * 这里按业务区块建模，而不是把 243 行误当作一张同构 13 列表。
 */
import { dataTableNames, buildRemovedTableKeys } from '../../composables/disclosureSyncedTables'
import { buildG7SlotColumns, dynamicRowCount, type G7SlotSubColumn } from '../../composables/g7SlotColumns'

export type G7DisclosureValue = string | number | null
export type G7DisclosureColumnType = 'text' | 'number' | 'percent'

export interface G7DisclosureColumn {
  key: string
  label: string
  type?: G7DisclosureColumnType
  width?: number
  /** 两级表头父分组名（禁含 '/'，只支持单级）；与 `flat` 二选一表态。 */
  group?: string
  /** 源模板本就是单行表头 —— 显式标注禁止前缀推断凭空造父表头。 */
  flat?: boolean
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
  /** 标签列头文字（须与 note_template headers[0] 逐字一致）。缺省 '项目'。 */
  labelHeader?: string
  /** 静态列（无 slotConfig 时的最终列集；有 slotConfig 时仅作初始态取值参考） */
  columns: G7DisclosureColumn[]
  rows: G7DisclosureRow[]
  description?: string
  dynamic?: boolean
  maxRows?: number
  /**
   * 声明该表「按被投资单位/公司横向展开」，列集改由 `state.entitySlots[slot]`
   * 动态生成（Task 5.6，Property 18），不再写死列数。
   * 同一 `slot` 可被多张表共享（如上市重要联营企业主要财务信息与其经营成果续表，
   * 两表指的是同 3 家联营企业）。
   */
  slotConfig?: { slot: string; sub?: G7SlotSubColumn[] }
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
  /** 同步到附注模块的目标章节编号（源模板一张披露 sheet 混排多个附注章）。 */
  noteSectionId: string
  noteSectionTitle: string
  guidance?: string[]
  tables?: G7DisclosureTable[]
  narratives?: G7DisclosureNarrative[]
}

export interface G7ListedSyncPayload {
  noteSectionId: string
  noteSectionTitle: string
  sheetName: string
  subTableData: Record<string, Record<string, unknown>[]>
}

export interface G7ListedDisclosureState {
  version: 2
  tables: Record<string, G7DisclosureRow[]>
  texts: Record<string, string>
  updatedAt?: string
  /**
   * 上次同步成功时按章节推送的数据子表名清单（`{noteSectionId: string[]}`）。
   * 供 `buildG7ListedSyncPayloads` 计算 `_removed_table_keys` 差集，避免
   * 删除未曾被本底稿推送过的同名表（可能属于别的底稿）。
   */
  previouslySyncedTables?: Record<string, string[]>
  /**
   * 动态槎位实体名清单（`{slot: string[]}`），供带 `slotConfig` 的表生成动态列
   * （Task 5.6）。审计师可增删改名；顺序即列序。缺省用 `G7_LISTED_DEFAULT_SLOT_NAMES`。
   */
  entitySlots?: Record<string, string[]>
}

function cols(items: Array<[string, string, G7DisclosureColumnType?, number?]>): G7DisclosureColumn[] {
  return items.map(([key, label, type = 'text', width]) => ({ key, label, type, width }))
}

/** 带两级表头分组的列定义：`(key, label, type, group|undefined)`。 */
function groupedCols(
  items: Array<[string, string, G7DisclosureColumnType, string | undefined]>,
): G7DisclosureColumn[] {
  return items.map(([key, label, type, group]) => ({ key, label, type, group }))
}

/** 显式标注单行表头（禁前缀推断凭空造父表头）；标签列（首列，通常 type='text'）也需要标注。 */
function flatCols(columns: G7DisclosureColumn[]): G7DisclosureColumn[] {
  return columns.map(c => ({ ...c, flat: true }))
}

function valuesFor(columns: G7DisclosureColumn[]): Record<string, G7DisclosureValue> {
  return Object.fromEntries(columns.map(col => [col.key, col.type === 'text' ? '' : null]))
}

/**
 * 生成 `count` 行空占位行。`count` 由调用方传入 `dynamicRowCount(seedRowCount)`
 * 得出（Requirement 11.7）——无数据时给 1 行空行，不写死 3/5/10。
 */
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

/** 生成 N 行空行 + 对应 id 列表（供分组小计 `sumRows` 动态引用，配合 `dynamicRowCount`）。 */
function blankRowsWithIds(
  prefix: string,
  count: number,
  columns: G7DisclosureColumn[],
  source?: (index: number) => string,
): { rows: G7DisclosureRow[]; ids: string[] } {
  const rows = blankRows(prefix, count, columns, source)
  return { rows, ids: rows.map(r => r.id) }
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

/** 主表「本期增减变动」两级表头分组名（上市/国企共用同名分组）。 */
const MOVEMENT_GROUP = '本期增减变动'

const movementColumns = groupedCols([
  ['openingBook', '期初余额（账面价值）', 'number', undefined],
  ['openingImpairment', '减值准备期初余额', 'number', undefined],
  ['addition', '追加/新增投资', 'number', MOVEMENT_GROUP],
  ['reduction', '减少投资', 'number', MOVEMENT_GROUP],
  ['equityProfit', '权益法下确认的投资损益', 'number', MOVEMENT_GROUP],
  ['oci', '其他综合收益调整', 'number', MOVEMENT_GROUP],
  ['otherEquity', '其他权益变动', 'number', MOVEMENT_GROUP],
  ['dividend', '宣告发放现金股利或利润', 'number', MOVEMENT_GROUP],
  ['impairment', '计提减值准备', 'number', MOVEMENT_GROUP],
  ['other', '其他', 'number', MOVEMENT_GROUP],
  ['closingBook', '期末余额（账面价值）', 'number', undefined],
  ['closingImpairment', '减值准备期末余额', 'number', undefined],
])

/** 持股比例% 两级表头分组名。 */
const HOLDING_RATIO_GROUP = '持股比例%'

// 混合分组：主要经营地/注册地/业务性质/取得方式为 rowspan=2 独立列（不给 group），
// 仅「持股比例%」两子列声明 group（不是 flat —— flat 表示整表无任何分组）。
const subsidiaryBasicColumns = groupedCols([
  ['principalPlace', '主要经营地', 'text', undefined],
  ['registeredPlace', '注册地', 'text', undefined],
  ['businessNature', '业务性质', 'text', undefined],
  ['directHolding', '直接', 'percent', HOLDING_RATIO_GROUP],
  ['indirectHolding', '间接', 'percent', HOLDING_RATIO_GROUP],
  ['acquisitionMethod', '取得方式', 'text', undefined],
])

// 🔴 首列 label 逐字取源 xlsx `少数股东持股比例%`（源文百分号紧跟其后，不得省略、
// 也不得改成全角括号形态）。列 key 不动。
const minorityColumns = flatCols(cols([
  ['holdingRatio', '少数股东持股比例%', 'percent'],
  ['currentProfit', '本期归属于少数股东的损益', 'number'],
  ['dividend', '本期向少数股东宣告分派的股利', 'number'],
  ['closingEquity', '期末少数股东权益余额', 'number'],
]))

// 「重要非全资子公司主要财务信息—期末数」（源 A56:G64）与「续（1）—期初数」（源 A65:G73）
// 各自一张表，**源 xlsx 两表都是两级表头**：父表头分别为 `期末数` / `期初数`，
// 下辖 流动资产/非流动资产/资产合计/流动负债/非流动负债/负债合计 六列。
//
// 🔴 改造前两表共用一份 `flatCols(...)` ⇒ 丢了 group、被 `buildG7*Columns()` 的
//   `...(hasGroup ? {} : { flat: true })` 自动标成 flat ⇒ 附注两级表头被压成单级。
//   `flat` 为真只是**症状**，病因是丢 group（spec Task 6 / A 类）。
//   修法照 soe 侧 `ASSOCIATE_FS_SUB` / `ASSOCIATE_PL_SUB` 已正确拆分的范式：
//   参数化父表头名，让两表各传自己的 group，**列 key 保持不变**（零数据风险）。
const BALANCE_GROUP_CLOSING = '期末数'
const BALANCE_GROUP_OPENING = '期初数'

/** 由父表头名生成重要非全资子公司资产负债类列（六列同 key、只有 group 不同）。 */
function balanceColumnsFor(group: string): G7DisclosureColumn[] {
  return groupedCols([
    ['currentAssets', '流动资产', 'number', group],
    ['nonCurrentAssets', '非流动资产', 'number', group],
    ['totalAssets', '资产合计', 'number', group],
    ['currentLiabilities', '流动负债', 'number', group],
    ['nonCurrentLiabilities', '非流动负债', 'number', group],
    ['totalLiabilities', '负债合计', 'number', group],
  ])
}

const balanceClosingColumns = balanceColumnsFor(BALANCE_GROUP_CLOSING)
const balanceOpeningColumns = balanceColumnsFor(BALANCE_GROUP_OPENING)

// 「续（2）—本期及上期发生额」单表内合并本期/上期两组（源 R74 两级表头）。
const resultColumns = groupedCols([
  ['currentRevenue', '营业收入', 'number', '本期发生额'],
  ['currentProfit', '净利润', 'number', '本期发生额'],
  ['currentComprehensive', '综合收益总额', 'number', '本期发生额'],
  ['currentCashFlow', '经营活动现金流量', 'number', '本期发生额'],
  ['priorRevenue', '营业收入', 'number', '上期发生额'],
  ['priorProfit', '净利润', 'number', '上期发生额'],
  ['priorComprehensive', '综合收益总额', 'number', '上期发生额'],
  ['priorCashFlow', '经营活动现金流量', 'number', '上期发生额'],
])

/** 「ownership-change-impact」槎位默认实体名（源模板字面 `公司1..公司6`，可改名/增删）。 */
const OWNERSHIP_CHANGE_SLOT = 'ownership-change-company'
const OWNERSHIP_CHANGE_SLOT_DEFAULT_NAMES = ['公司1', '公司2', '公司3', '公司4', '公司5', '公司6']

/** 由槎位实体名生成该表的列（单值列，无跨期分组 → flat）。 */
function companyColumnsFor(names: readonly string[]): G7DisclosureColumn[] {
  const slotCols = buildG7SlotColumns(OWNERSHIP_CHANGE_SLOT, names)
  return flatCols(slotCols.map(c => ({
    key: c.key,
    label: c.entityName,
    type: 'number' as G7DisclosureColumnType,
  })))
}

const investeeBasicColumns = groupedCols([
  ['principalPlace', '主要经营地', 'text', undefined],
  ['registeredPlace', '注册地', 'text', undefined],
  ['businessNature', '业务性质', 'text', undefined],
  ['directHolding', '直接', 'percent', '持股比例(%)'],
  ['indirectHolding', '间接', 'percent', '持股比例(%)'],
  // 🔴 逐字取源 xlsx（源文为完整表述，不得简写成「会计处理方法」）。列 key 不动。
  ['accountingMethod', '对合营企业或联营企业投资的会计处理方法', 'text', undefined],
])

/**
 * 「其他不重要合营企业和联营企业的汇总财务信息」列（源 A199:C213）。
 *
 * 🔴 该表源模板列名确为 `期末数/本期发生额` / `期初数/上期发生额`（同一列兼容两种口径），
 * 与下面按表拆分的合营企业 FS/PL 两表**不同**，不得"统一"。
 */
const currentPriorColumns = flatCols(cols([
  ['current', '期末数/本期发生额', 'number'],
  ['prior', '期初数/上期发生额', 'number'],
]))

/**
 * 「重要合营企业主要财务信息」列（源 A132:C151）—— 资产负债口径，列名 `期末数`/`期初数`。
 *
 * 🔴 与下面 PL 表按表拆分：改造前两表共用一份 `currentPriorColumns`（`期末数/本期发生额`），
 * 而源模板 FS 表是 `期末数`/`期初数`、PL 表是 `本期发生额`/`上期发生额` ——
 * 共用一份必然让其中一张与源模板不符。范式参照 soe 侧已正确拆分的
 * `_ASSOC_FS_COLUMNS` / `_ASSOC_PL_COLUMNS`。列 key 不变（`current`/`prior`）。
 */
const jointVentureFsColumns = flatCols(cols([
  ['current', '期末数', 'number'],
  ['prior', '期初数', 'number'],
]))

/** 「续：重要合营企业本期及上期经营成果」列（源 A152:C163）—— 损益口径。 */
const jointVenturePlColumns = flatCols(cols([
  ['current', '本期发生额', 'number'],
  ['prior', '上期发生额', 'number'],
]))

// 超额亏损分担额表：单期数值，无跨期/跨主体分组 → flat
// 🔴 label 逐字取源模板 A220:D232（`本期未确认的损失份额（或本期实现净利润的分享额）`
// 全角括号、`本期末累积未确认的损失份额`），禁简写。
//
// 🔴 列 key 用**美式**拼写，与 soe 变体统一（g7-column-alignment spec Task 9）：
// 本表原用英式 `Unrecognised`，soe 同表用美式 `priorCumulative`/`currentUnrecognized`/
// `closingCumulative`。美式是平台主流（`g7UnrecognizedLossModel` / `useG7EquityMethodFormData`
// / `G7TabUnrecognizedLoss.vue` / J3 / G6 共 40+ 处），英式仅本表 3 列在用 ⇒ 收敛到美式。
// 数据风险为零：量化闸实测 listed `七、1` 全章节 `sub_table_data` 从未推送过。
const excessLossesColumns = flatCols(cols([
  ['priorCumulative', '前期累积未确认的损失份额', 'number'],
  ['currentUnrecognized', '本期未确认的损失份额（或本期实现净利润的分享额）', 'number'],
  ['closingCumulative', '本期末累积未确认的损失份额', 'number'],
]))

// 重要的共同经营：主要经营地/注册地/业务性质独立列 + 持股比例/享有的份额(%) 分组
// （源模板字面「持股比例/享有的份额(%)」含 '/'；group 禁 '/'，改用等价无斜杠表述）
const jointOperationColumns = groupedCols([
  ['principalPlace', '主要经营地', 'text', undefined],
  ['registeredPlace', '注册地', 'text', undefined],
  ['businessNature', '业务性质', 'text', undefined],
  ['directShare', '直接', 'percent', '持股比例或享有的份额(%)'],
  ['indirectShare', '间接', 'percent', '持股比例或享有的份额(%)'],
])

/**
 * 「重要联营企业主要财务信息 / 续：本期及上期经营成果」共用**槎位**（同 3 家联营企业，
 * 源模板字面 `联营企业1..3`）—— 槎位共用是对的（同一批实体），但**子列 label 必须按表拆分**。
 *
 * 🔴 源 xlsx 实证：FS 表（`A165:G187`）子列是 `期末数` / `期初数`，
 * PL 表（`A188:G197`）子列是 `本期发生额` / `上期发生额`。改造前两表共用一份
 * `IMPORTANT_ASSOCIATE_SUB`（`期末/本期` / `期初/上期`）⇒ 两张表都与源模板不符。
 *
 * 🔴 **列 key 不变** —— `buildG7SlotColumns` 拼 key 用 `{slot}_{seq}_{sub.key}`，
 * `sub.key` 保持 `current`/`prior` ⇒ 只动 label 不动 key，零数据风险。
 *
 * 范式参照 soe 侧已正确拆分的 `ASSOCIATE_FS_SUB` / `ASSOCIATE_PL_SUB`（带「不得简写」注释）。
 */
const IMPORTANT_ASSOCIATE_SLOT = 'important-associate'
const IMPORTANT_ASSOCIATE_SLOT_DEFAULT_NAMES = ['联营企业1', '联营企业2', '联营企业3']
/** FS 表子列（源 A165:G187 逐字）。 */
const IMPORTANT_ASSOCIATE_FS_SUB: G7SlotSubColumn[] = [
  { key: 'current', label: '期末数' },
  { key: 'prior', label: '期初数' },
]
/** PL 表子列（源 A188:G197 逐字，不得简写为「本期/上期」）。 */
const IMPORTANT_ASSOCIATE_PL_SUB: G7SlotSubColumn[] = [
  { key: 'current', label: '本期发生额' },
  { key: 'prior', label: '上期发生额' },
]

/** 由槎位实体名 + 该表子列定义生成矩阵列（每实体两子列，按实体名分组）。 */
function associateMatrixColumnsFor(
  names: readonly string[],
  sub: G7SlotSubColumn[],
): G7DisclosureColumn[] {
  const slotCols = buildG7SlotColumns(IMPORTANT_ASSOCIATE_SLOT, names, sub)
  return groupedCols(slotCols.map(c => [
    c.key,
    c.subLabel ?? '',
    'number' as G7DisclosureColumnType,
    c.entityName,
  ]))
}

export const G7_LISTED_DISCLOSURE_SECTIONS: G7DisclosureSection[] = [
  {
    id: 'investment-movement',
    title: '长期股权投资',
    sourceRows: 'A5:M24',
    noteSectionId: '五、18',
    noteSectionTitle: '长期股权投资',
    tables: [
      {
        id: 'investment-movement',
        title: '长期股权投资本期增减变动',
        templateTableKey: '长期股权投资',
        labelHeader: '被投资单位',
        sourceRows: 'A8:M23',
        columns: movementColumns,
        // 🔴 Task 5.3：补源模板 R12「①合营企业」/ R16「②联营企业」分组标签行
        // （原实现只有小计，缺分组标题，行集与源模板不对应）。
        // 🔴 Task 5.6：骨架行数不写死（Requirement 11.7）—— 无数据时给 1 行，
        // `sumRows` 随生成的 id 列表动态构建，不硬编码具体条数。
        rows: (() => {
          const jv = blankRowsWithIds('joint-venture', dynamicRowCount(1), movementColumns, () => '合营企业')
          const assoc = blankRowsWithIds('associate', dynamicRowCount(1), movementColumns, () => '联营企业')
          return [
            groupRow('joint-venture-group', '①合营企业', movementColumns),
            ...jv.rows,
            {
              id: 'joint-venture-subtotal',
              label: '小  计',
              values: valuesFor(movementColumns),
              kind: 'subtotal',
              sumRows: jv.ids,
            },
            groupRow('associate-group', '②联营企业', movementColumns),
            ...assoc.rows,
            {
              id: 'associate-subtotal',
              label: '小  计',
              values: valuesFor(movementColumns),
              kind: 'subtotal',
              sumRows: assoc.ids,
            },
            {
              id: 'investment-total',
              label: '合  计',
              values: valuesFor(movementColumns),
              kind: 'total',
              sumRows: ['joint-venture-subtotal', 'associate-subtotal'],
            },
          ]
        })(),
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
    noteSectionId: '七、1',
    noteSectionTitle: '在其他主体中的权益',
    guidance: [
      '源模板将“集团构成、重要非全资子公司、主要财务信息、重大限制、结构化主体支持、未丧失控制权交易”分别披露。',
      '蓝色提示及示例仅用于编制判断，不作为附注正文同步。',
    ],
    tables: [
      {
        id: 'subsidiary-composition',
        title: '（1）企业集团的构成',
        templateTableKey: '企业集团的构成',
        labelHeader: '子公司名称',
        sourceRows: 'A28:G39',
        columns: subsidiaryBasicColumns,
        rows: blankRows(
          'subsidiary',
          dynamicRowCount(1),
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
        templateTableKey: '重要的非全资子公司',
        labelHeader: '子公司名称',
        sourceRows: 'A47:E55',
        columns: minorityColumns,
        rows: blankRows('minority-subsidiary', dynamicRowCount(1), minorityColumns),
        dynamic: true,
        maxRows: 30,
      },
      {
        id: 'minority-closing-balance',
        title: '（3）重要非全资子公司主要财务信息—期末数',
        templateTableKey: '重要非全资子公司主要财务信息—期末数',
        labelHeader: '子公司名称',
        sourceRows: 'A56:G64',
        columns: balanceClosingColumns,
        rows: blankRows('minority-closing', dynamicRowCount(1), balanceClosingColumns),
        dynamic: true,
        maxRows: 30,
      },
      {
        id: 'minority-opening-balance',
        title: '续（1）—期初数',
        templateTableKey: '续（1）',
        labelHeader: '子公司名称',
        sourceRows: 'A65:G72',
        columns: balanceOpeningColumns,
        rows: blankRows('minority-opening', dynamicRowCount(1), balanceOpeningColumns),
        dynamic: true,
        maxRows: 30,
      },
      {
        id: 'minority-results',
        title: '续（2）—本期及上期发生额',
        templateTableKey: '续（2）',
        labelHeader: '子公司名称',
        sourceRows: 'A73:I81',
        columns: resultColumns,
        rows: blankRows('minority-results', dynamicRowCount(1), resultColumns),
        dynamic: true,
        maxRows: 30,
      },
      {
        id: 'ownership-change-impact',
        title: '（6）未丧失控制权的所有者权益份额变动影响',
        templateTableKey: '未丧失控制权的所有者权益份额变动影响',
        // 🔴 源 A96 原文是「项  目」（**两个空格**）—— 必须逐字带上（R4.1/R4.4）。
        // 缺省回退值 `'项目'`（无空格）会让契约守卫 P5（labelHeader ↔ seed headers[0]）打红：
        // seed 侧 `headers[0]` 逐字保留了源原文，而 `facts.label_header` 经 `_norm()` 去掉
        // 全部空白 ⇒ 边①/边③ 对这类差异**结构上不可见**，只有 P5 能抓到。
        labelHeader: '项  目',
        sourceRows: 'A95:G108',
        columns: companyColumnsFor(OWNERSHIP_CHANGE_SLOT_DEFAULT_NAMES),
        slotConfig: { slot: OWNERSHIP_CHANGE_SLOT },
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
          companyColumnsFor(OWNERSHIP_CHANGE_SLOT_DEFAULT_NAMES),
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
    noteSectionId: '七、1',
    noteSectionTitle: '在其他主体中的权益',
    tables: [
      {
        id: 'important-jv-associate',
        title: '（1）重要的合营企业或联营企业',
        templateTableKey: '重要的合营企业或联营企业',
        labelHeader: '合营企业或联营企业名称',
        sourceRows: 'A111:G124',
        columns: investeeBasicColumns,
        rows: blankRows(
          'important-jv-associate',
          dynamicRowCount(1),
          investeeBasicColumns,
          index => `被投资单位基本信息G7-4 第${index < 5 ? 23 + index : 24 + index}行`,
        ),
        dynamic: true,
        maxRows: 50,
      },
      {
        id: 'important-jv-balance',
        title: '（2）重要合营企业主要财务信息—资产负债及权益法调节',
        templateTableKey: '重要合营企业主要财务信息',
        // 🔴 源 A132 原文是「项 目」（**一个空格**）—— 与联营表 A169 同为单空格，
        // 但与本 sheet 另外 4 张表的「项  目」（双空格）不同。R4.4 明确禁止统一，逐表取原文。
        labelHeader: '项 目',
        sourceRows: 'A132:C151',
        columns: jointVentureFsColumns,
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
          jointVentureFsColumns,
          '被投资单位财务信息（合营、联营）G7-5',
        )),
      },
      {
        id: 'important-jv-results',
        title: '续：重要合营企业本期及上期经营成果',
        templateTableKey: '续：重要合营企业本期及上期经营成果',
        // 🔴 源 A153 原文是「项  目」（双空格）；注意上一张合营表 A132 是**单**空格。
        labelHeader: '项  目',
        sourceRows: 'A152:C163',
        columns: jointVenturePlColumns,
        rows: metricRows(
          'important-jv-results',
          ['营业收入', '财务费用', '所得税费用', '净利润', '终止经营的净利润', '其他综合收益', '综合收益总额', '本期收到的股利'],
          jointVenturePlColumns,
          '被投资单位财务信息（合营、联营）G7-5',
        ),
      },
      {
        id: 'important-associate-balance',
        title: '（3）重要联营企业主要财务信息—资产负债及权益法调节',
        templateTableKey: '重要联营企业主要财务信息',
        // 🔴 源 A169 原文是「项 目」（**一个空格**）。
        labelHeader: '项 目',
        sourceRows: 'A165:G187',
        columns: associateMatrixColumnsFor(
          IMPORTANT_ASSOCIATE_SLOT_DEFAULT_NAMES,
          IMPORTANT_ASSOCIATE_FS_SUB,
        ),
        slotConfig: { slot: IMPORTANT_ASSOCIATE_SLOT, sub: IMPORTANT_ASSOCIATE_FS_SUB },
        // 🔴 Property 12：源模板 R171:R187 为 17 行，不含「其中：现金和现金等价物」
        // （该行只在合营表 R135 出现，18 行）—— 联营表禁复制合营表行集。
        rows: annotateEquityBridgeSources(metricRows(
          'important-associate-balance',
          [
            '流动资产',
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
          associateMatrixColumnsFor(
            IMPORTANT_ASSOCIATE_SLOT_DEFAULT_NAMES,
            IMPORTANT_ASSOCIATE_FS_SUB,
          ),
          '被投资单位财务信息（合营、联营）G7-5',
        )),
      },
      {
        id: 'important-associate-results',
        title: '续：重要联营企业本期及上期经营成果',
        templateTableKey: '续：重要联营企业本期及上期经营成果',
        // 🔴 源 A189 原文是「项  目」（双空格）。
        labelHeader: '项  目',
        sourceRows: 'A188:G197',
        columns: associateMatrixColumnsFor(
          IMPORTANT_ASSOCIATE_SLOT_DEFAULT_NAMES,
          IMPORTANT_ASSOCIATE_PL_SUB,
        ),
        slotConfig: { slot: IMPORTANT_ASSOCIATE_SLOT, sub: IMPORTANT_ASSOCIATE_PL_SUB },
        rows: metricRows(
          'important-associate-results',
          ['营业收入', '净利润', '终止经营的净利润', '其他综合收益', '综合收益总额', '本期收到的股利'],
          associateMatrixColumnsFor(
            IMPORTANT_ASSOCIATE_SLOT_DEFAULT_NAMES,
            IMPORTANT_ASSOCIATE_PL_SUB,
          ),
          '被投资单位财务信息（合营、联营）G7-5',
        ),
      },
      {
        id: 'unimportant-aggregate',
        title: '（4）其他不重要合营企业和联营企业的汇总财务信息',
        templateTableKey: '其他不重要合营企业和联营企业的汇总财务信息',
        // 🔴 源 A200 原文是「项  目」（双空格）。
        labelHeader: '项  目',
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
        templateTableKey: '对合营企业或联营企业发生超额亏损的分担额',
        labelHeader: '被投资单位名称',
        sourceRows: 'A220:D232',
        columns: excessLossesColumns,
        rows: (() => {
          const excessColumns = excessLossesColumns
          const jv = blankRowsWithIds(
            'el-jv', dynamicRowCount(1), excessColumns,
            index => `未确认投资损失测试表G7-16 第${12 + index}行`,
          )
          const assoc = blankRowsWithIds(
            'el-assoc', dynamicRowCount(1), excessColumns,
            index => `未确认投资损失测试表G7-16 第${17 + index}行`,
          )
          return [
            groupRow('el-jv-group', '合营企业', excessColumns),
            ...jv.rows,
            {
              id: 'el-jv-subtotal',
              label: '小计',
              values: valuesFor(excessColumns),
              kind: 'subtotal',
              sumRows: jv.ids,
            },
            groupRow('el-assoc-group', '联营企业', excessColumns),
            ...assoc.rows,
            {
              id: 'el-assoc-subtotal',
              label: '小计',
              values: valuesFor(excessColumns),
              kind: 'subtotal',
              sumRows: assoc.ids,
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
    noteSectionId: '七、1',
    noteSectionTitle: '在其他主体中的权益',
    tables: [
      {
        id: 'joint-operations',
        title: '重要共同经营基本情况',
        templateTableKey: '重要的共同经营',
        labelHeader: '共同经营名称',
        sourceRows: 'A235:F240',
        columns: jointOperationColumns,
        rows: blankRows(
          'joint-operation',
          dynamicRowCount(1),
          jointOperationColumns,
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

/** 各 `slot` 的初始默认实体名（缺省态取值参考，仅在 `state.entitySlots` 未声明该 slot 时生效）。 */
const G7_LISTED_DEFAULT_SLOT_NAMES: Record<string, string[]> = {
  [OWNERSHIP_CHANGE_SLOT]: OWNERSHIP_CHANGE_SLOT_DEFAULT_NAMES,
  [IMPORTANT_ASSOCIATE_SLOT]: IMPORTANT_ASSOCIATE_SLOT_DEFAULT_NAMES,
}

/**
 * 解析某表的**有效**列集：无 `slotConfig` 时原样返回 `table.columns`（静态表）；
 * 有 `slotConfig` 时按 `entitySlots[slot]`（缺省回退该 slot 的默认实体名）动态生成
 * （Task 5.6，Property 18 —— 列数随 `names` 长度变化，`key` 改名后保持不变）。
 *
 * 无 `sub` 子列 → 单值列（无跨期分组，`flatCols`）；有 `sub` → 每实体两子列按实体名分组
 * （两级表头）。两种形态与 `companyColumnsFor` / `associateMatrixColumnsFor` 生成规则一致，
 * 泛化实现避免新增槎位时还要各写一份 if 分支。
 */
export function resolveG7ListedTableColumns(
  table: G7DisclosureTable,
  entitySlots?: Record<string, string[]>,
): G7DisclosureColumn[] {
  const slotConfig = table.slotConfig
  if (!slotConfig) return table.columns
  const names = entitySlots?.[slotConfig.slot] ?? G7_LISTED_DEFAULT_SLOT_NAMES[slotConfig.slot] ?? []
  const slotCols = buildG7SlotColumns(slotConfig.slot, names, slotConfig.sub)
  if (!slotConfig.sub?.length) {
    return flatCols(slotCols.map(c => ({
      key: c.key,
      label: c.entityName,
      type: 'number' as G7DisclosureColumnType,
    })))
  }
  return groupedCols(slotCols.map(c => [
    c.key,
    c.subLabel ?? '',
    'number' as G7DisclosureColumnType,
    c.entityName,
  ]))
}

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
  const entitySlots: Record<string, string[]> = {}
  for (const [slot, names] of Object.entries(G7_LISTED_DEFAULT_SLOT_NAMES)) {
    entitySlots[slot] = [...names]
  }
  return { version: 2, tables, texts, previouslySyncedTables: {}, entitySlots }
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
      // 🔴 行对象的标签键必须与 `buildG7ListedColumns()` 标签列的 `key` **逐字一致**，
      //    否则投影器 `_project_row` 取 `r.get(label_key)` 拿不到值 ⇒ **整表行名变空**。
      //    改造前这里是 `项目: row.label` 而列 key 已改成 `'label'` ⇒ 两侧不自洽
      //    （实测该 skew 会让存量行 8/7/12/10 行的行名全部投影成 `''`）。
      //    这条不变式由守卫 `g7ColumnThreeWayAlignment.spec.ts` 的
      //    「行构造标签键 ≡ 标签列 key」断言钉死。
      label: row.label,
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
 *
 * `entitySlots` 缺省时用各槎位默认实体名解析动态列（覆盖率 sweep 用空入参调用要求
 * 非空列集 — Property 6）；传入实际 `state.entitySlots` 则按用户增删改名后的列集输出，
 * 保证同步载荷与 seed 路径列头一致（Property 9 双向表态）。
 */
export function buildG7ListedColumns(
  entitySlots?: Record<string, string[]>,
): Record<string, import('../../composables/disclosureColumnDefs').ColumnDef[]> {
  const result: Record<string, import('../../composables/disclosureColumnDefs').ColumnDef[]> = {}
  for (const section of G7_LISTED_DISCLOSURE_SECTIONS) {
    for (const table of section.tables ?? []) {
      const key = table.templateTableKey ?? table.title
      const columns = resolveG7ListedTableColumns(table, entitySlots)
      // 🔴 flat/group 必须在此处透传（同步载荷）与模板 seed 两处都表态（Property 9）：
      // 只加一侧会让另一路径继续被 `_infer_groups_from_headers` 前缀推断出凭空父表头。
      const hasGroup = columns.some(c => c.group)
      const labelText = table.labelHeader ?? '项目'
      // 🔴 标签列 key 用平台惯例 `'label'`（不是中文字面量 `'项目'`）—— 裁决依据：
      //   ① 平台 266 个标签列定义里 241 个（91%）用 `'label'`，跨 70 个文件；
      //      硬编码 `'项目'` 全平台仅 7 处且全在 G 循环，属少数派偏离；
      //   ② 中文字面量当 key 违反平台「禁硬编码」取向；
      //   ③ 零数据风险：`note_sub_table_projector._project_row` 有双向兜底
      //      （L67-68 任意标签 key ← 规范 `label`；L204-205 标签值为空 → 回退 `label`），
      //      且标签列不承载数据（行名真源是 `rows[].label`，`_cell_meta`/`_cell_modes`
      //      按 value 列索引、标签列不算数据列）。
      // `label: labelText` 是**显示文字**（与 key 无关），`table.labelHeader ?? '项目'` 不动。
      // `is_label: true` 必须保留：投影器靠它选标签列并**跳过它**算 group 索引（header_idx 从 1 起），
      // 去掉会让 group 的 start 整体偏移一位。
      result[key] = [
        { key: 'label', label: labelText, is_label: true, ...(hasGroup ? {} : { flat: true }) },
        ...columns.map((c) => ({
          key: c.key,
          label: c.label,
          format: (c.type === 'number' ? 'amount' : c.type === 'percent' ? 'percent' : 'text') as
            'amount' | 'percent' | 'text',
          ...(c.group ? { group: c.group } : {}),
          ...(c.flat ? { flat: true } : {}),
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
      const columns = resolveG7ListedTableColumns(table, state.entitySlots)
      result[key] = materializeG7ListedRows(state.tables[table.id] ?? [], columns)
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

/**
 * 按目标附注章节聚合同步载荷（源模板一张披露 sheet 混排 `五、18` 与 `七、1` 两章）。
 *
 * 🔴 R8.1：旧实现把 15 张表全推 `五、18`，其中 14 张（子公司权益/合营联营权益/共同经营）
 * 在该章节是孤儿表。改为按 `section.noteSectionId` 分组，对齐国企侧已有的
 * `buildG7SoeSyncPayloads` 范式；调用方改用 `sync-batch-from-workpaper`。
 *
 * `_note_texts` 按其所属 section 归入对应 payload（而非全部塞进第一个），
 * 且放在 `subTableData` 内（`_` 前缀元数据键，不是顶层字段）。
 */
export function buildG7ListedSyncPayloads(
  state: G7ListedDisclosureState,
): G7ListedSyncPayload[] {
  const SHEET_NAME = '附注披露信息（上市公司）'
  const byNote = new Map<string, G7ListedSyncPayload>()

  function ensure(section: G7DisclosureSection): G7ListedSyncPayload {
    const existing = byNote.get(section.noteSectionId)
    if (existing) return existing
    const created: G7ListedSyncPayload = {
      noteSectionId: section.noteSectionId,
      noteSectionTitle: section.noteSectionTitle,
      sheetName: SHEET_NAME,
      subTableData: {},
    }
    byNote.set(section.noteSectionId, created)
    return created
  }

  for (const section of G7_LISTED_DISCLOSURE_SECTIONS) {
    const payload = ensure(section)
    for (const table of section.tables ?? []) {
      const key = table.templateTableKey ?? table.title
      payload.subTableData[key] = materializeG7ListedRows(
        state.tables[table.id] ?? [],
        resolveG7ListedTableColumns(table, state.entitySlots),
      )
    }
    const texts = (section.narratives ?? [])
      .map(narrative => ({
        section: narrative.id,
        title: narrative.title,
        text: state.texts[narrative.id] ?? '',
      }))
      .filter(item => item.text.trim())
    if (texts.length) {
      const existingTexts = (payload.subTableData._note_texts as unknown[] | undefined) ?? []
      payload.subTableData._note_texts = [...existingTexts, ...texts]
    }
  }

  // 动态区（`dynamic: true`）用户可增删行，但表本身固定存在不会被删表 —— 本模型无
  // 「审计师自由命名的整张动态表」（对齐 D2 组合分表那种场景），故差集只需按章节
  // 求「上次推送 − 本次推送」，不必额外声明命名空间前缀。
  for (const payload of byNote.values()) {
    const pushed = dataTableNames(payload.subTableData)
    const removed = buildRemovedTableKeys({
      previouslySynced: state.previouslySyncedTables?.[payload.noteSectionId],
      pushed,
    })
    if (removed.length) payload.subTableData._removed_table_keys = removed
  }

  return Array.from(byNote.values())
}

/**
 * 同步成功后调用：把本次各章节实际推送的表名记入 `previouslySyncedTables`，
 * 供下次同步计算 `_removed_table_keys` 差集。返回新状态片段（浅合并进 `state`）。
 */
export function markG7ListedSynced(
  state: G7ListedDisclosureState,
  payloads: G7ListedSyncPayload[],
): Record<string, string[]> {
  const next: Record<string, string[]> = { ...(state.previouslySyncedTables ?? {}) }
  for (const payload of payloads) {
    next[payload.noteSectionId] = dataTableNames(payload.subTableData)
  }
  return next
}
