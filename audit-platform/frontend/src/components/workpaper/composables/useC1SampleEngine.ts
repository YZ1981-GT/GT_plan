/**
 * useC1SampleEngine — C1 企业层面控制测试 C1-4-4 样本借贷勾稽纯函数引擎
 *
 * 所有函数为纯函数，无副作用，无 Vue 响应式依赖，便于单元测试和 PBT。
 * 覆盖 C1-4-4「会计分录人工授权测试」样本明细表的借贷勾稽计算（源模板 19 公式的口径归纳）。
 *
 * 核心口径（Phase0 第 4 节实测）：
 *   - 每个分录样本由多行明细组成，借（F 列）/贷（G 列）成对镜像；
 *   - 模板用 19 个公式把一侧金额镜像到另一侧并对区段求和；
 *   - 整表勾稽本质：Σ借方 = Σ贷方。
 *   - debitTotal = Σdebit，creditTotal = Σcredit，balanced = (debitTotal == creditTotal)（浮点误差内）。
 *
 * Spec: .kiro/specs/c1-entity-level-control/
 * Requirements: 4.4
 */

// ─── 类型定义 ──────────────────────────────────────────────────────────────────

/** C1-4-4 样本明细行（源模板列：日期/账户编码/引用/交易描述/借方/贷方） */
export interface JeSample {
  date: string      // 日期（B 列）
  account: string   // 账户编码（C 列）
  ref: string       // 引用（D 列）
  desc: string      // 交易描述（E 列）
  debit: number     // 借方金额（F 列）
  credit: number    // 贷方金额（G 列）
}

/** 借贷勾稽结果 */
export interface SampleBalance {
  debitTotal: number   // Σ借方
  creditTotal: number  // Σ贷方
  balanced: boolean    // 借贷是否平衡（浮点误差内）
}

// ─── 常量 ──────────────────────────────────────────────────────────────────────

/**
 * 借贷勾稽浮点比较容差。
 *
 * 金额以「元」为单位累加时，浮点误差会随累加次数与量级放大，
 * 直接用 `===` 判定借贷相等不可靠。采用「绝对容差 + 相对容差」组合，
 * 相对项按借贷两侧的量级缩放，兼顾小额精确与大额稳健。
 */
export const SAMPLE_BALANCE_TOLERANCE = 1e-6

// ─── 数值解析 ─────────────────────────────────────────────────────────────────

/**
 * 安全数值解析：null/undefined/空串/NaN/Infinity → 0
 *
 * 样本单元可能为空或含无效值，统一转为数字 0 以确保勾稽求和不出 NaN。
 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || (val as unknown) === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  if (!isFinite(n)) return 0
  return n
}

// ─── 借贷勾稽核心公式 ───────────────────────────────────────────────────────────

/**
 * 判定两浮点金额在容差内是否相等。
 *
 * 采用绝对容差与相对容差（按两值量级缩放）的组合判据：
 *   |a - b| <= tolerance * max(1, |a|, |b|)
 * 既能处理接近 0 的小额（绝对容差），又能处理大额累加的浮点漂移（相对容差）。
 */
export function amountsEqual(a: number, b: number, tolerance = SAMPLE_BALANCE_TOLERANCE): boolean {
  const scale = Math.max(1, Math.abs(a), Math.abs(b))
  return Math.abs(a - b) <= tolerance * scale
}

/**
 * C1-4-4 样本借贷勾稽：汇总样本明细的借方/贷方并判定是否平衡。
 *
 * - debitTotal = Σsamples.debit
 * - creditTotal = Σsamples.credit
 * - balanced = amountsEqual(debitTotal, creditTotal)（浮点容差内，避免直接 == 比较）
 *
 * 纯函数：不修改入参，空数组返回 {0, 0, true}。
 */
export function calcSampleBalance(
  samples: JeSample[],
  tolerance = SAMPLE_BALANCE_TOLERANCE,
): SampleBalance {
  let debitTotal = 0
  let creditTotal = 0
  for (const s of samples) {
    debitTotal += parseNum(s.debit)
    creditTotal += parseNum(s.credit)
  }
  return {
    debitTotal,
    creditTotal,
    balanced: amountsEqual(debitTotal, creditTotal, tolerance),
  }
}

// ─── OCR 附件识别 → 样本行非破坏性 merge（Task 7.2, Req 10.2/10.3） ───────────────

/**
 * 样本行单元映射（列 slug → 字符串值）。
 * 与组件 SampleRow 的可编辑列一致：date/account/ref/desc/debit/credit。
 * 金额列在组件内以字符串存储，故此处统一按字符串处理，便于 merge 判空与持久化。
 */
export type SampleCellMap = Record<string, string>

/** 样本行可 merge 的列（源模板 C1-4-4：日期/账户编码/引用/交易描述/借方/贷方） */
export const SAMPLE_MERGE_COLS = ['date', 'account', 'ref', 'desc', 'debit', 'credit'] as const
export type SampleMergeCol = (typeof SAMPLE_MERGE_COLS)[number]

/** 判空：null/undefined/纯空白视为空（可被 OCR 填充） */
function isBlank(v: string | number | null | undefined): boolean {
  if (v === null || v === undefined) return true
  return String(v).trim() === ''
}

/**
 * 将 OCR 端点（/d4/contract-ocr）返回的 extracted_fields 映射为样本行单元。
 *
 * 复用契约 OCR 端点（铁律：抽凭表行级 OCR 复用 /d4/contract-ocr），其字段面向合同，
 * 此处按语义就近映射到会计分录样本的关键字段（日期/账户编码/金额/摘要）。
 * 同时兼容通用键名（date/account/amount/desc/summary 及中文键），提升鲁棒性。
 *
 * 仅输出**非空**值：空字符串、0 金额一律不产出，避免污染既有单元（配合非破坏性 merge）。
 * 纯函数，不修改入参。
 */
export function mapOcrToSampleCells(fields: Record<string, any> | null | undefined): SampleCellMap {
  const f = fields || {}
  const pick = (...keys: string[]): string => {
    for (const k of keys) {
      const v = f[k]
      if (v !== null && v !== undefined && String(v).trim() !== '') return String(v).trim()
    }
    return ''
  }
  const out: SampleCellMap = {}
  // 日期：合同签订日期 / 通用日期键
  const date = pick('signDate', 'date', 'voucherDate', '日期', 'recognitionTime')
  if (date) out.date = date
  // 账户编码：契约 OCR 一般无此字段，兼容通用键
  const account = pick('account', 'accountCode', 'accountNo', '账户编码', '科目编码')
  if (account) out.account = account
  // 摘要 / 交易描述：服务内容 / 交易对方 / 通用摘要键
  const desc = pick('serviceContent', 'desc', 'summary', 'counterparty', '摘要', '交易描述')
  if (desc) out.desc = desc
  // 金额：合同金额 / 通用金额键 → 借方（贷方留待用户手动或后续识别）
  const amount = pick('contractAmount', 'amount', 'debit', '金额', '借方金额')
  if (amount && parseNum(amount) !== 0) out.debit = String(parseNum(amount))
  const credit = pick('credit', '贷方金额')
  if (credit && parseNum(credit) !== 0) out.credit = String(parseNum(credit))
  return out
}

/** 非破坏性 merge 结果 */
export interface SampleMergeResult {
  /** merge 后的样本行单元 */
  merged: SampleCellMap
  /** 实际被 OCR 填充的列（原为空且 OCR 有值） */
  filledCols: string[]
  /** 因原值非空而被跳过（保护）的列 */
  skippedCols: string[]
}

/**
 * 非破坏性 merge：把 OCR 识别结果合并进既有样本行单元（Property P8）。
 *
 * 铁律（Req 10.3）：不直接覆盖。对每个列：
 *   - 若既有值为空（isBlank）且 OCR 提供非空值 → 填充（记入 filledCols）；
 *   - 若既有值非空 → 保留既有值，跳过 OCR 值（记入 skippedCols）。
 *
 * confirmedCols（可选）：用户在确认弹窗中明确选择覆盖的列，这些列即使原值非空也允许覆盖。
 * 未在 confirmedCols 中的非空列**永不**被覆盖。
 *
 * 纯函数：不修改入参，返回全新对象。
 */
export function mergeSampleRow(
  existing: SampleCellMap | null | undefined,
  incoming: SampleCellMap | null | undefined,
  confirmedCols: string[] = [],
): SampleMergeResult {
  const base: SampleCellMap = { ...(existing || {}) }
  const inc = incoming || {}
  const confirmed = new Set(confirmedCols)
  const merged: SampleCellMap = { ...base }
  const filledCols: string[] = []
  const skippedCols: string[] = []

  for (const col of Object.keys(inc)) {
    const incVal = inc[col]
    if (isBlank(incVal)) continue // OCR 无有效值，忽略
    const existingBlank = isBlank(base[col])
    if (existingBlank || confirmed.has(col)) {
      // 原值为空 → 填充；或用户确认覆盖
      merged[col] = String(incVal).trim()
      filledCols.push(col)
    } else {
      // 原值非空且未确认 → 保护，不覆盖（非破坏性）
      skippedCols.push(col)
    }
  }

  return { merged, filledCols, skippedCols }
}
