/**
 * useExcelIO 安全加固守卫 —— Wave 2 Task 8（判据先行于 Task 3 建立）
 * spec: frontend-excel-io-single-entry-convergence
 *   (Requirements 4.1 / 4.2 / 4.3 / 4.4 / 4.5 · Property 20 / 21 / 22 / 23 / 24)
 *
 * ## 🔴 判据推理：为什么不能断言「Object.prototype 被污染」
 *
 * 直觉写法是「构造列头为 `__proto__` 的 xlsx，断言解析后 `({}).polluted !== undefined`」。
 * **这个断言会永远绿，是个假守卫。** 推理如下：
 *
 * `parseFile` 对象模式的写入点是 `rowObj[header] = val`，而 xlsx 单元格值只能是
 * string / number / boolean / Date 这些**标量**。JS 语义下：
 *
 * - 普通对象上 `o.__proto__ = 'abc'` —— 原型必须是 object 或 null，赋标量**静默无效**，
 *   既不污染原型也不创建自有属性；
 * - `o.constructor = 'abc'` —— 只在该对象上创建自有属性，**不触及 Object.prototype**。
 *
 * 所以走标量值这条路根本到不了「污染全局原型」。若照直觉写，守卫在有防护和无防护
 * 两种情况下都绿 ⇒ 撤掉 `_BLOCKED_KEYS` 也发现不了（memory：守卫把错值当基线锁死、
 * grep 式守卫只查字符串存在，都是假绿三源）。
 *
 * ## 真正的风险点与真正的判据
 *
 * 风险不在「本次赋值污染原型」，而在**危险键进入数据流后被下游放大**：
 * 行对象会被 `Object.assign` / 深合并 / `JSON.parse(JSON.stringify())` / 后端序列化
 * 层层传递，其中任一环节把自有的 `__proto__` 键当普通键合并，污染就发生在那里。
 *
 * 而本实现用 `Object.create(null)` 建行对象 —— **这恰恰让 `bare['__proto__'] = 'abc'`
 * 创建出真正的自有属性**（无原型对象上 `__proto__` 不是访问器），展开成普通对象后
 * 就带着一个自有 `__proto__` 键流向下游。故 `Object.create(null)` 单独用**反而放大风险**，
 * 必须与 `_BLOCKED_KEYS` 过滤配对。
 *
 * ⇒ 判据落在三处可被变异打红的事实上：
 *   1. 危险列头不出现在 `headers` 与行对象的自有键里；
 *   2. `blockedKeys` 如实回报被拦下的键（可观测性，否则静默丢列）；
 *   3. 行对象没有自有 `__proto__` 属性（撤掉过滤后这条必红）。
 *
 * 兜底断言「Object.prototype 未获得新属性」仍保留，但它是**辅助**而非主判据。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import * as XLSX from 'xlsx'

import { parseFile } from '../useExcelIO'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

// ═══════════════════════════════════════════════════════════════════════════
// 工具：构造真实 xlsx File（真实执行判据，不 mock 解析层）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 构造真实 xlsx 的 File。
 *
 * ⚠ jsdom 的 `File`/`Blob` 实现不含 `arrayBuffer()`（浏览器有、jsdom 没有），而
 * `parseFile` 的第一步就是 `await file.arrayBuffer()` ⇒ 不打 polyfill 全部用例都会
 * 以 `TypeError: file.arrayBuffer is not a function` 失败。这是**环境缺失**，
 * 不是生产代码缺陷，故在此补齐而非改生产代码去迁就测试环境。
 *
 * 注：本文件是 `parseFile` 的首个测试覆盖 —— 既有 `useExcelIO.spec.ts` 的 21 例
 * 全部只测导出侧，读侧（也正是 CVE 攻击面所在）此前零覆盖。
 */
function makeXlsxFile(aoa: any[][], sheetName = '数据填写'): File {
  const wb = XLSX.utils.book_new()
  const ws = XLSX.utils.aoa_to_sheet(aoa)
  XLSX.utils.book_append_sheet(wb, ws, sheetName)
  const bytes = XLSX.write(wb, { type: 'array', bookType: 'xlsx' }) as ArrayBuffer

  const file = new File([bytes], 'probe.xlsx', {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })

  if (typeof (file as any).arrayBuffer !== 'function') {
    Object.defineProperty(file, 'arrayBuffer', {
      value: async () => bytes,
      configurable: true,
    })
  }

  return file
}

const DANGEROUS_KEYS = ['__proto__', 'constructor', 'prototype'] as const

describe('useExcelIO 安全加固 · 原型污染防护', () => {
  let protoSnapshot: string[]

  beforeEach(() => {
    protoSnapshot = Object.getOwnPropertyNames(Object.prototype).sort()
  })

  afterEach(() => {
    // 兜底：确保任何一例都没给全局原型加东西（哪怕主判据没覆盖到）
    const after = Object.getOwnPropertyNames(Object.prototype).sort()
    expect(after, 'Object.prototype 在本例执行后多出了属性 —— 存在真实原型污染').toEqual(protoSnapshot)
  })

  it('危险列头不进 headers（Property 20）', async () => {
    const file = makeXlsxFile([
      ['__proto__', 'constructor', 'prototype', '正常列'],
      ['v1', 'v2', 'v3', 'ok'],
    ])

    const res = await parseFile(file)

    for (const k of DANGEROUS_KEYS) {
      expect(res.headers, `危险列头 ${k} 出现在 headers 里 —— 它会被当作行对象的键使用`).not.toContain(k)
    }
    expect(res.headers, '正常列应保留').toContain('正常列')
  })

  it('危险列头不进行对象的自有键（Property 20，这是撤掉过滤后必红的主判据）', async () => {
    const file = makeXlsxFile([
      ['__proto__', 'constructor', 'prototype', '正常列'],
      ['v1', 'v2', 'v3', 'ok'],
    ])

    const res = await parseFile(file)
    expect(res.rows.length, '应解析出 1 行').toBe(1)

    const own = Object.getOwnPropertyNames(res.rows[0])
    for (const k of DANGEROUS_KEYS) {
      expect(
        own,
        `行对象带上了自有属性 ${k}。实现用 Object.create(null) 建对象，` +
          `无原型对象上 ${k} 会成为真正的自有属性，展开后随数据流向下游，` +
          '被 Object.assign / 深合并 / 反序列化任一环节放大即造成污染。',
      ).not.toContain(k)
    }
    expect(res.rows[0]['正常列'], '正常列的值应正常解析').toBe('ok')
  })

  it('blockedKeys 如实回报被拦下的键（可观测性，防静默丢列）', async () => {
    const file = makeXlsxFile([
      ['__proto__', 'A', 'constructor'],
      ['v1', 'a1', 'v3'],
    ])

    const res = await parseFile(file)

    expect(res.blockedKeys, 'blockedKeys 未回报 __proto__ —— 调用方无从得知有列被丢弃').toContain('__proto__')
    expect(res.blockedKeys, 'blockedKeys 未回报 constructor').toContain('constructor')
    expect(res.blockedKeys, '未出现的危险键不该被回报').not.toContain('prototype')
  })

  it('行对象的原型仍是 Object.prototype（Object.create(null) 已转回普通对象）', async () => {
    const file = makeXlsxFile([
      ['A', 'B'],
      ['a1', 'b1'],
    ])

    const res = await parseFile(file)

    // 若忘了 { ...bare } 转回，调用方的 Object.keys / JSON.stringify / hasOwnProperty
    // 行为都会变，属静默回归。
    expect(
      Object.getPrototypeOf(res.rows[0]),
      '行对象是无原型对象 —— 调用方调 hasOwnProperty / toString 会抛错',
    ).toBe(Object.prototype)
  })

  it('rawArrayMode 的键是数字下标，不受列头控制（Property 24 的边界说明）', async () => {
    const file = makeXlsxFile([
      ['__proto__', 'B'],
      ['v1', 'b1'],
    ])

    const res = await parseFile(file, { rawArrayMode: true })

    expect(res.rows.length).toBe(1)
    const own = Object.getOwnPropertyNames(res.rows[0])
    expect(own, 'rawArrayMode 的键应为数字下标字符串').toEqual(['0', '1'])
    expect(res.rows[0]['0']).toBe('v1')
  })
})

describe('useExcelIO 安全加固 · 行数上限', () => {
  it('超过 maxRows 时截断且回报被丢弃条数（Property 22）', async () => {
    const aoa: any[][] = [['A']]
    for (let i = 0; i < 25; i += 1) aoa.push([`r${i}`])

    const file = makeXlsxFile(aoa)
    const res = await parseFile(file, { maxRows: 10 })

    expect(res.rows.length, '应截断到 maxRows').toBe(10)
    expect(res.truncatedRows, '被丢弃 15 行应如实回报，而非静默丢失').toBe(15)
  })

  it('未超限时 truncatedRows 为 0 且不截断', async () => {
    const aoa: any[][] = [['A'], ['r0'], ['r1'], ['r2']]
    const file = makeXlsxFile(aoa)
    const res = await parseFile(file, { maxRows: 10 })

    expect(res.rows.length).toBe(3)
    expect(res.truncatedRows).toBe(0)
  })

  it('超限时不抛错（大文件不能让页面崩，Property 22）', async () => {
    const aoa: any[][] = [['A']]
    for (let i = 0; i < 60; i += 1) aoa.push([`r${i}`])
    const file = makeXlsxFile(aoa)

    await expect(parseFile(file, { maxRows: 5 })).resolves.toBeDefined()
  })
})

describe('useExcelIO 安全加固 · 合法输入零回归（Property 23 / R4.4）', () => {
  it('无危险列头时 headers 与 rows 与加固前语义一致', async () => {
    const file = makeXlsxFile([
      ['编号', '名称', '金额'],
      ['E0-6-1', '产品甲', 1000],
      ['E0-6-2', '产品乙', 2000],
    ])

    const res = await parseFile(file)

    expect(res.headers).toEqual(['编号', '名称', '金额'])
    expect(res.rows).toEqual([
      { 编号: 'E0-6-1', 名称: '产品甲', 金额: 1000 },
      { 编号: 'E0-6-2', 名称: '产品乙', 金额: 2000 },
    ])
    expect(res.blockedKeys, '无危险列头时不该有拦截记录').toEqual([])
    expect(res.truncatedRows).toBe(0)
  })

  it('🔴 表头中间有空列时后续列不错位（既有缺陷的修正，防回退）', async () => {
    // 改造前用 `headers.filter(h => h !== '')` 的下标去取 rawRow[colIdx]，
    // 空列头会让其右侧所有列取到左移一位的值。
    const file = makeXlsxFile([
      ['编号', '', '名称'],
      ['E-1', 'IGNORED', '产品甲'],
    ])

    const res = await parseFile(file)

    expect(res.headers, '空列头应被剔除').toEqual(['编号', '名称'])
    expect(res.rows[0].编号).toBe('E-1')
    expect(
      res.rows[0].名称,
      '名称取到了空列的值 —— 说明用了过滤后的下标而非原始列索引，整行右侧全部错位',
    ).toBe('产品甲')
  })

  it('🔴 危险列头位于中间时后续列不错位（同一缺陷的危险键变体）', async () => {
    const file = makeXlsxFile([
      ['编号', '__proto__', '名称'],
      ['E-2', 'IGNORED', '产品乙'],
    ])

    const res = await parseFile(file)

    expect(res.headers).toEqual(['编号', '名称'])
    expect(res.rows[0].名称, '危险列被剔除后，其右侧列必须仍取自己的原始列').toBe('产品乙')
    expect(res.blockedKeys).toContain('__proto__')
  })

  it('空值仍归一为 null（既有语义）', async () => {
    const file = makeXlsxFile([
      ['A', 'B'],
      ['a1', ''],
    ])

    const res = await parseFile(file)
    expect(res.rows[0].B, '空串应归一为 null').toBeNull()
  })

  it('新增字段均为可选，既有 { rows, headers } 解构不受影响', async () => {
    const file = makeXlsxFile([
      ['A'],
      ['a1'],
    ])

    const { rows, headers } = await parseFile(file)
    expect(rows.length).toBe(1)
    expect(headers).toEqual(['A'])
  })
})

/**
 * 防护在单点（Property 24 / R4.5）
 *
 * 🔴 改造前这条是**假绿守卫**（2026-08-14 复盘查出）：它名为「调用方不各自防护」，
 * 实际只对**入口自己**的源码做 `toContain('_BLOCKED_KEYS' / '__proto__' / ...)`，
 * **从不读任何调用方** —— 四条断言恒真，撤掉全部防护也不会红，从未参与过打红
 * （M1 命中的是另外三条行为断言）。这违反本 spec 自己的 R5.3「禁止 grep 式守卫」。
 *
 * 真判据是两条**可被变异打红**的事实：
 *   1. 危险键的**拦截行为**发生在入口（撤掉过滤即红 —— 已由本文件前面的三条行为
 *      断言覆盖，M1 已验证）
 *   2. **调用方没有各自重复实现防护**（Property 24 的实际含义）—— 扫全部生产文件，
 *      不得出现自建的危险键黑名单
 */
describe('useExcelIO 安全加固 · 防护在单点（Property 24 / R4.5）', () => {
  it('🔴 调用方不各自实现危险键黑名单（防护只写一处，扫全部生产文件）', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')

    let dir = __dirname
    let root = ''
    for (let i = 0; i < 12; i += 1) {
      if (fs.existsSync(path.join(dir, 'audit-platform', 'frontend', 'package.json'))) {
        root = dir
        break
      }
      dir = path.dirname(dir)
    }
    expect(root, '未找到仓库根').not.toBe('')

    const SRC = path.join(root, 'audit-platform', 'frontend', 'src')
    const ENTRY_REL = 'composables/useExcelIO.ts'

    /** 自建危险键黑名单的特征：把三个危险键放进 Set/数组字面量或连续 includes 判断 */
    const SELF_GUARD_PATTERNS = [
      /new Set\(\[[^\]]*['"]__proto__['"][^\]]*\]\)/,
      /\[[^\]]*['"]__proto__['"][^\]]*['"]constructor['"][^\]]*\]/,
      /['"]__proto__['"]\s*,\s*['"]constructor['"]\s*,\s*['"]prototype['"]/,
    ]

    function walk(d: string, out: string[] = []): string[] {
      for (const e of fs.readdirSync(d, { withFileTypes: true })) {
        const p = path.join(d, e.name)
        if (e.isDirectory()) {
          if (e.name === 'node_modules' || e.name === '__tests__' || e.name === 'stories') continue
          walk(p, out)
        } else if (/\.(vue|ts)$/.test(e.name) && !/\.(spec|test)\.ts$/.test(e.name)) {
          out.push(p)
        }
      }
      return out
    }

    const files = walk(SRC)
    expect(files.length, '扫描到 0 个文件 —— 本守卫没在验真东西').toBeGreaterThan(1000)

    const offenders: string[] = []
    for (const f of files) {
      const rel = path.relative(SRC, f).replace(/\\/g, '/')
      if (rel === ENTRY_REL) continue // 入口本身就该有
      const src = fs.readFileSync(f, 'utf-8')
      if (SELF_GUARD_PATTERNS.some((re) => re.test(src))) offenders.push(rel)
    }

    expect(
      offenders,
      '以下文件自建了危险键黑名单 —— 防护应只在 useExcelIO 一处（否则漏一处就是一个攻击面，' +
        '且改一次要改 N 处）：\n  ' + offenders.join('\n  '),
    ).toEqual([])
  })

  it('入口确实拦截三个危险键（行为判据，非源码 grep）', async () => {
    // 与本文件前面的行为断言互补：这里只确认「三个键都在拦截名单里生效」，
    // 判据是**解析结果**而非源码字样 —— 故撤掉任一键的过滤都会红。
    const XLSX: any = await import('xlsx')
    const wb = XLSX.utils.book_new()
    const ws = XLSX.utils.aoa_to_sheet([
      ['__proto__', 'constructor', 'prototype', '正常列'],
      ['v1', 'v2', 'v3', 'ok'],
    ])
    XLSX.utils.book_append_sheet(wb, ws, '数据填写')
    const bytes = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
    const file = new File([bytes], 'k.xlsx')
    Object.defineProperty(file, 'arrayBuffer', { value: async () => bytes, configurable: true })

    const { parseFile } = await import('../useExcelIO')
    const res = await parseFile(file, { sheetName: '数据填写' })

    for (const key of ['__proto__', 'constructor', 'prototype']) {
      expect(res.headers, `危险键「${key}」不该进 headers`).not.toContain(key)
      expect(res.blockedKeys, `危险键「${key}」应被如实回报`).toContain(key)
    }
    expect(res.rows[0]['正常列'], '正常列不受影响').toBe('ok')
  })
})
