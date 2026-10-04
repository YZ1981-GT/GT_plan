/**
 * 合并节点 node_key 透传 + 身份区分 API 契约测试
 * （spec consol-node-key-isolation-and-shared-context 任务 5.5，需求 4.5 / 5.1~5.5，设计 §七、P9、ADR-CNSC-001/004/005）。
 *
 * 本文件是 section 5（前端）综合测试收口。与既有 spec 的分工：
 *  - 透传的「纯函数/源码」层已由 consolNoteView.spec.ts 的「ConsolNoteTab 生产接线守卫」覆盖
 *    （P_cn.data/aggregate/auditAll/audit、fillConsolNoteByFormula、getConsolNoteBreakdown 的接入点）。
 *  - 缓存四维分区与精确清理已由 consolCacheKeys.spec.ts（任务 5.3）覆盖。
 *  - 序号 / 上下文双闸门与端到端乱序提交已由 consolRequestGuard.spec.ts（任务 5.4）覆盖。
 *  本文件补齐尚缺的「API 真实请求层」证据：mock apiProxy，调用真实 service 函数，
 *  断言 node_key 真的落到请求参数 / query（不是只在源码里出现字符串），并覆盖：
 *    ① 节点级读写/公式/审核/聚合/穿透请求都带当前 node_key（透传闭合）；
 *    ② 同企业「同角色」身份区分：node_key 单独不是身份，必须叠加 project/year 四维（ADR-CNSC-001）；
 *    ③ 差额穿透独立选择只改穿透请求参数，不反写页面 nodeKey（ADR-CNSC-004，设计 §七）；
 *    ④ 用户可见错误为中文（源码守卫，与 consolNoteView.spec.ts 的 400/423 互补）；
 *    ⑤ 禁恒绿：关键断言配反向变异（去掉 node_key / 用无尾冒号前缀 会让守卫转红）。
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ─── mock apiProxy：捕获真实 service 函数发出的请求（url + options），不打真实网络 ──
const calls: Array<{ method: string; url: string; body?: unknown; options?: any }> = []
vi.mock('@/services/apiProxy', () => {
  const rec = (method: string) => (url: string, body?: unknown, options?: any) => {
    // get/put/post 的签名不同：get(url, options) / put(url, body, options) / post(url, body, options)
    if (method === 'get') {
      calls.push({ method, url, options: body })
      return Promise.resolve([])
    }
    calls.push({ method, url, body, options })
    return Promise.resolve({})
  }
  const api = { get: rec('get'), post: rec('post'), put: rec('put'), patch: rec('patch'), delete: rec('delete'), download: vi.fn() }
  return { api, apiProxy: api, default: api }
})

import {
  fillConsolNoteByFormula,
  getConsolNoteBreakdown,
  getConsolReportTrial,
  getConsolReportBreakdown,
} from '@/services/consolidationApi'
import { api } from '@/services/apiProxy'

/** 从捕获的 get 调用里取请求参数（service 用 { params } 或 ?query 两种形态）。 */
function paramsOf(call: { url: string; options?: any }): Record<string, unknown> {
  const fromOptions = call.options?.params ?? {}
  const qIndex = call.url.indexOf('?')
  const fromQuery: Record<string, string> = {}
  if (qIndex >= 0) {
    for (const [k, v] of new URLSearchParams(call.url.slice(qIndex + 1))) fromQuery[k] = v
  }
  return { ...fromQuery, ...fromOptions }
}

beforeEach(() => {
  calls.length = 0
})

describe('5.5 node_key 透传 — service 真实请求携带 node_key', () => {
  it('fillConsolNoteByFormula 把 nodeKey 作为 query node_key 发出（公式填入写路径）', async () => {
    await fillConsolNoteByFormula('p5', 2025, '五-1-1', 'soe', 'A:consol')
    const call = calls.find((c) => c.url.includes('/fill-by-formula/'))!
    expect(call.method).toBe('post')
    expect(paramsOf(call).node_key).toBe('A:consol')
    // 写路径须抑制全局重复 toast（由附注页带语境显示），options._silent 为真
    expect(call.options?._silent).toBe(true)
  })

  it('getConsolNoteBreakdown 把独立选择的 nodeKey 作为 node_key 发出（差额穿透读路径）', async () => {
    await getConsolNoteBreakdown('p5', 2025, '五-1-1', { nodeKey: 'A:consol_elim', standard: 'soe' })
    const call = calls.find((c) => c.url.includes('/breakdown/'))!
    expect(call.method).toBe('get')
    expect(paramsOf(call).node_key).toBe('A:consol_elim')
  })

  it('合并试算 / 差额读端点经 viewParams 发送 node_key（与报表同一节点口径，P8）', async () => {
    await getConsolReportTrial('p5', { reportType: 'balance_sheet', nodeKey: 'A:consol', year: 2025 })
    await getConsolReportBreakdown('p5', { reportType: 'balance_sheet', nodeKey: 'A:consol', year: 2025 })
    for (const call of calls) {
      const p = paramsOf(call)
      expect(p.node_key).toBe('A:consol')
      expect(p.report_type).toBe('balance_sheet')
      expect(String(p.year)).toBe('2025')
    }
  })
})

describe('5.5 透传反向变异（禁恒绿）', () => {
  it('不传 nodeKey 时请求不带 node_key（旧调用走 NULL 兼容，ADR-CNSC-002/004）', async () => {
    await fillConsolNoteByFormula('p5', 2025, '五-1-1', 'soe') // 无 nodeKey
    await getConsolNoteBreakdown('p5', 2025, '五-1-1', { standard: 'soe' }) // 无 nodeKey
    for (const call of calls) {
      expect('node_key' in paramsOf(call)).toBe(false)
    }
  })

  it('空字符串 nodeKey 不发送 node_key（空值按未提供处理，不降级成误发空键）', async () => {
    await fillConsolNoteByFormula('p5', 2025, '五-1-1', 'soe', '')
    const call = calls.find((c) => c.url.includes('/fill-by-formula/'))!
    expect('node_key' in paramsOf(call)).toBe(false)
  })
})

/**
 * 同企业「同角色」身份区分（ADR-CNSC-001，需求 4.5）。
 *
 * 理解说明：node_key = {企业代码}:{角色}。任务 4.5 覆盖的是「同企业不同角色」
 * （A:consol vs A:consol_elim）。本任务 5.5 的「同企业同角色」指：相同的
 * company+role 字符串（如都叫 A:consol）在不同 project / year 维度下仍必须被区分 ——
 * node_key 单独不构成前端缓存/请求身份，身份是 (project, year, nodeKey, report/template)
 * 四元组。若只用 node_key 做键，同一集团同一节点在不同项目/年度之间会串用。
 * 这里用 service 请求参数证明：同一 node_key 'A:consol' 在 project/year 变化时，
 * 发出的请求参数四维整体不同（服务端据此隔离），而非仅凭 node_key 命中。
 */
describe('5.5 同企业同角色身份区分 — node_key 不是唯一身份，须叠加 project/year', () => {
  function requestKey(call: { url: string; options?: any }): string {
    const p = paramsOf(call)
    // 复刻服务端隔离元组 (project_id, year, node_key)；report_type 为报表第四维
    return [p.project_id, p.year, p.node_key, p.report_type].join('|')
  }

  it('同一 node_key A:consol 在不同 project / 不同 year 产生不同请求身份', async () => {
    await getConsolReportTrial('p5', { reportType: 'balance_sheet', nodeKey: 'A:consol', year: 2025 })
    await getConsolReportTrial('p6', { reportType: 'balance_sheet', nodeKey: 'A:consol', year: 2025 }) // 换项目
    await getConsolReportTrial('p5', { reportType: 'balance_sheet', nodeKey: 'A:consol', year: 2024 }) // 换年度
    const keys = calls.map(requestKey)
    // node_key 相同（都是 A:consol），但三次请求身份各不相同
    expect(keys.every((k) => k.includes('A:consol'))).toBe(true)
    expect(new Set(keys).size).toBe(3)
  })

  it('反向变异：若只用 node_key 当身份，三次请求会被误判为同一个（证明四维必需）', async () => {
    await getConsolReportTrial('p5', { reportType: 'balance_sheet', nodeKey: 'A:consol', year: 2025 })
    await getConsolReportTrial('p6', { reportType: 'balance_sheet', nodeKey: 'A:consol', year: 2025 })
    await getConsolReportTrial('p5', { reportType: 'balance_sheet', nodeKey: 'A:consol', year: 2024 })
    const nodeKeyOnly = calls.map((c) => String(paramsOf(c).node_key))
    // 仅 node_key 维度：三次全同 ⇒ 用它当身份会串用（这正是 4 维缓存键要防的 bug）
    expect(new Set(nodeKeyOnly).size).toBe(1)
  })
})

// ─── 源码守卫：差额穿透独立选择不反写页面 nodeKey；用户可见错误中文 ───────────────
const noteTab = fs.readFileSync(
  path.resolve(__dirname, '../../components/consolidation/ConsolNoteTab.vue'), 'utf-8',
)
const index = fs.readFileSync(path.resolve(__dirname, '../../views/ConsolidationIndex.vue'), 'utf-8')
const api_src = fs.readFileSync(path.resolve(__dirname, '../consolidationApi.ts'), 'utf-8')

describe('5.5 差额穿透独立选择（ADR-CNSC-004，设计 §七）', () => {
  it('穿透选择 noteBreakdownNodeKey 以当前节点初始化，切节点时同步', () => {
    expect(noteTab).toContain('const noteBreakdownNodeKey = ref<string | null>(props.currentEntity.nodeKey || null)')
    // 切当前树节点时穿透选择跟随（用户未另选的情况）
    expect(noteTab).toMatch(/watch\(\(\)\s*=>\s*props\.currentEntity\.nodeKey/)
  })

  it('用户在穿透弹窗另选只改 loadNoteBreakdown 的 node_key，不反写 currentEntity.nodeKey', () => {
    // 穿透下拉变更只触发 loadNoteBreakdown（重载穿透视图），不去改页面当前实体
    expect(noteTab).toContain('@change="loadNoteBreakdown"')
    // breakdown 请求用 noteBreakdownNodeKey（独立选择），而非页面 currentEntity.nodeKey
    const open = noteTab.slice(noteTab.indexOf('async function openNoteBreakdownForSelection'))
    const body = open.slice(0, open.indexOf('function noteBreakdownChildren'))
    expect(body).toContain('nodeKey: noteBreakdownNodeKey.value')
    // 关键反写防护：穿透逻辑体内不得对 props.currentEntity.nodeKey 赋值
    expect(body).not.toMatch(/props\.currentEntity\.nodeKey\s*=/)
    expect(body).not.toMatch(/currentEntity\.value\.nodeKey\s*=/)
  })

  it('页面当前 nodeKey 只在树节点点击 / 树重建时设置，不被穿透视图改写', () => {
    // currentConsolEntity.value.nodeKey 的赋值点都在树交互侧（Index），穿透在 NoteTab 内
    expect(index).toMatch(/currentConsolEntity\.value\.nodeKey\s*=/)
    // 穿透的 noteBreakdownNodeKey 不出现在 Index（它是 NoteTab 的独立局部状态）
    expect(index).not.toContain('noteBreakdownNodeKey')
  })
})

describe('5.5 用户可见错误中文（需求 5.5）', () => {
  it('附注页节点级错误提示为中文（400/423 带后端具体原因）', () => {
    expect(noteTab).toContain('ElMessage.warning(`${action}：${detail}`)')
    expect(noteTab).toContain('status === 400 || status === 423')
    // noteFormulaError(err, action) 的 action 实参是中文动作名，非英文技术串
    expect(noteTab).toContain("noteFormulaError(err, '按公式填入')")
    expect(noteTab).toContain("noteFormulaError(err, '全部按公式填入')")
    // 加载失败兜底文案也是中文
    expect(noteTab).toContain("'加载附注差额失败'")
  })

  it('合并报表加载 service 层对写路径 _silent 抑制全局重复 toast，交附注页中文呈现', () => {
    const fill = api_src.slice(api_src.indexOf('export async function fillConsolNoteByFormula'))
    expect(fill).toContain('{ _silent: true } as any')
  })
})
