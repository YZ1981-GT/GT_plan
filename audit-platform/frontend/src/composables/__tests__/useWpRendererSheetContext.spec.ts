import { describe, expect, it } from 'vitest'
import {
  resolveRenderSheet,
  resolveUniverSheetContext,
  resolveWorkpaperSheetContext,
  type SheetRenderConfig,
} from '../useWpRenderer'

function sheet(
  sheetName: string,
  sheetCode: string | null,
  componentType = 'd-form-table',
  htmlData: Record<string, unknown> = {},
  extras: Partial<SheetRenderConfig> = {},
): SheetRenderConfig {
  return {
    sheet_name: sheetName,
    sheet_code: sheetCode,
    sheet_code_reason: sheetCode ? 'embedded_code' : 'no_canonical_code',
    whole_workbook: false,
    componentType: componentType as SheetRenderConfig['componentType'],
    schema: {},
    html_data: htmlData,
    cross_refs: [],
    ...extras,
  }
}

const SHEETS = [
  sheet('底稿目录', null, 'b-index'),
  sheet('询证函控制表D0-4b', 'D0-4b', 'd-form-table', {}, {
    sheet_uid: 'uid:D0:D0-4b',
    sheet_uid_null_reason: null,
  }),
  sheet('附注披露信息（上市公司）D0-8', 'D0-8', 'd-form-table', {}, {
    sheet_uid: 'uid:D0:D0-8',
  }),
  sheet('复杂测算D0-9', 'D0-9', 'onlyoffice-sheet', { onlyoffice: true }, {
    sheet_uid: 'uid:D0:D0-9',
  }),
]

describe('render sheet 的 canonical context 纯投影', () => {
  it('deep-link、locate 和 navigate 共用同一归一化解析，并保留小写后缀 code', () => {
    expect(resolveRenderSheet(SHEETS, 'D0-4b')?.sheet_code).toBe('D0-4b')
    expect(resolveRenderSheet(SHEETS, '附注披露信息(上市公司)D0-8')?.sheet_name)
      .toBe('附注披露信息（上市公司）D0-8')
    expect(resolveRenderSheet(SHEETS, '不存在')).toBeNull()
  })

  it('HTML、OnlyOffice 外层与整册产生互斥且完整的结构化 context（含 sheetUid）', () => {
    expect(resolveWorkpaperSheetContext('wp-1', 'wp-1', SHEETS[1].sheet_name, SHEETS[1], false, 'D0'))
      .toEqual({
        sheetName: '询证函控制表D0-4b',
        sheetCode: 'D0-4b',
        sheetUid: 'uid:D0:D0-4b',
        sheetUidNullReason: null,
        host: 'html',
        wholeWorkbook: false,
      })

    expect(resolveWorkpaperSheetContext('wp-1', 'wp-1', SHEETS[3].sheet_name, SHEETS[3], false, 'D0'))
      .toEqual({
        sheetName: '复杂测算D0-9',
        sheetCode: 'D0-9',
        sheetUid: 'uid:D0:D0-9',
        sheetUidNullReason: null,
        host: 'onlyoffice',
        wholeWorkbook: false,
      })

    expect(resolveWorkpaperSheetContext('wp-1', 'wp-1', '__whole_excel__', null, true, 'D0'))
      .toEqual({
        sheetName: '__whole_excel__',
        sheetCode: null,
        sheetUid: null,
        sheetUidNullReason: 'whole_workbook',
        host: 'onlyoffice',
        wholeWorkbook: true,
      })
  })

  it('无 canonical code 时不靠显示名发明 uid', () => {
    const unnamed = sheet('客户自定义页', null)
    expect(resolveWorkpaperSheetContext('wp-1', 'wp-1', unnamed.sheet_name, unnamed, false, 'D0'))
      .toEqual({
        sheetName: '客户自定义页',
        sheetCode: null,
        sheetUid: null,
        sheetUidNullReason: 'no_canonical_code',
        host: 'html',
        wholeWorkbook: false,
      })
  })

  it('render-config 仍属于旧 wp 时拒绝产生 context，阻止跨底稿残留', () => {
    expect(resolveWorkpaperSheetContext('wp-old', 'wp-new', SHEETS[1].sheet_name, SHEETS[1], false, 'D0'))
      .toBeNull()
  })
})

describe('Univer engine id → render-config identity', () => {
  const engineSheets = [
    { id: 'engine-1', name: '询证函控制表D0-4b' },
    { id: 'engine-2', name: '附注披露信息(上市公司)D0-8' },
    { id: 'engine-custom', name: '客户自定义页' },
  ]

  it('custom nav/native tab/locate 的共同 active id 映射到 canonical uid/code', () => {
    expect(resolveUniverSheetContext(engineSheets, 'engine-2', SHEETS, 'D0')).toEqual({
      sheetName: '附注披露信息（上市公司）D0-8',
      sheetCode: 'D0-8',
      sheetUid: 'uid:D0:D0-8',
      sheetUidNullReason: null,
      host: 'univer',
      wholeWorkbook: false,
    })
  })

  it('自定义 sheet 无 canonical identity 时保留真实 engine name，不猜 code/uid', () => {
    expect(resolveUniverSheetContext(engineSheets, 'engine-custom', SHEETS, 'D0')).toEqual({
      sheetName: '客户自定义页',
      sheetCode: null,
      sheetUid: null,
      sheetUidNullReason: 'display_name_not_identity',
      host: 'univer',
      wholeWorkbook: false,
    })
    expect(resolveUniverSheetContext(engineSheets, 'missing-id', SHEETS, 'D0')).toBeNull()
  })
})
