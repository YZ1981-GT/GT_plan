/**
 * e1CurrencyScope — E1 货币资金「币种 / 外币分组」单一真源
 *
 * **为什么要收敛**
 *
 * 改造前 `E1TabDisclosure.vue` 内联三份常量（`SIMPLE_CURRENCIES` /
 * `DETAILED_CURRENCIES` / `DETAILED_PROJECTS`），违反平台「避免硬编码」铁律；
 * 且与附注「外币货币性项目」章节的币种行口径不一致（底稿 美元/日元/澳元/欧元，
 * 附注 五、73 / 八、92 是 美元/欧元/港币）。
 *
 * **E 类没有账龄维度** —— 货币资金不涉及账龄。E 类与其它循环「账龄枚举
 * （3年段/5年段/自定义）」对应的枚举维度是**币种**与**受限类别**（后者见
 * `e1RestrictedScope.ts`），本模块按同款「枚举驱动 + 动态插行 + 稳定 key」范式处理。
 *
 * **行 key 不能用 label**：自定义币种可能与预置同名（或两个分组下同名），
 * 用 label 作 key 会撞键（H7 已踩过）。故 key = `${groupSlot}_${currencyKey}_${seq}`。
 *
 * 源模板依据（openpyxl 直读 `E1-1至E1-11 …xlsx`）：
 * - 「附注披露信息(上市公司)」R35~R62「货币资金」原币表：四个分组
 *   R38 `库存现金：` / R44 `银行存款：` / R50 `银行存款中：财务公司存款` /
 *   R56 `其他货币资金：`，每组下 R39~R43 等 5 个币种行 人民币/美元/日元/澳元/欧元
 * - R25~R32「外币性货币项目」是**派生表**（`B29=B40+B46+B52+B58`），
 *   只列外币（其中：美元/日元/澳元/欧元），不含人民币
 *
 * spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/
 *       Requirements 4.5, 4.6 / Property 9
 */

// ─── 币种 ─────────────────────────────────────────────────────────────────────

export interface E1Currency {
  /** 稳定标识（持久化用，**不可改**） */
  key: string
  /** 展示名（逐字取自源 xlsx 原币表币种行） */
  label: string
  /** 是否记账本位币（折算率恒 1，且不进「外币性货币项目」派生表） */
  isBase: boolean
}

/** 预置币种 —— 逐字取自源 xlsx 原币表 R39~R43。 */
export const E1_DEFAULT_CURRENCIES: readonly E1Currency[] = Object.freeze([
  { key: 'cny', label: '人民币', isBase: true },
  { key: 'usd', label: '美元', isBase: false },
  { key: 'jpy', label: '日元', isBase: false },
  { key: 'aud', label: '澳元', isBase: false },
  { key: 'eur', label: '欧元', isBase: false },
])

/**
 * 附注「外币货币性项目」（五、73 / 八、92）现有的币种行。
 *
 * 该章节**跨循环共享**（同时承载 应收账款/短期借款/长期借款/应付债券 各段），
 * 其币种行是 美元/欧元/港币 —— 与底稿原币表口径不同。推送时按 label 对齐，
 * 底稿有而附注无的币种走动态插行，不改附注既有行集。
 */
export const E1_NOTE_FX_CURRENCY_LABELS: readonly string[] = Object.freeze([
  '美元',
  '欧元',
  '港币',
])

// ─── 外币原币表分组 ───────────────────────────────────────────────────────────

export interface E1FxGroup {
  /** 稳定标识 */
  slot: string
  /** 展示名（逐字取自源 xlsx，含尾部冒号由 UI 决定是否显示） */
  label: string
  /** 源 xlsx 分组行引用（供守卫反查） */
  sourceRef: string
}

/** 原币表四个分组 —— 逐字取自源 xlsx R38 / R44 / R50 / R56。 */
export const E1_FX_GROUPS: readonly E1FxGroup[] = Object.freeze([
  { slot: 'cash', label: '库存现金', sourceRef: '附注披露信息(上市公司)!A38' },
  { slot: 'bank', label: '银行存款', sourceRef: '附注披露信息(上市公司)!A44' },
  {
    slot: 'finance_co',
    label: '银行存款中：财务公司存款',
    sourceRef: '附注披露信息(上市公司)!A50',
  },
  { slot: 'other', label: '其他货币资金', sourceRef: '附注披露信息(上市公司)!A56' },
])

// ─── 稳定 key ─────────────────────────────────────────────────────────────────

/**
 * 原币表行的稳定 key。
 *
 * 🔴 **禁用 label 作 key**：自定义币种可与预置同名、不同分组下也可同名 →
 * 用 label 会撞键并把两行数据合并（H7 实证）。`seq` 保证同分组同币种多行也不撞。
 */
export function e1CurrencyRowKey(groupSlot: string, currencyKey: string, seq: number): string {
  return `fx_${groupSlot}_${currencyKey}_${seq}`
}

/** 自定义币种的 key（由展示名派生但**加序号**，避免同名撞键）。 */
export function e1CustomCurrencyKey(label: string, seq: number): string {
  const slug = String(label ?? '')
    .trim()
    .replace(/\s+/g, '')
    .slice(0, 12)
  return `custom_${slug || 'ccy'}_${seq}`
}

// ─── 派生计算（纯函数，读时推导不持久化）─────────────────────────────────────

/** 人民币金额 = 原币金额 × 折算率（源 xlsx `D39=B39*C39`）。 */
export function e1RmbAmount(foreign: number, rate: number): number {
  const f = Number(foreign)
  const r = Number(rate)
  if (!Number.isFinite(f) || !Number.isFinite(r)) return 0
  return f * r
}

/** 记账本位币的折算率恒为 1（源 xlsx `C39=1` / `F39=1`）。 */
export function e1DefaultRate(currencyKey: string): number {
  const c = E1_DEFAULT_CURRENCIES.find((x) => x.key === currencyKey)
  return c?.isBase ? 1 : 0
}

/**
 * 「外币性货币项目」派生表某币种的合计 = 原币表**四个分组**同币种之和。
 *
 * 源 xlsx `B29=B40+B46+B52+B58`（美元在 库存现金/银行存款/财务公司存款/其他货币资金
 * 四组的原币金额之和）。人民币不进该表（`isBase`）。
 */
export function e1SumCurrencyAcrossGroups<T extends { currencyKey: string; groupSlot: string }>(
  rows: readonly T[],
  currencyKey: string,
  pick: (row: T) => number,
): number {
  return rows
    .filter((r) => r.currencyKey === currencyKey)
    .reduce((s, r) => s + (Number(pick(r)) || 0), 0)
}

/** 参与「外币性货币项目」派生表的币种（排除记账本位币）。 */
export function e1ForeignCurrencies(
  currencies: readonly E1Currency[] = E1_DEFAULT_CURRENCIES,
): E1Currency[] {
  return currencies.filter((c) => !c.isBase)
}

/** 记账本位币的展示名（供组件判定折算率是否恒 1，避免内联「人民币」字面量）。 */
export function e1BaseCurrencyLabel(
  currencies: readonly E1Currency[] = E1_DEFAULT_CURRENCIES,
): string {
  return currencies.find((c) => c.isBase)?.label ?? ''
}

/**
 * 简版（源 xlsx R25「外币性货币项目」）的唯一分组名。
 *
 * 该表是**派生表**（`B29=B40+B46+B52+B58`），只有一个分组行 R28「货币资金：」，
 * 下辖「其中：美元/日元/澳元/欧元」。
 */
export const E1_FX_SIMPLE_GROUP_LABEL = '货币资金'
