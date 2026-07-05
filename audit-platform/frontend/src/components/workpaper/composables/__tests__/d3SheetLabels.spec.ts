import { describe, it, expect } from 'vitest'
import { D3_SHEET_LABEL_MAP, resolveD3SheetLabel } from '../d3SheetLabels'

describe('d3SheetLabels', () => {
  it('D3A 默认名为实质性程序表', () => {
    expect(D3_SHEET_LABEL_MAP.D3A).toBe('预收账款实质性程序表D3A')
  })

  it('D3-5 默认名与模板一致', () => {
    expect(D3_SHEET_LABEL_MAP['D3-5']).toBe('账龄1年以上的预收账款检查表D3-5')
  })

  it('resolveD3SheetLabel 优先 render-config sheets', () => {
    const label = resolveD3SheetLabel('D3A', [
      { sheet_name: '预收账款实质性程序表D3A' },
    ])
    expect(label).toBe('预收账款实质性程序表D3A')
  })
})
