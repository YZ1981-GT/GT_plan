/**
 * useExcelIO ExcelJS 侧入口守卫（L1-10）—— Wave 4 Task 13（B5 批）
 * spec: frontend-excel-io-single-entry-convergence
 *
 * ## 这批为什么不换引擎
 *
 * 立项写的是「B5 = 唯一换引擎批（ExcelJS → SheetJS）」。2026-08-12 实测推翻：
 * 收敛的目标是「库调用只在一处、CVE 与版本统一管控」，**不是**「全项目用同一个库」。
 * 换引擎要逐条对齐五处语义差异（空行/1-based/尾部补齐/空单元格键/找不到 sheet 的
 * 降级），而 exceljs 是独立实现、不带 xlsx 那两个永不修复的 CVE ⇒ 风险换不来收益。
 *
 * 还有一条硬缺失：**xlsx-js-style 写入端不保留冻结窗格**。
 * `exportFormulaTemplate.ts` 依赖冻结首行，换引擎必然丢功能。
 *
 * 所以本文件的守卫重点不是「产物等价」而是两条**结构性约束**：
 *   1. 引擎确实还是 ExcelJS（冻结窗格能真的写出去 ⇒ 反证没被偷偷换成 SheetJS）
 *   2. 不是回调式（调用方能在 writeBuffer 之前拦下空工作簿）
 */
import { describe, it, expect } from 'vitest'

import { createExcelJsWorkbook, loadExcelJsWorkbook } from '../useExcelIO'

describe('L1-10 ExcelJS 侧入口（B5 批）', () => {
  it('createExcelJsWorkbook 交出可用的 ExcelJS 工作簿', async () => {
    const { wb, ExcelJS, toBuffer } = await createExcelJsWorkbook()

    expect(typeof wb.addWorksheet, '应是 ExcelJS Workbook（有 addWorksheet）').toBe('function')
    expect(typeof ExcelJS.Workbook, '应把 ExcelJS 命名空间一并交出').toBe('function')
    expect(typeof toBuffer, '应提供 toBuffer 收口产物').toBe('function')
    expect(wb.worksheets.length, '新工作簿应为空').toBe(0)
  })

  it('🔴 引擎仍是 ExcelJS —— 冻结窗格能真的写出去', async () => {
    // 这条同时反证「没被偷偷换成 SheetJS」：xlsx-js-style 的写入端会丢弃冻结窗格
    // （实测：ExcelJS 读回 state:"normal"）。故此断言只在引擎确实是 ExcelJS 时成立。
    const { wb, toBuffer } = await createExcelJsWorkbook()
    const ws = wb.addWorksheet('公式数据')
    ws.addRow(['row_code', 'row_name'])
    ws.getRow(1).font = { bold: true }
    ws.views = [{ state: 'frozen', ySplit: 1 }]

    const buf = await toBuffer()

    // 用同一引擎读回
    const rb = await loadExcelJsWorkbook(buf as ArrayBuffer)
    const rws = rb.getWorksheet('公式数据')

    expect(rws.views?.[0]?.state, '冻结窗格丢失 —— 引擎可能被换成了 SheetJS（它写不出 pane）').toBe(
      'frozen',
    )
    expect(rws.views?.[0]?.ySplit, '冻结行数应为 1').toBe(1)
    expect(rws.getCell('A1').font?.bold, '表头加粗应保留').toBe(true)
  })

  it('🔴 非回调式：不接受 build 回调，工作簿交给调用方', async () => {
    // B23 的 exportData 要「0 个 sheet 就走 warning 分支、不产出文件」。
    // 若封装做成回调式（回调内建表、封装内部直接 writeBuffer），调用方就没有
    // 「建完表、写出前」这个时机，那段业务判断无处安放。
    //
    // 注：实测空工作簿 writeBuffer() **不抛错**（立项时以为会抛）。所以「先判断」
    // 不是为了防抛错，而是纯业务决策 —— 不给用户一个空文件。
    expect(
      createExcelJsWorkbook.length,
      '不得接受参数 —— 一旦变成 createExcelJsWorkbook(build) 就是回调式，调用方失去写出前的判断时机',
    ).toBe(0)

    const { wb } = await createExcelJsWorkbook()
    expect(wb.worksheets.length, '调用方必须能在写出前拿到 sheet 数').toBe(0)
  })

  it('loadExcelJsWorkbook 接受 ArrayBuffer', async () => {
    const { wb, toBuffer } = await createExcelJsWorkbook()
    const ws = wb.addWorksheet('S1')
    ws.addRow(['A', 'B'])
    ws.addRow([1, 2])
    const buf = await toBuffer()

    const rb = await loadExcelJsWorkbook(buf as ArrayBuffer)

    expect(rb.worksheets.length).toBe(1)
    expect(rb.getWorksheet('S1').getCell('A1').value).toBe('A')
  })

  it('loadExcelJsWorkbook 接受 File（jsdom 下补 arrayBuffer polyfill）', async () => {
    const { wb, toBuffer } = await createExcelJsWorkbook()
    wb.addWorksheet('S1').addRow(['x'])
    const buf = await toBuffer()

    const file = new File([buf as ArrayBuffer], 'a.xlsx')
    Object.defineProperty(file, 'arrayBuffer', { value: async () => buf, configurable: true })

    const rb = await loadExcelJsWorkbook(file)

    expect(rb.getWorksheet('S1').getCell('A1').value).toBe('x')
  })

  it('getWorksheet 找不到时返回 undefined（GtB30 据此报「格式不符」）', async () => {
    const { wb, toBuffer } = await createExcelJsWorkbook()
    wb.addWorksheet('集团结构').addRow(['名称'])
    const buf = await toBuffer()

    const rb = await loadExcelJsWorkbook(buf as ArrayBuffer)

    expect(rb.getWorksheet('组成部分明细'), '找不到必须是 undefined，不能降级取第一个').toBeUndefined()
    expect(rb.getWorksheet('集团结构'), '存在的应能取到').toBeDefined()
  })

  it('🔴 row.values 仍是 1-based（GtB30 下游按 r[1] 取第一列）', async () => {
    // 这条钉死的是「语义没变」。若哪天有人把 GtB30 改成走 SheetJS 的 AOA，
    // 下游 r[1] 就会取到第二列 —— 整体错列，且没有任何编译期报错。
    const { wb, toBuffer } = await createExcelJsWorkbook()
    const ws = wb.addWorksheet('组成部分明细')
    ws.addRow(['名称', '总资产'])
    ws.addRow(['甲公司', 100])
    const buf = await toBuffer()

    const rb = await loadExcelJsWorkbook(buf as ArrayBuffer)
    const rows: any[] = []
    rb.getWorksheet('组成部分明细').eachRow((row: any, idx: number) => {
      if (idx > 1) rows.push(row.values)
    })

    expect(rows.length).toBe(1)
    expect(rows[0][0], 'row.values 的索引 0 应为空（1-based）').toBeUndefined()
    expect(rows[0][1], '第一列应在索引 1').toBe('甲公司')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// OOXML 合法性 —— 样式模板不得写出非法枚举值
//
// 2026-08-14 Playwright 实测顺带发现：`applyExcelStyleTemplate` 写的是
// `vertical: 'middle'`（CSS 的写法），而 OOXML 的 ST_VerticalAlignment 只认
// top / center / bottom / distributed / justify。
//
// 后果不是「样式不生效」这么轻：Excel 容忍并静默忽略，但严格读取器**拒绝打开整个
// 文件** —— openpyxl 抛 `Unable to read workbook: could not read stylesheet`。
// 本项目后端有 674 处 openpyxl，「前端导出模板 → 用户填 → 后端解析」这条路上，
// 只要用户没在 Excel 里重存过就会崩。
//
// 判据必须是「**真写出字节**后 styles.xml 里的值合法」，不能只断言源码常量 ——
// 后者是 grep 式守卫（memory 假绿三源之一）：常量对了但某处内联写死仍会漏。
// ═══════════════════════════════════════════════════════════════════════════

describe('OOXML 合法性：样式模板不写出非法枚举值', () => {
  /** OOXML ST_VerticalAlignment 的全部合法值 */
  const LEGAL_VERTICAL = new Set(['top', 'center', 'bottom', 'distributed', 'justify'])
  /** OOXML ST_HorizontalAlignment 的全部合法值 */
  const LEGAL_HORIZONTAL = new Set([
    'general',
    'left',
    'center',
    'right',
    'fill',
    'justify',
    'centerContinuous',
    'distributed',
  ])

  /** 走 applyStyles:true（默认值）真写一份字节，回读 styles.xml */
  async function stylesXmlOfStyledExport(): Promise<string> {
    const { exportMultiSheetToBytes } = await import('../useExcelIO')
    const bytes = await exportMultiSheetToBytes({
      sheets: [
        {
          sheetName: '带样式',
          columns: [
            { key: 'name', header: '项目' },
            { key: 'amt', header: '金额' },
          ],
          data: [
            { name: '货币资金', amt: 9182572.99 },
            { name: '应收账款', amt: 123456.78 },
          ],
        },
      ],
      // 不传 applyStyles ⇒ 走默认 true，正是受影响的那条路
    })

    // 用 JSZip 解 xlsx 取 styles.xml（xlsx-js-style 自带 CFB/zip 能力，但这里
    // 直接用 fflate/jszip 都不稳；改用 SheetJS 自己读回后检查 cell.s 不够 ——
    // 它读不回完整样式。故走 DecompressionStream 之外最稳的路：jszip。）
    const JSZip = (await import('jszip')).default
    const zip = await JSZip.loadAsync(bytes)
    const f = zip.file('xl/styles.xml')
    expect(f, '产物里应有 xl/styles.xml（applyStyles 默认 true）').toBeTruthy()
    return await f!.async('string')
  }

  it('🔴 vertical 只写 OOXML 合法值（middle 会让 openpyxl 拒绝打开整个文件）', async () => {
    const xml = await stylesXmlOfStyledExport()

    const verticals = [...xml.matchAll(/vertical="([^"]*)"/g)].map((m) => m[1])
    expect(verticals.length, 'styles.xml 里应有 vertical 属性（否则本守卫没在验真东西）').toBeGreaterThan(0)

    const illegal = [...new Set(verticals)].filter((v) => !LEGAL_VERTICAL.has(v))
    expect(
      illegal,
      `styles.xml 写出了非法 vertical 值 ${JSON.stringify(illegal)}。` +
        `OOXML ST_VerticalAlignment 只认 ${[...LEGAL_VERTICAL].join('/')}。` +
        'CSS 的 middle 不是合法值 —— Excel 会静默忽略，但 openpyxl 会拒绝打开整个文件' +
        '（后端 674 处 openpyxl 都会受影响）。',
    ).toEqual([])
  })

  it('horizontal 只写 OOXML 合法值', async () => {
    const xml = await stylesXmlOfStyledExport()

    const horizontals = [...xml.matchAll(/horizontal="([^"]*)"/g)].map((m) => m[1])
    const illegal = [...new Set(horizontals)].filter((v) => !LEGAL_HORIZONTAL.has(v))
    expect(illegal, `styles.xml 写出了非法 horizontal 值 ${JSON.stringify(illegal)}`).toEqual([])
  })

  it('🔴 产物能被严格读取器打开（本条是上面两条的最终判据）', async () => {
    // vitest 里没有 openpyxl，故用「styles.xml 的每个枚举属性都合法」作为代理判据。
    // 真实的 openpyxl 验证在 CI 之外由脚本做（见 tasks.md Task 18 的实证记录）。
    const xml = await stylesXmlOfStyledExport()

    // 除 alignment 外，另拦两个常见的枚举写错点
    const borderStyles = [...xml.matchAll(/<(?:top|bottom|left|right|diagonal) style="([^"]*)"/g)].map(
      (m) => m[1],
    )
    const LEGAL_BORDER = new Set([
      'none', 'thin', 'medium', 'dashed', 'dotted', 'thick', 'double', 'hair',
      'mediumDashed', 'dashDot', 'mediumDashDot', 'dashDotDot', 'mediumDashDotDot', 'slantDashDot',
    ])
    const illegalBorder = [...new Set(borderStyles)].filter((v) => !LEGAL_BORDER.has(v))
    expect(illegalBorder, `非法 border style ${JSON.stringify(illegalBorder)}`).toEqual([])

    const patterns = [...xml.matchAll(/patternType="([^"]*)"/g)].map((m) => m[1])
    const LEGAL_PATTERN = new Set([
      'none', 'solid', 'mediumGray', 'darkGray', 'lightGray', 'darkHorizontal', 'darkVertical',
      'darkDown', 'darkUp', 'darkGrid', 'darkTrellis', 'lightHorizontal', 'lightVertical',
      'lightDown', 'lightUp', 'lightGrid', 'lightTrellis', 'gray125', 'gray0625',
    ])
    const illegalPattern = [...new Set(patterns)].filter((v) => !LEGAL_PATTERN.has(v))
    expect(illegalPattern, `非法 patternType ${JSON.stringify(illegalPattern)}`).toEqual([])
  })
})
