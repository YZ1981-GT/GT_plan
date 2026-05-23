/**
 * useExcelIO — 统一 Excel 导入导出 composable [R3.5]
 *
 * 所有 worksheet 组件共用的 Excel 操作：
 *   exportTemplate(columns, sheetName, fileName)  — 导出空白模板（含表头+说明）
 *   exportData(data, columns, sheetName, fileName) — 导出数据到 Excel
 *   parseFile(file, options)                       — 解析上传的 Excel 文件，返回行数组
 *   onFileSelected(event, callback)                — 处理 file input change 事件
 *
 * 库选择（2026-05-22 升级，task 3.2 / C-2 真实生效）：
 *   导出（exportTemplate / exportData）：用 `xlsx-js-style@1.2.0` 写入完整 cell.s 样式
 *     （仿宋_GB2312 / Arial Narrow / 三线表边框；社区版 xlsx 不序列化 cell.s）
 *   解析（parseFile）：继续用 `xlsx@0.18.5`（解析无需样式，零额外依赖体积）
 *
 *   API 100% 兼容（xlsx-js-style 是 xlsx 的 fork），`book_new` / `aoa_to_sheet` /
 *   `writeFile` / `utils.encode_cell` 行为一致；其余 18 处 `import('xlsx')` 调用
 *   不动（只读 + 不写样式 = 用社区版即可）。
 */

import { ElMessage } from 'element-plus'

/**
 * 加载 xlsx-js-style 并兼容 CJS/ESM 互操作
 *
 * xlsx-js-style 是 CommonJS 模块，Vite 在 dev 模式下 `await import()` 返回
 * `{ default: 实际模块, utils: ..., ... }` 的 namespace 对象；
 * 部分构建器/Node 环境下又只有 `{ default: 实际模块 }` 形式。
 * 取 `mod.utils ?? mod.default?.utils` 都能命中。
 */
async function _loadXlsxStyle(): Promise<any> {
  const mod: any = await import('xlsx-js-style')
  // 优先用 namespace 顶层（Vite dev 模式）；否则解 default
  if (mod && mod.utils) return mod
  if (mod && mod.default && mod.default.utils) return mod.default
  return mod
}

async function _loadXlsxPlain(): Promise<any> {
  const mod: any = await import('xlsx')
  if (mod && mod.utils) return mod
  if (mod && mod.default && mod.default.utils) return mod.default
  return mod
}

/* ── 类型定义 ── */

/* ─── task 3.2 / C-2: 样式模板辅助函数 ─── */

/**
 * 计算字符串可视宽度（CJK 字符算 2，其余算 1），适用于 Excel 列宽自适应。
 */
export function computeColumnWidth(header: string, values: any[]): number {
  const visualWidth = (s: string): number => {
    let w = 0
    for (const ch of s) {
      const code = ch.codePointAt(0) || 0
      // CJK + 全角范围
      if (
        (code >= 0x4e00 && code <= 0x9fff) ||
        (code >= 0x3000 && code <= 0x303f) ||
        (code >= 0xff00 && code <= 0xffef)
      ) {
        w += 2
      } else {
        w += 1
      }
    }
    return w
  }
  let maxW = visualWidth(String(header || ''))
  for (const v of values) {
    if (v == null || v === '') continue
    const w = visualWidth(String(v))
    if (w > maxW) maxW = w
  }
  return Math.min(60, Math.max(8, maxW + 2))
}

/**
 * 判定列是否为数字列（≥80% 非空值为有限数字）
 */
export function isNumericColumn(values: any[]): boolean {
  let nonEmpty = 0
  let numeric = 0
  for (const v of values) {
    if (v == null || v === '') continue
    nonEmpty++
    if (typeof v === 'number' && Number.isFinite(v)) {
      numeric++
    } else if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) {
      numeric++
    }
  }
  if (nonEmpty === 0) return false
  return numeric / nonEmpty >= 0.8
}

const _STYLE_CHINESE_FONT = '仿宋_GB2312'
const _STYLE_NUMERIC_FONT = 'Arial Narrow'
const _STYLE_HEADER_SIZE = 11
const _STYLE_BODY_SIZE = 10
const _STYLE_TOP = { style: 'medium' as const, color: { rgb: '000000' } }
const _STYLE_MID = { style: 'thin' as const, color: { rgb: '000000' } }
const _STYLE_BOTTOM = { style: 'medium' as const, color: { rgb: '000000' } }

function _setCellStyle(ws: any, r: number, c: number, style: any, XLSX: any): void {
  const addr = XLSX.utils.encode_cell({ r, c })
  if (!ws[addr]) return
  ws[addr].s = { ...(ws[addr].s || {}), ...style }
}

/**
 * 应用 task 3.2 / C-2 样式模板（仿宋_GB2312 + Arial Narrow + 三线表 + 列宽自适应）
 *
 * @param opts.dataEndRowIdx 含；无数据行时传 -1
 */
export function applyExcelStyleTemplate(
  ws: any,
  XLSX: any,
  opts: {
    headerRowIdx: number
    dataStartRowIdx: number
    dataEndRowIdx: number
    columns: ExcelColumn[]
    dataMatrix: any[][]
    numericColumnKeys?: string[]
  },
): void {
  const { headerRowIdx, dataStartRowIdx, dataEndRowIdx, columns, dataMatrix, numericColumnKeys } = opts
  const explicitNumeric = new Set(numericColumnKeys || [])

  // 列宽 + 数字列检测
  const cols: Array<{ wch: number }> = []
  const colIsNumeric: boolean[] = []
  for (let c = 0; c < columns.length; c++) {
    const colDef = columns[c]
    const colVals = dataMatrix.map(row => row?.[c])
    const wch =
      colDef.width != null && colDef.width > 0
        ? colDef.width
        : computeColumnWidth(colDef.header || '', colVals)
    cols.push({ wch })
    colIsNumeric.push(explicitNumeric.has(colDef.key) || isNumericColumn(colVals))
  }
  ws['!cols'] = cols

  // 表头：仿宋加粗 + medium top + thin bottom
  for (let c = 0; c < columns.length; c++) {
    _setCellStyle(
      ws,
      headerRowIdx,
      c,
      {
        font: { name: _STYLE_CHINESE_FONT, sz: _STYLE_HEADER_SIZE, bold: true },
        alignment: { horizontal: 'center', vertical: 'middle' },
        border: { top: _STYLE_TOP, bottom: _STYLE_MID },
      },
      XLSX,
    )
  }

  // 数据行
  if (dataEndRowIdx >= dataStartRowIdx) {
    for (let r = dataStartRowIdx; r <= dataEndRowIdx; r++) {
      for (let c = 0; c < columns.length; c++) {
        const isLast = r === dataEndRowIdx
        const fontName = colIsNumeric[c] ? _STYLE_NUMERIC_FONT : _STYLE_CHINESE_FONT
        const style: any = {
          font: { name: fontName, sz: _STYLE_BODY_SIZE },
          alignment: {
            horizontal: colIsNumeric[c] ? 'right' : 'left',
            vertical: 'middle',
          },
        }
        if (isLast) style.border = { bottom: _STYLE_BOTTOM }
        _setCellStyle(ws, r, c, style, XLSX)
      }
    }
  } else {
    // 无数据行：表头同时承担三线表上+下边框
    for (let c = 0; c < columns.length; c++) {
      _setCellStyle(
        ws,
        headerRowIdx,
        c,
        { border: { top: _STYLE_TOP, bottom: _STYLE_BOTTOM } },
        XLSX,
      )
    }
  }
}

/* ── 列定义 ── */

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
  /** 是否应用样式模板（task 3.2 / C-2，默认 true） */
  applyStyles?: boolean
  /** 显式指定数字列 key（不指定则按 ≥80% 数字值自动检测） */
  numericColumnKeys?: string[]
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
  /** 是否应用样式模板（task 3.2 / C-2，默认 true） */
  applyStyles?: boolean
  /** 显式指定数字列 key */
  numericColumnKeys?: string[]
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
  // task 3.2 / C-2: 导出走 xlsx-js-style 写入 cell.s 样式
  const XLSX = await _loadXlsxStyle()
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
    applyStyles = true,
    numericColumnKeys,
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
  let curIdx = 0

  // 分类行（可选）
  if (categoryRow) {
    allRows.push(categoryRow)
    curIdx++
  }

  // 说明行（可选）
  if (includeNoteRow) {
    allRows.push(columns.map(c => c.note || ''))
    curIdx++
  }

  // 表头行
  const headerRowIdx = curIdx
  allRows.push(columns.map(c => c.header))
  curIdx++

  // 数据行：优先使用现有数据，否则使用示例行
  const dataStartRowIdx = curIdx
  let dataMatrix: any[][] = []
  if (existingData && existingData.length > 0) {
    allRows.push(...existingData)
    dataMatrix = existingData
  } else if (exampleRows && exampleRows.length > 0) {
    allRows.push(...exampleRows)
    dataMatrix = exampleRows
  }
  const dataEndRowIdx = dataStartRowIdx + dataMatrix.length - 1

  const wsData = XLSX.utils.aoa_to_sheet(allRows)

  if (applyStyles) {
    applyExcelStyleTemplate(wsData, XLSX, {
      headerRowIdx,
      dataStartRowIdx,
      dataEndRowIdx,
      columns,
      dataMatrix,
      numericColumnKeys,
    })
  } else {
    wsData['!cols'] = columns.map(c => ({
      wch: c.width || Math.max(c.header.length * 2.5, 14),
    }))
  }

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
  // task 3.2 / C-2: 导出走 xlsx-js-style 写入 cell.s 样式
  const XLSX = await _loadXlsxStyle()
  const wb = XLSX.utils.book_new()
  const {
    data,
    columns,
    sheetName = '数据',
    fileName,
    extraHeaders,
    extraDataFn,
    applyStyles = true,
    numericColumnKeys,
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

  if (applyStyles) {
    const fullCols: ExcelColumn[] = [
      ...columns,
      ...(extraHeaders || []).map(h => ({ key: `__extra_${h}`, header: h })),
    ]
    applyExcelStyleTemplate(ws, XLSX, {
      headerRowIdx: 0,
      dataStartRowIdx: 1,
      dataEndRowIdx: dataRows.length,
      columns: fullCols,
      dataMatrix: dataRows,
      numericColumnKeys,
    })
  } else {
    ws['!cols'] = headers.map(h => ({
      wch: Math.max(h.length * 2.5, 14),
    }))
  }

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
  const XLSX = await _loadXlsxPlain()
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
    targetSheet = wb.SheetNames.find((n: string) => n === sheetName) || ''
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
