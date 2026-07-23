/**
 * d1InspectionFormulas — D1 监盘核查组共享类型定义与纯函数
 *
 * 所有函数为纯函数，无副作用，便于单元测试和 PBT。
 * 供 useD1InventoryCount / useD1RelatedPartyCheck / useD1PledgeCheck / useD1SamplingVouching 复用。
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Requirements: 4.4, 4.5, 8.1, 8.3, 12.4, 18.2
 */

// ═══════════════════════════════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════════════════════════════

/** D1-10 监盘日结存行（15列） */
export interface InventoryCountRow {
  id: string                    // 唯一标识(uuid)
  noteType: string              // A: 票据类型（银行承兑汇票/商业承兑汇票）
  noteNo: string                // B: 票据号
  issueDate: string             // C: 出票日
  drawer: string                // D: 出票人
  acceptor: string              // E: 承兑人
  amount: number                // F: 金额
  maturityDate: string          // G: 到期日
  predecessor: string           // H: 前手
  receiveDate: string           // I: 收到日期
  endorseDate: string           // J: 背书/贴现日
  endorsee: string              // K: 被背书人/贴现行
  noteStatus: string            // L: 票据状态
  hasDifference: string         // M: 是否存在差异（是/否）
  differenceReason: string      // N: 差异原因
  indexRef: string              // O: 索引号
}

/** D1-11 关联方行（13列） */
export interface RelatedPartyRow {
  id: string
  partyName: string             // A: 关联方名称
  relationship: string          // B: 关联关系
  openingBalance: number        // C: 期初余额
  debitOccurrence: number       // D: 借方发生
  creditOccurrence: number      // E: 贷方发生
  closingBalance: number        // F: 期末余额 (公式: C+D-E, 只读)
  badDebtProvision: number      // G: 减：坏账准备
  bookValue: number             // H: 账面价值 (公式: F-G, 只读)
  agingInfo: string             // I: 发生时间及账龄
  transactionNature: string     // J: 发生原因（款项性质）
  postHonored: number           // K: 期后已兑现或已贴现
  indexRef: string              // L: 索引号
  remark: string                // M: 备注
}

/** D1-12 质押行（16列 + OCR附件） */
export interface PledgeRow {
  id: string
  noteType: string              // A: 票据类型
  noteNo: string                // B: 票据号码
  receiveDate: string           // C: 收到票据日期
  predecessor: string           // D: 票据前手名称
  issueDate: string             // E: 出票日期
  drawer: string                // F: 出票人名称
  acceptor: string              // G: 承兑人名称
  noteAmount: number            // H: 票据金额
  maturityDate: string          // I: 票据到期日
  pledgeAmount: number          // J: 质押金额
  pledgee: string               // K: 质权人
  pledgeReason: string          // L: 质押原因
  pledgeCondition: string       // M: 质押条件
  pledgePeriod: string          // N: 质押期限 (日期范围)
  pledgeAgreement: string       // O: 质押协议
  indexRef: string              // P: 索引号
  attachmentId: string          // 附件ID
  attachmentName: string        // 附件名称
  ocrStatus: 'none' | 'processing' | 'done' // OCR状态
}

/** D1-13 凭证核对明细行（13列） */
export interface VouchingRow {
  id: string
  seq: number                   // 序号（自动编号）
  noteType: string              // 票据类型
  noteNo: string                // 票据号码
  drawer: string                // 出票人
  acceptor: string              // 承兑人
  amount: number                // 金额
  maturityDate: string          // 到期日
  existenceCheck: string        // 存在性验证（已核实/未核实/不适用）
  accuracyCheck: string         // 准确性验证（金额一致/金额不一致/不适用）
  appropriatenessCheck: string  // 记录恰当性（恰当/不恰当/不适用）
  attachmentId: string          // 附件ID（OCR上传后回传）
  attachmentName: string        // 附件名称
  ocrStatus: string             // OCR状态（none/processing/done/failed）
  remark: string                // 备注
  indexRef: string              // 索引号
}

/** D1-13 例外汇总行 */
export interface ExceptionSummaryRow {
  category: string              // 存在性/准确性/记录恰当性
  count: number                 // 例外笔数
  amount: number                // 例外金额
  rate: number                  // 占比 (= amount / totalCheckedAmount)
}

/** D1-13 抽样总体定义 */
export interface SamplePopulation {
  testPopulation: string        // 测试总体
  specificItemScope: string     // 特定样本范围（大额/关联方/异常等）
  populationDesc: string        // 抽样总体（扣除特定样本后的范围）
  samplingMethod: string        // 抽样方法
  totalCount: number            // 总体笔数
  totalAmount: number           // 总体金额
  sampleSize: number            // 确定的抽样样本量
  actualDrawn: number           // 实际抽取笔数
  sampleCalcRef: string         // 样本计算器索引号
}

/** D1-13 特定样本行 */
export interface SpecificSampleRow {
  id: string
  description: string           // 项目描述
  amount: number                // 金额
  reason: string                // 抽出原因
}

// ═══════════════════════════════════════════════════════════════════════════
// 常量选项
// ═══════════════════════════════════════════════════════════════════════════

/** 票据类型选项 */
export const NOTE_TYPE_OPTIONS = ['银行承兑汇票', '商业承兑汇票'] as const

/** 票据状态选项 */
export const NOTE_STATUS_OPTIONS = ['在库', '已背书', '已贴现', '已到期', '已质押'] as const

/** 关联关系选项 */
export const RELATIONSHIP_OPTIONS = ['母公司', '子公司', '联营企业', '合营企业', '关键管理人员', '其他关联方'] as const

/** 存在性验证选项 */
export const EXISTENCE_OPTIONS = ['已核实', '未核实', '不适用'] as const

/** 准确性验证选项 */
export const ACCURACY_OPTIONS = ['金额一致', '金额不一致', '不适用'] as const

/** 记录恰当性验证选项 */
export const APPROPRIATENESS_OPTIONS = ['恰当', '不恰当', '不适用'] as const

/** 测试结论选项 */
export const TEST_CONCLUSION_OPTIONS = [
  '未发现重大例外',
  '发现例外已获合理解释',
  '发现例外需扩大测试',
  '发现重大错报',
] as const

/** 是否存在差异选项 */
export const DIFFERENCE_OPTIONS = ['是', '否'] as const

// ═══════════════════════════════════════════════════════════════════════════
// 纯函数
// ═══════════════════════════════════════════════════════════════════════════

/**
 * D1-11 期末余额公式: F = C + D - E
 *
 * 关联方余额变动：期末余额 = 期初余额 + 借方发生 - 贷方发生。
 * 适用于 D1-11 每一行的 F 列自动计算。
 */
export function computeClosingBalance(
  openingBalance: number,
  debit: number,
  credit: number
): number {
  return openingBalance + debit - credit
}

/**
 * D1-11 账面价值公式: H = F - G
 *
 * 关联方账面价值 = 期末余额 - 坏账准备。
 * 链式依赖 computeClosingBalance 的 F 值。
 */
export function computeBookValue(
  closingBalance: number,
  badDebtProvision: number
): number {
  return closingBalance - badDebtProvision
}

/**
 * SUM合计: 对数组某字段求和
 *
 * 通用合计公式，覆盖 D1-10 H21、D1-11 Row14 七列、D1-12 Row18、D1-13 G45 等合计行。
 * 非数字字段值安全降级为 0。
 */
export function sumColumn<T>(rows: T[], field: keyof T): number {
  return rows.reduce((sum, row) => sum + (Number(row[field]) || 0), 0)
}

/**
 * D1-12 质押比例: J18 / adjBookValue，零值守卫
 *
 * 当审定表净值为 null 或 0 时返回 null（无法计算），否则返回质押金额合计除以审定表净值。
 */
export function computePledgeRatio(
  pledgeTotal: number,
  adjBookValue: number | null
): number | null {
  if (adjBookValue == null || adjBookValue === 0) return null
  return pledgeTotal / adjBookValue
}

/**
 * D1-13 例外占比: exceptionAmount / totalCheckedAmount
 *
 * 当核查金额合计为 0 时返回 0（避免除零），否则返回例外金额占比。
 * 覆盖存在性/准确性/记录恰当性三类例外占比计算。
 */
export function computeExceptionRate(
  exceptionAmount: number,
  totalCheckedAmount: number
): number {
  if (totalCheckedAmount === 0) return 0
  return exceptionAmount / totalCheckedAmount
}

/**
 * 负数金额括号格式化: -1234.56 → "(1,234.56)"
 *
 * 审计底稿中负数金额以红色括号格式显示（会计惯例）。
 * 非负数返回空字符串（不处理）。
 */
export function formatNegativeAmount(value: number): string {
  if (value >= 0) return ''
  const abs = Math.abs(value)
  const formatted = abs.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return `(${formatted})`
}
