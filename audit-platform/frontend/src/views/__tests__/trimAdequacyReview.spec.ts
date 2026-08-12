/**
 * 裁剪充分性复核视图守卫（只读 + 同真源 + 未知态不退化 + 异常判据承重）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 20
 * _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_ / Property 29
 *
 * ## 本文件首要防的四类缺陷
 *
 * 1. **只读被悄悄破掉**。复核视图一旦能写，复核者同时是执行者，「独立复核」在流程上
 *    就不成立。判据不止「没出现写函数名」（那种判据一个 `as any` 就绕过），而是
 *    **组件的 import 源里没有任何 api / http 模块** —— 没有写入能力比"约定不写"可靠。
 *
 * 2. **第二套统计口径**。「相同输入下与裁剪页统计逐项相等」（R12.7）只有一种可靠落法：
 *    两处调同一个函数。故判据落在「汇总闸参数由同一个 `suggestedGateItems` computed
 *    提供」「金额汇总由 `evaluateAggregateGate` 承担、复核模块不自己求和」上，并配
 *    行为级 deepEqual 与「与 `progressStats` / `suggestionStats` 逐项相等」的 mount 断言。
 *
 * 3. **未知态退化成 0**。三处：未加载循环、待确认不可派生、重要性水平未确定。
 *    三者都会让复核者读出一个错的结论（「该循环没裁过东西」「没有待确认建议」
 *    「合计低于重要性」），而界面上都显示得出数、看不出异常。
 *
 * 4. **两类互为对偶的渲染缺陷**（本文件此前实证，四层检查全绿）：
 *    - Task 13：模板调了个**零声明**标识符 ⇒ 运行时 ReferenceError
 *    - Task 14：脚本声明了绑定却**没有模板宿主** ⇒ 交互永远不存在
 *    故绑定判据必须**双向**，且模板自由调用要逐个回落到脚本声明。
 *
 * ## 🔴 `get_diagnostics` 在 `ProcedureTrimming.vue` 上是盲的
 *
 * Task 19 用负控制证明过：往该文件塞 `const x: number = '字符串'` 也返回 0 条。
 * 故类型面另用隔离 tsconfig 跑 vue-tsc 核（本轮：正控制静默 + 三条负控制
 * TS2305 / TS2322 / TS2339 全部打红）。本文件承担的是**结构与行为**，不是类型。
 *
 * ## 判据必须剥注释
 *
 * 实现里刻意在注释中保留了 `aggregateGate` / `buildTrimAdequacyReview` /
 * `evaluateAggregateGate` 等字样（记录同真源的理由），故一切「名字是否出现」类判据
 * 必须先 `stripComments`，并配反向自检「raw 命中 > clean 命中」——否则判据会被
 * 自己的说明文字骗绿。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import * as fs from 'node:fs'
import * as path from 'node:path'

// ── 行为级判据用的 mock ──────────────────────────────────────────────────────
const mocks = vi.hoisted(() => ({
  getProcedures: vi.fn(),
  initProcedures: vi.fn(),
  addCustomProcedure: vi.fn(),
  listProjects: vi.fn(),
  assignProcedures: vi.fn(),
  previewProcedureDelegation: vi.fn(),
  applyProcedureDelegation: vi.fn(),
  fetchDelegationMemberLoads: vi.fn(),
  fetchB50RiskRows: vi.fn(),
  canonicalTrimPreview: vi.fn(),
  canonicalTrimApply: vi.fn(),
  fetchTrimDecisionContext: vi.fn(),
  rejectTrimSuggestions: vi.fn(),
  fetchCompletenessScopeOverrides: vi.fn(),
  saveCompletenessScopeOverride: vi.fn(),
  clearCompletenessScopeOverride: vi.fn(),
  listAssignments: vi.fn(),
  listWorkpapersPaged: vi.fn(),
  httpGet: vi.fn(),
  httpPost: vi.fn(),
  confirm: vi.fn(),
  msgSuccess: vi.fn(),
  msgWarning: vi.fn(),
}))

vi.mock('@/services/commonApi', () => ({
  getProcedures: mocks.getProcedures,
  initProcedures: mocks.initProcedures,
  addCustomProcedure: mocks.addCustomProcedure,
  listProjects: mocks.listProjects,
  assignProcedures: mocks.assignProcedures,
  previewProcedureDelegation: mocks.previewProcedureDelegation,
  applyProcedureDelegation: mocks.applyProcedureDelegation,
  fetchDelegationMemberLoads: mocks.fetchDelegationMemberLoads,
  fetchB50RiskRows: mocks.fetchB50RiskRows,
  canonicalTrimPreview: mocks.canonicalTrimPreview,
  canonicalTrimApply: mocks.canonicalTrimApply,
  fetchTrimDecisionContext: mocks.fetchTrimDecisionContext,
  rejectTrimSuggestions: mocks.rejectTrimSuggestions,
  fetchCompletenessScopeOverrides: mocks.fetchCompletenessScopeOverrides,
  saveCompletenessScopeOverride: mocks.saveCompletenessScopeOverride,
  clearCompletenessScopeOverride: mocks.clearCompletenessScopeOverride,
}))
vi.mock('@/services/staffApi', () => ({ listAssignments: mocks.listAssignments }))
vi.mock('@/services/workpaperApi', () => ({ listWorkpapersPaged: mocks.listWorkpapersPaged }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: mocks.httpGet, post: mocks.httpPost } }))
vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({ currentRole: { value: 'manager' } }),
}))
vi.mock('@/composables/useAuditContext', () => ({
  useAuditContext: () => ({ year: { value: 2025 } }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'project-1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
  onBeforeRouteLeave: vi.fn(),
}))
vi.mock('element-plus', () => ({
  ElMessage: Object.assign(
    (..._a: any[]) => {},
    { success: mocks.msgSuccess, warning: mocks.msgWarning, error: vi.fn(), info: vi.fn() },
  ),
  ElMessageBox: {
    confirm: mocks.confirm,
    prompt: vi.fn().mockResolvedValue({ value: 'x' }),
    alert: vi.fn().mockResolvedValue(true),
  },
}))

import ProcedureTrimming from '../ProcedureTrimming.vue'
import GtTrimAdequacyReview from '@/components/workpaper/trim/GtTrimAdequacyReview.vue'
import {
  buildTrimAdequacyReview,
  type ReviewCycleInput,
  type ReviewProcedureRow,
} from '@/components/workpaper/composables/trimAdequacyReview'
import { evaluateAggregateGate } from '@/components/workpaper/composables/trimAggregateGate'

// ═══════════════════════════════════════════════════════════════════════════
// 源码读取与 helper（沿用 Task 13/14/19 已修好的版本）
// ═══════════════════════════════════════════════════════════════════════════

/** 双哨兵向上找仓库根（单哨兵不稳，目录做哨兵会被历史空目录骗停）。 */
function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 12; i += 1) {
    const a = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    const b = path.join(dir, 'backend', 'app', 'main.py')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repoRoot 未找到（双哨兵 audit-platform/frontend/package.json + backend/app/main.py）')
}

const ROOT = repoRoot()
const FE = path.join(ROOT, 'audit-platform', 'frontend', 'src')

const P_TRIM_VUE = path.join(FE, 'views', 'ProcedureTrimming.vue')
const P_REVIEW_VUE = path.join(FE, 'components', 'workpaper', 'trim', 'GtTrimAdequacyReview.vue')
const P_REVIEW_TS = path.join(FE, 'components', 'workpaper', 'composables', 'trimAdequacyReview.ts')

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/**
 * 带字符串状态的注释剥离（`accept="image/*"` 里的 `/*` 不能当块注释起点）。
 * 同时剥 SFC 模板的 `<!-- -->`。
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
 * 🔴 不能用「声明后第一个 `{`」—— 那个 `{` 可能是**参数列表里的解构/内联对象类型**
 * （`function onReviewLocate(payload: { cycle: string; ... })`）或内联返回类型注解，
 * 截出来的"函数体"是那段类型，断言全在无关文本上求值（可能假红也可能假绿）。
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

/**
 * 截取 `const NAME = computed(...)` 的**实参区**（圆括号配对）。
 *
 * 🔴 不能对 `computed` 写带泛型的正则：`computed<Record<string, boolean> | null>(` 里
 * `[^>]*` 会停在内层 `>` 上导致整条失配、返回空串，进而以
 * `expected '' to contain ...` 的形态**假红**（Task 14 实证）。故只锚
 * `const NAME = computed`，再取其后第一个 `(`（泛型里不会有圆括号）。
 */
function computedArg(src: string, name: string): string {
  const anchor = new RegExp(`const\\s+${name}\\s*=\\s*computed`)
  const m = src.match(anchor)
  if (!m || m.index === undefined) return ''
  const open = src.indexOf('(', m.index + m[0].length)
  if (open < 0) return ''
  let depth = 0
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === '(') depth += 1
    else if (src[i] === ')') {
      depth -= 1
      if (depth === 0) return src.slice(open, i + 1)
    }
  }
  return ''
}

/**
 * SFC 三段切分。
 *
 * 🔴 `</template>` 取 `<script setup` 之前的**最后一个** —— 大 SFC 里有几十个嵌套
 * `<template #default>` 插槽，按第一个闭合标签切只能拿到一小截模板，判据会空转恒绿。
 */
function sfcSegments(clean: string) {
  const tplStart = clean.indexOf('<template>')
  const scStart = clean.indexOf('<script setup')
  const scEnd = clean.indexOf('</script>', scStart)
  expect(tplStart, '未找到 <template>').toBeGreaterThanOrEqual(0)
  expect(scStart, '未找到 <script setup').toBeGreaterThan(tplStart)
  const tplEnd = clean.lastIndexOf('</template>', scStart)
  expect(tplEnd, '未找到 </template>').toBeGreaterThan(tplStart)
  return {
    template: clean.slice(tplStart, tplEnd),
    script: clean.slice(scStart, scEnd),
    style: clean.slice(clean.indexOf('<style')),
    naiveTemplate: clean.slice(tplStart, clean.indexOf('</template>', tplStart)),
  }
}

function rawSegments(raw: string) {
  const tplStart = raw.indexOf('<template>')
  const scStart = raw.indexOf('<script setup')
  const tplEnd = raw.lastIndexOf('</template>', scStart)
  return {
    template: raw.slice(tplStart, tplEnd),
    script: raw.slice(scStart, raw.indexOf('</script>', scStart)),
  }
}

function countOf(hay: string, needle: string): number {
  return hay.split(needle).length - 1
}

/** 抽出所有 `from '...'` 的 import 源。 */
function importSources(src: string): string[] {
  return Array.from(src.matchAll(/from\s+['"]([^'"]+)['"]/g)).map(m => m[1])
}

/**
 * 抽出模板里的自由调用标识符（`foo(` 形态，排除 `a.foo(`）。
 *
 * 🔴 左边界用**负向后顾**而非 `\b`：`\b` 在 `$emit(` 前不成立，会把 `$` 起头的
 * 标识符整类漏掉（Task 13 实证）。提取域含 `_` / `$` 起头。
 */
function templateFreeCalls(template: string): Set<string> {
  const out = new Set<string>()
  for (const m of template.matchAll(/(?<![\w$.])([a-z_$][\w$]*)\s*\(/g)) {
    out.add(m[1])
  }
  return out
}

const RAW = read(P_TRIM_VUE)
const CLEAN = stripComments(RAW)
const SEG = sfcSegments(CLEAN)
const RAW_SEG = rawSegments(RAW)

const RVW_RAW = read(P_REVIEW_VUE)
const RVW_CLEAN = stripComments(RVW_RAW)
const RVW = sfcSegments(RVW_CLEAN)

const TS_RAW = read(P_REVIEW_TS)
const TS_CLEAN = stripComments(TS_RAW)

/** 宿主侧新增函数体（结构判据落在它们身上）。 */
const FN_TO_ROW = fnBody(SEG.script, /function toReviewRow\b/)
const FN_LOCATE = fnBody(SEG.script, /async function onReviewLocate\b/)
const FN_JUMP_CYCLE = fnBody(SEG.script, /async function onReviewJumpCycle\b/)
const FN_OPEN = fnBody(SEG.script, /async function openTrimReview\b/)
const FN_ROWCLASS = fnBody(SEG.script, /function procedureRowClass\b/)

/** 纯函数模块侧函数体。 */
const FN_BUILD = fnBody(TS_CLEAN, /export function buildTrimAdequacyReview\b/)
const FN_MAT_PANEL = fnBody(TS_CLEAN, /function buildMaterialityPanel\b/)
const FN_MAT_NARR = fnBody(TS_CLEAN, /function buildMaterialityNarrative\b/)
const FN_RISK = fnBody(TS_CLEAN, /function isRiskProtected\b/)
const FN_MISSING = fnBody(TS_CLEAN, /function isMissingReason\b/)

/** Task 20 在宿主脚本声明、且**必须**有模板消费方的绑定。 */
const TASK20_UI_BINDINGS = [
  'showReviewDrawer',
  'reviewLoading',
  'trimAdequacyReview',
  'openTrimReview',
  'onReviewLocate',
  'onReviewJumpCycle',
  'locatedWpCode',
  'procedureRowClass',
] as const

/**
 * 复核视图**绝不允许**出现的写入入口。
 *
 * 判据不止「名字不出现」（`(x as any).f()` 一个类型断言就绕过），主判据是
 * import 源里没有 api/http 模块 —— 没有写入能力比"约定不写"可靠。
 */
const FORBIDDEN_WRITE_CALLS = [
  'canonicalTrimApply',
  'canonicalTrimPreview',
  'rejectTrimSuggestions',
  'saveCompletenessScopeOverride',
  'clearCompletenessScopeOverride',
  'applyProcedureDelegation',
  'previewProcedureDelegation',
  'assignProcedures',
  'initProcedures',
  'addCustomProcedure',
] as const

// ── 构造输入（真实库 procedure_instances 已裁剪恒 0 行，只能用构造输入）──
function row(over: Partial<ReviewProcedureRow> = {}): ReviewProcedureRow {
  return {
    wpCode: 'D2-1',
    procedureCode: 'D2-1-01',
    procedureName: '应收账款函证',
    trimmed: false,
    skipReason: '',
    reasonCode: null,
    rejected: false,
    accountName: '应收账款',
    accountAmount: 1000,
    riskLevel: null,
    riskSpecial: false,
    riskKnown: false,
    ...over,
  }
}

function cyc(over: Partial<ReviewCycleInput> = {}): ReviewCycleInput {
  return { cycle: 'D', label: 'D 收入', loaded: true, rows: [], suggested: null, ...over }
}

function build(over: Partial<Parameters<typeof buildTrimAdequacyReview>[0]> = {}) {
  return buildTrimAdequacyReview({
    cycles: [],
    platformDefaultCompleteness: [],
    performanceMateriality: 500000,
    suggestedGateItems: [],
    ...over,
  })
}

// ═══════════════════════════════════════════════════════════════════════════
// helper 自检（防判据空转 / 假红）
// ═══════════════════════════════════════════════════════════════════════════
describe('Task 20 helper 自检', () => {
  it('stripComments 剥 JS/HTML 注释，保留字符串字面量', () => {
    const s = '<!-- openTrimReview 只在注释里 -->\n<a accept="image/*" />\n// x\nconst y = "/*keep*/"'
    const out = stripComments(s)
    expect(out).not.toContain('openTrimReview')
    expect(out).toContain('accept="image/*"')
    expect(out).toContain('/*keep*/')
    expect(out).not.toContain('// x')
  })

  it('fnBody 跳过参数列表里的内联对象类型，截到真正的函数体', () => {
    const s = [
      'async function f(p: { a: string; b: number | null }) {',
      '  const t = 1',
      '  return t',
      '}',
    ].join('\n')
    const body = fnBody(s, /async function f\b/)
    expect(body, 'fnBody 截空 = helper 失效').not.toBe('')
    expect(body).toContain('const t = 1')
    expect(body, '误截了参数列表的类型注解').not.toContain('b: number | null')
  })

  it('computedArg 不被嵌套泛型骗到（Task 14 的假红成因）', () => {
    const s = "const m = computed<Record<string, boolean> | null>(() => resolveIt(1))"
    expect(computedArg(s, 'm'), '泛型里的 > 让正则失配 ⇒ 返回空串 ⇒ 假红').toContain('resolveIt')
  })

  it('templateFreeCalls 提取域含 $ 与 _ 起头，且排除 a.foo(', () => {
    const got = templateFreeCalls('<div>{{ $emit(1) }}{{ _priv(2) }}{{ obj.skip(3) }}{{ ok(4) }}</div>')
    expect(got.has('$emit')).toBe(true)
    expect(got.has('_priv')).toBe(true)
    expect(got.has('ok')).toBe(true)
    expect(got.has('skip'), '接收者形态不该被当自由调用').toBe(false)
  })

  it('模板切分取「script 前最后一个 </template>」而非第一个', () => {
    expect(SEG.template.length, '正确切法必须显著长于朴素切法')
      .toBeGreaterThan(SEG.naiveTemplate.length * 2)
    expect(RVW.template.length).toBeGreaterThan(0)
  })

  it('被测函数体与扫描面均非空（扫描面空 = 判据空转恒绿）', () => {
    const surfaces: Array<[string, string]> = [
      ['宿主 template', SEG.template], ['宿主 script', SEG.script], ['宿主 style', SEG.style],
      ['复核组件 template', RVW.template], ['复核组件 script', RVW.script],
      ['复核组件 style', RVW.style], ['纯函数模块', TS_CLEAN],
      ['toReviewRow', FN_TO_ROW], ['onReviewLocate', FN_LOCATE],
      ['onReviewJumpCycle', FN_JUMP_CYCLE], ['openTrimReview', FN_OPEN],
      ['procedureRowClass', FN_ROWCLASS], ['buildTrimAdequacyReview', FN_BUILD],
      ['buildMaterialityPanel', FN_MAT_PANEL], ['buildMaterialityNarrative', FN_MAT_NARR],
      ['isRiskProtected', FN_RISK], ['isMissingReason', FN_MISSING],
    ]
    for (const [label, body] of surfaces) {
      expect(body.length, `${label} 提取为空 ⇒ 相关判据在空文本上求值`).toBeGreaterThan(20)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 A：只读是承重属性（R12.6 / Property 29）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 A — 复核视图只读', () => {
  it('复核组件不 import 任何 api / http 模块（没有写入能力，而不是约定不写）', () => {
    const srcs = importSources(RVW_CLEAN)
    expect(srcs.length, 'import 抽取为 0 = 判据空转').toBeGreaterThan(0)
    for (const s of srcs) {
      expect(
        /services\//.test(s) || /utils\/http/.test(s) || /axios/.test(s),
        `复核组件 import 了 ${s} —— 只读视图不得具备发请求的能力`,
      ).toBe(false)
    }
  })

  it('复核组件源码里不出现任何写入函数名（剥注释后）', () => {
    for (const name of FORBIDDEN_WRITE_CALLS) {
      expect(RVW_CLEAN.includes(name), `复核组件出现写入入口 ${name}`).toBe(false)
    }
  })

  it('复核组件不含 http 写方法结构（post/put/delete/patch）', () => {
    expect(RVW_CLEAN).not.toMatch(/\.(post|put|delete|patch)\s*\(/)
  })

  it('纯函数模块零 IO：不 import api/http，也不含 async / await / fetch', () => {
    for (const s of importSources(TS_CLEAN)) {
      expect(/services\//.test(s) || /utils\/http/.test(s), `纯函数模块 import 了 ${s}`).toBe(false)
    }
    expect(TS_CLEAN, '纯函数模块出现 async').not.toMatch(/\basync\b/)
    expect(TS_CLEAN, '纯函数模块出现 await').not.toMatch(/\bawait\b/)
    expect(TS_CLEAN, '纯函数模块出现 fetch').not.toMatch(/\bfetch\s*\(/)
  })

  it('纯函数模块零 Vue 依赖（可直接单测与变异检验）', () => {
    for (const s of importSources(TS_CLEAN)) {
      expect(s === 'vue' || s.startsWith('vue/'), `纯函数模块 import 了 ${s}`).toBe(false)
    }
  })

  it('反向自检：这些写入函数名在宿主里确实存在（证明上面不是恒真）', () => {
    const present = FORBIDDEN_WRITE_CALLS.filter(n => SEG.script.includes(n))
    expect(present.length, '宿主里一个写入函数都没有 ⇒ 判据 A 的对照失效').toBeGreaterThan(3)
  })

  it('反向自检：注释里提到的写入函数名被剥掉（raw 命中 > clean 命中）', () => {
    const raw = countOf(RVW_RAW, 'canonicalTrimApply')
    const clean = countOf(RVW_CLEAN, 'canonicalTrimApply')
    expect(raw, '复核组件注释里未提该名，本条反向自检失去意义').toBeGreaterThan(0)
    expect(clean, '剥注释失效 ⇒ 判据会被自己的说明文字骗红').toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 B：统计同真源（R12.7 / Property 29）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 B — 统计由裁剪决策同一真源派生', () => {
  it('汇总闸参数由 suggestedGateItems 提供，而不是自己再 map 一遍', () => {
    const arg = computedArg(SEG.script, 'aggregateGate')
    expect(arg.length, '未截到 aggregateGate 的 computed 实参区').toBeGreaterThan(20)
    expect(arg).toContain('suggestedGateItems.value')
    expect(arg, '汇总闸自己又 map 一遍 suggestedRows ⇒ 与复核视图两份口径')
      .not.toMatch(/suggestedRows\.value\s*\.map/)
    expect(arg).toContain('performanceMateriality.value')
  })

  it('复核视图入参用同一批建议项与同一个阈值来源', () => {
    const arg = computedArg(SEG.script, 'trimAdequacyReview')
    expect(arg.length, '未截到 trimAdequacyReview 的 computed 实参区').toBeGreaterThan(20)
    expect(arg).toContain('buildTrimAdequacyReview(')
    expect(arg).toContain('suggestedGateItems.value')
    expect(arg).toContain('performanceMateriality.value')
    expect(arg, '复核视图自己再构造一份建议项 ⇒ 第二真源')
      .not.toMatch(/suggestedRows\.value\s*\.map/)
  })

  it('宿主只有一处构造汇总闸建议项（suggestedGateItems 是唯一 map 点）', () => {
    const decl = countOf(SEG.script, 'const suggestedGateItems = computed')
    expect(decl, 'suggestedGateItems 声明数应恰为 1').toBe(1)
    const mapPoints = countOf(SEG.script, 'suggestedRows.value.map')
    expect(mapPoints, `suggestedRows.value.map 出现 ${mapPoints} 处 ⇒ 存在第二份建议项构造`).toBe(1)
  })

  it('阈值只有一处读取点（禁两处各写一遍 ?? null 表达式）', () => {
    const reads = countOf(SEG.script, 'materiality?.performance_materiality')
    expect(reads, `performance_materiality 读取点 ${reads} 处 ⇒ 一侧改口径不会被发现`).toBe(1)
  })

  it('金额汇总由 evaluateAggregateGate 承担，复核模块不自己求和', () => {
    expect(FN_MAT_PANEL).toContain('evaluateAggregateGate(')
    expect(countOf(FN_MAT_PANEL, 'evaluateAggregateGate('), '待确认与已确认两道闸都要走同一函数')
      .toBe(2)
    expect(FN_MAT_PANEL, '复核模块自己取绝对值求和 = 第二份去重/阈值口径')
      .not.toMatch(/Math\.abs/)
    expect(FN_BUILD, 'buildTrimAdequacyReview 主体不该自己求金额合计')
      .not.toMatch(/Math\.abs/)
  })

  it('理由码分类走 trimReasonCodes 真源（不在本模块另列机器码集合）', () => {
    expect(TS_CLEAN).toMatch(/from\s+'\.\/trimReasonCodes'/)
    expect(TS_CLEAN).toContain('isMachineReasonCode(')
    expect(TS_CLEAN, '另建一份机器码集合 = 与后端交叉锁死的守卫管不到它')
      .not.toMatch(/MACHINE_REASON_CODES\s*[:=]\s*new\s+Set/)
  })

  it('整体重要性不得作为判据（两个新文件都不出现）', () => {
    for (const [label, src] of [['纯函数模块', TS_CLEAN], ['复核组件', RVW_CLEAN]] as const) {
      expect(src, `${label} 出现 overall_materiality`).not.toContain('overall_materiality')
      expect(src, `${label} 出现 overallMateriality`).not.toContain('overallMateriality')
    }
  })

  it('行为级：待确认汇总闸与直接调 evaluateAggregateGate 逐字段相等', () => {
    const items = [
      { accountName: '应收账款', amount: -120000, reasonCode: 'below_materiality' },
      { accountName: '应收账款', amount: -120000, reasonCode: 'below_trivial' },
      { accountName: '预付款项', amount: 30000, reasonCode: 'below_trivial' },
      { accountName: '其他', amount: 999999, reasonCode: 'no_data' },
    ]
    const direct = evaluateAggregateGate({ items, performanceMateriality: 500000 })
    const review = build({ suggestedGateItems: items })
    expect(review.materiality.suggestedGate).toEqual(direct)
  })

  it('行为级：保留/已裁/缺理由与裁剪页表达式逐项相等', () => {
    const rows = [
      row({ trimmed: false }),
      row({ wpCode: 'D2-2', trimmed: true, skipReason: '本期无该类交易' }),
      row({ wpCode: 'D2-3', trimmed: true, skipReason: '' }),
      row({ wpCode: 'D2-4', trimmed: true, skipReason: '   ' }),
    ]
    const r = build({ cycles: [cyc({ rows })] })
    const s = r.cycles[0]
    // 裁剪页 progressStats / overviewRows 的同款表达式
    expect(s.keep).toBe(rows.filter(x => !x.trimmed).length)
    expect(s.trimmed).toBe(rows.filter(x => x.trimmed).length)
    expect(s.missingReason).toBe(
      rows.filter(x => x.trimmed && !(x.skipReason || '').trim()).length,
    )
    expect(s.missingReason).toBe(2)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 C：三个未知态不得退化成 0
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 C — 未知态不退化为 0', () => {
  it('未加载循环：suggested 为 null 且计数不进合计', () => {
    const r = build({
      cycles: [
        cyc({ cycle: 'D', rows: [row({ trimmed: true, skipReason: 'x' })], suggested: 3 }),
        cyc({ cycle: 'E', loaded: false, rows: [], suggested: null }),
      ],
    })
    const e = r.cycles.find(c => c.cycle === 'E')!
    expect(e.loaded).toBe(false)
    expect(e.suggested, '未加载循环报 0 会被读成"该循环没有待确认建议"').toBeNull()
    expect(r.unloadedCycles).toContain('E')
    expect(r.totals.total, '未加载循环不得进合计').toBe(1)
    expect(r.totals.suggested).toBe(3)
  })

  it('待确认不可派生的已加载循环：suggested 为 null，不是 0', () => {
    const r = build({ cycles: [cyc({ rows: [row()], suggested: null })] })
    expect(r.cycles[0].loaded).toBe(true)
    expect(r.cycles[0].suggested).toBeNull()
    expect(r.suggestedDerivableCycles).toEqual([])
    expect(r.totals.suggested, '一个循环都不可派生时合计必须为 null').toBeNull()
  })

  it('重要性水平未确定：materialityAvailable=false 且不得宣称"低于重要性"', () => {
    const r = build({
      performanceMateriality: null,
      cycles: [cyc({ rows: [row({ trimmed: true, skipReason: 'x', reasonCode: 'below_materiality' })] })],
    })
    expect(r.materiality.materialityAvailable).toBe(false)
    expect(r.materiality.performanceMateriality).toBeNull()
    expect(r.materiality.confirmedGate.blocked, '无基准时不得阻断也不得放行结论').toBe(false)
    expect(r.materiality.narrative).toContain('尚未确定实际执行重要性')
    expect(r.materiality.narrative, '未确定重要性却给出"低于"结论 = 谎报已做汇总评估')
      .not.toContain('合计低于')
    // 但已按金额类理由码裁掉的条数仍要如实报出
    expect(r.materiality.confirmedCount).toBe(1)
  })

  it('已确认金额类裁剪但金额无法定位：单独计数，不当 0 计入合计', () => {
    const r = build({
      cycles: [cyc({
        rows: [
          row({ wpCode: 'D2-1', trimmed: true, skipReason: 'x', reasonCode: 'below_materiality', accountAmount: 200000 }),
          row({ wpCode: 'D2-2', trimmed: true, skipReason: 'x', reasonCode: 'below_materiality', accountName: null, accountAmount: null }),
        ],
      })],
    })
    expect(r.materiality.confirmedCount).toBe(2)
    expect(r.materiality.amountUnknownCount).toBe(1)
    expect(r.materiality.confirmedGate.distinctAccountCount, '不可定位项不得占去重槽位').toBe(1)
    expect(r.materiality.confirmedGate.totalAmount).toBe(200000)
    expect(r.materiality.narrative).toContain('无法定位')
    expect(r.materiality.narrative).toContain('实际汇总额高于此数')
  })

  it('完整性覆盖状态未知：标 unknown 且不产出任何平台默认异常', () => {
    const r = build({ platformDefaultCompleteness: null })
    expect(r.completenessOverrideUnknown).toBe(true)
    expect(
      r.anomalies.filter(a => a.kind === 'platform_default_completeness').length,
      '读取失败被当成"全部平台默认" ⇒ 把技术故障说成实质结论',
    ).toBe(0)
  })

  it('宿主：覆盖表未加载时如实传 null（不传空数组）', () => {
    const arg = computedArg(SEG.script, 'reviewPlatformDefaults')
    expect(arg.length, '未截到 reviewPlatformDefaults 实参区').toBeGreaterThan(20)
    expect(arg).toMatch(/completenessOverrides\.value\s*===\s*null/)
    expect(arg).toMatch(/return\s+null/)
    expect(arg, '标注开关必须取纯函数输出的 usingPlatformDefault').toContain('usingPlatformDefault')
  })

  it('宿主：非当前循环的待确认数如实传 null', () => {
    const arg = computedArg(SEG.script, 'reviewCycleInputs')
    expect(arg.length, '未截到 reviewCycleInputs 实参区').toBeGreaterThan(20)
    expect(arg, '待确认必须由 isActive 门控并在其余循环传 null')
      .toMatch(/suggested:\s*isActive\s*&&\s*loaded\s*\?[\s\S]{0,80}?:\s*null/)
    expect(arg, '待确认必须取本页 suggestionStats（同真源）').toContain('suggestionStats.value.suggested')
    expect(arg, '禁在概览侧读原始行上不存在的 _suggest（Task 13 边界）').not.toContain('_suggest')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 D：异常判据承重（R12.3）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 D — 异常组合判据', () => {
  it('风险维度不可用时不得断言高风险被裁（未评估 ≠ 高风险，也 ≠ 非高风险）', () => {
    const r = build({
      cycles: [cyc({
        rows: [row({ trimmed: true, skipReason: 'x', riskLevel: 'H', riskSpecial: true, riskKnown: false })],
      })],
    })
    expect(
      r.anomalies.filter(a => a.kind === 'risk_protected_trimmed').length,
      'B50 未填时凭空断言高风险 = 制造假异常',
    ).toBe(0)
  })

  it('反向：风险已知且为 H 的被裁项必须打出异常', () => {
    const r = build({
      cycles: [cyc({
        rows: [row({ trimmed: true, skipReason: 'x', riskLevel: 'H', riskKnown: true })],
      })],
    })
    const hits = r.anomalies.filter(a => a.kind === 'risk_protected_trimmed')
    expect(hits.length, '高风险科目被裁是本视图最要紧的一条异常').toBe(1)
    expect(hits[0].severity).toBe('high')
    expect(hits[0].wpCode).toBe('D2-1')
  })

  it('特别风险单独成立（riskLevel 为 null 也要打红）', () => {
    const r = build({
      cycles: [cyc({
        rows: [row({ trimmed: true, skipReason: 'x', riskLevel: null, riskSpecial: true, riskKnown: true })],
      })],
    })
    const hits = r.anomalies.filter(a => a.kind === 'risk_protected_trimmed')
    expect(hits.length).toBe(1)
    expect(hits[0].detail).toContain('特别风险')
  })

  it('未被裁的高风险科目不是异常（异常判据必须含 trimmed）', () => {
    const r = build({
      cycles: [cyc({ rows: [row({ trimmed: false, riskLevel: 'H', riskKnown: true })] })],
    })
    expect(r.anomalies.length).toBe(0)
    expect(FN_RISK, 'isRiskProtected 必须先过 riskKnown').toContain('riskKnown')
  })

  it('缺理由判据 = 已裁剪且理由文本为空（与裁剪页/saveTrim 同口径）', () => {
    const r = build({
      cycles: [cyc({
        rows: [
          row({ wpCode: 'A', trimmed: true, skipReason: '' }),
          row({ wpCode: 'B', trimmed: true, skipReason: '本期无该类交易', reasonCode: null }),
        ],
      })],
    })
    const miss = r.anomalies.filter(a => a.kind === 'missing_reason')
    expect(miss.length, '有文本无理由码的存量记录不得算缺理由（R8.4）').toBe(1)
    expect(miss[0].wpCode).toBe('A')
    expect(r.cycles[0].legacyTextOnly, '存量记录应计入"仅自由文本"桶').toBe(1)
    expect(FN_MISSING, 'isMissingReason 必须看 skipReason 而不是 reasonCode').toContain('skipReason')
    expect(FN_MISSING).not.toContain('reasonCode')
  })

  it('平台默认完整性清单 → medium 异常，且 detail 含审计依据原文', () => {
    const r = build({
      platformDefaultCompleteness: [{
        cycle: 'L', label: 'L 债务', sensitiveByDefault: true,
        rationale: '表外负债与未记录负债是最经典的完整性风险',
      }],
    })
    const hits = r.anomalies.filter(a => a.kind === 'platform_default_completeness')
    expect(hits.length).toBe(1)
    expect(hits[0].severity).toBe('medium')
    expect(hits[0].wpCode, '循环级异常没有具体程序').toBeNull()
    expect(hits[0].detail, '依据原文必须带出来，否则复核者看不出凭什么默认这样')
      .toContain('表外负债与未记录负债是最经典的完整性风险')
  })

  it('每条异常的 detail 都必须写清判据与后果（只上色不算）', () => {
    const r = build({
      cycles: [cyc({
        rows: [
          row({ wpCode: 'A', trimmed: true, skipReason: '' }),
          row({ wpCode: 'B', trimmed: true, skipReason: 'x', riskLevel: 'H', riskKnown: true }),
        ],
      })],
      platformDefaultCompleteness: [{ cycle: 'L', label: 'L 债务', sensitiveByDefault: true, rationale: '表外负债风险' }],
    })
    expect(r.anomalies.length).toBe(3)
    for (const a of r.anomalies) {
      expect(a.detail.length, `${a.kind} 的 detail 过短 ⇒ 复核者看不出为什么被标`)
        .toBeGreaterThanOrEqual(40)
      expect(a.title.length).toBeGreaterThan(4)
    }
  })

  it('每循环异常计数与异常清单一致（回填不得漏）', () => {
    const r = build({
      cycles: [
        cyc({ cycle: 'D', rows: [row({ trimmed: true, skipReason: '' })] }),
        cyc({ cycle: 'E', label: 'E 货币资金', rows: [] }),
      ],
      platformDefaultCompleteness: [{ cycle: 'E', label: 'E 货币资金', sensitiveByDefault: false, rationale: '主风险为存在与估值' }],
    })
    for (const s of r.cycles) {
      expect(s.anomalyCount).toBe(r.anomalies.filter(a => a.cycle === s.cycle).length)
    }
    expect(r.cycles.find(c => c.cycle === 'D')!.anomalyCount).toBe(1)
    expect(r.cycles.find(c => c.cycle === 'E')!.anomalyCount).toBe(1)
  })

  it('理由码分布：机器码在前，含存量与缺理由两个非码桶', () => {
    const r = build({
      cycles: [cyc({
        rows: [
          row({ wpCode: 'A', trimmed: true, skipReason: 'x', reasonCode: 'below_materiality' }),
          row({ wpCode: 'B', trimmed: true, skipReason: 'x', reasonCode: 'no_related_business' }),
          row({ wpCode: 'C', trimmed: true, skipReason: 'x', reasonCode: null }),
          row({ wpCode: 'D', trimmed: true, skipReason: '' }),
        ],
      })],
    })
    const kinds = r.reasonDistribution.map(e => e.kind)
    expect(kinds[0]).toBe('machine')
    expect(kinds).toContain('manual')
    expect(kinds).toContain('legacy_text')
    expect(kinds).toContain('missing')
    const machine = r.reasonDistribution.find(e => e.code === 'below_materiality')!
    expect(machine.label, '未翻成中文标签 ⇒ 复核者看到裸英文码').toBe('金额低于实际执行重要性')
  })

  it('宿主 toReviewRow：风险已知必须同时满足维度可用 + 该科目有结论', () => {
    expect(FN_TO_ROW).toContain('risk_dimension_available')
    expect(FN_TO_ROW, '未覆盖循环不得跨循环解析科目（会张冠李戴）')
      .toContain('trimContextCycles')
    expect(FN_TO_ROW, '科目名解析必须复用同一个 resolveAccountName')
      .toContain('resolveAccountName(')
    expect(FN_TO_ROW, '风险入参必须复用同一个 toRiskInput').toContain('toRiskInput(')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 E：绑定 × 渲染宿主 双向（Task 13 / 14 两类缺陷的对偶）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 E — 绑定与渲染宿主双向存在', () => {
  it.each(TASK20_UI_BINDINGS)('%s 既在宿主脚本声明又被宿主模板消费', (name) => {
    const declared = new RegExp(`(const|let|function|async\\s+function)\\s+${name}\\b`).test(SEG.script)
    expect(declared, `${name} 无脚本声明 ⇒ 模板引用即 ReferenceError`).toBe(true)
    expect(
      SEG.template.includes(name),
      `${name} 无模板消费方 ⇒ 声明而无渲染宿主（死代码，四层检查全绿）`,
    ).toBe(true)
  })

  it('复核组件真的被宿主模板挂载（import 了却没渲染宿主 = Task 14 那类缺陷）', () => {
    expect(SEG.script).toContain('GtTrimAdequacyReview')
    // 🔴 必须带定界符：`toContain('<GtTrimAdequacyReview')` 会被改名后的
    //    `<GtTrimAdequacyReviewXX` 以子串形态骗过（判据缺陷，非代码缺陷）。
    expect(
      /<GtTrimAdequacyReview[\s/>]/.test(SEG.template),
      '组件未出现在模板里（或标签名被改）⇒ 复核视图永远打不开',
    ).toBe(true)
    expect(SEG.template).toMatch(/:review="trimAdequacyReview"/)
    expect(SEG.template).toMatch(/@locate="onReviewLocate"/)
    expect(SEG.template).toMatch(/@jump-cycle="onReviewJumpCycle"/)
  })

  it('反向自检：哨兵名不在模板里（证明上一条不是恒真）', () => {
    expect(SEG.template.includes('trimReviewNonexistentBinding')).toBe(false)
  })

  it('反向自检：注释里提到的名字被剥掉（raw 命中 > clean 命中）', () => {
    const raw = countOf(RAW_SEG.template, 'aggregateGate')
    const clean = countOf(SEG.template, 'aggregateGate')
    expect(raw, '模板注释里未提该名，本条反向自检失去意义').toBeGreaterThan(clean)
    expect(clean, '模板里必须真的有 aggregateGate 的用法').toBeGreaterThan(0)
  })

  it('复核组件模板的自由调用都在脚本里有声明（Task 13 那类缺陷）', () => {
    const declared = new Set<string>()
    for (const m of RVW.script.matchAll(/(?:const|let|function)\s+([a-zA-Z_$][\w$]*)/g)) {
      declared.add(m[1])
    }
    // Vue 内置与模板宏
    const builtins = new Set(['$emit', '$slots', '$attrs', '$props'])
    // CSS 函数（来自 style 属性里的 calc() / var()），冻结为最小豁免清单
    const cssFns = new Set(['calc', 'var'])
    const free = templateFreeCalls(RVW.template)
    expect(free.size, '模板自由调用提取为 0 = 判据空转').toBeGreaterThan(0)
    const unresolved = Array.from(free).filter(
      n => !declared.has(n) && !builtins.has(n) && !cssFns.has(n),
    )
    expect(unresolved, `模板调用了无声明的标识符：${unresolved.join(', ')}`).toEqual([])
  })

  it('复核组件模板用到的 scoped 类都有样式（缺类只有浏览器能看出没分层）', () => {
    const used = Array.from(new Set(RVW.template.match(/gt-trim-review[\w-]*/g) ?? []))
    expect(used.length, '模板未使用 gt-trim-review 类').toBeGreaterThan(5)
    for (const cls of used) {
      expect(RVW.style.includes(`.${cls}`), `模板用了 .${cls} 但样式里没有`).toBe(true)
    }
  })

  it('宿主：定位行高亮的类既在脚本返回又在样式里定义', () => {
    expect(FN_ROWCLASS).toContain('gt-proc-row--located')
    expect(SEG.style.includes('.gt-proc-row--located'), '行类无样式 ⇒ 定位在表格上看不见')
      .toBe(true)
    expect(SEG.template, '主表格必须挂 row-class-name 否则行类永不生效')
      .toMatch(/:row-class-name="procedureRowClass"/)
  })

  it('复核组件表格字号 13px（平台底稿表格铁律）', () => {
    expect(RVW.template).toMatch(/font-size:\s*13px/)
  })

  it('模板属性里不得出现中文弯引号（会静默崩 Vite 编译）', () => {
    for (const [label, src] of [['宿主', RAW], ['复核组件', RVW_RAW]] as const) {
      for (const ch of ['\u201c', '\u201d', '\ufffd']) {
        expect(src.includes(ch), `${label} 含禁用字符 U+${ch.charCodeAt(0).toString(16)}`).toBe(false)
      }
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 F：定位真的定位（R12.5）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 F — 跳转必须定位到行，不是只切 Tab', () => {
  it('onReviewLocate 切循环 + 过滤到该条 + 记录高亮', () => {
    expect(FN_LOCATE, '未复用既有的循环切换（含脏检查）').toContain('jumpToCycleFromOverview(')
    expect(FN_LOCATE, '只切 Tab 不过滤 = 复核者仍要自己在几十行里找')
      .toContain('searchText.value')
    expect(FN_LOCATE).toContain('locatedWpCode.value')
    expect(FN_LOCATE, '循环级异常应改为打开完整性面板').toContain('openCompletenessPanel(')
  })

  it('onReviewLocate 内不含任何写入调用（复核入口不得改数据）', () => {
    for (const name of FORBIDDEN_WRITE_CALLS) {
      expect(FN_LOCATE.includes(name), `定位路径出现写入调用 ${name}`).toBe(false)
    }
    for (const name of FORBIDDEN_WRITE_CALLS) {
      expect(FN_OPEN.includes(name), `打开复核视图时出现写入调用 ${name}`).toBe(false)
    }
  })

  it('openTrimReview 只做只读取数（三条懒加载都是读）', () => {
    expect(FN_OPEN).toContain('loadAllCyclesData(')
    expect(FN_OPEN).toContain('loadCompletenessOverrides(')
    expect(FN_OPEN).toContain('loadTrimContext(')
    expect(FN_OPEN, '不得在打开复核视图时触发保存').not.toContain('saveTrim(')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 G：行为级（mount 真跑）—— 源码结构对不等于跑得起来
// ═══════════════════════════════════════════════════════════════════════════
const passthrough = (cls: string) => ({ template: `<div class="${cls}"><slot /></div>` })
const ElTableStub = defineComponent({
  props: { data: { type: Array, default: () => [] } },
  setup(_p, { slots }) {
    return () => h('table', { class: 'el-table-stub' }, slots.default?.())
  },
})
const stubs: Record<string, any> = {
  'el-table': ElTableStub,
  'el-table-column': { template: '<div><slot name="header" /></div>' },
  'el-tabs': passthrough('el-tabs'),
  'el-tab-pane': passthrough('el-tab-pane'),
  'el-alert': { template: '<div class="el-alert"><slot name="title" /><slot /></div>' },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>' },
  'el-switch': { template: '<span />' },
  'el-input': { template: '<input />' },
  'el-select': { template: '<div><slot /></div>' },
  'el-option': { template: '<div />' },
  'el-tooltip': { template: '<span><slot name="content" /><slot /></span>' },
  'el-divider': { template: '<span />' },
  'el-progress': { template: '<span />' },
  'el-dialog': { template: '<div class="el-dialog"><slot /><slot name="footer" /></div>' },
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<div><slot /></div>' },
  'el-upload': { template: '<div><slot /></div>' },
  'el-descriptions': { template: '<div><slot /></div>' },
  'el-descriptions-item': { template: '<div><slot /></div>' },
  'el-radio-group': { template: '<div><slot /></div>' },
  'el-radio': { template: '<label><slot /></label>' },
  'el-checkbox': { template: '<label><slot /></label>' },
  'el-checkbox-group': { template: '<div><slot /></div>' },
  'el-empty': { template: '<div />' },
  'el-drawer': { template: '<div><slot /></div>' },
  'el-dropdown': { template: '<div><slot /><slot name="dropdown" /></div>' },
  'el-dropdown-menu': { template: '<div><slot /></div>' },
  'el-dropdown-item': { template: '<div><slot /></div>' },
  GtDelegationSuggestionTable: { template: '<div class="sugtable-stub" />' },
}

const PROC_ROWS = [
  { id: '1', wp_code: 'D2-1', procedure_code: 'D2-1-01', procedure_name: '应收账款函证', status: 'execute' },
  {
    id: '2', wp_code: 'D2-2', procedure_code: 'D2-2-01', procedure_name: '预付款项检查',
    status: 'not_applicable', skip_reason: '',
  },
  {
    id: '3', wp_code: 'D2-3', procedure_code: 'D2-3-01', procedure_name: '合同资产检查',
    status: 'not_applicable', skip_reason: '本期无该类交易',
    suggestion_state: { reason_code: 'below_materiality' },
  },
]

async function mountView() {
  mocks.getProcedures.mockResolvedValue(PROC_ROWS)
  mocks.initProcedures.mockResolvedValue(PROC_ROWS)
  mocks.listAssignments.mockResolvedValue([{ staff_id: 's1', role: 'auditor' }])
  mocks.listProjects.mockResolvedValue([{ id: 'project-1', project_name: '示例项目' }])
  mocks.fetchDelegationMemberLoads.mockResolvedValue({ s1: 2 })
  mocks.fetchB50RiskRows.mockResolvedValue([])
  mocks.fetchCompletenessScopeOverrides.mockResolvedValue([])
  mocks.fetchTrimDecisionContext.mockResolvedValue({
    accounts: { 应收账款: { amount: 120000, cycle: 'D' } },
    materiality: { performance_materiality: 500000, trivial_threshold: 25000 },
    risk: {},
    risk_dimension_available: false,
    completeness_override: {},
    workpaper_entry: {},
    degradations: [],
  })
  mocks.httpGet.mockResolvedValue({ data: { data: { subject_with_data: [], subject_no_data: [] } } })
  mocks.confirm.mockResolvedValue(true)
  const wrapper = mount(ProcedureTrimming, { global: { stubs } })
  await flushPromises()
  return wrapper
}

const WRITE_MOCKS = [
  'canonicalTrimApply', 'canonicalTrimPreview', 'rejectTrimSuggestions',
  'saveCompletenessScopeOverride', 'clearCompletenessScopeOverride',
  'applyProcedureDelegation', 'previewProcedureDelegation', 'assignProcedures',
] as const

function expectNoWrites(label: string) {
  for (const name of WRITE_MOCKS) {
    expect((mocks as any)[name], `${label} 触发了写入调用 ${name}`).not.toHaveBeenCalled()
  }
  expect(mocks.httpPost, `${label} 发了 http.post`).not.toHaveBeenCalled()
}

/**
 * 取重要性面板里某个标签对应格子的值文本。
 *
 * 🔴 判据必须落到**具体那一格**：对整组件文本做 `not.toContain('0.00 元')` 会被
 * 「余额合计 1,000.00 元」里的子串命中而假红（本文件首轮实证）。
 */
function matCellValue(w: any, label: string): string {
  for (const cell of w.findAll('.gt-trim-review__mat-cell')) {
    const lab = cell.find('.gt-trim-review__mat-label')
    if (lab.exists() && lab.text().trim() === label) {
      return cell.find('.gt-trim-review__mat-num').text().trim()
    }
  }
  throw new Error(`未找到重要性面板格子: ${label}`)
}

describe('判据 G — 行为级：复核视图可渲染、只读、且与裁剪页统计相等', () => {
  beforeEach(() => vi.clearAllMocks())

  it('打开复核视图：抽屉开、只读取数、零写入调用', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as any
    vi.clearAllMocks()
    await vm.openTrimReview()
    await flushPromises()
    expect(vm.showReviewDrawer).toBe(true)
    expect(vm.reviewLoading).toBe(false)
    expectNoWrites('openTrimReview')
  })

  it('复核统计与裁剪页 progressStats / suggestionStats 逐项相等（R12.7）', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as any
    await vm.openTrimReview()
    await flushPromises()
    const active = vm.trimAdequacyReview.cycles.find((c: any) => c.cycle === vm.activeCycle)
    expect(active, '当前循环未出现在复核视图里').toBeTruthy()
    expect(active.loaded).toBe(true)
    expect(active.keep).toBe(vm.progressStats.execute)
    expect(active.trimmed).toBe(vm.progressStats.trimmed)
    expect(active.total).toBe(vm.progressStats.total)
    expect(active.suggested).toBe(vm.suggestionStats.suggested)
    // 汇总闸与裁剪页那道闸门同输入同输出
    expect(vm.trimAdequacyReview.materiality.suggestedGate).toEqual(vm.aggregateGate)
  })

  it('缺理由计数与裁剪页概览口径一致（同一批行）', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as any
    await vm.openTrimReview()
    await flushPromises()
    const active = vm.trimAdequacyReview.cycles.find((c: any) => c.cycle === vm.activeCycle)
    const expected = vm.procedures.filter(
      (p: any) => !p._applicable && !(p.skip_reason || '').trim(),
    ).length
    expect(active.missingReason).toBe(expected)
    expect(expected, '构造数据里应有一条缺理由，否则本条空转').toBe(1)
  })

  it('定位：切循环 + 过滤到该条 + 行高亮，且零写入', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as any
    await vm.openTrimReview()
    await flushPromises()
    vi.clearAllMocks()
    await vm.onReviewLocate({ cycle: vm.activeCycle, wpCode: 'D2-2', kind: 'missing_reason' })
    await flushPromises()
    expect(vm.showReviewDrawer).toBe(false)
    expect(vm.searchText).toBe('D2-2')
    expect(vm.locatedWpCode).toBe('D2-2')
    expect(vm.filteredProcedures.length, '过滤后应只剩被定位那一条').toBe(1)
    expect(vm.procedureRowClass({ row: { wp_code: 'D2-2' } })).toBe('gt-proc-row--located')
    expect(vm.procedureRowClass({ row: { wp_code: 'D2-1' } })).toBe('')
    expectNoWrites('onReviewLocate')
  })

  it('循环级异常定位 → 打开完整性面板，不动搜索框', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as any
    await vm.openTrimReview()
    await flushPromises()
    vi.clearAllMocks()
    await vm.onReviewLocate({ cycle: 'L', wpCode: null, kind: 'platform_default_completeness' })
    await flushPromises()
    expect(vm.completenessPanelVisible).toBe(true)
    expect(vm.searchText).toBe('')
    expect(vm.locatedWpCode).toBeNull()
    expectNoWrites('onReviewLocate(platform_default)')
  })

  it('复核组件独立 mount：渲染异常判据原文，点击只 emit 不写库', async () => {
    const review = build({
      cycles: [cyc({ rows: [row({ trimmed: true, skipReason: '', wpCode: 'D2-9' })], suggested: 2 })],
      platformDefaultCompleteness: [{
        cycle: 'L', label: 'L 债务', sensitiveByDefault: true,
        rationale: '表外负债与未记录负债是最经典的完整性风险',
      }],
    })
    const w = mount(GtTrimAdequacyReview, { props: { review }, global: { stubs } })
    await flushPromises()
    const text = w.text()
    expect(text, '异常判据原文未渲染 ⇒ 复核者看不出为什么被标')
      .toContain('表外负债与未记录负债是最经典的完整性风险')
    expect(text).toContain('无理由的裁剪在复核时无法评价其适当性')
    const btns = w.findAll('button')
    expect(btns.length, '异常项没有跳转入口').toBeGreaterThan(0)
    await btns[0].trigger('click')
    expect(w.emitted('locate'), '点击未 emit locate').toBeTruthy()
    expectNoWrites('复核组件独立 mount')
  })

  it('复核组件在重要性未确定时该格显示"未确定"而不是金额', async () => {
    const review = build({
      performanceMateriality: null,
      cycles: [cyc({ rows: [row({ trimmed: true, skipReason: 'x', reasonCode: 'below_materiality' })] })],
    })
    const w = mount(GtTrimAdequacyReview, { props: { review }, global: { stubs } })
    await flushPromises()
    expect(w.text()).toContain('重要性水平未确定')
    // 🔴 判据落在**那一格**上，不是整组件文本 —— 首版写成
    //    `expect(w.text()).not.toContain('0.00 元')`，被「余额合计 1,000.00 元」里的
    //    子串命中而假红（那是判据缺陷不是代码缺陷）。
    expect(matCellValue(w, '实际执行重要性'), '未确定重要性却渲染出金额 = 谎报已做汇总评估')
      .toBe('未确定')
  })

  it('反向自检：重要性已确定时同一格渲染金额（证明上一条不是恒真）', async () => {
    const review = build({
      performanceMateriality: 500000,
      cycles: [cyc({ rows: [row({ trimmed: true, skipReason: 'x', reasonCode: 'below_materiality' })] })],
    })
    const w = mount(GtTrimAdequacyReview, { props: { review }, global: { stubs } })
    await flushPromises()
    expect(matCellValue(w, '实际执行重要性')).toBe('500,000.00 元')
  })

  it('复核组件在待确认不可派生时显示提示而不是 0', async () => {
    const review = build({ cycles: [cyc({ rows: [row()], suggested: null })] })
    const w = mount(GtTrimAdequacyReview, { props: { review }, global: { stubs } })
    await flushPromises()
    expect(w.text()).toContain('需打开该循环')
  })
})
