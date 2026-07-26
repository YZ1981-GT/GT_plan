/**
 * h5NoteSectionMap.spec — P1/P2/P3 正确性属性测试
 */
import { describe, it, expect } from 'vitest'
import {
  H5_NOTE_SECTION,
  H5_SOE_COLUMNS,
  buildH5SyncPayload,
} from '../h5NoteSectionMap'

describe('h5NoteSectionMap', () => {
  // ─── P1: 子表键匹配附注模板 ──────────────────────────────────────────────
  it('P1: sub_table_data 子表键应为有效中文表名', () => {
    const payload = buildH5SyncPayload({
      wpId: 'wp-123',
      projectId: 'proj-456',
      year: 2025,
      summaryRows: [
        { label: '油气资产原值', values: [1000, 800] },
        { label: '减：累计折耗', values: [200, 150] },
      ],
    })
    const keys = Object.keys(payload.sub_table_data)
    expect(keys.length).toBeGreaterThan(0)
    // 子表键应为中文（非英文字段键）
    for (const k of keys) {
      expect(/[\u4e00-\u9fff]/.test(k)).toBe(true)
    }
    // 应含 '油气资产'
    expect(keys).toContain('油气资产')
  })

  // ─── P2: 列头为中文 ──────────────────────────────────────────────────────
  it('P2: columns 列头 label 为非空中文字符串', () => {
    for (const [, cols] of Object.entries(H5_SOE_COLUMNS)) {
      for (const col of cols) {
        expect(col.label).toBeTruthy()
        expect(/[\u4e00-\u9fff]/.test(col.label)).toBe(true)
      }
    }
  })

  // ─── P3: year 正确传入 ────────────────────────────────────────────────────
  it('P3: payload.year 等于传入的 year 参数', () => {
    const payload = buildH5SyncPayload({
      wpId: 'wp-x',
      projectId: 'p-y',
      year: 2025,
      summaryRows: [{ label: '净值', values: [100, 80] }],
    })
    expect(payload.year).toBe(2025)
    expect(payload.year).not.toBe(new Date().getFullYear())
  })

  // ─── 补充: section_id 正确 ────────────────────────────────────────────────
  it('section_id 应为 八、25', () => {
    expect(H5_NOTE_SECTION.soe).toBe('八、25')
    const payload = buildH5SyncPayload({
      wpId: 'w', projectId: 'p', year: 2025,
      summaryRows: [{ label: 'x', values: [1, 2] }],
    })
    expect(payload.section_id).toBe('八、25')
  })

  // ─── 补充: current_standard 恒为 soe_standalone ───────────────────────────
  it('current_standard 恒为 soe_standalone', () => {
    const payload = buildH5SyncPayload({
      wpId: 'w', projectId: 'p', year: 2025,
      summaryRows: [{ label: 'x', values: [1, 2] }],
    })
    expect(payload.current_standard).toBe('soe_standalone')
  })

  // ─── 补充: _note_texts 组装 ──────────────────────────────────────────────
  it('soeDisclosureText 非空时 _note_texts 含一条', () => {
    const payload = buildH5SyncPayload({
      wpId: 'w', projectId: 'p', year: 2025,
      summaryRows: [{ label: 'x', values: [1, 2] }],
      soeDisclosureText: '产能利用率85%',
    })
    expect(payload._note_texts).toHaveLength(1)
    expect(payload._note_texts[0].text).toBe('产能利用率85%')
  })

  it('soeDisclosureText 为空时 _note_texts 为空数组', () => {
    const payload = buildH5SyncPayload({
      wpId: 'w', projectId: 'p', year: 2025,
      summaryRows: [{ label: 'x', values: [1, 2] }],
      soeDisclosureText: '',
    })
    expect(payload._note_texts).toHaveLength(0)
  })

  // ─── 补充: summaryRows 空时 sub_table_data 空 ────────────────────────────
  it('summaryRows 空时 sub_table_data 为空对象', () => {
    const payload = buildH5SyncPayload({
      wpId: 'w', projectId: 'p', year: 2025,
      summaryRows: [],
    })
    expect(Object.keys(payload.sub_table_data)).toHaveLength(0)
  })
})
