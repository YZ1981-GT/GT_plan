/**
 * Property 9 / 10 / 11 / 12 — 替代程序区块「金额语义」守卫（七枢纽）
 *
 * spec: confirmation-orphan-and-amount-format-closure（Requirement 4 / 6）
 *
 * ## 为什么要这条守卫
 *
 * G0 Task 23 浏览器实测发现：替代程序区块的可编辑金额列输 `1234567.5` 显示
 * `1234567.5`（无千分符）。根因是 `CheckBlock.vue` 对 `type:'number'` 一律用
 * `<el-input type="number">` —— HTML number input **天然拒逗号**，千分符结构上
 * 不可能出现。而 `type:'number'` 同时承载金额与非金额（数量 / 投资比例 /
 * 每股股利 / 成交价），一刀切换成 `WpAmountInput` 会把「3 股」显示成 `3.00 元`。
 *
 * 故引入 `render:'amount'` 维度：**两侧都显式声明并互相锁死**
 * （金额列标 `render`，非金额列进 `NON_AMOUNT_NUMBER_COLUMNS` 且带 reason），
 * 而不是按 label 关键字推断 —— 实测 `cap_cost`（原值）关键字抓不到，
 * `成交价` / `每股股利` 会被「价 / 利」误抓。
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {
  NON_AMOUNT_NUMBER_COLUMNS,
  isNonAmountNumberColumn,
} from '../alternativeD05/blockColumnAmountRegistry'

function findRepoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i++) {
    // 哨兵必须是具体文件：`backend/app/routers` 目录在 audit-platform 层也存在（历史空目录）
    if (fs.existsSync(path.join(dir, 'backend', 'app', 'main.py'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error('未能向上定位仓库根（哨兵 backend/app/main.py 缺失）')
}
const REPO_ROOT = findRepoRoot()
const WP = path.join(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper')
const CONFIRM = path.join(WP, 'confirmation')

/** 9 个区块配置文件（七枢纽 8 张替代程序表；D0-5/D0-6 各一份，G0-6 在 g0-confirmation 下） */
const CONFIG_FILES: Record<string, string> = {
  'blockColumnConfigs.ts': path.join(CONFIRM, 'alternativeD05/blockColumnConfigs.ts'),
  'blockColumnConfigsD06.ts': path.join(CONFIRM, 'alternativeD06/blockColumnConfigsD06.ts'),
  'blockColumnConfigsF05.ts': path.join(CONFIRM, 'alternativeF05/blockColumnConfigsF05.ts'),
  'blockColumnConfigsF06.ts': path.join(CONFIRM, 'alternativeF06/blockColumnConfigsF06.ts'),
  'blockColumnConfigsH05.ts': path.join(CONFIRM, 'alternativeH05/blockColumnConfigsH05.ts'),
  'blockColumnConfigsK05.ts': path.join(CONFIRM, 'alternativeK05/blockColumnConfigsK05.ts'),
  'blockColumnConfigsK06.ts': path.join(CONFIRM, 'alternativeK06/blockColumnConfigsK06.ts'),
  'blockColumnConfigsG06.ts': path.join(
    WP,
    'g0-confirmation/alternativeG06/blockColumnConfigsG06.ts',
  ),
}

const CHECK_BLOCK = path.join(CONFIRM, 'alternativeD05/CheckBlock.vue')
const G06_HOST = path.join(WP, 'g0-confirmation/alternativeG06/GtConfirmationAlternativeG06.vue')

/**
 * 剥注释（带字符串状态机）。
 *
 * 🔴 必需：本 spec 的改动说明注释里写着被禁的旧写法字面（如
 * 「原先无条件对全部 number 列调 prefs.fmt」），不剥注释会把说明数成真实代码，
 * 让「不得出现旧写法」的断言恒红或恒绿。
 * 同族坑：`accept="image/*"` 的 `/*` 被当块注释起点会吞掉几千字符
 * （memory 已登记两个真实宿主因此逃出扫描面）→ 故必须带引号状态。
 */
function stripComments(src: string): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (quote) {
      if (c === '\\') {
        out += c + (n ?? '')
        i += 2
        continue
      }
      if (c === quote) quote = null
      out += c
      i++
      continue
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c
      out += c
      i++
      continue
    }
    if (c === '/' && n === '*') {
      const end = src.indexOf('*/', i + 2)
      i = end === -1 ? src.length : end + 2
      out += ' '
      continue
    }
    if (c === '/' && n === '/') {
      const end = src.indexOf('\n', i)
      i = end === -1 ? src.length : end
      out += ' '
      continue
    }
    if (c === '<' && src.startsWith('<!--', i)) {
      const end = src.indexOf('-->', i)
      i = end === -1 ? src.length : end + 3
      out += ' '
      continue
    }
    out += c
    i++
  }
  return out
}

type Col = { file: string; block: string; field: string; hasRender: boolean }

/**
 * 从一个配置文件抽出全部 `type:'number'` 列。
 *
 * 🔴 必须同时扫共享列数组 `VOUCHER_COLS` —— H0-5 / K0-5 / K0-6 / G0-6 把
 * 「记账凭证」5 列抽成它并在四个区块各 spread 一次，它声明在 `BLOCK1_COLUMNS`
 * **之前**。只按 `BLOCKn_COLUMNS` 分区扫会整段漏掉（实测少 4 列：72 vs 76），
 * 而漏掉的列在 UI 上就是「金额不带千分符」，四层验证全绿。
 */
function extractNumberCols(file: string, absPath: string): Col[] {
  const src = stripComments(fs.readFileSync(absPath, 'utf-8'))
  const lines = src.split('\n')
  const out: Col[] = []
  let block: string | null = null
  for (const line of lines) {
    const b = /^const BLOCK([1-4])_COLUMNS:\s*BlockColumnDef\[\]\s*=\s*\[/.exec(line)
    if (b) {
      block = `block${b[1]}`
      continue
    }
    if (/^const VOUCHER_COLS:\s*BlockColumnDef\[\]\s*=\s*\[/.test(line)) {
      block = 'shared'
      continue
    }
    if (block && /^\]/.test(line)) {
      block = null
      continue
    }
    if (!block) continue
    if (!/type:\s*'number'/.test(line)) continue
    const f = /field:\s*'([^']+)'/.exec(line)
    if (!f) continue
    if (f[1] === 'seq') continue // CheckBlock 的 seq 分支早于 number 分支命中 → 标了是死配置
    out.push({ file, block, field: f[1], hasRender: /render:\s*'amount'/.test(line) })
  }
  return out
}

const ALL_COLS: Col[] = Object.entries(CONFIG_FILES).flatMap(([name, abs]) =>
  extractNumberCols(name, abs),
)

const CHECK_BLOCK_SRC = fs.readFileSync(CHECK_BLOCK, 'utf-8')
const CHECK_BLOCK_CODE = stripComments(CHECK_BLOCK_SRC)
const G06_SRC = fs.readFileSync(G06_HOST, 'utf-8')
const G06_CODE = stripComments(G06_SRC)

describe('自检：抽取非空且数量锚定（正则失效必须打红而非空转）', () => {
  it('9 个配置文件全部存在且抽出的 number 列数量锚定', () => {
    for (const [name, abs] of Object.entries(CONFIG_FILES)) {
      expect(fs.existsSync(abs), `缺文件 ${name}`).toBe(true)
    }
    // 实测：76 金额 + 17 非金额 = 93（不含 32 个 seq）
    expect(ALL_COLS.length).toBe(93)
  })

  it('每个配置文件都至少抽出一列（防单文件正则失效被总数掩盖）', () => {
    for (const name of Object.keys(CONFIG_FILES)) {
      const n = ALL_COLS.filter((c) => c.file === name).length
      expect(n, `${name} 抽出 0 列（正则失效？）`).toBeGreaterThan(0)
    }
  })

  it('共享列数组 VOUCHER_COLS 确实被扫到（4 个文件各一处，漏扫即少 4 个金额列）', () => {
    const sharedFiles = new Set(
      ALL_COLS.filter((c) => c.block === 'shared').map((c) => c.file),
    )
    expect([...sharedFiles].sort()).toEqual(
      [
        'blockColumnConfigsG06.ts',
        'blockColumnConfigsH05.ts',
        'blockColumnConfigsK05.ts',
        'blockColumnConfigsK06.ts',
      ].sort(),
    )
  })

  /**
   * spread 解析的**具体锚点**：把「4 个文件用 spread」与「5 个文件声明 voucher_amount」
   * 这两个**不同集合**分开钉死。
   *
   * 🔴 K0-6 不在 voucher_amount 集合里 —— 它的 `VOUCHER_COLS` 只有 1 个 number 列且
   * 字段名是 `amount`。若反向自检把 K0-6 也算进「voucher_amount 必须被看到」会假红。
   * （G0-6 另有一条 `field:'voucher_amount'` 但不带 `type:'number'`，是已停渲染的字段
   * 登记项，本判据基于 ALL_COLS 故天然排除。）
   */
  it('spread 解析锚点：voucher_amount 恰在 5 个文件且全部已标 render（K0-6 例外）', () => {
    const va = ALL_COLS.filter((c) => c.field === 'voucher_amount')
    const byFile: Record<string, number> = {}
    for (const c of va) byFile[c.file] = (byFile[c.file] ?? 0) + 1
    expect(byFile).toEqual({
      'blockColumnConfigsF05.ts': 3, // BLOCK1/2/4 各自内联一次
      'blockColumnConfigsF06.ts': 2, // BLOCK1/BLOCK3
      'blockColumnConfigsH05.ts': 1, // 经 VOUCHER_COLS
      'blockColumnConfigsK05.ts': 1, // 经 VOUCHER_COLS
      'blockColumnConfigsG06.ts': 1, // 经 VOUCHER_COLS
    })
    expect(va.every((c) => c.hasRender), 'voucher_amount 是金额列，必须全部标 render').toBe(true)
    expect(
      va.some((c) => c.file === 'blockColumnConfigsK06.ts'),
      'K0-6 没有 voucher_amount，算进来即假红',
    ).toBe(false)
    // K0-6 的共享列确实被扫到，只是字段名不同 → 证明上一条 false 不是「漏扫」导致的
    expect(
      ALL_COLS.filter((c) => c.file === 'blockColumnConfigsK06.ts' && c.block === 'shared').map(
        (c) => c.field,
      ),
    ).toEqual(['amount'])
  })

  it('反向自检：stripComments 剥掉注释里的字面且不被引号内斜杠骗到', () => {
    expect(stripComments("const a = 1 // render: 'amount'\n")).not.toContain("render: 'amount'")
    expect(stripComments("/* render: 'amount' */ const b = 2")).not.toContain("render: 'amount'")
    // 引号内的 /* 不是注释起点（MIME 通配符同款）
    const mime = `const t = 'image/*'\nconst keep = 3\n`
    expect(stripComments(mime)).toContain('const keep = 3')
  })
})

describe("Property 9: 每个 number 列的金额语义已表态（Validates 4.6, 4.7, 4.8）", () => {
  it('每列要么标 render:amount，要么在非金额登记表内（不许沉默）', () => {
    const untyped = ALL_COLS.filter(
      (c) => !c.hasRender && !isNonAmountNumberColumn(c.file, c.block, c.field),
    ).map((c) => `${c.file}/${c.block}.${c.field}`)
    expect(
      untyped,
      `以下 number 列未表态金额语义。金额列标 render:'amount'，非金额列写进 blockColumnAmountRegistry：\n${untyped.join('\n')}`,
    ).toEqual([])
  })

  it('两侧无交集（标了 render 的不得同时登记为非金额）', () => {
    const both = ALL_COLS.filter(
      (c) => c.hasRender && isNonAmountNumberColumn(c.file, c.block, c.field),
    ).map((c) => `${c.file}/${c.block}.${c.field}`)
    expect(both, `以下列两侧同时声明，语义矛盾：\n${both.join('\n')}`).toEqual([])
  })

  it('两侧数量之和等于总列数（76 金额 + 17 非金额 = 93）', () => {
    const amount = ALL_COLS.filter((c) => c.hasRender).length
    const nonAmount = ALL_COLS.filter((c) =>
      isNonAmountNumberColumn(c.file, c.block, c.field),
    ).length
    expect(amount).toBe(76)
    expect(nonAmount).toBe(17)
    expect(amount + nonAmount).toBe(ALL_COLS.length)
  })

  it('逐文件金额列数与实测一致（防某个枢纽整体漏标被总数掩盖）', () => {
    const byFile: Record<string, number> = {}
    for (const c of ALL_COLS) if (c.hasRender) byFile[c.file] = (byFile[c.file] ?? 0) + 1
    expect(byFile).toEqual({
      'blockColumnConfigs.ts': 7,
      'blockColumnConfigsD06.ts': 7,
      'blockColumnConfigsF05.ts': 11,
      'blockColumnConfigsF06.ts': 12,
      'blockColumnConfigsH05.ts': 6,
      'blockColumnConfigsK05.ts': 6,
      'blockColumnConfigsK06.ts': 7,
      'blockColumnConfigsG06.ts': 20,
    })
  })

  it('非金额登记表恰 17 条，每条 reason ≥8 字且不含占位词', () => {
    expect(NON_AMOUNT_NUMBER_COLUMNS.length).toBe(17)
    for (const e of NON_AMOUNT_NUMBER_COLUMNS) {
      expect(e.reason.replace(/\s/g, '').length, `${e.field} 的 reason 过短`).toBeGreaterThanOrEqual(
        8,
      )
      for (const bad of ['TODO', '待补充', '待定', '暂时']) {
        expect(e.reason.includes(bad), `${e.field} 的 reason 是占位词「${bad}」`).toBe(false)
      }
    }
  })

  it('登记表每条都指向真实存在的列（防登记漂移成噪声）', () => {
    const known = new Set(ALL_COLS.map((c) => `${c.file}|${c.block}|${c.field}`))
    const stale = NON_AMOUNT_NUMBER_COLUMNS.filter(
      (e) => !known.has(`${e.file}|${e.block}|${e.field}`),
    ).map((e) => `${e.file}/${e.block}.${e.field}`)
    expect(stale, `登记表条目在配置里不存在（列已删/改名）：\n${stale.join('\n')}`).toEqual([])
  })

  it('identity 必须是 (file, block, field) 三元组：同名 field 跨区块复现', () => {
    // 实测 transport_qty 在 D06 的 block1/block3 各一次 → 按 field 建索引会静默漏标
    const dup = new Map<string, number>()
    for (const c of ALL_COLS) {
      const k = `${c.file}|${c.field}`
      dup.set(k, (dup.get(k) ?? 0) + 1)
    }
    const multi = [...dup.entries()].filter(([, n]) => n > 1)
    expect(multi.length, '应存在同文件同名 field 跨区块复现的情形（否则本断言空转）').toBeGreaterThan(
      0,
    )
  })

  it('反向自检：对未登记的假列判为「未表态」', () => {
    expect(isNonAmountNumberColumn('blockColumnConfigs.ts', 'block1', '__no_such_field__')).toBe(
      false,
    )
    // 且真登记项确实为 true（防判据恒假）
    const first = NON_AMOUNT_NUMBER_COLUMNS[0]
    expect(isNonAmountNumberColumn(first.file, first.block, first.field)).toBe(true)
  })

  it('反向自检：把某条登记项拿掉后该列会被判为未表态', () => {
    const victim = NON_AMOUNT_NUMBER_COLUMNS[0]
    const shrunk = NON_AMOUNT_NUMBER_COLUMNS.filter((e) => e !== victim)
    const stillCovered = shrunk.some(
      (e) => e.file === victim.file && e.block === victim.block && e.field === victim.field,
    )
    expect(stillCovered, '拿掉后不应再被覆盖（证明判据真读登记表）').toBe(false)
  })
})

describe('Property 10: CheckBlock 按 render 分流三处渲染（Validates 4.1~4.5）', () => {
  it('编辑态：金额列走 WpAmountInput，条件含 render === \'amount\'', () => {
    expect(CHECK_BLOCK_CODE).toContain('<WpAmountInput')
    expect(CHECK_BLOCK_CODE).toMatch(/col\.render === 'amount'/)
    expect(CHECK_BLOCK_CODE).toContain("import WpAmountInput from '../../shared/WpAmountInput.vue'")
  })

  it('编辑态：非金额分支仍是 el-input + type="number"（零回归）', () => {
    expect(CHECK_BLOCK_CODE).toContain('<el-input')
    expect(CHECK_BLOCK_CODE).toContain('type="number"')
  })

  it('只读态与合计行都按 render 分流（同一对格式化函数）', () => {
    expect(CHECK_BLOCK_CODE).toMatch(/formatCell\(row\[col\.field\], col\.render\)/)
    expect(CHECK_BLOCK_CODE).toMatch(/formatCell\(val, getFieldRender\(/)
    expect(CHECK_BLOCK_CODE).toMatch(/function getFieldRender/)
  })

  it('formatCell 内部按 render 判定，金额分支走 prefs.fmt（平台单一真源）', () => {
    const m = /function formatCell\([\s\S]*?\n\}/.exec(CHECK_BLOCK_CODE)
    expect(m, '未截到 formatCell 函数体（正则失效）').toBeTruthy()
    const body = m![0]
    expect(body).toMatch(/render === 'amount'/)
    expect(body).toContain('prefs.fmt(')
  })

  it('🔴 不得 import 模块级 fmtAmount（它是 store 成员，写成命名导入整页崩）', () => {
    expect(CHECK_BLOCK_CODE).not.toMatch(/import\s*\{[^}]*\bfmtAmount\b[^}]*\}\s*from/)
  })

  it('不得出现「无条件对全部 number 列套金额格式」的旧写法', () => {
    // 旧写法特征：type==='number' 直接调 prefs.fmt，中间不经 render 判定
    expect(CHECK_BLOCK_CODE).not.toMatch(/type === 'number'[^\n]*prefs\.fmt/)
  })

  it('反向自检：内联 fixture 复现旧无条件写法时被判红', () => {
    const legacy = `const s = col.type === 'number' ? prefs.fmt(v) : v`
    expect(/type === 'number'[^\n]*prefs\.fmt/.test(legacy)).toBe(true)
  })

  it('反向自检：stripComments 生效（原文注释含旧写法字面，剥后消失）', () => {
    // 本文件与 CheckBlock 的说明注释都会提到 render/WpAmountInput，剥注释后仍应留下代码字面
    expect(CHECK_BLOCK_SRC.length).toBeGreaterThan(CHECK_BLOCK_CODE.length)
  })
})

describe('Property 11: G0-6 余额卡片金额输入已换 WpAmountInput（Validates 4.9, 4.10）', () => {
  const BALANCE_FIELDS = [
    'opening_balance',
    'increase_amount',
    'decrease_amount',
    'closing_balance',
    'investment_income',
    'fv_change',
  ]

  it('宿主已 import 并使用 WpAmountInput', () => {
    expect(G06_CODE).toContain('<WpAmountInput')
    expect(G06_CODE).toMatch(/import WpAmountInput from '.*WpAmountInput\.vue'/)
  })

  it('6 个余额字段各有一个 WpAmountInput，且不再与 type="number" 同现', () => {
    for (const f of BALANCE_FIELDS) {
      // 抓 `<WpAmountInput ... v-model="...f" ... />` 这一段
      const re = new RegExp(`<WpAmountInput[\\s\\S]{0,400}?${f}[\\s\\S]{0,300}?/>`)
      const m = re.exec(G06_CODE)
      expect(m, `${f} 未落在 WpAmountInput 上`).toBeTruthy()
      expect(m![0], `${f} 的输入块仍含 type="number"`).not.toContain('type="number"')
    }
  })

  it('余额字段不再用 v-model.number（WpAmountInput 自己收敛为 number）', () => {
    for (const f of BALANCE_FIELDS) {
      expect(
        new RegExp(`v-model\\.number="[^"]*${f}`).test(G06_CODE),
        `${f} 仍用 v-model.number`,
      ).toBe(false)
    }
  })

  it('只传 WpAmountInput 的合法 prop（传不存在的 prop = 静默失效）', () => {
    const legal = new Set(['model-value', 'modelValue', 'disabled', 'size', 'placeholder', 'aria-label', 'ariaLabel'])
    for (const m of G06_CODE.matchAll(/<WpAmountInput([\s\S]*?)\/>/g)) {
      for (const a of m[1].matchAll(/(?:^|\s)(?::)?([a-zA-Z][\w-]*)=/g)) {
        const name = a[1]
        if (['v-model', 'key', 'ref', 'class', 'style'].includes(name)) continue
        if (name.startsWith('v-') || name.startsWith('@')) continue
        expect(legal.has(name), `WpAmountInput 收到非法 prop「${name}」`).toBe(true)
      }
    }
  })

  it('反向自检：内联 fixture 复现旧 el-input type=number 写法时被判红', () => {
    const legacy = `<el-input v-model.number="b.opening_balance" type="number" />`
    expect(/v-model\.number="[^"]*opening_balance/.test(legacy)).toBe(true)
    expect(legacy).toContain('type="number"')
  })
})

describe('Property 12: 七枢纽零回归（Validates 6.1, 6.2, 6.3）', () => {
  it('render 是**可选**字段（缺省不改变行为，加法式改动）', () => {
    // 🔴 BlockColumnDef 声明在 `blockColumnConfigs.ts`（不是 alternativeD05Types.ts）——
    //    首版守卫查错文件直接打红，正是「读源码型守卫必须先定位真源」的实例。
    const decl = stripComments(
      fs.readFileSync(path.join(CONFIRM, 'alternativeD05/blockColumnConfigs.ts'), 'utf-8'),
    )
    const iface = /export interface BlockColumnDef\s*\{([\s\S]*?)\n\}/.exec(decl)
    expect(iface, '未截到 BlockColumnDef 接口体（正则失效即报错，不空转）').toBeTruthy()
    expect(iface![1], "BlockColumnDef 应声明可选 render?: 'amount'").toMatch(
      /render\?:\s*'amount'/,
    )
    // 必须是**可选**（带 `?`）：非可选会让 125 个 number 列全部编译期报错 = 破坏加法式前提
    expect(iface![1]).not.toMatch(/\brender:\s*'amount'/)
  })

  it('非金额列在 CheckBlock 走的仍是 el-input 分支（属性集合含 type/size/@change）', () => {
    const m = /<el-input[\s\S]{0,600}?type="number"[\s\S]{0,600}?\/>/.exec(CHECK_BLOCK_CODE)
    expect(m, '未截到非金额 number 输入块').toBeTruthy()
    expect(m![0]).toContain('type="number"')
  })

  /**
   * 🔴 R6.3「未标 render 的列与改动前逐字节等价」的硬锚点。
   *
   * 基线由 `git show HEAD:...CheckBlock.vue` 在改造时（2026-08-05，本 spec Wave 3 之前
   * 的 HEAD）真实抽取：非金额 number 输入块的属性名集合。
   * **不在测试里现跑 git show** —— 一旦本 spec 提交，HEAD 就变成新版本，
   * 「新 vs 新」恒等 → 守卫永久空转。故写成捕获基线 + 提供出处。
   *
   * 唯一允许的差异是条件指令由 `v-if` 变 `v-else-if`（金额分支接过了 `v-if`），
   * 故比对时排除条件指令本身。
   */
  const LEGACY_NUMBER_INPUT_ATTRS = [
    ':placeholder',
    '@change',
    'size',
    'type',
    'v-model.number',
  ] as const

  it('R6.3：非金额 number 输入块的属性集合与改造前 HEAD 逐字相同（仅条件指令由 v-if→v-else-if）', () => {
    const m = /<el-input\b[\s\S]{0,800}?type="number"[\s\S]{0,800}?\/>/.exec(CHECK_BLOCK_CODE)
    expect(m, '未截到非金额 number 输入块（正则失效即打红）').toBeTruthy()
    const seg = m![0]
    const attrs = [...new Set([...seg.matchAll(/(?:^|\s)(:?@?[a-zA-Z][\w.\-]*)=/g)].map((a) => a[1]))]
    const cond = attrs.filter((a) => a === 'v-if' || a === 'v-else-if')
    expect(cond.length, '非金额分支必须带条件指令（否则两分支会同时渲染）').toBe(1)
    expect(
      attrs.filter((a) => a !== 'v-if' && a !== 'v-else-if').sort(),
      '非金额列的输入控件属性集合相对改造前发生了变化 → 破坏 R6.3 零回归',
    ).toEqual([...LEGACY_NUMBER_INPUT_ATTRS].sort())
  })

  /**
   * R6.2「六枢纽导航项与改造前逐字节相等」的**唯一**基线是
   * `coordination/__tests__/crossWorkpaperNav.spec.ts` 的 `SIX_HUB_BASELINE`
   * （改造前真实跑 `buildCrossWorkpaperNavDefs()` 采集）。
   *
   * 本文件**只复核它存在且唯一**，绝不抄第二份 —— 两份基线打架时无法裁决谁是真值。
   */
  it('R6.2：六枢纽导航基线守卫存在，且 SIX_HUB_BASELINE 只有一份', () => {
    const baselineGuard = path.join(
      CONFIRM,
      'coordination/__tests__/crossWorkpaperNav.spec.ts',
    )
    expect(fs.existsSync(baselineGuard), '六枢纽零回归基线守卫缺失').toBe(true)
    const src = fs.readFileSync(baselineGuard, 'utf-8')
    expect(src).toContain('SIX_HUB_BASELINE')
    expect(src).toContain('buildCrossWorkpaperNavDefs')
    for (const cycle of ['D0', 'E0', 'F0', 'H0', 'K0', 'L0']) {
      expect(src, `基线缺少 ${cycle}`).toMatch(new RegExp(`\\b${cycle}:\\s*\\[`))
    }

    // 唯一性：全部前端测试文件里只有它声明该基线
    const owners: string[] = []
    const walk = (dir: string) => {
      for (const name of fs.readdirSync(dir)) {
        const full = path.join(dir, name)
        const st = fs.statSync(full)
        if (st.isDirectory()) {
          if (name === 'node_modules' || name === 'dist') continue
          walk(full)
        } else if (/\.(ts|vue)$/.test(name)) {
          if (/SIX_HUB_BASELINE/.test(fs.readFileSync(full, 'utf-8'))) {
            owners.push(full.replace(/\\/g, '/').split('/src/')[1])
          }
        }
      }
    }
    walk(path.join(REPO_ROOT, 'audit-platform/frontend/src'))

    // 🔴 本文件自己也提到该符号（就在这条断言里）→ 必须自排除。
    //    但先断言「原始扫描确实看见了本文件」，否则 walk 失效时自排除会掩盖空转。
    const SELF = 'components/workpaper/confirmation/__tests__/blockColumnAmountRender.spec.ts'
    expect(owners, '扫描面没覆盖到本文件 → walk 失效').toContain(SELF)
    expect(
      owners.filter((p) => p !== SELF),
      `SIX_HUB_BASELINE 出现在多处，基线打架时无法裁决：\n${owners.join('\n')}`,
    ).toEqual(['components/workpaper/confirmation/coordination/__tests__/crossWorkpaperNav.spec.ts'])
  })

  it('每个枢纽都至少有一个金额列被标注（无枢纽整体漏改）', () => {
    for (const name of Object.keys(CONFIG_FILES)) {
      const n = ALL_COLS.filter((c) => c.file === name && c.hasRender).length
      expect(n, `${name} 一个金额列都没标（整体漏改？）`).toBeGreaterThan(0)
    }
  })

  it('seq 列一律不标 render（CheckBlock 的 seq 分支早于 number 分支命中）', () => {
    for (const [name, abs] of Object.entries(CONFIG_FILES)) {
      const src = stripComments(fs.readFileSync(abs, 'utf-8'))
      for (const line of src.split('\n')) {
        if (!/field:\s*'seq'/.test(line)) continue
        expect(/render:\s*'amount'/.test(line), `${name} 的 seq 列被标了 render（死配置）`).toBe(
          false,
        )
      }
    }
  })
})
