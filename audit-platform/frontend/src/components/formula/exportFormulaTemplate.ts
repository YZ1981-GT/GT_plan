/**
 * exportFormulaTemplate — 导出公式模板为 Excel（含编制说明 sheet）
 *
 * 独立文件避免在巨型 FormulaManagerDialog.vue 中动态导入 exceljs
 * 导致 Vite import-analysis 解析失败。
 */
import { ElMessage } from 'element-plus'

interface FormulaRow {
  row_code?: string
  row_name?: string
  formula?: string
  formula_category?: string
  formula_type?: string
  formula_description?: string
  description?: string
}

export async function exportFormulaTemplate(
  rows: FormulaRow[],
  selectedNodeKey: string,
  selectedPath: string,
): Promise<void> {
  if (!rows.length) {
    ElMessage.warning('当前节点无行次数据，请先选择一个报表节点')
    return
  }

  try {
    const ExcelJS = await import(/* @vite-ignore */ 'exceljs')
    const wb = new ExcelJS.Workbook()

    // ── Sheet 1: 编制说明 ──
    const wsGuide = wb.addWorksheet('编制说明')
    wsGuide.columns = [
      { header: '项目', width: 20 },
      { header: '说明', width: 80 },
    ]
    wsGuide.addRows([
      ['文件用途', '公式管理模板 — 在 Excel 中编辑公式后，通过公式管理中心的"Excel导入"按钮回导'],
      ['当前节点', selectedPath],
      ['报表类型', selectedNodeKey],
      ['导出时间', new Date().toLocaleString('zh-CN')],
      ['', ''],
      ['列说明', ''],
      ['row_code', '行次编码（不可修改）— 系统识别用'],
      ['row_name', '项目名称（不可修改）— 仅供参考'],
      ['formula', '公式表达式 — 可编辑。语法：TB(\'科目\', \'期末余额\') / ROW(\'行次\') / SUM_TB(...) 等'],
      ['formula_type', '公式类型 — auto_calc(自动运算) / logic_check(逻辑审核) / reasonability(合理性提示)'],
      ['description', '说明 — 可编辑。中文描述该公式的业务含义'],
      ['', ''],
      ['注意事项', ''],
      ['1', '不要修改 row_code 列，否则导入时无法匹配'],
      ['2', '公式语法参考 ACNR grammar_v1：TB(科目,字段) / ROW(行次) / PREV(行次) / WP(底稿,sheet,坐标)'],
      ['3', '删除 formula 列值 = 清空该行公式；新增行无效（只能修改已有行次）'],
      ['4', '导入时会覆盖已有公式（按 row_code 匹配）'],
    ])
    wsGuide.getRow(1).font = { bold: true }

    // ── Sheet 2: 公式数据 ──
    const wsData = wb.addWorksheet('公式数据')
    wsData.columns = [
      { header: 'row_code', width: 12 },
      { header: 'row_name', width: 30 },
      { header: 'formula', width: 60 },
      { header: 'formula_type', width: 16 },
      { header: 'description', width: 40 },
    ]
    for (const row of rows) {
      wsData.addRow([
        row.row_code || '',
        row.row_name || '',
        row.formula || '',
        row.formula_category || row.formula_type || 'auto_calc',
        row.formula_description || row.description || '',
      ])
    }
    wsData.getRow(1).font = { bold: true }
    wsData.views = [{ state: 'frozen', ySplit: 1 }]

    // 下载
    const buffer = await wb.xlsx.writeBuffer()
    const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `公式模板_${selectedNodeKey}_${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('公式模板已导出，编辑后可通过"Excel导入"回导')
  } catch (e: any) {
    ElMessage.error('导出公式模板失败：' + (e?.message || '未知错误'))
  }
}
