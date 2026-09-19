/**
 * 建议分配「逐组应用」守卫（走既有委派 preview → apply 两阶段）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 19
 * _Requirements: 11.7, 14.1_ / Property 28（委派写入路径唯一）
 *
 * ## 本文件首要防的三类缺陷（都是本轮实证，不是假想）
 *
 * 1. **第二套写入路径**。逐组应用只要图省事直接 `assignProcedures` 或直写
 *    `procedure_row_tasks` 的分配字段，就同时绕过后端的 `target_versions` 版本校验、
 *    逐 task `assert_sod_distinct`、history / outbox / policy epoch。判据落在
 *    「本 spec 所有自有文件里不得出现直写分配字段的结构」上（剥注释后）。
 *
 * 2. **`wp_index_id` / `wp_id` 混用**。组件 emit 的 `selector.wp_index_ids` 是
 *    `wp_index.id`；`getProcedures` 下发的 `wp_id` 是 `working_paper.id`。后端按
 *    `ProcedureRowTask.wp_index_id.in_(...)` 匹配 ⇒ 传错那个**不报错**、统计全 0。
 *    Task 18 落地时宿主 handler 的形参类型被写成 `{ assigneeStaffId; wpIndexIds }`
 *    （组件根本没有 `wpIndexIds` 字段），`g.wpIndexIds.length` 运行时抛 TypeError。
 *
 * 3. **`summary.targets === 0` 冒充成功**。目标数为 0 时 apply 也会 200 且返回
 *    `applied: 0`，屏幕上就是「委派成功」而一行未动。真实库 `procedure_row_tasks`
 *    仅 46 行 / 3 个项目，多数项目正是这个形态（行任务未物化）。故 `no_target`
 *    必须是独立态，且必须在 apply 调用**之前**短路。
 *
 * ## 🔴 `get_diagnostics` 在 `ProcedureTrimming.vue` 上是**盲的**（本轮实证）
 *
 * 往该文件里塞 `const x: number = 'definitely-not-a-number'` 与一个不存在的
 * type import，`get_diagnostics` 依然返回 0 条。故此前交付记录里「四层全绿」的
 * 那一层在本文件上不构成任何证据。类型面的核验改用隔离 tsconfig 跑 vue-tsc
 * （全项目跑会 OOM，8G 堆也不够）：负控制（不存在的导出 TS2614 + 类型不匹配
 * TS2322）都能打红，正控制 `DelegationApplyGroup` 静默通过 —— 这才证明
 * `<script setup>` 的 type-only export 真的可被别的模块 import。
 *
 * ## 判据必须剥注释
 *
 * 实现里**刻意**在注释中保留了 `wpIndexIds` / `procedure_row_tasks` /
 * `retrySuggestionGroup` 等字样（记录缺陷成因），故一切「名字是否出现」类判据
 * 必须先 `stripComments`，且配反向自检断言「raw 侧命中数 > clean 侧」——
 * 否则判据会被自己的说明文字骗绿。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import * as fs from 'node:fs'
import * as path from 'node:path'

// ── 行为级判据用的 mock（源码级断言证明结构，mount 证明它真能跑）──
//
// 🔴 源码断言与行为断言缺一不可：Task 13 在本文件踩到的「模板调了个零声明标识符」
//    只有 mount 型测试能抓（Volar / vitest 源码扫 / get_diagnostics / HEAD-swap 全绿）；
//    而「一组 409 不中断其余组」这种时序性质只有真跑一遍才算证明。
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
vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
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
  ElMessageBox: { confirm: mocks.confirm, prompt: vi.fn().mockResolvedValue({ value: 'x' }) },
}))

import ProcedureTrimming from '../ProcedureTrimming.vue'

// ── 双哨兵向上找仓库根（单哨兵不稳，目录做哨兵会被历史空目录骗停）──
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
const BE = path.join(ROOT, 'backend', 'app')

const P_TRIM_VUE = path.join(FE, 'views', 'ProcedureTrimming.vue')
const P_COMP = path.join(FE, 'components', 'workpaper', 'delegation', 'GtDelegationSuggestionTable.vue')
const P_COMMON_API = path.join(FE, 'services', 'commonApi.ts')
const P_DELEG_ROUTER = path.join(BE, 'routers', 'procedure_delegations.py')
const P_DELEG_SVC = path.join(BE, 'services', 'procedure_delegation_service.py')
const P_AUTHZ = path.join(BE, 'services', 'procedure_authorization.py')

function read(p: string): string {
  expect(fs.existsSync(p), `文件不存在: ${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8').replace(/\r\n/g, '\n')
}

/**
 * 带字符串状态的注释剥离（`accept="image/*"` 里的 `/*` 不能当块注释起点）。
 * 同时剥 SFC 模板的 `<!-- -->` 与 python 的 `#`（后者仅在非字符串态）。
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
 * 🔴 不能用「声明后第一个 `{`」—— 那个 `{` 可能是内联返回类型注解
 * （`function classifyDelegationConflict(e): { status: X; message: string } {`），
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
 * 截取 python 顶层 class 的类体（缩进边界，**不能**用花括号配对）。
 *
 * 🔴 本文件首轮就踩了：拿 `braceBlockAfter` 去截 `class DelegationSelector` 会命中
 * 类体里第一个字典字面量（`to_payload` 的 `return {...}`），于是断言在无关文本上求值
 * 并以「后端未声明 wp_index_ids」的形态**假红**。python 没有花括号块。
 */
function pyClassBlock(src: string, name: string): string {
  const lines = src.split('\n')
  const start = lines.findIndex(l => new RegExp(`^class\\s+${name}\\b`).test(l))
  if (start < 0) return ''
  let end = lines.length
  for (let i = start + 1; i < lines.length; i += 1) {
    const l = lines[i]
    if (l.trim() === '') continue
    if (/^\S/.test(l)) { end = i; break }
  }
  return lines.slice(start, end).join('\n')
}

/** 截取 `const NAME = {...}` / `interface NAME {...}` 的花括号块（配对，不看类型注解）。 */
function braceBlockAfter(src: string, anchor: RegExp): string {
  const m = src.match(anchor)
  if (!m || m.index === undefined) return ''
  const open = src.indexOf('{', m.index + m[0].length)
  if (open < 0) return ''
  let depth = 0
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === '{') depth += 1
    else if (src[i] === '}') {
      depth -= 1
      if (depth === 0) return src.slice(open, i + 1)
    }
  }
  return ''
}

/**
 * SFC 三段切分。
 *
 * 🔴 `</template>` 取 `<script setup` 之前的**最后一个** —— 本 SFC 有 20+ 个嵌套
 * `<template #default>` 插槽，按第一个闭合标签切只能拿到 ~4% 的模板，判据会空转恒绿。
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
    naiveTemplate: clean.slice(tplStart, clean.indexOf('</template>', tplStart)),
  }
}

function countOf(hay: string, needle: string): number {
  return hay.split(needle).length - 1
}

const RAW = read(P_TRIM_VUE)
const CLEAN = stripComments(RAW)
const SEG = sfcSegments(CLEAN)
const RAW_SEG = (() => {
  // raw 侧同法切分（用于「raw 命中 > clean 命中」的反向自检）
  const tplStart = RAW.indexOf('<template>')
  const scStart = RAW.indexOf('<script setup')
  const tplEnd = RAW.lastIndexOf('</template>', scStart)
  return { template: RAW.slice(tplStart, tplEnd), script: RAW.slice(scStart, RAW.indexOf('</script>', scStart)) }
})()

const COMP_CLEAN = stripComments(read(P_COMP))
const API_CLEAN = stripComments(read(P_COMMON_API))
const ROUTER_PY = stripComments(read(P_DELEG_ROUTER), true)
const SVC_PY = stripComments(read(P_DELEG_SVC), true)
const AUTHZ_PY = stripComments(read(P_AUTHZ), true)

/** 逐组应用的三个核心函数体（结构判据全落在它们身上）。 */
const FN_GROUP = fnBody(SEG.script, /async function applySuggestionGroup\b/)
const FN_ORCH = fnBody(SEG.script, /async function onSuggestionApplyRequest\b/)
const FN_BODYBUILD = fnBody(SEG.script, /function suggestionGroupBody\b/)
const FN_CLASSIFY = fnBody(SEG.script, /function classifyDelegationConflict\b/)
const FN_RETRY = fnBody(SEG.script, /async function retrySuggestionGroup\b/)

/** Task 19 在脚本侧声明、且**必须**有模板消费方的 UI 绑定。 */
const TASK19_UI_BINDINGS = [
  'suggestApply',
  'suggestApplyTotals',
  'suggestApplyStatusLabel',
  'suggestApplyStatusTagType',
  'retrySuggestionGroup',
  'onSuggestionApplyRequest',
] as const

/** 本 spec 自有文件（判据 A 的扫描面）。写入路径唯一性只对它们负责。 */
const SPEC_OWNED_FILES: string[] = [
  P_TRIM_VUE,
  P_COMP,
  path.join(FE, 'components', 'workpaper', 'composables', 'delegationSuggestion.ts'),
  path.join(FE, 'components', 'workpaper', 'composables', 'delegationSeniority.ts'),
  path.join(FE, 'components', 'workpaper', 'composables', 'procedureTrimDecision.ts'),
  path.join(FE, 'components', 'workpaper', 'composables', 'completenessExemption.ts'),
  path.join(FE, 'components', 'workpaper', 'composables', 'trimAggregateGate.ts'),
  path.join(FE, 'components', 'workpaper', 'composables', 'trimReasonCodes.ts'),
  path.join(FE, 'components', 'workpaper', 'composables', 'b50Completeness.ts'),
  path.join(BE, 'services', 'trim_decision_context.py'),
  path.join(BE, 'services', 'workpaper_entry_probe.py'),
  path.join(BE, 'services', 'b50_risk_reader.py'),
  path.join(BE, 'services', 'procedure_trim_service.py'),
  path.join(BE, 'routers', 'procedure_trim.py'),
]

/** 直写 `procedure_row_tasks` 分配字段的结构（一条都不许出现在自有文件里）。 */
const FORBIDDEN_WRITE_PATTERNS: { re: RegExp; why: string }[] = [
  { re: /UPDATE\s+procedure_row_tasks/i, why: '裸 SQL 直改行任务表' },
  { re: /INSERT\s+INTO\s+procedure_row_tasks/i, why: '裸 SQL 直插行任务' },
  { re: /sa\.update\(\s*ProcedureRowTask/, why: 'ORM update() 直改行任务' },
  { re: /ProcedureRowTask\s*\(\s*$/m, why: '直接构造 ProcedureRowTask 实例' },
  { re: /\.assignee_staff_id\s*=(?!=)/, why: '直接赋值执行人字段（绕过 Coordinator）' },
  { re: /\.reviewer_staff_id\s*=(?!=)/, why: '直接赋值复核人字段（绕过 SOD 双查）' },
  { re: /\.assignment_version\s*=(?!=)/, why: '手改分配版本号（会破坏乐观锁）' },
  { re: /\.delegation_batch_id\s*=(?!=)/, why: '手造委派批次号（history/outbox 会对不上）' },
]

// ═══════════════════════════════════════════════════════════════════════════
// helper 自检（防判据空转 / 假红）
// ═══════════════════════════════════════════════════════════════════════════
describe('Task 19 helper 自检', () => {
  it('stripComments 剥 JS/HTML 注释，保留字符串字面量', () => {
    const s = '<!-- retrySuggestionGroup 只在注释里 -->\n<a accept="image/*" />\n// x\nconst y = "/*keep*/"'
    const out = stripComments(s)
    expect(out).not.toContain('retrySuggestionGroup')
    expect(out).toContain('accept="image/*"')
    expect(out).toContain('/*keep*/')
    expect(out).not.toContain('// x')
  })

  it('stripComments(hash) 剥 python 注释但不动字符串里的 #', () => {
    const s = 'x = "a#b"  # 真注释\ny = 1'
    const out = stripComments(s, true)
    expect(out).toContain('"a#b"')
    expect(out).not.toContain('真注释')
  })

  it('fnBody 跳过内联返回类型注解，截到真正的函数体', () => {
    const s = [
      "function f(e: any): { status: string; message: string } {",
      "  const t = 1",
      "  return { status: 'x', message: String(t) }",
      '}',
    ].join('\n')
    const body = fnBody(s, /function f\b/)
    expect(body, 'fnBody 截空 = helper 失效').not.toBe('')
    expect(body).toContain('const t = 1')
    // 若误截返回类型注解，body 里不会有 return
    expect(body).toContain('return')
  })

  it('pyClassBlock 按缩进切类体，不被类体内的字典字面量骗到', () => {
    const s = [
      'class A(BaseModel):',
      '    kind: str',
      '    wp_index_ids: list[UUID] = Field(default_factory=list)',
      '',
      '    def to_payload(self) -> dict:',
      '        return {',
      '            "kind": self.kind,',
      '        }',
      '',
      '',
      'class B(A):',
      '    preview_id: UUID',
    ].join('\n')
    const blk = pyClassBlock(s, 'A')
    expect(blk).toContain('wp_index_ids')
    expect(blk, '越界截到了下一个 class').not.toContain('preview_id')
    // 花括号配对法在 python 上会截错 —— 保留这条对照，防后续会话"统一"成一个 helper
    expect(braceBlockAfter(s, /class\s+A\b/), '花括号法在 python 上必然截错').not.toContain(
      'wp_index_ids',
    )
  })

  it('模板切分取「script 前最后一个 </template>」而非第一个', () => {
    const nested = (SEG.template.match(/<template\s+#/g) ?? []).length
    expect(nested, '未见嵌套 template 插槽，切分自检失去意义').toBeGreaterThan(5)
    expect(SEG.template.length, '正确切法必须显著长于朴素切法').toBeGreaterThan(SEG.naiveTemplate.length * 2)
  })

  it('五个被测函数体都真的截到了（截空会让整组判据空转恒绿）', () => {
    const table: [string, string][] = [
      ['applySuggestionGroup', FN_GROUP],
      ['onSuggestionApplyRequest', FN_ORCH],
      ['suggestionGroupBody', FN_BODYBUILD],
      ['classifyDelegationConflict', FN_CLASSIFY],
      ['retrySuggestionGroup', FN_RETRY],
    ]
    for (const [name, body] of table) {
      expect(body.length, `${name} 函数体截空`).toBeGreaterThan(60)
    }
  })

  it('扫描面非空自检：自有文件全部存在且非空', () => {
    expect(SPEC_OWNED_FILES.length).toBeGreaterThan(8)
    for (const p of SPEC_OWNED_FILES) {
      expect(fs.existsSync(p), `扫描面缺文件 ${p}`).toBe(true)
      expect(read(p).length, `扫描面文件为空 ${p}`).toBeGreaterThan(200)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 A：委派写入路径唯一（Property 28 / R11.7）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 A — 委派写入路径唯一', () => {
  it('逐组应用走既有 preview → apply 两阶段（两个调用都在同一函数体内）', () => {
    expect(FN_GROUP, 'applySuggestionGroup 未调 previewProcedureDelegation').toMatch(
      /previewProcedureDelegation\s*\(/,
    )
    expect(FN_GROUP, 'applySuggestionGroup 未调 applyProcedureDelegation').toMatch(
      /applyProcedureDelegation\s*\(/,
    )
  })

  it('apply 在 preview 之后（顺序倒了就没有一次性凭证可消费）', () => {
    const iPv = FN_GROUP.indexOf('previewProcedureDelegation')
    const iAp = FN_GROUP.indexOf('applyProcedureDelegation')
    expect(iPv).toBeGreaterThanOrEqual(0)
    expect(iAp).toBeGreaterThan(iPv)
  })

  it('本 spec 自有文件不存在直写 procedure_row_tasks 分配字段的结构', () => {
    const hits: string[] = []
    for (const p of SPEC_OWNED_FILES) {
      const isPy = p.endsWith('.py')
      const clean = stripComments(read(p), isPy)
      for (const { re, why } of FORBIDDEN_WRITE_PATTERNS) {
        if (re.test(clean)) hits.push(`${path.basename(p)}: ${why}（${re}）`)
      }
    }
    expect(hits, `发现第二套写入路径:\n${hits.join('\n')}`).toEqual([])
  })

  it('反向自检：注释里确实提到了 procedure_row_tasks（证明 stripComments 承重）', () => {
    const rawHits = countOf(RAW_SEG.script, 'procedure_row_tasks')
    const cleanHits = countOf(SEG.script, 'procedure_row_tasks')
    expect(rawHits, '注释里未提该表名，本组「不得出现」判据无法证明剥注释有效').toBeGreaterThan(0)
    expect(cleanHits, '剥注释后仍出现该表名 = 代码里真有直写').toBe(0)
    expect(rawHits).toBeGreaterThan(cleanHits)
  })

  it('反向自检：禁写模式表非空且真能匹配（防正则全部失效导致空转）', () => {
    expect(FORBIDDEN_WRITE_PATTERNS.length).toBeGreaterThanOrEqual(6)
    const sample = 'task.assignee_staff_id = other_staff_id'
    const matched = FORBIDDEN_WRITE_PATTERNS.filter(x => x.re.test(sample))
    expect(matched.length, '构造样本未被任何禁写模式命中 = 正则失效').toBeGreaterThan(0)
    // `==` 比较不得被误判为赋值
    expect(
      FORBIDDEN_WRITE_PATTERNS.some(x => x.re.test('if (t.assignee_staff_id == s) pass')),
      '比较运算被误判成赋值 → 会把只读代码打红',
    ).toBe(false)
  })

  it('逐组应用不借用 assignProcedures（那是底稿主编层的另一真源）', () => {
    for (const [name, body] of [
      ['applySuggestionGroup', FN_GROUP],
      ['onSuggestionApplyRequest', FN_ORCH],
      ['retrySuggestionGroup', FN_RETRY],
    ] as [string, string][]) {
      expect(body, `${name} 调了 assignProcedures = 双真源`).not.toMatch(/assignProcedures\s*\(/)
      expect(body, `${name} 调了行任务状态机 = 绕过委派服务`).not.toMatch(
        /transitionProcedureRowTask\s*\(/,
      )
    }
  })

  it('展示组件仍然零 IO（写入编排留在宿主）', () => {
    expect(COMP_CLEAN).not.toMatch(/previewProcedureDelegation\s*\(/)
    expect(COMP_CLEAN).not.toMatch(/applyProcedureDelegation\s*\(/)
    expect(COMP_CLEAN, '组件不得 import commonApi').not.toMatch(/from\s+['"]@\/services\/commonApi['"]/)
    // 宿主接住组件的 apply 事件（emit 出口 → 编排入口这条线必须在）
    expect(SEG.template).toMatch(/@apply\s*=\s*"onSuggestionApplyRequest"/)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 B：按执行人分组 + 底稿粒度 selector + 同 body 两阶段
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 B — 分组载荷与 selector 粒度', () => {
  it('selector 用底稿粒度 workpaper + snake_case wp_index_ids', () => {
    expect(FN_BODYBUILD).toMatch(/kind:\s*'workpaper'/)
    expect(FN_BODYBUILD).toMatch(/wp_index_ids\s*:/)
    expect(FN_BODYBUILD, '建议分配是底稿粒度，用 cycle 会把整循环都改成本组执行人').not.toMatch(
      /kind:\s*'cycle'/,
    )
  })

  it('wp_index_ids 取组件的 selector.wp_index_ids，不读不存在的 wpIndexIds', () => {
    expect(FN_ORCH, '未从 selector.wp_index_ids 取值').toMatch(/g\.selector\.wp_index_ids/)
    expect(SEG.script).not.toMatch(/selector\.wpIndexIds/)
    // 🔴 判据按**接收者**而非固定标识符判：首版写成 `not.toMatch(/\bg\.wpIndexIds\b/)`，
    //    被变异 M2 的 `(g as any).wpIndexIds` 一个类型断言就绕过（判定 WRONG-TEST）。
    //    改为「脚本里所有 `.wpIndexIds` 读取的接收者必须是本页的 state」——
    //    括号收尾（强转 / 任意表达式）一律不合格。
    const receivers = Array.from(SEG.script.matchAll(/([A-Za-z_$][\w$]*|\))\s*\.wpIndexIds\b/g))
      .map(m => m[1])
    expect(receivers.length, '脚本里一处 .wpIndexIds 都没有 ⇒ 判据空转').toBeGreaterThan(0)
    for (const r of receivers) {
      expect(
        r,
        `.wpIndexIds 的接收者是 ${r}（只允许本页 SuggestionApplyGroupState 的 state；`
        + '组件 group 上没有这个字段，读它得 undefined 且不报错）',
      ).toBe('state')
    }
    // 组件 group 只以 `g` 出现，且只能从 selector 取 id 列表
    expect(FN_ORCH).not.toMatch(/\bg\b[^\n]{0,20}\.wpIndexIds/)
  })

  it('反向自检：接收者判据抓得住类型断言绕过（M2 的形态）', () => {
    const sample = "wpIndexIds: [...(g as any).wpIndexIds],"
    const receivers = Array.from(sample.matchAll(/([A-Za-z_$][\w$]*|\))\s*\.wpIndexIds\b/g))
      .map(m => m[1])
    expect(receivers, '强转形态未被提取 ⇒ 判据仍有洞').toContain(')')
    // 合法形态不得被误判
    const ok = Array.from('if (state.wpIndexIds.length === 0) {'.matchAll(
      /([A-Za-z_$][\w$]*|\))\s*\.wpIndexIds\b/g,
    )).map(m => m[1])
    expect(ok).toEqual(['state'])
  })

  it('跨文件锁死：组件导出的 DelegationApplyGroup 就是 snake_case 的 wp_index_ids', () => {
    const iface = braceBlockAfter(COMP_CLEAN, /export\s+interface\s+DelegationApplyGroup\b/)
    expect(iface.length, '未截到组件导出的 DelegationApplyGroup').toBeGreaterThan(40)
    expect(iface).toMatch(/wp_index_ids\s*:\s*string\[\]/)
    expect(iface, '组件侧若改成 camelCase 则宿主取值全 undefined').not.toMatch(/wpIndexIds/)
    expect(iface).toMatch(/kind:\s*'workpaper'/)
    // 宿主用组件导出的类型作单一真源，不在本文件镜像第二份
    expect(SEG.script).toMatch(/type\s+DelegationApplyGroup/)
    expect(SEG.script).toMatch(/groups:\s*DelegationApplyGroup\[\]/)
  })

  it('preview 与 apply 复用同一个 body 对象（后端重算 hash 防篡改）', () => {
    const calls = (FN_GROUP.match(/suggestionGroupBody\s*\(/g) ?? []).length
    expect(calls, 'body 构造超过一次 ⇒ 两侧 payload 可能不同 ⇒ 409「预览请求已被篡改」').toBe(1)
    expect(FN_GROUP).toMatch(/previewProcedureDelegation\s*\(\s*projectId\.value\s*,\s*body\s*\)/)
    expect(FN_GROUP).toMatch(/applyProcedureDelegation\s*\([\s\S]{0,160}?\bbody\s*,?\s*\)/)
  })

  it('每组自带 request_id（幂等按组隔离，不共用一个）', () => {
    expect(FN_GROUP).toMatch(/newRequestId\s*\(\s*\)/)
    expect(FN_GROUP, 'apply 第三参必须是本组的 requestId').toMatch(/state\.requestId/)
  })

  it('逐组顺序执行而非并行（并行会互相把 lock_version 顶掉，全组 409）', () => {
    expect(FN_ORCH).toMatch(/for\s*\(/)
    expect(FN_ORCH).toMatch(/await\s+applySuggestionGroup\s*\(/)
    expect(FN_ORCH, '并行提交会让后组恒 409「目标任务版本已变化」').not.toMatch(
      /Promise\.all\([\s\S]{0,200}applySuggestionGroup/,
    )
    expect(FN_ORCH).not.toMatch(/\.map\([^)]*applySuggestionGroup/)
  })

  it('空 wp_index_ids 组不发请求（后端 canonical_selector 会 422）', () => {
    expect(FN_GROUP).toMatch(/wpIndexIds\.length\s*===\s*0/)
    const iEarly = FN_GROUP.indexOf('wpIndexIds.length === 0')
    const iPv = FN_GROUP.indexOf('previewProcedureDelegation')
    expect(iEarly, '空组判断必须在发请求之前').toBeLessThan(iPv)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 C：一组失败不影响其他组 + 409 三分类
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 C — 逐组隔离与 409 分类', () => {
  it('单组自吞异常，循环体不中断后续组', () => {
    expect(FN_GROUP, '组内无 catch ⇒ 异常冒泡到循环 ⇒ 后续组全部不执行').toMatch(/catch\s*\(/)
    expect(FN_ORCH, '循环体内 break ⇒ 一组失败即放弃其余组').not.toMatch(/\bbreak\b/)
    expect(FN_ORCH, '编排层重新抛出 ⇒ 已成功组的结果无从展示').not.toMatch(/\bthrow\b/)
  })

  it('409 三分类：stale / assigned_conflict / sod 各自独立', () => {
    for (const s of ['assigned_conflict', 'sod', 'stale']) {
      expect(FN_CLASSIFY, `409 分类缺 ${s}`).toContain(`'${s}'`)
    }
    expect(FN_GROUP, '409 未走三分类').toMatch(/classifyDelegationConflict\s*\(/)
    expect(FN_GROUP).toMatch(/status\s*===\s*409|=== 409/)
  })

  it('SOD 类 409 不得建议「重新预览」（重新预览一万次也没用，得换人）', () => {
    // 截 sod 分支的返回块
    const sodIdx = FN_CLASSIFY.indexOf("status: 'sod'")
    expect(sodIdx, '未找到 sod 分支').toBeGreaterThan(0)
    const sodBlock = FN_CLASSIFY.slice(sodIdx, sodIdx + 400)
    expect(sodBlock, 'SOD 分支必须明说重新预览无效').toContain('重新预览无效')
    expect(sodBlock, 'SOD 分支必须指向真正的处置：改复核人').toMatch(/改选?操作复核人|改复核人/)
    // 反向：stale 分支才是「可重新预览」
    const staleIdx = FN_CLASSIFY.indexOf("status: 'stale'")
    expect(staleIdx).toBeGreaterThan(0)
    expect(FN_CLASSIFY.slice(staleIdx, staleIdx + 400)).toContain('重新预览')
  })

  it('单组重试只重跑该组，不重建 groups 数组（否则已成功组计数被抹成 0）', () => {
    expect(FN_RETRY).toMatch(/groups\[\s*index\s*\]/)
    expect(FN_RETRY).toMatch(/await\s+applySuggestionGroup\s*\(/)
    expect(FN_RETRY, '重试里重建 groups ⇒ 屏幕上像「上次全白做了」，审计师会重复委派').not.toMatch(
      /suggestApply\.value\.groups\s*=/,
    )
  })

  it('模板逐组展示状态 + 单组重试入口 + 「已成功组不受影响」的明示', () => {
    expect(SEG.template).toMatch(/:data\s*=\s*"suggestApply\.groups"/)
    expect(SEG.template).toMatch(/retrySuggestionGroup\(\s*\$index\s*\)/)
    expect(SEG.template).toMatch(/suggestApplyStatusLabel\(/)
    expect(SEG.template).toMatch(/suggestApplyStatusTagType\(/)
    expect(SEG.template, '必须明示 409 组不影响已成功组，否则审计师会整体重做').toMatch(
      /已成功的组不受影响/,
    )
    expect(SEG.template).toMatch(/suggestApplyTotals\.retryable/)
  })

  it('汇总口径把成功 / 可重试 / 受阻 / 无目标分开计（合成一个数就看不出该做什么）', () => {
    const totals = braceBlockAfter(SEG.script, /const\s+suggestApplyTotals\s*=\s*computed/)
    expect(totals.length).toBeGreaterThan(80)
    for (const k of ['applied', 'retryable', 'blocked', 'noTarget']) {
      expect(totals, `汇总缺 ${k}`).toContain(k)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 D：targets === 0 不冒充成功
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 D — 无目标不得报成功', () => {
  it('目标数读后端真键 summary.targets（顶层 target_count 不存在）', () => {
    expect(FN_GROUP).toMatch(/summary\?\.targets|summary\.targets/)
    expect(FN_GROUP, '读不存在的顶层键会恒得 undefined').not.toMatch(/\btarget_count\b/)
  })

  it('targets === 0 在 apply 调用之前短路，且落独立态 no_target', () => {
    const iZero = FN_GROUP.search(/targets\s*===\s*0/)
    const iApply = FN_GROUP.indexOf('applyProcedureDelegation')
    expect(iZero, '缺 targets === 0 判断').toBeGreaterThan(0)
    expect(iZero, '零目标判断必须在 apply 之前，否则会拿到 applied:0 的"成功"').toBeLessThan(iApply)
    const zeroBlock = FN_GROUP.slice(iZero, iApply)
    expect(zeroBlock).toContain("'no_target'")
    expect(zeroBlock, '零目标分支必须 return，不能继续走到 apply').toMatch(/\breturn\b/)
  })

  it('no_target 的说明写明三种成因（未物化 / 已裁 / 非 execute）', () => {
    const iZero = FN_GROUP.search(/targets\s*===\s*0/)
    const zeroBlock = FN_GROUP.slice(iZero, iZero + 500)
    expect(zeroBlock).toMatch(/物化/)
    expect(zeroBlock).toMatch(/粗裁|不适用/)
    expect(zeroBlock).toMatch(/execute/)
  })

  it('no_target 的标签与配色都不是「成功」', () => {
    const labels = braceBlockAfter(SEG.script, /const\s+SUGGEST_APPLY_LABELS\b/)
    expect(labels.length).toBeGreaterThan(60)
    const line = labels.split('\n').find(l => l.includes('no_target')) ?? ''
    expect(line, '缺 no_target 标签').not.toBe('')
    expect(line).not.toContain('成功')
    expect(line).not.toContain('已应用')
    const tagFn = fnBody(SEG.script, /function suggestApplyStatusTagType\b/)
    const successLine = tagFn.split('\n').find(l => l.includes("'success'")) ?? ''
    expect(successLine, 'no_target 不得配成功色').not.toContain('no_target')
  })

  it('applied 态的成功文案由真实 applied 计数派生（不写死"成功"）', () => {
    expect(FN_GROUP).toMatch(/state\.applied\s*=\s*Number\(/)
    expect(FN_GROUP).toMatch(/res\?\.applied/)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 E：脚本声明 × 模板消费方 双向（Task 13 / 14 两类缺陷的对偶）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 E — 绑定与渲染宿主双向存在', () => {
  it.each(TASK19_UI_BINDINGS)('%s 既在脚本声明又被模板消费', (name) => {
    const declared = new RegExp(
      `(const|let|function|async\\s+function)\\s+${name}\\b`,
    ).test(SEG.script)
    expect(declared, `${name} 无脚本声明 ⇒ 模板调用即 ReferenceError`).toBe(true)
    expect(
      SEG.template.includes(name),
      `${name} 无模板消费方 ⇒ 声明而无渲染宿主（死代码，四层检查全绿）`,
    ).toBe(true)
  })

  it('反向自检：哨兵名不在模板里（证明上一条不是恒真）', () => {
    expect(SEG.template.includes('suggestApplyNonexistentBinding')).toBe(false)
  })

  it('反向自检：注释里提到的绑定名被剥掉（raw 命中 > clean 命中）', () => {
    const raw = countOf(RAW_SEG.template, 'retrySuggestionGroup')
    const clean = countOf(SEG.template, 'retrySuggestionGroup')
    expect(raw, '模板注释里未提该名，本组反向自检失去意义').toBeGreaterThan(clean)
    expect(clean, '模板里必须真的有 retrySuggestionGroup 的调用').toBeGreaterThan(0)
  })

  it('样式类真的写了（模板引用不存在的 scoped 类不报错、只有浏览器能看出没分层）', () => {
    const style = CLEAN.slice(CLEAN.indexOf('<style'))
    const used = Array.from(new Set(
      (SEG.template.match(/gt-proc-sugapply[\w-]*/g) ?? []),
    ))
    expect(used.length, '模板未使用 gt-proc-sugapply 类').toBeGreaterThan(0)
    for (const cls of used) {
      expect(style.includes(`.${cls}`), `模板用了 .${cls} 但样式里没有`).toBe(true)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 F：跨前后端交叉锁死（一侧改名另一侧未跟进即打红）
// ═══════════════════════════════════════════════════════════════════════════
describe('判据 F — 前后端契约交叉锁死', () => {
  it('后端 DelegationSelector 声明 wp_index_ids，与前端 body 同名', () => {
    const model = pyClassBlock(ROUTER_PY, 'DelegationSelector')
    expect(model.length, '未截到后端 DelegationSelector 类体').toBeGreaterThan(80)
    expect(model, '类体越界（截到了别的 class）').not.toContain('class DelegationPreviewRequest')
    expect(model).toMatch(/wp_index_ids\s*:/)
    expect(model).toMatch(/kind\s*:/)
    // 前端 commonApi 的 selector 类型同名
    expect(API_CLEAN).toMatch(/wp_index_ids\?\s*:\s*string\[\]/)
  })

  it('后端 preview 的 summary 里确有 targets 键（前端读它）', () => {
    expect(SVC_PY).toMatch(/"summary":\s*\{/)
    expect(SVC_PY).toMatch(/"targets":\s*len\(targets\)/)
  })

  it('后端 apply 返回 applied / unchanged / conflict 三键（前端逐组展示它们）', () => {
    for (const k of ['"applied"', '"unchanged"', '"conflict"']) {
      expect(SVC_PY, `apply 返回缺 ${k}`).toContain(k)
    }
    expect(SEG.template).toMatch(/row\.applied/)
    expect(SEG.template).toMatch(/row\.unchanged/)
    expect(SEG.template).toMatch(/row\.conflict/)
  })

  it('workpaper selector 空列表在后端是 422（故前端必须先过滤空组）', () => {
    expect(SVC_PY).toContain('workpaper selector 缺 wp_index_ids')
    expect(SVC_PY).toMatch(/status_code=422/)
  })

  it('SOD 冲突在后端是 409 而非 422（决定前端把它归到 409 分类里）', () => {
    const sodFn = SVC_PY.includes('assert_sod_distinct')
    expect(sodFn, 'service 未调 assert_sod_distinct').toBe(true)
    const idx = AUTHZ_PY.indexOf('职责分离冲突')
    expect(idx, '未找到 SOD 冲突文案').toBeGreaterThan(0)
    const around = AUTHZ_PY.slice(Math.max(0, idx - 200), idx + 100)
    expect(around, 'SOD 若不是 409，前端的三分类归属就错了').toMatch(/status_code=409/)
  })

  it('版本变化与预览失效都是 409（前端归为 stale：重新预览有用）', () => {
    expect(SVC_PY).toContain('目标任务版本已变化，请重新预览')
    const pv = stripComments(read(path.join(BE, 'services', 'procedure_operation_preview.py')), true)
    expect(pv).toMatch(/预览凭证已过期/)
    expect(pv).toMatch(/预览请求已被篡改/)
    expect(pv).toMatch(/项目成员资格已变化/)
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

/** 组件 emit 的载荷形状（与 `DelegationApplyGroup` 同构，snake_case selector）。 */
function group(assignee: string, ids: string[], reviewer: string | null = null) {
  return {
    assigneeStaffId: assignee,
    assigneeName: `姓名-${assignee}`,
    reviewerStaffId: reviewer,
    selector: { kind: 'workpaper' as const, wp_index_ids: ids },
    wpCodes: ids.map((_, i) => `D2-${i + 1}`),
  }
}

function http409(detail: any) {
  return { response: { status: 409, data: { detail } } }
}

async function mountView() {
  mocks.getProcedures.mockResolvedValue([])
  mocks.initProcedures.mockResolvedValue([])
  mocks.listAssignments.mockResolvedValue([{ staff_id: 's1', role: 'auditor' }])
  mocks.listProjects.mockResolvedValue([{ id: 'project-1', project_name: '示例项目' }])
  mocks.fetchDelegationMemberLoads.mockResolvedValue({ s1: 2 })
  mocks.confirm.mockResolvedValue(true)
  const wrapper = mount(ProcedureTrimming, { global: { stubs } })
  await flushPromises()
  return wrapper
}

describe('判据 G — 行为级：逐组 preview → apply 且一组 409 不影响其他组', () => {
  beforeEach(() => vi.clearAllMocks())

  it('三组中间那组 409：另两组照旧落库，失败组标为需重新预览', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as any
    mocks.previewProcedureDelegation.mockResolvedValue({
      status: 'ready', preview_id: 'pv', summary: { targets: 3 },
    })
    mocks.applyProcedureDelegation
      .mockResolvedValueOnce({ applied: 3, unchanged: 0, conflict: 0 })
      .mockRejectedValueOnce(http409('目标任务版本已变化，请重新预览'))
      .mockResolvedValueOnce({ applied: 2, unchanged: 1, conflict: 0 })

    await vm.onSuggestionApplyRequest(
      [group('s1', ['w1', 'w2', 'w3']), group('s2', ['w4']), group('s3', ['w5', 'w6'])],
      [],
    )
    await flushPromises()

    // 三组都 preview 过、三组都尝试 apply（没有因中间失败而中断）
    expect(mocks.previewProcedureDelegation).toHaveBeenCalledTimes(3)
    expect(mocks.applyProcedureDelegation).toHaveBeenCalledTimes(3)

    const gs = vm.suggestApply.groups
    expect(gs.map((g: any) => g.status)).toEqual(['applied', 'stale', 'applied'])
    // 🔴 已成功组的计数不得被后来的失败抹掉
    expect(gs[0].applied).toBe(3)
    expect(gs[2].applied).toBe(2)
    expect(gs[1].applied).toBe(0)
    expect(gs[1].message).toContain('重新预览')
    expect(vm.suggestApplyTotals.applied).toBe(2)
    expect(vm.suggestApplyTotals.retryable).toBe(1)
    expect(vm.suggestApplyTotals.rows).toBe(5)
  })

  it('每组的 selector 用底稿粒度 wp_index_ids，且 preview 与 apply 的 body 逐字段相同', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as any
    mocks.previewProcedureDelegation.mockResolvedValue({
      status: 'ready', preview_id: 'pv-1', summary: { targets: 2 },
    })
    mocks.applyProcedureDelegation.mockResolvedValue({ applied: 2, unchanged: 0, conflict: 0 })

    await vm.onSuggestionApplyRequest([group('s1', ['w1', 'w2'], 's9')], [])
    await flushPromises()

    const [, pvBody] = mocks.previewProcedureDelegation.mock.calls[0]
    expect(pvBody.selector).toEqual({ kind: 'workpaper', wp_index_ids: ['w1', 'w2'] })
    expect(pvBody.assignee_staff_id).toBe('s1')
    expect(pvBody.reviewer_staff_id).toBe('s9')
    // apply 的第 4 参必须与 preview 的 body **深相等**（后端重算 hash 防篡改）
    const [, previewId, requestId, apBody] = mocks.applyProcedureDelegation.mock.calls[0]
    expect(previewId).toBe('pv-1')
    expect(String(requestId).length).toBeGreaterThan(0)
    expect(apBody).toEqual(pvBody)
  })

  it('summary.targets 为 0 时不调 apply（否则 applied:0 会被读成"委派成功"）', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as any
    mocks.previewProcedureDelegation.mockResolvedValue({
      status: 'ready', preview_id: 'pv-0', summary: { targets: 0 },
    })

    await vm.onSuggestionApplyRequest([group('s1', ['w1'])], [])
    await flushPromises()

    expect(mocks.previewProcedureDelegation).toHaveBeenCalledTimes(1)
    expect(mocks.applyProcedureDelegation, '零目标仍调 apply = 冒充成功').not.toHaveBeenCalled()
    const g0 = vm.suggestApply.groups[0]
    expect(g0.status).toBe('no_target')
    expect(g0.targets).toBe(0)
    expect(vm.suggestApplyStatusLabel(g0.status)).not.toContain('成功')
  })

  it('SOD 类 409 归为 sod（不建议重新预览），冲突类归为 assigned_conflict', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as any
    mocks.previewProcedureDelegation.mockResolvedValue({
      status: 'ready', preview_id: 'pv', summary: { targets: 1 },
    })
    mocks.applyProcedureDelegation
      .mockRejectedValueOnce(http409('职责分离冲突：同一人员不能同时是该任务的执行人与操作复核人'))
      .mockRejectedValueOnce(http409({
        error: 'delegation_conflict', message: '存在已被他人分配的目标任务', conflict_task_ids: ['t1'],
      }))

    await vm.onSuggestionApplyRequest([group('s1', ['w1'], 's1'), group('s2', ['w2'])], [])
    await flushPromises()

    const gs = vm.suggestApply.groups
    expect(gs[0].status).toBe('sod')
    expect(gs[0].message).toContain('重新预览无效')
    expect(gs[1].status).toBe('assigned_conflict')
    expect(vm.suggestApplyTotals.blocked).toBe(2)
    expect(vm.suggestApplyTotals.retryable, 'SOD/冲突不该被算成"重新预览就能好"').toBe(0)
  })

  it('单组重试只动该组，已成功组的计数保持不变', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as any
    mocks.previewProcedureDelegation.mockResolvedValue({
      status: 'ready', preview_id: 'pv', summary: { targets: 1 },
    })
    mocks.applyProcedureDelegation
      .mockResolvedValueOnce({ applied: 4, unchanged: 0, conflict: 0 })
      .mockRejectedValueOnce(http409('预览凭证已过期'))

    await vm.onSuggestionApplyRequest([group('s1', ['w1']), group('s2', ['w2'])], [])
    await flushPromises()
    expect(vm.suggestApply.groups.map((g: any) => g.status)).toEqual(['applied', 'stale'])

    mocks.applyProcedureDelegation.mockResolvedValueOnce({ applied: 1, unchanged: 0, conflict: 0 })
    await vm.retrySuggestionGroup(1)
    await flushPromises()

    const gs = vm.suggestApply.groups
    expect(gs.length, '重试不得重建 groups 数组').toBe(2)
    expect(gs[0].applied, '已成功组的计数被抹掉了').toBe(4)
    expect(gs[0].status).toBe('applied')
    expect(gs[1].status).toBe('applied')
    expect(gs[1].applied).toBe(1)
  })

  it('确认框被取消时一个请求都不发（不能先发再问）', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as any
    mocks.confirm.mockRejectedValueOnce(new Error('cancel'))
    await vm.onSuggestionApplyRequest([group('s1', ['w1'])], [])
    await flushPromises()
    expect(mocks.previewProcedureDelegation).not.toHaveBeenCalled()
    expect(mocks.applyProcedureDelegation).not.toHaveBeenCalled()
    expect(vm.suggestApply.groups.length).toBe(0)
  })

  it('不借用底稿主编层的 assignProcedures（双真源）', async () => {
    const wrapper = await mountView()
    const vm = wrapper.vm as any
    mocks.previewProcedureDelegation.mockResolvedValue({
      status: 'ready', preview_id: 'pv', summary: { targets: 1 },
    })
    mocks.applyProcedureDelegation.mockResolvedValue({ applied: 1, unchanged: 0, conflict: 0 })
    await vm.onSuggestionApplyRequest([group('s1', ['w1'])], [])
    await flushPromises()
    expect(mocks.assignProcedures).not.toHaveBeenCalled()
  })
})
