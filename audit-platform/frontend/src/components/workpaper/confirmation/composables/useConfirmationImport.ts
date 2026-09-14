/**
 * useConfirmationImport — 批量导入函证清单 composable
 *
 * 复用 useExcelIO 模式：解析 Excel/CSV → 预览 → 确认导入
 * 缺列行标错跳过，不破坏已有行。
 */
import { ref } from 'vue'
import type { ConfirmationRow } from '../confirmationTypes'

export interface ImportPreviewRow {
  rowIndex: number
  data: Partial<ConfirmationRow>
  status: 'ok' | 'skip' | 'error'
  errorMsg?: string
}

/** 必填列映射（Excel 列名 → ConfirmationRow 字段） */
const COLUMN_MAP: Record<string, keyof ConfirmationRow> = {
  '序号': 'seq',
  '索引号': 'confirm_index',
  '被询证单位': 'entity_name',
  '地址': 'entity_address',
  '联系人': 'contact_person',
  '联系电话': 'contact_phone',
  '科目': 'account_type',
  '函证金额': 'amount',
  '币种': 'currency',
  '函证方式': 'confirmation_method',
  '发函日期': 'send_date',
  '备注': 'remark',
}

const REQUIRED_COLUMNS = ['被询证单位', '科目', '函证金额']

export function useConfirmationImport() {
  const previewRows = ref<ImportPreviewRow[]>([])
  const isPreviewVisible = ref(false)
  const importing = ref(false)

  /**
   * 解析原始行数据（从 Excel 表头映射）
   */
  function parseRawRows(rawRows: Record<string, any>[]): ImportPreviewRow[] {
    return rawRows.map((raw, idx) => {
      const data: Partial<ConfirmationRow> = {}
      const missingCols: string[] = []

      for (const [excelCol, field] of Object.entries(COLUMN_MAP)) {
        if (raw[excelCol] != null && raw[excelCol] !== '') {
          ;(data as any)[field] = raw[excelCol]
        }
      }

      // 检查必填列
      for (const req of REQUIRED_COLUMNS) {
        const field = COLUMN_MAP[req]
        if (!field || (data as any)[field] == null || (data as any)[field] === '') {
          missingCols.push(req)
        }
      }

      if (missingCols.length > 0) {
        return {
          rowIndex: idx + 1,
          data,
          status: 'error' as const,
          errorMsg: `缺少必填列: ${missingCols.join(', ')}`,
        }
      }

      // 数值校验
      if (data.amount != null && typeof data.amount === 'string') {
        const num = parseFloat(data.amount)
        if (isNaN(num)) {
          return { rowIndex: idx + 1, data, status: 'error' as const, errorMsg: '函证金额格式错误' }
        }
        data.amount = num
      }

      return { rowIndex: idx + 1, data, status: 'ok' as const }
    })
  }

  /**
   * 开始预览（从文件解析后的原始数据）
   */
  function startPreview(rawRows: Record<string, any>[]) {
    previewRows.value = parseRawRows(rawRows)
    isPreviewVisible.value = true
  }

  /**
   * 确认导入：只导入 status=ok 的行，返回新增行数据
   */
  function confirmImport(): Partial<ConfirmationRow>[] {
    const validRows = previewRows.value
      .filter(r => r.status === 'ok')
      .map(r => ({ ...r.data, _source: 'import' as const }))
    isPreviewVisible.value = false
    previewRows.value = []
    return validRows
  }

  function cancelPreview() {
    isPreviewVisible.value = false
    previewRows.value = []
  }

  /** 导出模板列名 */
  function getTemplateHeaders(): string[] {
    return Object.keys(COLUMN_MAP)
  }

  return {
    previewRows,
    isPreviewVisible,
    importing,
    startPreview,
    confirmImport,
    cancelPreview,
    getTemplateHeaders,
    COLUMN_MAP,
    REQUIRED_COLUMNS,
  }
}
