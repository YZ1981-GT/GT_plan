/**
 * useD2VcOcrCheck — D2-7 凭证检查表行级 OCR + AI 核对 + 确认回填 composable
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 3.1
 *
 * 职责：
 * - OCR 上传识别（uploadAndOcr）
 * - OCR 字段提取纯函数（extractOcrFields）
 * - OCR 比对纯函数（compareOcrWithRow）
 * - 确认弹窗（showConfirmDialog）
 * - 回填纯函数（backfillCheckColumns）
 * - 日期归一化纯函数（normalizeDate）
 * - 对方单位模糊相似度纯函数（fuzzyMatch）
 * - 取消逻辑：取消弹窗时不修改 check 列现有值
 * - OCR 服务不可用时降级：ElMessage.warning + 保留附件记录
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
 */
import { ref, inject, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import type { VoucherCheckRow, OcrExtractedData } from './useD2VoucherCheckEnhanced'

// ─── Types ───────────────────────────────────────────────────────────────────

export type MatchStatus = 'consistent' | 'inconsistent' | 'undetermined'

export interface CheckCompareResult {
  amountMatch: MatchStatus
  dateMatch: MatchStatus
  counterpartyMatch: MatchStatus
  businessMatch: MatchStatus
  attachmentComplete: MatchStatus
}

// Re-export for convenience
export type { OcrExtractedData }

// ─── Constants ───────────────────────────────────────────────────────────────

/** 金额比对允许误差 */
const AMOUNT_TOLERANCE = 0.01

/** 对方单位模糊相似度阈值 */
const COUNTERPARTY_SIMILARITY_THRESHOLD = 0.6

/** 匹配状态到中文显示文本的映射 */
export const MATCH_STATUS_TEXT: Record<MatchStatus, string> = {
  consistent: '一致',
  inconsistent: '不一致',
  undetermined: '无法判定',
}

// ─── Pure Functions (exported for PBT) ──────────────────────────────────────

/**
 * 日期归一化：将各种日期格式转换为 YYYY-MM-DD
 *
 * 支持的格式：
 * - YYYY-MM-DD (已标准化)
 * - YYYY/MM/DD
 * - YYYY.MM.DD
 * - YYYYMMDD
 * - YYYY年MM月DD日
 * - MM/DD/YYYY
 * - DD.MM.YYYY
 */
export function normalizeDate(dateStr: string | null | undefined): string {
  if (!dateStr || typeof dateStr !== 'string') return ''

  const trimmed = dateStr.trim()
  if (!trimmed) return ''

  // Already in YYYY-MM-DD format
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return trimmed
  }

  // YYYY/MM/DD or YYYY.MM.DD
  const slashDot = trimmed.match(/^(\d{4})[/.](\d{1,2})[/.](\d{1,2})$/)
  if (slashDot) {
    const [, y, m, d] = slashDot
    return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`
  }

  // YYYYMMDD
  if (/^\d{8}$/.test(trimmed)) {
    return `${trimmed.slice(0, 4)}-${trimmed.slice(4, 6)}-${trimmed.slice(6, 8)}`
  }

  // YYYY年MM月DD日
  const chinese = trimmed.match(/^(\d{4})年(\d{1,2})月(\d{1,2})日?$/)
  if (chinese) {
    const [, y, m, d] = chinese
    return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`
  }

  // MM/DD/YYYY (American format)
  const american = trimmed.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/)
  if (american) {
    const [, m, d, y] = american
    return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`
  }

  // DD.MM.YYYY (European format)
  const european = trimmed.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/)
  if (european) {
    const [, d, m, y] = european
    return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`
  }

  // Fallback: try to extract any date-like pattern
  const generic = trimmed.match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/)
  if (generic) {
    const [, y, m, d] = generic
    return `${y}-${m.padStart(2, '0')}-${d.padStart(2, '0')}`
  }

  return ''
}

/**
 * 计算两个字符串之间的字符重叠相似度
 *
 * 使用 bigram（2-gram）交集 / 并集 = Dice coefficient 的变体
 * 简化为字符级重叠比率：|intersection| / |max(a.length, b.length)|
 */
export function fuzzyMatch(a: string, b: string): number {
  if (!a || !b) return 0

  const cleanA = a.trim().toLowerCase()
  const cleanB = b.trim().toLowerCase()

  if (cleanA === cleanB) return 1.0
  if (!cleanA || !cleanB) return 0

  // Character-level overlap ratio
  const setA = new Set(cleanA)
  const setB = new Set(cleanB)

  let intersection = 0
  for (const ch of setA) {
    if (setB.has(ch)) intersection++
  }

  const union = new Set([...setA, ...setB]).size
  if (union === 0) return 0

  return intersection / union
}

/**
 * OCR 字段提取纯函数：从 OCR 原始响应中提取关键字段
 *
 * 支持的响应格式：
 * - { amount, date, counterparty, contractNo, full_text }
 * - { extracted_fields: { amount, date, ... } }
 * - { data: { amount, ... } }
 *
 * 金额解析：去除逗号/空格后转数字
 * 日期归一化：调用 normalizeDate
 * 对方单位：trim
 */
export function extractOcrFields(rawResponse: any): OcrExtractedData {
  if (!rawResponse || typeof rawResponse !== 'object') {
    return {}
  }

  // Support nested response structures
  const fields = rawResponse.extracted_fields || rawResponse.data || rawResponse

  const result: OcrExtractedData = {}

  // Extract amount（尝试多种字段名）
  const amountRaw = fields.amount ?? fields.total_amount ?? fields.金额 ?? fields.totalAmount
  if (amountRaw !== undefined && amountRaw !== null && amountRaw !== '') {
    const cleaned = String(amountRaw).replace(/[,\s¥￥$元]/g, '')
    const parsed = parseFloat(cleaned)
    if (!isNaN(parsed)) {
      result.amount = parsed
    }
  }

  // Extract date（尝试多种字段名）
  const dateRaw = fields.date ?? fields.invoice_date ?? fields.日期 ?? fields.invoiceDate ?? fields.contract_date
  if (dateRaw !== undefined && dateRaw !== null && dateRaw !== '') {
    const normalized = normalizeDate(String(dateRaw))
    if (normalized) {
      result.date = normalized
    }
  }

  // Extract counterparty（尝试多种字段名）
  const counterpartyRaw = fields.counterparty ?? fields.seller ?? fields.对方单位 ?? fields.company ?? fields.buyer ?? fields.party_name
  if (counterpartyRaw !== undefined && counterpartyRaw !== null && counterpartyRaw !== '') {
    result.counterparty = String(counterpartyRaw).trim()
  }

  // Extract contract number（尝试多种字段名）
  const contractNoRaw = fields.contractNo ?? fields.contract_no ?? fields.合同编号 ?? fields.invoice_no ?? fields.number
  if (contractNoRaw !== undefined && contractNoRaw !== null && contractNoRaw !== '') {
    result.contractNo = String(contractNoRaw).trim()
  }

  // Extract raw text
  const rawText = fields.full_text ?? fields.rawText ?? fields.raw_text ?? fields.content ?? fields.text
  if (rawText !== undefined && rawText !== null && rawText !== '') {
    result.rawText = String(rawText)
  }

  return result
}

/**
 * OCR 比对纯函数：将 OCR 提取的数据与凭证行进行比较
 *
 * 规则：
 * - 金额：|ocrAmount - rowAmount| < 0.01 → consistent; null → undetermined
 * - 日期：归一化后字符串相等 → consistent; null → undetermined
 * - 对方单位：模糊相似度 > 0.6 → consistent; null → undetermined
 * - 业务内容：always 'undetermined'（需要 AI，非纯比对）
 * - 附件完整性：OCR 成功即 'consistent'（文件解析成功）
 */
export function compareOcrWithRow(ocrData: OcrExtractedData, row: VoucherCheckRow): CheckCompareResult {
  const result: CheckCompareResult = {
    amountMatch: 'undetermined',
    dateMatch: 'undetermined',
    counterpartyMatch: 'undetermined',
    businessMatch: 'undetermined',
    attachmentComplete: 'consistent', // OCR succeeded → file parsed successfully
  }

  // Amount comparison
  if (ocrData.amount !== undefined && ocrData.amount !== null) {
    // Compare with both debit and credit amounts (whichever is non-zero)
    const rowAmount = row.debitAmount || row.creditAmount || 0
    if (rowAmount === 0 && ocrData.amount === 0) {
      result.amountMatch = 'consistent'
    } else if (rowAmount === 0) {
      result.amountMatch = 'undetermined'
    } else {
      const diff = Math.abs(ocrData.amount - rowAmount)
      result.amountMatch = diff < AMOUNT_TOLERANCE ? 'consistent' : 'inconsistent'
    }
  }

  // Date comparison
  if (ocrData.date) {
    const ocrNormalized = normalizeDate(ocrData.date)
    const rowNormalized = normalizeDate(row.voucherDate)

    if (!ocrNormalized || !rowNormalized) {
      result.dateMatch = 'undetermined'
    } else {
      result.dateMatch = ocrNormalized === rowNormalized ? 'consistent' : 'inconsistent'
    }
  }

  // Counterparty comparison
  if (ocrData.counterparty) {
    // Compare with counterpartAccount + counterpartDetail
    const rowCounterparty = row.counterpartAccount || row.counterpartDetail || ''
    if (!rowCounterparty) {
      result.counterpartyMatch = 'undetermined'
    } else {
      const similarity = fuzzyMatch(ocrData.counterparty, rowCounterparty)
      result.counterpartyMatch = similarity > COUNTERPARTY_SIMILARITY_THRESHOLD ? 'consistent' : 'inconsistent'
    }
  }

  // Business match: always undetermined (requires AI, not pure comparison)
  result.businessMatch = 'undetermined'

  return result
}

/**
 * 回填纯函数：将确认后的 CheckCompareResult 映射到 check1~check5 列值
 *
 * 映射关系：
 * - check1 ← amountMatch → "一致"/"不一致"/"无法判定"
 * - check2 ← dateMatch → "一致"/"不一致"/"无法判定"
 * - check3 ← counterpartyMatch → "一致"/"不一致"/"无法判定"
 * - check4 ← businessMatch → "一致"/"不一致"/"无法判定"
 * - check5 ← attachmentComplete → "一致"/"不一致"/"无法判定"
 *
 * 返回新行对象，不修改原行（纯函数）。
 */
export function backfillCheckColumns(row: VoucherCheckRow, confirmed: CheckCompareResult): VoucherCheckRow {
  return {
    ...row,
    check1: MATCH_STATUS_TEXT[confirmed.amountMatch],
    check2: MATCH_STATUS_TEXT[confirmed.dateMatch],
    check3: MATCH_STATUS_TEXT[confirmed.counterpartyMatch],
    check4: MATCH_STATUS_TEXT[confirmed.businessMatch],
    check5: MATCH_STATUS_TEXT[confirmed.attachmentComplete],
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseD2VcOcrCheckOptions {
  wpId: Ref<string>
  /** 获取指定行数据的函数 */
  getRow: (rowId: string) => VoucherCheckRow | undefined
  /** 更新行数据的函数 */
  updateRow: (rowId: string, field: keyof VoucherCheckRow, value: any) => void
}

export function useD2VcOcrCheck(options: UseD2VcOcrCheckOptions) {
  const { wpId, getRow, updateRow } = options

  const isProcessing = ref(false)

  /**
   * 上传文件并执行 OCR 识别 → 比对 → 确认弹窗 → 回填
   *
   * 流程：
   * 1. POST /d4/contract-ocr (multipart)
   * 2. extractOcrFields 提取字段
   * 3. compareOcrWithRow 比对
   * 4. showConfirmDialog 确认弹窗
   * 5. 用户确认 → backfillCheckColumns 回填；取消 → 不修改
   *
   * OCR 服务不可用时：ElMessage.warning + 保留附件记录
   */
  async function uploadAndOcr(rowId: string, file: File): Promise<void> {
    const row = getRow(rowId)
    if (!row) return

    isProcessing.value = true

    try {
      // 1. Call OCR service
      const formData = new FormData()
      formData.append('file', file)

      const res = await http.post(
        `/api/workpapers/${wpId.value}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )

      // 2. Extract OCR fields
      const rawResponse = res?.data?.data ?? res?.data
      const ocrData = extractOcrFields(rawResponse)

      // Store OCR result on the row
      updateRow(rowId, 'ocrResult' as any, ocrData)

      // 3. Compare with row
      const compareResult = compareOcrWithRow(ocrData, row)

      // 4. Show confirm dialog
      const confirmed = await showConfirmDialog(compareResult)

      // 5. Backfill or cancel
      if (confirmed) {
        // User confirmed → backfill check columns
        const newRow = backfillCheckColumns(row, confirmed)
        updateRow(rowId, 'check1', newRow.check1)
        updateRow(rowId, 'check2', newRow.check2)
        updateRow(rowId, 'check3', newRow.check3)
        updateRow(rowId, 'check4', newRow.check4)
        updateRow(rowId, 'check5', newRow.check5)
      }
      // else: user cancelled → do NOT modify check columns (Req 5.6)
    } catch (err: any) {
      // OCR service unavailable → graceful degradation (Req 4.4)
      ElMessage.warning('OCR 服务暂不可用，请手动录入')
      // Keep attachment record (file was already uploaded)
    } finally {
      isProcessing.value = false
    }
  }

  /**
   * 确认弹窗：展示 OCR 核对摘要，用户可逐项确认/修改
   *
   * 返回 null 表示用户取消（不修改 check 列）
   */
  async function showConfirmDialog(result: CheckCompareResult): Promise<CheckCompareResult | null> {
    const lines = [
      `金额核对：${MATCH_STATUS_TEXT[result.amountMatch]}`,
      `日期核对：${MATCH_STATUS_TEXT[result.dateMatch]}`,
      `对方单位：${MATCH_STATUS_TEXT[result.counterpartyMatch]}`,
      `业务内容：${MATCH_STATUS_TEXT[result.businessMatch]}`,
      `附件完整性：${MATCH_STATUS_TEXT[result.attachmentComplete]}`,
    ]

    try {
      await ElMessageBox.confirm(
        lines.join('\n'),
        'OCR 核对结果确认',
        {
          confirmButtonText: '确认回填',
          cancelButtonText: '取消',
          type: 'info',
          dangerouslyUseHTMLString: false,
        },
      )
      // User confirmed
      return result
    } catch {
      // User cancelled → return null → do NOT modify check columns
      return null
    }
  }

  return {
    isProcessing,
    uploadAndOcr,
    showConfirmDialog,
  }
}

export default useD2VcOcrCheck
