/**
 * 合并导出：xlsx-js-style 多 sheet 写入
 *
 * Req 1 AC 4: 「合并导出」按钮把所有分组合并到单 xlsx 多 sheet
 * 每个 wp_code 的结果写入独立 sheet（sheet 名 = wp_code）
 */

import XLSX from 'xlsx-js-style'

export interface ExportSheetData {
  wpCode: string
  columns: string[]
  rows: Record<string, any>[]
}

/**
 * 将多个 wp_code 的查询结果合并导出为单个 xlsx 文件（多 sheet）
 */
export function exportBatchToXlsx(
  sheets: ExportSheetData[],
  filename: string = '批量查询结果.xlsx',
): void {
  const wb = XLSX.utils.book_new()

  for (const sheet of sheets) {
    // 构建 sheet 名（xlsx sheet 名最长 31 字符）
    const sheetName = sheet.wpCode.slice(0, 31)

    // 构建表头 + 数据行
    const header = sheet.columns
    const data = sheet.rows.map((row) =>
      header.map((col) => row[col] ?? '')
    )

    // 创建 worksheet
    const ws = XLSX.utils.aoa_to_sheet([header, ...data])

    // 设置列宽（自适应）
    ws['!cols'] = header.map((col) => ({
      wch: Math.max(col.length * 2, 12),
    }))

    // 表头样式：加粗 + 灰底
    for (let c = 0; c < header.length; c++) {
      const cellRef = XLSX.utils.encode_cell({ r: 0, c })
      if (ws[cellRef]) {
        ws[cellRef].s = {
          font: { bold: true },
          fill: { fgColor: { rgb: 'F5F5F5' } },
          alignment: { horizontal: 'center' },
        }
      }
    }

    XLSX.utils.book_append_sheet(wb, ws, sheetName)
  }

  // 写入并下载
  XLSX.writeFile(wb, filename)
}
