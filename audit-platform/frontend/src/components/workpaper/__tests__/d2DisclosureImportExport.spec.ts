/**
 * D2 附注披露导入导出 composable 纯逻辑测试
 *  - sheet 参数（后端 Query，不能进 FormData）
 *  - Content-Disposition 文件名解析（RFC5987 优先）
 */
import { describe, it, expect } from 'vitest'
import {
  d2DisclosureSheetParam,
  parseFilenameFromHeader,
} from '../composables/useD2DisclosureImportExport'

describe('d2DisclosureSheetParam', () => {
  it('按变体产出后端 sheet 参数', () => {
    expect(d2DisclosureSheetParam('listed')).toBe('D2-disc-listed')
    expect(d2DisclosureSheetParam('soe')).toBe('D2-disc-soe')
  })
})

describe('parseFilenameFromHeader', () => {
  it('优先解析 RFC5987 filename*（中文名 URL 解码）', () => {
    const header = "attachment; filename*=UTF-8''D2%E5%BA%94%E6%94%B6%E8%B4%A6%E6%AC%BE.xlsx"
    expect(parseFilenameFromHeader(header, 'fallback.xlsx')).toBe('D2应收账款.xlsx')
  })

  it('回退解析 filename=""', () => {
    expect(parseFilenameFromHeader('attachment; filename="a b.xlsx"', 'fb.xlsx')).toBe('a b.xlsx')
  })

  it('缺失/异常时用 fallback', () => {
    expect(parseFilenameFromHeader(null, 'fb.xlsx')).toBe('fb.xlsx')
    expect(parseFilenameFromHeader('attachment', 'fb.xlsx')).toBe('fb.xlsx')
  })
})
