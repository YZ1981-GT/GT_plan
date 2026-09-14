/**
 * 裁剪金额来源优先级守卫（报表行优先 / 科目名兜底 / 两处同源）。
 *
 * Feature: procedure-trim-report-line-account-resolution — Task 3（Wave 1 打红）
 * Requirements: 5.1, 5.2, 6.2, 6.3, 7.1
 * Validates: Property 14（报表行优先、科目名兜底、差异留痕）,
 *            Property 17（裁剪页与复核视图金额同源）,
 *            Property 18（兜底来源在界面上显式可辨）,
 *            Property 5（部分：与后端 normalize_wp_code 交叉锁死）
 *
 * ═══ 断言分两类 ═══
 *
 * - **类 A = 独立口径判据**：`resolveAccountName` 的当前实现冻结（函数体 md5 + 行为
 *   快照）、`subjectPrefixOf` 的归一正则字面量、改造前"取金额有两处各算一份"的现状
 *   事实、`stripComments` 反向自检。**现在就应全绿**。
 * - **类 B = 被测实现**：`trimAmountSource.resolveAccountAmount` 的存在与行为、
 *   宿主两处改读同一函数。**Task 10 / 12 之前应全红**。
 *
 * ═══ 一处对 design 的偏离（有意，理由如下）═══
 *
 * design 写「组件 5：`ProcedureTrimming.vue` 新增 `resolveAccountAmount()`」。落地改为
 * **独立纯函数模块** `composables/trimAmountSource.ts`，SFC import 使用。理由：
 *
 * 1. R6.2 要求「裁剪页与复核视图相同输入下逐项相等」—— 定义在 `<script setup>` 内部的
 *    函数无法被 vitest import，只能做源码级断言（"两处都写了这个函数名"），而那**证明
 *    不了两处结果相等**。抽成纯函数后可直接喂同一入参断言逐项相等。
 * 2. 与平台既有范式一致：判据/派生逻辑一律落纯函数模块
 *    （`procedureTrimDecision.ts` / `trimAdequacyReview.ts` / `trimAggregateGate.ts`），
 *    SFC 只做映射与渲染。
 *
 * ═══ 改造前的现状（类 A 冻结，改造后必须收敛）═══
 *
 * 取金额的地方**有两处、各算一份**：
 *
 * - `buildAndDecide`（`ProcedureTrimming.vue` ~1435）：`resolveAccountName` +
 *   `ctx.accounts[name].amount`
 * - `toReviewRow`（~2915）：`covered` 门控 + 同样的 `resolveAccountName` + 自己再取一次
 *
 * 两处目前口径相同故未产生分叉，但它们是**两份实现** —— 本 spec 给报表行来源加优先级时
 * 若只改一处，复核视图就会显示旧口径金额，而复核者无从知道该信哪个。故 Task 10/12 要求
 * 两处都收口到 `resolveAccountAmount`。
 *
 * 🔴 读 `.vue` / `.ts` 源码前必 `stripComments()`，并配反向自检「raw 命中 > clean 命中」
 *    —— 否则判据会被注释里的说明文字骗（本平台已反复出现）。
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'
import * as crypto from 'node:crypto'

// ═══════════════════════════════════════════════════════════════════════════
// 路径与源码读取
// ═══════════════════════════════════════════════════════════════════════════
function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 10; i += 1) {
    if (fs.existsSync(path.join(dir, '.kiro'))) return dir
    dir = path.dirname(dir)
  }
  throw new Error('未定位到仓库根（.kiro 不存在）')
}

const ROOT = repoRoot()
const FE = path.join(ROOT, 'audit-platform', 'frontend', 'src')
const P_TRIM_VUE = path.join(FE, 'views', 'ProcedureTrimming.vue')
const P_AMOUNT_TS = path.join(FE, 'components', 'workpaper', 'composables', 'trimAmountSource.ts')
const P_BACKEND_INDEX = path.join(
  ROOT, 'backend', 'app', 'services', 'four_table', 'report_line_index.py',
)

const NOT_IMPLEMENTED = '尚未实现（Task 10 / 12）。本条红是预期的 Wave 1 打红结果'

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/**
 * 带字符串状态的注释剥离（`accept="image/*"` 里的 `/*` 不能当块注释起点）。
 * 同时剥 SFC 模板的 `<!-- -->`。与既有裁剪守卫同款实现。
 */
function stripComments(src: string, hash = false): string {
  let out = ''
  let i = 0
  let quote: string | null = null
  while (i < src.length) {
    const c = src[i]
    const n = src[i + 1]
    if (quote) {
      out += c
      if (c === '\\') { out += n ?? ''; i += 2; continue }
      if (c === quote) quote = null
      i += 1
      continue
    }
    if (c === '"' || c === "'" || c === '`') { quote = c; out += c; i += 1; continue }
    if (!hash && c === '/' && n === '/') { while (i < src.length && src[i] !== '\n') i += 1; continue }
    if (!hash && c === '/' && n === '*') {
      i += 2
      while (i < src.length && !(src[i] === '*' && src[i + 1] === '/')) i += 1
      i += 2
      continue
    }
    if (hash && c === '#') { while (i < src.length && src[i] !== '\n') i += 1; continue }
    if (c === '<' && src.startsWith('<!--', i)) {
      const end = src.indexOf('-->', i)
      i = end < 0 ? src.length : end + 3
      continue
    }
    out += c
    i += 1
  }
  return out
}

/**
 * 截取具名函数的**函数体**（花括号配对 + 语句特征筛选）。
 *
 * 🔴 不能用「声明后第一个 `{`」—— 那个 `{` 可能是参数列表里的解构/内联对象类型
 * 或内联返回类型注解，截出来的"函数体"是那段类型，断言全在无关文本上求值。
 */
function fnBody(src: string, decl: RegExp): string {
  const m = src.match(decl)
  if (!m || m.index === undefined) return ''
  let from = m.index + m[0].length
  for (let guard = 0; guard < 12; guard += 1) {
    const open = src.indexOf('{', from)
    if (open < 0) return ''
    let depth = 0
    let end = -1
    for (let i = open; i < src.length; i += 1) {
      if (src[i] === '{') depth += 1
      else if (src[i] === '}') {
        depth -= 1
        if (depth === 0) { end = i; break }
      }
    }
    if (end < 0) return ''
    const block = src.slice(open, end + 1)
    if (/\b(return|const|let|await|if|for|throw)\b/.test(block)) return block
    from = end + 1
  }
  return ''
}

function sfcScript(clean: string): string {
  const scStart = clean.indexOf('<script setup')
  const scEnd = clean.indexOf('</script>', scStart)
  expect(scStart, '未找到 <script setup').toBeGreaterThan(0)
  return clean.slice(scStart, scEnd)
}

function sfcTemplate(clean: string): string {
  const tplStart = clean.indexOf('<template>')
  const scStart = clean.indexOf('<script setup')
  // 🔴 取 <script setup 之前的**最后一个** </template> —— 大 SFC 里有几十个嵌套
  //    <template #default> 插槽，按第一个闭合标签切只能拿到一小截，判据会空转恒绿。
  const tplEnd = clean.lastIndexOf('</template>', scStart)
  expect(tplEnd, '未找到 </template>').toBeGreaterThan(tplStart)
  return clean.slice(tplStart, tplEnd)
}

function md5(text: string): string {
  return crypto.createHash('md5').update(text.replace(/\s+/g, ' ').trim()).digest('hex')
}

function countOf(hay: string, needle: string): number {
  return hay.split(needle).length - 1
}

const RAW = read(P_TRIM_VUE)
const CLEAN = stripComments(RAW)
const SCRIPT = sfcScript(CLEAN)
const TEMPLATE = sfcTemplate(CLEAN)

const FN_RESOLVE_NAME = fnBody(SCRIPT, /function resolveAccountName\b/)
const FN_SUBJECT_PREFIX = fnBody(SCRIPT, /function subjectPrefixOf\b/)
const FN_BUILD_DECIDE = fnBody(SCRIPT, /function buildAndDecide\b/)
const FN_TO_REVIEW_ROW = fnBody(SCRIPT, /function toReviewRow\b/)

// ═══════════════════════════════════════════════════════════════════════════
// 类 A-0：stripComments 反向自检（现在应绿）
// ═══════════════════════════════════════════════════════════════════════════
describe('类 A：判据基础设施自检', () => {
  it('stripComments 剥 JS/HTML 注释，保留字符串字面量', () => {
    const s = `
// 注释里提到 resolveAccountAmount 与 report_line
/* 块注释也提到 amountSource */
<!-- 模板注释提到 divergence -->
const KEY = 'report_line'
const accept = "image/*"
`
    const out = stripComments(s)
    expect(out, '行注释未剥').not.toContain('注释里提到')
    expect(out, '块注释未剥').not.toContain('块注释也提到')
    expect(out, '模板注释未剥').not.toContain('模板注释提到')
    expect(out, '字符串字面量被误剥').toContain("'report_line'")
    expect(out, 'accept="image/*" 被当块注释起点').toContain('"image/*"')
  })

  it('stripComments 反向自检：raw 命中数 > clean 命中数', () => {
    // 本页注释里大量提到 resolveAccountAmount / report_line（设计留痕），
    // 若两侧命中数相同，说明剥离失效，后续"代码里出现 X"类判据全部空转。
    const rawHits = countOf(RAW, 'resolveAccountName')
    const cleanHits = countOf(CLEAN, 'resolveAccountName')
    expect(rawHits, 'RAW 未命中 resolveAccountName —— 锚点已漂移').toBeGreaterThan(0)
    expect(
      rawHits,
      'raw 与 clean 命中数相同 ⇒ 注释未被剥离，源码级判据是空转',
    ).toBeGreaterThan(cleanHits)
  })

  it('fnBody 能截到四个宿主函数体（锚点未漂移）', () => {
    expect(FN_RESOLVE_NAME, 'resolveAccountName 函数体截取失败').toContain('procName')
    expect(FN_SUBJECT_PREFIX, 'subjectPrefixOf 函数体截取失败').toContain('match')
    expect(FN_BUILD_DECIDE, 'buildAndDecide 函数体截取失败').toContain('decideTrim')
    expect(FN_TO_REVIEW_ROW, 'toReviewRow 函数体截取失败').toContain('wpCode')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 A-1：resolveAccountName 冻结（Task 10 之后必须逐字不变）
// ═══════════════════════════════════════════════════════════════════════════
/**
 * 🔴 `resolveAccountName` 的函数体 md5（空白归一后）。
 *
 * 本 spec 明确**不改**它：报表行映射一旦生效它就退居兜底，且它仍是复核视图与委派目标
 * 定位科目名的唯一实现。改它会同时波及三个消费方（决策入参 / 复核视图 / 委派风险匹配）。
 *
 * 本条打红的两种情形：
 * - Task 10 顺手"优化"了它 ⇒ 违反 R5.1 的「现有科目名匹配保留为兜底」，撤回改动
 * - 别的 spec 有意改它 ⇒ 更新此常量并在 commit 说明里写清为什么
 */
const RESOLVE_ACCOUNT_NAME_MD5 = md5(FN_RESOLVE_NAME)

describe('类 A：resolveAccountName 冻结基线', () => {
  it('函数体非空且含最长匹配优先的排序逻辑', () => {
    expect(FN_RESOLVE_NAME.length, '函数体为空 —— 锚点漂移或函数被删').toBeGreaterThan(80)
    expect(FN_RESOLVE_NAME, '最长匹配优先的排序被移除').toContain('sort')
    expect(FN_RESOLVE_NAME, 'b.length - a.length 降序排序被改').toContain('b.length - a.length')
    expect(FN_RESOLVE_NAME, 'procName.includes(n) 方向匹配被改').toContain('procName.includes(n)')
    expect(FN_RESOLVE_NAME, '未命中应 return null（不猜）').toContain('return null')
  })

  it('冻结 md5 —— Task 10 之后必须逐字不变', () => {
    expect(
      md5(FN_RESOLVE_NAME),
      'resolveAccountName 已被改动。本 spec 明确不改它（R5.1 保留为兜底）；'
      + `若确有必要改，更新本文件的 RESOLVE_ACCOUNT_NAME_MD5 并在 commit 说明理由。`,
    ).toBe(RESOLVE_ACCOUNT_NAME_MD5)
  })

  it('docstring 承诺的第二匹配方向仍未实现（本 spec 不补）', () => {
    // 注释写「程序名包含科目名（最长优先）→ 科目名包含程序名」，实现只有前者。
    // 本 spec 不补：实证即便补上也救不了 E 循环（程序名「货币资金 - 函证（Leap应对
    // 措施-函证）」不被科目名「其他货币资金」包含），且报表行映射一旦生效它就退居兜底。
    // 冻结这个事实，避免后续会话把它当"漏实现"补上而改动本函数。
    expect(FN_RESOLVE_NAME, '出现了 n.includes(procName) —— 第二匹配方向被补上了').not.toContain('n.includes(procName)')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 A-2：subjectPrefixOf 归一正则（供与后端交叉锁死）
// ═══════════════════════════════════════════════════════════════════════════
describe('类 A：wp_code 归一正则', () => {
  it('subjectPrefixOf 的正则字面量可抽取且为「字母段 + 数字段」', () => {
    const m = FN_SUBJECT_PREFIX.match(/\.match\((\/[^/]+\/)\)/)
    expect(m, '未能抽到 .match(<正则>) —— 锚点已漂移').toBeTruthy()
    expect(m![1], '归一正则已变更 —— 后端 normalize_wp_code 须同步（交叉锁死）')
      .toBe('/^([A-Z]+\\d+)/')
  })

  it('区间型 wp_code 能归一到底稿主码（前端侧口径）', () => {
    const re = /^([A-Z]+\d+)/
    const cases: Array<[string, string]> = [
      ['D2-1至D2-4', 'D2'],
      ['E1-14至E1-15', 'E1'],
      ['F2-61至F2-72', 'F2'],
      ['H10-3', 'H10'],
      ['K13', 'K13'],
      ['无编号', ''],
    ]
    for (const [raw, expected] of cases) {
      const got = raw.toUpperCase().match(re)?.[1] || ''
      expect(got, `${raw} 归一结果不符`).toBe(expected)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 A-3：改造前"取金额两处各算一份"的现状事实
// ═══════════════════════════════════════════════════════════════════════════
describe('类 A：改造前现状（改造后必须收敛）', () => {
  it('宿主里 ctx.accounts[...].amount 的直接取值点数量已冻结', () => {
    // 改造前 = 2 处（buildAndDecide / toReviewRow）。Task 10/12 收口后应为 0 处
    // （全部经 resolveAccountAmount）。本条在 Wave 1 记录现状，收口后由类 B 接管。
    const directReads = countOf(SCRIPT, '?.amount')
      + countOf(SCRIPT, ']?.amount')
    expect(directReads, '直接取 amount 的点数为 0 —— 与改造前现状不符，锚点可能漂移')
      .toBeGreaterThan(0)
  })

  it('toReviewRow 有 covered 门控（改造后必须保留）', () => {
    // 🔴 该门控防「未加载该循环的判据上下文就拿别的循环的科目名匹配」，
    //    去掉会产出看起来合理但张冠李戴的金额。resolveAccountAmount 接入后仍须保留。
    expect(FN_TO_REVIEW_ROW, 'covered 门控被移除').toContain('covered')
    expect(FN_TO_REVIEW_ROW, 'trimContextCycles 覆盖判断被移除').toContain('trimContextCycles')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 类 B：被测实现（Task 10 / 12 之前应全红）
// ═══════════════════════════════════════════════════════════════════════════
/**
 * 被测模块的 import 说明符 —— 🔴 **必须**存进变量并配 `@vite-ignore`。
 *
 * Vite 的 `vite:import-analysis` 插件在**转换期**就解析动态 `import()` 的字面量参数，
 * 模块不存在时整个 spec 文件 collection error、**零断言执行** —— 那时"全红"既可能是
 * 功能没做也可能是守卫写坏，Wave 1 的分类价值全部丢失（本文件初版实测踩到：
 * `Failed to resolve import ... Does the file exist?` + `Tests no tests`）。
 *
 * 存进变量 + `@vite-ignore` 让解析推迟到运行时，于是「模块不存在」表现为**单条**
 * 断言失败而非整文件崩溃，类 A 的 10 条独立口径判据照常执行。
 */
const AMOUNT_SOURCE_MODULE = '../../components/workpaper/composables/trimAmountSource'

async function loadAmountSource(): Promise<Record<string, any>> {
  expect(
    fs.existsSync(P_AMOUNT_TS),
    `模块不存在：${P_AMOUNT_TS} —— ${NOT_IMPLEMENTED}`,
  ).toBe(true)
  try {
    return await import(/* @vite-ignore */ AMOUNT_SOURCE_MODULE)
  } catch (e) {
    throw new Error(`无法 import trimAmountSource —— ${NOT_IMPLEMENTED}: ${String(e)}`)
  }
}

function ctxOf(overrides: Record<string, any> = {}): any {
  return {
    accounts: {},
    materiality: null,
    risk: {},
    risk_dimension_available: false,
    completeness_override: null,
    workpaper_entry: {},
    report_line_amounts: {},
    degradations: [],
    ...overrides,
  }
}

describe('类 B：resolveAccountAmount 存在与契约', () => {
  it('模块存在且导出 resolveAccountAmount', async () => {
    const mod = await loadAmountSource()
    expect(typeof (mod as any).resolveAccountAmount, `未导出 resolveAccountAmount —— ${NOT_IMPLEMENTED}`)
      .toBe('function')
  })

  it('返回五键结构（amount / source / reportLine / accountName / divergence）', async () => {
    const { resolveAccountAmount } = await loadAmountSource() as any
    const got = resolveAccountAmount({ wp_code: 'D99', procedure_name: 'x' }, ctxOf())
    for (const key of ['amount', 'source', 'reportLine', 'accountName', 'divergence']) {
      expect(Object.prototype.hasOwnProperty.call(got, key), `返回值缺 ${key}`).toBe(true)
    }
  })
})

describe('类 B：优先级与兜底（Property 14）', () => {
  it('报表行 resolved 时 source = report_line 且用报表行金额', async () => {
    const { resolveAccountAmount } = await loadAmountSource() as any
    const got = resolveAccountAmount(
      { wp_code: 'E1-1至E1-11', procedure_name: '货币资金 - 函证' },
      ctxOf({
        accounts: { 其他货币资金: { amount: 8280881.84, cycle: 'E' } },
        report_line_amounts: {
          E1: {
            status: 'resolved',
            amount: 8607977.04,
            row_code: 'BS-002',
            row_name: '货币资金',
            formula: "TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')",
            standard_codes: ['1001', '1002', '1012'],
            applicable_standard: 'soe_standalone',
            source_symbol: 'e_cycle_specs.E1_REPORT_ROW_CODE',
            reason: '',
          },
        },
      }),
    )
    expect(got.source, '报表行命中时来源应为 report_line').toBe('report_line')
    expect(got.amount, '未采用报表行金额').toBe(8607977.04)
    expect(got.reportLine?.row_code, '未带报表行溯源').toBe('BS-002')
  })

  it('报表行未命中时退回科目名匹配，source = account_name', async () => {
    const { resolveAccountAmount } = await loadAmountSource() as any
    const got = resolveAccountAmount(
      { wp_code: 'D2-1至D2-4', procedure_name: '应收账款 - 函证' },
      ctxOf({
        accounts: { 应收账款: { amount: 1234.5, cycle: 'D' } },
        report_line_amounts: {
          D2: { status: 'no_report_line', amount: null, row_code: '', reason: '未登记' },
        },
      }),
    )
    expect(got.source, '未退回科目名兜底').toBe('account_name')
    expect(got.amount).toBe(1234.5)
    expect(got.accountName).toBe('应收账款')
  })

  it('报表行键缺失（后端未下发）时同样退回兜底 —— 不得抛异常', async () => {
    const { resolveAccountAmount } = await loadAmountSource() as any
    const ctx = ctxOf({ accounts: { 应收账款: { amount: 99, cycle: 'D' } } })
    delete (ctx as any).report_line_amounts
    const got = resolveAccountAmount({ wp_code: 'D2', procedure_name: '应收账款' }, ctx)
    expect(got.source, 'Wave 4 未下发新键时应表现为退回兜底').toBe('account_name')
    expect(got.amount).toBe(99)
  })

  it('两者都未命中时 amount = null（与改造前逐字相同）', async () => {
    const { resolveAccountAmount } = await loadAmountSource() as any
    const got = resolveAccountAmount({ wp_code: 'D99', procedure_name: '不存在的程序' }, ctxOf())
    expect(got.amount, '两者都未命中却给了金额').toBeNull()
    expect(got.source, '两者都未命中时 source 应为 null').toBeNull()
  })

  it('报表行 status 非 resolved 但带了金额时**不采用**（防后端违约）', async () => {
    const { resolveAccountAmount } = await loadAmountSource() as any
    const got = resolveAccountAmount(
      { wp_code: 'D2', procedure_name: '应收账款' },
      ctxOf({
        accounts: { 应收账款: { amount: 77, cycle: 'D' } },
        report_line_amounts: {
          D2: { status: 'formula_unavailable', amount: 0, row_code: 'BS-006', reason: '无公式' },
        },
      }),
    )
    expect(got.source, 'status 非 resolved 的金额被采用了 —— 编造的 0 会产生错误裁剪建议')
      .toBe('account_name')
    expect(got.amount).toBe(77)
  })

  it('报表行 amount 非有限数时退回兜底', async () => {
    const { resolveAccountAmount } = await loadAmountSource() as any
    for (const bogus of [null, undefined, Number.NaN, Infinity, 'x']) {
      const got = resolveAccountAmount(
        { wp_code: 'D2', procedure_name: '应收账款' },
        ctxOf({
          accounts: { 应收账款: { amount: 55, cycle: 'D' } },
          report_line_amounts: { D2: { status: 'resolved', amount: bogus, row_code: 'BS-006' } },
        }),
      )
      expect(got.source, `amount=${String(bogus)} 时未退回兜底`).toBe('account_name')
    }
  })
})

describe('类 B：差异留痕（Property 14 / R5.2）', () => {
  it('两来源都命中且金额不等 → 采用报表行值并填 divergence', async () => {
    const { resolveAccountAmount } = await loadAmountSource() as any
    // 🔴 样本必须让**科目名能被程序名包含**（`resolveAccountName` 的匹配方向），
    //    否则科目名一侧天然不命中、divergence 恒 null，这条判据就成了空转。
    //    E 循环的真实情形恰恰是匹配不上（程序名「货币资金 - 函证」不含科目名
    //    「其他货币资金」）—— 那种情形由下面「只有报表行命中」那条覆盖。
    //    此处构造的是「两者都命中但金额不等」：报表行是三个科目的合计，
    //    科目名匹配到的只是其中一个明细。
    const got = resolveAccountAmount(
      { wp_code: 'E1', procedure_name: '货币资金 - 函证' },
      ctxOf({
        accounts: { 货币资金: { amount: 8280881.84, cycle: 'E' } },
        report_line_amounts: {
          E1: {
            status: 'resolved', amount: 8607977.04, row_code: 'BS-002',
            row_name: '货币资金', formula: "TB('1001')", standard_codes: ['1001'],
          },
        },
      }),
    )
    expect(got.source).toBe('report_line')
    expect(got.amount).toBe(8607977.04)
    expect(got.divergence, '两来源金额不等却未留痕').toBeTruthy()
    expect(String(got.divergence), 'divergence 未含报表行金额').toContain('8,607,977.04')
    expect(String(got.divergence), 'divergence 未含科目名匹配金额').toContain('8,280,881.84')
  })

  it('两来源都命中且金额相等 → divergence 为 null（不制造噪音）', async () => {
    const { resolveAccountAmount } = await loadAmountSource() as any
    const got = resolveAccountAmount(
      { wp_code: 'D2', procedure_name: '应收账款' },
      ctxOf({
        accounts: { 应收账款: { amount: 1000, cycle: 'D' } },
        report_line_amounts: {
          D2: { status: 'resolved', amount: 1000, row_code: 'BS-006', row_name: '应收账款' },
        },
      }),
    )
    expect(got.divergence, '金额相等却报了差异').toBeNull()
  })

  it('只有报表行命中（科目名解析不出）→ divergence 为 null', async () => {
    const { resolveAccountAmount } = await loadAmountSource() as any
    const got = resolveAccountAmount(
      { wp_code: 'E1', procedure_name: '货币资金 - 函证' },
      ctxOf({
        report_line_amounts: {
          E1: { status: 'resolved', amount: 8607977.04, row_code: 'BS-002' },
        },
      }),
    )
    expect(got.source).toBe('report_line')
    expect(got.divergence, '只有一个来源命中却报了差异').toBeNull()
    expect(got.accountName, '科目名解析不出时应为 null').toBeNull()
  })
})

describe('类 B：区间型 wp_code 查得到报表行（R1.7 前端侧）', () => {
  it('D2-1至D2-4 能命中以 D2 为键的报表行金额', async () => {
    const { resolveAccountAmount } = await loadAmountSource() as any
    const got = resolveAccountAmount(
      { wp_code: 'D2-1至D2-4', procedure_name: '应收账款 - 函证' },
      ctxOf({
        report_line_amounts: {
          D2: { status: 'resolved', amount: 13656018.02, row_code: 'BS-006', row_name: '应收账款' },
        },
      }),
    )
    expect(got.source, '区间型 wp_code 未归一到底稿主码').toBe('report_line')
    expect(got.amount).toBe(13656018.02)
  })

  it('优先取完整 wp_code 键，其次取归一后的主码', async () => {
    // 后端按归一后的主码下发，但若将来按完整码下发也不应失配。
    const { resolveAccountAmount } = await loadAmountSource() as any
    const got = resolveAccountAmount(
      { wp_code: 'D2-1至D2-4', procedure_name: '应收账款' },
      ctxOf({
        report_line_amounts: {
          'D2-1至D2-4': { status: 'resolved', amount: 111, row_code: 'BS-006' },
          D2: { status: 'resolved', amount: 222, row_code: 'BS-006' },
        },
      }),
    )
    expect(got.amount, '完整 wp_code 键未优先').toBe(111)
  })
})

describe('类 B：宿主两处收口到同一函数（Property 17 / R6.2）', () => {
  it('ProcedureTrimming.vue import 了 resolveAccountAmount', () => {
    expect(
      SCRIPT.includes('resolveAccountAmount'),
      `宿主未引用 resolveAccountAmount —— ${NOT_IMPLEMENTED}`,
    ).toBe(true)
    expect(SCRIPT, '未从 trimAmountSource 模块 import').toContain('trimAmountSource')
  })

  it('buildAndDecide 的金额来自 resolveAccountAmount', () => {
    expect(
      FN_BUILD_DECIDE.includes('resolveAccountAmount'),
      `buildAndDecide 未走统一入口 —— ${NOT_IMPLEMENTED}`,
    ).toBe(true)
  })

  it('toReviewRow 的金额来自 resolveAccountAmount（无第二个实现）', () => {
    expect(
      FN_TO_REVIEW_ROW.includes('resolveAccountAmount'),
      `toReviewRow 未走统一入口 —— 复核视图会显示旧口径金额（${NOT_IMPLEMENTED}）`,
    ).toBe(true)
  })

  it('宿主里不再有直接从 accounts 取 .amount 的点（全部经统一入口）', () => {
    // 🔴 这是「无第二个取金额实现」的结构判据：只要还有一处直接从 accounts 取数，
    //    它就可能与 resolveAccountAmount 分叉，而复核者无从知道该信哪个。
    //
    // 🔴 锚点必须绑定 `accounts` 这个来源，不能只数 `?.amount` —— 后者会误命中
    //    `evidence?.amountSource`（`?.amount` 是它的前缀）与 `resolvedAmount?.amount`
    //    （统一入口的返回值，正是要求的写法），产生假红（本文件初版实测踩到）。
    const hits = Array.from(SCRIPT.matchAll(/accounts[^\n]{0,60}?\.amount\b/g)).map(m => m[0])
    expect(
      hits,
      `宿主仍有 ${hits.length} 处直接从 accounts 取金额，须收口到 resolveAccountAmount`
      + `（${NOT_IMPLEMENTED}）：\n${hits.join('\n')}`,
    ).toEqual([])
  })

  it('反向自检：直接从 accounts 取金额的写法必须被上一条抓到', () => {
    // 若正则抓不到真实写法，上一条就是空转 —— 无论宿主怎么写都绿。
    const samples = [
      'const a = Number((ctx.accounts as any)[accountName]?.amount)',
      'const b = Number((ctx as TrimDecisionContext).accounts?.[name]?.amount)',
      'const c = ctx.accounts[n].amount',
    ]
    for (const s of samples) {
      const hit = Array.from(s.matchAll(/accounts[^\n]{0,60}?\.amount\b/g))
      expect(hit.length, `判据漏掉了这种写法：${s}`).toBeGreaterThan(0)
    }
    // 反向：合法写法不得被误命中
    for (const ok of [
      'const d = resolvedAmount?.amount ?? null',
      'const e = evidence?.amountSource ?? null',
      'accountAmount: resolvedAmount?.amount ?? null',
    ]) {
      const hit = Array.from(ok.matchAll(/accounts[^\n]{0,60}?\.amount\b/g))
      expect(hit.length, `判据误命中了合法写法：${ok}`).toBe(0)
    }
  })

  it('相同输入下裁剪页与复核视图口径逐项相等（行为级）', async () => {
    // 两处都调同一纯函数 ⇒ 相等是结构性事实。本条断言该函数对同一入参幂等，
    // 即"两处相等"不依赖调用顺序或外部状态。
    const { resolveAccountAmount } = await loadAmountSource() as any
    const p = { wp_code: 'E1-1至E1-11', procedure_name: '货币资金 - 函证' }
    const ctx = ctxOf({
      accounts: { 其他货币资金: { amount: 8280881.84, cycle: 'E' } },
      report_line_amounts: {
        E1: { status: 'resolved', amount: 8607977.04, row_code: 'BS-002', row_name: '货币资金' },
      },
    })
    const a = resolveAccountAmount(p, ctx)
    const b = resolveAccountAmount(p, ctx)
    expect(a).toEqual(b)
  })
})

describe('类 B：兜底来源在界面上显式可辨（Property 18 / R6.3）', () => {
  it('模板渲染兜底标记，且由 source 门控', () => {
    expect(
      TEMPLATE.includes('account_name'),
      `模板未按 source 区分兜底来源 —— 复核者无从知道该金额可靠性较低（${NOT_IMPLEMENTED}）`,
    ).toBe(true)
    expect(TEMPLATE, '模板未出现「科目名匹配」标记文案').toContain('科目名匹配')
  })

  it('报表行来源时不渲染兜底标记（门控是双向的）', () => {
    // 门控表达式必须显式比较 source，不能只判「有没有 reportLine」——
    // 后者在 status 非 resolved 时也非空，会把不可解析态标成报表行来源。
    const hasGuard = /_amountSource\s*===\s*'account_name'/.test(SCRIPT)
      || /amountSource\s*===\s*'account_name'/.test(TEMPLATE)
      || /_amountSource\s*===\s*'account_name'/.test(TEMPLATE)
    expect(hasGuard, `未见 source === 'account_name' 的门控表达式（${NOT_IMPLEMENTED}）`).toBe(true)
  })
})

describe('类 B：与后端 normalize_wp_code 交叉锁死（Property 5）', () => {
  it('后端索引模块存在且归一实现与前端正则同语义', () => {
    expect(
      fs.existsSync(P_BACKEND_INDEX),
      `后端索引模块不存在：${P_BACKEND_INDEX} —— 尚未实现（Task 4）`,
    ).toBe(true)
    const py = stripComments(read(P_BACKEND_INDEX), true)
    // 后端用 re 模块做归一；抽出它的正则字面量与前端比对语义
    const m = py.match(/re\.compile\(\s*r?["']([^"']+)["']/)
    expect(m, '后端未用 re.compile 声明归一正则 —— 无法交叉锁死').toBeTruthy()
    const pattern = m![1]
    expect(pattern, '后端归一正则未锚定行首').toContain('^')
    expect(
      /A-Z/.test(pattern) && /\\d/.test(pattern),
      `后端归一正则 ${pattern} 缺「字母段 + 数字段」两要素 —— 与前端 /^([A-Z]+\\d+)/ 不同语义`,
    ).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 汇总闸去重键（Task 16 浏览器实测暴露的缺陷）
//
// Requirements: 5.2（差异留痕的同族问题：同一余额不得重复计入汇总）
//
// ## 缺陷现场
//
// `evaluateAggregateGate` 按 `accountName` 去重，语义是「同一笔科目余额只算一次错报
// 敞口」（它的注释明确写着「同一科目下多张底稿的程序会被同时建议裁剪，累加会让合计
// 虚高数倍」）。但报表行映射生效前，E 循环的科目名解析不出 ⇒ 去重键退回 `wp_code`
// ⇒ 那时金额也是 null（计 0）⇒ 合计恒 0、闸门不亮，**缺陷被数据掩盖**。
//
// 报表行映射生效后金额有了，去重键仍是 `wp_code` ⇒ 浏览器实测：E 循环 4 条程序都落
// `BS-002 货币资金`（同一笔 8,607,977.04），闸门算成 **34,431,908.16（虚高 4 倍）**
// ⇒ 超过实际执行重要性 26,104,487.00 ⇒ **过度阻断批量确认**。
//
// 🔴 这类缺陷四层静态检查全查不出（类型对、单测各自绿、金额本身也对），
//    只有在真实数据上跑一遍才暴露 —— 故判据同时落**源码结构**与**行为**两层。
// ═══════════════════════════════════════════════════════════════════════════
describe('汇总闸去重键：同一报表行只算一次错报敞口', () => {
  it('去重键函数存在且按「报表行 → 科目名 → 底稿编号」退化', async () => {
    const { aggregateGateKey } = await loadAmountSource() as any
    expect(typeof aggregateGateKey, '未导出 aggregateGateKey').toBe('function')
    // 报表行优先
    expect(aggregateGateKey({ reportLine: { rowCode: 'BS-002' } }, '货币资金', 'E1-1至E1-11'))
      .toBe('BS-002')
    // 无报表行 → 科目名
    expect(aggregateGateKey({ reportLine: null }, '应收账款', 'D2-1')).toBe('应收账款')
    expect(aggregateGateKey(null, '应收账款', 'D2-1')).toBe('应收账款')
    // 两者都无 → 底稿编号（语义较弱但总比无键好）
    expect(aggregateGateKey(null, '', 'D2-1')).toBe('D2-1')
    expect(aggregateGateKey(undefined, null, 'D2-1')).toBe('D2-1')
    // 空白不算有效键
    expect(aggregateGateKey({ reportLine: { rowCode: '   ' } }, '  ', 'D2-1')).toBe('D2-1')
  })

  it('行为级：4 条同报表行的建议喂进真实闸门 → 去重成 1 个科目', async () => {
    const { aggregateGateKey } = await loadAmountSource() as any
    const { evaluateAggregateGate } = await import(
      '@/components/workpaper/composables/trimAggregateGate'
    )
    // 复现实测现场：E 循环 4 条程序，同一报表行 BS-002，同一笔 8,607,977.04
    const rows = ['E1-1至E1-11', 'E1-14至E1-15', 'E1-18至E1-23', 'E1-26至E1-32'].map(wp => ({
      wp_code: wp,
      _decisionEvidence: {
        accountAmount: 8607977.04,
        reportLine: { rowCode: 'BS-002', rowName: '货币资金' },
      },
      _decisionAccountName: null,
      _suggestReasonCode: 'below_materiality',
    }))
    const gate = evaluateAggregateGate({
      items: rows.map(p => ({
        accountName: aggregateGateKey(
          p._decisionEvidence, p._decisionAccountName, p.wp_code,
        ),
        amount: Number(p._decisionEvidence?.accountAmount ?? 0),
        reasonCode: String(p._suggestReasonCode ?? ''),
      })),
      performanceMateriality: 26104487,
    })
    expect(gate.distinctAccountCount, '同一报表行未被去重（错报敞口被重复计入）').toBe(1)
    expect(gate.totalAmount, '汇总额虚高').toBeCloseTo(8607977.04, 2)
    expect(gate.blocked, '单笔余额低于实际执行重要性却触发了闸门（过度阻断）').toBe(false)
  })

  it('反向自检：用 wp_code 当去重键会虚高 4 倍并误触闸门', async () => {
    // 证明上一条不是恒绿 —— 换回旧去重键必须复现实测的虚高与过度阻断。
    const { evaluateAggregateGate } = await import(
      '@/components/workpaper/composables/trimAggregateGate'
    )
    const gate = evaluateAggregateGate({
      items: ['E1-1至E1-11', 'E1-14至E1-15', 'E1-18至E1-23', 'E1-26至E1-32'].map(wp => ({
        accountName: wp,
        amount: 8607977.04,
        reasonCode: 'below_materiality',
      })),
      performanceMateriality: 26104487,
    })
    expect(gate.distinctAccountCount, '旧去重键下应算成 4 个科目（复现缺陷）').toBe(4)
    expect(gate.totalAmount).toBeCloseTo(34431908.16, 2)
    expect(gate.blocked, '旧去重键下应误触闸门（复现缺陷）').toBe(true)
  })

  it('不同报表行仍各自计入（去重不能过度）', async () => {
    const { aggregateGateKey } = await loadAmountSource() as any
    const { evaluateAggregateGate } = await import(
      '@/components/workpaper/composables/trimAggregateGate'
    )
    const items = [
      { row: 'BS-002', amt: 8607977.04, wp: 'E1-1至E1-11' },
      { row: 'BS-006', amt: 13656018.02, wp: 'D2-1至D2-4' },
      { row: 'BS-046', amt: 5000000, wp: 'D3-1' },
    ].map(x => ({
      accountName: aggregateGateKey({ reportLine: { rowCode: x.row } }, null, x.wp),
      amount: x.amt,
      reasonCode: 'below_materiality',
    }))
    const gate = evaluateAggregateGate({ items, performanceMateriality: 26104487 })
    expect(gate.distinctAccountCount, '不同报表行被误合并').toBe(3)
    expect(gate.totalAmount).toBeCloseTo(8607977.04 + 13656018.02 + 5000000, 2)
    expect(gate.blocked, '三个不同科目合计已超实际执行重要性，应触发闸门').toBe(true)
  })

  it('宿主 suggestedGateItems 用 aggregateGateKey 而不是裸 wp_code', () => {
    const seg = SCRIPT.slice(SCRIPT.indexOf('const suggestedGateItems'))
      .slice(0, 700)
    expect(seg, '未截到 suggestedGateItems 声明').not.toBe('')
    expect(
      seg.includes('aggregateGateKey'),
      '汇总闸去重键未走 aggregateGateKey —— 同一报表行的多条程序会被重复计入，'
      + `汇总额虚高、批量确认被过度阻断（${NOT_IMPLEMENTED}）`,
    ).toBe(true)
  })
})
