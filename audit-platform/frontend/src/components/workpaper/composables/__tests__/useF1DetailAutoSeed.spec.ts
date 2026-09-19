/**
 * useF1DetailAutoSeed — F1-2 四表库自动取数（手工优先）单测
 *
 * 覆盖：
 *  Property 1  空表判定：无/[]/null/{}/空数组 → 可 seed；非空数组/不可解析 → 不 seed
 *  Property 2  手工优先：F1-det-rows 已有行 → 不调端点、不 reload
 *  Property 3  空表 + 端点返回行 → 落库后 reload 级联；返回真
 *  Property 4  fail-open：只读 / 无 wpId / 端点异常 / 返回 0 行 → 不 reload、返回假
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  shouldAutoSeedF1Detail,
  autoSeedF1DetailFromAux,
} from '../useF1DetailAutoSeed'
import type { ChecklistResponse } from '../useF1FormData'

const postMock = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { post: (...args: any[]) => postMock(...args) },
}))

function makeResponses(detRemark?: string): Map<string, ChecklistResponse> {
  const m = new Map<string, ChecklistResponse>()
  if (detRemark !== undefined) {
    m.set('F1-det-rows', { conclusion: '', remark: detRemark } as ChecklistResponse)
  }
  return m
}

function setup(opts: {
  detRemark?: string
  readonly?: boolean
  wpId?: string
}) {
  const reloadAll = vi.fn().mockResolvedValue(undefined)
  const deps = {
    wpId: ref(opts.wpId ?? 'wp-1'),
    projectId: ref('proj-1'),
    isReadonly: ref(!!opts.readonly),
    allResponses: ref(makeResponses(opts.detRemark)),
    reloadAll,
  }
  return { deps, reloadAll }
}

beforeEach(() => {
  postMock.mockReset()
})

describe('shouldAutoSeedF1Detail — Property 1 空表判定', () => {
  it.each(['', '   ', '[]', 'null', '{}', undefined, null])(
    '空标记 %s → 可 seed',
    (v) => {
      expect(shouldAutoSeedF1Detail(v as any)).toBe(true)
    },
  )

  it('空数组 JSON → 可 seed', () => {
    expect(shouldAutoSeedF1Detail(JSON.stringify([]))).toBe(true)
  })

  it('非空数组 → 不 seed（手工优先）', () => {
    expect(shouldAutoSeedF1Detail(JSON.stringify([{ rowId: 'a' }]))).toBe(false)
  })

  it('不可解析字符串 → 保守不 seed', () => {
    expect(shouldAutoSeedF1Detail('不是JSON')).toBe(false)
  })
})

describe('autoSeedF1DetailFromAux — 编排', () => {
  it('Property 2 手工优先：已有行 → 不调端点、不 reload', async () => {
    const { deps, reloadAll } = setup({ detRemark: JSON.stringify([{ rowId: 'x' }]) })
    const ran = await autoSeedF1DetailFromAux(deps)
    expect(ran).toBe(false)
    expect(postMock).not.toHaveBeenCalled()
    expect(reloadAll).not.toHaveBeenCalled()
  })

  it('Property 3 空表 + 端点返回行 → reload 级联、返回真', async () => {
    postMock.mockResolvedValue({ data: { rows: [{ customerName: 'A公司' }] } })
    const { deps, reloadAll } = setup({ detRemark: '[]' })
    const ran = await autoSeedF1DetailFromAux(deps)
    expect(ran).toBe(true)
    expect(postMock).toHaveBeenCalledWith(
      '/api/workpapers/wp-1/f1/import-aux-balance',
      { project_id: 'proj-1' },
    )
    expect(reloadAll).toHaveBeenCalledTimes(1)
  })

  it('Property 4a 只读 → 跳过', async () => {
    const { deps, reloadAll } = setup({ detRemark: '[]', readonly: true })
    expect(await autoSeedF1DetailFromAux(deps)).toBe(false)
    expect(postMock).not.toHaveBeenCalled()
    expect(reloadAll).not.toHaveBeenCalled()
  })

  it('Property 4b 无 wpId → 跳过', async () => {
    const { deps, reloadAll } = setup({ detRemark: '[]', wpId: '' })
    expect(await autoSeedF1DetailFromAux(deps)).toBe(false)
    expect(postMock).not.toHaveBeenCalled()
    expect(reloadAll).not.toHaveBeenCalled()
  })

  it('Property 4c 端点返回 0 行 → 不 reload', async () => {
    postMock.mockResolvedValue({ data: { rows: [] } })
    const { deps, reloadAll } = setup({ detRemark: '[]' })
    expect(await autoSeedF1DetailFromAux(deps)).toBe(false)
    expect(reloadAll).not.toHaveBeenCalled()
  })

  it('Property 4d 端点异常 → fail-open 返回假', async () => {
    postMock.mockRejectedValue(new Error('boom'))
    const { deps, reloadAll } = setup({ detRemark: '[]' })
    expect(await autoSeedF1DetailFromAux(deps)).toBe(false)
    expect(reloadAll).not.toHaveBeenCalled()
  })

  it('端点返回裸数组（非 {rows}）亦识别', async () => {
    postMock.mockResolvedValue({ data: [{ customerName: 'B公司' }] })
    const { deps, reloadAll } = setup({ detRemark: undefined })
    expect(await autoSeedF1DetailFromAux(deps)).toBe(true)
    expect(reloadAll).toHaveBeenCalledTimes(1)
  })
})
