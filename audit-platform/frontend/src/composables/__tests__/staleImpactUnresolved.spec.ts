/**
 * RV9.1-02 守卫：起点身份算不出时，照实告诉用户「未能分析下游影响」
 *
 * 判据（design §10.2）：
 * 1. useStaleImpact 暴露 unresolvedReason，取后端 unresolved_reason；能分析时为空。
 * 2. 同一会话同一 (底稿, sheet) 只提示一次；换 sheet 会再提示一次。
 * 3. 后端能分析时不提示。
 *
 * 变异：notify 不再读 unresolved_reason，或去掉去重 → 本文件对应用例红。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// vi.mock 的工厂会被提升到文件顶部，桩必须用 vi.hoisted 才能被它引用
const { post } = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { post, get: vi.fn() } }))
vi.mock('@/utils/logger', () => ({ logger: { log: vi.fn(), warn: vi.fn() } }))
vi.mock('@/services/apiPaths', () => ({
  linkageBus: { impact: '/api/linkage-bus/impact' },
  addressRegistry: { v2: { staleImpact: '/api/address-registry/v2/stale-impact' } },
}))

import { useStaleImpact } from '../useStaleImpact'

describe('useStaleImpact.unresolvedReason', () => {
  beforeEach(() => {
    post.mockReset()
  })

  it('后端算不出起点身份时暴露中文原因', async () => {
    post.mockResolvedValue({
      data: {
        unresolved_code: 'label_not_a1',
        unresolved_reason: '引用末段是语义标签、不是 A1 单元格坐标',
        affected: [],
        total: 0,
      },
    })
    const s = useStaleImpact('D2')
    await s.notify({ sheet: '审定表D2-1', cell: '期末余额', project_id: 'p1', year: 2025 })
    expect(s.unresolvedReason.value).toBe('引用末段是语义标签、不是 A1 单元格坐标')
  })

  it('能分析时原因为空', async () => {
    post.mockResolvedValue({ data: { affected: ['WP:D3:审定表D3-1:C10'], total: 1 } })
    const s = useStaleImpact('D2')
    await s.notify({ sheet: '审定表D2-1', cell: 'C10', project_id: 'p1', year: 2025 })
    expect(s.unresolvedReason.value).toBe('')
    expect(s.totalAffected.value).toBe(1)
  })

  it('clear 会清掉原因', async () => {
    post.mockResolvedValue({ data: { unresolved_reason: 'x', affected: [], total: 0 } })
    const s = useStaleImpact('D2')
    await s.notify({ sheet: 's', cell: 'c', project_id: 'p1', year: 2025 })
    expect(s.unresolvedReason.value).toBe('x')
    s.clear()
    expect(s.unresolvedReason.value).toBe('')
  })
})

// ─── 保存流程只提示一次 ───

const infoMessages: string[] = []

describe('保存后「未能分析下游影响」只提示一次', () => {
  beforeEach(() => {
    infoMessages.length = 0
  })

  /**
   * 直接复刻 useEditorSave 里的提示判定（同一份判据：非空 + 同一 (底稿, sheet) 去重），
   * 以免为了测一句提示去搭整个 Univer 编辑器。去重集合的实现由下面的源码断言钉住。
   */
  function makeNotifier() {
    const seen = new Set<string>()
    return (wp: string, sheet: string, reason: string) => {
      const text = String(reason || '').trim()
      if (!text) return
      const key = `${wp}|${sheet}`
      if (seen.has(key)) return
      seen.add(key)
      infoMessages.push(`未能分析下游影响：${text}`)
    }
  }

  it('同一底稿同一 sheet 连存两次只提示一次，换 sheet 再提示', () => {
    const notify = makeNotifier()
    notify('D2', '审定表D2-1', '引用末段是语义标签、不是 A1 单元格坐标')
    notify('D2', '审定表D2-1', '引用末段是语义标签、不是 A1 单元格坐标')
    expect(infoMessages).toHaveLength(1)
    notify('D2', '明细表D2-2', '引用末段是语义标签、不是 A1 单元格坐标')
    expect(infoMessages).toHaveLength(2)
  })

  it('原因为空时不提示', () => {
    const notify = makeNotifier()
    notify('D2', '审定表D2-1', '')
    notify('D2', '审定表D2-1', '   ')
    expect(infoMessages).toHaveLength(0)
  })
})

// ─── 源码判据：保证生产代码真的接了这条线 ───

describe('useEditorSave 源码判据', () => {
  it('保存流程读 unresolvedReason，并按 (底稿, sheet) 去重提示', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const src = fs.readFileSync(
      path.resolve(__dirname, '../useEditorSave.ts'),
      'utf-8',
    )
    expect(src).toContain('unresolvedReason')
    expect(src).toContain('未能分析下游影响：')
    // 去重集合在模块级（同一会话跨挂载有效），且按 底稿|sheet 作键
    expect(src).toMatch(/const notifiedUnresolved = new Set<string>\(\)/)
    expect(src).toMatch(/notifiedUnresolved\.has\(key\)/)
    expect(src).toMatch(/notifiedUnresolved\.add\(key\)/)
  })

  it('useStaleImpact 导出 unresolvedReason 并从响应体读取', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const src = fs.readFileSync(
      path.resolve(__dirname, '../useStaleImpact.ts'),
      'utf-8',
    )
    expect(src).toContain('unresolved_reason')
    expect(src).toMatch(/unresolvedReason,/)
  })
})
