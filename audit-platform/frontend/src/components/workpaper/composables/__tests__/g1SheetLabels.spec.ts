import { describe, it, expect } from 'vitest'
import { extractG1SheetCode, resolveG1SheetLabel, G1_SHEET_LABEL_MAP } from '../g1SheetLabels'

describe('resolveG1SheetLabel', () => {
  it('从 availableSheets 按末尾编码匹配真实 sheet 名', () => {
    const sheets = [
      { sheet_name: '明细表G1-2' },
      { sheet_name: '分类的适当性检查表G1-9' },
      { sheet_name: '审定表G1-1' },
    ]
    expect(resolveG1SheetLabel('G1-9', sheets)).toBe('分类的适当性检查表G1-9')
    expect(resolveG1SheetLabel('G1-1', sheets)).toBe('审定表G1-1')
  })

  it('无 availableSheets 时用默认映射（无空格）', () => {
    expect(resolveG1SheetLabel('G1-9')).toBe(G1_SHEET_LABEL_MAP['G1-9'])
    expect(G1_SHEET_LABEL_MAP['G1-9']).toBe('分类的适当性检查表G1-9')
  })

  it('优先使用与编码一致的 fallbackSheetName', () => {
    expect(
      resolveG1SheetLabel('G1-9', undefined, '分类的适当性检查表 G1-9'),
    ).toBe('分类的适当性检查表 G1-9')
  })
})

describe('extractG1SheetCode', () => {
  it('识别 G1-9 分类检查表', () => {
    expect(extractG1SheetCode('分类的适当性检查表G1-9')).toBe('G1-9')
    expect(extractG1SheetCode('分类的适当性检查表 G1-9')).toBe('G1-9')
  })
})
