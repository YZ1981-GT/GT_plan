/**
 * 循环底稿「回填程序表」写入位置 —— spec audit-year-calendar-fallback-ratchet R0 / 任务 0.3
 * G8~G12 六个回填函数收口到 writeProgramStepOverrides：scope 用表码（与读取方一致）、年度缺省取项目审计年度。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const warn = vi.hoisted(() => vi.fn())
vi.mock('@/services/apiProxy', () => ({ api }))
vi.mock('element-plus', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ElMessage: { warning: warn, error: vi.fn(), success: vi.fn() },
}))

import { writeProgramStepOverrides } from '../programStepOverrides'
import { markG8AProcedureSteps } from '../g8CrossHelpers'
import { markG9AProcedureSteps } from '../g9FvCrossHelpers'
import { markG10AProcedureSteps } from '../g10FvCrossHelpers'
import { markG11AProcedureSteps } from '../g11VoucherCross'
import { markG12AProcedureSteps } from '../g12VoucherCross'

beforeEach(() => {
  api.get.mockReset().mockResolvedValue({ audit_year: 2025 })
  // 批量端点：回执逐项列出写入成功的（spec procedure-chain-hardening-and-java-contracts R8）
  api.post.mockReset().mockImplementation(async (_url: string, body: any) => ({
    saved: body.items.map((i: any) => ({ scope: i.scope, item_key: i.item_key, field: i.field })), failed: [],
  }))
  warn.mockReset()
})

const items = () => api.post.mock.calls.flatMap(c => c[1].items.map((it: any) => ({ ...it, year: c[1].year })))
const scopes = () => [...new Set(items().map(it => `${it.scope}@${it.year}`))]

describe('writeProgramStepOverrides', () => {
  it('scope 用表码而不是整张表名；传了年度就用', async () => {
    const n = await writeProgramStepOverrides({
      projectId: 'p1', year: 2024, sheet: '其他权益工具投资实质性程序表G8A', programNos: [3, 10],
      status: 'completed', linkedWorkpapers: 'G8-4', executionSummary: '已测试',
    })
    expect(n).toBe(2)
    expect(scopes()).toEqual(['procedure_table:G8A@2024'])
    expect(api.post).toHaveBeenCalledTimes(1) // 一次请求（原先逐字段 6 发）
    expect(api.post.mock.calls[0][0]).toBe('/api/workpapers/field-overrides/batch')
    expect(items().map(it => `${it.item_key}:${it.field}`)).toEqual([
      '3:status', '3:linked_workpapers', '3:execution_summary', '10:status', '10:linked_workpapers', '10:execution_summary',
    ])
    expect(api.get).not.toHaveBeenCalled()
  })

  it('没传年度 ⇒ 取项目审计年度（不再取今年）', async () => {
    await writeProgramStepOverrides({ projectId: 'p1', sheet: 'G9A', programNos: [1], status: 'completed' })
    expect(api.get).toHaveBeenCalledWith('/api/projects/p1', { _dedupe: false, _silent: true })
    expect(scopes()).toEqual(['procedure_table:G9A@2025'])
  })

  it('项目没填年度 ⇒ 不写、提示、返回 0', async () => {
    api.get.mockResolvedValue({ audit_year: null })
    const n = await writeProgramStepOverrides({ projectId: 'p1', sheet: 'G9A', programNos: [1], status: 'completed' })
    expect(n).toBe(0)
    expect(api.post).not.toHaveBeenCalled()
    expect(warn).toHaveBeenCalledTimes(1)
  })

  it('不是登记过的循环程序表 ⇒ 不写', async () => {
    expect(await writeProgramStepOverrides({ projectId: 'p1', year: 2025, sheet: '审计程序A7', programNos: [1], status: 'x' }))
      .toBe(0)
    expect(api.post).not.toHaveBeenCalled()
  })
})

describe('G8~G12 回填函数都走同一写入（scope = 表码）', () => {
  it.each([
    ['G8A', markG8AProcedureSteps],
    ['G9A', markG9AProcedureSteps],
    ['G10A', markG10AProcedureSteps],
    ['G11A', markG11AProcedureSteps],
    ['G12A', markG12AProcedureSteps],
  ] as const)('%s', async (code, mark) => {
    const n = await (mark as any)({ projectId: 'p1', programNos: [2], executionSummary: '已检查' })
    expect(n).toBe(1)
    expect(scopes()).toEqual([`procedure_table:${code}@2025`])
    expect(items().find(it => it.field === 'status')?.value).toBe('completed')
  })
})

// ─── 变异验证 ─────────────────────────────────────────────────────────────────
describe('变异：writeProgramStepOverrides 不可回退到旧写法', () => {
  it('MO-S1: scope 只用表码、不用整张表名——整表名「其他权益工具投资实质性程序表G8A」不会出现在 scope 里', async () => {
    await writeProgramStepOverrides({
      projectId: 'p1', year: 2025, sheet: '其他权益工具投资实质性程序表G8A',
      programNos: [1], status: 'completed',
    })
    for (const it of items()) {
      // scope 应该是 procedure_table:G8A，不是 procedure_table:其他权益工具投资实质性程序表G8A
      expect(it.scope).toBe('procedure_table:G8A')
      expect(it.scope).not.toContain('其他权益工具')
    }
  })

  it('MO-S2: 年度取不到时不发任何 POST、不传 undefined 年度', async () => {
    api.get.mockResolvedValue({ audit_year: null, audit_period_end: null, name: '无年度项目' })
    await writeProgramStepOverrides({ projectId: 'p1', sheet: 'G8A', programNos: [1], status: 'completed' })
    expect(api.post).not.toHaveBeenCalled()
    // 提示已经给了
    expect(warn).toHaveBeenCalledTimes(1)
  })

  it('MO-S3: 调用方传了有效年度就用，不额外请求项目信息', async () => {
    await writeProgramStepOverrides({
      projectId: 'p1', year: 2024, sheet: 'G9A', programNos: [1, 2], status: 'completed',
    })
    // 传了 year=2024，不该调 GET /api/projects/...
    expect(api.get).not.toHaveBeenCalled()
    // 所有 POST 的 year 必须是 2024
    for (const call of api.post.mock.calls) {
      expect(call[1].year).toBe(2024)
    }
    expect(items().length).toBe(2)
  })

  it('MO-S4: 未知的表名返回 0、不发请求（防止写到错误的 scope）', async () => {
    const n = await writeProgramStepOverrides({
      projectId: 'p1', year: 2025, sheet: '不存在的程序表XYZ', programNos: [1], status: 'completed',
    })
    expect(n).toBe(0)
    expect(api.post).not.toHaveBeenCalled()
  })
})

describe('批量写入的失败如实提示（R8：原先逐字段吞错）', () => {
  it('后端回报不能写的项 ⇒ 提示原因，只计写入成功的状态', async () => {
    api.post.mockResolvedValueOnce({
      saved: [{ scope: 'procedure_table:G8A', item_key: '1', field: 'status' }],
      failed: [{ scope: 'procedure_table:G8A', item_key: '2', field: 'status', status: 403, reason: '只能填写派给本人的程序行' }],
    })
    const n = await writeProgramStepOverrides({ projectId: 'p1', year: 2025, sheet: 'G8A', programNos: [1, 2], status: 'completed' })
    expect(n).toBe(1)
    expect(warn).toHaveBeenCalledWith('回填程序表有 1 项没有写入 —— 第 2 条：只能填写派给本人的程序行')
  })

  it('超过单次上限按 200 项分批（后端 MAX_BATCH_ITEMS）', async () => {
    const programNos = Array.from({ length: 70 }, (_, i) => i + 1) // 70 × 3 字段 = 210 项
    const n = await writeProgramStepOverrides({
      projectId: 'p1', year: 2025, sheet: 'G8A', programNos, status: 'completed', linkedWorkpapers: 'G8-4', executionSummary: 'x',
    })
    expect(api.post.mock.calls.map(c => c[1].items.length)).toEqual([200, 10])
    expect(n).toBe(70)
  })

  it('请求失败 ⇒ 提示后端原因、返回 0', async () => {
    api.post.mockRejectedValueOnce({ response: { status: 403, data: { detail: '权限不足' } } })
    const n = await writeProgramStepOverrides({ projectId: 'p1', year: 2025, sheet: 'G8A', programNos: [1], status: 'completed' })
    expect(n).toBe(0)
    expect(warn).toHaveBeenCalledWith('回填程序表失败：权限不足')
  })
})
