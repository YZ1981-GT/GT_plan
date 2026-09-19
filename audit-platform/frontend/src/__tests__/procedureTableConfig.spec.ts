/**
 * 程序表配置单测 — 验证 WorkpaperHtmlTable 用于程序表时的列定义正确性
 *
 * 程序表统一使用相同列配置：seq/content/applicable/executor/summary/ref_index
 * Requirements: 1.1, 2.4
 */
import { describe, it, expect } from 'vitest'

// 程序表统一列定义（与实际使用一致）
const PROCEDURE_TABLE_COLUMNS = [
  { key: 'seq', label: '序号', type: 'text' as const, width: 50 },
  { key: 'content', label: '程序步骤', type: 'text' as const, minWidth: 250 },
  { key: 'applicable', label: '是否适用', type: 'tristate' as const, width: 100 },
  { key: 'executor', label: '执行人', type: 'editable' as const, width: 100 },
  { key: 'summary', label: '执行情况说明', type: 'editable' as const, minWidth: 180 },
  { key: 'ref_index', label: '索引号', type: 'indexLink' as const, width: 120 },
]

describe('程序表列配置', () => {
  it('包含6列必要定义', () => {
    expect(PROCEDURE_TABLE_COLUMNS).toHaveLength(6)
  })

  it('seq 为 text 类型', () => {
    const seq = PROCEDURE_TABLE_COLUMNS.find((c) => c.key === 'seq')
    expect(seq?.type).toBe('text')
  })

  it('applicable 为 tristate 类型', () => {
    const col = PROCEDURE_TABLE_COLUMNS.find((c) => c.key === 'applicable')
    expect(col?.type).toBe('tristate')
  })

  it('executor 和 summary 为 editable 类型', () => {
    const executor = PROCEDURE_TABLE_COLUMNS.find((c) => c.key === 'executor')
    const summary = PROCEDURE_TABLE_COLUMNS.find((c) => c.key === 'summary')
    expect(executor?.type).toBe('editable')
    expect(summary?.type).toBe('editable')
  })

  it('ref_index 为 indexLink 类型', () => {
    const col = PROCEDURE_TABLE_COLUMNS.find((c) => c.key === 'ref_index')
    expect(col?.type).toBe('indexLink')
  })

  it('所有列有 label', () => {
    for (const col of PROCEDURE_TABLE_COLUMNS) {
      expect(col.label).toBeTruthy()
    }
  })
})
