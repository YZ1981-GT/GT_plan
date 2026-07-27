/**
 * confirmationColumnSpec.ts — X0-1 函证结果汇总表 列配置驱动层
 *
 * spec: confirmation-shared-model-extension（决策 1/2/3/4）
 *
 * 现状 `ConfirmationMaster.vue` 列硬编码。补 ~8 共性列 + 三类 Cycle_Variant 列若继续
 * 硬编码 + if-else 不可维护且违反 Requirement 2.1「配置驱动而非 if-else」。
 * 本文件抽 `ColumnDef`，`resolveConfirmationColumns(cycle)` 返回该枢纽应渲染的列
 * （BASE ∪ 该枢纽 variant），Master 用 v-for 渲染，分段表头按 `ColumnDef.group` 分组。
 *
 * 铁律：
 * - 各枢纽源模板用词不同不强行统一（Requirement 8.3）→ `label` 按各自源模板
 * - 源模板没有的列不进集合（Requirement 2.5 空列噪声避免）
 * - 每列 `source` 标注源模板出处（Requirement 8.2）
 */

export type ConfirmCycle = 'D0' | 'E0' | 'F0' | 'G0' | 'H0' | 'K0' | 'L0'

export type ColumnGroup =
  | 'send_info' // 发函信息
  | 'reply_info' // 收到回函
  | 'reply_amount' // 回函金额确认
  | 'alternative' // 未收到回函的替代程序
  | 'send_memo' // 发函询证纪要（K0/L0）

export const COLUMN_GROUP_LABELS: Record<ColumnGroup, string> = {
  send_info: '发函信息',
  reply_info: '收到回函',
  reply_amount: '回函金额确认',
  alternative: '未收到回函的替代程序',
  send_memo: '发函询证纪要',
}

export interface ColumnDef {
  /** 对应 ConfirmationRow 字段名 */
  key: string
  /** 源模板列名（各枢纽用词，不强行统一） */
  label: string
  group: ColumnGroup
  width?: number
  minWidth?: number
  align?: 'left' | 'right' | 'center'
  editable?: boolean
  kind?: 'text' | 'number' | 'amount' | 'date' | 'bool' | 'select'
  /** 源模板出处「枢纽·sheet·列名」（Requirement 8.2） */
  source: string
  /** 固定列（关键列横向滚动仍可辨识，Requirement 6.4） */
  fixed?: 'left' | 'right'
  /** 派生列（自动计算，只读，Requirement 1.5） */
  derived?: boolean
}

// ─── BASE：七枢纽共性列（含本 spec 补的 8 个共性新列 + 既有列） ──────────────

export const BASE_CONFIRMATION_COLUMNS: ColumnDef[] = [
  // 发函信息
  { key: 'seq', label: '序号', group: 'send_info', width: 50, align: 'center', editable: false, kind: 'number', fixed: 'left', source: 'X0-1·序号' },
  { key: 'sample_purpose', label: '选取样本目的', group: 'send_info', minWidth: 120, kind: 'text', source: 'X0-1·选取样本目的' },
  { key: 'confirm_index', label: '函证索引号', group: 'send_info', width: 90, kind: 'text', fixed: 'left', source: 'X0-1·函证索引号' },
  { key: 'account_type', label: '科目', group: 'send_info', width: 90, kind: 'text', source: 'X0-1·科目大类' },
  { key: 'entity_name', label: '被询证单位名称', group: 'send_info', minWidth: 140, kind: 'text', fixed: 'left', source: 'X0-1·被询证单位名称' },
  { key: 'entity_address', label: '地址', group: 'send_info', minWidth: 130, kind: 'text', source: 'X0-1·地址' },
  { key: 'contact_person', label: '联系人', group: 'send_info', width: 90, kind: 'text', source: 'X0-1·联系人' },
  { key: 'contact_phone', label: '联系电话', group: 'send_info', width: 110, kind: 'text', source: 'X0-1·联系电话' },
  { key: 'amount', label: '函证金额', group: 'send_info', minWidth: 110, align: 'right', kind: 'amount', source: 'X0-1·函证金额' },
  { key: 'currency', label: '币种', group: 'send_info', width: 70, kind: 'text', source: 'X0-1·币种' },
  { key: 'confirmation_method', label: '函证方式', group: 'send_info', width: 90, kind: 'text', source: 'X0-1·函证方式' },
  { key: 'send_date', label: '发函日期', group: 'send_info', width: 110, kind: 'date', source: 'X0-1·发函日期' },
  { key: 'send_doc_no', label: '发函单号', group: 'send_info', width: 100, kind: 'text', source: 'X0-1·发函单号' },
  { key: 'send_addr_match', label: '收件地址核查是否一致', group: 'send_info', width: 120, align: 'center', kind: 'select', source: 'X0-1·收件地址核查是否一致' },

  // 收到回函
  { key: 'is_replied', label: '是否已回函', group: 'reply_info', width: 80, align: 'center', kind: 'bool', source: 'X0-1·是否已回函' },
  { key: 'reply_method', label: '回函方式', group: 'reply_info', width: 90, kind: 'text', source: 'X0-1·回函方式' },
  { key: 'reply_date', label: '收函日期', group: 'reply_info', width: 110, kind: 'date', source: 'X0-1·收函日期' },
  { key: 'reply_courier_no', label: '回函快递单号', group: 'reply_info', width: 110, kind: 'text', source: 'X0-1·回函快递单号' },
  { key: 'reply_from_addr', label: '回函发出地址', group: 'reply_info', minWidth: 130, kind: 'text', source: 'X0-1·回函发出地址' },
  { key: 'send_reply_addr_match', label: '发函地址与回函地址是否一致', group: 'reply_info', width: 130, align: 'center', kind: 'select', source: 'X0-1·发函地址与回函地址是否一致' },

  // 回函金额确认
  { key: 'reply_amount', label: '回函金额', group: 'reply_amount', minWidth: 110, align: 'right', kind: 'amount', source: 'X0-1·回函金额' },
  { key: 'match_status', label: '相符情况', group: 'reply_amount', width: 80, align: 'center', kind: 'select', source: 'X0-1·相符情况' },
  { key: 'difference', label: '差异金额', group: 'reply_amount', minWidth: 100, align: 'right', kind: 'amount', editable: false, derived: true, source: 'X0-1·差异金额(自动)' },
  { key: 'confirmed_amount', label: '可确认金额', group: 'reply_amount', minWidth: 110, align: 'right', kind: 'amount', editable: false, derived: true, source: 'X0-1·可确认金额(自动)' },

  // 未收到回函的替代程序
  { key: 'use_alternative', label: '是否采取替代程序', group: 'alternative', width: 110, align: 'center', kind: 'bool', source: 'X0-1·是否采取替代程序' },
  { key: 'alt_confirmed', label: '替代程序确认金额', group: 'alternative', minWidth: 120, align: 'right', kind: 'amount', source: 'X0-1·替代程序确认金额' },
  { key: 'alt_unconfirmed', label: '替代后不可确认金额', group: 'alternative', minWidth: 130, align: 'right', kind: 'amount', source: 'X0-1·替代后不可确认金额' },
  { key: 'alt_ref_index', label: '替代程序索引', group: 'alternative', width: 100, kind: 'text', source: 'X0-1·替代程序索引' },
  { key: 'diff_ref_index', label: '差异调节表索引', group: 'alternative', width: 100, kind: 'text', source: 'X0-1·差异调节表索引' },
  { key: 'remark', label: '备注', group: 'alternative', minWidth: 120, kind: 'text', source: 'X0-1·备注' },
]

// ─── Cycle_Variant 列定义（仅部分枢纽源模板存在） ───────────────────────────

const VARIANT_COLUMN_DEFS: Record<string, ColumnDef> = {
  // K0/L0 五段：发函询证纪要 + 行级审计结论（源模板 5 段 28 列）
  send_memo: { key: 'send_memo', label: '发函询证纪要', group: 'send_memo', minWidth: 160, kind: 'text', source: 'K0-1/L0-1·发函询证纪要' },
  row_conclusion: { key: 'row_conclusion', label: '审计结论', group: 'send_memo', minWidth: 140, kind: 'text', source: 'K0-1/L0-1·审计结论' },

  // E0 原币/本位币/汇率（本位币复用既有 amount/confirmed_amount，见决策 3）
  account_no: { key: 'account_no', label: '账号或理财产品名称', group: 'send_info', minWidth: 140, kind: 'text', source: 'E0-1·账号或理财产品名称' },
  amount_orig: { key: 'amount_orig', label: '发函金额（原币）', group: 'send_info', minWidth: 120, align: 'right', kind: 'amount', source: 'E0-1·发函金额（原币）' },
  fx_rate: { key: 'fx_rate', label: '汇率', group: 'reply_amount', width: 90, align: 'right', kind: 'number', source: 'E0-1·汇率' },
  confirmed_amount_orig: { key: 'confirmed_amount_orig', label: '可确认金额（原币）', group: 'reply_amount', minWidth: 130, align: 'right', kind: 'amount', source: 'E0-1·可确认金额（原币）' },

  // H0 条款口径（决策 4：文本载体，不改 amount 类型）
  term_book: { key: 'term_book', label: '账面合同条款', group: 'reply_amount', minWidth: 140, kind: 'text', source: 'H0-1·金额或合同条款(账面侧)' },
  term_reply: { key: 'term_reply', label: '回函合同条款', group: 'reply_amount', minWidth: 140, kind: 'text', source: 'H0-1·金额或合同条款(回函侧)' },
  term_match: { key: 'term_match', label: '条款是否一致', group: 'reply_amount', width: 100, align: 'center', kind: 'select', source: 'H0-1·条款一致性' },
  term_note: { key: 'term_note', label: '条款差异说明', group: 'reply_amount', minWidth: 140, kind: 'text', source: 'H0-1·条款差异说明' },
}

/** 枢纽 → 启用的 variant 列 key（源模板没有的不进集合） */
export const CYCLE_VARIANT_COLUMNS: Record<ConfirmCycle, string[]> = {
  D0: [],
  E0: ['account_no', 'amount_orig', 'fx_rate', 'confirmed_amount_orig'],
  F0: [],
  G0: [],
  H0: ['term_book', 'term_reply', 'term_match', 'term_note'],
  K0: ['send_memo', 'row_conclusion'],
  L0: ['send_memo', 'row_conclusion'],
}

const BASE_BY_KEY: Record<string, ColumnDef> = Object.fromEntries(
  BASE_CONFIRMATION_COLUMNS.map((c) => [c.key, c]),
)

/**
 * 纯函数：返回该枢纽应渲染的列 = BASE ∪ CYCLE_VARIANT_COLUMNS[cycle]
 * variant 列插到其 group 内既有 BASE 列之后，保持分段表头顺序。
 */
export function resolveConfirmationColumns(cycle: ConfirmCycle): ColumnDef[] {
  const variantKeys = CYCLE_VARIANT_COLUMNS[cycle] ?? []
  if (!variantKeys.length) return [...BASE_CONFIRMATION_COLUMNS]

  const variantDefs = variantKeys
    .map((k) => VARIANT_COLUMN_DEFS[k])
    .filter((d): d is ColumnDef => !!d)

  // 分 group 合并：先 BASE 该 group 列，再该 group 的 variant 列，保持 group 顺序
  const groupOrder: ColumnGroup[] = ['send_info', 'reply_info', 'reply_amount', 'alternative', 'send_memo']
  const result: ColumnDef[] = []
  for (const g of groupOrder) {
    result.push(...BASE_CONFIRMATION_COLUMNS.filter((c) => c.group === g))
    result.push(...variantDefs.filter((c) => c.group === g))
  }
  return result
}

/** 该枢纽默认「核心」列 key（列显隐预设，Requirement 6.1 覆盖最常用列） */
export const CORE_COLUMN_KEYS: string[] = [
  'seq', 'confirm_index', 'entity_name', 'account_type', 'amount',
  'confirmation_method', 'send_date', 'is_replied', 'reply_amount',
  'match_status', 'difference', 'confirmed_amount',
]

export { VARIANT_COLUMN_DEFS, BASE_BY_KEY }
