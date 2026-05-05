/**
 * useExcelIO — 统一 Excel 导入导出 composable [R3.5]
 *
 * 所有 worksheet 组件共用的 Excel 操作：
 *   exportTemplate(columns, sheetName, fileName)  — 导出空白模板（含表头+说明）
 *   exportData(data, columns, sheetName, fileName) — 导出数据到 Excel
 *   parseFile(file, options)                       — 解析上传的 Excel 文件，返回行数组
 *   onFileSelected(event, callback)                — 处理 file input change 事件
 *
 * 全部使用 dynamic import('xlsx') 实现代码分割。
 */

import { ElMessage } from 'element-plus'

/* ── 类型定义 ── */

/** 列定义 */
export interface ExcelColumn {
  /** 数据字段名 */
  key: string
  /** Excel 表头文字 */
  header: string
  /** 字段说明（用于模板说明行/填写说明 sheet） */
  note?: string
  /** 示例值 */
  example?: string
  /** 列宽（字符数），默认自动计算 */
  width?: number
}

/** 模板导出选项 */
export interface ExportTemplateOptions {
  /** 列定义 */
  columns: ExcelColumn[]
  /** 工作表名称 */
  sheetName?: string
  /** 导出文件名（含 .xlsx） */
  fileName: string
  /** 分类行（第一行，可选） */
  categoryRow?: (string | null | undefined)[]
  /** 分类行合并区域 */
  categoryMerges?: Array<{ s: { r: number; c: number }; e: { r: number; c: number } }>
  /** 是否生成"填写说明"sheet */
  includeInstructions?: boolean
  /** 填写说明标题 */
  instructionTitle?: string
  /** 额外的填写说明行 */
  instructionRows?: string[][]
  /** 示例数据行（如果有） */
  exampleRows?: any[][]
  /** 现有数据行（如果有，优先于 exampleRows） */
  existingData?: any[][]
  /** 是否包含说明行（第二行，列 note） */
  includeNoteRow?: boolean
}

/** 数据导出选项 */
export interface ExportDataOptions {
  /** 数据数组 */
  data: Record<string, any>[]
  /** 列定义 */
  columns: ExcelColumn[]
  /** 工作表名称 */
  sheetName?: string
  /** 导出文件名（含 .xlsx） */
  fileName: string
  /** 额外的表头列（追加在 columns 之后） */
  extraHeaders?: string[]
  /** 额外列的数据提取函数 */
  extraDataFn?: (row: Record<string, any>) => any[]
}

/** 文件解析选项 */
export interface ParseFileOptions {
  /** 目标工作表名称，找不到时取最后一个 sheet */
  sheetName?: string
  /** 跳过前 N 行（分类行+说明行+表头行），默认 1（只有表头行） */
  skipRows?: number
  /** 以此前缀开头的行自动跳过 */
  skipExamplePrefix?: string
  /** 表头行索引（0-based），默认 = skipRows - 1 */
  headerRowIndex?: number
  /** 是否按列索引解析（而非按表头名称），返回数组而非对象 */
  rawArrayMode?: boolean
}

/** 解析结果 */
export interface ParseResult<T = Record<string, any>> {
  rows: T[]
  headers: string[]
}

/* ── 核心函数 ── */

/**
 * 导出模板（含表头+说明+示例）
 */
export async function exportTemplate(options: ExportTemplateOptions): Promise<void> {
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const {
    columns,
    sheetName = '数据填写',
    fileName,
    categoryRow,
    categoryMerges,
    includeInstructions = false,
    instructionTitle,
    instructionRows,
    exampleRows,
    existingData,
    includeNoteRow = true,
  } = options

  // ── 填写说明 sheet（可选） ──
  if (includeInstructions) {
    const instrData: any[][] = [
      [instructionTitle || `${fileName.replace('.xlsx', '')} — 填写说明`],
      [],
      ['⚠ 重要提示：'],
      ['1. 请在"数据填写"工作表中填写数据，不要修改表头行'],
      ['2. 不要修改工作表名称，系统按名称识别'],
      ['3. 金额字段填数字，不要带逗号或货币符号'],
      ['4. 示例行导入时自动跳过，可删除或保留'],
    ]
    if (instructionRows) {
      instrData.push([], ...instructionRows)
    }
    instrData.push([], ['字段说明：'], ['列号', '字段名', '说明', '示例'])
    columns.forEach((c, i) => {
      instrData.push([String(i + 1), c.header, c.note || '', c.example || '-'])
    })
    const wsInstr = XLSX.utils.aoa_to_sheet(instrData)
    wsInstr['!cols'] = [{ wch: 6 }, { wch: 20 }, { wch: 50 }, { wch: 20 }]
    wsInstr['!merges'] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 3 } }]
    XLSX.utils.book_append_sheet(wb, wsInstr, '填写说明')
  }

  // ── 数据填写 sheet ──
  const allRows: any[][] = []

  // 分类行（可选）
  if (categoryRow) {
    allRows.push(categoryRow)
  }

  // 说明行（可选）
  if (includeNoteRow) {
    allRows.push(columns.map(c => c.note || ''))
  }

  // 表头行
  allRows.push(columns.map(c => c.header))

  // 数据行：优先使用现有数据，否则使用示例行
  if (existingData && existingData.length > 0) {
    allRows.push(...existingData)
  } else if (exampleRows && exampleRows.length > 0) {
    allRows.push(...exampleRows)
  }

  const wsData = XLSX.utils.aoa_to_sheet(allRows)
  wsData['!cols'] = columns.map(c => ({
    wch: c.width || Math.max(c.header.length * 2.5, 14),
  }))

  if (categoryMerges) {
    wsData['!merges'] = categoryMerges
  }

  XLSX.utils.book_append_sheet(wb, wsData, sheetName)
  XLSX.writeFile(wb, fileName)
  ElMessage.success('模板已导出')
}

/**
 * 导出数据到 Excel
 */
export async function exportData(options: ExportDataOptions): Promise<void> {
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const {
    data,
    columns,
    sheetName = '数据',
    fileName,
    extraHeaders,
    extraDataFn,
  } = options

  const headers = columns.map(c => c.header)
  if (extraHeaders) {
    headers.push(...extraHeaders)
  }

  const dataRows = data.map(row => {
    const base = columns.map(c => row[c.key] ?? '')
    if (extraDataFn) {
      base.push(...extraDataFn(row))
    }
    return base
  })

  const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  ws['!cols'] = headers.map(h => ({
    wch: Math.max(h.length * 2.5, 14),
  }))

  XLSX.utils.book_append_sheet(wb, ws, sheetName)
  XLSX.writeFile(wb, fileName)
  ElMessage.success('数据已导出')
}

/**
 * 解析上传的 Excel 文件
 *
 * @returns 按表头名称映射的行对象数组（默认），或原始数组（rawArrayMode）
 */
export async function parseFile(
  file: File,
  options: ParseFileOptions = {},
): Promise<ParseResult> {
  const XLSX = await import('xlsx')
  const {
    sheetName = '数据填写',
    skipRows = 1,
    skipExamplePrefix = '示例',
    headerRowIndex,
    rawArrayMode = false,
  } = options

  const buf = await file.arrayBuffer()
  const wb = XLSX.read(buf, { type: 'array' })

  // 查找目标 sheet
  let targetSheet = ''
  if (sheetName) {
    targetSheet = wb.SheetNames.find(n => n === sheetName) || ''
  }
  if (!targetSheet) {
    // 降级：取第一个 sheet（而非最后一个），多 sheet 文件时更符合预期
    targetSheet = wb.SheetNames[0]
  }

  const ws = wb.Sheets[targetSheet]
  if (!ws) {
    throw new Error(`未找到工作表"${sheetName || targetSheet}"`)
  }

  const jsonData: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1 })

  if (jsonData.length <= skipRows) {
    return { rows: [], headers: [] }
  }

  // 表头行
  const hdrIdx = headerRowIndex ?? (skipRows > 0 ? skipRows - 1 : 0)
  const headers: string[] = (jsonData[hdrIdx] || []).map((h: any) => String(h || '').trim())
  const cleanHeaders = headers.filter(h => h !== '')

  // 解析数据行
  const rows: Record<string, any>[] = []
  for (let i = skipRows; i < jsonData.length; i++) {
    const rawRow = jsonData[i]
    if (!rawRow || rawRow.length === 0) continue

    const firstCell = String(rawRow[0] || '').trim()
    if (!firstCell) continue

    // 跳过示例行
    if (skipExamplePrefix && firstCell.startsWith(skipExamplePrefix)) continue

    if (rawArrayMode) {
      // 原始数组模式：直接返回行数组
      rows.push(
        Object.fromEntries(rawRow.map((v: any, idx: number) => [String(idx), v])),
      )
    } else {
      // 对象模式：按表头映射
      const rowObj: Record<string, any> = {}
      cleanHeaders.forEach((header, colIdx) => {
        const val = rawRow[colIdx]
        rowObj[header] = val != null && val !== '' ? val : null
      })
      rows.push(rowObj)
    }
  }

  return { rows, headers: cleanHeaders }
}

/**
 * 处理 file input change 事件的便捷包装
 *
 * @param event - input change 事件
 * @param callback - 解析成功后的回调，接收 ParseResult
 * @param options - 解析选项
 */
export async function onFileSelected(
  event: Event,
  callback: (result: ParseResult) => void,
  options: ParseFileOptions = {},
): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  try {
    const result = await parseFile(file, options)
    callback(result)
  } catch (err: any) {
    ElMessage.error('解析失败：' + (err.message || '格式错误'))
  } finally {
    // 重置 input 以便重复选择同一文件
    input.value = ''
  }
}

/**
 * useExcelIO composable — 返回所有函数的便捷包装
 *
 * 用法：
 *   const { exportTemplate, exportData, parseFile, onFileSelected } = useExcelIO()
 */
export function useExcelIO() {
  return {
    exportTemplate,
    exportData,
    parseFile,
    onFileSelected,
  }
}
