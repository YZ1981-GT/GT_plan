import { describe, it, expect, vi, beforeEach } from 'vitest'
import { sanitizeExportName } from '../queryExport'

/**
 * ## 为什么这个文件的 mock 层从「底层库」上移到「useExcelIO」
 *
 * spec: frontend-excel-io-single-entry-convergence（B1 批迁移）
 *
 * 改造前 `queryExport.ts` 自己 `await import('xlsx')` 手搭 `aoa_to_sheet`，所以本文件
 * mock `xlsx` 并从 `_sheets` 里取 AOA 断言。迁移到 `useExcelIO.exportData` 后，写引擎
 * 变成 `xlsx-js-style`，`xlsx._sheets` 永远是空数组 ⇒ 原断言以
 * `TypeError: Cannot read properties of undefined (reading '0')` 失败。
 *
 * 简单的修法是把 mock 目标从 `xlsx` 换成 `xlsx-js-style`。但那只是把测试重新钉在
 * 另一个**实现细节**上 —— 下次换库还得再改一遍，而这恰是本 spec 要消除的耦合。
 *
 * 故改为 mock `useExcelIO.exportData`，断言 `queryExport` 的**真实职责**：
 * 把 `QueryExportInput`（列 key 数组 + 行对象数组 + labelFn）转成
 * `ExcelColumn[] + data[]`，并带上迁移必需的三个显式关闭。
 *
 * 端到端的产物正确性（AOA 首行是中文标题、缺失值为 ''、列宽 16、无样式）由
 * `composables/__tests__/excelIoEquivalence.spec.ts` 逐格比对覆盖，两者互补不重叠。
 */

const exportDataSpy = vi.fn()

vi.mock('@/composables/useExcelIO', () => ({
  exportData: (...args: any[]) => exportDataSpy(...args),
}))

beforeEach(() => {
  exportDataSpy.mockClear()
})

describe('exportQueryResultToXlsx — 列标题与取值转换 (Property 4)', () => {
  it('列定义按 labelFn 解析中文标题，data 原样透传（取值由 exportData 按 key 做）', async () => {
    const { exportQueryResultToXlsx } = await import('../queryExport')
    const rows = [
      { account_code: '1001', account_name: '库存现金', closing_balance: 376.73 },
      { account_code: '1002', account_name: '银行存款' },
    ]

    await exportQueryResultToXlsx({
      columns: ['account_code', 'account_name', 'closing_balance'],
      rows,
      fileName: '测试导出',
    })

    expect(exportDataSpy).toHaveBeenCalledTimes(1)
    const arg = exportDataSpy.mock.calls[0][0]

    // 列定义：key 保持原 key，header 走 resolveColumnLabel
    expect(arg.columns).toEqual([
      { key: 'account_code', header: '科目编码', width: 16 },
      { key: 'account_name', header: '科目名称', width: 16 },
      { key: 'closing_balance', header: '期末余额', width: 16 },
    ])

    // 行数据原样透传（缺失字段的 '' 兜底由 exportData 内部 `row[c.key] ?? ''` 完成）
    expect(arg.data).toBe(rows)

    // 文件名经 sanitizeExportName 且带 .xlsx
    expect(arg.fileName).toBe('测试导出.xlsx')
  })

  it('自定义 labelFn 覆盖默认标签解析', async () => {
    const { exportQueryResultToXlsx } = await import('../queryExport')

    await exportQueryResultToXlsx({
      columns: ['x'],
      rows: [{ x: 1 }],
      labelFn: () => '自定义',
      fileName: 'f',
    })

    expect(exportDataSpy.mock.calls[0][0].columns).toEqual([{ key: 'x', header: '自定义', width: 16 }])
  })

  it('sheetName 默认「查询结果」，可覆盖', async () => {
    const { exportQueryResultToXlsx } = await import('../queryExport')

    await exportQueryResultToXlsx({ columns: ['x'], rows: [], fileName: 'f' })
    expect(exportDataSpy.mock.calls[0][0].sheetName).toBe('查询结果')

    exportDataSpy.mockClear()
    await exportQueryResultToXlsx({ columns: ['x'], rows: [], fileName: 'f', sheetName: '自定义表' })
    expect(exportDataSpy.mock.calls[0][0].sheetName).toBe('自定义表')
  })

  it('🔴 迁移必需的三个显式关闭都在位（否则产物外观/行号/弹窗会变）', async () => {
    const { exportQueryResultToXlsx } = await import('../queryExport')

    await exportQueryResultToXlsx({ columns: ['x'], rows: [{ x: 1 }], fileName: 'f' })
    const arg = exportDataSpy.mock.calls[0][0]

    expect(arg.applyStyles, '本导出原本无任何单元格样式；开着会被加上仿宋 + 三线表').toBe(false)
    expect(
      arg.successMessage,
      '调用方（CustomQueryDialog / CustomQueryTab）自行弹提示，封装再弹一次就是双弹窗',
    ).toBe(false)
    expect(arg.columns[0].width, '原本是固定 wch:16，不显式给会落到自适应算法上').toBe(16)
  })
})

describe('sanitizeExportName — 文件名清洗 (Property 6)', () => {
  it('去除 Windows 非法字符', () => {
    expect(sanitizeExportName('a\\b/c:d*e?f"g<h>i|j')).toBe('a_b_c_d_e_f_g_h_i_j')
  })

  it('去除 emoji', () => {
    expect(sanitizeExportName('📊报表📋')).toBe('报表')
  })

  it('空字符串返回兜底名', () => {
    expect(sanitizeExportName('')).toBe('导出')
    expect(sanitizeExportName('   ')).toBe('导出')
  })

  it('正常字符串不变', () => {
    expect(sanitizeExportName('重药控股_试算表_2025')).toBe('重药控股_试算表_2025')
  })
})
