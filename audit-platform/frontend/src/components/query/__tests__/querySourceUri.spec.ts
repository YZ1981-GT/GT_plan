import { describe, it, expect } from 'vitest'
import { buildWorkpaperUri, buildTraceUri, RESOLVE_FAIL_MSG } from '../querySourceUri'

describe('buildWorkpaperUri — URI 拼装 (Property 7)', () => {
  it('完整三段', () => {
    expect(buildWorkpaperUri('D2', '审定表D2-1', 'B7')).toBe('workpaper:D2|审定表D2-1|B7')
  })

  it('省略 cellRef', () => {
    expect(buildWorkpaperUri('K1', '明细表K1-2')).toBe('workpaper:K1|明细表K1-2')
  })

  it('省略 sheetName 和 cellRef', () => {
    expect(buildWorkpaperUri('E1')).toBe('workpaper:E1')
  })

  it('sheetName 为空字符串视同省略', () => {
    expect(buildWorkpaperUri('F2', '')).toBe('workpaper:F2')
  })

  it('有 cellRef 但无 sheetName 时不输出 cellRef（语法依赖 sheet 段）', () => {
    expect(buildWorkpaperUri('G1', '', 'C3')).toBe('workpaper:G1')
  })
})

describe('buildTraceUri — 溯源 URI 推断分支', () => {
  it('优先 workpaper（有 wp_code + sheet_name）', () => {
    const row = { wp_code: 'D2', sheet_name: '审定表D2-1', cell_ref: 'A1', module: 'report', report_type: 'BS' }
    expect(buildTraceUri(row, 'fallback')).toBe('workpaper:D2|审定表D2-1|A1')
  })

  it('report 分支', () => {
    const row = { module: 'report', report_type: 'IS' }
    expect(buildTraceUri(row, '')).toBe('report:IS')
  })

  it('note 分支', () => {
    const row = { module: 'note', section_id: '五、1' }
    expect(buildTraceUri(row, '')).toBe('note:五、1')
  })

  it('回退 selectedSource', () => {
    const row = { amount: 100 }
    expect(buildTraceUri(row, 'tb_detail')).toBe('tb_detail')
  })

  it('全无则返回空串', () => {
    expect(buildTraceUri({}, '')).toBe('')
  })
})

describe('RESOLVE_FAIL_MSG — 文案常量', () => {
  it('wpNotFound 包含底稿编码', () => {
    expect(RESOLVE_FAIL_MSG.wpNotFound('K3')).toContain('K3')
  })

  it('常量非空', () => {
    expect(RESOLVE_FAIL_MSG.notRegistered).toBeTruthy()
    expect(RESOLVE_FAIL_MSG.noUri).toBeTruthy()
  })
})
