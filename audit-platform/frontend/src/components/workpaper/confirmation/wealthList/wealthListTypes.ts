/**
 * wealthListTypes.ts — E0-6 理财产品发函记录表 类型定义
 *
 * 源模板真源：`E0 货币资金 - 函证（Leap应对措施-函证）.xlsx` 的
 * `理财产品发函记录表E0-6`（`A1:K20`，表头单行在 R5，数据区 R6:R20 全空骨架，
 * 无合计行、无两级表头）。11 列逐字对照见 `WEALTH_LIST_COLUMN_SOURCE`。
 *
 * 设计要点：
 * - **单层 11 列网格**，无 master-detail（对齐 D0-7 可靠性表的形态）
 * - `产品名称` 是 E0-1 E 列「账号/理财产品名称」的来源 —— 理财产品没有账号，
 *   源模板拿产品名称当汇总键；故它**不是**被询证单位名（被询证单位是银行）
 * - `产品净值` 是**总额口径**（源 E0-1 F 列 `SUMIFS(E0-6!$H:$H,…)` 直接求和 H），
 *   与 E0-3 `账户余额（原币）` / E0-4 `余额` / E0-5 `票面金额` 同构。
 *   `持有份额` 是询证函正文补充信息，**不参与金额计算**（禁 `份额 × 净值`）
 * - 源模板**无「是否函证」列** → 入表即视为发函对象，不做筛选门
 * - 质量红线：缺汇总键(索引号/产品名称)=红（E0-1 汇总不到）；已到期=橙；受限=提示
 */

// ─── 源模板列对照（单一真源，守卫按此逐字比对 A5:K5） ────────────────────────

export const WEALTH_LIST_COLUMN_SOURCE = [
  { field: 'confirm_index', label: '索引号', cell: 'A5' },
  { field: 'cutoff_date', label: '报表截止日', cell: 'B5' },
  { field: 'bank_and_recipient', label: '开户行名称及收件人', cell: 'C5' },
  { field: 'product_name', label: '产品名称', cell: 'D5' },
  { field: 'product_type', label: '产品类型（封闭式/开放式）', cell: 'E5' },
  { field: 'currency', label: '币种', cell: 'F5' },
  { field: 'units_held', label: '持有份额', cell: 'G5' },
  { field: 'net_value', label: '产品净值', cell: 'H5' },
  { field: 'purchase_date', label: '购买日', cell: 'I5' },
  { field: 'maturity_date', label: '到期日', cell: 'J5' },
  { field: 'restricted', label: '是否被用于担保或存在其他使用限制', cell: 'K5' },
] as const

/** 顶部说明（源模板口径提示，防"份额×净值"误解） */
export const WEALTH_LIST_HEADER_NOTE =
  '本表逐只理财产品登记发函信息。「产品净值」为总额口径，按「索引号 + 产品名称」直接汇入 E0-1「发函金额（原币）」；'
  + '「持有份额」仅作询证函正文补充信息，不参与金额计算。'

// ─── 明细行 ──────────────────────────────────────────────────────────────────

export interface WealthProductRow {
  /** 内部行 ID（前端生成） */
  _row_id?: string
  /** 序号（UI 用，源模板无此列） */
  seq?: number

  /** 索引号 — 源 A 列；E0-1 汇总键之一（对 E0-1 B「询证函索引号」） */
  confirm_index?: string
  /** 报表截止日 — 源 B 列 */
  cutoff_date?: string
  /** 开户行名称及收件人 — 源 C 列；被询证单位（银行） */
  bank_and_recipient?: string
  /** 产品名称 — 源 D 列；E0-1 汇总键之一（对 E0-1 E「账号/理财产品名称」） */
  product_name?: string
  /** 产品类型 — 源 E 列，列名自带枚举括注 */
  product_type?: '封闭式' | '开放式'
  /** 币种 — 源 F 列 */
  currency?: string
  /** 持有份额 — 源 G 列（数量，非金额） */
  units_held?: number | null
  /** 产品净值 — 源 H 列（金额，总额口径 → E0-1 发函金额） */
  net_value?: number | null
  /** 购买日 — 源 I 列 */
  purchase_date?: string
  /** 到期日 — 源 J 列 */
  maturity_date?: string
  /** 是否被用于担保或存在其他使用限制 — 源 K 列，DV「是/否」 */
  restricted?: '是' | '否'

  /** 数据来源标识（manual/import/auto） */
  _source?: string
}

// ─── 看板指标 ────────────────────────────────────────────────────────────────

export interface WealthListMetrics {
  /** 产品笔数 */
  total_count: number
  /** 发函金额合计（Σ 产品净值） */
  net_value_total: number
  /** 持有份额合计 */
  units_total: number
  /** 受限笔数（是否被用于担保=是） */
  restricted_count: number
  /** 受限金额合计 */
  restricted_amount: number
  /** 已到期笔数（到期日 ≤ 报表截止日） */
  matured_count: number
  /** 封闭式笔数 */
  closed_count: number
  /** 开放式笔数 */
  open_count: number
  /** 汇总键缺失笔数（缺 索引号 或 产品名称 → E0-1 汇总不到） */
  missing_key_count: number
  /** 金额为空或 0 的笔数 */
  zero_amount_count: number
}

// ─── 审计说明 ────────────────────────────────────────────────────────────────

export interface WealthListAuditNote {
  /** 发函范围与选取说明 */
  note_scope?: string
  /** 受限情况说明（担保/使用限制） */
  note_restricted?: string
  /** 其他事项 */
  note_other?: string
}

// ─── 审计结论 ────────────────────────────────────────────────────────────────

export interface WealthListConclusion {
  /** 结论类型 */
  conclusion_type?: '完整' | '存在例外需跟进' | '不适用'
  /** 结论说明 */
  conclusion_text?: string
}

// ─── 持久化 payload ──────────────────────────────────────────────────────────

export interface WealthListPayload {
  /** 格式版本标识 */
  _format: 'wealth-list-v1'
  rows: WealthProductRow[]
  audit_note?: WealthListAuditNote
  conclusion?: WealthListConclusion
}
