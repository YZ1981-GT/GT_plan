/**
 * useD2VcImportExport — D2-7 凭证检查表双区分 sheet 导入导出 composable
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 6.1
 *
 * 职责：
 * - 导出模板：生成两 sheet xlsx（"本期增减变动检查" / "期后收款调整检查"），每 sheet 17 列表头
 * - 导出数据：两 sheet + 已填数据序列化
 * - 导入数据：读两 sheet → 按凭证编号合并或追加到对应区
 * - 缺少 sheet 时仅导入存在的 sheet 并 ElMessage.info 提示
 * - 列名匹配容忍顺序不同，无法匹配的列跳过并 warn
 *
 * Requirements: 12.1, 12.2, 12.3, 12.4, 12.5
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { mergeVoucherRows, type VoucherCheckRow } from './useD2VoucherCheckEnhanced'

// ─── Constants ───────────────────────────────────────────────────────────────

export const SHEET_NAME_CURRENT = '本期增减变动检查'
export const SHEET_NAME_POST = '期后收款调整检查'

/** 17 列表头（顺序为标准导出顺序） */
export const COLUMN_HEADERS: string[] = [
  '客户名称',
  '日期',
  '凭证编号',
  '业务内容',
  '对方科目',
  '对方明细科目',
  '借方金额',
  '贷方金额',
  '支持性文件',
  '核对内容1',
  '核对内容2',
  '核对内容3',
  '核对内容4',
  '核对内容5',
  '索引号',
  '是否异常',
  '备注说明',
]

/** 表头 → VoucherCheckRow 字段名映射 */
export const HEADER_TO_FIELD_MAP: Record<string, keyof VoucherCheckRow> = {
  '客户名称': 'customerName',
  '日期': 'voucherDate',
  '凭证编号': 'voucherNo',
  '业务内容': 'businessContent',
  '对方科目': 'counterpartAccount',
  '对方明细科目': 'counterpartDetail',
  '借方金额': 'debitAmount',
  '贷方金额': 'creditAmount',
  '支持性文件': 'supportingDoc',
  '核对内容1': 'check1',
  '核对内容2': 'check2',
  '核对内容3': 'check3',
  '核对内容4': 'check4',
  '核对内容5': 'check5',
  '索引号': 'indexRef',
  '是否异常': 'isAbnormal',
  '备注说明': 'remark',
}

/** VoucherCheckRow 字段名 → 表头映射（反向） */
const FIELD_TO_HEADER_MAP: Record<string, string> = Object.fromEntries(
  Object.entries(HEADER_TO_FIELD_MAP).map(([h, f]) => [f, h])
)

const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

// ─── Pure Functions (exported for PBT testing) ───────────────────────────────

/**
 * 将 VoucherCheckRow[] 序列化为 2D 数组（含表头行）
 * 第一行为表头，后续行为数据
 */
export function serializeRowsToSheetData(rows: VoucherCheckRow[]): (string | number)[][] {
  const headerRow: string[] = [...COLUMN_HEADERS]
  const dataRows: (string | number)[][] = rows.map((row) => {
    return COLUMN_HEADERS.map((header) => {
      const field = HEADER_TO_FIELD_MAP[header]
      if (!field) return ''
      const value = row[field]
      if (field === 'debitAmount' || field === 'creditAmount') {
        return typeof value === 'number' ? value : Number(value) || 0
      }
      // Trim string fields: whitespace-only values are semantically empty in this domain
      return value != null ? String(value).trim() : ''
    })
  })
  return [headerRow, ...dataRows]
}

/**
 * 根据表头行构建列索引到字段名的映射
 * 容忍列顺序不同，无法匹配的列跳过（返回的 map 不包含该列索引）
 *
 * @param headerRow - xlsx 文件中读取的表头行
 * @returns Map<列索引, VoucherCheckRow字段名>
 */
export function buildHeaderMap(headerRow: (string | number | null | undefined)[]): Map<number, keyof VoucherCheckRow> {
  const map = new Map<number, keyof VoucherCheckRow>()
  const unmatchedHeaders: string[] = []

  for (let i = 0; i < headerRow.length; i++) {
    const raw = headerRow[i]
    if (raw == null) continue
    const headerText = String(raw).trim()
    if (!headerText) continue

    const field = HEADER_TO_FIELD_MAP[headerText]
    if (field) {
      map.set(i, field)
    } else {
      unmatchedHeaders.push(headerText)
    }
  }

  // 无法匹配的列 warn
  if (unmatchedHeaders.length > 0) {
    console.warn(
      `[useD2VcImportExport] 以下列名无法匹配，已跳过: ${unmatchedHeaders.join(', ')}`
    )
  }

  return map
}

/**
 * 将 2D 数组（含表头行）反序列化为 VoucherCheckRow[]
 * 使用 buildHeaderMap 的结果做列→字段映射
 *
 * @param sheetData - xlsx sheet 的 2D 数组（第一行为表头）
 * @param headerMap - buildHeaderMap 返回的映射（如不传，自动从 sheetData[0] 构建）
 * @returns VoucherCheckRow[]
 */
export function deserializeSheetDataToRows(
  sheetData: (string | number | null | undefined)[][],
  headerMap?: Map<number, keyof VoucherCheckRow>,
): VoucherCheckRow[] {
  if (!sheetData || sheetData.length < 2) return []

  const map = headerMap ?? buildHeaderMap(sheetData[0])
  const rows: VoucherCheckRow[] = []

  for (let rowIdx = 1; rowIdx < sheetData.length; rowIdx++) {
    const dataRow = sheetData[rowIdx]
    if (!dataRow || dataRow.every((cell) => cell == null || String(cell).trim() === '')) {
      continue // 跳过空行
    }

    const row = createEmptyImportRow(rowIdx)

    for (const [colIdx, field] of map.entries()) {
      const cellValue = dataRow[colIdx]
      if (cellValue == null) continue

      if (field === 'debitAmount' || field === 'creditAmount') {
        ;(row as any)[field] = Number(cellValue) || 0
      } else {
        ;(row as any)[field] = String(cellValue).trim()
      }
    }

    rows.push(row)
  }

  return rows
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `vcr-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function createEmptyImportRow(seq: number): VoucherCheckRow {
  return {
    rowId: generateRowId(),
    seq,
    customerName: '',
    voucherDate: '',
    voucherNo: '',
    businessContent: '',
    counterpartAccount: '',
    counterpartDetail: '',
    debitAmount: 0,
    creditAmount: 0,
    supportingDoc: '',
    check1: '',
    check2: '',
    check3: '',
    check4: '',
    check5: '',
    indexRef: '',
    isAbnormal: '',
    remark: '',
    attachments: [],
    source: '导入',
  }
}

/**
 * 触发浏览器下载 blob 文件
 */
function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseD2VcImportExportOptions {
  wpId: Ref<string>
  currentRows: Ref<VoucherCheckRow[]>
  postRows: Ref<VoucherCheckRow[]>
  /** 保存回调（导入完成后触发持久化） */
  saveToResponses: () => void
}

export interface VcImportResult {
  currentImported: number
  postImported: number
  skippedSheets: string[]
  warnings: string[]
}

/**
 * 从 axios 错误里取后端写明的失败原因（R4：三个请求共用同一套解析）。
 *
 * 后端错误体有两种形状，且**导出端点是 blob 响应**（`responseType: 'blob'` ⇒ `err.response.data`
 * 是 Blob 而不是对象），所以必须先把 Blob 读成文本再解析，否则只能拿到通用兜底文案：
 * - 业务 `HTTPException` 走平台全局处理器：`{"code":400,"message":"仅支持 .xlsx 文件"}`
 * - starlette / 422 原生：`{"detail": "…"}` 或 `{"detail":[{…}]}`
 *
 * 优先顺序与 `utils/http.ts` 的 `extractErrorDetail` 同口径：字符串 detail → message →
 * 对象 detail 里的 message → 原始文本（不是 JSON 时）。
 * 解析不出来（断网、超时、CORS）才用调用方给的兜底中文。
 */
export async function resolveFailureReason(err: any, fallback: string): Promise<string> {
  const data = err?.response?.data
  if (data == null) return fallback

  let payload: any = data
  if (isBlobLike(data)) {
    try {
      const text = await new Promise<string>((resolve, reject) => {
        const fr = new FileReader()
        fr.onload = () => resolve(String(fr.result ?? ''))
        fr.onerror = reject
        fr.readAsText(data)
      })
      try {
        payload = JSON.parse(text)
      } catch {
        // 不是 JSON：后端可能直接回了纯文本原因
        return text.trim() || fallback
      }
    } catch {
      return fallback
    }
  }

  if (typeof payload === 'string') return payload.trim() || fallback
  if (typeof payload?.detail === 'string' && payload.detail.trim()) return payload.detail
  if (typeof payload?.message === 'string' && payload.message.trim()) return payload.message
  if (typeof payload?.detail?.message === 'string' && payload.detail.message.trim()) return payload.detail.message
  return fallback
}

/** jsdom 与浏览器双环境下的 Blob 判定（jsdom 的 Blob 不一定与全局 Blob 同源） */
function isBlobLike(value: any): boolean {
  return value instanceof Blob
    || (value != null && typeof value.slice === 'function' && typeof value.size === 'number')
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2VcImportExport(options: UseD2VcImportExportOptions) {
  const { wpId, currentRows, postRows, saveToResponses } = options

  const importing = ref<boolean>(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ───────────────────────────────────────────────────

  /**
   * 导出空白 xlsx 模板（两 sheet，仅表头）
   * POST /api/workpapers/{wpId}/d2/vc-export-template
   */
  async function exportTemplate(): Promise<void> {
    lastError.value = null
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d2/vc-export-template`,
        null,
        { responseType: 'blob', _silent: true },
      )
      const blob = new Blob([res.data], { type: XLSX_MIME })
      triggerBlobDownload(blob, 'D2-7_凭证检查表模板.xlsx')
      ElMessage.success('凭证检查表模板已导出')
    } catch (err: any) {
      // R4：三个请求同一套解析 —— 后端原因优先（blob 响应也要读出来），网络错误才用兜底中文
      lastError.value = await resolveFailureReason(err, '导出模板失败，请检查网络后重试')
      ElMessage.error(lastError.value!)
    }
  }

  // ─── Export Data ───────────────────────────────────────────────────────

  /**
   * 导出当前双区数据为 xlsx（两 sheet + 数据）
   * POST /api/workpapers/{wpId}/d2/vc-export-data
   */
  async function exportData(): Promise<void> {
    lastError.value = null
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d2/vc-export-data`,
        {
          currentRows: serializeRowsToSheetData(currentRows.value),
          postRows: serializeRowsToSheetData(postRows.value),
        },
        { responseType: 'blob', _silent: true },
      )
      const blob = new Blob([res.data], { type: XLSX_MIME })
      triggerBlobDownload(blob, 'D2-7_凭证检查表数据.xlsx')
      ElMessage.success('凭证检查表数据已导出')
    } catch (err: any) {
      // R4：与导出模板同一套解析（blob 响应体也要读出来），保证三个请求口径一致
      lastError.value = await resolveFailureReason(err, '导出数据失败，请检查网络后重试')
      ElMessage.error(lastError.value!)
    }
  }

  // ─── Import Data ───────────────────────────────────────────────────────

  /**
   * 导入 xlsx 文件（两 sheet → 分别导入对应区块）
   * POST /api/workpapers/{wpId}/d2/vc-import-data (multipart/form-data)
   *
   * 后端解析 xlsx 返回 { sheets: { [sheetName]: 2D array } }
   * 前端按 sheet 名匹配→反序列化→合并到对应区
   */
  async function importData(file: File): Promise<VcImportResult | null> {
    lastError.value = null
    importing.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)

      const res = await http.post(
        `/api/workpapers/${wpId.value}/d2/vc-import-data`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true },
      )

      // 后端返回解析后的 sheet 数据
      const data = res.data?.data ?? res.data
      const sheets: Record<string, (string | number | null)[][]> = data?.sheets ?? {}

      const result: VcImportResult = {
        currentImported: 0,
        postImported: 0,
        skippedSheets: [],
        warnings: [],
      }

      // 查找 current sheet（本期增减变动检查）
      const currentSheetData = findSheetData(sheets, 'current')
      if (currentSheetData) {
        const importedRows = deserializeSheetDataToRows(currentSheetData)
        const merged = mergeVoucherRows(currentRows.value, importedRows)
        currentRows.value = merged
        result.currentImported = importedRows.length
      } else {
        result.skippedSheets.push(SHEET_NAME_CURRENT)
        ElMessage.info(`未找到'${SHEET_NAME_CURRENT}'sheet，已跳过`)
      }

      // 查找 post sheet（期后收款调整检查）
      const postSheetData = findSheetData(sheets, 'post')
      if (postSheetData) {
        const importedRows = deserializeSheetDataToRows(postSheetData)
        const merged = mergeVoucherRows(postRows.value, importedRows)
        postRows.value = merged
        result.postImported = importedRows.length
      } else {
        result.skippedSheets.push(SHEET_NAME_POST)
        ElMessage.info(`未找到'${SHEET_NAME_POST}'sheet，已跳过`)
      }

      // 导入后持久化
      if (result.currentImported > 0 || result.postImported > 0) {
        saveToResponses()
        const total = result.currentImported + result.postImported
        ElMessage.success(`成功导入 ${total} 行数据`)
      }

      return result
    } catch (err: any) {
      // R4：与两个导出请求同一套解析
      lastError.value = await resolveFailureReason(err, '导入失败，请检查网络后重试')
      ElMessage.error(lastError.value!)
      return null
    } finally {
      importing.value = false
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    importing,
    lastError,
    exportTemplate,
    exportData,
    importData,
  }
}

// ─── Internal Helpers ────────────────────────────────────────────────────────

/**
 * 从后端返回的 sheets 对象中查找对应 zone 的 sheet 数据
 * 容忍不同命名方式：
 * - exact match: "本期增减变动检查" / "期后收款调整检查"
 * - 包含关键字: "本期" / "current" → zone current; "期后" / "post" → zone post
 */
function findSheetData(
  sheets: Record<string, (string | number | null)[][]>,
  zone: 'current' | 'post',
): (string | number | null)[][] | null {
  const names = Object.keys(sheets)

  if (zone === 'current') {
    // 精确匹配
    if (sheets[SHEET_NAME_CURRENT]) return sheets[SHEET_NAME_CURRENT]
    // 模糊匹配
    const found = names.find((n) =>
      n.includes('本期') || n.toLowerCase().includes('current')
    )
    return found ? sheets[found] : null
  } else {
    // 精确匹配
    if (sheets[SHEET_NAME_POST]) return sheets[SHEET_NAME_POST]
    // 模糊匹配
    const found = names.find((n) =>
      n.includes('期后') || n.toLowerCase().includes('post')
    )
    return found ? sheets[found] : null
  }
}

export default useD2VcImportExport
