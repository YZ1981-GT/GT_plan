/**
 * 过期响应保护单测（spec consol-node-key-isolation-and-shared-context 任务 5.4，需求 4.5 / 5.2，设计 §七、P9、ADR-CNSC-005）。
 *
 * 覆盖：
 *  - 同通道响应乱序：先发的慢请求后到，旧序号响应被判过期，只有最新序号可提交；
 *  - 切 nodeKey / year / project：旧上下文响应被判过期（上下文闸门），不覆盖新节点；
 *  - 两重闸门独立：序号与上下文各自都能单独拦下过期响应；
 *  - 端到端模拟乱序提交：慢(旧) + 快(新) 两段请求乱序 resolve，断言最终落地的是新节点数据；
 *  - 反向变异（禁恒绿）：若去掉守卫（无条件提交），同一乱序场景会让旧节点数据覆盖新节点 —— 守卫转红。
 */
import { describe, it, expect } from 'vitest'
import { ConsolRequestGuard, sameContext, type RequestContext } from './consolRequestGuard'

const ctx = (projectId: string | number, year: number, nodeKey: string): RequestContext => ({
  projectId,
  year,
  nodeKey,
})

describe('consolRequestGuard — sameContext 四元比较', () => {
  it('projectId number/string 等价、year 与 nodeKey 逐项相等才为真', () => {
    expect(sameContext(ctx(5, 2025, 'A:consol'), ctx('5', 2025, 'A:consol'))).toBe(true)
    expect(sameContext(ctx(5, 2025, 'A:consol'), ctx(6, 2025, 'A:consol'))).toBe(false) // project
    expect(sameContext(ctx(5, 2025, 'A:consol'), ctx(5, 2024, 'A:consol'))).toBe(false) // year
    expect(sameContext(ctx(5, 2025, 'A:consol'), ctx(5, 2025, 'A:consol_elim'))).toBe(false) // nodeKey
  })
})

describe('consolRequestGuard — 序号闸门（同通道乱序）', () => {
  it('同节点连发两次，先到的旧序号响应被判过期，只有最新序号可提交', () => {
    const g = new ConsolRequestGuard()
    const current = ctx(5, 2025, 'A:consol')
    const t1 = g.begin('report', current) // 慢请求
    const t2 = g.begin('report', current) // 后发的快请求推高序号
    // 快请求（最新序号）先到并提交 —— 允许
    expect(g.isCurrent(t2, current)).toBe(true)
    // 慢请求后到 —— 序号已非最新 ⇒ 过期，必须丢弃
    expect(g.isCurrent(t1, current)).toBe(false)
  })

  it('不同通道（report / note）序号互不干扰', () => {
    const g = new ConsolRequestGuard()
    const current = ctx(5, 2025, 'A:consol')
    const r1 = g.begin('report', current)
    const n1 = g.begin('note', current)
    // 各自通道只有一个在飞行，均为最新
    expect(g.isCurrent(r1, current)).toBe(true)
    expect(g.isCurrent(n1, current)).toBe(true)
    // report 通道再发一次，只影响 report 序号
    const r2 = g.begin('report', current)
    expect(g.isCurrent(r1, current)).toBe(false) // report 旧序号过期
    expect(g.isCurrent(r2, current)).toBe(true)
    expect(g.isCurrent(n1, current)).toBe(true) // note 不受影响
  })
})

describe('consolRequestGuard — 上下文闸门（切节点/年度/项目）', () => {
  it('发起时在 A:consol，响应到达时已切到 A:consol_elim ⇒ 旧响应过期', () => {
    const g = new ConsolRequestGuard()
    const ticket = g.begin('report', ctx(5, 2025, 'A:consol'))
    // 用户已切到同企业另一角色节点
    const nowCurrent = ctx(5, 2025, 'A:consol_elim')
    expect(g.isCurrent(ticket, nowCurrent)).toBe(false)
  })

  it('切年度 / 切项目同样触发上下文闸门', () => {
    const g = new ConsolRequestGuard()
    const t = g.begin('note', ctx(5, 2025, 'A:consol'))
    expect(g.isCurrent(t, ctx(5, 2024, 'A:consol'))).toBe(false) // 切年度
    expect(g.isCurrent(t, ctx(6, 2025, 'A:consol'))).toBe(false) // 切项目
  })

  it('两重闸门独立：序号最新但上下文不符仍丢弃', () => {
    const g = new ConsolRequestGuard()
    // 该通道只有这一个请求（序号最新），但发起/到达之间上下文变了
    const t = g.begin('report', ctx(5, 2025, 'A:consol'))
    expect(g.isCurrent(t, ctx(5, 2025, 'A:parent'))).toBe(false)
  })
})

/**
 * 端到端乱序提交模拟：复刻 loadConsolReport 的提交结构
 * （发起 → await → 提交前 isCurrent 校验 → 写入）。
 * 模拟「慢请求发给旧节点、快请求发给新节点」且慢请求后 resolve 的乱序。
 */
async function simulateOutOfOrderLoad(opts: { useGuard: boolean }) {
  const g = new ConsolRequestGuard()
  // 页面当前展示的数据（相当于 consolReportRows.value）
  let committed: { nodeKey: string; rows: string } = { nodeKey: '', rows: '' }
  // 响应乱序控制：用两个可控 resolve 的 promise
  let resolveSlow!: (v: string) => void
  let resolveFast!: (v: string) => void
  const slow = new Promise<string>((r) => (resolveSlow = r))
  const fast = new Promise<string>((r) => (resolveFast = r))

  // ① 当前在旧节点 A:consol，发起慢请求
  const oldCtx = ctx(5, 2025, 'A:consol')
  const slowTicket = g.begin('report', oldCtx)
  const slowDone = (async () => {
    const rows = await slow
    // 响应到达时，当前上下文读的是「页面现在的节点」= 新节点
    const nowCurrent = ctx(5, 2025, newCurrentNodeKey())
    if (opts.useGuard && !g.isCurrent(slowTicket, nowCurrent)) return // 守卫：丢弃过期响应
    committed = { nodeKey: 'A:consol', rows }
  })()

  // ② 用户切到新节点 A:consol_elim，发起快请求
  const newCtx = ctx(5, 2025, 'A:consol_elim')
  const fastTicket = g.begin('report', newCtx)
  const fastDone = (async () => {
    const rows = await fast
    const nowCurrent = ctx(5, 2025, newCurrentNodeKey())
    if (opts.useGuard && !g.isCurrent(fastTicket, nowCurrent)) return
    committed = { nodeKey: 'A:consol_elim', rows }
  })()

  // 当前页面节点现在是新节点
  function newCurrentNodeKey() {
    return 'A:consol_elim'
  }

  // 乱序：快请求（新节点）先 resolve 并提交，慢请求（旧节点）后 resolve
  resolveFast('elim-rows')
  await fastDone
  resolveSlow('consol-rows')
  await slowDone

  return committed
}

describe('consolRequestGuard — 端到端乱序提交 + 反向变异', () => {
  it('有守卫：慢(旧节点)响应后到也不覆盖新节点，最终展示新节点数据', async () => {
    const committed = await simulateOutOfOrderLoad({ useGuard: true })
    expect(committed.nodeKey).toBe('A:consol_elim')
    expect(committed.rows).toBe('elim-rows')
  })

  it('反向变异（去掉守卫）：慢(旧节点)响应后到会覆盖新节点 —— 证明守卫非恒绿', async () => {
    const committed = await simulateOutOfOrderLoad({ useGuard: false })
    // 没有守卫时，后 resolve 的旧节点响应串用覆盖了新节点数据（这正是任务 5.4 要防的 bug）。
    expect(committed.nodeKey).toBe('A:consol')
    expect(committed.rows).toBe('consol-rows')
  })
})
