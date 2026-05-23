/**
 * useExcelIO 单元测试 — task 3.2 / C-2 样式模板
 *
 * 验证导出时应用：
 * - 仿宋_GB2312（中文列）+ Arial Narrow（数字列）字体
 * - 三线表边框（首行 medium top + thin bottom，末数据行 medium bottom）
 * - 列宽自适应（CJK 字符算 2 字符宽度）
 * - applyStyles: false 时 fallback 到原有简易列宽
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock element-plus 的 ElMessage（避免 jsdom 环境告警）
vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

// 用变量捕获最近一次写入的 workbook，便于断言 worksheet 内容
let lastWrittenWb: any = null

// Mock xlsx：保留所有真实导出（aoa_to_sheet/utils/encode_cell 等），仅替换 writeFile
// 同时也覆盖 default 导出（useExcelIO.ts 用 `await import('xlsx')` 的命名空间形式）
vi.mock('xlsx', async importOriginal => {
  const actual: any = await importOriginal()
  const stubbedWriteFile = (wb: any, _fileName: string) => {
    lastWrittenWb = wb
  }
  return {
    ...actual,
    writeFile: stubbedWriteFile,
    default: {
      ...actual,
      writeFile: stubbedWriteFile,
    },
  }
})

// task 3.2 升级（2026-05-22）：导出 API 切换到 xlsx-js-style fork
// 该 fork 与 xlsx API 100% 兼容，mock 同款 writeFile 拦截
vi.mock('xlsx-js-style', async () => {
  const actual: any = await vi.importActual('xlsx-js-style')
  // CJS 模块在 vitest 下 importActual 返回 { default: 实际模块, utils, writeFile, ... }
  // 取实际模块（优先 default 解包）
  const real: any = actual.default && actual.default.utils ? actual.default : actual
  const stubbedWriteFile = (wb: any, _fileName: string) => {
    lastWrittenWb = wb
  }
  // 同时暴露顶层 + default 两种形态以兼容 useExcelIO._loadXlsxStyle 检查路径
  return {
    ...real,
    writeFile: stubbedWriteFile,
    default: {
      ...real,
      writeFile: stubbedWriteFile,
    },
  }
})

import {
  exportData,
  exportTemplate,
  computeColumnWidth,
  isNumericColumn,
  applyExcelStyleTemplate,
  type ExcelColumn,
} from '../useExcelIO'
import * as XLSX from 'xlsx'

beforeEach(() => {
  lastWrittenWb = null
})

describe('computeColumnWidth', () => {
  it('返回 header 与数据值的最大视觉宽度（CJK 算 2，留 2 字符余量）', () => {
    // header "金额" 视觉宽 4 + 2 = 6 → clamped to 8（下限）
    expect(computeColumnWidth('金额', [1000, 2000])).toBe(8)
    // header 长度 6 + 数据 "100,000.00" (10) → max=10 + 2 = 12
    expect(computeColumnWidth('期末', ['100,000.00'])).toBe(12)
    // 长 CJK 文本：12 字符 × 2 = 24，+ 2 = 26
    expect(computeColumnWidth('应收账款客户名称编号', [])).toBe(22)
  })

  it('上限 60，下限 8', () => {
    expect(computeColumnWidth('a', [])).toBe(8)
    expect(computeColumnWidth('a'.repeat(100), [])).toBe(60)
  })

  it('忽略 null/空字符串', () => {
    expect(computeColumnWidth('Hi', [null, '', undefined])).toBe(8)
  })
})

describe('isNumericColumn', () => {
  it('80%+ 数字判为数字列', () => {
    expect(isNumericColumn([1, 2, 3, 4, 'x'])).toBe(true) // 4/5 = 80%
    expect(isNumericColumn([1, 2, 3, 'x', 'y'])).toBe(false) // 3/5 = 60%
  })

  it('字符串数字也算', () => {
    expect(isNumericColumn(['1.5', '2.0', '3'])).toBe(true)
  })

  it('全空返回 false', () => {
    expect(isNumericColumn([null, '', undefined])).toBe(false)
  })

  it('混合 number 与字符串数字（3/4 < 80% 阈值）', () => {
    expect(isNumericColumn([100, '200.50', 300, '混合'])).toBe(false) // 3/4 = 75% < 80%
    expect(isNumericColumn([100, '200.50', 300, 400])).toBe(true) // 4/4 = 100%
  })

  it('特殊值 NaN/Infinity 不计为数字', () => {
    expect(isNumericColumn([NaN, Infinity, 1])).toBe(false) // 1/3
  })
})

describe('applyExcelStyleTemplate', () => {
  it('表头行设置仿宋_GB2312 加粗 + 上下边框', () => {
    const ws = XLSX.utils.aoa_to_sheet([
      ['客户', '金额'],
      ['A 公司', 1000],
      ['B 公司', 2000],
    ])
    const cols: ExcelColumn[] = [
      { key: 'name', header: '客户' },
      { key: 'amt', header: '金额' },
    ]
    applyExcelStyleTemplate(ws, XLSX, {
      headerRowIdx: 0,
      dataStartRowIdx: 1,
      dataEndRowIdx: 2,
      columns: cols,
      dataMatrix: [
        ['A 公司', 1000],
        ['B 公司', 2000],
      ],
    })

    // 表头 A1
    expect(ws['A1'].s.font.name).toBe('仿宋_GB2312')
    expect(ws['A1'].s.font.bold).toBe(true)
    expect(ws['A1'].s.border.top.style).toBe('medium')
    expect(ws['A1'].s.border.bottom.style).toBe('thin')
    // 表头 B1
    expect(ws['B1'].s.font.bold).toBe(true)
  })

  it('数字列用 Arial Narrow，中文列用仿宋_GB2312', () => {
    const ws = XLSX.utils.aoa_to_sheet([
      ['客户', '金额'],
      ['A 公司', 1000],
      ['B 公司', 2000],
    ])
    const cols: ExcelColumn[] = [
      { key: 'name', header: '客户' },
      { key: 'amt', header: '金额' },
    ]
    applyExcelStyleTemplate(ws, XLSX, {
      headerRowIdx: 0,
      dataStartRowIdx: 1,
      dataEndRowIdx: 2,
      columns: cols,
      dataMatrix: [
        ['A 公司', 1000],
        ['B 公司', 2000],
      ],
    })

    // 数据 A2（"客户"列，文本）→ 仿宋_GB2312
    expect(ws['A2'].s.font.name).toBe('仿宋_GB2312')
    expect(ws['A2'].s.alignment.horizontal).toBe('left')
    // 数据 B2（"金额"列，数字）→ Arial Narrow
    expect(ws['B2'].s.font.name).toBe('Arial Narrow')
    expect(ws['B2'].s.alignment.horizontal).toBe('right')
  })

  it('末数据行有 medium bottom 边框（三线表底线）', () => {
    const ws = XLSX.utils.aoa_to_sheet([
      ['客户', '金额'],
      ['A 公司', 1000],
      ['B 公司', 2000],
    ])
    const cols: ExcelColumn[] = [
      { key: 'name', header: '客户' },
      { key: 'amt', header: '金额' },
    ]
    applyExcelStyleTemplate(ws, XLSX, {
      headerRowIdx: 0,
      dataStartRowIdx: 1,
      dataEndRowIdx: 2,
      columns: cols,
      dataMatrix: [
        ['A 公司', 1000],
        ['B 公司', 2000],
      ],
    })

    // 中间行 A2 不应有 bottom 边框
    expect(ws['A2'].s.border).toBeUndefined()
    // 末行 A3 + B3 应有 medium bottom
    expect(ws['A3'].s.border.bottom.style).toBe('medium')
    expect(ws['B3'].s.border.bottom.style).toBe('medium')
  })

  it('!cols 列宽按 CJK 视觉宽度自适应', () => {
    const ws = XLSX.utils.aoa_to_sheet([
      ['应收账款客户名称', '金额'],
      ['一家很长的中文公司名称', 1000000.5],
    ])
    const cols: ExcelColumn[] = [
      { key: 'name', header: '应收账款客户名称' },
      { key: 'amt', header: '金额' },
    ]
    applyExcelStyleTemplate(ws, XLSX, {
      headerRowIdx: 0,
      dataStartRowIdx: 1,
      dataEndRowIdx: 1,
      columns: cols,
      dataMatrix: [['一家很长的中文公司名称', 1000000.5]],
    })

    // header "应收账款客户名称" 8 中文字符 × 2 = 16；data "一家很长的中文公司名称" 11 字符 × 2 = 22
    // → max=22+2=24
    expect(ws['!cols']![0].wch).toBe(24)
    // header "金额" 4，data "1000000.5" 9 → max=9+2=11
    expect(ws['!cols']![1].wch).toBe(11)
  })

  it('显式 numericColumnKeys 优先于自动检测', () => {
    const ws = XLSX.utils.aoa_to_sheet([
      ['编号', '描述'],
      ['1001', '混合内容'],
      ['1002', '混合 abc'],
    ])
    const cols: ExcelColumn[] = [
      { key: 'code', header: '编号' },
      { key: 'desc', header: '描述' },
    ]
    applyExcelStyleTemplate(ws, XLSX, {
      headerRowIdx: 0,
      dataStartRowIdx: 1,
      dataEndRowIdx: 2,
      columns: cols,
      dataMatrix: [
        ['1001', '混合内容'],
        ['1002', '混合 abc'],
      ],
      numericColumnKeys: ['code'],
    })

    // code 显式标为数字列 → Arial Narrow
    expect(ws['A2'].s.font.name).toBe('Arial Narrow')
    // desc 自动检测为非数字 → 仿宋_GB2312
    expect(ws['B2'].s.font.name).toBe('仿宋_GB2312')
  })

  it('显式 ExcelColumn.width 优先于自适应计算', () => {
    const ws = XLSX.utils.aoa_to_sheet([
      ['Code'],
      ['很长的中文内容字符串测试'],
    ])
    const cols: ExcelColumn[] = [{ key: 'code', header: 'Code', width: 5 }]
    applyExcelStyleTemplate(ws, XLSX, {
      headerRowIdx: 0,
      dataStartRowIdx: 1,
      dataEndRowIdx: 1,
      columns: cols,
      dataMatrix: [['很长的中文内容字符串测试']],
    })

    expect(ws['!cols']![0].wch).toBe(5)
  })
})

describe('exportData (集成)', () => {
  it('默认 applyStyles=true 时 worksheet 含字体 + 边框 + 列宽', async () => {
    await exportData({
      data: [
        { name: 'A 公司', amt: 1000 },
        { name: 'B 公司', amt: 2000 },
      ],
      columns: [
        { key: 'name', header: '客户' },
        { key: 'amt', header: '金额' },
      ],
      fileName: 'test.xlsx',
    })

    expect(lastWrittenWb).not.toBeNull()
    const ws = lastWrittenWb.Sheets['数据']
    expect(ws).toBeDefined()

    // 表头 A1: 仿宋加粗 + 上边框
    expect(ws['A1'].s.font.name).toBe('仿宋_GB2312')
    expect(ws['A1'].s.font.bold).toBe(true)
    expect(ws['A1'].s.border.top.style).toBe('medium')
    // 数据数字列 B2 (金额) → Arial Narrow
    expect(ws['B2'].s.font.name).toBe('Arial Narrow')
    // 末行 B3 → medium bottom
    expect(ws['B3'].s.border.bottom.style).toBe('medium')
    // 列宽设置
    expect(ws['!cols']).toBeDefined()
    expect(ws['!cols']!.length).toBe(2)
  })

  it('applyStyles=false 时不写入 cell.s，使用简易列宽 fallback', async () => {
    await exportData({
      data: [{ name: 'A', amt: 100 }],
      columns: [
        { key: 'name', header: 'Name' },
        { key: 'amt', header: 'Amount' },
      ],
      fileName: 'test.xlsx',
      applyStyles: false,
    })

    const ws = lastWrittenWb.Sheets['数据']
    // cell.s 不应存在
    expect(ws['A1'].s).toBeUndefined()
    expect(ws['B2'].s).toBeUndefined()
    // 但 !cols 还在（旧逻辑）
    expect(ws['!cols']).toBeDefined()
  })

  it('extraHeaders 列也参与样式应用', async () => {
    await exportData({
      data: [{ name: 'A', amt: 100 }],
      columns: [
        { key: 'name', header: '客户' },
        { key: 'amt', header: '金额' },
      ],
      extraHeaders: ['备注'],
      extraDataFn: () => ['—'],
      fileName: 'test.xlsx',
    })

    const ws = lastWrittenWb.Sheets['数据']
    // 第 3 列 C1 表头也有样式
    expect(ws['C1']).toBeDefined()
    expect(ws['C1'].s.font.name).toBe('仿宋_GB2312')
    expect(ws['!cols']!.length).toBe(3)
  })
})

describe('exportTemplate (集成)', () => {
  it('默认应用样式到表头与示例行', async () => {
    await exportTemplate({
      columns: [
        { key: 'name', header: '客户名称' },
        { key: 'amt', header: '金额' },
      ],
      fileName: 'tpl.xlsx',
      includeNoteRow: false,
      exampleRows: [
        ['示例公司 A', 100000],
        ['示例公司 B', 200000],
      ],
    })

    const ws = lastWrittenWb.Sheets['数据填写']
    // 表头 A1 / B1（无 noteRow，header 在第 0 行）
    expect(ws['A1'].s.font.name).toBe('仿宋_GB2312')
    expect(ws['B1'].s.font.bold).toBe(true)
    // 数据 B2 数字列 → Arial Narrow
    expect(ws['B2'].s.font.name).toBe('Arial Narrow')
    // 末行 A3 / B3 → medium bottom
    expect(ws['A3'].s.border.bottom.style).toBe('medium')
  })

  it('includeNoteRow=true 时表头偏移到第 2 行', async () => {
    await exportTemplate({
      columns: [
        { key: 'name', header: '客户', note: '客户名称' },
        { key: 'amt', header: '金额', note: '本期发生额' },
      ],
      fileName: 'tpl.xlsx',
      includeNoteRow: true,
      exampleRows: [['示例', 100]],
    })

    const ws = lastWrittenWb.Sheets['数据填写']
    // 第 0 行是 noteRow（无样式）
    expect(ws['A1'].s).toBeUndefined()
    // 第 1 行是 header（A2 / B2 含样式）
    expect(ws['A2'].s.font.name).toBe('仿宋_GB2312')
    expect(ws['A2'].s.font.bold).toBe(true)
    expect(ws['A2'].s.border.top.style).toBe('medium')
  })

  it('applyStyles=false 时不写样式但保留旧列宽行为', async () => {
    await exportTemplate({
      columns: [{ key: 'name', header: '客户' }],
      fileName: 'tpl.xlsx',
      includeNoteRow: false,
      applyStyles: false,
    })

    const ws = lastWrittenWb.Sheets['数据填写']
    expect(ws['A1'].s).toBeUndefined()
    expect(ws['!cols']).toBeDefined()
  })

  it('无数据行时表头同时承担三线表上+下边框', async () => {
    await exportTemplate({
      columns: [{ key: 'name', header: '客户' }],
      fileName: 'tpl.xlsx',
      includeNoteRow: false,
      // 不传 exampleRows / existingData → 无数据行
    })

    const ws = lastWrittenWb.Sheets['数据填写']
    // 表头 A1 既有 medium top 又有 medium bottom（三线表两道边线压缩到一行）
    expect(ws['A1'].s.border.top.style).toBe('medium')
    expect(ws['A1'].s.border.bottom.style).toBe('medium')
  })
})
