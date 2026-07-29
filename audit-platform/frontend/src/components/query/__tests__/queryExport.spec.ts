import { describe, it, expect, vi } from 'vitest'
import { sanitizeExportName } from '../queryExport'

// Mock xlsx to avoid actual file I/O in unit tests
vi.mock('xlsx', () => {
  const _sheets: any[] = []
  return {
    default: undefined,
    utils: {
      book_new: () => ({ SheetNames: [], Sheets: {} }),
      aoa_to_sheet: (aoa: any[][]) => { _sheets.push(aoa); return { '!cols': [] } },
      book_append_sheet: (wb: any, ws: any, name: string) => { wb.SheetNames.push(name); wb.Sheets[name] = ws },
    },
    writeFile: vi.fn(),
    _sheets,
  }
})

describe('exportQueryResultToXlsx — 导出列标题与取值 (Property 4)', () => {
  it('生成 aoa 首行为中文标题、数据行按 key 取值', async () => {
    const xlsx = await import('xlsx') as any
    xlsx._sheets.length = 0

    const { exportQueryResultToXlsx } = await import('../queryExport')
    await exportQueryResultToXlsx({
      columns: ['account_code', 'account_name', 'closing_balance'],
      rows: [
        { account_code: '1001', account_name: '库存现金', closing_balance: 376.73 },
        { account_code: '1002', account_name: '银行存款' },
      ],
      fileName: '测试导出',
    })

    const aoa = xlsx._sheets[0]
    // 首行=中文标题（来自 resolveColumnLabel）
    expect(aoa[0]).toEqual(['科目编码', '科目名称', '期末余额'])
    // 数据行按 key 取值，缺失为 ''
    expect(aoa[1]).toEqual(['1001', '库存现金', 376.73])
    expect(aoa[2]).toEqual(['1002', '银行存款', ''])

    // writeFile 被调用且文件名经 sanitizeExportName
    expect(xlsx.writeFile).toHaveBeenCalledWith(expect.anything(), '测试导出.xlsx')
  })

  it('自定义 labelFn 覆盖默认标签解析', async () => {
    const xlsx = await import('xlsx') as any
    xlsx._sheets.length = 0

    const { exportQueryResultToXlsx } = await import('../queryExport')
    await exportQueryResultToXlsx({
      columns: ['x'],
      rows: [{ x: 1 }],
      labelFn: () => '自定义',
      fileName: 'f',
    })
    expect(xlsx._sheets[0][0]).toEqual(['自定义'])
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
