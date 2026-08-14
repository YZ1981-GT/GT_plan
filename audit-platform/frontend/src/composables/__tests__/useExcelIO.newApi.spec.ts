/**
 * useExcelIO L1 新增 API 契约守卫 —— Wave 2 Task 4~7
 * spec: frontend-excel-io-single-entry-convergence
 *   (Requirements 2.8 / 3.1 / 3.2 / 3.3 / 3.4 · Property 13 / 14 / 15 / 16 / 17)
 *
 * ## 这四项 API 为什么是迁移的硬前置
 *
 * 46 个待迁移文件里，机械替换会**静默改变产物**，因为本封装的默认值是「加工过的」：
 * - `applyStyles` 默认 true → 给原本无样式的产物加仿宋 + 三线表
 * - `includeNoteRow` 默认 true → 在表头前插一行，全表行号下移
 * - 成功提示写死在封装内 → 调用方自己也弹时出现重复弹窗
 *
 * 前两项改造前就能用 `false` 关掉，第三项**改造前无法关闭** ⇒ `successMessage`
 * 不先加，就没有任何办法在迁移时保持文案等价（R2.8）。
 *
 * ## 🔴 立项时另写的三项「硬阻塞」，实测全部不成立（2026-08-14 复核）
 *
 * 立项理由原文与实际结果对照：
 *
 * | 立项理由 | 实际 |
 * | --- | --- |
 * | `exportToBytes` ← 4 个 exceljs 文件用 `writeBuffer` 自行处理产物 | 那 4 个文件改走 `createExcelJsWorkbook().toBuffer()`（引擎不变），**未用** |
 * | `sheetMatcher` ← `ShareChangeSheet` 按「含公司名且含净资产」模糊定位 | 它要跨「公司数 × 3」个 sheet 逐家匹配，单 sheet 定位表达不了，改走 `readWorkbookAoa`，**未用** ⇒ 已删 |
 * | `customInstructionSheet` ← 12 个函证文件说明 sheet 是手写长文本 | 14 个文件走 `exportMultiSheetData` + 纯 AOA，**未用** ⇒ 已删 |
 *
 * 教训：立项阶段判定「某能力是某批文件的硬阻塞」时，如果没有先把那批文件的目标写法
 * 落到具体代码，判断很容易错 —— 三项里错了三项。后来补出的 L1-5（多 sheet 纯 AOA）
 * 与 L1-9（整簿读）才是真正解决问题的，而它们**立项时都没预见到**。
 *
 * `exportToBytes` / `exportMultiSheetToBytes` 未删，原因不是「留着备用」，而是
 * **它们是 OOXML 合法性守卫的载体**：只有拿到真实字节才能解 zip 读 `styles.xml`，
 * 而 mock `writeFile` 拿到的内存 wb 里 `cell.s` 未经序列化，验不出实际写入的值 ——
 * `vertical:'middle'` 那个缺陷正是靠这条路径发现的（见 useExcelIO.excelJs.spec.ts）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

import {
  exportData,
  exportMultiSheetData,
  exportMultiSheetToBytes,
  exportTemplate,
  exportToBytes,
  parseFile,
  type ExcelColumn,
} from '../useExcelIO'

// ── mock ElMessage 以验证提示三态 ──
const successSpy = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: {
    success: (...args: any[]) => successSpy(...args),
    warning: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}))

// ── mock writeFile 以捕获落盘文件名、避免真写盘；其余 API 用真实实现 ──
const writtenFiles: Array<{ fileName: string; wb: any }> = []

/**
 * xlsx-js-style 是 CJS 模块，vitest 下 `importActual` 返回 `{ default: 实际模块, ... }`，
 * 顶层不一定带 `utils` ⇒ 必须**先解包 default** 再展开，否则 `_loadXlsxStyle` 的
 * `mod.utils` 与 `mod.default.utils` 两条检查路径都落空，报
 * 「No "utils" export is defined on the mock」。
 * 写法沿用已验证的 useExcelIO.spec.ts。
 */
vi.mock('xlsx-js-style', async () => {
  const actual: any = await vi.importActual('xlsx-js-style')
  const real: any = actual.default && actual.default.utils ? actual.default : actual
  const stubbedWriteFile = (wb: any, fileName: string) => {
    writtenFiles.push({ fileName, wb })
  }
  return {
    ...real,
    writeFile: stubbedWriteFile,
    default: { ...real, writeFile: stubbedWriteFile },
  }
})

const COLUMNS: ExcelColumn[] = [
  { key: 'code', header: '编号', width: 12 },
  { key: 'name', header: '名称', width: 20 },
]
const DATA = [
  { code: 'E-1', name: '甲' },
  { code: 'E-2', name: '乙' },
]

beforeEach(() => {
  successSpy.mockClear()
  writtenFiles.length = 0
})

/** 用真实 xlsx 把字节读回，便于做语义比对（禁比 sha256，见 design §行为等价判据边界） */
async function readBack(bytes: Uint8Array): Promise<any> {
  const XLSX: any = await import('xlsx')
  return XLSX.read(bytes, { type: 'array' })
}

// ═══════════════════════════════════════════════════════════════════════════
// Property 14 — exportToBytes 与 exportData 同源
// ═══════════════════════════════════════════════════════════════════════════

describe('L1-1 exportToBytes / exportMultiSheetToBytes（Property 14 / R3.1）', () => {
  it('返回 Uint8Array 且可被 reader 读回', async () => {
    const bytes = await exportToBytes({ data: DATA, columns: COLUMNS, sheetName: '数据' })

    expect(bytes, '应返回 Uint8Array').toBeInstanceOf(Uint8Array)
    expect(bytes.byteLength, '字节数应大于 0').toBeGreaterThan(0)

    const wb = await readBack(bytes)
    expect(wb.SheetNames).toEqual(['数据'])
  })

  it('不触发下载、不弹提示（供调用方自行处理产物）', async () => {
    await exportToBytes({ data: DATA, columns: COLUMNS })

    expect(writtenFiles.length, 'exportToBytes 不该调 writeFile').toBe(0)
    expect(successSpy, 'exportToBytes 不该弹提示').not.toHaveBeenCalled()
  })

  it('与 exportData 产出的工作簿逐格相等（同源判据）', async () => {
    // 走 exportData 拿到 wb（writeFile 被 mock 捕获）
    await exportData({ data: DATA, columns: COLUMNS, sheetName: '数据', fileName: 'x.xlsx' })
    expect(writtenFiles.length, 'exportData 应调用 writeFile').toBe(1)
    const wbFromExportData = writtenFiles[0].wb

    // 走 exportToBytes 拿字节再读回
    const bytes = await exportToBytes({ data: DATA, columns: COLUMNS, sheetName: '数据' })
    const wbFromBytes = await readBack(bytes)

    expect(wbFromBytes.SheetNames, 'sheet 名应一致').toEqual(wbFromExportData.SheetNames)

    const XLSX: any = await import('xlsx')
    const aoaA = XLSX.utils.sheet_to_json(wbFromExportData.Sheets['数据'], { header: 1 })
    const aoaB = XLSX.utils.sheet_to_json(wbFromBytes.Sheets['数据'], { header: 1 })
    expect(
      aoaB,
      '两个入口产出的单元格不一致 —— 说明建表逻辑被复制成了两份（design 明确禁止）',
    ).toEqual(aoaA)
  })

  it('L1-5 多 sheet 支持纯 AOA 形态（原样写入 + colWidths 原样传）', async () => {
    const instructions = [
      ['D0-5 合同负债及销售替代程序 — 导入模板说明'],
      [''],
      ['【列名请勿修改】第一行列名与源模板逐字一致'],
    ]

    await exportMultiSheetData({
      sheets: [
        // 结构化形态
        { sheetName: '公司汇总', columns: COLUMNS, data: DATA },
        // 只有表头行的空模板（AOA）
        { sheetName: '①期后结转', rows: [['列A', '列B', '列C']], colWidths: [{ wch: 20 }, { wch: 12 }, { wch: 12 }] },
        // 纯文本说明（AOA）
        { sheetName: '填写说明', rows: instructions, colWidths: [{ wch: 80 }] },
      ],
      fileName: 'mixed.xlsx',
      applyStyles: false,
      successMessage: false,
    })

    expect(writtenFiles.length).toBe(1)
    const wb = writtenFiles[0].wb
    expect(wb.SheetNames, '三种形态混排时 sheet 顺序必须保持').toEqual(['公司汇总', '①期后结转', '填写说明'])

    const XLSX: any = await import('xlsx')

    // AOA sheet 原样写入
    const aoaB = XLSX.utils.sheet_to_json(wb.Sheets['①期后结转'], { header: 1 })
    expect(aoaB[0]).toEqual(['列A', '列B', '列C'])
    expect(aoaB.length, '只有表头行的 sheet 不应被塞进数据行').toBe(1)
    expect(wb.Sheets['①期后结转']['!cols'], 'colWidths 应原样传递').toEqual([
      { wch: 20 },
      { wch: 12 },
      { wch: 12 },
    ])

    const aoaC = XLSX.utils.sheet_to_json(wb.Sheets['填写说明'], { header: 1, blankrows: true })
    expect(aoaC[0]).toEqual([instructions[0][0]])
    expect(aoaC[2]).toEqual([instructions[2][0]])
    expect(wb.Sheets['填写说明']['!cols']).toEqual([{ wch: 80 }])

    // AOA sheet 不该被套三线表样式
    const styledInAoa = Object.keys(wb.Sheets['填写说明']).filter(
      (k) => !k.startsWith('!') && wb.Sheets['填写说明'][k]?.s,
    )
    expect(styledInAoa, 'AOA sheet 应原样写入，不套任何样式').toEqual([])
  })

  it('L1-5 AOA sheet 名同样截断到 31 字符', async () => {
    await exportMultiSheetData({
      sheets: [{ sheetName: 'Y'.repeat(40), rows: [['A']] }],
      fileName: 'x.xlsx',
      successMessage: false,
    })
    expect(writtenFiles[0].wb.SheetNames[0].length).toBe(31)
  })

  it('L1-5 省略 colWidths 时不设置 !cols（区分「无列宽」与「空数组」）', async () => {
    await exportMultiSheetData({
      sheets: [{ sheetName: 'A', rows: [['x']] }],
      fileName: 'x.xlsx',
      successMessage: false,
    })
    expect(writtenFiles[0].wb.Sheets['A']['!cols']).toBeUndefined()
  })

  it('exportMultiSheetToBytes 保持多 sheet 名与顺序', async () => {
    const bytes = await exportMultiSheetToBytes({
      sheets: [
        { sheetName: '甲表', columns: COLUMNS, data: DATA },
        { sheetName: '乙表', columns: COLUMNS, data: DATA },
      ],
    })

    const wb = await readBack(bytes)
    expect(wb.SheetNames, 'sheet 顺序必须保持').toEqual(['甲表', '乙表'])
    expect(successSpy, 'toBytes 变体不该弹提示').not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// parseFile 的 sheet 定位与 requireFirstCell
//
// ⚠️ 原有「L1-2 sheetMatcher」5 例（Property 15 / R3.2）已随该选项一并删除，
// 2026-08-14。立项判定它是「ShareChangeSheet 按『含公司名且含净资产』模糊定位」
// 的硬前置，实测**零生产消费方** —— 那个文件要在「公司数 × 3」个 sheet 间逐家
// 匹配，单 sheet 定位表达不了，最后走了 `readWorkbookAoa`（L1-9）。
// ⇒ L1-9 功能上覆盖了 L1-2，留着是设计冗余。定位现在只有两级：sheetName → 第一个。
// ═══════════════════════════════════════════════════════════════════════════

describe('parseFile sheet 定位（两级）与 requireFirstCell（L1-6）', () => {
  /** 构造多 sheet 文件；jsdom 缺 File.arrayBuffer 故补 polyfill */
  async function makeMultiSheetFile(sheetNames: string[]): Promise<File> {
    const XLSX: any = await import('xlsx')
    const wb = XLSX.utils.book_new()
    for (const name of sheetNames) {
      const ws = XLSX.utils.aoa_to_sheet([['标记'], [name]])
      XLSX.utils.book_append_sheet(wb, ws, name)
    }
    const bytes = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
    const file = new File([bytes], 'multi.xlsx')
    if (typeof (file as any).arrayBuffer !== 'function') {
      Object.defineProperty(file, 'arrayBuffer', { value: async () => bytes, configurable: true })
    }
    return file
  }

  it('sheetName 精确匹配（第一级）', async () => {
    const file = await makeMultiSheetFile(['数据填写', '甲公司净资产', '其他'])
    const res = await parseFile(file, { sheetName: '甲公司净资产' })
    expect(res.rows[0].标记).toBe('甲公司净资产')
  })

  it('找不到时降级取第一个 sheet（第二级，与改造前逐字相同）', async () => {
    const file = await makeMultiSheetFile(['数据填写', '其他'])

    const res = await parseFile(file, { sheetName: '数据填写' })
    expect(res.rows[0].标记).toBe('数据填写')

    const res2 = await parseFile(file, { sheetName: '不存在' })
    expect(res2.rows[0].标记, '找不到指定 sheet 时仍取第一个').toBe('数据填写')
  })

  it('🔴 L1-6 requireFirstCell:false 时首列留空的行不被丢弃', async () => {
    const XLSX: any = await import('xlsx')
    const wb = XLSX.utils.book_new()
    // 模板首列是「序号」，说明书写「留空即可」⇒ 真实数据里首列常为空
    const ws = XLSX.utils.aoa_to_sheet([
      ['序号', '公司名称'],
      ['', '甲公司'],
      ['2', '乙公司'],
      ['', ''],
    ])
    XLSX.utils.book_append_sheet(wb, ws, '数据填写')
    const bytes = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
    const file = new File([bytes], 'a.xlsx')
    if (typeof (file as any).arrayBuffer !== 'function') {
      Object.defineProperty(file, 'arrayBuffer', { value: async () => bytes, configurable: true })
    }

    // 默认（requireFirstCell 省略 = true）：首列空的行被丢
    const withDefault = await parseFile(file, { sheetName: '数据填写' })
    expect(
      withDefault.rows.length,
      '默认行为要求首列非空 —— 这正是会静默丢数据的那个隐含假设',
    ).toBe(1)
    expect(withDefault.rows[0].公司名称).toBe('乙公司')

    // 关掉后：首列空但其余有值的行保留，整行全空的仍丢
    const relaxed = await parseFile(file, { sheetName: '数据填写', requireFirstCell: false })
    expect(relaxed.rows.length, '应保留 2 行（甲/乙），整行全空的那行仍须丢弃').toBe(2)
    expect(relaxed.rows[0].公司名称).toBe('甲公司')
    expect(relaxed.rows[1].公司名称).toBe('乙公司')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// L1-7/8 低层读取 —— readSheetAoa / readSheetObjects
//
// 这两个 API 的唯一职责是把库调用收敛进单一入口，**语义必须与直接调 SheetJS
// 逐项相同**。故守卫的判据是「与手写 XLSX.read + sheet_to_json 的结果逐项相等」，
// 而不是「结果看起来合理」—— 后者会放过 defval / raw / cellDates 透传不全这类
// 静默改数的偏差。
// ═══════════════════════════════════════════════════════════════════════════

describe('L1-7/8 低层读取 readSheetAoa / readSheetObjects', () => {
  async function makeFile(aoa: any[][], sheetNames = ['Sheet1']): Promise<File> {
    const XLSX: any = await import('xlsx')
    const wb = XLSX.utils.book_new()
    sheetNames.forEach((name, idx) => {
      XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(idx === 0 ? aoa : [['other']]), name)
    })
    const bytes = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
    const file = new File([bytes], 'low.xlsx')
    if (typeof (file as any).arrayBuffer !== 'function') {
      Object.defineProperty(file, 'arrayBuffer', { value: async () => bytes, configurable: true })
    }
    return file
  }

  it('readSheetAoa 与手写 read + sheet_to_json(header:1) 逐项相等', async () => {
    const aoa = [
      ['列A', '列B', '列C'],
      ['a1', 1, ''],
      ['a2', 2, 'c2'],
    ]
    const file = await makeFile(aoa)
    const { readSheetAoa } = await import('../useExcelIO')

    const got = await readSheetAoa(file, { defval: '' })

    // 手写基准
    const XLSX: any = await import('xlsx')
    const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' })
    const expected = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { header: 1, defval: '' })

    expect(got.rows).toEqual(expected)
    expect(got.sheetName).toBe('Sheet1')
    expect(got.truncatedRows).toBe(0)
  })

  it('🔴 defval 透传生效：空单元格填 "" 而非归一为 null', async () => {
    const file = await makeFile([
      ['A', 'B'],
      ['a1', ''],
    ])
    const { readSheetAoa, readSheetObjects } = await import('../useExcelIO')

    const aoaRes = await readSheetAoa(file, { defval: '' })
    expect(aoaRes.rows[1][1], 'defval 未透传 —— B3 批全部 8 个文件都显式传 defval:""').toBe('')

    const objRes = await readSheetObjects(file, { defval: '' })
    expect(objRes.rows[0].B, '对象模式的 defval 同样要透传').toBe('')
    expect(objRes.rows[0].B, '不得像 parseFile 那样归一为 null（下游用 ?? 时行为不同）').not.toBeNull()
  })

  it('readSheetObjects 与手写 sheet_to_json(defval) 逐项相等', async () => {
    const aoa = [
      ['资产名称', '原值', '备注'],
      ['设备甲', 1000, ''],
      ['设备乙', 2000, '备注2'],
    ]
    const file = await makeFile(aoa)
    const { readSheetObjects } = await import('../useExcelIO')

    const got = await readSheetObjects(file, { defval: '' })

    const XLSX: any = await import('xlsx')
    const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' })
    const expected = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { defval: '' })

    expect(got.rows).toEqual(expected)
  })

  it('cellDates 透传：true 时日期返回 Date，省略时返回序列号', async () => {
    const XLSX: any = await import('xlsx')
    const wb = XLSX.utils.book_new()
    const ws = XLSX.utils.aoa_to_sheet([['日期'], [new Date(Date.UTC(2025, 11, 31))]])
    XLSX.utils.book_append_sheet(wb, ws, 'Sheet1')
    const bytes = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
    const file = new File([bytes], 'd.xlsx')
    if (typeof (file as any).arrayBuffer !== 'function') {
      Object.defineProperty(file, 'arrayBuffer', { value: async () => bytes, configurable: true })
    }

    const { readSheetAoa } = await import('../useExcelIO')

    const withDates = await readSheetAoa(file, { cellDates: true })
    expect(withDates.rows[1][0], 'cellDates:true 时应为 Date 实例').toBeInstanceOf(Date)

    const withoutDates = await readSheetAoa(file, { cellDates: false })
    expect(
      withoutDates.rows[1][0] instanceof Date,
      'cellDates:false 时不应为 Date（H1 传 true、其余 6 个传 false，透传不全会静默改类型）',
    ).toBe(false)
  })

  it('raw:false 透传：返回格式化字符串而非原始值', async () => {
    const file = await makeFile([['数值'], [1234.5]])
    const { readSheetAoa } = await import('../useExcelIO')

    const rawTrue = await readSheetAoa(file, { raw: true })
    expect(typeof rawTrue.rows[1][0]).toBe('number')

    const rawFalse = await readSheetAoa(file, { raw: false })
    expect(typeof rawFalse.rows[1][0], 'raw:false 时应为字符串（useH1Depreciation 依赖此行为）').toBe('string')
  })

  it('sheet 定位两级优先级与 parseFile 口径一致（共用 _pickSheetName）', async () => {
    const file = await makeFile([['x']], ['数据填写', '甲公司净资产'])
    const { readSheetAoa } = await import('../useExcelIO')

    const byName = await readSheetAoa(file, { sheetName: '甲公司净资产' })
    expect(byName.sheetName).toBe('甲公司净资产')

    const fallback = await readSheetAoa(file, { sheetName: '不存在' })
    expect(fallback.sheetName, '找不到时降级取第一个').toBe('数据填写')

    const omitted = await readSheetAoa(file)
    expect(omitted.sheetName, '不传 sheetName 时取第一个').toBe('数据填写')
  })

  /**
   * 🔴 SheetJS 对象模式对冲突列头**改名而非跳过**（2026-08-12 实测 xlsx@0.18.5）
   *
   * 列头 `['constructor','prototype','__proto__','正常列']` 经 `sheet_to_json` 后，
   * 实际自有键是：
   *   `["__rowNum__","constructor_NaN","prototype","__proto___NaN","正常列"]`
   *
   * 即 SheetJS 用 `key in obj` 判重，命中原型链就加后缀去重，而后缀算成了 `NaN`。
   * `prototype` 因 `'prototype' in {}` 为 false 而保持原名。
   *
   * 两个结论：
   * 1. **原型污染在这条路径上被 SheetJS 自己规避了** —— `Object.prototype` 实测未被污染。
   *    `_BLOCKED_KEYS` 在此是第二道防线（拦 `prototype`）；它在 `parseFile` 那条
   *    「AOA → 自建对象」路径上才是唯一防线，那里三键都能拦全。
   * 2. **数据会落到 `constructor_NaN` 这种意外键名下** —— 调用方按 `r['constructor']`
   *    取值会得到 undefined。这是 SheetJS 既有行为，不在本次收敛中改（改了就不是
   *    行为等价了），但要留证在此，免得下轮有人把它当成本封装引入的 bug。
   */
  it('readSheetObjects 做原型污染防护，且如实反映 SheetJS 的改名行为', async () => {
    const file = await makeFile([
      ['constructor', 'prototype', '__proto__', '正常列'],
      ['v1', 'v2', 'v3', 'ok'],
    ])
    const { readSheetObjects } = await import('../useExcelIO')

    const protoBefore = Object.getOwnPropertyNames(Object.prototype).sort()
    const res = await readSheetObjects(file, { defval: '' })
    const own = Object.getOwnPropertyNames(res.rows[0])

    // 危险键的**原名**一律不在结果里
    expect(own, 'constructor 原名不该出现').not.toContain('constructor')
    expect(own, 'prototype 原名不该出现（这个是被 _BLOCKED_KEYS 拦下的）').not.toContain('prototype')
    expect(own, '__proto__ 原名不该出现').not.toContain('__proto__')

    // 被 _BLOCKED_KEYS 实际拦下的只有 prototype（另两个已被 SheetJS 改名）
    expect(res.blockedKeys, '_BLOCKED_KEYS 应拦下 prototype').toContain('prototype')

    // SheetJS 改名产物如实存在 —— 记录既有行为，不做修改
    expect(own, 'SheetJS 把 constructor 改名为 constructor_NaN').toContain('constructor_NaN')
    expect(own, 'SheetJS 把 __proto__ 改名为 __proto___NaN').toContain('__proto___NaN')

    // 正常列不受影响，原型未被污染
    expect(res.rows[0]['正常列']).toBe('ok')
    expect(Object.getPrototypeOf(res.rows[0]), '应转回普通对象').toBe(Object.prototype)
    expect(
      Object.getOwnPropertyNames(Object.prototype).sort(),
      'Object.prototype 不得被污染',
    ).toEqual(protoBefore)
  })

  it('maxRows 截断并回报（低层也有上限保护）', async () => {
    const aoa: any[][] = [['A']]
    for (let i = 0; i < 20; i += 1) aoa.push([`r${i}`])
    const file = await makeFile(aoa)
    const { readSheetAoa } = await import('../useExcelIO')

    const res = await readSheetAoa(file, { maxRows: 5 })
    expect(res.rows.length).toBe(5)
    expect(res.truncatedRows).toBe(16) // 21 行(含表头) - 5
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// exportTemplate 的 includeInstructions
//
// ⚠️ 原有「L1-3 customInstructionSheet」6 例（Property 16 / R3.3）已随该选项
// 一并删除，2026-08-14。立项判定它是「B2 函证组 12 文件无法迁移的硬阻塞」，实测
// **零生产消费方** —— 那 14 个文件走的是 `exportMultiSheetData` + 纯 AOA 形态
// （L1-5），因为说明 sheet 与数据 sheet 本就是同一批 `sheets[]` 里的两项。
// ⇒ L1-5 功能上覆盖了 L1-3。
//
// 下面两条**保留**：它们验的是 `includeInstructions` 自身（真有调用方），
// 与被删的选项无关。其中「说明 sheet 在数据 sheet 之前」是判断
// `ExcelImportPreviewDialog`「降级取最后一个 sheet」是否合理的**依据**
// （见 tasks.md Task 18 内那条被撤回的误判），删了会让那个结论失去支撑。
// ═══════════════════════════════════════════════════════════════════════════

describe('exportTemplate includeInstructions', () => {
  it('生成通用提示 + 「字段说明」表', async () => {
    await exportTemplate({
      columns: COLUMNS,
      fileName: 'tpl.xlsx',
      includeInstructions: true,
    })

    const wb = writtenFiles[0].wb
    const XLSX: any = await import('xlsx')
    const text = JSON.stringify(XLSX.utils.sheet_to_json(wb.Sheets['填写说明'], { header: 1 }))
    expect(text, '通用提示应仍然生成').toContain('重要提示')
    expect(text, '字段说明表应仍然生成').toContain('字段说明')
  })

  it('🔴 说明 sheet 在数据 sheet 之前（`ExcelImportPreviewDialog` 降级取最后一个 sheet 的依据）', async () => {
    await exportTemplate({
      columns: COLUMNS,
      fileName: 'tpl.xlsx',
      sheetName: '数据区',
      includeNoteRow: false,
      applyStyles: false,
      includeInstructions: true,
    })

    expect(
      writtenFiles[0].wb.SheetNames,
      '说明 sheet 必须在前 —— ExcelImportPreviewDialog 的「降级取最后一个 sheet 以跳过填写说明」' +
        '正是建立在这个顺序上。若这里改成说明在后，那个降级规则就会取错 sheet。',
    ).toEqual(['填写说明', '数据区'])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 13 / 17 — successMessage 三态与既有零回归
// ═══════════════════════════════════════════════════════════════════════════

describe('L1-4 successMessage 三态（Property 13 / R2.8 / R3.4）', () => {
  it('省略时用默认文案（既有调用方零回归）', async () => {
    await exportData({ data: DATA, columns: COLUMNS, fileName: 'a.xlsx' })
    expect(successSpy).toHaveBeenCalledWith('数据已导出')

    successSpy.mockClear()
    await exportTemplate({ columns: COLUMNS, fileName: 'b.xlsx' })
    expect(successSpy).toHaveBeenCalledWith('模板已导出')
  })

  it('传 string 时用该文案', async () => {
    await exportData({ data: DATA, columns: COLUMNS, fileName: 'a.xlsx', successMessage: '已生成 E0-6 数据' })
    expect(successSpy).toHaveBeenCalledWith('已生成 E0-6 数据')
  })

  it('传 false 时不弹（供调用方自行提示，避免重复弹窗）', async () => {
    await exportData({ data: DATA, columns: COLUMNS, fileName: 'a.xlsx', successMessage: false })
    expect(successSpy, 'successMessage:false 时封装不该弹提示').not.toHaveBeenCalled()

    await exportTemplate({ columns: COLUMNS, fileName: 'b.xlsx', successMessage: false })
    expect(successSpy).not.toHaveBeenCalled()
  })

  it('exportMultiSheetData 三态一致', async () => {
    await exportMultiSheetData({
      sheets: [{ sheetName: '甲', columns: COLUMNS, data: DATA }],
      fileName: 'm.xlsx',
    })
    expect(successSpy).toHaveBeenCalledWith('数据已导出')

    successSpy.mockClear()
    await exportMultiSheetData({
      sheets: [{ sheetName: '甲', columns: COLUMNS, data: DATA }],
      fileName: 'm.xlsx',
      successMessage: false,
    })
    expect(successSpy).not.toHaveBeenCalled()
  })

  it('提示只弹一次（防封装与调用方双弹）', async () => {
    await exportData({ data: DATA, columns: COLUMNS, fileName: 'a.xlsx' })
    expect(successSpy, '同一次导出弹了多次提示').toHaveBeenCalledTimes(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 17 — 三个显式关闭组合下的产物形状（迁移默认姿势）
// ═══════════════════════════════════════════════════════════════════════════

describe('迁移默认姿势：三个显式关闭的产物形状（Property 8 / 17）', () => {
  it('applyStyles:false 时不写入任何 cell.s 与 !cols 自动列宽', async () => {
    await exportData({ data: DATA, columns: COLUMNS, fileName: 'a.xlsx', applyStyles: false, successMessage: false })

    const ws = writtenFiles[0].wb.Sheets['数据']
    // applyStyles:false 分支只按 header 长度设 !cols，不设 cell.s
    const styled = Object.keys(ws).filter((k) => !k.startsWith('!') && ws[k]?.s)
    expect(styled, 'applyStyles:false 时不该有任何带样式的单元格').toEqual([])
  })

  it('includeNoteRow:false 时表头就是第一行（不插 note 行）', async () => {
    await exportTemplate({
      columns: COLUMNS,
      fileName: 'b.xlsx',
      includeNoteRow: false,
      applyStyles: false,
      successMessage: false,
      sheetName: '数据填写',
    })

    const XLSX: any = await import('xlsx')
    const aoa = XLSX.utils.sheet_to_json(writtenFiles[0].wb.Sheets['数据填写'], { header: 1 })
    expect(aoa[0], '第一行必须是表头 —— 若是 note 行则全表行号下移，导入侧会整体错行').toEqual([
      '编号',
      '名称',
    ])
  })

  it('includeNoteRow 默认 true 时确实会插 note 行（证明该默认值的危险性）', async () => {
    await exportTemplate({
      columns: [
        { key: 'code', header: '编号', note: '请填编号' },
        { key: 'name', header: '名称', note: '请填名称' },
      ],
      fileName: 'c.xlsx',
      applyStyles: false,
      successMessage: false,
      sheetName: '数据填写',
    })

    const XLSX: any = await import('xlsx')
    const aoa = XLSX.utils.sheet_to_json(writtenFiles[0].wb.Sheets['数据填写'], { header: 1 })
    expect(aoa[0], '默认值下第一行是 note 行 —— 这就是机械迁移会破坏行为等价的原因').toEqual([
      '请填编号',
      '请填名称',
    ])
    expect(aoa[1]).toEqual(['编号', '名称'])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// L1-9 整簿读取 —— readWorkbookAoa
//
// 这个 API 的存在理由很窄：**跨 sheet 匹配导入**。
// ShareChangeSheet.onFileSelected 要在「公司数 × 3」个 sheet 里按「含公司名且含
// 净资产」逐家模糊匹配；ConsolNoteTab.onNoteBatchImport 要遍历全部 sheet 按章节
// 标题匹配。这两处原实现都是 **read 一次 + 多次 sheet_to_json**。
//
// 若改成多次调 readSheetAoa，就会对同一份文件重复 arrayBuffer() + read() N 次
// —— 既慢，也不等价于原行为。所以下面「只解析一次」那条守卫不是性能测试，
// 它钉的是这个 API 的存在理由：一旦有人把实现改成内部循环调 readSheetAoa，
// 理由就被抹掉了，该条必须打红。
// ═══════════════════════════════════════════════════════════════════════════

describe('L1-9 整簿读取 readWorkbookAoa', () => {
  /** 构造每个 sheet 内容各不相同的多 sheet 文件 */
  async function makeWorkbookFile(sheets: Record<string, any[][]>): Promise<File> {
    const XLSX: any = await import('xlsx')
    const wb = XLSX.utils.book_new()
    for (const [name, aoa] of Object.entries(sheets)) {
      XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(aoa), name)
    }
    const bytes = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
    const file = new File([bytes], 'wb.xlsx')
    Object.defineProperty(file, 'arrayBuffer', { value: async () => bytes, configurable: true })
    return file
  }

  const FIXTURE: Record<string, any[][]> = {
    甲公司净资产: [['项目', '变动前'], ['实收资本', 1000]],
    '甲公司-直接模拟': [['科目', '明细', '借'], ['长期股权投资', '成本', 500]],
    乙公司净资产: [['项目', '变动前'], ['资本公积', 200]],
  }

  it('与手写 read + 逐 sheet sheet_to_json(header:1) 逐项相等', async () => {
    const file = await makeWorkbookFile(FIXTURE)
    const { readWorkbookAoa } = await import('../useExcelIO')

    const got = await readWorkbookAoa(file)

    // 手写基准：原实现就是这么写的
    const XLSX: any = await import('xlsx')
    const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' })
    for (const name of wb.SheetNames) {
      const expected = XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1 })
      expect(got.sheets[name], `sheet「${name}」的 AOA 与手写基准不符`).toEqual(expected)
    }
  })

  it('🔴 只解析一次（这是本 API 存在的唯一理由）', async () => {
    const file = await makeWorkbookFile(FIXTURE)
    const { readWorkbookAoa } = await import('../useExcelIO')

    // 计数 arrayBuffer 调用次数：一次解析 ⇒ 恰好 1 次
    const original = (file as any).arrayBuffer.bind(file)
    let calls = 0
    Object.defineProperty(file, 'arrayBuffer', {
      value: async () => {
        calls += 1
        return original()
      },
      configurable: true,
    })

    const got = await readWorkbookAoa(file)

    expect(Object.keys(got.sheets).length, '应拿到全部 3 个 sheet').toBe(3)
    expect(
      calls,
      '文件被解析了多次 —— 若实现改成内部循环调 readSheetAoa，本 API 就没有存在理由了（应直接用 readSheetAoa）',
    ).toBe(1)
  })

  it('sheetNames 保持工作簿内顺序（按名匹配的调用方依赖遍历序）', async () => {
    const file = await makeWorkbookFile(FIXTURE)
    const { readWorkbookAoa } = await import('../useExcelIO')

    const got = await readWorkbookAoa(file)

    expect(got.sheetNames).toEqual(['甲公司净资产', '甲公司-直接模拟', '乙公司净资产'])
  })

  it('sheetNames 与 sheets 的键集合一致（不漏 sheet、不多造 sheet）', async () => {
    const file = await makeWorkbookFile(FIXTURE)
    const { readWorkbookAoa } = await import('../useExcelIO')

    const got = await readWorkbookAoa(file)

    expect(Object.keys(got.sheets).sort()).toEqual([...got.sheetNames].sort())
  })

  it('🔴 空 sheet 返回空数组而非 undefined', async () => {
    // ConsolNoteTab.onNoteBatchImport 直接写 `if (json.length < 2) continue`，
    // 拿到 undefined 会抛 TypeError 而不是跳过该 sheet。
    const file = await makeWorkbookFile({ 有内容: [['A'], ['a1']], 空表: [] })
    const { readWorkbookAoa } = await import('../useExcelIO')

    const got = await readWorkbookAoa(file)

    expect(got.sheets['空表'], '空 sheet 必须返回 []，否则调用方的 .length 会抛').toEqual([])
    expect(() => got.sheets['空表'].length).not.toThrow()
  })

  it('maxRows 对每个 sheet 分别截断', async () => {
    const many: any[][] = [['A']]
    for (let i = 0; i < 20; i += 1) many.push([`r${i}`])
    const file = await makeWorkbookFile({ 大表: many, 小表: [['B'], ['b1']] })
    const { readWorkbookAoa } = await import('../useExcelIO')

    const got = await readWorkbookAoa(file, { maxRows: 5 })

    expect(got.sheets['大表'].length).toBe(5)
    expect(got.sheets['小表'].length, '未超限的 sheet 不受影响').toBe(2)
  })

  it('🔴 截断必须如实回报 truncatedRows（R4.3：不静默丢数据）', async () => {
    // 改造前本函数是四个读入口里唯一**静默截断**的：调用方拿到少了行的数据却无从知晓。
    const many: any[][] = [['A']]
    for (let i = 0; i < 20; i += 1) many.push([`r${i}`])
    const file = await makeWorkbookFile({ 大表: many, 小表: [['B'], ['b1']] })
    const { readWorkbookAoa } = await import('../useExcelIO')

    const got = await readWorkbookAoa(file, { maxRows: 5 })

    expect(got.truncatedRows, 'truncatedRows 字段缺失 —— 截断被静默吞掉').toBeDefined()
    // 21 行（含表头）截到 5 ⇒ 丢 16
    expect(got.truncatedRows['大表'], '被截断的 sheet 应回报丢弃行数').toBe(16)
    expect(
      '小表' in got.truncatedRows,
      '未截断的 sheet 不该出现在 truncatedRows 里（否则调用方无法一眼看出哪些表被截了）',
    ).toBe(false)
  })

  it('未触发上限时 truncatedRows 为空对象', async () => {
    const file = await makeWorkbookFile(FIXTURE)
    const { readWorkbookAoa } = await import('../useExcelIO')

    const got = await readWorkbookAoa(file)

    expect(got.truncatedRows).toEqual({})
  })

  it('defval / raw 透传到每个 sheet', async () => {
    const file = await makeWorkbookFile({
      表一: [['A', 'B'], ['a1', '']],
      表二: [['数值'], [1234.5]],
    })
    const { readWorkbookAoa } = await import('../useExcelIO')

    const withDefval = await readWorkbookAoa(file, { defval: '' })
    expect(withDefval.sheets['表一'][1][1], 'defval 应透传').toBe('')

    const rawFalse = await readWorkbookAoa(file, { raw: false })
    expect(typeof rawFalse.sheets['表二'][1][0], 'raw:false 应透传').toBe('string')
  })

  it('单 sheet 文件也正常工作（不强制多 sheet）', async () => {
    const file = await makeWorkbookFile({ Sheet1: [['A'], ['a1']] })
    const { readWorkbookAoa } = await import('../useExcelIO')

    const got = await readWorkbookAoa(file)

    expect(got.sheetNames).toEqual(['Sheet1'])
    expect(got.sheets['Sheet1']).toEqual([['A'], ['a1']])
  })
})
