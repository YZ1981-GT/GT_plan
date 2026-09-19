/**
 * useAuditCheckReport.spec.ts
 *
 * audit-check-review-gate-hardening Task 4.3
 * 验证前端上报 composable：
 * - reportAuditChecks 调对 URL + body（source + items）+ _silent
 * - 空 items / 缺 projectId·wpId·source → 跳过请求
 * - 请求失败静默不抛（旁路增强，不阻断底稿保存主流程）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/http', () => ({
  default: { post: vi.fn() },
}))

import http from '@/utils/http'
import { useAuditCheckReport, type AuditCheckItemInput } from '../useAuditCheckReport'

const mockPost = vi.mocked(http.post)

const SAMPLE_ITEMS: AuditCheckItemInput[] = [
  {
    code: 'K11-1-vs-TB-6701',
    severity: 'warning',
    check_type: 'balance',
    description: '审定合计与试算表 6701 审定发生额核对',
    message: '审定合计与试算表 6701 一致',
    passed: true,
    actual: 1000,
    expected: 1000,
    diff: 0,
    sheet_hint: 'K11-1',
  },
]

describe('useAuditCheckReport — reportAuditChecks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPost.mockResolvedValue({ data: { reported: 1, source: 'tb_recon', total_checks: 1 } } as any)
  })

  it('正常上报：调对 URL + body(source+items) + _silent', async () => {
    const { reportAuditChecks } = useAuditCheckReport()
    await reportAuditChecks('P1', 'W1', 'tb_recon', SAMPLE_ITEMS)

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body, cfg] = mockPost.mock.calls[0]
    expect(url).toBe('/api/projects/P1/workpapers/W1/audit-checks/report')
    expect(body).toEqual({ source: 'tb_recon', items: SAMPLE_ITEMS })
    expect((cfg as any)?._silent).toBe(true)
  })

  it('URL 自带 /api 前缀（http baseURL=/ 不自动加）', async () => {
    const { reportAuditChecks } = useAuditCheckReport()
    await reportAuditChecks('proj-abc', 'wp-xyz', 'report_cross_check', SAMPLE_ITEMS)
    expect(mockPost.mock.calls[0][0]).toMatch(/^\/api\/projects\/proj-abc\/workpapers\/wp-xyz\/audit-checks\/report$/)
  })

  it('不同 source 各自独立上报（同 source 命名空间）', async () => {
    const { reportAuditChecks } = useAuditCheckReport()
    await reportAuditChecks('P1', 'W1', 'tb_recon', SAMPLE_ITEMS)
    await reportAuditChecks('P1', 'W1', 'adjustment_recon', SAMPLE_ITEMS)
    expect(mockPost).toHaveBeenCalledTimes(2)
    expect((mockPost.mock.calls[0][1] as any).source).toBe('tb_recon')
    expect((mockPost.mock.calls[1][1] as any).source).toBe('adjustment_recon')
  })

  it('空 items 数组 → 跳过请求（不上报空）', async () => {
    const { reportAuditChecks } = useAuditCheckReport()
    await reportAuditChecks('P1', 'W1', 'tb_recon', [])
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('缺 projectId / wpId / source → 跳过请求', async () => {
    const { reportAuditChecks } = useAuditCheckReport()
    await reportAuditChecks('', 'W1', 'tb_recon', SAMPLE_ITEMS)
    await reportAuditChecks('P1', '', 'tb_recon', SAMPLE_ITEMS)
    await reportAuditChecks('P1', 'W1', '', SAMPLE_ITEMS)
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('请求失败静默：不抛错 + console.warn（旁路增强不阻断主流程）', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mockPost.mockRejectedValueOnce(new Error('400 不支持的上报来源'))
    const { reportAuditChecks } = useAuditCheckReport()

    await expect(reportAuditChecks('P1', 'W1', 'tb_recon', SAMPLE_ITEMS)).resolves.toBeUndefined()
    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })

  it('passed 三态透传：true / false / null 原样进 body', async () => {
    const { reportAuditChecks } = useAuditCheckReport()
    const items: AuditCheckItemInput[] = [
      { code: 'a', passed: true },
      { code: 'b', passed: false },
      { code: 'c', passed: null },
    ]
    await reportAuditChecks('P1', 'W1', 'cross_sheet', items)
    expect((mockPost.mock.calls[0][1] as any).items).toEqual(items)
  })
})
