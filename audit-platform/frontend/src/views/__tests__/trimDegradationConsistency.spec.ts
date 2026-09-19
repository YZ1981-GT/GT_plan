/**
 * 降级标注与实际执行一致性守卫（Property 12 / R4.1 / R4.2 / R4.5 / R14.7）。
 *
 * spec: procedure-trimming-and-delegation-intelligence — Task 22
 * 变异脚本: `backend/scripts/check/mutate_trim_decision_guards.py`（M12A / M12B / M12C）
 *
 * ## 它防的是「假装做了联动」
 *
 * 裁剪有三个法定判据维度（风险评估 / 重要性 / 数据存在性）。任一维度数据缺失时，
 * 平台必须**整体跳过该维度并如实告知**，而不是用默认值把它糊过去。危险不在于
 * 「跳过」—— 数据确实没有，跳过是唯一诚实的选择；危险在于**跳过了却不说**：
 * 审计师会以为这份裁剪结论已经过风险与重要性的检验，从而放弃自己动手复核。
 *
 * 所以判据必须是**双向**的（design.md Property 12）：
 *
 * - 标注含 `materiality` ⟺ 该次决策集合中不存在重要性类 `reasonCode`
 * - 标注含 `risk`        ⟺ 不存在因风险保护而 `keep` 的项
 *
 * ## 🔴 ⟺ 极易写成「两边都空」的恒真断言
 *
 * 若 fixture 里压根不会产生重要性类理由码（例如所有科目金额都远高于阈值），那么
 * 「无重要性类理由码」恒成立，于是不论标注在不在，`⟺` 的一半都自动为真 —— 守卫
 * 全绿而什么都没证明。故本文件的构造方式是**成对**的：**同一份科目金额与同一份
 * 风险数据**，只切换该维度的可用性，两个 arm 都断言等价关系，并额外断言
 *
 * - 「维度可用」那一 arm 里该类**确实出现**（`count > 0`）
 * - 「维度不可用」那一 arm 里该类**确实消失**（`count === 0`）
 *
 * 两条非空性断言就是本文件的非恒真保证（`describe('非恒真自检')`）：把它们删掉，
 * `⟺` 立刻退化成可以用空集满足的形式。
 *
 * ## 本轮修掉的真缺陷：标注的门控与它的内容互斥
 *
 * 落地前，降级标注嵌在建议态条 `v-if="suggestionStats.suggested > 0"` 内部。而
 * 「未做重要性联动」这条标注**存在的前提**就是重要性维度不可用 ⇒ 该维度不产生
 * 任何建议 ⇒ `suggested === 0` ⇒ 宿主整块不渲染 ⇒ 该标注在它唯一该出现的场景下
 * **永远不显示**。风险那条同理，只在「风险缺失但重要性可用且恰好有建议」时偶然
 * 可见。同族于 Task 13 定性的「`loadTrimContext` 零调用点 ⇒ 降级标注从未渲染」——
 * 那次是数据源never写入，这次是门控条件与内容互斥。两次都四层检查全绿。
 *
 * 故本文件的断言落在**两个层次**上，缺一不可：
 * - `vm.degradationNotes`（计算结果）—— 抓「维度判断错」
 * - 真实 DOM 里 `.gt-proc-degrade-bar` 的文本 —— 抓「算对了但用户看不到」
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import * as fs from 'node:fs'
import * as path from 'node:path'

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
  fetchTrimNoteLinkage: vi.fn(),
  applyTrimNoteLinkage: vi.fn(),
  listAssignments: vi.fn(),
  listWorkpapersPaged: vi.fn(),
  httpGet: vi.fn(),
  httpPost: vi.fn(),
  confirm: vi.fn(),
  alert: vi.fn(),
  msgSuccess: vi.fn(),
  msgWarning: vi.fn(),
  msgInfo: vi.fn(),
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
  fetchTrimNoteLinkage: mocks.fetchTrimNoteLinkage,
  applyTrimNoteLinkage: mocks.applyTrimNoteLinkage,
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
    { success: mocks.msgSuccess, warning: mocks.msgWarning, error: vi.fn(), info: mocks.msgInfo },
  ),
  ElMessageBox: {
    confirm: mocks.confirm,
    prompt: vi.fn().mockResolvedValue({ value: 'x' }),
    alert: mocks.alert,
  },
}))

import ProcedureTrimming from '../ProcedureTrimming.vue'

// ═══════════════════════════════════════════════════════════════════════════
// 源码扫描面（宿主门控的源码级判据）
// ═══════════════════════════════════════════════════════════════════════════

function repoRoot(): string {
  let dir = __dirname
  for (let i = 0; i < 14; i += 1) {
    const a = path.join(dir, 'audit-platform', 'frontend', 'package.json')
    const b = path.join(dir, 'backend', 'app', 'main.py')
    if (fs.existsSync(a) && fs.existsSync(b)) return dir
    dir = path.dirname(dir)
  }
  throw new Error('repoRoot 未找到（双哨兵）')
}

const ROOT = repoRoot()
const P_VUE = path.join(ROOT, 'audit-platform', 'frontend', 'src', 'views', 'ProcedureTrimming.vue')
const P_CTX_PY = path.join(ROOT, 'backend', 'app', 'services', 'trim_decision_context.py')
const RAW = fs.readFileSync(P_VUE, 'utf-8').replace(/\r\n/g, '\n')

/** 剥 HTML 注释（模板判据必须剥 —— 实现里刻意在注释中保留了反例字样作缺陷留痕）。 */
function stripHtmlComments(src: string): string {
  return src.replace(/<!--[\s\S]*?-->/g, '')
}

/**
 * 取 `<template>` 区：`<script setup` 之前的**最后一个** `</template>`。
 *
 * 🔴 不能取第一个 —— 本 SFC 有 20+ 个嵌套 `<template #default>` 插槽，第一个闭合
 * 标签在 L175 左右，按它切只得 ~4% 模板，判据会在绝大部分模板上空转恒绿
 * （Task 13 实证的守卫缺陷之一）。
 */
function templateSegment(src: string): string {
  const scriptAt = src.indexOf('<script setup')
  const head = scriptAt < 0 ? src : src.slice(0, scriptAt)
  const close = head.lastIndexOf('</template>')
  return close < 0 ? head : head.slice(head.indexOf('<template>'), close)
}

function styleSegment(src: string): string {
  const m = src.match(/<style[^>]*>([\s\S]*?)<\/style>/)
  return m ? m[1] : ''
}

const TPL = stripHtmlComments(templateSegment(RAW))
const STY = styleSegment(RAW)

/**
 * 取 needle 所在 `<div>` 元素的整块（按缩进边界，够用且不依赖 HTML 解析器）。
 *
 * 🔴 needle 必须落在**目标元素自己的开标签行**上。写成 `'gt-proc-suggest-bar__head'`
 * 会命中**内层** `<div class="gt-proc-suggest-bar__head">`，于是 `lastIndexOf('<div')`
 * 取到内层开标签、截出来的"块"只有 head 一小段 —— 那时「块内不含 degradationNotes」
 * 恒成立，判据在最该承重的地方空转。故一律用带引号的完整属性片段
 * （`class="gt-proc-suggest-bar"`）作 needle，并由下方 helper 自检钉死该差异。
 */
function divBlockContaining(tpl: string, needle: string): string {
  const at = tpl.indexOf(needle)
  if (at < 0) return ''
  const openAt = tpl.lastIndexOf('<div', at)
  if (openAt < 0) return ''
  const indent = (() => {
    const lineStart = tpl.lastIndexOf('\n', openAt) + 1
    return tpl.slice(lineStart, openAt)
  })()
  const closer = `\n${indent}</div>`
  const end = tpl.indexOf(closer, openAt)
  return end < 0 ? tpl.slice(openAt) : tpl.slice(openAt, end + closer.length)
}

// ═══════════════════════════════════════════════════════════════════════════
// mount 装置
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
  GtTrimAdequacyReview: { template: '<div class="review-stub" />' },
}

/**
 * D 循环三个程序，程序名各含一个科目名（`resolveAccountName` 按名字最长匹配）。
 *
 * 三条都是 `execute`（applicable），故都会真的进 `decideTrim`。
 */
const PROC_ROWS = [
  { id: '1', wp_code: 'D2-1', procedure_code: 'D2-1-01', procedure_name: '应收账款函证程序', status: 'execute' },
  { id: '2', wp_code: 'D3-1', procedure_code: 'D3-1-01', procedure_name: '合同资产检查程序', status: 'execute' },
  { id: '3', wp_code: 'D4-1', procedure_code: 'D4-1-01', procedure_name: '主营业务收入截止测试', status: 'execute' },
]

/**
 * 三个科目的余额**在全部 arm 中固定不变**。
 *
 * 🔴 这是「非恒真」的关键：金额低于实际执行重要性（500,000）而高于明显微小错报
 * 临界值（25,000）⇒ 重要性维度可用时必产 `below_materiality`。若把金额调到阈值
 * 之上，两个 arm 都不会有重要性类理由码，`⟺` 就退化成恒真了。
 */
const ACCOUNTS = {
  应收账款: { amount: 120_000, cycle: 'D' },
  合同资产: { amount: 88_000, cycle: 'D' },
  主营业务收入: { amount: 310_000, cycle: 'D' },
}

const MATERIALITY = { performance_materiality: 500_000, trivial_threshold: 25_000 }

/** B50 已评估：应收账款的重大错报风险为高 ⇒ 档 1 风险保护必命中。 */
const RISK_PRESENT = {
  应收账款: {
    max_risk: 'H',
    has_special: false,
    cells: { completeness: { rmm: 'M', special: false } },
    approach: 'combined',
    reliance: '是',
  },
}

interface CtxArm {
  materiality: typeof MATERIALITY | null
  risk: Record<string, any>
  risk_dimension_available: boolean
  degradations: { dimension: string; reason: string; cause?: string }[]
}

async function mountWithContext(arm: CtxArm) {
  mocks.getProcedures.mockResolvedValue(JSON.parse(JSON.stringify(PROC_ROWS)))
  mocks.initProcedures.mockResolvedValue(JSON.parse(JSON.stringify(PROC_ROWS)))
  mocks.listAssignments.mockResolvedValue([{ staff_id: 's1', role: 'auditor' }])
  mocks.listProjects.mockResolvedValue([{ id: 'project-1', project_name: '示例项目' }])
  mocks.fetchDelegationMemberLoads.mockResolvedValue({ s1: 2 })
  mocks.fetchB50RiskRows.mockResolvedValue([])
  mocks.fetchCompletenessScopeOverrides.mockResolvedValue([])
  mocks.fetchTrimNoteLinkage.mockResolvedValue(null)
  mocks.fetchTrimDecisionContext.mockResolvedValue({
    accounts: JSON.parse(JSON.stringify(ACCOUNTS)),
    materiality: arm.materiality,
    risk: arm.risk,
    risk_dimension_available: arm.risk_dimension_available,
    // 完整性豁免固定为「项目已确认不敏感」——否则 D 循环平台默认敏感会在档 5
    // 短路掉重要性判据，重要性那一对 arm 就永远看不到 below_materiality。
    completeness_override: { D: false },
    workpaper_entry: {},
    degradations: arm.degradations,
  })
  mocks.httpGet.mockResolvedValue({ data: { data: { subject_with_data: [], subject_no_data: [] } } })
  mocks.confirm.mockResolvedValue(true)
  mocks.alert.mockResolvedValue(true)
  const wrapper = mount(ProcedureTrimming, { global: { stubs } })
  await flushPromises()
  return wrapper
}

/** 跑一次当前循环的智能裁剪（内存态，不落库）。 */
async function runSmartTrim(vm: any) {
  vm.smartTrimScope = 'current'
  await vm.confirmSmartTrim()
  await flushPromises()
}

const MATERIALITY_CODES = new Set(['below_trivial', 'below_materiality'])

/** 结果集里重要性类理由码的条数。 */
function materialityClassCount(vm: any): number {
  return vm.procedures.filter((p: any) => MATERIALITY_CODES.has(String(p._suggestReasonCode ?? ''))).length
}

/** 结果集里「因风险保护而 keep」的条数（判据 = evidence 记录的档位）。 */
function riskProtectedCount(vm: any): number {
  return vm.procedures.filter((p: any) => p._decisionEvidence?.decidedBy === 'risk_protection').length
}

/**
 * 因风险保护而 keep 的项无法从 `_decisionEvidence` 读到（该字段只在建议态写入），
 * 故对 keep 侧改用**重跑同一决策内核**取 evidence —— 与页面用的是同一个函数、
 * 同一份上下文，不是第二套判据。
 */
function decisionsOf(vm: any): any[] {
  const ctx = vm.trimContext
  if (!ctx) return []
  return vm.procedures.map((p: any) => vm.buildAndDecide(p, ctx, vm.subjectWithData, vm.subjectNoData))
}

function keptByRiskCount(vm: any): number {
  return decisionsOf(vm).filter(
    (d: any) => d.verdict === 'keep' && d.evidence?.decidedBy === 'risk_protection',
  ).length
}

function reasonCodesOf(vm: any): string[] {
  return decisionsOf(vm).map((d: any) => String(d.reasonCode ?? '')).filter(Boolean)
}

/** 标注（计算结果层）里出现的维度集合。 */
function noticeDimensions(vm: any): Set<string> {
  return new Set((vm.degradationNotes || []).map((d: any) => String(d.dimension)))
}

/** 标注（DOM 层）—— 抓「算对了但用户看不到」。 */
function noticeDomText(wrapper: any): string {
  const bar = wrapper.find('.gt-proc-degrade-bar')
  return bar.exists() ? bar.text() : ''
}

// ═══════════════════════════════════════════════════════════════════════════
// helper 自检
// ═══════════════════════════════════════════════════════════════════════════
describe('helper 自检', () => {
  it('模板切分取「script setup 之前的最后一个 </template>」而非第一个', () => {
    const naive = RAW.slice(RAW.indexOf('<template>'), RAW.indexOf('</template>'))
    expect(TPL.length, '正确切法应显著长于朴素切法（本 SFC 有大量嵌套插槽 template）')
      .toBeGreaterThan(naive.length * 2)
    expect(TPL, '模板段应含循环 Tab 条').toContain('gt-proc-cycle-bar')
  })

  it('stripHtmlComments 真的生效（原文含反例字样、剥后不含）', () => {
    const rawTpl = templateSegment(RAW)
    expect(rawTpl, '实现里应在注释中留下缺陷成因说明').toContain('条件与内容互斥')
    expect(TPL, '剥注释后不应再含注释里的说明文字').not.toContain('条件与内容互斥')
  })

  it('divBlockContaining 能截出 v-if 所在整块', () => {
    const block = divBlockContaining(TPL, 'class="gt-proc-degrade-bar"')
    expect(block, '未截到降级标注块').not.toBe('')
    expect(block).toContain('degradationNotes')
    expect(block, '未截到该块的 v-if 门控').toContain('v-if=')
    expect(block.length, '截出的块过长，边界可疑（可能吞了后面的建议态条）').toBeLessThan(1200)
  })

  it('🔴 helper 自检：needle 落在内层 div 上会截出错误的块（本文件首轮踩到过）', () => {
    const outer = divBlockContaining(TPL, 'class="gt-proc-suggest-bar"')
    const inner = divBlockContaining(TPL, 'class="gt-proc-suggest-bar__head"')
    expect(outer, '未截到建议态条外层块').not.toBe('')
    expect(inner, '未截到 head 内层块').not.toBe('')
    // 外层必须含门控、内层必然不含 —— 若两者相同说明 needle 选取规则失效
    expect(outer).toContain('v-if="suggestionStats.suggested > 0"')
    expect(inner, '内层 head 不该有门控（证明 needle 选错会让判据空转）')
      .not.toContain('v-if="suggestionStats.suggested > 0"')
    expect(outer.length, '外层块应显著长于内层 head').toBeGreaterThan(inner.length)
  })

  it('扫描面非空自检', () => {
    expect(RAW.length).toBeGreaterThan(100_000)
    expect(STY.length, '未截到 <style> 段').toBeGreaterThan(2000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 A：标注必须有**独立**渲染宿主（门控不得与内容互斥）
// ═══════════════════════════════════════════════════════════════════════════
describe('[A] 降级标注的渲染宿主独立于建议态条', () => {
  it('存在独立宿主，且只由 degradationNotes.length 门控', () => {
    const block = divBlockContaining(TPL, 'class="gt-proc-degrade-bar"')
    expect(block, '降级标注没有独立宿主').not.toBe('')
    expect(block, '独立宿主的门控应是 degradationNotes.length').toMatch(
      /v-if="degradationNotes\.length\s*>\s*0"/,
    )
    expect(
      block,
      '独立宿主内不得再引用 suggestionStats —— 那会重新把标注挂在「有建议」这个前提上',
    ).not.toContain('suggestionStats')
  })

  it('🔴 标注块不得嵌在 suggestionStats.suggested > 0 的宿主内（条件与内容互斥）', () => {
    const suggestBar = divBlockContaining(TPL, 'class="gt-proc-suggest-bar"')
    expect(suggestBar, '未截到建议态条').not.toBe('')
    expect(suggestBar, '建议态条的门控应是 suggested > 0').toMatch(
      /v-if="suggestionStats\.suggested\s*>\s*0"/,
    )
    // 扫描面非空自检：必须真的截到了条体（否则下一条 not.toContain 恒真）
    expect(suggestBar, '截出的建议态条不含汇总闸说明，边界可疑').toContain('aggregateGate.narrative')
    expect(
      suggestBar,
      '降级标注仍嵌在建议态条内 —— 「未做重要性联动」这条在它唯一该出现的场景下 suggested 恒为 0，永远不显示',
    ).not.toContain('degradationNotes')
  })

  it('宿主用到的 scoped 类在 <style> 里真有样式（带定界符，防子串误判）', () => {
    for (const cls of ['gt-proc-degrade-bar', 'gt-proc-degrade-bar__label']) {
      expect(
        new RegExp('\\.' + cls.replace(/[-_]/g, '[-_]') + '(?![\\w-])').test(STY),
        `模板用到 .${cls} 但 <style> 里没有它的样式（缺类不报错、只表现为无视觉分层）`,
      ).toBe(true)
    }
  })

  it('反向自检：带定界符的类名判据不会被更长的类名骗过', () => {
    const fake = '.gt-proc-degrade-barX { color: red; }'
    expect(/\.gt-proc-degrade-bar(?![\w-])/.test(fake), '定界符失效').toBe(false)
    expect(/\.gt-proc-degrade-bar(?![\w-])/.test('.gt-proc-degrade-bar {}')).toBe(true)
  })

  it('维度措辞映射的键与后端维度常量取值域交叉锁死', () => {
    const py = fs.readFileSync(P_CTX_PY, 'utf-8')
    const dims = [...py.matchAll(/^DIM_[A-Z_]+\s*=\s*"([a-z_]+)"/gm)].map((m) => m[1])
    expect(dims.length, '未从后端抽出任何 DIM_* 常量（判据失效）').toBeGreaterThan(3)
    const scriptAt = RAW.indexOf('<script setup')
    const script = RAW.slice(scriptAt)
    const fn = script.slice(script.indexOf('function degradationText'))
    const body = fn.slice(0, fn.indexOf('\n}\n') + 3)
    expect(body, '未截到 degradationText 函数体').toContain('dim ===')
    const used = [...body.matchAll(/dim === '([a-z_]+)'/g)].map((m) => m[1])
    expect(used.length, '未抽出任何维度分支').toBeGreaterThan(3)
    for (const d of used) {
      expect(dims, `前端 degradationText 的分支键 '${d}' 不在后端 DIM_* 取值域内（该分支永不命中）`)
        .toContain(d)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 B：重要性维度 —— 双向等价，成对构造
// ═══════════════════════════════════════════════════════════════════════════
describe('[B] Property 12 · 重要性：标注含 materiality ⟺ 结果集无重要性类 reasonCode', () => {
  beforeEach(() => vi.clearAllMocks())

  it('arm1 重要性可用：标注不含 materiality，且重要性类理由码确实出现', async () => {
    const wrapper = await mountWithContext({
      materiality: MATERIALITY,
      risk: {},
      risk_dimension_available: false,
      degradations: [{ dimension: 'risk', reason: 'B50 未填写' }],
    })
    const vm = wrapper.vm as any
    await runSmartTrim(vm)

    const dims = noticeDimensions(vm)
    const count = materialityClassCount(vm)
    expect(dims.has('materiality'), '重要性可用却标注了「未做重要性联动」').toBe(false)
    expect(count, '重要性可用且金额低于阈值时必须产生重要性类建议（否则本组判据恒真）')
      .toBeGreaterThan(0)
    // 双向等价：标注含 materiality ⟺ 无重要性类理由码
    expect(dims.has('materiality')).toBe(count === 0)
  })

  it('arm2 重要性不可用：标注含 materiality，且重要性类理由码确实为零', async () => {
    const wrapper = await mountWithContext({
      materiality: null,
      risk: {},
      risk_dimension_available: false,
      degradations: [
        { dimension: 'materiality', reason: '本项目未确定重要性水平' },
        { dimension: 'risk', reason: 'B50 未填写' },
      ],
    })
    const vm = wrapper.vm as any
    await runSmartTrim(vm)

    const dims = noticeDimensions(vm)
    const count = materialityClassCount(vm)
    expect(dims.has('materiality'), '重要性不可用却没有标注（= 静默跳过一个法定判据维度）').toBe(true)
    expect(count, '标注说没做重要性联动，结果集里却有重要性类理由码（自相矛盾）').toBe(0)
    expect(reasonCodesOf(vm).filter((c) => MATERIALITY_CODES.has(c)), '决策内核侧也不得产出重要性类理由码')
      .toEqual([])
    expect(dims.has('materiality')).toBe(count === 0)
  })

  it('arm2 的标注真的渲染到 DOM（不是只算对了）', async () => {
    const wrapper = await mountWithContext({
      materiality: null,
      risk: {},
      risk_dimension_available: false,
      degradations: [{ dimension: 'materiality', reason: '本项目未确定重要性水平' }],
    })
    const vm = wrapper.vm as any
    await runSmartTrim(vm)
    expect(vm.suggestionStats.suggested, '构造前提：重要性不可用时建议数为 0').toBe(0)
    const text = noticeDomText(wrapper)
    expect(text, '降级标注块未渲染（宿主被「有建议」门控挡住了）').not.toBe('')
    expect(text, 'DOM 里未出现「未做重要性联动」措辞').toContain('未做重要性联动')
  })

  it('arm1 的 DOM 不出现重要性那条措辞（反向，防标注恒显）', async () => {
    const wrapper = await mountWithContext({
      materiality: MATERIALITY,
      risk: {},
      risk_dimension_available: false,
      degradations: [{ dimension: 'risk', reason: 'B50 未填写' }],
    })
    const vm = wrapper.vm as any
    await runSmartTrim(vm)
    const text = noticeDomText(wrapper)
    expect(text, '风险那条应渲染').toContain('未做风险联动')
    expect(text, '重要性可用却渲染了「未做重要性联动」').not.toContain('未做重要性联动')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 C：风险维度 —— 双向等价，成对构造
// ═══════════════════════════════════════════════════════════════════════════
describe('[C] Property 12 · 风险：标注含 risk ⟺ 无因风险保护而 keep 的项', () => {
  beforeEach(() => vi.clearAllMocks())

  it('arm1 风险可用：标注不含 risk，且确实有项因风险保护而 keep', async () => {
    const wrapper = await mountWithContext({
      materiality: MATERIALITY,
      risk: JSON.parse(JSON.stringify(RISK_PRESENT)),
      risk_dimension_available: true,
      degradations: [],
    })
    const vm = wrapper.vm as any
    await runSmartTrim(vm)

    const dims = noticeDimensions(vm)
    const kept = keptByRiskCount(vm)
    expect(dims.has('risk'), '风险可用却标注了「未做风险联动」').toBe(false)
    expect(kept, '应收账款的重大错报风险为高，必须有项因风险保护而 keep（否则本组判据恒真）')
      .toBeGreaterThan(0)
    expect(dims.has('risk')).toBe(kept === 0)
  })

  it('arm1 风险保护确实压住了金额判据（同一科目金额低于实际执行重要性）', async () => {
    const wrapper = await mountWithContext({
      materiality: MATERIALITY,
      risk: JSON.parse(JSON.stringify(RISK_PRESENT)),
      risk_dimension_available: true,
      degradations: [],
    })
    const vm = wrapper.vm as any
    await runSmartTrim(vm)
    const ar = vm.procedures.find((p: any) => p.wp_code === 'D2-1')
    expect(ar, '未找到应收账款那条程序').toBeTruthy()
    expect(ar._suggest, '高风险科目金额虽低于实际执行重要性也不得进建议态').not.toBe(true)
    // 其余两个科目没有风险数据 ⇒ 仍按金额产生建议（证明压制是针对性的、不是全局关闭）
    expect(materialityClassCount(vm), '无风险数据的科目仍应按金额产生建议').toBeGreaterThan(0)
  })

  it('arm2 风险不可用：标注含 risk，且无任何项因风险保护而 keep', async () => {
    const wrapper = await mountWithContext({
      materiality: MATERIALITY,
      risk: {},
      risk_dimension_available: false,
      degradations: [{ dimension: 'risk', reason: 'B50 认定层次风险矩阵未填写' }],
    })
    const vm = wrapper.vm as any
    await runSmartTrim(vm)

    const dims = noticeDimensions(vm)
    const kept = keptByRiskCount(vm)
    expect(dims.has('risk'), '风险不可用却没有标注').toBe(true)
    expect(kept, '标注说没做风险联动，却有项因风险保护而 keep（自相矛盾）').toBe(0)
    // evidence 侧同样不得伪装成已评估
    for (const d of decisionsOf(vm)) {
      expect(d.evidence.maxRisk, '风险维度不可用时不得给出风险等级').toBeNull()
      expect(d.evidence.risk_unknown, '风险维度不可用时应留 risk_unknown 痕迹').toBe(true)
    }
    expect(dims.has('risk')).toBe(kept === 0)
  })

  it('arm2 的 DOM 出现风险那条措辞', async () => {
    const wrapper = await mountWithContext({
      materiality: MATERIALITY,
      risk: {},
      risk_dimension_available: false,
      degradations: [{ dimension: 'risk', reason: 'B50 认定层次风险矩阵未填写' }],
    })
    const vm = wrapper.vm as any
    await runSmartTrim(vm)
    expect(noticeDomText(wrapper)).toContain('未做风险联动')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 判据 D：非恒真自检 —— 把这一组删掉，⟺ 就退化成可用空集满足
// ═══════════════════════════════════════════════════════════════════════════
describe('[D] 非恒真自检：两个方向各有一组真正起判别作用的输入', () => {
  beforeEach(() => vi.clearAllMocks())

  it('重要性方向：同一份金额下，仅切换可用性就让重要性类理由码从有变无', async () => {
    const w1 = await mountWithContext({
      materiality: MATERIALITY,
      risk: {},
      risk_dimension_available: false,
      degradations: [{ dimension: 'risk', reason: 'x' }],
    })
    await runSmartTrim(w1.vm as any)
    const withMat = materialityClassCount(w1.vm as any)

    vi.clearAllMocks()
    const w2 = await mountWithContext({
      materiality: null,
      risk: {},
      risk_dimension_available: false,
      degradations: [
        { dimension: 'materiality', reason: 'x' },
        { dimension: 'risk', reason: 'x' },
      ],
    })
    await runSmartTrim(w2.vm as any)
    const withoutMat = materialityClassCount(w2.vm as any)

    expect(withMat, '可用侧必须 > 0').toBeGreaterThan(0)
    expect(withoutMat, '不可用侧必须 === 0').toBe(0)
    expect(
      withMat !== withoutMat,
      '两侧计数相同 ⇒ 该维度的 ⟺ 断言实际上是恒真的（fixture 不产生该类）',
    ).toBe(true)
  })

  it('风险方向：同一份风险数据下，仅切换可用性就让风险保护从有变无', async () => {
    const w1 = await mountWithContext({
      materiality: MATERIALITY,
      risk: JSON.parse(JSON.stringify(RISK_PRESENT)),
      risk_dimension_available: true,
      degradations: [],
    })
    await runSmartTrim(w1.vm as any)
    const withRisk = keptByRiskCount(w1.vm as any)

    vi.clearAllMocks()
    const w2 = await mountWithContext({
      materiality: MATERIALITY,
      risk: {},
      risk_dimension_available: false,
      degradations: [{ dimension: 'risk', reason: 'x' }],
    })
    await runSmartTrim(w2.vm as any)
    const withoutRisk = keptByRiskCount(w2.vm as any)

    expect(withRisk, '可用侧必须 > 0').toBeGreaterThan(0)
    expect(withoutRisk, '不可用侧必须 === 0').toBe(0)
    expect(
      withRisk !== withoutRisk,
      '两侧计数相同 ⇒ 风险方向的 ⟺ 断言实际上是恒真的',
    ).toBe(true)
  })

  it('标注不是恒显也不是恒隐（两个 arm 的 DOM 文本必须不同）', async () => {
    const w1 = await mountWithContext({
      materiality: MATERIALITY,
      risk: JSON.parse(JSON.stringify(RISK_PRESENT)),
      risk_dimension_available: true,
      degradations: [],
    })
    await runSmartTrim(w1.vm as any)
    const t1 = noticeDomText(w1)

    vi.clearAllMocks()
    const w2 = await mountWithContext({
      materiality: null,
      risk: {},
      risk_dimension_available: false,
      degradations: [
        { dimension: 'materiality', reason: 'x' },
        { dimension: 'risk', reason: 'x' },
      ],
    })
    await runSmartTrim(w2.vm as any)
    const t2 = noticeDomText(w2)

    expect(t1, '三维全可用时不应有任何降级标注').toBe('')
    expect(t2.length, '两维不可用时应有标注').toBeGreaterThan(0)
    expect(t1).not.toBe(t2)
  })
})
