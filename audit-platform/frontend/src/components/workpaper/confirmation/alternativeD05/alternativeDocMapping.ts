/**
 * 函证替代程序：单据类型 → 本区块哪些列可以由识别结果填入（spec attachment-confirmation-evidence-loop 需求 3，ADR-ACE-03）
 *
 * 键 = 「表头分组 | 列名」（与 `blockColumnConfigs*.ts` 的 group / label 逐字一致；L0-5 自有表格的证据列没有分组，
 * 键为 `|列名`），值 = 后端 `_confirmation_alt_doc_ocr.DOCUMENT_SCHEMAS[类型]` 的字段；`date_no` 是派生字段（日期 + 编号）。
 * 守卫：每个键都能在某页列配置里找到（无死条目）；每个值都在后端该类 schema 里。
 *
 * 改造前四页各写一张 `OCR_FIELD_MAP`，键是 `date` / `金额` / `付款方`，而借来的合同识别回 `contractNo` / `contractAmount`
 * ⇒ 几乎从不填入；填入时也不看本行是否已有值。
 */

export type AltDocType = 'bank_receipt' | 'invoice' | 'shipping' | 'statement' | 'contract' | 'voucher'

/** 界面顺序 = 缺省选中顺序（记账凭证多从账上取，排最后） */
export const ALT_DOC_TYPES: ReadonlyArray<{ value: AltDocType; label: string; hint: string }> = [
  { value: 'bank_receipt', label: '银行回单 / 回款单', hint: '日期、付款方、收款方、金额、摘要' },
  { value: 'invoice', label: '发票', hint: '日期 / 号码、销售方、购买方、金额' },
  { value: 'shipping', label: '发运 / 物流单据', hint: '出库、运输、签收、入库、验收单：品名、数量、承运、签收' },
  { value: 'statement', label: '对账单（证券 / 往来）', hint: '对账日期、品种、数量、市值、双方余额、交易明细' },
  { value: 'contract', label: '合同 / 协议', hint: '编号、对方单位、金额、期限' },
  { value: 'voucher', label: '记账凭证', hint: '日期、凭证编号、摘要、对方科目、金额' },
]

/** 「仅上传，不识别」时附件的证据类型 */
export const UPLOAD_ONLY_EVIDENCE_TYPE = 'support'

export const ALT_DOC_COLUMN_MAP: Record<AltDocType, Record<string, string>> = {
  voucher: {
    '记账凭证|日期': 'date', '记账凭证|凭证编号': 'doc_no', '记账凭证|编号': 'doc_no',
    '记账凭证|业务内容': 'summary', '记账凭证|对方科目': 'counter_account', '记账凭证|明细科目': 'detail_account',
    '记账凭证|借方金额': 'amount', '记账凭证|贷方金额': 'amount', '记账凭证|金额': 'amount',
    '记账凭证|品名': 'product', '记账凭证|数量': 'qty',
  },
  bank_receipt: {
    '银行回单|日期': 'date', '银行回单|日期/编号': 'date_no', '银行回单|付款方': 'payer', '银行回单|收款方': 'payee',
    '银行回单|金额': 'amount', '银行回单|摘要': 'summary',
    '银行收款凭单|付款方': 'payer', '银行收款凭单|金额': 'amount',
    '付款凭证|付款日期': 'date', '付款凭证|付款金额': 'amount',
    '股利收入|银行回单日期': 'date', '股利收入|到账金额': 'amount',
    '|银行回单日期': 'date', '|收款方': 'payee', '|到账银行回单日期': 'date', '|到账金额': 'amount',
  },
  invoice: {
    '销售发票|日期/编号': 'date_no', '销售发票|收票方名称': 'buyer', '销售发票|对手方名称': 'buyer', '销售发票|金额': 'amount',
    '采购发票|日期/编号': 'date_no', '采购发票|发票日期/编号': 'date_no', '采购发票|对手方': 'seller',
    '采购发票|金额': 'amount', '采购发票|发票金额': 'amount',
  },
  shipping: {
    '客户验收单/出库单|日期/编号': 'date_no', '客户验收单/出库单|数量': 'qty', '客户验收单/出库单|签字、签章信息': 'sign_info',
    '客户验收单/出库单|确认金额': 'amount', '客户验收单/出库单|签收人': 'signer',
    '客户验收单/出库单|盖章类型': 'stamp_type', '客户验收单/出库单|盖章单位': 'stamp_entity',
    '出库单|编号': 'doc_no', '出库单|品名': 'product', '出库单|数量': 'qty', '出库单|仓库保管员': 'keeper', '出库单|发货人': 'shipper',
    '运输单|运输数量': 'qty', '运输单|运输公司': 'carrier', '运输单|运输地址': 'address',
    '签收单|签收人': 'signer', '签收单|盖章类型': 'stamp_type', '签收单|盖章单位': 'stamp_entity',
    '入库单|日期/编号': 'date_no', '入库单|品名': 'product', '入库单|单位': 'unit', '入库单|数量': 'qty',
    '验收单|验收单日期/编号': 'date_no', '验收单|资产名称': 'product', '验收单|规格型号': 'spec', '验收单|数量': 'qty',
    '到货验收|到货验收日期': 'date', '到货验收|资产名称': 'product', '到货验收|数量': 'qty',
  },
  statement: {
    '持仓证明|对账单日期': 'date', '持仓证明|持仓品种': 'variety', '持仓证明|数量': 'qty', '持仓证明|市值': 'market_value',
    '对账单|对账单日期': 'date', '对账单|对方余额': 'counterparty_balance', '对账单|本方余额': 'own_balance',
    '往来对账|对账单日期': 'date', '往来对账|对方余额': 'counterparty_balance', '往来对账|本方余额': 'own_balance',
    '源外增强·处置明细|交易确认单日期': 'trade_date', '源外增强·处置明细|卖出/赎回数量': 'trade_qty',
    '源外增强·处置明细|成交价': 'trade_price', '源外增强·处置明细|成交金额': 'trade_amount',
    '源外增强·处置明细|手续费': 'fee', '源外增强·处置明细|净收入': 'net_amount',
    '|银行对账单日期': 'date',
  },
  contract: {
    '合同|客户名称': 'counterparty', '合同|合同供应商': 'counterparty', '合同|供应商': 'counterparty',
    '合同|合同金额': 'amount', '合同|金额': 'amount', '合同|日期/编号': 'date_no', '合同|合同日期': 'date',
    '销售合同/销售订单|合同号': 'doc_no', '销售订单/销售合同|订单号/合同号': 'doc_no',
    '采购合同|合同日期/编号': 'date_no', '采购合同|供应商': 'counterparty', '采购合同|合同金额': 'amount',
    '借据/协议|借据/协议编号': 'doc_no', '借据/协议|对方单位': 'counterparty', '借据/协议|金额': 'amount',
    '协议证据|借据/协议编号': 'doc_no', '协议证据|对方单位': 'counterparty', '协议证据|金额': 'amount',
    '协议证据|往来协议编号': 'doc_no', '协议证据|签订日期': 'date',
    '往来协议|往来协议编号': 'doc_no', '往来协议|签订日期': 'date',
    '初始投资协议|被投资单位': 'counterparty', '初始投资协议|投资比例': 'ratio',
    '初始投资协议|投资金额': 'amount', '初始投资协议|投资条款': 'terms',
    '投资协议/交易确认单/交割单|日期/编号': 'date_no', '投资协议/交易确认单/交割单|被投资单位名称': 'counterparty',
    '投资协议/交易确认单/交割单|金额': 'amount',
    '抵押担保|抵押合同编号': 'doc_no', '抵押担保|抵押权人': 'counterparty', '抵押担保|担保金额': 'amount',
    '融资租赁|融资租赁合同编号': 'doc_no', '融资租赁|出租方': 'counterparty', '融资租赁|租赁期': 'term',
    '|借款合同编号': 'doc_no', '|债权人': 'counterparty', '|合同金额': 'amount', '|借款期限': 'term',
    '|抵质押合同编号': 'doc_no', '|抵押金额': 'amount', '|担保合同编号': 'doc_no', '|担保方': 'counterparty',
    '|担保金额': 'amount',
  },
}

/** 识别结果里能填进行内的列（CheckBlock 列定义与 L0-5 证据列的公共子集） */
export interface AltColumn {
  field: string
  label: string
  group?: string
  type?: string
}

export function columnKey(col: AltColumn): string {
  return `${col.group ?? ''}|${col.label}`
}

/** 本区块用得上的单据类型（按界面顺序） */
export function applicableDocTypes(columns: readonly AltColumn[]): AltDocType[] {
  return ALT_DOC_TYPES.map((t) => t.value).filter((t) =>
    columns.some((c) => !!ALT_DOC_COLUMN_MAP[t][columnKey(c)]))
}

function isBlank(v: unknown): boolean {
  return v == null || String(v).trim() === ''
}

/** 识别出的日期归一为 YYYY-MM-DD；认不出 ⇒ null */
export function normalizeDate(raw: unknown): string | null {
  const m = /(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})/.exec(String(raw ?? ''))
  if (!m) return null
  const [, y, mo, d] = m
  return `${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}`
}

/** 数值：去千分符与货币符号；非数或 0（后端「未识别」的缺省值）⇒ null */
export function toNumber(raw: unknown): number | null {
  if (typeof raw === 'number') return Number.isFinite(raw) && raw !== 0 ? raw : null
  const text = String(raw ?? '').replace(/[,，\s¥￥元]/g, '')
  if (!text) return null
  const n = Number(text)
  return Number.isFinite(n) && n !== 0 ? n : null
}

function fieldValue(fields: Record<string, unknown>, docField: string): unknown {
  if (docField !== 'date_no') return fields[docField]
  const parts = [normalizeDate(fields.date) ?? (isBlank(fields.date) ? '' : String(fields.date).trim()), String(fields.doc_no ?? '').trim()]
  return parts.filter(Boolean).join(' ')
}

function coerce(raw: unknown, col: AltColumn, docField: string): string | number | null {
  if (col.type === 'number') return toNumber(raw)
  if (col.type === 'date') return normalizeDate(raw)
  if (col.type === 'select' || col.type === 'formula') return null
  if (isBlank(raw) || raw === 0) return null
  if (docField === 'date' || docField === 'trade_date') return normalizeDate(raw) ?? String(raw).trim()
  return String(raw).trim()
}

export interface FillItem {
  field: string
  /** 列名（有分组时带分组前缀） */
  label: string
  value: string | number
  current: unknown
  /** 本行这一列为空 ⇒ 可填（缺省勾选）；已有值 ⇒ 不覆盖 */
  fillable: boolean
}

/** 识别结果 → 本区块各列的填入计划（只含识别到值的列，按列顺序） */
export function buildFillPlan(
  columns: readonly AltColumn[],
  row: Record<string, unknown>,
  docType: AltDocType,
  fields: Record<string, unknown>,
): FillItem[] {
  const map = ALT_DOC_COLUMN_MAP[docType]
  const plan: FillItem[] = []
  for (const col of columns) {
    const docField = map[columnKey(col)]
    if (!docField) continue
    const value = coerce(fieldValue(fields, docField), col, docField)
    if (value == null || value === '') continue
    const current = row[col.field]
    plan.push({ field: col.field, label: col.group ? `${col.group} · ${col.label}` : col.label, value, current, fillable: isBlank(current) })
  }
  return plan
}
