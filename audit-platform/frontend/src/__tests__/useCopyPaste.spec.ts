/**
 * useCopyPaste 增强测试
 * 覆盖：HTML table 解析、数值格式识别、diff 预览、undo stack、审计摘要
 *
 * Validates: Requirements 3.3, 3.4
 */
import { describe, it, expect, vi } from 'vitest'
import {
  parseAmountString,
  parseHtmlTable,
  parseTextMatrix,
  buildPasteDiff,
} from '@/utils/pasteParser'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() },
}))

vi.mock('@/composables/useCellSelection', () => ({}))

import {
  pasteToSelection,
  undoLastPaste,
  type UndoEntry,
  type PasteAuditSummary,
} from '@/composables/useCopyPaste'

describe('parseAmountString', () => {
  it('解析千分位金额', () => {
    expect(parseAmountString('1,234,567.89')).toBe('1234567.89')
    expect(parseAmountString('1,000')).toBe('1000')
  })

  it('解析括号负数', () => {
    expect(parseAmountString('(1,234.56)')).toBe('-1234.56')
    expect(parseAmountString('(500)')).toBe('-500')
  })

  it('解析百分比', () => {
    expect(parseAmountString('12.5%')).toBe('0.125')
    expect(parseAmountString('100%')).toBe('1')
    expect(parseAmountString('0.5%')).toBe('0.005')
  })

  it('空白/横杠返回空字符串', () => {
    expect(parseAmountString('')).toBe('')
    expect(parseAmountString('-')).toBe('')
    expect(parseAmountString('—')).toBe('')
    expect(parseAmountString('–')).toBe('')
    expect(parseAmountString('  ')).toBe('')
  })

  it('普通数字直接返回', () => {
    expect(parseAmountString('123.45')).toBe('123.45')
    expect(parseAmountString('0')).toBe('0')
    expect(parseAmountString('-99.9')).toBe('-99.9')
  })

  it('非数字文本原样返回', () => {
    expect(parseAmountString('hello')).toBe('hello')
    expect(parseAmountString('N/A')).toBe('N/A')
  })

  it('null/undefined 返回空字符串', () => {
    expect(parseAmountString(null as any)).toBe('')
    expect(parseAmountString(undefined as any)).toBe('')
  })
})

describe('parseHtmlTable', () => {
  it('解析简单 HTML 表格', () => {
    const html = '<table><tr><td>A1</td><td>B1</td></tr><tr><td>A2</td><td>B2</td></tr></table>'
    expect(parseHtmlTable(html)).toEqual([['A1', 'B1'], ['A2', 'B2']])
  })

  it('解析带 th 的表格', () => {
    const html = '<table><tr><th>Header</th></tr><tr><td>Data</td></tr></table>'
    expect(parseHtmlTable(html)).toEqual([['Header'], ['Data']])
  })

  it('非表格 HTML 返回 null', () => {
    expect(parseHtmlTable('<p>hello</p>')).toBeNull()
    expect(parseHtmlTable('')).toBeNull()
    expect(parseHtmlTable('plain text')).toBeNull()
  })

  it('trim 单元格内容中的空白', () => {
    const html = '<table><tr><td>  hello  </td><td>\n123\n</td></tr></table>'
    expect(parseHtmlTable(html)).toEqual([['hello', '123']])
  })
})

describe('parseTextMatrix', () => {
  it('解析制表符分隔文本', () => {
    const text = 'A1\tB1\nA2\tB2'
    expect(parseTextMatrix(text)).toEqual([['A1', 'B1'], ['A2', 'B2']])
  })

  it('处理 Windows 换行', () => {
    const text = 'A1\tB1\r\nA2\tB2'
    expect(parseTextMatrix(text)).toEqual([['A1', 'B1'], ['A2', 'B2']])
  })

  it('过滤空行', () => {
    const text = 'A1\tB1\n\nA2\tB2\n'
    expect(parseTextMatrix(text)).toEqual([['A1', 'B1'], ['A2', 'B2']])
  })

  it('空输入返回空数组', () => {
    expect(parseTextMatrix('')).toEqual([])
    expect(parseTextMatrix('   ')).toEqual([])
  })
})

describe('buildPasteDiff', () => {
  const columns = [
    { key: 'code', label: '编码' },
    { key: 'amount', label: '金额' },
    { key: 'note', label: '备注' },
  ]
  const tableData = [
    { code: 'A001', amount: '100', note: '' },
    { code: 'A002', amount: '200', note: 'test' },
  ]

  it('生成 diff 预览（有变更）', () => {
    const matrix = [['999'], ['888']]
    const diff = buildPasteDiff(matrix, 0, 1, tableData, columns)
    expect(diff.cells.length).toBe(2)
    expect(diff.cells[0].oldValue).toBe('100')
    expect(diff.cells[0].newValue).toBe('999')
    expect(diff.cells[1].oldValue).toBe('200')
    expect(diff.cells[1].newValue).toBe('888')
    expect(diff.rowCount).toBe(2)
    expect(diff.colCount).toBe(1)
  })

  it('无变更时 diff 为空', () => {
    const matrix = [['100']]
    const diff = buildPasteDiff(matrix, 0, 1, tableData, columns)
    expect(diff.cells.length).toBe(0)
  })

  it('超出范围计入 overflowCount', () => {
    const matrix = [['x', 'y', 'z', 'overflow!']]
    const diff = buildPasteDiff(matrix, 0, 1, tableData, columns)
    expect(diff.overflowCount).toBe(2)  // col 3, col 4 超出
  })

  it('标准化金额格式', () => {
    const matrix = [['(1,234.56)']]
    const diff = buildPasteDiff(matrix, 0, 1, tableData, columns, true)
    expect(diff.cells[0].newValue).toBe('-1234.56')
  })
})

describe('pasteToSelection + undo', () => {
  function makeClipboardEvent(text: string, html = ''): ClipboardEvent {
    return {
      clipboardData: {
        getData(type: string) {
          if (type === 'text/plain') return text
          if (type === 'text/html') return html
          return ''
        },
      },
      preventDefault: () => {},
    } as unknown as ClipboardEvent
  }

  const columns = [
    { key: 'code', label: '编码' },
    { key: 'amount', label: '金额' },
  ]

  it('粘贴纯文本并写入 undo stack', () => {
    const tableData = [
      { code: 'A', amount: '100' },
      { code: 'B', amount: '200' },
    ]
    const selectedCells = [{ row: 0, col: 1, value: '100' }]
    const undoStack: UndoEntry[] = []

    const event = makeClipboardEvent('999\n888')
    const written = pasteToSelection(event, selectedCells, tableData, columns, { undoStack })

    expect(written).toBe(2)
    expect(tableData[0].amount).toBe('999')
    expect(tableData[1].amount).toBe('888')
    expect(undoStack.length).toBe(1)
    expect(undoStack[0].changes.length).toBe(2)
  })

  it('undo 恢复原始值', () => {
    const tableData = [
      { code: 'A', amount: '100' },
      { code: 'B', amount: '200' },
    ]
    const selectedCells = [{ row: 0, col: 1, value: '100' }]
    const undoStack: UndoEntry[] = []

    const event = makeClipboardEvent('999\n888')
    pasteToSelection(event, selectedCells, tableData, columns, { undoStack })

    expect(tableData[0].amount).toBe('999')

    const result = undoLastPaste(undoStack, tableData)
    expect(result).toBe(true)
    expect(tableData[0].amount).toBe('100')
    expect(tableData[1].amount).toBe('200')
    expect(undoStack.length).toBe(0)
  })

  it('优先解析 HTML table 格式', () => {
    const tableData = [{ code: 'A', amount: '100' }]
    const selectedCells = [{ row: 0, col: 0, value: 'A' }]
    const undoStack: UndoEntry[] = []

    const html = '<table><tr><td>X</td><td>555</td></tr></table>'
    const event = makeClipboardEvent('X\t555', html)
    const written = pasteToSelection(event, selectedCells, tableData, columns, { undoStack })

    expect(written).toBe(2)
    expect(tableData[0].code).toBe('X')
    expect(tableData[0].amount).toBe('555')
  })

  it('生成审计摘要（不含原文）', () => {
    const tableData = [{ code: 'A', amount: '100' }]
    const selectedCells = [{ row: 0, col: 1, value: '100' }]
    let auditSummary: PasteAuditSummary | null = null

    const event = makeClipboardEvent('(5,000)')
    pasteToSelection(event, selectedCells, tableData, columns, {
      onAuditLog: (s) => { auditSummary = s },
      normalizeAmounts: true,
    })

    expect(auditSummary).not.toBeNull()
    expect(auditSummary!.action).toBe('paste')
    expect(auditSummary!.cellCount).toBe(1)
    expect(auditSummary!.sampleChanges[0].new).toBe('-5000')
    // 确保摘要不含完整剪贴板原文
    expect(JSON.stringify(auditSummary)).not.toContain('(5,000)')
  })

  it('金额标准化：千分位+括号负数', () => {
    const tableData = [
      { code: 'A', amount: '0' },
      { code: 'B', amount: '0' },
    ]
    const selectedCells = [{ row: 0, col: 1, value: '0' }]

    const event = makeClipboardEvent('1,234,567.89\n(99,000)')
    pasteToSelection(event, selectedCells, tableData, columns, { normalizeAmounts: true })

    expect(tableData[0].amount).toBe('1234567.89')
    expect(tableData[1].amount).toBe('-99000')
  })
})
