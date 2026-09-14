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
 *   `writeFile` / `utils.encode_cell` 行为一致。
 *
 * ## 🔴 本文件是全前端唯一允许 import Excel 库的生产文件
 *
 * spec: frontend-excel-io-single-entry-convergence
 *
 * `xlsx@0.18.5` 是 SheetJS 在 npm 上的最后一版（已撤出 npm 改 CDN 分发），带
 * CVE-2023-30533（prototype pollution）与 CVE-2024-22363（ReDoS），**修复版永远
 * 不会进 npm**。散点直连意味着每处读上传文件都是独立攻击面，故收敛到本文件，
 * 防护只做一次（见 `_BLOCKED_KEYS`）。
 *
 * 守卫 `__tests__/excelIoConvergence.spec.ts` 钉死「除本文件外零裸 import」。
 *
 * ### 迁移调用方时的三个显式关闭（行为等价铁律）
 *
 * 本文件的默认值会**主动改变产物**，机械迁移必破坏等价：
 * - `applyStyles` 默认 `true` → 给原本无样式的产物加仿宋 + 三线表
 * - `includeNoteRow` 默认 `true` → 在表头前插一行 note 行，全表行号下移
 * - 成功提示默认弹出 → 调用方自己也弹时出现重复弹窗
 *
 * ⇒ 迁移既有调用点时一律显式传 `applyStyles: false` + `includeNoteRow: false`
 *   + `successMessage: false`，除非该调用点原本就要这些效果。
 */

import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'

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

/**
 * 🔴 垂直居中必须写 `center`，不能写 `middle`（2026-08-14 实测修正）
 *
 * OOXML 的 `ST_VerticalAlignment` 只认 `top` / `center` / `bottom` /
 * `distributed` / `justify`。改造前这里写的是 `middle`（CSS 的写法），产出的
 * `styles.xml` 里是 `<alignment horizontal="center" vertical="middle"/>` ——
 * **非法值**。
 *
 * 后果不是「样式不生效」这么轻：Excel 会容忍并静默忽略，但严格读取器**拒绝打开
 * 整个文件**。实测 `openpyxl.load_workbook` 直接抛
 *   `ValueError: Value must be one of {'top','bottom','distributed','justify','center'}`
 *   `→ Unable to read workbook: could not read stylesheet`
 * 而本项目后端有 674 处 openpyxl —— 「前端导出模板 → 用户填 → 后端解析」这条路
 * 上，只要用户没在 Excel 里重存过（Excel 保存时会修正非法值），后端就读不了。
 *
 * 实证样本：`.playwright-mcp/审定表-审定表D2-1.xlsx`（2026-06-20 导出，早于本轮
 * 改动），openpyxl 至今打不开；同目录下本轮用 `applyStyles:false` 导出的两个文件
 * 正常。对照实验（同样内容只改这一个值）：`middle` → 打不开，`center` → 正常。
 *
 * 修它会让外观变化 —— 但方向是「让原本写坏的意图生效」：非法值被 Excel 忽略后
 * 用的是默认垂直对齐，改对后才真的垂直居中。守卫见 useExcelIO.spec.ts。
 */
const _STYLE_VERTICAL = 'center' as const
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
        alignment: { horizontal: 'center', vertical: _STYLE_VERTICAL },
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
            vertical: _STYLE_VERTICAL,
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
  /*
   * ⚠️ 曾有 `customInstructionSheet?: CustomInstructionSheet`（L1-3），2026-08-14 删除。
   *
   * 立项时判定它是「B2 函证组 12 文件无法迁移的硬阻塞」，实测**从未被用到**：
   * 那 14 个文件最后走的是 `exportMultiSheetData` + 纯 AOA 形态（L1-5），因为它们的
   * 说明 sheet 与数据 sheet 是同一批 `sheets[]` 里的两项，用多 sheet 形态更自然。
   * ⇒ L1-5 在功能上**覆盖**了 L1-3，留着就是设计冗余 + 零消费方 API。
   *
   * 若将来真需要「exportTemplate 带自定义说明」，直接用 exportMultiSheetData 的
   * AOA 形态即可，不必恢复此选项。
   */
  /**
   * 成功提示：省略 = 用默认文案「模板已导出」；string = 用该文案；false = 不弹。
   *
   * 存在的原因：部分调用方自行弹提示（如 queryExport.ts），封装内再弹一次会出现
   * 重复弹窗。省略时行为与改造前逐字相同。
   */
  successMessage?: string | false
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
  /** 成功提示：省略 = 默认文案「数据已导出」；string = 用该文案；false = 不弹 */
  successMessage?: string | false
}

/** 文件解析选项 */
export interface ParseFileOptions {
  /** 目标工作表名称；找不到时降级取**第一个** sheet（见 `_pickSheetName`） */
  sheetName?: string
  /**
   * 行数上限，默认 50000。超限时截断并回报 `truncatedRows`，不抛错、不 OOM。
   *
   * 存在的原因：上传文件的行数不可控，真实库里曾出现单份底稿 103 万行的情形。
   *
   * ⚠️ **口径**：这里数的是**跳过 `skipRows` 之后的数据行**（不含表头/说明行）。
   * 低层的 `readSheetAoa` / `readWorkbookAoa` 数的是**含表头的原始行**，
   * 因为它们不知道哪几行是表头 —— 同名不同义，传值时注意。
   */
  maxRows?: number
  /** 跳过前 N 行（分类行+说明行+表头行），默认 1（只有表头行） */
  skipRows?: number
  /** 以此前缀开头的行自动跳过 */
  skipExamplePrefix?: string
  /**
   * 是否要求首列非空才认这一行，默认 `true`（保持既有行为）。
   *
   * 🔴 这个默认值藏着一个**对很多表不成立的假设**：首列必有值。
   * 实际模板里首列常是「序号」，而填写说明往往写着「序号：自动生成（留空即可）」——
   * 此时用户留空序号、其余列填满的行会被**静默丢弃**，且不报任何错。
   *
   * 迁移调用方时若原实现是 `sheet_to_json(ws)`（不带 `header:1`），它**不做**首列
   * 非空检查，只跳过完全空行 ⇒ 必须传 `requireFirstCell: false` 才行为等价，
   * 并由调用方自己按「整行是否全空」过滤。
   */
  requireFirstCell?: boolean
  /** 表头行索引（0-based），默认 = skipRows - 1 */
  headerRowIndex?: number
  /** 是否按列索引解析（而非按表头名称），返回数组而非对象 */
  rawArrayMode?: boolean
}

/** 解析结果 */
export interface ParseResult<T = Record<string, any>> {
  rows: T[]
  headers: string[]
  /**
   * 被安全过滤掉的危险列头（`__proto__` / `constructor` / `prototype`）。
   *
   * 可选字段 ⇒ 既有 `{ rows, headers }` 解构不受影响。
   */
  blockedKeys?: string[]
  /** 因超过 `maxRows` 而被丢弃的行数；未截断时为 0 */
  truncatedRows?: number
}

/**
 * 原型污染防护：这三个列头一律不写入行对象。
 *
 * ## 为什么必须在这里拦
 *
 * `xlsx@0.18.5` 是 SheetJS 在 npm 上的最后一版（已撤出 npm 改 CDN 分发），带
 * CVE-2023-30533（prototype pollution，上游 0.19.3 修复），**修复版永远不会进 npm**。
 * `parseFile` 对象模式里 `rowObj[header] = ...` 的 `header` 直接来自用户上传文件的
 * 列头，列头为 `__proto__` 时这行就是污染写入点。
 *
 * 上游修不了 ⇒ 在我们自己的单一入口拦。
 */
const _BLOCKED_KEYS = new Set(['__proto__', 'constructor', 'prototype'])

/** 默认行数上限 */
const _DEFAULT_MAX_ROWS = 50000

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
    successMessage,
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
  _notifySuccess(successMessage, '模板已导出')
}

/**
 * 成功提示三态：`undefined` = 默认文案 / `string` = 自定义 / `false` = 不弹。
 *
 * 省略时与改造前逐字相同 ⇒ 既有调用方零回归。
 */
function _notifySuccess(msg: string | false | undefined, fallback: string): void {
  if (msg === false) return
  ElMessage.success(msg ?? fallback)
}

/**
 * 建数据工作簿（`exportData` 与 `exportToBytes` 的唯一共享实现）
 *
 * 🔴 **禁止把这段逻辑复制第二份**。两个导出入口必须同源，否则将来改样式模板
 * 或列宽算法时要改两处，正是「单一入口」要消除的漂移。
 *
 * @returns `{ XLSX, wb }` —— 调用方决定是 `writeFile` 落盘还是 `write` 取字节
 */
async function _buildDataWorkbook(options: ExportDataOptions): Promise<{ XLSX: any; wb: any }> {
  // task 3.2 / C-2: 导出走 xlsx-js-style 写入 cell.s 样式
  const XLSX = await _loadXlsxStyle()
  const wb = XLSX.utils.book_new()
  const {
    data,
    columns,
    sheetName = '数据',
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

  // 两个分支都要用（样式模板算列宽 / fallback 也要尊重 width），故提到外层
  const fullCols: ExcelColumn[] = [
    ...columns,
    ...(extraHeaders || []).map(h => ({ key: `__extra_${h}`, header: h })),
  ]

  if (applyStyles) {
    applyExcelStyleTemplate(ws, XLSX, {
      headerRowIdx: 0,
      dataStartRowIdx: 1,
      dataEndRowIdx: dataRows.length,
      columns: fullCols,
      dataMatrix: dataRows,
      numericColumnKeys,
    })
  } else {
    // `applyStyles: false` 分支同样尊重 `columns[].width`。
    //
    // 改造前这里用 `headers.map(h => Math.max(h.length * 2.5, 14))`，**忽略了 width** ——
    // 而 `exportTemplate` 的同一分支早就写着 `c.width || Math.max(...)`。两个入口口径
    // 不一致，导致「关掉样式模板但保留原有列宽」这个迁移必需的组合无法表达
    // （调用方传了 width 也不生效）。此处对齐 exportTemplate 的既有行为。
    ws['!cols'] = fullCols.map(c => ({
      wch: c.width || Math.max(c.header.length * 2.5, 14),
    }))
  }

  XLSX.utils.book_append_sheet(wb, ws, sheetName)
  return { XLSX, wb }
}

/**
 * 导出数据到 Excel（触发浏览器下载）
 */
export async function exportData(options: ExportDataOptions): Promise<void> {
  const { XLSX, wb } = await _buildDataWorkbook(options)
  XLSX.writeFile(wb, options.fileName)
  _notifySuccess(options.successMessage, '数据已导出')
}

/**
 * 导出数据为字节（不触发下载、不弹提示）
 *
 * 供需要自行处理产物的调用方使用（上传、拼 ZIP、走别的分发路径等）。
 * 与 `exportData` 共用 `_buildDataWorkbook` ⇒ 两者产出的工作簿结构一致。
 */
export async function exportToBytes(
  options: Omit<ExportDataOptions, 'fileName'> & { fileName?: string },
): Promise<Uint8Array> {
  const { XLSX, wb } = await _buildDataWorkbook({
    ...options,
    fileName: options.fileName ?? 'unused.xlsx',
  })
  const out = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
  return new Uint8Array(out)
}

/**
 * 多 sheet 导出：纯 AOA 形态的 sheet 定义
 *
 * 用于本质就是二维数组、无法用 `columns + data` 表达的 sheet：
 * - 只有表头行的空模板 sheet（`[headers]`，无数据行）
 * - 纯文本说明 sheet（`[['标题'], [''], ['【列名请勿修改】…']]`）
 * - 表头 + 单条示例行的清单 sheet
 *
 * 存在的原因：函证组 14 个底稿一次导出 2~6 个 sheet，其中混着上述三类。
 * 硬凑成 `columns + data` 既失真又要为「说明文本」编造假列名 —— 那会让产物
 * 偏离原样（违反行为等价），也让代码更难读。
 */
export interface ExcelAoaSheetDef {
  sheetName: string
  /** 原样写入的二维数组 */
  rows: any[][]
  /** 列宽；省略则不设置 `!cols` */
  colWidths?: Array<{ wch: number }>
}

/** 多 sheet 导出：结构化（columns + data）形态的 sheet 定义 */
export interface ExcelColumnSheetDef {
  sheetName: string
  columns: ExcelColumn[]
  data: Record<string, any>[]
  numericColumnKeys?: string[]
}

/**
 * 多 sheet 导出：单个 sheet 定义（两种形态之一）
 *
 * 判别式：带 `rows` 字段 ⇒ 纯 AOA；否则按 `columns + data` 处理。
 * 既有调用方全部是后者，故此改动向后兼容。
 */
/**
 * 多 sheet 导出：对象数组形态的 sheet 定义（走 `json_to_sheet`）
 *
 * 为什么不让调用方自己转成 AOA：`json_to_sheet` 收集的表头是**所有**对象键的
 * 并集（按首次出现顺序），不是只看第一个对象。手写 `Object.keys(data[0])` 在对象
 * 键不齐时会**静默漏列**，且空数组时直接抛错。既有调用方（ReportLineMappingDialog
 * 的三个 sheet、LedgerBalanceTreeView）都是 `json_to_sheet(objArray)`，
 * 原样透传才是等价的。
 */
export interface ExcelJsonSheetDef {
  /** sheet 名（超 31 字符自动截断） */
  sheetName: string
  /** 原样交给 json_to_sheet 的对象数组 */
  json: Record<string, any>[]
  /** 列宽，原样写入 `!cols` */
  colWidths?: { wch: number }[]
}

export type ExcelMultiSheetDef = ExcelColumnSheetDef | ExcelAoaSheetDef | ExcelJsonSheetDef

/** 类型守卫：是否为对象数组形态 */
function _isJsonSheet(s: ExcelMultiSheetDef): s is ExcelJsonSheetDef {
  return Array.isArray((s as ExcelJsonSheetDef).json)
}

/** 类型守卫：是否为纯 AOA 形态 */
function _isAoaSheet(s: ExcelMultiSheetDef): s is ExcelAoaSheetDef {
  return Array.isArray((s as ExcelAoaSheetDef).rows)
}

/** 多 sheet 导出选项（如 I2-5 构成/同行/人均同期/人均同行/说明） */
export interface ExportMultiSheetOptions {
  sheets: ExcelMultiSheetDef[]
  fileName: string
  applyStyles?: boolean
  /** 成功提示：省略 = 默认文案「数据已导出」；string = 用该文案；false = 不弹 */
  successMessage?: string | false
}

/**
 * 建多 sheet 工作簿（`exportMultiSheetData` 与 `exportMultiSheetToBytes` 的唯一共享实现）
 *
 * 🔴 同 `_buildDataWorkbook`：禁止复制第二份。
 */
async function _buildMultiSheetWorkbook(
  options: Omit<ExportMultiSheetOptions, 'fileName'>,
): Promise<{ XLSX: any; wb: any }> {
  const XLSX = await _loadXlsxStyle()
  const wb = XLSX.utils.book_new()
  const { sheets, applyStyles = true } = options

  for (const sheet of sheets) {
    // ── 对象数组形态：原样交给 json_to_sheet（表头由它按键并集生成）──
    if (_isJsonSheet(sheet)) {
      const ws = XLSX.utils.json_to_sheet(sheet.json)
      if (sheet.colWidths) {
        ws['!cols'] = sheet.colWidths
      }
      XLSX.utils.book_append_sheet(wb, ws, sheet.sheetName.slice(0, 31))
      continue
    }

    // ── 纯 AOA 形态：原样写入，不套样式模板、不算自适应列宽 ──
    if (_isAoaSheet(sheet)) {
      const ws = XLSX.utils.aoa_to_sheet(sheet.rows)
      if (sheet.colWidths) {
        ws['!cols'] = sheet.colWidths
      }
      XLSX.utils.book_append_sheet(wb, ws, sheet.sheetName.slice(0, 31))
      continue
    }

    const { sheetName, columns, data, numericColumnKeys } = sheet
    const headers = columns.map(c => c.header)
    const dataRows = data.map(row => columns.map(c => row[c.key] ?? ''))
    const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows])

    if (applyStyles) {
      applyExcelStyleTemplate(ws, XLSX, {
        headerRowIdx: 0,
        dataStartRowIdx: 1,
        dataEndRowIdx: dataRows.length,
        columns,
        dataMatrix: dataRows,
        numericColumnKeys,
      })
    } else {
      // 同 exportData：fallback 也尊重 columns[].width
      ws['!cols'] = columns.map(c => ({
        wch: c.width || Math.max(c.header.length * 2.5, 14),
      }))
    }

    XLSX.utils.book_append_sheet(wb, ws, sheetName.slice(0, 31))
  }

  return { XLSX, wb }
}

/**
 * 导出多个 sheet 到同一个 Excel 文件（如 I2-5 构成/同行/人均同期/人均同行/说明）
 */
export async function exportMultiSheetData(options: ExportMultiSheetOptions): Promise<void> {
  const { XLSX, wb } = await _buildMultiSheetWorkbook(options)
  XLSX.writeFile(wb, options.fileName)
  _notifySuccess(options.successMessage, '数据已导出')
}

/**
 * 导出多 sheet 为字节（不触发下载、不弹提示）
 */
export async function exportMultiSheetToBytes(
  options: Omit<ExportMultiSheetOptions, 'fileName' | 'successMessage'>,
): Promise<Uint8Array> {
  const { XLSX, wb } = await _buildMultiSheetWorkbook(options)
  const out = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
  return new Uint8Array(out)
}

/**
 * 低层读取选项 —— 透传 SheetJS 的关键行为开关
 *
 * ## 为什么需要「低层」这一层
 *
 * `parseFile` 是**带业务约定**的高层 API：固定表头行、跳示例行、空值归一为 `null`。
 * 这套约定适合函证组那类「表头固定在第一行、列名直接当键」的底稿。
 *
 * 但 H/I 循环的折旧/摊销/减值 composable 是另一种形态：
 * - 自己在前 10 行里**自动定位表头行**（按映射字段数打分），`parseFile` 的固定表头模型表达不了
 * - 显式传 `defval: ''`（空单元格填空串），而 `parseFile` 归一为 `null` ——
 *   下游若用 `??` 取默认值，`''` 与 `null` 结果不同，是会静默改数的差异
 * - 有的还要 `raw: false`（数值/日期返回格式化字符串）与 `cellDates: true`
 *
 * 把这些开关全塞进 `parseFile` 会让它变成一个「什么都能干因而什么都不保证」的函数。
 * 故另开低层薄封装：职责只有一个 —— **把库调用收敛进单一入口**，语义与直接调
 * SheetJS 逐项相同。
 */
export interface ReadSheetOptions {
  /** 目标 sheet 名（精确匹配）；找不到时降级取第一个 */
  sheetName?: string
  /** 透传 `XLSX.read` 的 `cellDates`：true 时日期单元格返回 Date 而非序列号 */
  cellDates?: boolean
  /** 透传 `sheet_to_json` 的 `defval`：空单元格的填充值（省略则由 SheetJS 决定，即跳过该格） */
  defval?: any
  /** 透传 `sheet_to_json` 的 `raw`：false 时返回格式化字符串而非原始值 */
  raw?: boolean
  /**
   * 透传 `sheet_to_json` 的 `blankrows`：false 时丢弃全空行
   *
   * 注意默认值随 `header` 而变：`header:1`（AOA 模式）下 SheetJS 默认**保留**空行，
   * 故 `GtCustomWpBatchDialog` 显式传 `false`。省略时不传该键，行为交给 SheetJS 决定。
   */
  blankrows?: boolean
  /** 行数上限，默认 50000；超限截断并回报 */
  maxRows?: number
}

/** 低层读取结果 */
export interface ReadSheetResult<T> {
  /** 实际读取的 sheet 名 */
  sheetName: string
  rows: T[]
  /** 因超过 `maxRows` 被丢弃的行数 */
  truncatedRows: number
  /** 被安全过滤掉的危险列头（仅对象模式有意义） */
  blockedKeys?: string[]
}

/**
 * 按 `sheetName` 精确匹配 → 第一个的顺序定位 sheet（低层与 parseFile 共用口径）
 *
 * ⚠️ 曾有第三级 `sheetMatcher`（谓词，优先级最高，L1-2），2026-08-14 删除。
 * 立项时判定它是「ShareChangeSheet 按『含公司名且含净资产』模糊定位」的硬前置，
 * 实测**从未被用到**：那个文件要在「公司数 × 3」个 sheet 间逐家匹配，单 sheet
 * 定位表达不了，最后走的是 `readWorkbookAoa`（L1-9，整簿读后调用方自己挑）。
 * ⇒ L1-9 在功能上**覆盖**了 L1-2。需要模糊/多 sheet 定位的场景一律用 readWorkbookAoa。
 */
function _pickSheetName(wb: any, sheetName?: string): string {
  const names: string[] = wb.SheetNames || []
  if (sheetName) {
    const hit = names.find((n: string) => n === sheetName)
    if (hit) return hit
  }
  return names[0]
}

/**
 * 低层：读成原始二维数组（AOA）
 *
 * 等价于 `XLSX.read(buf, { type:'array', cellDates })` +
 * `XLSX.utils.sheet_to_json(sheet, { header: 1, defval, raw })`。
 *
 * 用于调用方需要自己定位表头行 / 自己做列映射的场景。
 */
export async function readSheetAoa(
  file: File,
  options: ReadSheetOptions = {},
): Promise<ReadSheetResult<any[]>> {
  const XLSX = await _loadXlsxPlain()
  const { sheetName, cellDates, defval, raw, blankrows, maxRows = _DEFAULT_MAX_ROWS } = options

  const buf = await file.arrayBuffer()
  const wb = XLSX.read(buf, cellDates === undefined ? { type: 'array' } : { type: 'array', cellDates })

  const picked = _pickSheetName(wb, sheetName)
  const ws = picked ? wb.Sheets[picked] : undefined
  if (!ws) {
    return { sheetName: picked || '', rows: [], truncatedRows: 0 }
  }

  const jsonOpts: Record<string, any> = { header: 1 }
  if (defval !== undefined) jsonOpts.defval = defval
  if (raw !== undefined) jsonOpts.raw = raw
  if (blankrows !== undefined) jsonOpts.blankrows = blankrows

  const all: any[][] = XLSX.utils.sheet_to_json(ws, jsonOpts)
  const rows = all.slice(0, maxRows)
  return { sheetName: picked, rows, truncatedRows: Math.max(0, all.length - rows.length) }
}

/* ══════════════════════════════════════════════════════════════════════════
 * ExcelJS 侧入口（L1-10）
 *
 * ## 为什么单一入口要收两个引擎，而不是把 exceljs 全换成 SheetJS
 *
 * 收敛的目标是「库调用只在一处、CVE 与版本统一管控、将来换库只改一个文件」，
 * **不是**「全项目必须用同一个库」。把 4 个 exceljs 文件强行改成 SheetJS 会引入
 * 五处静默错列风险（2026-08-12 实测，见下），而这些风险换不来任何安全收益 ——
 * exceljs 是独立实现，不带 xlsx 那两个永不修复的 CVE。
 *
 * ### 实测到的 ExcelJS ↔ SheetJS 语义差异（换引擎就必须逐条对齐）
 *
 * | 差异点            | ExcelJS                      | SheetJS AOA                  |
 * | ----------------- | ---------------------------- | ---------------------------- |
 * | 中间整空行        | `eachRow` **跳过**           | **保留**（给 `[]`）          |
 * | `row.values`      | **1-based**（[0] 是 null）   | 0-based                      |
 * | 尾部缺列          | 不补齐                       | 传 `defval` 会**补齐到最宽** |
 * | 行内空单元格      | `eachCell` **不产生键**      | 给 `undefined` / `''`        |
 * | 找不到 sheet      | `getWorksheet()` → undefined | `readSheetAoa` **降级取第一个** |
 *
 * 还有一条硬缺失：**xlsx-js-style 的写入端不保留冻结窗格**（实测：ExcelJS 读回
 * `state:"normal"`，而 ExcelJS 自写自读是 `state:"frozen"`）。`exportFormulaTemplate.ts`
 * 依赖 `views:[{state:'frozen',ySplit:1}]`，换引擎必然丢功能。
 *
 * ## 形态：回调式
 *
 * 库的 import 在这里，建表 / 解析逻辑仍留在调用方回调里 —— 故调用方语义
 * **逐字不变**，严格等价自动成立。这两个函数不做数据加工，只做「加载库 + 交出
 * 工作簿 + 收口产物」。
 * ══════════════════════════════════════════════════════════════════════════ */

/** 动态加载 exceljs；兼容 CJS/ESM 两种 default 包裹形态 */
async function _loadExcelJs(): Promise<any> {
  const mod: any = await import('exceljs')
  // 有的打包形态下 Workbook 挂在 default 上
  if (mod && mod.Workbook) return mod
  if (mod && mod.default && mod.default.Workbook) return mod.default
  return mod
}

/**
 * ExcelJS 侧导出：交出一个空工作簿，建表逻辑留在调用方
 *
 * 用于 SheetJS 无法等价表达的产物（目前只有冻结窗格一项），以及不值得为收敛
 * 承担换引擎错列风险的既有文件。
 *
 * **不是回调式**：调用方需要在 `writeBuffer` **之前**做判断（如 B23 的
 * 「0 个 sheet 就走 warning 分支而不是导出」——空工作簿调 writeBuffer 会抛错，
 * 回调式封装会把 warning 变成 error，不等价）。返回工作簿本体，调用方逐行不变。
 */
export async function createExcelJsWorkbook(): Promise<{
  wb: any
  ExcelJS: any
  toBuffer: () => Promise<ArrayBuffer>
}> {
  const ExcelJS = await _loadExcelJs()
  const wb = new ExcelJS.Workbook()
  return { wb, ExcelJS, toBuffer: () => wb.xlsx.writeBuffer() }
}

/**
 * ExcelJS 侧读取：解析成 ExcelJS Workbook 交给调用方
 *
 * 接受 `File` 或已拿到的 `ArrayBuffer`（D2TabAnalysis 走 FileReader，
 * 到手的是 ArrayBuffer 而非 File）。
 */
export async function loadExcelJsWorkbook(source: File | Blob | ArrayBuffer | Uint8Array): Promise<any> {
  const ExcelJS = await _loadExcelJs()
  const wb = new ExcelJS.Workbook()
  // 🔴 不能用 `source instanceof ArrayBuffer` 分流：ExcelJS 的 writeBuffer() 返回的是
  // Buffer（Node/jsdom 下），它**不是** ArrayBuffer 的实例，会被误判成 File 分支而
  // 报「source.arrayBuffer is not a function」。改按「有没有 arrayBuffer 方法」分流：
  // File / Blob 走取字节，其余（ArrayBuffer / Buffer / Uint8Array）原样交给 load —— 
  // ExcelJS 的 load 本就都接受。
  const buf =
    typeof (source as any)?.arrayBuffer === 'function'
      ? await (source as Blob).arrayBuffer()
      : source
  await wb.xlsx.load(buf as any)
  return wb
}

/** 整簿读取结果 */
export interface ReadWorkbookResult {
  /** sheet 名，保持工作簿内顺序 */
  sheetNames: string[]
  /** sheet 名 → 该 sheet 的 AOA */
  sheets: Record<string, any[][]>
  /**
   * 各 sheet 因 `maxRows` 被丢弃的行数（只列真正被截断的 sheet，未截断的不出现）
   *
   * 🔴 R4.3 要求「超限时截断并**回报**，不静默丢数据」。改造前本函数是四个读入口里
   * 唯一**静默截断**的（2026-08-14 复盘查出）—— 调用方拿到少了行的数据却无从知晓。
   */
  truncatedRows: Record<string, number>
}

/**
 * 低层：一次解析，返回**全部** sheet 的 AOA
 *
 * 用于「跨 sheet 匹配导入」场景 —— 调用方需要按自己的规则在多个 sheet 之间挑选
 * （如合并工作底稿按「含公司名且含净资产」逐家匹配，一份文件里有
 * 公司数 × 3 个 sheet）。
 *
 * 为什么不让调用方多次调 `readSheetAoa`：那会对同一份文件重复
 * `arrayBuffer()` + `XLSX.read()` N 次（N = 公司数 × 3）。原实现只 read 一次，
 * 重复解析既慢又不等价于原行为。
 */
export async function readWorkbookAoa(
  file: File,
  options: Omit<ReadSheetOptions, 'sheetName'> = {},
): Promise<ReadWorkbookResult> {
  const XLSX = await _loadXlsxPlain()
  const { cellDates, defval, raw, blankrows, maxRows = _DEFAULT_MAX_ROWS } = options

  const buf = await file.arrayBuffer()
  const wb = XLSX.read(buf, cellDates === undefined ? { type: 'array' } : { type: 'array', cellDates })

  const jsonOpts: Record<string, any> = { header: 1 }
  if (defval !== undefined) jsonOpts.defval = defval
  if (raw !== undefined) jsonOpts.raw = raw
  if (blankrows !== undefined) jsonOpts.blankrows = blankrows

  const sheetNames: string[] = [...(wb.SheetNames || [])]
  const sheets: Record<string, any[][]> = {}
  const truncatedRows: Record<string, number> = {}
  for (const name of sheetNames) {
    const ws = wb.Sheets[name]
    if (!ws) {
      sheets[name] = []
      continue
    }
    const all = XLSX.utils.sheet_to_json(ws, jsonOpts) as any[][]
    sheets[name] = all.slice(0, maxRows)
    // R4.3：截断必须回报，不静默丢数据。只记真正被截断的 sheet。
    if (all.length > maxRows) truncatedRows[name] = all.length - maxRows
  }

  return { sheetNames, sheets, truncatedRows }
}

/**
 * 低层：读成对象数组（键取表头行的列名）
 *
 * 等价于 `XLSX.read(...)` + `XLSX.utils.sheet_to_json(sheet, { defval, raw })`，
 * **额外做原型污染防护**（这正是收敛到单一入口的价值：防护只写一处）。
 */
export async function readSheetObjects<T = Record<string, any>>(
  file: File,
  options: ReadSheetOptions = {},
): Promise<ReadSheetResult<T>> {
  const XLSX = await _loadXlsxPlain()
  const { sheetName, cellDates, defval, raw, blankrows, maxRows = _DEFAULT_MAX_ROWS } = options

  const buf = await file.arrayBuffer()
  const wb = XLSX.read(buf, cellDates === undefined ? { type: 'array' } : { type: 'array', cellDates })

  const picked = _pickSheetName(wb, sheetName)
  const ws = picked ? wb.Sheets[picked] : undefined
  if (!ws) {
    return { sheetName: picked || '', rows: [], truncatedRows: 0, blockedKeys: [] }
  }

  const jsonOpts: Record<string, any> = {}
  if (defval !== undefined) jsonOpts.defval = defval
  if (raw !== undefined) jsonOpts.raw = raw
  if (blankrows !== undefined) jsonOpts.blankrows = blankrows

  const all: Record<string, any>[] = XLSX.utils.sheet_to_json(ws, jsonOpts)
  const sliced = all.slice(0, maxRows)

  // 原型污染防护：剔除危险列头。
  // 注意 SheetJS 在普通对象上写 `obj['__proto__'] = v` 是静默无效的，故 `__proto__`
  // 通常不会出现在自有键里；但 `constructor` / `prototype` 会。三键统一过滤。
  const blockedKeys: string[] = []
  const rows = sliced.map((r) => {
    const bare: Record<string, any> = Object.create(null)
    for (const k of Object.keys(r)) {
      if (_BLOCKED_KEYS.has(k)) {
        if (!blockedKeys.includes(k)) blockedKeys.push(k)
        continue
      }
      bare[k] = r[k]
    }
    return { ...bare } as T
  })

  return { sheetName: picked, rows, truncatedRows: Math.max(0, all.length - sliced.length), blockedKeys }
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
    maxRows = _DEFAULT_MAX_ROWS,
    skipRows = 1,
    skipExamplePrefix = '示例',
    headerRowIndex,
    rawArrayMode = false,
    requireFirstCell = true,
  } = options

  const buf = await file.arrayBuffer()
  const wb = XLSX.read(buf, { type: 'array' })

  // ── 查找目标 sheet ──
  // 优先级：sheetName（精确）→ 第一个。与低层读取共用 `_pickSheetName` 的口径。
  // （曾有第三级 sheetMatcher 谓词，2026-08-14 删除 —— 见 `_pickSheetName` 的说明。）
  const targetSheet = _pickSheetName(wb, sheetName)

  const ws = wb.Sheets[targetSheet]
  if (!ws) {
    throw new Error(`未找到工作表"${sheetName || targetSheet}"`)
  }

  const jsonData: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1 })

  if (jsonData.length <= skipRows) {
    return { rows: [], headers: [], blockedKeys: [], truncatedRows: 0 }
  }

  // 表头行
  const hdrIdx = headerRowIndex ?? (skipRows > 0 ? skipRows - 1 : 0)
  const headers: string[] = (jsonData[hdrIdx] || []).map((h: any) => String(h || '').trim())

  // ── 列头筛选 + 原型污染防护（对象模式专用）──
  //
  // 🔴 **必须保留原始列索引**。改造前是 `headers.filter(h => h !== '')` 后用
  // filter 结果的下标去取 `rawRow[colIdx]` —— 这是一处**既有缺陷**：表头行中间
  // 出现空列时（如 `['A', '', 'B']`），`B` 会取到空列的值而非自己的值，整行右侧
  // 全部错位。加入危险键过滤会让该缺陷从「仅空列头触发」扩大到「危险列头也触发」，
  // 故一并修正为按 `{ header, colIdx }` 配对，colIdx 始终是原始列索引。
  //
  // cleanHeaders 直接来自用户上传文件，会被当作行对象的键使用，
  // `__proto__` 等键必须在这里剔除，而不是让调用方各自防护。
  const blockedKeys: string[] = []
  const headerEntries: Array<{ header: string; colIdx: number }> = []
  headers.forEach((h, i) => {
    if (h === '') return
    if (_BLOCKED_KEYS.has(h)) {
      if (!blockedKeys.includes(h)) blockedKeys.push(h)
      return
    }
    headerEntries.push({ header: h, colIdx: i })
  })
  const cleanHeaders = headerEntries.map(e => e.header)

  // 解析数据行
  const rows: Record<string, any>[] = []
  let truncatedRows = 0
  for (let i = skipRows; i < jsonData.length; i++) {
    const rawRow = jsonData[i]
    if (!rawRow || rawRow.length === 0) continue

    const firstCell = String(rawRow[0] || '').trim()
    // 首列非空检查（可关闭）：模板首列常是「序号」且允许留空，
    // 此时若强制要求首列非空会静默丢行。见 ParseFileOptions.requireFirstCell。
    if (requireFirstCell && !firstCell) continue
    // requireFirstCell 关闭时仍须跳过**整行全空**的行，否则会产出一堆空对象
    if (!requireFirstCell && rawRow.every((v: any) => v == null || String(v).trim() === '')) continue

    // 跳过示例行
    if (skipExamplePrefix && firstCell.startsWith(skipExamplePrefix)) continue

    // 行数上限：截断而非抛错，被丢弃的条数回报给调用方
    if (rows.length >= maxRows) {
      truncatedRows += 1
      continue
    }

    if (rawArrayMode) {
      // 原始数组模式：键是数字下标，不受用户列头控制 ⇒ 无需原型污染防护。
      // 🔴 请勿「顺手也给这个分支加一遍」—— 加了只会让键名语义变形。
      rows.push(
        Object.fromEntries(rawRow.map((v: any, idx: number) => [String(idx), v])),
      )
    } else {
      // 对象模式：按表头映射（colIdx 为原始列索引，见上方 headerEntries 的说明）。
      // 用 Object.create(null) 建对象 ⇒ 即使有键绕过 _BLOCKED_KEYS 也无原型可污染；
      // 再 { ...o } 转回普通对象 ⇒ 调用方的 Object.keys / 展开 / JSON.stringify 行为不变。
      const bare: Record<string, any> = Object.create(null)
      for (const { header, colIdx } of headerEntries) {
        const val = rawRow[colIdx]
        bare[header] = val != null && val !== '' ? val : null
      }
      rows.push({ ...bare })
    }
  }

  return { rows, headers: cleanHeaders, blockedKeys, truncatedRows }
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
    handleApiError(err, '解析')
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
    exportToBytes,
    exportMultiSheetData,
    exportMultiSheetToBytes,
    parseFile,
    readSheetAoa,
    readSheetObjects,
    readWorkbookAoa,
    createExcelJsWorkbook,
    loadExcelJsWorkbook,
    onFileSelected,
  }
}
