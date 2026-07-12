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
      ['row_code', '行次编码（必填，不可修改已有行次的 code）— 系统识别用，如 BS-001、IS-001'],
      ['row_name', '项目名称（选填）— 仅供参考，导入时不使用'],
      ['formula', '公式表达式（必填）— 语法：TB(\'科目\', \'期末余额\') / ROW(\'行次\') / SUM_TB(...) / PREV(...) / WP(...)'],
      ['formula_type', '公式类型（必填）— auto_calc(自动运算) / logic_check(逻辑审核) / reasonability(合理性提示)'],
      ['description', '说明（选填）— 中文描述该公式的业务含义'],
      ['', ''],
      ['公式语法参考', ''],
      ['TB(科目, 字段)', '从试算表取数。字段：期末余额/期初余额/发生额/变动额。示例：TB(\'1001\', \'期末余额\')'],
      ['ROW(行次)', '引用本报表其他行次的值。示例：ROW(\'BS-027\') 即流动资产合计'],
      ['PREV(行次)', '引用上年同行次的值。示例：PREV(\'BS-002\') 即上年货币资金'],
      ['WP(底稿,sheet,坐标)', '引用底稿单元格。示例：WP(\'D2\',\'审定表D2-1\',\'审定数\')'],
      ['SUM_TB(科目范围)', '汇总多个科目。示例：SUM_TB(\'1001~1099\')'],
      ['', ''],
      ['注意事项', ''],
      ['1', '每行一个公式，按 row_code 匹配写入（已有公式会被覆盖）'],
      ['2', 'row_code 必须是系统中已存在的行次编码（如 BS-001~BS-129、IS-001~IS-034 等）'],
      ['3', '删除 formula 列值 = 清空该行公式'],
      ['4', '新增不存在的 row_code 行会被忽略'],
      ['5', '可以只填部分行（空行跳过），不需要填满全部'],
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

    if (rows.length) {
      // 有数据：导出当前节点的实际行次（含已有公式）
      for (const row of rows) {
        wsData.addRow([
          row.row_code || '',
          row.row_name || '',
          row.formula || '',
          row.formula_category || row.formula_type || 'auto_calc',
          row.formula_description || row.description || '',
        ])
      }
    } else {
      // 无数据：生成通用空白模板（示例行 + 提示）
      wsData.addRow(['BS-001', '（示例）流动资产：', '', 'auto_calc', '标题行，通常无公式'])
      wsData.addRow(['BS-002', '（示例）货币资金', "TB('1001', '期末余额')", 'auto_calc', '取试算表科目 1001 期末余额'])
      wsData.addRow(['BS-027', '（示例）流动资产合计', "ROW('BS-002') + ROW('BS-005') + ...", 'auto_calc', '合计行 = 各明细行之和'])
      wsData.addRow(['IS-001', '（示例）营业收入', "TB('6001', '发生额')", 'auto_calc', '损益类取发生额'])
      wsData.addRow(['', '', '', '', ''])
      wsData.addRow(['说明：', '请删除以上示例行，填入实际的 row_code 和公式', '', '', ''])
      wsData.addRow(['', 'row_code 可从公式管理中心左侧选中报表节点后查看', '', '', ''])
      wsData.addRow(['', '也可以先在节点中加载数据后再点"导出模板"获取含行次的版本', '', '', ''])
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
