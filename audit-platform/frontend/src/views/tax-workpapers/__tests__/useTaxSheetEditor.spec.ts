/**
 * 税审单表编辑：恢复自动值（spec citar-table-manual-edit R1）。
 * 已保存的手工值点「恢复」后保存时不再提交；草稿点「恢复」直接去掉；恢复后再改又成为手工值。
 */
import { describe, expect, it, vi } from 'vitest'

vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), warning: vi.fn() } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import { useTaxSheetEditor } from '../useTaxSheetEditor'
import type { TaxInputs, TaxSheetResult } from '../taxWorkpaperApi'

function sheet(): TaxSheetResult {
  return {
    code: '2-02',
    year: 2025,
    version: 3,
    updated_at: null,
    issues: [],
    notices: [],
    parts: [{
      source: '2-02',
      values: { D10: { n: '1500' }, G10: { n: '5' }, F10: { n: '1' } },
      cells: {
        D10: { origin: 'input', status: 'auto', auto: { n: '1000' } },
        G10: { origin: 'input', auto: { n: '1000' } },
        F10: { origin: 'input' },
      },
    }],
  }
}

function setup() {
  const saved: TaxInputs[] = []
  const editor = useTaxSheetEditor({
    projectId: () => 'p',
    year: () => 2025,
    code: () => '2-02',
    fetch: async () => sheet(),
    save: async (_p, _y, _c, _v, inputs) => {
      saved.push(inputs)
      return sheet()
    },
    label: '底稿',
  })
  return { editor, saved }
}

describe('useTaxSheetEditor 恢复自动值', () => {
  it('已保存的手工值恢复后不再提交，其余手工值照提交', async () => {
    const { editor, saved } = setup()
    await editor.loadValues()
    editor.restore('2-02', 'G10')
    expect(editor.restoredOf('2-02').has('G10')).toBe(true)
    expect(editor.dirty.value).toBe(true)
    await editor.save()
    expect(saved[0]).toEqual({ '2-02': { D10: 1500, F10: 1 } })
    expect(editor.restoredOf('2-02').size).toBe(0)
  })

  it('草稿恢复即去掉；恢复后再改又成为手工值', async () => {
    const { editor } = setup()
    await editor.loadValues()
    editor.setDraft('2-02', 'H10', 7)
    editor.restore('2-02', 'H10')
    expect(editor.drafts.value['2-02']).toEqual({})
    expect(editor.restoredOf('2-02').has('H10')).toBe(false) // 未保存过的格不进 restored

    editor.restore('2-02', 'D10')
    editor.setDraft('2-02', 'D10', 1600)
    expect(editor.restoredOf('2-02').has('D10')).toBe(false)
    expect(editor.mergedInputs()).toEqual({ '2-02': { D10: 1600, G10: 5, F10: 1 } })
  })

  it('放弃修改同时清掉恢复标记', async () => {
    const { editor } = setup()
    await editor.loadValues()
    editor.restore('2-02', 'F10')
    editor.discard()
    expect(editor.dirty.value).toBe(false)
    expect(editor.mergedInputs()['2-02']).toHaveProperty('F10', 1)
  })
})
