/**
 * P17 第三写入方定序 —— D1-16「同步到D1-4」在 OO 会话期间不得直写 store。
 *
 * spec: d1-sync-row-table-engine-and-d1-coverage · Task 26 子目标 ② · 需求 5.7
 *
 * ═══ 为什么这条是必须的 ═══
 *
 * `D1-bd-portfolio-rows` 接 sync 之后有**三个**写入方：
 *   ① D1-4 自己的 HTML 保存  ② OO 回写（extract/merge）  ③ D1-16 的「同步到D1-4」
 * ③ 绕过 sync 的 CAS 直接改 store ⇒ 与已 materialize 的产物分叉：
 * 下次 extract 反读到非预期值（roundtrip 门红），或本次直写被 OO 合并结果静默覆盖。
 *
 * 🔴 **分叉窗口真实可达，不是理论风险**：宿主有**两个独立的 mode 源** ——
 * D1-3 走 `syncBridge`、其余 sheet 走 `useD1EntryDualMode`。在 D1-3 切到「在线编辑」
 * （`syncBridge.mode='oo'`）后导航到 D1-16，`renderMode` 读的是 `dualMode.mode`（仍 `html`）
 * ⇒ D1-16 的 HTML 表单正常渲染，**而 OO 会话还开着**。
 *
 * ═══ 判据分两层 ═══
 * 1. **行为层**（真调 composable）：拒绝时返回带中文原因的结果，且 store 与 saveImmediate
 *    **一个都不能动** —— 只验「返回了 false」不够，静默直写恰恰是返回值之外的副作用。
 * 2. **源码守卫**（零挂载、防回退）：宿主真的把 entry 级信号传下来了、tab 真的接进了
 *    composable、`.vue` 真的按返回值分支（不再无条件报成功）。
 */
import { describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ref } from 'vue'

import { useD1WriteoffCheck } from '../useD1WriteoffCheck'
import type { ReversalRow, WriteoffRow } from '../useD1WriteoffCheck'

const D14_PORTFOLIO_KEY = 'D1-bd-portfolio-rows'

const SRC_DIR = resolve(__dirname, '../..')
const HOST_SRC = readFileSync(resolve(SRC_DIR, 'GtD1NotesReceivable.vue'), 'utf-8')
const TAB_SRC = readFileSync(resolve(SRC_DIR, 'd1/D1TabWriteoffCheck.vue'), 'utf-8')

function reversal(amount: number): ReversalRow {
  return {
    id: 'r1', unitName: '甲公司', reason: '收回', recoveryMethod: '现金收回',
    originalBasis: '账龄', reversalAmount: amount, priorProvisionAmount: amount + 100,
    reasonabilityAnalysis: '合理', indexRef: '',
  }
}

function writeoff(amount: number): WriteoffRow {
  return {
    id: 'w1', unitName: '乙公司', noteNature: '商业承兑汇票', writeoffAmount: amount,
    writeoffReason: '无法收回', writeoffProcedure: '已审批',
    isRelatedPartyGenerated: '否', reasonabilityAnalysis: '合理', indexRef: '',
  }
}

function setup(opts: { oo?: boolean; readonly?: boolean } = {}) {
  const map = new Map<string, any>([
    ['D1-writeoff-reversal-rows', {
      item_id: 'D1-writeoff-reversal-rows', conclusion: null,
      remark: JSON.stringify([reversal(777)]),
    }],
    ['D1-writeoff-writeoff-rows', {
      item_id: 'D1-writeoff-writeoff-rows', conclusion: null,
      remark: JSON.stringify([writeoff(555)]),
    }],
  ])
  const allResponses = ref(map)
  const saveImmediate = vi.fn().mockResolvedValue(undefined)
  const ooSessionActive = ref(opts.oo ?? false)
  const api = useD1WriteoffCheck({
    allResponses: allResponses as any,
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    saveImmediate,
    saveDebouncedText: vi.fn(),
    isReadonly: ref(opts.readonly ?? false),
    ooSessionActive,
  })
  return { api, allResponses, saveImmediate, ooSessionActive }
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. 行为层：OO 会话期间被拒，且不得留下任何副作用
// ═══════════════════════════════════════════════════════════════════════════

describe('P17 行为层：OO 会话期间拒绝跨 sheet 直写', () => {
  // 🔴 两个入口都必须覆盖：只测一个就允许「改一半」——另一条路照样静默直写
  const entries: Array<['syncReversalToD14' | 'syncWriteoffToD14', string]> = [
    ['syncReversalToD14', '转回'],
    ['syncWriteoffToD14', '核销'],
  ]

  it.each(entries)('%s 在 OO 会话中返回可见中文原因', (fn) => {
    const { api } = setup({ oo: true })
    const res = (api as any)[fn]() as { ok: boolean; reason?: string }
    expect(res.ok).toBe(false)
    expect(res.reason).toBeTruthy()
    // 原因必须是**给人看的中文**，且点名「在线编辑」与「D1-4」两个用户可识别的名词
    expect(res.reason).toMatch(/[\u4e00-\u9fa5]/)
    expect(res.reason).toContain('在线编辑')
    expect(res.reason).toContain('D1-4')
  })

  it.each(entries)('%s 在 OO 会话中**不得**留下任何副作用（这才是要堵的）', (fn) => {
    const { api, allResponses, saveImmediate } = setup({ oo: true })
    const before = new Map(allResponses.value)
    ;(api as any)[fn]()
    // store 不得出现 D1-4 的键
    expect(allResponses.value.has(D14_PORTFOLIO_KEY)).toBe(false)
    // 整个 map 逐键不变（防「写了别的键」这种绕过）
    expect([...allResponses.value.keys()].sort()).toEqual([...before.keys()].sort())
    for (const [k, v] of before) expect(allResponses.value.get(k)).toBe(v)
    // 不得发起持久化
    expect(saveImmediate).not.toHaveBeenCalled()
  })

  it.each(entries)('%s 在非 OO 会话中正常落库（正面对照，防判据把功能焊死）', (fn) => {
    const { api, allResponses, saveImmediate } = setup({ oo: false })
    const res = (api as any)[fn]() as { ok: boolean }
    expect(res).toEqual({ ok: true })
    expect(allResponses.value.has(D14_PORTFOLIO_KEY)).toBe(true)
    expect(saveImmediate).toHaveBeenCalledTimes(1)
  })

  it('OO 会话结束后同一实例即可落库（门是动态的，不是一次性拒绝）', () => {
    const { api, allResponses, ooSessionActive } = setup({ oo: true })
    expect((api as any).syncReversalToD14().ok).toBe(false)
    ooSessionActive.value = false
    expect((api as any).syncReversalToD14()).toEqual({ ok: true })
    expect(allResponses.value.has(D14_PORTFOLIO_KEY)).toBe(true)
  })

  it('🔴 readonly 也必须给可见原因（改造前是静默 return + UI 假成功）', () => {
    const { api, allResponses, saveImmediate } = setup({ readonly: true })
    const res = (api as any).syncReversalToD14() as { ok: boolean; reason?: string }
    expect(res.ok).toBe(false)
    expect(res.reason).toContain('只读')
    expect(allResponses.value.has(D14_PORTFOLIO_KEY)).toBe(false)
    expect(saveImmediate).not.toHaveBeenCalled()
  })

  it('🔴 OO 判定必须先于 readonly（否则 OO+可写时 OO 分支被短路掉）', () => {
    // OO 开着但**不是** readonly ⇒ 必须命中 OO 那条原因，而不是 readonly 那条
    const { api } = setup({ oo: true, readonly: false })
    const res = (api as any).syncReversalToD14() as { ok: boolean; reason?: string }
    expect(res.reason).toContain('在线编辑')
    expect(res.reason).not.toContain('只读')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. 源码守卫：接线真的存在（零挂载、专防回退）
// ═══════════════════════════════════════════════════════════════════════════

/** 剥掉注释再扫，否则「注释里写了这个标识名」会把守卫骗过去（L 节踩过的坑）。 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')   // HTML 注释
    .replace(/\/\*[\s\S]*?\*\//g, '')  // 块注释
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1') // 行注释（不吃掉 https://）
}

describe('P17 源码守卫：宿主 → tab → composable 三段接线', () => {
  it('剥注释器自检（正反两向）', () => {
    expect(stripComments('a // x\nb')).not.toContain('x')
    expect(stripComments('<!-- y -->z')).not.toContain('y')
    // 🔴 首版写成 `not.toContain('w' && 'q')` —— JS 里 `'w' && 'q'` 求值为 `'q'`，
    //    于是「w 必须保留」这半条根本没验。正反两向必须分开断言。
    expect(stripComments('/* q */w')).not.toContain('q')   // 注释内容被剥掉
    expect(stripComments('/* q */w')).toContain('w')       // 注释外的代码保留
    // 不得吃掉 URL
    expect(stripComments("const u = 'https://a.b/c'")).toContain('https://a.b/c')
    // 不得吃掉正常代码
    expect(stripComments('const keep = 1 // drop')).toContain('const keep = 1')
  })

  it('宿主定义了 entry 级信号，且口径取自 syncBridge 而非 renderMode', () => {
    const src = stripComments(HOST_SRC)
    expect(src).toContain('crossSheetWriteBlocked')
    // 🔴 必须读 syncBridge.mode（entry 级），不能读 renderMode（当前 sheet 级）
    expect(src).toMatch(/crossSheetWriteBlocked[\s\S]{0,400}syncBridge\.mode/)
    expect(src).toMatch(/crossSheetWriteBlocked[\s\S]{0,400}WP_BRIDGE_IN_FLIGHT_STATES/)
  })

  it('宿主把信号传给了 D1TabWriteoffCheck', () => {
    const src = stripComments(HOST_SRC)
    const idx = src.indexOf('<D1TabWriteoffCheck')
    expect(idx, '宿主里找不到 D1TabWriteoffCheck 挂点').toBeGreaterThan(-1)
    const block = src.slice(idx, idx + 700)
    expect(block).toContain(':oo-session-active="crossSheetWriteBlocked"')
  })

  it('tab 把 prop 接进了 composable', () => {
    const src = stripComments(TAB_SRC)
    expect(src).toContain('ooSessionActive')
    expect(src).toMatch(/useD1WriteoffCheck\(\{[\s\S]{0,900}ooSessionActive:/)
  })

  it('🔴 tab 不再无条件报成功（改造前 success 与调用同层直排）', () => {
    const src = stripComments(TAB_SRC)
    // 两个 handler 都必须经由结果分派函数，而不是「调完就 success」
    expect(src).toContain('reportCrossSheetWrite(syncReversalToD14())')
    expect(src).toContain('reportCrossSheetWrite(syncWriteoffToD14())')
    // 成功提示只允许出现在分派函数的 ok 分支里：全文件 success 次数恰 1
    const successCount = (src.match(/ElMessage\.success\('已同步到D1-4'\)/g) || []).length
    expect(successCount, '「已同步到D1-4」出现多次 ⇒ 可能有分支绕过了结果判定').toBe(1)
    // 且拒绝路径必须真的把 reason 显示出来
    expect(src).toMatch(/result\.reason/)
  })

  it('🔴 变异反证：把 OO 门从 composable 里拿掉，行为判据必须打红', () => {
    // 不改磁盘文件 —— 直接构造一个「没有 OO 门」的等价实现，证明上面那批断言
    // 依赖的是真实存在的门，而不是恰好为空的 store。
    const map = new Map<string, any>([
      ['D1-writeoff-reversal-rows', {
        item_id: 'D1-writeoff-reversal-rows', conclusion: null,
        remark: JSON.stringify([reversal(777)]),
      }],
    ])
    const allResponses = ref(map)
    const saveImmediate = vi.fn().mockResolvedValue(undefined)
    // 模拟「门被摘掉」= ooSessionActive 恒 false（生产里若忘接线就是这个效果）
    const api = useD1WriteoffCheck({
      allResponses: allResponses as any,
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      saveImmediate,
      saveDebouncedText: vi.fn(),
      isReadonly: ref(false),
      ooSessionActive: ref(false),
    })
    // 门失效时它**会**直写 —— 这正是 `ooSessionActive` 不给默认值的理由
    expect((api as any).syncReversalToD14()).toEqual({ ok: true })
    expect(allResponses.value.has(D14_PORTFOLIO_KEY)).toBe(true)
    expect(saveImmediate).toHaveBeenCalled()
  })

  it('composable 的 option 是必填（漏接线会在类型层暴露，不是静默放行）', () => {
    const src = stripComments(
      readFileSync(resolve(SRC_DIR, 'composables/useD1WriteoffCheck.ts'), 'utf-8'),
    )
    // 必填：不得写成 `ooSessionActive?:`
    expect(src).toMatch(/ooSessionActive:\s*Ref<boolean>/)
    expect(src).not.toMatch(/ooSessionActive\?:/)
    // 门必须在 writeBackToD14 里，且在 isReadonly 判定之前
    const body = src.slice(src.indexOf('function writeBackToD14'))
    const ooAt = body.indexOf('ooSessionActive.value')
    const roAt = body.indexOf('isReadonly.value')
    expect(ooAt).toBeGreaterThan(-1)
    expect(roAt).toBeGreaterThan(-1)
    expect(ooAt, 'OO 门必须先判，否则 readonly 分支会短路掉它').toBeLessThan(roAt)
  })
})
