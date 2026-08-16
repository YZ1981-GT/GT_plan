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
import { attachRemovedTableKeys, dataTableNames } from '../../composables/disclosureSyncedTables'
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
  /** 标签列头文字（须与 note_template headers[0] 逐字一致）。缺省 '项目'。 */
  labelHeader?: string
  /** 静态列（无 slotConfig 时的最终列集；有 slotConfig 时仅作初始态取值参考） */
  columns: G7DisclosureColumn[]
  rows: G7DisclosureRow[]
  description?: string
  dynamic?: boolean
  maxRows?: number
  /**
   * 声明该表「按被投资单位/子公司横向展开」，列集改由 `state.entitySlots[slot]`
   * 动态生成（Task 5.6，Property 18），不再写死列数。
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
  /**
   * 上次同步成功时按章节推送的数据子表名清单（`{noteSectionId: string[]}`）。
   * 供 `buildG7SoeSyncPayloads` 计算 `_removed_table_keys` 差集（Task 5.5）。
   */
  previouslySyncedTables?: Record<string, string[]>
  /**
   * 动态槎位实体名清单（`{slot: string[]}`），供带 `slotConfig` 的表生成动态列
   * （Task 5.6）。缺省用各槎位默认实体名。
   */
  entitySlots?: Record<string, string[]>
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

/**
 * 带两级表头分组的列定义：`(key, label, type, group|undefined[, width])`。
 *
 * 第 5 位 `width` 为**可选**（additive）—— 既有 4 元组调用方行为逐字不变
 * （`width` 为 `undefined` 时与改造前产出的对象等价）。加它是为了让原本用
 * `flatCols(cols([...]))`（支持宽度）的表在补 `group` 后不必丢掉列宽。
 */
function groupedCols(
  items: Array<[string, string, G7DisclosureColumnType, string | undefined, number?]>,
): G7DisclosureColumn[] {
  return items.map(([key, label, type, group, width]) => ({ key, label, type, group, width }))
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

// 🔴 行标识列是「序号」、`企业名称` 是**第 1 个数据列**（源 A9:M9 共 12 个数据列）。
// 改造前漏了 `name` 列 ⇒ 运行时 11 列 vs 源 12 列（E 类偏差），且 seed 侧有 `name`
// 而运行时没有，两侧永久错位（C 类偏差）。`labelHeader: '序号'` 见表定义处。
//
// 🔴 百分号括号一律**全角**，逐字取源 xlsx（`认缴持股比例（%）`）：改造前用半角
// `(%)`，与源模板不符（D 类偏差）。此前被 E 类掩盖 —— 守卫在列数不等时跳过 label
// 比对（`compareTableTriple` 的 `else` 分支），故补列后 D 类才浮现。
const subsidiaryBasicColumns = flatCols(cols([
  ['name', '企业名称', 'text', 140],
  ['level', '级次', 'text', 80],
  ['enterpriseType', '企业类型', 'text', 100],
  ['registeredPlace', '注册地', 'text', 110],
  ['principalPlace', '主要经营地', 'text', 110],
  ['businessNature', '业务性质', 'text', 110],
  ['paidInCapital', '实收资本', 'number', 120],
  ['subscribedRatio', '认缴持股比例（%）', 'percent', 130],
  ['paidInRatio', '实缴持股比例（%）', 'percent', 130],
  ['votingRights', '享有的表决权（%）', 'percent', 130],
  ['investmentAmount', '投资额', 'number', 120],
  ['acquisitionMethod', '取得方式', 'text', 120],
]))

// 「表决权例外」两张表（A25:H35 表决权不足半数但形成控制 / A37:H52 表决权过半但未形成
// 控制）列结构同构，**只有末列 label 不同**：源 xlsx 分别是「纳入合并范围原因」与
// 「未纳入合并范围原因」。改造前共用一份且写成折衷的「原因说明」，两张表都与源模板不符
// （D 类偏差）⇒ 拆成两份，各自逐字取源。
//
// 🔴 `享有的表决权` 源 xlsx **不带 (%)**（同表「认缴持股比例（%）」才带，且是全角）；
// 改造前统一加了半角 `(%)`。`name`（企业名称）是第 1 个数据列，改造前漏列（E 类）。
function controlExceptionColumnsFor(reasonLabel: string) {
  return flatCols(cols([
    ['name', '企业名称', 'text', 140],
    ['subscribedRatio', '认缴持股比例（%）', 'percent', 130],
    ['votingRights', '享有的表决权', 'percent', 120],
    ['registeredCapital', '注册资本', 'number', 120],
    ['investmentAmount', '投资额', 'number', 120],
    ['level', '级次', 'text', 80],
    ['reason', reasonLabel, 'text', 220],
  ]))
}

/** A25:H35「表决权不足半数但能形成控制」——末列源文为「纳入合并范围原因」。 */
const controlBelowHalfColumns = controlExceptionColumnsFor('纳入合并范围原因')
/** A37:H52「表决权过半但未形成控制」——末列源文为「未纳入合并范围原因」。 */
const noControlAboveHalfColumns = controlExceptionColumnsFor('未纳入合并范围原因')

// 🔴 `name`（企业名称）是源 A55:F55 的第 1 个数据列（共 5 个），改造前漏列（E 类偏差）。
const minorityColumns = flatCols(cols([
  ['name', '企业名称', 'text', 140],
  ['holdingRatio', '少数股东持股比例', 'percent', 130],
  ['currentProfit', '当期归属于少数股东的损益', 'number', 160],
  ['dividend', '当期向少数股东支付的股利', 'number', 160],
  ['closingEquity', '期末累计少数股东权益', 'number', 150],
]))

const currentPriorColumns = flatCols(cols([
  ['current', '期末数/本期发生额', 'number', 140],
  ['prior', '期初数/上期发生额', 'number', 140],
]))

/** 「非全资子公司主要财务信息」槎位（源模板按重要非全资子公司横向展开，字面 `公司1..N`）。 */
const MINORITY_FS_SLOT = 'minority-fs-company'
const MINORITY_FS_SLOT_DEFAULT_NAMES = ['公司1', '公司2', '公司3', '公司4', '公司5']
// 🔴 子列 label 逐字取源模板 A61:L73（`期末数/本期发生额` / `期初数/上期发生额`），
// 改造前简写成 `期末/本期`。列 key 不变（`current`/`prior`）。
const MINORITY_FS_SUB: G7SlotSubColumn[] = [
  { key: 'current', label: '期末数/本期发生额' },
  { key: 'prior', label: '期初数/上期发生额' },
]

/** 由槎位实体名生成矩阵列（每实体 期末/本期·期初/上期 两子列，按实体名分组）。 */
function multiCompanyCurrentPriorColumnsFor(names: readonly string[]): G7DisclosureColumn[] {
  const slotCols = buildG7SlotColumns(MINORITY_FS_SLOT, names, MINORITY_FS_SUB)
  return groupedCols(slotCols.map(c => [
    c.key,
    c.subLabel ?? '',
    'number' as G7DisclosureColumnType,
    c.entityName,
  ]))
}

// 🔴 `name`（企业名称）是源 A78:G78 的第 1 个数据列（共 6 个），改造前漏列（E 类偏差）；
// 比例两列的括号源文是**全角**（`持股比例（%）`），改造前写成半角（D 类偏差）。
const formerSubsidiaryColumns = flatCols(cols([
  ['name', '企业名称', 'text', 140],
  ['registeredPlace', '注册地', 'text', 110],
  ['businessNature', '业务性质', 'text', 110],
  ['holdingRatio', '持股比例（%）', 'percent', 110],
  ['votingRights', '表决权比例（%）', 'percent', 120],
  ['reason', '本期不再成为子公司的原因', 'text', 220],
]))

/** 「本期出售的子公司出售日的财务状况」槎位（源模板按出售子公司横向展开，字面 `公司1..N`）。 */
const SOLD_FS_POSITION_SLOT = 'sold-fs-position-company'
const SOLD_FS_POSITION_SLOT_DEFAULT_NAMES = ['公司1', '公司2']
const SOLD_FS_POSITION_SUB: G7SlotSubColumn[] = [
  { key: 'saleDate', label: '出售日' },
  { key: 'opening', label: '期初余额' },
]

function soldFsPositionColumnsFor(names: readonly string[]): G7DisclosureColumn[] {
  const slotCols = buildG7SlotColumns(SOLD_FS_POSITION_SLOT, names, SOLD_FS_POSITION_SUB)
  return groupedCols(slotCols.map(c => [
    c.key,
    c.subLabel ?? '',
    'number' as G7DisclosureColumnType,
    c.entityName,
  ]))
}

/** 「本期出售的子公司出售日的经营成果」槎位（源模板字面 `A~E公司`，本质仍是横向展开）。 */
const SOLD_FS_RESULT_SLOT = 'sold-fs-result-company'
const SOLD_FS_RESULT_SLOT_DEFAULT_NAMES = ['A公司', 'B公司', 'C公司', 'D公司', 'E公司']
// 🔴 子列 label 逐字取源模板（`本年年初-出售日`，用短横不是「至」）。列 key 不变。
const SOLD_FS_RESULT_SUB: G7SlotSubColumn[] = [
  { key: 'current', label: '本年年初-出售日' },
  { key: 'prior', label: '上年发生额' },
]

function soldFsResultColumnsFor(names: readonly string[]): G7DisclosureColumn[] {
  const slotCols = buildG7SlotColumns(SOLD_FS_RESULT_SLOT, names, SOLD_FS_RESULT_SUB)
  return groupedCols(slotCols.map(c => [
    c.key,
    c.subLabel ?? '',
    'number' as G7DisclosureColumnType,
    c.entityName,
  ]))
}

const newEntityColumns = flatCols(cols([
  ['closingNetAssets', '期末净资产', 'number', 130],
  ['currentNetProfit', '本期净利润', 'number', 130],
]))

/**
 * 同一控制下企业合并列 —— **两级表头**（源 `附注披露信息（国企）` A120:J126）。
 *
 * 🔴 源 xlsx 合并区实证：末 4 列共享父表头「本年初至合并日的相关情况」，
 * 其叶子列名逐字为 `收入` / `净利润` / `现金净增加额` / `经营活动现金流量净额`。
 * 改造前把父表头**压进 label 前缀**（`本年初至合并日-收入`）且整表标 `flat` ——
 * 后者只是「丢了 group」的症状（`buildG7SoeColumns` 的
 * `...(hasGroup ? {} : { flat: true })` 自动加），补 group 后 flat 随之消失。
 * 列 key 一律不动（`revenue` / `netProfit` 等），只动 group 与 label。
 */
const COMMON_CONTROL_GROUP = '本年初至合并日的相关情况'

const commonControlColumns = groupedCols([
  ['consolidationDate', '合并日', 'text', undefined, 110],
  ['bookNetAssets', '账面净资产', 'number', undefined, 120],
  ['consideration', '交易对价', 'number', undefined, 120],
  ['ultimateController', '实际控制人', 'text', undefined, 120],
  ['revenue', '收入', 'number', COMMON_CONTROL_GROUP, 140],
  ['netProfit', '净利润', 'number', COMMON_CONTROL_GROUP, 140],
  ['cashIncrease', '现金净增加额', 'number', COMMON_CONTROL_GROUP, 120],
  ['operatingCashFlow', '经营活动现金流量净额', 'number', COMMON_CONTROL_GROUP, 160],
])

/**
 * 非同一控制下企业合并列 —— **两级表头**（源 `附注披露信息（国企）` A127:M136）。
 *
 * 🔴 源 xlsx 合并区实证：第 5~7 列共享父表头「购买日被购买方」，叶子列名逐字为
 * `账面净资产总额` / `可辨认净资产公允价值总额金额` / `可辨认净资产公允价值总额确定方法`；
 * 其余列 rowspan=2（不给 group）。另 4 处 label 需逐字取源文（比例列源文不带 `(%)`、
 * 购买日至期末三列源文带「被购买方的」）。列 key 一律不动。
 */
const NON_COMMON_CONTROL_GROUP = '购买日被购买方'

const nonCommonControlColumns = groupedCols([
  ['purchaseDate', '购买日', 'text', undefined, 110],
  ['purchaseDateBasis', '购买日的确定依据', 'text', undefined, 150],
  ['preHolding', '购买日前持有被购买方权益比例', 'percent', undefined, 150],
  [
    'atCombinationHolding',
    '形成合并时持有的被购买方权益比例（不含合并后的股权增减）',
    'percent',
    undefined,
    160,
  ],
  ['bookNetAssets', '账面净资产总额', 'number', NON_COMMON_CONTROL_GROUP, 130],
  ['fvIdentifiable', '可辨认净资产公允价值总额金额', 'number', NON_COMMON_CONTROL_GROUP, 160],
  ['fvMethod', '可辨认净资产公允价值总额确定方法', 'text', NON_COMMON_CONTROL_GROUP, 140],
  ['consideration', '交易对价', 'number', undefined, 120],
  ['goodwill', '形成商誉', 'number', undefined, 120],
  ['postRevenue', '购买日至期末被购买方的收入', 'number', undefined, 140],
  ['postProfit', '购买日至期末被购买方的净利润', 'number', undefined, 140],
  ['postCashFlow', '购买日至期末被购买方的现金流量', 'number', undefined, 150],
])

/**
 * 吸收合并列 —— **两级表头**。
 *
 * 🔴 源模板 `附注披露信息（国企）` A139:F172 的合并区实证：
 * `A139:B140` 标签列「吸收合并的类型」、`C139:D139`「并入的主要资产」下辖
 * `C140='项目'` / `D140='金额'`、`E139:F139`「并入的主要负债」下辖 `E140/F140` 同名。
 * 附注模板 seed 亦已按此落地
 * （`_column_groups=[{并入的主要资产,1,2},{并入的主要负债,3,2}]`）。
 *
 * 改造前这里是 `flatCols` + label 拼接（`并入主要资产-项目`）= **压扁两级表头**，
 * 推送后附注列头会从两级退化成单级（违反平台铁律「同步不得压扁列结构」）。
 * 列 key 保持不变，只改 label 与 group ⇒ 既有已录数据不丢。
 */
const _ABSORB_ASSET_GROUP = '并入的主要资产'
const _ABSORB_LIABILITY_GROUP = '并入的主要负债'
const absorptionColumns = groupedCols([
  ['assetItem', '项目', 'text', _ABSORB_ASSET_GROUP],
  ['assetAmount', '金额', 'number', _ABSORB_ASSET_GROUP],
  ['liabilityItem', '项目', 'text', _ABSORB_LIABILITY_GROUP],
  ['liabilityAmount', '金额', 'number', _ABSORB_LIABILITY_GROUP],
])

/** 「母公司在子公司的所有者权益份额发生变化的情况」槎位（源模板字面 `公司1..N`）。 */
const OWNERSHIP_CHANGE_SLOT = 'ownership-change-company'
const OWNERSHIP_CHANGE_SLOT_DEFAULT_NAMES = ['公司1', '公司2', '公司3']

function ownershipChangeImpactColumnsFor(names: readonly string[]): G7DisclosureColumn[] {
  const slotCols = buildG7SlotColumns(OWNERSHIP_CHANGE_SLOT, names)
  return flatCols(slotCols.map(c => ({
    key: c.key,
    label: c.entityName,
    type: 'number' as G7DisclosureColumnType,
  })))
}

const classificationColumns = flatCols(cols([
  ['opening', '年初余额', 'number', 120],
  ['increase', '本期增加', 'number', 120],
  ['decrease', '本期减少', 'number', 120],
  ['closing', '期末余额', 'number', 120],
]))

/** 「长期股权投资明细」本期增减变动（8 子列，与上市侧 `movementColumns` 同分组名）。 */
const MOVEMENT_GROUP = '本期增减变动'

const movementColumns = groupedCols([
  ['investmentCost', '投资成本', 'number', undefined],
  ['opening', '期初余额', 'number', undefined],
  ['addition', '追加投资', 'number', MOVEMENT_GROUP],
  ['reduction', '减少投资', 'number', MOVEMENT_GROUP],
  ['equityProfit', '权益法下确认的投资损益', 'number', MOVEMENT_GROUP],
  ['oci', '其他综合收益调整', 'number', MOVEMENT_GROUP],
  ['otherEquity', '其他权益变动', 'number', MOVEMENT_GROUP],
  ['dividend', '宣告发放现金股利或利润', 'number', MOVEMENT_GROUP],
  ['impairment', '计提减值准备', 'number', MOVEMENT_GROUP],
  ['other', '其他', 'number', MOVEMENT_GROUP],
  ['closing', '期末余额', 'number', undefined],
  ['closingImpairment', '减值准备期末余额', 'number', undefined],
])

const jvFsColumns = flatCols(cols([
  ['current', '期末数', 'number', 120],
  ['prior', '期初数', 'number', 120],
]))

const jvPlColumns = flatCols(cols([
  ['current', '本期发生额', 'number', 120],
  ['prior', '上期发生额', 'number', 120],
]))

/** 「重要联营企业主要财务信息」矩阵槎位（源模板按合营企业2/联营企业1/2 横向展开）。 */
const ASSOCIATE_FS_SLOT = 'associate-fs-company'
const ASSOCIATE_FS_SLOT_DEFAULT_NAMES = ['合营企业2', '联营企业1', '联营企业2']
// 🔴 子列 label 逐字取源模板 `附注披露信息（国企）` r258（`期末数` / `期初数`），
// 不得简写成「期末/期初」—— 附注模板 seed 与本处必须一致，否则推送后列头从
// 正确写法退化成简写（seed 侧由 `fix_note_g7_soe_structure.py` 保证）。
const ASSOCIATE_FS_SUB: G7SlotSubColumn[] = [
  { key: 'current', label: '期末数' },
  { key: 'prior', label: '期初数' },
]

function associateFsMatrixColumnsFor(names: readonly string[]): G7DisclosureColumn[] {
  const slotCols = buildG7SlotColumns(ASSOCIATE_FS_SLOT, names, ASSOCIATE_FS_SUB)
  return groupedCols(slotCols.map(c => [
    c.key,
    c.subLabel ?? '',
    'number' as G7DisclosureColumnType,
    c.entityName,
  ]))
}

/** 「续：重要联营企业经营成果」矩阵槎位（同上，子列为本期/上期）。 */
const ASSOCIATE_PL_SLOT = 'associate-pl-company'
const ASSOCIATE_PL_SLOT_DEFAULT_NAMES = ['合营企业2', '联营企业1', '联营企业2']
// 🔴 子列 label 逐字取源模板 r272（`本期发生额` / `上期发生额`），同 FS 表不得简写。
const ASSOCIATE_PL_SUB: G7SlotSubColumn[] = [
  { key: 'current', label: '本期发生额' },
  { key: 'prior', label: '上期发生额' },
]

function associatePlMatrixColumnsFor(names: readonly string[]): G7DisclosureColumn[] {
  const slotCols = buildG7SlotColumns(ASSOCIATE_PL_SLOT, names, ASSOCIATE_PL_SUB)
  return groupedCols(slotCols.map(c => [
    c.key,
    c.subLabel ?? '',
    'number' as G7DisclosureColumnType,
    c.entityName,
  ]))
}

const aggregateColumns = flatCols(cols([
  ['current', '本期数', 'number', 120],
  ['prior', '上期数', 'number', 120],
]))

const unrecognizedLossColumns = flatCols(cols([
  ['priorCumulative', '前期累积未确认的损失份额', 'number', 170],
  ['currentUnrecognized', '本期未确认的损失份额（或本期实现净利润的分享额）', 'number', 220],
  ['closingCumulative', '本期末累积未确认的损失份额', 'number', 170],
]))

/**
 * 未纳入合并范围结构化主体的账面价值与最大损失敞口列 —— **三段两级表头**
 * （源 `附注披露信息（国企）` A323:G328）。
 *
 * 🔴 源 xlsx 合并区实证：`发起`（1 列，叶子 `规模`）/ `期末数`（2 列，叶子
 * `账面价值` / `最大损失敞口`）/ `期初数`（2 列，同名叶子）；`列报项目` rowspan=2
 * 不给 group。改造前把父表头压进 label 前缀（`发起规模` / `期末账面价值`）并整表标
 * `flat` —— 后者是「丢了 group」的症状。列 key 一律不动。
 *
 * 🔴 期末/期初两段的叶子 label **有意同名**（`账面价值` / `最大损失敞口`），靠父表头区分；
 * 不得为「看起来不重复」而加期别前缀（那正是改造前的错误形态）。
 */
const STRUCTURED_GROUP_SPONSOR = '发起'
const STRUCTURED_GROUP_CLOSING = '期末数'
const STRUCTURED_GROUP_OPENING = '期初数'

const structuredExposureColumns = groupedCols([
  ['sponsorScale', '规模', 'text', STRUCTURED_GROUP_SPONSOR, 110],
  ['closingCarrying', '账面价值', 'number', STRUCTURED_GROUP_CLOSING, 130],
  ['closingMaxLoss', '最大损失敞口', 'number', STRUCTURED_GROUP_CLOSING, 140],
  ['openingCarrying', '账面价值', 'number', STRUCTURED_GROUP_OPENING, 130],
  ['openingMaxLoss', '最大损失敞口', 'number', STRUCTURED_GROUP_OPENING, 140],
  ['presentationItem', '列报项目', 'text', undefined, 120],
])

/**
 * 发起人从结构化主体获得的收益及转移资产列 —— **两级表头**
 * （源 `附注披露信息（国企）` A340:E345）。
 *
 * 🔴 源 xlsx 合并区实证：前 3 列共享父表头「当期从结构化主体获得的收益」；
 * 第 2 列叶子 label 源文用**全角**括号 `向结构化主体出售资产的利得（损失）`
 * （改造前写半角），末列 rowspan=2 不给 group。列 key 一律不动。
 */
const SPONSOR_INCOME_GROUP = '当期从结构化主体获得的收益'

const sponsorIncomeColumns = groupedCols([
  ['serviceFee', '服务收费', 'number', SPONSOR_INCOME_GROUP, 120],
  ['assetSaleGain', '向结构化主体出售资产的利得（损失）', 'number', SPONSOR_INCOME_GROUP, 200],
  ['total', '合计', 'number', SPONSOR_INCOME_GROUP, 110],
  ['transferredAssets', '当期向结构化主体转移资产账面价值', 'number', undefined, 200],
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
        labelHeader: '序号',
        sourceRows: 'A9:M19',
        columns: subsidiaryBasicColumns,
        rows: blankRows(
          'subsidiary-basic',
          dynamicRowCount(1),
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
        // 🔴 原值 '序号' 是**表头首格泄漏名**，且与下一张表撞名 ⇒ 附注模板无此表名
        // → 推送出孤儿表（投影器只渲染模板里存在的表名），两张表还会互相覆盖丢整表。
        templateTableKey: '母公司拥有被投资单位表决权不足半数但能对被投资单位形成控制的原因',
        labelHeader: '序号',
        sourceRows: 'A25:H35',
        columns: controlBelowHalfColumns,
        rows: blankRows(
          'control-below-half',
          dynamicRowCount(1),
          controlBelowHalfColumns,
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
        // 🔴 原值 '序号'（表头首格泄漏名），与上一张表撞名，见上方说明
        templateTableKey:
          '母公司直接或通过其他子公司间接拥有被投资单位半数以上的表决权但未能对其形成控制的原因',
        labelHeader: '序号',
        sourceRows: 'A37:H52',
        columns: noControlAboveHalfColumns,
        rows: [
          groupRow('nc-jv-group', '合营企业', noControlAboveHalfColumns),
          ...blankRows('nc-jv', dynamicRowCount(1), noControlAboveHalfColumns, index => `G7-4 合营条件筛选 第${23 + index}行`),
          groupRow('nc-assoc-group', '联营企业', noControlAboveHalfColumns),
          ...blankRows('nc-assoc', dynamicRowCount(1), noControlAboveHalfColumns, index => `G7-4 联营条件筛选 第${29 + index}行`),
          groupRow('nc-other-group', '其他', noControlAboveHalfColumns),
          ...blankRows('nc-other', dynamicRowCount(1), noControlAboveHalfColumns),
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
        labelHeader: '序号',
        sourceRows: 'A54:F60',
        columns: minorityColumns,
        rows: blankRows('minority', dynamicRowCount(1), minorityColumns),
        dynamic: true,
        maxRows: 30,
      },
      {
        id: 'minority-financials',
        title: '2、主要财务信息',
        templateTableKey: '主要财务信息',
        // 🔴 源 A62 原文是「项  目」（**两个空格**）—— 必须逐字带上（R4.1/R4.4）。
        // 缺省回退值 `'项目'`（无空格）会让契约守卫 P5（labelHeader ↔ seed headers[0]）打红：
        // seed 侧 `headers[0]` 逐字保留源原文，而 `facts.label_header` 经 `_norm()` 去掉全部
        // 空白 ⇒ 边①/边③ 对这类差异**结构上不可见**，只有 P5 能抓到。
        labelHeader: '项  目',
        sourceRows: 'A61:L73',
        columns: multiCompanyCurrentPriorColumnsFor(MINORITY_FS_SLOT_DEFAULT_NAMES),
        slotConfig: { slot: MINORITY_FS_SLOT, sub: MINORITY_FS_SUB },
        rows: metricRows('minority-fs', minorityFsLabels, multiCompanyCurrentPriorColumnsFor(MINORITY_FS_SLOT_DEFAULT_NAMES)),
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
        labelHeader: '序号',
        sourceRows: 'A77:G83',
        columns: formerSubsidiaryColumns,
        rows: blankRows(
          'former-sub',
          dynamicRowCount(1),
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
        columns: soldFsPositionColumnsFor(SOLD_FS_POSITION_SLOT_DEFAULT_NAMES),
        slotConfig: { slot: SOLD_FS_POSITION_SLOT, sub: SOLD_FS_POSITION_SUB },
        rows: metricRows('sold-position', soldPositionLabels, soldFsPositionColumnsFor(SOLD_FS_POSITION_SLOT_DEFAULT_NAMES)),
      },
      {
        id: 'former-subsidiary-results',
        title: '（3）本期出售的子公司出售日的经营成果',
        // 🔴 原值把「出售日」写成「处置日」，与附注模板表名一字之差 ⇒ 孤儿表
        templateTableKey: '本期出售的子公司出售日的经营成果',
        sourceRows: 'A97:L106',
        columns: soldFsResultColumnsFor(SOLD_FS_RESULT_SLOT_DEFAULT_NAMES),
        slotConfig: { slot: SOLD_FS_RESULT_SLOT, sub: SOLD_FS_RESULT_SUB },
        rows: metricRows('sold-result', soldResultLabels, soldFsResultColumnsFor(SOLD_FS_RESULT_SLOT_DEFAULT_NAMES)),
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
        // 🔴 原值 '公司名称' 是表头首格泄漏名，且与「同一控制下企业合并」撞名 ⇒ 孤儿表 + 互相覆盖
        templateTableKey: '本期新纳入合并范围的主体',
        labelHeader: '公司名称',
        sourceRows: 'A109:D119',
        columns: newEntityColumns,
        rows: blankRows(
          'new-entity',
          dynamicRowCount(1),
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
        // 🔴 原值 '公司名称'（表头首格泄漏名），与「本期新纳入合并范围的主体」撞名，见上方说明
        templateTableKey: '本期发生的同一控制下企业合并情况',
        labelHeader: '公司名称',
        sourceRows: 'A122:J126',
        columns: commonControlColumns,
        rows: blankRows('common-control', dynamicRowCount(1), commonControlColumns),
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
        labelHeader: '被购买方名称',
        sourceRows: 'A129:M134',
        columns: nonCommonControlColumns,
        rows: blankRows('non-common-control', dynamicRowCount(1), nonCommonControlColumns),
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
      // 🔴 源模板 A139:F172 是**一张表 + 两个段标签行**（`A141='同一控制下吸收合并'`、
      // `A157='非同一控制下吸收合并'`，各段下 15 行动态区），附注模板 seed 亦为
      // 单表 12 行（段标签 + 5 空行 ×2）。
      // 改造前这里拆成两张表，且 `templateTableKey` 分别是表头首格泄漏名
      // `吸收合并的类型`（附注模板已把它登记为 alias 正名掉）与**缺省**（回退 title）
      // ⇒ 两张表在附注侧都是孤儿表，推送后永远拿不到数据。
      // 合并后不能只改 key —— 两张表同指一个表名会让后推的覆盖先推的、丢同一控制段。
      {
        id: 'absorption-merger-table',
        title: '（十）本期发生的吸收合并',
        templateTableKey: '本期发生的吸收合并',
        labelHeader: '吸收合并的类型',
        sourceRows: 'A139:F172',
        columns: absorptionColumns,
        rows: [
          groupRow('abs-cc-group', '同一控制下吸收合并', absorptionColumns),
          ...blankRows('abs-cc', dynamicRowCount(1), absorptionColumns),
          groupRow('abs-ncc-group', '非同一控制下吸收合并', absorptionColumns),
          ...blankRows('abs-ncc', dynamicRowCount(1), absorptionColumns),
        ],
        dynamic: true,
        maxRows: 40,
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
        // 🔴 源 A187 原文是「项  目」（双空格）。
        labelHeader: '项  目',
        sourceRows: 'A186:E199',
        columns: ownershipChangeImpactColumnsFor(OWNERSHIP_CHANGE_SLOT_DEFAULT_NAMES),
        slotConfig: { slot: OWNERSHIP_CHANGE_SLOT },
        rows: metricRows('ownership-impact', ownershipImpactLabels, ownershipChangeImpactColumnsFor(OWNERSHIP_CHANGE_SLOT_DEFAULT_NAMES)),
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
        // 🔴 源 A202 原文是「项  目」（双空格）—— 原先写 `'项目'` 属 R4.4 禁止的
        // 「统一成好看的那种」，且 seed 侧 `headers[0]` 一直是双空格 ⇒ P5 打红。
        labelHeader: '项  目',
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
        labelHeader: '被投资单位',
        sourceRows: 'A209:M222',
        columns: movementColumns,
        rows: (() => {
          const jv = blankRowsWithIds('mv-jv', dynamicRowCount(1), movementColumns, () => '合营企业')
          const assoc = blankRowsWithIds('mv-assoc', dynamicRowCount(1), movementColumns, () => '联营企业')
          return [
            groupRow('mv-jv-group', '一、合营企业', movementColumns),
            ...jv.rows,
            groupRow('mv-assoc-group', '二、联营企业', movementColumns),
            ...assoc.rows,
            {
              id: 'mv-total',
              label: '合计',
              values: valuesFor(movementColumns),
              kind: 'total',
              sumRows: [...jv.ids, ...assoc.ids],
            },
          ]
        })(),
        dynamic: true,
        maxRows: 40,
      },
      {
        id: 'important-jv-fs',
        title: '（3）重要合营企业的主要财务信息（划分为持有待售的除外）',
        templateTableKey: '重要合营企业的主要财务信息（划分为持有待售的除外）',
        // 🔴 源 A229 原文是「项 目」（**一个空格**）—— 本 sheet 唯一的单空格表，
        // 其余 7 张是「项  目」（双空格）。R4.4 明确禁止统一，逐表取原文。
        labelHeader: '项 目',
        sourceRows: 'A225:D241',
        columns: jvFsColumns,
        rows: annotateEquityBridgeSources(metricRows('jv-fs', jvFsLabels, jvFsColumns, '被投资单位财务信息（合营、联营）G7-5')),
        description: '“调整事项”包括正商誉、抵消的未实现内部交易损益、减值准备等。',
      },
      {
        id: 'important-jv-pl',
        title: '续：重要合营企业经营成果',
        templateTableKey: '续：重要合营企业本期及上期经营成果',
        // 🔴 源 A243 原文是「项  目」（双空格）；注意上一张合营表 A229 是**单**空格。
        labelHeader: '项  目',
        sourceRows: 'A242:D251',
        columns: jvPlColumns,
        rows: metricRows('jv-pl', jvPlLabels, jvPlColumns, '被投资单位财务信息（合营、联营）G7-5'),
      },
      {
        id: 'important-associate-fs',
        title: '（4）重要联营企业的主要财务信息',
        templateTableKey: '重要联营企业的主要财务信息',
        // 🔴 源 A257 是「项  目」（两个空格）；合营表 A229 才是「项 目」（一个空格）。
        // 改造前此处注释已写明源原文带双空格，值却写成 `'项目'` —— 正是 R4.4 禁止的
        // 「统一成好看的那种」，且注释与值自相矛盾。现按原文逐字带上。
        labelHeader: '项  目',
        sourceRows: 'A253:H269',
        columns: associateFsMatrixColumnsFor(ASSOCIATE_FS_SLOT_DEFAULT_NAMES),
        slotConfig: { slot: ASSOCIATE_FS_SLOT, sub: ASSOCIATE_FS_SUB },
        rows: annotateEquityBridgeSources(metricRows(
          'assoc-fs', associateFsLabels,
          associateFsMatrixColumnsFor(ASSOCIATE_FS_SLOT_DEFAULT_NAMES),
          '被投资单位财务信息（合营、联营）G7-5',
        )),
      },
      {
        id: 'important-associate-pl',
        title: '续：重要联营企业经营成果',
        templateTableKey: '续：重要联营企业本期及上期经营成果',
        // 🔴 源 A271 原文是「项  目」（双空格）。
        labelHeader: '项  目',
        sourceRows: 'A270:H277',
        columns: associatePlMatrixColumnsFor(ASSOCIATE_PL_SLOT_DEFAULT_NAMES),
        slotConfig: { slot: ASSOCIATE_PL_SLOT, sub: ASSOCIATE_PL_SUB },
        rows: metricRows(
          'assoc-pl', associatePlLabels,
          associatePlMatrixColumnsFor(ASSOCIATE_PL_SLOT_DEFAULT_NAMES),
          '被投资单位财务信息（合营、联营）G7-5',
        ),
      },
      {
        id: 'insignificant-aggregate',
        title: '（5）不重要合营企业和联营企业的汇总信息',
        templateTableKey: '不重要合营企业和联营企业的汇总信息',
        // 🔴 源 A280 原文是「项  目」（双空格）。
        labelHeader: '项  目',
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
        labelHeader: '被投资单位名称',
        sourceRows: 'A301:E312',
        columns: unrecognizedLossColumns,
        rows: (() => {
          const jv = blankRowsWithIds(
            'ul-jv', dynamicRowCount(1), unrecognizedLossColumns,
            index => `未确认投资损失测试表G7-16 第${12 + index}行`,
          )
          const assoc = blankRowsWithIds(
            'ul-assoc', dynamicRowCount(1), unrecognizedLossColumns,
            index => `未确认投资损失测试表G7-16 第${17 + index}行`,
          )
          return [
            groupRow('ul-jv-group', '合营企业', unrecognizedLossColumns),
            ...jv.rows,
            {
              id: 'ul-jv-subtotal',
              label: '小计',
              values: valuesFor(unrecognizedLossColumns),
              kind: 'subtotal',
              sumRows: jv.ids,
            },
            groupRow('ul-assoc-group', '联营企业', unrecognizedLossColumns),
            ...assoc.rows,
            {
              id: 'ul-assoc-subtotal',
              label: '小计',
              values: valuesFor(unrecognizedLossColumns),
              kind: 'subtotal',
              sumRows: assoc.ids,
            },
            {
              id: 'ul-total',
              label: '合计',
              values: valuesFor(unrecognizedLossColumns),
              kind: 'total',
              sumRows: ['ul-jv-subtotal', 'ul-assoc-subtotal'],
            },
          ]
        })(),
        dynamic: true,
        maxRows: 40,
      },
      {
        id: 'unconsolidated-structured-exposure',
        title: '未纳入合并范围结构化主体的账面价值与最大损失敞口',
        templateTableKey: '结构化主体权益的账面价值和最大损失敞口',
        sourceRows: 'A323:G328',
        columns: structuredExposureColumns,
        rows: [
          { id: 'se-senior', label: '优先级债券', values: valuesFor(structuredExposureColumns), kind: 'data' },
          { id: 'se-sub', label: '次级债券', values: valuesFor(structuredExposureColumns), kind: 'data' },
          { id: 'se-cds', label: '信用违约互换（负债）', values: valuesFor(structuredExposureColumns), kind: 'data' },
          ...blankRows('se-other', dynamicRowCount(1), structuredExposureColumns),
        ],
        dynamic: true,
        maxRows: 20,
      },
      {
        id: 'sponsor-income',
        title: '发起人从结构化主体获得的收益及转移资产',
        templateTableKey: '结构化主体获得收益及转移资产情况',
        labelHeader: '结构化主体类型',
        sourceRows: 'A340:E345',
        columns: sponsorIncomeColumns,
        rows: (() => {
          const other = blankRowsWithIds('si-other', dynamicRowCount(1), sponsorIncomeColumns)
          return [
            { id: 'si-abs', label: '信用资产证券化', values: valuesFor(sponsorIncomeColumns), kind: 'data' },
            { id: 'si-fund', label: '投资基金', values: valuesFor(sponsorIncomeColumns), kind: 'data' },
            ...other.rows,
            {
              id: 'si-total',
              label: '合计',
              values: valuesFor(sponsorIncomeColumns),
              kind: 'total',
              sumRows: ['si-abs', 'si-fund', ...other.ids],
            },
          ]
        })(),
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

/** 各 `slot` 的初始默认实体名（缺省态取值参考，仅在 `state.entitySlots` 未声明该 slot 时生效）。 */
const G7_SOE_DEFAULT_SLOT_NAMES: Record<string, string[]> = {
  [MINORITY_FS_SLOT]: MINORITY_FS_SLOT_DEFAULT_NAMES,
  [SOLD_FS_POSITION_SLOT]: SOLD_FS_POSITION_SLOT_DEFAULT_NAMES,
  [SOLD_FS_RESULT_SLOT]: SOLD_FS_RESULT_SLOT_DEFAULT_NAMES,
  [OWNERSHIP_CHANGE_SLOT]: OWNERSHIP_CHANGE_SLOT_DEFAULT_NAMES,
  [ASSOCIATE_FS_SLOT]: ASSOCIATE_FS_SLOT_DEFAULT_NAMES,
  [ASSOCIATE_PL_SLOT]: ASSOCIATE_PL_SLOT_DEFAULT_NAMES,
}

/**
 * 解析某表的**有效**列集：无 `slotConfig` 时原样返回 `table.columns`（静态表）；
 * 有 `slotConfig` 时按 `entitySlots[slot]`（缺省回退该 slot 的默认实体名）动态生成
 * （Task 5.6，Property 18 —— 列数随 `names` 长度变化，`key` 改名后保持不变）。
 *
 * 无 `sub` 子列 → 单值列（无跨期分组，`flatCols`）；有 `sub` → 每实体两子列按实体名分组
 * （两级表头）。泛化实现避免新增槎位时还要各写一份 if 分支。
 */
export function resolveG7SoeTableColumns(
  table: G7DisclosureTable,
  entitySlots?: Record<string, string[]>,
): G7DisclosureColumn[] {
  const slotConfig = table.slotConfig
  if (!slotConfig) return table.columns
  const names = entitySlots?.[slotConfig.slot] ?? G7_SOE_DEFAULT_SLOT_NAMES[slotConfig.slot] ?? []
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
  const entitySlots: Record<string, string[]> = {}
  for (const [slot, names] of Object.entries(G7_SOE_DEFAULT_SLOT_NAMES)) {
    entitySlots[slot] = [...names]
  }
  return { version: 2, tables, texts, previouslySyncedTables: {}, entitySlots }
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
      // 🔴 行对象的标签键必须与 `buildG7SoeColumns()` 标签列的 `key` **逐字一致**，
      //    否则投影器 `_project_row` 取 `r.get(label_key)` 拿不到值 ⇒ **整表行名变空**。
      //    这条不变式由守卫 `g7ColumnThreeWayAlignment.spec.ts` 的
      //    「行构造标签键 ≡ 标签列 key」断言钉死（只改一侧即打红）。
      label: row.label,
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
      const columns = table.columns
      // 🔴 Property 9: flat/group 必须在同步载荷 columns 与模板 seed 两处都表态。
      // 有 group 的表 → 标签列不标 flat（混合分组：标签列 rowspan=2，其余列按 group 聚合）。
      // 无 group 的表 → 标签列标 flat（显式单级表头，抑制后端前缀推断）。
      const hasGroup = columns.some(c => c.group)
      const labelText = table.labelHeader ?? '项目'
      // 🔴 标签列 key 用平台惯例 `'label'`（不是中文字面量 `'项目'`）—— 裁决依据：
      //   ① 平台 266 个标签列定义里 241 个（91%）用 `'label'`，跨 70 个文件；
      //      硬编码 `'项目'` 全平台仅 7 处且全在 G 循环，属少数派偏离；
      //   ② 中文字面量当 key 违反平台「禁硬编码」取向；
      //   ③ 投影器 `note_sub_table_projector` 有双向兜底
      //      （`_inverse_project_row` L92-93 任意标签 key ← 规范 `label`；
      //       `project_sub_tables` L231-232 标签值为空 → 回退 `label`），
      //      且标签列不承载数据（行名真源是 `rows[].label`，`_cell_meta`/`_cell_modes`
      //      按 value 列索引、标签列不算数据列）。
      //
      // 🔴🔴 但兜底**只在一个方向成立** —— L231-232 的回退条件是 `label_key != "label"`，
      //    改成 `'label'` 后该分支不再触发。故必须同时满足两条，缺一即丢行名：
      //      (a) 行对象**必须带 `label` 键**（见 `materializeG7DisclosureRows`，已同步改）；
      //      (b) 列元数据与行对象**同一次请求一起推送**（`sync-batch-from-workpaper` 的
      //          每个 item 同时带 `sub_table_data` 与 `columns`，见 `G7TabDisclosureSOE.vue`），
      //          不存在「列已更新而行仍是旧键」的中间态。
      //    实测（`_wip_t4_live.py` 直跑投影器）：存量 5 张 soe 表的行对象只有 `项目` 键、
      //    **没有 `label` 键**，若只改列不改行 ⇒ 行名全部变空串；两侧同改后 6/6 表行名保留。
      //    存量记录在下一次同步时被整表覆盖（`sub_table_data` 按表名浅合并 + 行对象整体替换），
      //    故不需要数据迁移；同步前的旧记录仍由 `_sub_table_columns` 旧值（`项目`）正确渲染。
      result[syncTableKey(table)] = [
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

  // ── `_removed_table_keys` 逐章节差集（Task 13）──────────────────────────────
  //
  // 🔴 改造前 soe 侧**整条链是死的**：`dataTableNames` / `buildRemovedTableKeys`
  //    在本文件的调用数都是 **0**（死导入），`markG7SoeSynced` 不存在，
  //    `previouslySyncedTables` 只在 `createG7SoeDisclosureState` 初始化成 `{}`
  //    并被 `G7TabDisclosureSOE.vue` 持久化时原样透传 —— **无写入方、无消费方**。
  //    后果：soe 侧删掉一张表（如把条件表清空、或改名动态槎位）后，附注侧的
  //    `sub_table_data` / `_sub_table_columns` 永久残留过时明细（披露同步按 key
  //    浅合并，删除必须显式上报），而 listed 侧同一能力早已接通 ⇒ 两变体行为不一致。
  //
  // 判定口径（逐章节，与 listed 同源）：
  //   * **有录入区块**的章节 ⇒ 参与差集，「上次推送 − 本次推送」即需清理的过时表；
  //   * **无录入区块**的章节（纯文字披露，`tables` 为空）⇒ 天然不进 `byNote`，
  //     既不推表也不上报 removed（表不属本载荷所有，同章节可能被别的底稿推送）。
  //
  // 越权删的防线有三重，缺一不可：
  //   ① 被减数只能是 `previouslySyncedTables[该章节]`（= 本底稿自己推过的），
  //      不是附注现存表名 ⇒ 结构上删不到别的底稿的表；
  //   ② `buildRemovedTableKeys` 内部「推送优先」——本次推送的 key 绝不进结果；
  //   ③ 后端 `_drop_removed_tables` 同向再挡一次。
  // 🔴 门控用「章节**声明**里有没有录入区块」这一**结构性事实**，
  //    不是「本次推送了几张表」这一运行时数据：
  //    * 声明有 `tables` 但本次推送 0 张 ⇒ 数据被清空 ⇒ **应当**删（正是条件表场景）；
  //    * 声明无 `tables`（纯文字披露章节，只有 `narratives`）⇒ 该章节的表**不属本载荷所有**，
  //      同一附注章节可能被别的底稿推送 ⇒ 永不参与差集。
  //    实测 soe 有 3 个纯文字章节仍会进 `byNote`（它们有叙述段要推），
  //    若按「推送数为 0」门控就会把别的底稿的表算成自己的孤儿并删掉（越权删）。
  const sectionsWithTables = new Set(
    G7_SOE_DISCLOSURE_SECTIONS.filter(section => (section.tables ?? []).length > 0).map(
      section => section.noteSectionId,
    ),
  )
  for (const payload of byNote.values()) {
    if (!sectionsWithTables.has(payload.noteSectionId)) continue
    // 用共享模块的正式 API `attachRemovedTableKeys`（内部就是
    // `buildRemovedTableKeys` + 「空数组不挂键」），而不是手写赋值：
    // 它的入参是 `Record<string, unknown>`，能容纳 `string[]` 的元数据键，
    // 不必为一个元数据键去放宽 `G7SoeSyncPayload.subTableData` 的行数组类型。
    attachRemovedTableKeys(payload.subTableData as Record<string, unknown>, {
      previouslySynced: state.previouslySyncedTables?.[payload.noteSectionId],
      pushed: dataTableNames(payload.subTableData),
    })
  }

  return [...byNote.values()]
}

/**
 * 同步成功后调用：把本次各章节实际推送的表名记入 `previouslySyncedTables`，
 * 供下次同步计算 `_removed_table_keys` 差集。返回新状态片段（浅合并进 `state`）。
 *
 * 🔴 **没有这个写入方，差集恒为空** —— `previouslySyncedTables` 会永远停留在
 * `createG7SoeDisclosureState()` 给的 `{}`，`buildRemovedTableKeys` 的被减数恒空，
 * `_removed_table_keys` 永不上报。这正是改造前 soe 侧的状态（能力写了但没有写入方），
 * 也是平台记过的「additive 注入即死代码」形态：单测可以手动塞 `previouslySyncedTables`
 * 把它测绿，而生产路径上整条链空转。
 *
 * 故 `G7TabDisclosureSOE.vue` 同步成功后必须调用本函数并 `persist()`，
 * 且载入时要从持久化载荷恢复 `previouslySyncedTables`（三者缺一即断链）。
 */
export function markG7SoeSynced(
  state: G7SoeDisclosureState,
  payloads: G7SoeSyncPayload[],
): Record<string, string[]> {
  const sectionsWithTables = new Set(
    G7_SOE_DISCLOSURE_SECTIONS.filter(section => (section.tables ?? []).length > 0).map(
      section => section.noteSectionId,
    ),
  )
  const next: Record<string, string[]> = { ...(state.previouslySyncedTables ?? {}) }
  for (const payload of payloads) {
    // 与 `buildG7SoeSyncPayloads` 的差集门控**同一判据**：纯文字披露章节不建基线。
    // 否则会给它写一个空清单，下一轮该章节就带着「空基线」参与差集 ——
    // 虽然空基线减出来也是空，但基线里凭空多出这些章节键会误导后人以为它们参与清理。
    if (!sectionsWithTables.has(payload.noteSectionId)) continue
    next[payload.noteSectionId] = dataTableNames(payload.subTableData)
  }
  return next
}

export function g7SoeChapterSections(chapter: G7SoeDisclosureSection['chapter']): G7SoeDisclosureSection[] {
  return G7_SOE_DISCLOSURE_SECTIONS.filter(section => section.chapter === chapter)
}
