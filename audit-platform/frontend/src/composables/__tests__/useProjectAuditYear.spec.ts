/**
 * 项目审计年度（写请求单一来源）—— spec audit-year-calendar-fallback-ratchet R0 / 任务 0.2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const apiGet = vi.hoisted(() => vi.fn())
const warn = vi.hoisted(() => vi.fn())
vi.mock('@/services/apiProxy', () => ({ api: { get: apiGet, post: vi.fn() } }))
vi.mock('element-plus', () => ({ ElMessage: { warning: warn, error: vi.fn(), success: vi.fn() } }))

import {
  MISSING_AUDIT_YEAR_MESSAGE,
  fetchProjectAuditYear,
  requireProjectAuditYear,
  useProjectAuditYear,
} from '../useProjectAuditYear'
import { resolveAuditYearOrNull, resolveEffectiveAuditYear } from '@/utils/resolveAuditYear'

beforeEach(() => {
  apiGet.mockReset()
  warn.mockReset()
})

describe('resolveAuditYearOrNull', () => {
  it('来源顺序同 resolveEffectiveAuditYear，全部缺失返回 null（不按日历猜）', () => {
    expect(resolveAuditYearOrNull({ routeYear: '2024', storeAuditYear: 2025 })).toBe(2024)
    expect(resolveAuditYearOrNull({ periodEnd: '2025-12-31' })).toBe(2025)
    expect(resolveAuditYearOrNull({ projectName: '某公司_2023' })).toBe(2023)
    expect(resolveAuditYearOrNull({ routeYear: 'abc', storeYear: 0 })).toBeNull()
    expect(resolveAuditYearOrNull({})).toBeNull()
    // 读取请求同样不猜日历年：缺年度由调用方显示空态或由后端按项目上下文处理。
    expect(resolveEffectiveAuditYear({})).toBeNull()
  })
})

describe('fetchProjectAuditYear / requireProjectAuditYear', () => {
  it('取项目详情的审计年度；请求不参与 GET 去重、错误自管', async () => {
    apiGet.mockResolvedValue({ id: 'p1', audit_year: 2025, audit_period_end: '2026-12-31' })
    expect(await fetchProjectAuditYear('p1')).toEqual({ year: 2025, failed: false })
    expect(apiGet).toHaveBeenCalledWith('/api/projects/p1', { _dedupe: false, _silent: true })
  })

  it('项目没填年度 ⇒ null 并提示先填；请求失败 ⇒ null 并提示失败（两种提示不同）', async () => {
    apiGet.mockResolvedValueOnce({ id: 'p1', audit_year: null, audit_period_end: null, name: '无年度项目' })
    expect(await requireProjectAuditYear('p1', '回填程序表')).toBeNull()
    expect(warn).toHaveBeenLastCalledWith(`${MISSING_AUDIT_YEAR_MESSAGE}（本次回填程序表未提交）`)

    apiGet.mockRejectedValueOnce(new Error('network'))
    expect(await requireProjectAuditYear('p1')).toBeNull()
    expect(warn).toHaveBeenLastCalledWith('读取项目审计年度失败，本次保存未提交，请稍后重试')
  })

  it('没有项目 id 不发请求', async () => {
    expect(await fetchProjectAuditYear('')).toEqual({ year: null, failed: false })
    expect(apiGet).not.toHaveBeenCalled()
  })
})

describe('useProjectAuditYear', () => {
  it('非空结果按实例缓存；并发调用共用一次请求', async () => {
    apiGet.mockResolvedValue({ audit_year: 2025 })
    const { ensureAuditYear, auditYear } = useProjectAuditYear(() => 'p1')
    const [a, b] = await Promise.all([ensureAuditYear(), ensureAuditYear()])
    expect([a, b]).toEqual([2025, 2025])
    expect(await ensureAuditYear()).toBe(2025)
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(auditYear.value).toBe(2025)
  })

  it('null 不缓存：用户填了年度后下一次就能写', async () => {
    apiGet.mockResolvedValueOnce({ audit_year: null }).mockResolvedValueOnce({ audit_year: 2025 })
    const { requireAuditYear } = useProjectAuditYear(() => 'p1')
    expect(await requireAuditYear()).toBeNull()
    expect(warn).toHaveBeenCalledTimes(1)
    expect(await requireAuditYear()).toBe(2025)
    expect(apiGet).toHaveBeenCalledTimes(2)
  })

  it('换项目重取', async () => {
    apiGet.mockImplementation(async (url: string) => ({ audit_year: url.endsWith('/p2') ? 2024 : 2025 }))
    const pid = ref('p1')
    const { ensureAuditYear } = useProjectAuditYear(pid)
    expect(await ensureAuditYear()).toBe(2025)
    pid.value = 'p2'
    expect(await ensureAuditYear()).toBe(2024)
    expect(apiGet).toHaveBeenCalledTimes(2)
  })
})
