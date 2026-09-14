import { describe, it, expect } from 'vitest'
import { D1_SHEET_LABEL_MAP, resolveD1SheetLabel } from '../d1SheetLabels'

describe('d1SheetLabels', () => {
  it('D1-8 默认名与模板 xlsx 一致', () => {
    expect(D1_SHEET_LABEL_MAP['D1-8']).toBe('应收票据贴现、票据已背书未到期明细表D1-8')
  })

  it('附注上市使用全角括号', () => {
    expect(D1_SHEET_LABEL_MAP['附注上市']).toBe('附注披露信息（上市公司）')
  })

  it('resolveD1SheetLabel 优先 render-config sheets', () => {
    const label = resolveD1SheetLabel('D1-8', [
      { sheet_name: '自定义背书表D1-8' },
    ])
    expect(label).toBe('自定义背书表D1-8')
  })
})
